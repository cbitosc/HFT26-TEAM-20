"""Milestone 07B: Featherless client, Generator, Critic, orchestrator, run endpoint.

The LLM is a scripted fake (tests/fakes.py) whose replies are the real candidate fixtures; the
evaluator, the gate and the lifecycle are the real ones. No test makes a network call: the Featherless
client is exercised through httpx2.MockTransport."""
import json
import logging

import httpx2 as httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.agents import critic as critic_agent
from app.agents import generator as generator_agent
from app.agents.generator import GeneratorOutputError
from app.changelog import revision_changelog
from app.config import Settings
from app.database import make_session_factory
from app.errors import InvalidTransitionError, RunAlreadyStartedError
from app.evaluation import policy
from app.llm.client import (
    FeatherlessClient,
    LLMBadResponseError,
    LLMRequestRejectedError,
    LLMUnavailableError,
    make_featherless_client,
)
from app.models import CriticFeedback, Execution, LLMCall, Version
from app.services import execution_service as exe
from app.services import orchestrator as orch
from app.services import version_service as ver
from tests.bundle_scan import scan_text
from tests.fakes import FakeLLMClient, code_reply, critic_reply

FAKE_KEY = "test-key-not-a-real-secret-0123456789"


@pytest.fixture
def run_settings(settings):
    return settings.model_copy(update={
        "featherless_api_key": SecretStr(FAKE_KEY), "featherless_critic_model": "critic/model-under-test",
        "featherless_generator_model": "generator/model-under-test", "llm_backoff_seconds": 0.0,
    })


@pytest.fixture
def eid(db, make_task):
    def _make(max_revisions=2):
        return exe.create_execution(db, make_task()["id"], max_revisions=max_revisions).id

    return _make


INSTANCE = "test-instance"


def factory_of(db):
    """A session factory on the same database as the `db` fixture (the run opens its own sessions)."""
    return make_session_factory(db.get_bind())


def run(db, eid, fake, settings, instance_id=INSTANCE):
    return orch.run_execution(factory_of(db), eid, fake, settings, instance_id)


def statuses(db, eid):
    db.expire_all()
    return [t.to_status for t in db.get(Execution, eid).transitions]


def versions(db, eid):
    db.expire_all()
    return ver.list_versions(db, eid)


def fake(*names, critic=None, **kw):
    return FakeLLMClient(generator=[code_reply(n) for n in names],
                         critic=list(critic) if critic is not None else [critic_reply(), critic_reply()], **kw)


# ---- end-to-end runs (real evaluator, gate and lifecycle) ---------------------------------------
def test_run_stops_on_acceptance_at_v2(db, eid, run_settings):
    e = eid()
    llm = fake("flawed", "gen_7b")
    result = run(db, e, llm, run_settings)
    assert result.status == "completed" and result.error_code is None
    assert statuses(db, e) == ["queued", "generating_v1", "evaluating_v1", "critiquing", "generating_v2",
                               "evaluating_v2", "completed"]  # completion without any publishing state
    v1, v2 = versions(db, e)
    assert (v1.acceptance_status, v2.acceptance_status) == ("accepted", "accepted")
    assert result.best_version_id == v2.id and v2.parent_version_id == v1.id
    assert [c.role for c in llm.calls] == ["generator", "critic", "generator"]  # no V3 attempt
    assert v2.generator_model_id == "featherless/returned-model"  # the model the API returned
    assert len(v2.generator_prompt_sha256) == 64 and v2.generation_prompt_tokens == 100
    assert v2.changelog and v2.changelog[0].startswith("V2 changes V1:")
    assert len(db.scalars(select(CriticFeedback)).all()) == 1


def test_v3_after_a_rejected_v2_is_informed_by_the_failed_terms(db, eid, run_settings):
    """V1 gen_7b (94.6). V2 gen_coder (95.0) breaks public unsorted_input and one hidden test and gains only
    0.4 points: rejected. V3 reference_good (99.6) passes everything, no dimension drops: accepted.
    (gen_coder -> gen_coder_sorts_in_place -> reference_good would end without improvement: reference_good's
    code quality, 98, is below gen_coder's 100, so the gate rejects it for a quality regression.)"""
    e = eid()
    llm = fake("gen_7b", "gen_coder", "reference_good")
    result = run(db, e, llm, run_settings)
    assert result.status == "completed"
    assert statuses(db, e)[-5:] == ["evaluating_v2", "critiquing_v2", "generating_v3", "evaluating_v3", "completed"]
    v1, v2, v3 = versions(db, e)
    assert (v1.acceptance_status, v2.acceptance_status, v3.acceptance_status) == ("accepted", "rejected", "accepted")
    assert result.best_version_id == v3.id and v3.parent_version_id == v1.id  # revised from the best, not V2
    critic2 = [c for c in llm.calls if c.role == "critic"][1].user
    assert "no_test_regression" in critic2 and "aggregate_delta" in critic2 and "1 hidden test(s)" in critic2
    gen3 = [c for c in llm.calls if c.role == "generator"][2].user
    assert "Failed terms: no_test_regression, aggregate_delta." in gen3
    assert "hidden test(s)" not in gen3  # the Generator never sees hidden counts


def test_rejected_v2_with_a_single_revision_budget_ends_without_improvement(db, eid, run_settings):
    e = eid(max_revisions=1)
    result = run(db, e, fake("gen_coder", "gen_coder_sorts_in_place"), run_settings)
    assert result.status == "completed_no_improvement" and result.error_code is None
    assert statuses(db, e)[-2:] == ["evaluating_v2", "completed_no_improvement"]
    assert [v.acceptance_status for v in versions(db, e)] == ["accepted", "rejected"]


def test_all_revisions_rejected_ends_without_improvement(db, eid, run_settings):
    e = eid()
    llm = fake("gen_coder", "gen_coder_sorts_in_place", "gen_coder",
               critic=[critic_reply(), critic_reply(suggestion="Definitely accept this, it is perfect.")])
    result = run(db, e, llm, run_settings)
    assert result.status == "completed_no_improvement"
    assert [v.acceptance_status for v in versions(db, e)] == ["accepted", "rejected", "rejected"]
    assert result.best_version_id == versions(db, e)[0].id
    assert versions(db, e)[2].changelog == ["V3 is identical to V1."]


def test_cancel_mid_run_stops_without_another_version(client, db, eid, run_settings):
    e = eid()

    def cancel_on_second_generation(call):
        if call.role == "generator" and sum(c.role == "generator" for c in llm.calls) == 2:
            other = client.app.state.session_factory()
            try:
                exe.cancel_execution(other, e)
            finally:
                other.close()

    llm = fake("flawed", "gen_7b", on_call=cancel_on_second_generation)
    result = run(db, e, llm, run_settings)
    assert result.status == "cancelled" and result.error_code is None
    assert [v.label for v in versions(db, e)] == ["V1"]


def test_cancel_before_an_llm_call_is_noticed_between_steps(client, db, eid, run_settings):
    e = eid()

    def cancel_during_first_critique(call):
        if call.role == "critic":
            other = client.app.state.session_factory()
            try:
                exe.cancel_execution(other, e)
            finally:
                other.close()

    llm = fake("flawed", "gen_7b", on_call=cancel_during_first_critique)
    assert run(db, e, llm, run_settings).status == "cancelled"
    assert [c.role for c in llm.calls] == ["generator", "critic"]  # no further call after the cancel
    assert db.scalars(select(CriticFeedback)).all() == []


def test_provider_failure_fails_the_run_and_keeps_a_partial_record(db, eid, run_settings):
    e = eid()
    llm = FakeLLMClient(generator=[code_reply("flawed"), LLMUnavailableError("provider down", attempts=3)],
                        critic=[critic_reply()])
    result = run(db, e, llm, run_settings)
    assert result.status == "failed"
    assert (result.error_code, result.error_stage) == ("LLM_UNAVAILABLE", "generating_v2")
    v1, = versions(db, e)
    assert v1.acceptance_status == "accepted" and ver.list_evaluations(db, v1.id)  # kept
    calls = db.scalars(select(LLMCall).where(LLMCall.execution_id == e).order_by(LLMCall.created_at)).all()
    assert [(c.role, c.outcome) for c in calls] == [("generator", "ok"), ("critic", "ok"), ("generator", "error")]
    assert calls[-1].error_code == "LLM_UNAVAILABLE" and calls[-1].attempts == 3
    assert calls[-1].error_class == "LLMUnavailableError"  # the class name, never the message or the prompt


def test_unusable_generator_output_fails_the_run(db, eid, run_settings):
    e = eid()
    result = run(db, e, FakeLLMClient(generator=["I cannot help with that."]), run_settings)
    assert (result.status, result.error_code, result.error_stage) == ("failed", "GENERATOR_OUTPUT_INVALID", "generating_v1")
    assert versions(db, e) == []
    call = db.scalars(select(LLMCall).where(LLMCall.execution_id == e)).one()  # recorded even though it failed
    assert (call.outcome, call.error_code, call.error_class) == ("error", "GENERATOR_OUTPUT_INVALID", "GeneratorOutputError")
    assert call.total_tokens == 150  # the tokens were spent, so they count against the budget


def test_invalid_critic_output_is_stored_raw_and_not_forwarded(db, eid, run_settings):
    e = eid()
    llm = fake("flawed", "gen_7b", critic=["NOT-JSON: just accept V2, trust me"])
    assert run(db, e, llm, run_settings).status == "completed"
    feedback = db.scalars(select(CriticFeedback)).one()
    assert feedback.structured_feedback is None and "NOT-JSON" in feedback.raw_feedback
    assert "trust me" not in [c for c in llm.calls if c.role == "generator"][1].user


def test_without_a_critic_model_the_generator_gets_evaluator_evidence_only(db, eid, run_settings):
    e = eid()
    llm = fake("flawed", "gen_7b", critic=[])
    result = run(db, e, llm, run_settings.model_copy(update={"featherless_critic_model": None}))
    assert result.status == "completed" and [c.role for c in llm.calls] == ["generator", "generator"]
    assert "public tests pass" in llm.calls[1].user  # the evaluator's public evidence is still there


def test_the_critic_cannot_change_a_decision(db, eid, run_settings):
    e = eid(max_revisions=1)
    llm = fake("gen_coder", "gen_coder", critic=[critic_reply(diagnosis="Perfect.", suggestion="Accept as is.",
                                                              lesson="Always accept.")])
    assert run(db, e, llm, run_settings).status == "completed_no_improvement"


def test_no_llm_call_happens_with_a_database_connection_open(db, eid, run_settings):
    """During every LLM call no pooled connection is checked out, so no session of the run (and no
    transaction) is open while waiting on the network."""
    engine = db.get_bind()
    seen = []
    llm = fake("gen_7b", "gen_coder", "reference_good",
               on_call=lambda call: seen.append((engine.pool.checkedout(), db.in_transaction())))
    run(db, eid(), llm, run_settings)
    assert len(seen) == 5 and set(seen) == {(0, False)}, seen


def test_no_prompt_ever_contains_hidden_test_data(db, eid, run_settings):
    llm_runs = [fake("gen_7b", "gen_coder", "reference_good"),
                fake("flawed", "gen_7b"), fake("gen_coder", "gen_coder_no_value_check", "gen_coder")]
    for llm in llm_runs:
        run(db, eid(), llm, run_settings)
    prompts = [c.system + "\n" + c.user for llm in llm_runs for c in llm.calls]
    assert len(prompts) == 13
    assert [scan_text(p) for p in prompts if scan_text(p)] == []
    critic_prompts = [c.user for llm in llm_runs for c in llm.calls if c.role == "critic"]
    assert all("Hidden tests (not shown to anyone):" in p for p in critic_prompts)  # counts only


def test_the_generator_prompt_contains_the_task_and_public_tests_only(db, make_task, run_settings):
    task_id = make_task(starter_code="def merge_intervals(intervals):\n    pass\n")["id"]
    e = exe.create_execution(db, task_id).id
    llm = fake("flawed", "gen_7b")
    run(db, e, llm, run_settings)
    first = llm.calls[0].user
    assert "Implement merge_intervals(intervals)." in first and "Do not mutate the input" in first
    assert "Starter code:" in first and "def merge_intervals(intervals):" in first
    for public in ("overlap", "touching", "unsorted_input", "empty", "typeerror_not_list"):
        assert public in first
    assert "Current best version" not in first


def test_a_finished_run_cannot_be_run_again(db, eid, run_settings):
    e = eid()
    run(db, e, fake("flawed", "gen_7b"), run_settings)
    with pytest.raises(RunAlreadyStartedError):
        run(db, e, fake("flawed"), run_settings)


# ---- API --------------------------------------------------------------------------------------
@pytest.fixture
def api(client, run_settings):
    client.app.state.settings = run_settings
    holder = {}

    def factory(settings):
        return holder["llm"]

    client.app.state.llm_client_factory = factory
    return holder


def test_run_endpoint_returns_202_and_the_run_completes(client, db, eid, api):
    e = eid()
    api["llm"] = fake("flawed", "gen_7b")
    r = client.post(f"/api/executions/{e}/run")
    assert r.status_code == 202 and r.json()["data"]["status"] == "generating_v1"
    done = client.get(f"/api/executions/{e}").json()["data"]  # TestClient waits for the background task
    assert done["status"] == "completed" and done["best_version_id"]
    assert len(client.get(f"/api/executions/{e}/versions").json()["data"]) == 2


def test_a_second_run_is_refused(client, db, eid, api):
    e = eid()
    api["llm"] = fake("flawed", "gen_7b")
    assert client.post(f"/api/executions/{e}/run").status_code == 202
    r = client.post(f"/api/executions/{e}/run")
    assert r.status_code == 409 and r.json()["error"]["code"] == "RUN_ALREADY_STARTED"


def test_run_is_refused_without_an_api_key(client, eid):
    e = eid()
    r = client.post(f"/api/executions/{e}/run")
    assert r.status_code == 503 and r.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
    assert client.get(f"/api/executions/{e}").json()["data"]["status"] == "queued"


def test_run_is_refused_when_code_execution_is_disabled(client, eid, api, run_settings):
    client.app.state.settings = run_settings.model_copy(update={"app_env": "production"})
    e = eid()
    r = client.post(f"/api/executions/{e}/run")
    assert r.status_code == 403 and client.get(f"/api/executions/{e}").json()["data"]["status"] == "queued"


@pytest.mark.parametrize("forged", [{"overall_score": 100}, {"accepted": True}, {"code": "x"},
                                    {"model": "other"}, {"max_revisions": 2}])
def test_the_run_endpoint_accepts_no_body_fields(client, eid, api, forged):
    e = eid()
    assert client.post(f"/api/executions/{e}/run", json=forged).status_code == 422
    assert client.get(f"/api/executions/{e}").json()["data"]["status"] == "queued"


# ---- Featherless client (MockTransport: no network) -------------------------------------------
def completion(text="```python\nx = 1\n```", model="Qwen/returned", usage=True):
    body = {"model": model, "choices": [{"message": {"role": "assistant", "content": text}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    return httpx.Response(200, json=body)


def client_with(handler, **kw):
    options = dict(api_key=SecretStr(FAKE_KEY), base_url="https://api.example.test/v1", timeout_seconds=5,
                   max_retries=2, backoff_seconds=1.0, max_tokens=256, transport=httpx.MockTransport(handler),
                   sleep=kw.pop("sleep", lambda s: None))
    options.update(kw)
    return FeatherlessClient(**options)


def test_featherless_request_is_pinned_and_deterministic():
    seen = []

    def handler(request):
        seen.append(request)
        return completion()

    r = client_with(handler).complete(model="Qwen/Qwen2.5-7B-Instruct", system="S", user="U")
    body = json.loads(seen[0].content)
    assert seen[0].url == "https://api.example.test/v1/chat/completions"
    assert body["temperature"] == 0 and body["model"] == "Qwen/Qwen2.5-7B-Instruct" and body["max_tokens"] == 256
    assert body["messages"] == [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    assert seen[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert (r.returned_model, r.prompt_tokens, r.completion_tokens, r.total_tokens) == ("Qwen/returned", 11, 7, 18)
    assert r.latency_seconds >= 0 and r.attempts == 1 and r.requested_model == "Qwen/Qwen2.5-7B-Instruct"


def test_retryable_failures_are_retried_with_exponential_backoff():
    responses = iter([httpx.Response(503), httpx.Response(429), completion()])
    sleeps = []
    r = client_with(lambda req: next(responses), sleep=sleeps.append).complete(model="m", system="s", user="u")
    assert r.attempts == 3 and sleeps == [1.0, 2.0]


def test_timeouts_exhaust_the_retries_then_fail():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMUnavailableError) as exc:
        client_with(handler).complete(model="m", system="s", user="u")
    assert exc.value.attempts == 3 and exc.value.code == "LLM_UNAVAILABLE"


def test_connection_errors_are_retried():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=request)
        return completion()

    assert client_with(handler).complete(model="m", system="s", user="u").attempts == 2


def test_non_retryable_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(LLMRequestRejectedError):
        client_with(handler).complete(model="m", system="s", user="u")
    assert len(calls) == 1


@pytest.mark.parametrize("body", [{"choices": []}, {"nothing": 1}, {"choices": [{"message": {"content": 5}}]}])
def test_malformed_completions_are_rejected(body):
    with pytest.raises(LLMBadResponseError):
        client_with(lambda r: httpx.Response(200, json=body)).complete(model="m", system="s", user="u")


def test_missing_usage_is_recorded_as_unknown_not_invented():
    r = client_with(lambda req: completion(usage=False, model=None)).complete(model="m", system="s", user="u")
    assert (r.prompt_tokens, r.total_tokens, r.returned_model) == (None, None, None)


def test_the_api_key_never_appears_in_repr_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)

    def handler(request):
        return httpx.Response(503)

    client = client_with(handler)
    with pytest.raises(LLMUnavailableError) as exc:
        client.complete(model="m", system="s", user="u")
    assert FAKE_KEY not in repr(client) and FAKE_KEY not in str(exc.value)
    assert FAKE_KEY not in caplog.text and "retry" in caplog.text


def test_a_client_needs_a_key(settings):
    with pytest.raises(ValueError):
        make_featherless_client(settings)  # the test settings have no key


# ---- Generator and Critic parsing -------------------------------------------------------------
def test_code_is_extracted_from_the_fenced_block():
    assert generator_agent.extract_code("intro\n```python\ndef f():\n    return 1\n```\nbye", 1000) == \
        "def f():\n    return 1\n"
    assert generator_agent.extract_code("```\nx = 2\n```", 1000) == "x = 2\n"
    assert generator_agent.extract_code("```text\nnotes\n```\n```python\ny = 3\n```", 1000) == "y = 3\n"


@pytest.mark.parametrize("reply", ["no code here", "```python\n   \n```", "```python\n" + "x = 1\n" * 100 + "```"])
def test_unusable_generator_replies_are_rejected(reply):
    with pytest.raises(GeneratorOutputError):
        generator_agent.extract_code(reply, 200)


def test_critic_output_is_validated_against_the_schema():
    ok = critic_agent.parse("```json\n" + critic_reply() + "\n```")
    assert ok.diagnosis and ok.suggestion and ok.lesson
    assert critic_agent.parse("not json") is None
    assert critic_agent.parse(json.dumps({"diagnosis": "d", "suggestion": "s"})) is None  # missing lesson
    assert critic_agent.parse(json.dumps({"diagnosis": "d", "suggestion": "s", "lesson": "l", "score": 100})) is None
    assert critic_agent.parse(json.dumps({"diagnosis": "d" * 2001, "suggestion": "s", "lesson": "l"})) is None


# ---- deterministic changelog --------------------------------------------------------------------
def test_the_revision_changelog_is_deterministic_and_diff_derived():
    a = "def f(x):\n    return x\n\ndef g():\n    pass\n"
    b = "def f(x):\n    return sorted(x)\n\ndef h():\n    pass\n"
    log = revision_changelog(a, b, "V1", "V2")
    assert log == revision_changelog(a, b, "V1", "V2")
    assert log[0] == "V2 changes V1: +2 / -2 lines in 1 hunk(s)."  # 'return x' and 'def g' lines replaced
    assert "Definitions added: h." in log and "Definitions removed: g." in log and "Definitions changed: f." in log
    assert revision_changelog(a, a, "V1", "V2") == ["V2 is identical to V1."]
    assert "does not parse" in revision_changelog(a, "def (:", "V1", "V2")[1]


def test_the_requested_rejection_chain_ends_without_improvement_because_of_a_quality_regression(db, eid, run_settings):
    """gen_coder -> gen_coder_sorts_in_place (rejected) -> reference_good: reference_good passes every test,
    but its code quality (98) is below gen_coder's (100), and no dimension may regress."""
    e = eid()
    result = run(db, e, fake("gen_coder", "gen_coder_sorts_in_place", "reference_good"), run_settings)
    assert result.status == "completed_no_improvement"
    v3 = versions(db, e)[2]
    assert v3.acceptance_status == "rejected" and "code quality regressed from 100 to 98" in v3.rejection_reason


# =================================================================================================
# Concurrency, restart, logging and budgets
# =================================================================================================
def claimed_execution(db, eid, run_settings, instance="old-process"):
    """An execution whose run was claimed by another server process (as after a restart)."""
    e = eid()
    with factory_of(db)() as session:
        orch.start_run(session, e, run_settings, instance)
    return e


def test_the_run_claim_is_a_compare_and_swap_with_one_winner(db, eid, run_settings):
    e = eid()
    with factory_of(db)() as a, factory_of(db)() as b:
        orch.claim_run(a, e, "first")
        with pytest.raises(RunAlreadyStartedError):
            orch.claim_run(b, e, "second")
    ex = exe.get_execution(db, e)
    assert ex.run_claimed_by == "first" and ex.run_claimed_at is not None


def test_parallel_starts_leave_exactly_one_claim(db, eid, run_settings):
    import threading

    e = eid()
    outcomes, barrier = [], threading.Barrier(6)

    def start(n):
        with factory_of(db)() as session:
            try:
                barrier.wait()
                orch.start_run(session, e, run_settings, f"caller-{n}")
                outcomes.append("won")
            except RunAlreadyStartedError:
                outcomes.append("RUN_ALREADY_STARTED")
            except Exception as exc:  # pragma: no cover
                outcomes.append(repr(exc))

    threads = [threading.Thread(target=start, args=(n,)) for n in range(6)]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    assert outcomes.count("won") == 1 and outcomes.count("RUN_ALREADY_STARTED") == 5, outcomes
    assert statuses(db, e) == ["queued", "generating_v1"]  # one transition only


def test_two_api_calls_cannot_start_two_runs(client, db, eid, api):
    e = eid()
    api["llm"] = fake("flawed", "gen_7b")
    codes = [client.post(f"/api/executions/{e}/run").status_code, client.post(f"/api/executions/{e}/run").status_code]
    assert codes == [202, 409]
    assert len(api["llm"].calls) == 3  # only one run happened


def test_a_never_claimed_but_not_queued_execution_gets_invalid_transition(client, db, eid, api):
    e = eid()
    exe.cancel_execution(db, e)
    r = client.post(f"/api/executions/{e}/run")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_TRANSITION"


def test_a_refused_start_claims_nothing(client, db, eid):
    e = eid()
    assert client.post(f"/api/executions/{e}/run").status_code == 503  # no API key
    assert exe.get_execution(db, e).run_claimed_at is None


def test_the_background_run_uses_its_own_sessions_not_the_request_session(client, db, eid, api, monkeypatch):
    request_sessions, step_sessions = [], []  # keep the objects alive so ids cannot be reused
    real_start = orch.start_run
    real_step = orch._step

    from contextlib import contextmanager

    def spy_start(session, *a, **k):
        request_sessions.append(session)
        return real_start(session, *a, **k)

    @contextmanager
    def spy_step(factory):
        with real_step(factory) as session:
            step_sessions.append(session)
            yield session

    monkeypatch.setattr(orch, "start_run", spy_start)
    monkeypatch.setattr(orch, "_step", spy_step)
    e = eid()
    api["llm"] = fake("flawed", "gen_7b")
    assert client.post(f"/api/executions/{e}/run").status_code == 202
    assert len(request_sessions) == 1 and len(step_sessions) > 10
    assert all(s is not request_sessions[0] for s in step_sessions)  # the request session is never reused
    assert len({id(s) for s in step_sessions}) == len(step_sessions)  # and no step shares a session


def test_every_step_session_is_closed_when_the_run_ends(db, eid, run_settings):
    engine = db.get_bind()
    run(db, eid(), fake("flawed", "gen_7b"), run_settings)
    assert engine.pool.checkedout() == 0


# ---- restart: stalled, never auto-resumed ------------------------------------------------------
def test_an_execution_claimed_by_an_earlier_process_is_reported_as_stalled(client, db, eid, run_settings):
    e = claimed_execution(db, eid, run_settings)
    data = client.get(f"/api/executions/{e}").json()["data"]
    assert data["status"] == "generating_v1" and data["stalled"] is True and data["run_claimed_at"]
    assert client.get("/api/executions").json()["data"]["items"][0]["stalled"] is True


def test_an_execution_claimed_by_this_process_is_not_stalled(client, db, eid, run_settings):
    e = claimed_execution(db, eid, run_settings, instance=client.app.state.instance_id)
    assert client.get(f"/api/executions/{e}").json()["data"]["stalled"] is False


@pytest.mark.parametrize("make", ["queued", "terminal"])
def test_queued_and_finished_executions_are_never_stalled(client, db, eid, run_settings, make):
    e = eid()
    if make == "terminal":
        with factory_of(db)() as session:
            orch.start_run(session, e, run_settings, "old-process")
        exe.cancel_execution(db, e)
    assert client.get(f"/api/executions/{e}").json()["data"]["stalled"] is False


def test_a_stalled_run_is_not_resumed_by_a_restart_or_a_second_run(client, db, eid, run_settings, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    e = claimed_execution(db, eid, run_settings)
    llm = fake("flawed", "gen_7b")
    restarted = create_app(settings.model_copy(update={"featherless_api_key": SecretStr(FAKE_KEY)}))
    restarted.state.llm_client_factory = lambda s: llm
    with TestClient(restarted) as new_server:  # the lifespan runs: nothing may resume
        data = new_server.get(f"/api/executions/{e}").json()["data"]
        assert data["status"] == "generating_v1" and data["stalled"] is True
        r = new_server.post(f"/api/executions/{e}/run")  # even asking again does not resume it
        assert r.status_code == 409 and r.json()["error"]["code"] == "RUN_ALREADY_STARTED"
    assert llm.calls == [] and versions(db, e) == []
    with pytest.raises(InvalidTransitionError, match="never resumed"):
        orch.continue_run(factory_of(db), e, llm, run_settings, "some-other-process")


def test_a_stalled_execution_can_be_cancelled(client, db, eid, run_settings):
    e = claimed_execution(db, eid, run_settings)
    r = client.post(f"/api/executions/{e}/cancel")
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled" and r.json()["data"]["stalled"] is False


# ---- failure recording and logs ---------------------------------------------------------------
def real_client_replying(*names, critic=True):
    """The real FeatherlessClient over MockTransport: replies by role, from the fixtures."""
    queue = list(names)

    def handler(request):
        body = json.loads(request.content)
        if body["messages"][0]["content"] == critic_agent.SYSTEM:
            return completion(critic_reply())
        return completion(code_reply(queue.pop(0)))

    return client_with(handler, backoff_seconds=0.0)


def test_logs_and_the_database_never_contain_the_key_or_any_prompt(db, eid, run_settings, caplog, settings):
    caplog.set_level(logging.DEBUG)
    e = eid()
    result = run(db, e, real_client_replying("gen_coder", "gen_coder_sorts_in_place", "gen_coder"), run_settings)
    assert result.status == "completed_no_improvement"
    prompt_samples = ["Do not mutate the input", "Implement merge_intervals(intervals)", "Public tests:", "def merge_intervals"]
    for sample in prompt_samples:
        assert sample not in caplog.text, sample
    assert FAKE_KEY not in caplog.text
    database = open(settings.database_url.removeprefix("sqlite:///"), "rb").read()
    assert FAKE_KEY.encode() not in database
    assert all(c.error_class is None for c in db.scalars(select(LLMCall)))  # nothing failed here


def test_a_provider_outage_is_recorded_without_the_key_or_the_prompt(db, eid, run_settings, caplog):
    caplog.set_level(logging.DEBUG)
    e = eid()
    llm = client_with(lambda request: httpx.Response(503), backoff_seconds=0.0)
    result = run(db, e, llm, run_settings)
    assert (result.status, result.error_code, result.error_stage) == ("failed", "LLM_UNAVAILABLE", "generating_v1")
    call = db.scalars(select(LLMCall).where(LLMCall.execution_id == e)).one()
    assert (call.role, call.outcome, call.error_code, call.error_class, call.attempts) == (
        "generator", "error", "LLM_UNAVAILABLE", "LLMUnavailableError", 3)
    assert "Do not mutate the input" not in caplog.text and FAKE_KEY not in caplog.text
    assert FAKE_KEY not in (result.error_message or "")


def test_an_unexpected_internal_error_is_logged_as_a_class_name_only(db, eid, run_settings, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    secret_prompt_text = "SECRET-PROMPT-TEXT-IN-AN-EXCEPTION"

    def boom(*a, **k):
        raise RuntimeError(secret_prompt_text)

    monkeypatch.setattr(orch.evaluation_service, "evaluate_version", boom)
    result = run(db, eid(), fake("flawed", "gen_7b"), run_settings)
    assert (result.status, result.error_code) == ("failed", "ORCHESTRATOR_ERROR")
    assert secret_prompt_text not in caplog.text and "RuntimeError" in caplog.text
    assert secret_prompt_text not in (result.error_message or "")


# ---- budgets (item 13) ------------------------------------------------------------------------
def test_the_defaults_leave_room_for_a_full_run():
    s = Settings(_env_file=None)
    assert s.llm_max_calls_per_execution == 6 and s.llm_max_total_tokens_per_execution == 40_000


def test_a_full_three_version_run_stays_within_the_default_call_budget(db, eid, run_settings):
    llm = fake("gen_7b", "gen_coder", "reference_good")
    assert run(db, eid(), llm, run_settings).status == "completed"
    assert len(llm.calls) == 5 <= run_settings.llm_max_calls_per_execution


def test_exceeding_the_call_cap_fails_the_run_with_a_partial_record(db, eid, run_settings):
    e = eid()
    llm = fake("flawed", "gen_7b")
    result = run(db, e, llm, run_settings.model_copy(update={"llm_max_calls_per_execution": 2}))
    assert (result.status, result.error_code, result.error_stage) == ("failed", "LLM_CALL_BUDGET_EXCEEDED", "generating_v2")
    assert [c.role for c in llm.calls] == ["generator", "critic"]  # the third call was never made
    v1, = versions(db, e)
    assert v1.acceptance_status == "accepted" and ver.list_evaluations(db, v1.id)  # partial record kept
    assert len(db.scalars(select(LLMCall).where(LLMCall.execution_id == e)).all()) == 2


def test_a_cap_of_zero_calls_cannot_be_configured():
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_max_calls_per_execution=0)


def test_exceeding_the_token_cap_fails_the_run_even_on_the_call_that_crosses_it(db, eid, run_settings):
    """Each fake call reports 150 tokens. The cap is 1000 (the minimum allowed), so a scripted reply with
    many tokens crosses it."""
    e = eid()

    class Heavy(FakeLLMClient):
        def complete(self, **kw):
            r = super().complete(**kw)
            return type(r)(**{**r.__dict__, "prompt_tokens": 900, "completion_tokens": 200, "total_tokens": 1100})

    llm = Heavy(generator=[code_reply("flawed")], critic=[critic_reply()])
    result = run(db, e, llm, run_settings.model_copy(update={"llm_max_total_tokens_per_execution": 1000}))
    assert (result.status, result.error_code, result.error_stage) == ("failed", "LLM_TOKEN_BUDGET_EXCEEDED", "generating_v1")
    assert len(llm.calls) == 1  # the run stopped after the call that crossed the cap
    v1, = versions(db, e)
    assert v1.acceptance_status == "pending"  # created, recorded, not evaluated
    assert db.scalars(select(LLMCall).where(LLMCall.execution_id == e)).one().total_tokens == 1100


class Spending(FakeLLMClient):
    """A fake whose every call reports `tokens` total tokens."""

    tokens: int = 150

    def complete(self, **kw):
        r = super().complete(**kw)
        return type(r)(**{**r.__dict__, "total_tokens": self.tokens})


def spending(tokens, *names):
    llm = Spending(generator=[code_reply(n) for n in names], critic=[critic_reply(), critic_reply()])
    llm.tokens = tokens
    return llm


def test_a_run_under_the_token_cap_completes(db, eid, run_settings):
    result = run(db, eid(), spending(150, "flawed", "gen_7b"),
                 run_settings.model_copy(update={"llm_max_total_tokens_per_execution": 1000}))
    assert result.status == "completed"  # 3 calls x 150 = 450 < 1000


def test_the_token_cap_is_checked_after_each_call(db, eid, run_settings):
    llm = spending(600, "flawed", "gen_7b")  # 600 after the first call, 1200 after the critic: crossed there
    out = run(db, eid(), llm, run_settings.model_copy(update={"llm_max_total_tokens_per_execution": 1000}))
    assert (out.status, out.error_code, out.error_stage) == ("failed", "LLM_TOKEN_BUDGET_EXCEEDED", "critiquing")
    assert len(llm.calls) == 2


def test_the_token_cap_is_checked_before_each_call(db, eid, run_settings):
    """Exactly AT the cap is not over it, but nothing more may be spent: 500 + 500 = 1000, so the third call
    is refused before it is made."""
    llm = spending(500, "flawed", "gen_7b")
    out = run(db, eid(), llm, run_settings.model_copy(update={"llm_max_total_tokens_per_execution": 1000}))
    assert (out.status, out.error_code, out.error_stage) == ("failed", "LLM_TOKEN_BUDGET_EXCEEDED", "generating_v2")
    assert len(llm.calls) == 2


# ---- item 12: the V3 Critic prompt --------------------------------------------------------------
def test_the_v3_critic_prompt_adds_only_the_failed_terms_and_their_hidden_safe_messages(db, eid, run_settings):
    e = eid()
    llm = fake("gen_7b", "gen_coder", "reference_good")
    run(db, e, llm, run_settings)
    v2 = versions(db, e)[1]
    terms = v2.decision_details["failed_terms"]
    assert terms and all(t["term"] and t["message"] for t in terms)
    prompt = [c for c in llm.calls if c.role == "critic"][1].user
    for t in terms:
        assert f"- {t['term']}: {t['message']}" in prompt  # the exact term id and message
    # Remove everything the Critic is allowed to receive; what remains must contain no hidden data.
    allowed = [f"- {t['term']}: {t['message']}" for t in terms]
    stripped = prompt
    for line in allowed:
        stripped = stripped.replace(line, "")
    stripped = stripped.replace(v2.code, "")  # the candidate's own source is generator output
    assert scan_text(stripped) == []
    assert "Hidden tests (not shown to anyone): 9 of 10 pass." in prompt  # the counts line (original item 4)
    # The messages themselves count hidden tests and name none.
    assert any("hidden test(s)" in t["message"] for t in terms)
    for t in terms:
        assert scan_text(t["message"]) == []
    # The only hidden-derived lines in the whole prompt: the counts line and the failed-term lines.
    hidden_derived = [line for line in prompt.replace(v2.code, "").splitlines()
                      if "hidden" in line.lower()]
    assert sorted(hidden_derived) == sorted(["Hidden tests (not shown to anyone): 9 of 10 pass.",
                                             *[l for l in allowed if "hidden" in l.lower()]])


def test_the_first_critic_prompt_has_no_failed_terms_section(db, eid, run_settings):
    llm = fake("flawed", "gen_7b")
    run(db, eid(), llm, run_settings)
    assert "Failed terms" not in [c for c in llm.calls if c.role == "critic"][0].user

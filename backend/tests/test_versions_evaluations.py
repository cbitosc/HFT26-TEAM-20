"""Version, evaluation and Critic-feedback persistence and their read endpoints."""
import pytest
from pydantic import ValidationError

from app.errors import ConflictError, NotFoundError
from app.lifecycle import ExecutionStatus as S
from app.schemas.critic_feedback import CriticFeedbackInput
from app.schemas.evaluation import EvaluationInput, OperationalMetricsInput, TestFailureDetail
from app.services import execution_service as exe
from app.services import version_service as ver

CODE_V1 = "def f(x):\n    return x\n"
CODE_V2 = "def f(x):\n    return x + 0\n"


@pytest.fixture
def execution_id(make_execution):
    return make_execution()["id"]


def _eval_input(**kw):
    base = dict(tests_passed=7, tests_total=10, correctness_score=80, code_quality_score=90)
    return EvaluationInput(**{**base, **kw})


# ---- versions --------------------------------------------------------------------------------
def test_versions_are_numbered_and_labelled_in_order(db, execution_id):
    v1 = ver.create_version(db, execution_id, CODE_V1, generator_model_id="gen/model")
    v2 = ver.create_version(db, execution_id, CODE_V2, parent_version_id=v1.id)
    assert (v1.sequence, v1.label, v2.sequence, v2.label) == (1, "V1", 2, "V2")
    assert v1.parent_version_id is None and v2.parent_version_id == v1.id
    assert v1.acceptance_status == "pending" and v1.rejection_reason is None
    assert v1.generator_model_id == "gen/model" and v1.code == CODE_V1
    assert v1.created_at.tzinfo is not None and v1.id != v2.id


def test_version_numbering_is_per_execution(db, make_execution):
    a, b = make_execution()["id"], make_execution()["id"]
    assert ver.create_version(db, a, "x").label == "V1"
    assert ver.create_version(db, b, "y").label == "V1"
    assert ver.create_version(db, a, "z").label == "V2"


def test_version_endpoints(client, db, execution_id):
    v1 = ver.create_version(db, execution_id, CODE_V1)
    v2 = ver.create_version(db, execution_id, CODE_V2, parent_version_id=v1.id)
    listing = client.get(f"/api/executions/{execution_id}/versions").json()["data"]
    assert [v["label"] for v in listing] == ["V1", "V2"]
    one = client.get(f"/api/versions/{v2.id}")
    assert one.status_code == 200
    data = one.json()["data"]
    assert data["code"] == CODE_V2 and data["parent_version_id"] == v1.id
    assert data["execution_id"] == execution_id and data["acceptance_status"] == "pending"


def test_version_rules_are_enforced(db, make_execution, execution_id):
    other = make_execution()["id"]
    foreign_parent = ver.create_version(db, other, "x")
    with pytest.raises(ConflictError):
        ver.create_version(db, execution_id, "y", parent_version_id=foreign_parent.id)
    with pytest.raises(NotFoundError):
        ver.create_version(db, execution_id, "y", parent_version_id="missing")
    with pytest.raises(NotFoundError):
        ver.create_version(db, "missing", "y")
    with pytest.raises(ValueError):
        ver.create_version(db, execution_id, "   ")
    assert ver.list_versions(db, execution_id) == []  # nothing was persisted by the failed calls


def test_versions_cannot_be_added_to_a_finished_execution(db, execution_id):
    exe.cancel_execution(db, execution_id)
    with pytest.raises(ConflictError):
        ver.create_version(db, execution_id, CODE_V1)


def test_acceptance_decisions(db, execution_id):
    v1 = ver.create_version(db, execution_id, CODE_V1)
    v2 = ver.create_version(db, execution_id, CODE_V2)
    assert ver.decide_version(db, v1.id, accepted=True).acceptance_status == "accepted"
    rejected = ver.decide_version(db, v2.id, accepted=False, rejection_reason="  regressed test_overlap  ")
    assert rejected.acceptance_status == "rejected" and rejected.rejection_reason == "regressed test_overlap"
    with pytest.raises(ConflictError):  # decisions are final
        ver.decide_version(db, v1.id, accepted=False, rejection_reason="changed my mind")


def test_acceptance_decision_validation(db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    with pytest.raises(ValueError):
        ver.decide_version(db, v.id, accepted=False)  # a rejection needs a reason
    with pytest.raises(ValueError):
        ver.decide_version(db, v.id, accepted=False, rejection_reason="   ")
    with pytest.raises(ValueError):
        ver.decide_version(db, v.id, accepted=True, rejection_reason="why?")
    assert ver.get_version(db, v.id).acceptance_status == "pending"


def test_best_version_must_be_accepted_and_belong_to_the_execution(db, make_execution, execution_id):
    v1 = ver.create_version(db, execution_id, CODE_V1)
    with pytest.raises(ConflictError):
        exe.set_best_version(db, execution_id, v1.id)  # still pending
    ver.decide_version(db, v1.id, accepted=True)
    other_exec = make_execution()["id"]
    with pytest.raises(ConflictError):
        exe.set_best_version(db, other_exec, v1.id)  # belongs to another execution
    with pytest.raises(NotFoundError):
        exe.set_best_version(db, execution_id, "missing")
    ex = exe.set_best_version(db, execution_id, v1.id)
    assert ex.best_version_id == v1.id


def test_best_version_is_exposed_by_the_api(client, db, execution_id):
    v1 = ver.create_version(db, execution_id, CODE_V1)
    ver.decide_version(db, v1.id, accepted=True)
    exe.set_best_version(db, execution_id, v1.id)
    assert client.get(f"/api/executions/{execution_id}").json()["data"]["best_version_id"] == v1.id


def test_missing_version_endpoints_are_404(client):
    for path in ("", "/evaluations", "/critic-feedback"):
        r = client.get(f"/api/versions/nope{path}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "VERSION_NOT_FOUND"
    r = client.get("/api/executions/nope/versions")
    assert r.status_code == 404 and r.json()["error"]["code"] == "EXECUTION_NOT_FOUND"


# ---- evaluations -----------------------------------------------------------------------------
def test_evaluation_scores_are_derived_with_the_approved_weights(db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    ev = ver.record_evaluation(db, v.id, _eval_input())  # 70% pass, 80 correctness, 90 quality
    assert ev.test_pass_rate == pytest.approx(70.0)
    assert ev.overall_score == pytest.approx(0.5 * 70 + 0.3 * 80 + 0.2 * 90)  # 77
    assert (ev.tests_passed, ev.tests_total) == (7, 10)
    assert ev.operational is None


def test_evaluation_endpoint_separates_deterministic_and_operational(client, db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    ver.record_evaluation(
        db,
        v.id,
        _eval_input(
            failure_details=[
                TestFailureDetail(
                    test_name="touching",
                    expected="returns [(1, 5)]",
                    actual="returned [(1, 3), (3, 5)]",
                    exception=None,
                    traceback_excerpt=["line 6, in merge_intervals: if start < last_end:"],
                )
            ],
            operational=OperationalMetricsInput(
                execution_time_seconds=1.25, prompt_tokens=100, completion_tokens=50, total_tokens=150,
                api_cost_usd=0.0004, api_cost_source="provider_reported",
            ),
        ),
    )
    items = client.get(f"/api/versions/{v.id}/evaluations").json()["data"]
    assert len(items) == 1
    e = items[0]
    assert e["deterministic"] == {
        "tests_passed": 7, "tests_total": 10, "test_pass_rate": 70.0,
        "correctness_score": 80.0, "code_quality_score": 90.0, "overall_score": pytest.approx(77.0),
    }
    assert e["operational"] == {
        "execution_time_seconds": 1.25, "prompt_tokens": 100, "completion_tokens": 50,
        "total_tokens": 150, "api_cost_usd": 0.0004, "api_cost_source": "provider_reported",
    }
    assert e["failure_details"][0]["test_name"] == "touching"
    assert e["failure_details"][0]["traceback_excerpt"] == ["line 6, in merge_intervals: if start < last_end:"]
    assert not set(e["deterministic"]) & set(e["operational"])  # no field is in both groups


def test_operational_metrics_never_change_the_deterministic_score(db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    cheap = ver.record_evaluation(db, v.id, _eval_input())
    costly = ver.record_evaluation(
        db, v.id,
        _eval_input(operational=OperationalMetricsInput(
            execution_time_seconds=999, total_tokens=10**6, api_cost_usd=50, api_cost_source="estimated")),
    )
    assert cheap.overall_score == costly.overall_score


def test_evaluation_history_is_kept_in_order(client, db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    first = ver.record_evaluation(db, v.id, _eval_input(tests_passed=5))
    second = ver.record_evaluation(db, v.id, _eval_input(tests_passed=9))
    ids = [e["id"] for e in client.get(f"/api/versions/{v.id}/evaluations").json()["data"]]
    assert ids == [first.id, second.id]


def test_version_with_no_evaluations_returns_an_empty_list(client, db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    r = client.get(f"/api/versions/{v.id}/evaluations")
    assert r.status_code == 200 and r.json()["data"] == []


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(tests_passed=11),  # more passed than total
        dict(tests_passed=-1),
        dict(tests_total=0),
        dict(correctness_score=100.5),
        dict(correctness_score=-1),
        dict(code_quality_score=101),
        dict(operational=dict(prompt_tokens=-5)),
        dict(operational=dict(api_cost_usd=0.1)),  # cost without a source
        dict(operational=dict(api_cost_source="estimated")),  # source without a cost
        dict(operational=dict(api_cost_usd=0.1, api_cost_source="made_up")),
        dict(overall_score=100),  # callers cannot supply the aggregate
        dict(failure_details=[{"test_name": ""}]),
    ],
)
def test_invalid_evaluation_input_is_rejected(kwargs):
    with pytest.raises(ValidationError):
        EvaluationInput(**{"tests_passed": 7, "tests_total": 10, "correctness_score": 80,
                           "code_quality_score": 90, **kwargs})


def test_recording_an_evaluation_for_a_missing_version(db):
    with pytest.raises(NotFoundError):
        ver.record_evaluation(db, "missing", _eval_input())


def test_clients_cannot_write_evaluations_versions_or_feedback(client, db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    forged = {"tests_passed": 10, "tests_total": 10, "correctness_score": 100, "code_quality_score": 100,
              "overall_score": 100}
    for path in (f"/api/versions/{v.id}/evaluations", f"/api/versions/{v.id}/critic-feedback",
                 f"/api/executions/{execution_id}/versions", f"/api/versions/{v.id}"):
        for method in ("post", "put", "patch", "delete"):
            r = client.request(method.upper(), path, json=forged)
            assert r.status_code == 405, (method, path, r.status_code)
    assert client.get(f"/api/versions/{v.id}/evaluations").json()["data"] == []


# ---- critic feedback -------------------------------------------------------------------------
def test_critic_feedback_persistence_and_retrieval(client, db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    fb = ver.record_critic_feedback(
        db, v.id,
        CriticFeedbackInput(
            critic_model_id="some/critic",
            raw_feedback='{"identified_issues": [...]}',
            structured_feedback={"root_cause": "mutates input", "no_issues": False},
            identified_issues=[{"description": "sorts in place", "status": "confirmed"}],
            suggested_changes=["use sorted()"],
            confidence=0.95,
        ),
    )
    items = client.get(f"/api/versions/{v.id}/critic-feedback").json()["data"]
    assert len(items) == 1
    got = items[0]
    assert got["id"] == fb.id and got["critic_model_id"] == "some/critic"
    assert got["raw_feedback"] == '{"identified_issues": [...]}'
    assert got["structured_feedback"] == {"root_cause": "mutates input", "no_issues": False}
    assert got["identified_issues"] == [{"description": "sorts in place", "status": "confirmed"}]
    assert got["suggested_changes"] == ["use sorted()"] and got["confidence"] == 0.95


def test_critic_feedback_may_be_unstructured(client, db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    ver.record_critic_feedback(db, v.id, CriticFeedbackInput(critic_model_id="m", raw_feedback="free text"))
    got = client.get(f"/api/versions/{v.id}/critic-feedback").json()["data"][0]
    assert got["structured_feedback"] is None and got["identified_issues"] is None and got["confidence"] is None


def test_critic_feedback_is_not_an_evaluation_and_does_not_decide_anything(client, db, execution_id):
    v = ver.create_version(db, execution_id, CODE_V1)
    ver.record_critic_feedback(
        db, v.id, CriticFeedbackInput(critic_model_id="m", raw_feedback="looks great", confidence=1.0)
    )
    assert client.get(f"/api/versions/{v.id}/evaluations").json()["data"] == []
    assert ver.get_version(db, v.id).acceptance_status == "pending"


@pytest.mark.parametrize("kwargs", [dict(confidence=1.5), dict(confidence=-0.1), dict(raw_feedback=""), dict(critic_model_id="")])
def test_invalid_critic_feedback_is_rejected(kwargs):
    with pytest.raises(ValidationError):
        CriticFeedbackInput(**{"critic_model_id": "m", "raw_feedback": "x", **kwargs})


def test_critic_feedback_requires_an_existing_version(db):
    with pytest.raises(NotFoundError):
        ver.record_critic_feedback(db, "missing", CriticFeedbackInput(critic_model_id="m", raw_feedback="x"))

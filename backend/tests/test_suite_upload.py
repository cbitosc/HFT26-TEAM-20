"""Declarative suite upload: safe parsing, validation, sealing, and end-to-end identical behaviour.

HIDDEN_MARKERS are strings that appear only in the uploaded HIDDEN tests. No API response or log line
in this suite may contain them (checked here and, for bundles, by the autouse conftest scanner)."""
import json
import logging

import pytest
from sqlalchemy import select

from app.models import UploadedSuite
from app.services import suite_service

HIDDEN_VALUE = "hidden_marker_value_zzz"
HIDDEN_ID = "hid_secret_case"


def good_suite(public_extra=None, hidden_extra=None):
    public = [{"id": "pub_overlap", "description": "overlap",
               "checks": [{"kind": "returns", "args": "([(1, 3), (2, 6)],)", "expected": "[(1, 6)]"}]}]
    hidden = [{"id": HIDDEN_ID, "description": f"secret {HIDDEN_VALUE}",
               "checks": [{"kind": "returns", "args": f"(['{HIDDEN_VALUE}'],)", "expected": f"['{HIDDEN_VALUE}']"}]},
              {"id": "hid_empty", "description": "",
               "checks": [{"kind": "returns", "args": "([],)", "expected": "[]"}]}]
    return {
        "entrypoint": "merge_intervals",
        "contract": {"arity": 1, "smoke_args": "([(1, 2)],)", "smoke_type": "list"},
        "public_tests": public + (public_extra or []),
        "hidden_tests": hidden + (hidden_extra or []),
    }


def task_with(suite, **kw):
    return {"title": "Up", "description": "d", "suite": suite, **kw}


# ---- happy path ------------------------------------------------------------------------------
def test_an_uploaded_suite_is_sealed_and_summarised(client, db):
    r = client.post("/api/tasks", json=task_with(good_suite()))
    assert r.status_code == 201, r.text
    summary = r.json()["data"]["suite"]
    assert summary["source"] == "uploaded" and summary["public_test_count"] == 1 and summary["hidden_test_count"] == 2
    assert all(len(summary[h]) == 64 for h in ("suite_hash", "public_suite_hash", "hidden_suite_hash"))
    row = db.scalars(select(UploadedSuite)).one()
    assert HIDDEN_VALUE.encode() not in row.hidden_tests_sealed  # stored encrypted
    assert HIDDEN_VALUE not in json.dumps(row.public_tests)  # the marker is only in hidden tests


def test_the_response_and_task_reads_never_contain_hidden_data(client):
    created = client.post("/api/tasks", json=task_with(good_suite())).json()["data"]
    bodies = [json.dumps(created),
              client.get(f"/api/tasks/{created['id']}").text,
              client.get("/api/tasks").text]
    for body in bodies:
        assert HIDDEN_ID not in body and HIDDEN_VALUE not in body


def test_an_uploaded_suite_evaluates_and_decides_like_a_registered_one(client, db):
    """V1 fails one hidden test; the evaluator decrypts the hidden suite and scores it. The decision
    and counts are produced exactly as for a registered suite."""
    from app.services import evaluation_service as evs
    from app.services import execution_service as exe
    from app.services import version_service as ver

    suite = {
        "entrypoint": "f",
        "contract": {"arity": 1, "smoke_args": "(1,)", "smoke_type": "int"},
        "public_tests": [{"id": "pub1", "description": "", "checks": [{"kind": "returns", "args": "(1,)", "expected": "1"}]}],
        "hidden_tests": [{"id": "hid_double", "description": "",
                          "checks": [{"kind": "returns", "args": "(2,)", "expected": "4"}]},
                         {"id": "hid_zero", "description": "",
                          "checks": [{"kind": "returns", "args": "(0,)", "expected": "0"}]}],
    }
    task = client.post("/api/tasks", json=task_with(suite)).json()["data"]
    ex = exe.create_execution(db, task["id"], settings=client.app.state.settings)
    v1 = ver.create_version(db, ex.id, "def f(x):\n    return x * x\n")  # f(2)=4 ok, f(0)=0 ok, f(1)=1 ok
    stored = evs.evaluate_version(db, v1.id, client.app.state.settings)
    assert (stored.tests_passed, stored.tests_total) == (2, 2) and stored.public_tests_total == 1
    tree = client.get(f"/api/executions/{ex.id}/tree").json()["data"]
    assert tree["versions"][0]["hidden"] == {"passed": 2, "total": 2}
    assert "hid_double" not in client.get(f"/api/executions/{ex.id}/tree").text


# ---- validation / hostile payloads -----------------------------------------------------------
@pytest.mark.parametrize("mutate,fragment", [
    (lambda s: s.update(hidden_tests=[]), "at least 1"),  # no hidden tests (pydantic min_length)
    (lambda s: s.update(public_tests=[]), "at least 1"),  # no public tests
    (lambda s: s["hidden_tests"].__setitem__(0, {**s["hidden_tests"][0], "id": "pub_overlap"}), "shared"),
], ids=["no_hidden", "no_public", "shared_id"])
def test_structural_problems_are_refused(client, mutate, fragment):
    suite = good_suite()
    mutate(suite)
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code == 422


def test_an_id_shared_between_public_and_hidden_is_rejected(client):
    suite = good_suite()
    suite["hidden_tests"][0]["id"] = "pub_overlap"  # same id as the public test
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code == 422 and ("duplicate" in r.text.lower() or "shared" in r.text.lower())


@pytest.mark.parametrize("args,expected", [
    ("__import__('os').system('echo hi')", "1"),       # a call, not a literal
    ("open('x')", "1"),                                 # a call
    ("[1] * 999999999", "1"),                           # an operator expression, not a literal
    ("lambda: 1", "1"),                                 # not a literal
    ("x", "1"),                                          # a name
])
def test_executable_or_non_literal_payloads_are_refused(client, args, expected):
    suite = good_suite()
    suite["hidden_tests"][0]["checks"][0] = {"kind": "returns", "args": f"({args},)", "expected": expected}
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code in (422,) and ("literal" in r.text.lower() or "invalid" in r.text.lower())


def test_an_args_literal_that_is_not_a_tuple_is_refused(client):
    suite = good_suite()
    suite["hidden_tests"][0]["checks"][0] = {"kind": "returns", "args": "[1, 2]", "expected": "1"}  # list, not tuple
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code == 422 and "tuple" in r.text.lower()


def test_deeply_nested_literals_are_refused(client):
    suite = good_suite()
    deep = "[" * 40 + "]" * 40
    suite["hidden_tests"][0]["checks"][0] = {"kind": "returns", "args": f"({deep},)", "expected": "[]"}
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code == 422 and "nested" in r.text.lower()


def test_oversized_literals_are_refused(client):
    suite = good_suite()
    suite["hidden_tests"][0]["checks"][0] = {"kind": "returns", "args": "([" + "1," * 3000 + "],)", "expected": "[]"}
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code == 422


def test_too_many_hidden_tests_are_refused_by_the_delta_rule(client):
    # 50 hidden tests: one hidden test would be worth 50/50 = 1.0 points, not more than DELTA.
    extra = [{"id": f"hid_{i}", "description": "", "checks": [{"kind": "returns", "args": "([],)", "expected": "[]"}]}
             for i in range(48)]
    r = client.post("/api/tasks", json=task_with(good_suite(hidden_extra=extra)))
    assert r.status_code == 422 and "DELTA" in r.text


def test_unknown_check_kind_is_refused(client):
    suite = good_suite()
    suite["hidden_tests"][0]["checks"][0] = {"kind": "teleports", "args": "([],)", "expected": "[]"}
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code == 422


def test_a_bad_exception_name_for_raises_is_refused(client):
    suite = good_suite()
    suite["hidden_tests"][0]["checks"][0] = {"kind": "raises", "args": "(None,)", "expected": "NotARealError"}
    r = client.post("/api/tasks", json=task_with(suite))
    assert r.status_code == 422


# ---- encryption unavailable ------------------------------------------------------------------
def test_upload_is_refused_when_encryption_is_unavailable(client):
    from app.config import Settings

    base = client.app.state.settings
    client.app.state.settings = Settings(_env_file=None, app_env="production",
                                         database_url=base.database_url)  # production, no key
    r = client.post("/api/tasks", json=task_with(good_suite()))
    assert r.status_code == 409 and r.json()["error"]["code"] == "HIDDEN_SUITE_UNAVAILABLE"


def test_no_log_line_during_upload_contains_hidden_data(client, caplog):
    caplog.set_level(logging.DEBUG)
    client.post("/api/tasks", json=task_with(good_suite()))
    assert HIDDEN_ID not in caplog.text and HIDDEN_VALUE not in caplog.text


def test_no_response_body_or_log_line_anywhere_contains_hidden_data(client, db, caplog):
    """Item 6 scan: drive an uploaded suite through a full run and hit every read endpoint; no response
    body and no captured log line may contain any hidden test id or hidden literal value."""
    import logging as _logging

    from pydantic import SecretStr

    from app.services import execution_service as exe
    from app.services import orchestrator as orch
    from tests.fakes import FakeLLMClient, code_reply, critic_reply
    from tests.test_orchestrator import FAKE_KEY, factory_of

    caplog.set_level(_logging.DEBUG)
    run_settings = client.app.state.settings.model_copy(update={
        "featherless_api_key": SecretStr(FAKE_KEY), "featherless_critic_model": "critic/model",
        "llm_backoff_seconds": 0.0})
    client.app.state.settings = run_settings

    # A suite whose entry point is `f`; V1 passes everything so the run completes.
    suite = {
        "entrypoint": "f", "contract": {"arity": 1, "smoke_args": "(1,)", "smoke_type": "int"},
        "public_tests": [{"id": "pub1", "description": "", "checks": [{"kind": "returns", "args": "(1,)", "expected": "1"}]}],
        "hidden_tests": [{"id": HIDDEN_ID, "description": f"secret {HIDDEN_VALUE}",
                          "checks": [{"kind": "returns", "args": f"(2,)", "expected": "2"}]},
                         {"id": "hid_b", "description": "", "checks": [{"kind": "returns", "args": "(3,)", "expected": "3"}]}],
    }
    task = client.post("/api/tasks", json=task_with(suite)).json()["data"]
    eid = exe.create_execution(db, task["id"], settings=run_settings).id
    identity = "def f(x):\n    return x\n"
    llm = FakeLLMClient(generator=[f"```python\n{identity}\n```", f"```python\n{identity}\n```"],
                        critic=[critic_reply(), critic_reply()])
    orch.run_execution(factory_of(db), eid, llm, run_settings, "scan-instance")

    bodies = [
        client.get("/api/tasks").text, client.get(f"/api/tasks/{task['id']}").text,
        client.get("/api/dashboard/executions").text, client.get(f"/api/executions/{eid}").text,
        client.get(f"/api/executions/{eid}/tree").text, client.get(f"/api/executions/{eid}/evidence").text,
        client.get(f"/api/executions/{eid}/versions").text,
    ]
    for v in client.get(f"/api/executions/{eid}/versions").json()["data"]:
        bodies.append(client.get(f"/api/versions/{v['id']}/evaluations").text)
        bodies.append(client.get(f"/api/versions/{v['id']}/diff").text)
        bodies.append(client.get(f"/api/versions/{v['id']}/critic-feedback").text)
    for marker in (HIDDEN_ID, HIDDEN_VALUE):
        assert all(marker not in b for b in bodies), marker
        assert marker not in caplog.text, marker
    # the prompts sent to the Generator and Critic also never carried the hidden markers
    assert all(HIDDEN_ID not in c.user and HIDDEN_VALUE not in c.user for c in llm.calls)


# ---- tamper detection at evaluation ----------------------------------------------------------
def test_a_tampered_stored_suite_is_refused_at_evaluation(client, db):
    from sqlalchemy import update
    from app.services import evaluation_service as evs
    from app.services import execution_service as exe
    from app.services import version_service as ver
    from app.errors import EvaluationSuiteUnavailableError, HiddenSuiteUnavailableError  # noqa: F401
    from app import sealing

    task = client.post("/api/tasks", json=task_with(good_suite())).json()["data"]
    ex = exe.create_execution(db, task["id"], settings=client.app.state.settings)
    v1 = ver.create_version(db, ex.id, "def merge_intervals(x):\n    return x\n")
    # Re-seal DIFFERENT hidden tests under the right key: decrypts fine, but the hashes no longer match.
    forged = sealing.encrypt(client.app.state.settings, json.dumps(
        [{"id": "hid_forged", "description": "", "checks": [{"kind": "returns", "args": "([],)", "expected": "[]"}]}]
    ).encode())
    db.execute(update(UploadedSuite).values(hidden_tests_sealed=forged))
    db.commit()
    with pytest.raises(Exception) as exc:  # EvaluationSuiteUnavailableError
        evs.evaluate_version(db, v1.id, client.app.state.settings)
    assert "no longer matches" in str(exc.value)


def test_suite_service_refuses_a_row_whose_hashes_no_longer_match_its_content(client, db):
    """Defense in depth: evaluation_suite() recomputes the hashes of a reconstructed uploaded suite and
    refuses it if they differ from the hashes stored at upload, even before any execution is involved."""
    from sqlalchemy import update
    from app.errors import EvaluationSuiteUnavailableError
    from app.services import suite_service

    client.post("/api/tasks", json=task_with(good_suite()))
    row = db.scalars(select(UploadedSuite)).one()
    # Tamper a stored public test but leave the stored suite_hash untouched -> recomputed hash differs.
    tampered = [dict(row.public_tests[0], id="pub_tampered")]
    db.execute(update(UploadedSuite).where(UploadedSuite.id == row.id).values(public_tests=tampered))
    db.commit()
    with pytest.raises(EvaluationSuiteUnavailableError, match="no longer matches"):
        suite_service.evaluation_suite(db, row.id, client.app.state.settings)

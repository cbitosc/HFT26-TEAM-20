"""Dashboard-facing read endpoints and CORS. All read-only and hidden-safe."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import execution_service as exe
from app.services import orchestrator as orch
from tests.fakes import FakeLLMClient, code_reply, critic_reply
from tests.test_orchestrator import FAKE_KEY, factory_of


@pytest.fixture
def run_settings(settings):
    from pydantic import SecretStr

    return settings.model_copy(update={"featherless_api_key": SecretStr(FAKE_KEY),
                                       "featherless_critic_model": "critic/model", "llm_backoff_seconds": 0.0})


def completed_run(db, make_task, run_settings):
    eid = exe.create_execution(db, make_task()["id"], max_revisions=2).id
    llm = FakeLLMClient(generator=[code_reply("flawed"), code_reply("gen_7b")],
                        critic=[critic_reply(), critic_reply()])
    orch.run_execution(factory_of(db), eid, llm, run_settings, "dash-instance")
    return eid


# ---- GET /status -----------------------------------------------------------------------------
def test_status_reports_booleans_only(client):
    data = client.get("/api/status").json()["data"]
    assert data == {"featherless_configured": False, "critic_configured": False, "evaluator_mode": "subprocess",
                    "hidden_suite_encryption_available": True, "publishing": "not available"}


def test_status_reflects_configuration(client, run_settings):
    client.app.state.settings = run_settings
    data = client.get("/api/status").json()["data"]
    assert data["featherless_configured"] is True and data["critic_configured"] is True
    assert FAKE_KEY not in client.get("/api/status").text  # never the key itself


def test_status_shows_evaluator_disabled_in_production(client, settings):
    client.app.state.settings = settings.model_copy(update={"app_env": "production"})
    assert client.get("/api/status").json()["data"]["evaluator_mode"] == "disabled"


# ---- GET /dashboard/executions ---------------------------------------------------------------
def test_execution_list_has_title_status_stalled_and_best_hidden_accuracy(client, db, make_task, run_settings):
    eid = completed_run(db, make_task, run_settings)
    items = client.get("/api/dashboard/executions").json()["data"]["items"]
    row = next(e for e in items if e["id"] == eid)
    assert row["task_title"] == "Merge intervals" and row["status"] == "completed" and row["stalled"] is False
    assert row["best_hidden_accuracy"] == 90.0  # gen_7b passes 9 of 10 hidden tests
    assert row["best_version_id"]


def test_execution_list_best_accuracy_is_null_before_any_evaluation(client, make_execution):
    ex = make_execution()
    row = next(e for e in client.get("/api/dashboard/executions").json()["data"]["items"] if e["id"] == ex["id"])
    assert row["best_hidden_accuracy"] is None and row["status"] == "queued"


# ---- GET /executions/{id}/tree ---------------------------------------------------------------
def test_tree_shows_versions_counts_decisions_and_advisory_critic_note(client, db, make_task, run_settings):
    eid = completed_run(db, make_task, run_settings)
    tree = client.get(f"/api/executions/{eid}/tree").json()["data"]
    assert tree["task_title"] == "Merge intervals" and len(tree["versions"]) == 2
    v1, v2 = tree["versions"]
    assert v1["hidden"]["total"] == 10 and v1["public"]["total"] == 5
    assert v2["parent_version_id"] == v1["id"] and v2["acceptance_status"] == "accepted"
    assert v2["generator_model_id"] and v2["generation_prompt_tokens"] is not None
    assert v2["critic_note_kind"] == "advisory"


def test_tree_hides_every_hidden_test_id(client, db, make_task, run_settings):
    from app.evaluation.suites import get_suite

    eid = completed_run(db, make_task, run_settings)
    body = client.get(f"/api/executions/{eid}/tree").text
    for test in get_suite("python-merge-intervals-v1").hidden_tests:
        assert test.id not in body


def test_tree_reports_failed_terms_for_a_rejected_version(client, db, make_task, run_settings):
    eid = exe.create_execution(db, make_task()["id"], max_revisions=1).id
    llm = FakeLLMClient(generator=[code_reply("gen_coder"), code_reply("gen_coder_sorts_in_place")],
                        critic=[critic_reply()])
    orch.run_execution(factory_of(db), eid, llm, run_settings, "dash-instance")
    tree = client.get(f"/api/executions/{eid}/tree").json()["data"]
    v2 = tree["versions"][1]
    assert v2["acceptance_status"] == "rejected" and [t["term"] for t in v2["failed_terms"]]


# ---- GET /versions/{id}/diff -----------------------------------------------------------------
def test_version_diff_against_parent(client, db, make_task, run_settings):
    eid = completed_run(db, make_task, run_settings)
    tree = client.get(f"/api/executions/{eid}/tree").json()["data"]
    v2_id = tree["versions"][1]["id"]
    diff = client.get(f"/api/versions/{v2_id}/diff?against=parent").json()["data"]
    assert diff["against"] == "V1" and diff["unified_diff"].startswith("--- V1")
    assert diff["changelog"] and diff["changelog"][0].startswith("V2 changes V1")


def test_v1_diff_has_no_parent(client, db, make_task, run_settings):
    eid = completed_run(db, make_task, run_settings)
    v1_id = client.get(f"/api/executions/{eid}/tree").json()["data"]["versions"][0]["id"]
    diff = client.get(f"/api/versions/{v1_id}/diff").json()["data"]
    assert diff["against_version_id"] is None and diff["unified_diff"] == ""


# ---- CORS ------------------------------------------------------------------------------------
def test_allowed_origin_is_echoed(client):
    r = client.get("/api/status", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert r.headers.get("access-control-allow-credentials") != "true"


def test_other_origins_are_not_echoed(client):
    r = client.get("/api/status", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") is None


def test_no_wildcard_origin_is_ever_configured():
    from app.main import create_app

    app = create_app(Settings(_env_file=None, app_env="test", database_url="sqlite:///:memory:",
                              cors_allowed_origins="http://localhost:5173, https://dash.example"))
    from starlette.middleware.cors import CORSMiddleware

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors and "*" not in cors[0].kwargs["allow_origins"]
    assert cors[0].kwargs["allow_credentials"] is False


def test_a_custom_allowlist_is_honoured():
    app = create_app_with("https://dash.example")
    with TestClient(app) as c:
        assert c.get("/api/status", headers={"Origin": "https://dash.example"}).headers.get(
            "access-control-allow-origin") == "https://dash.example"
        assert c.get("/api/status", headers={"Origin": "http://localhost:5173"}).headers.get(
            "access-control-allow-origin") is None


def create_app_with(origins: str):
    from cryptography.fernet import Fernet

    from app.main import create_app

    return create_app(Settings(_env_file=None, app_env="test", database_url="sqlite:///:memory:",
                               cors_allowed_origins=origins, hidden_suite_key=Fernet.generate_key().decode()))

"""Application startup, health endpoint, database connectivity, configuration."""
import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_startup_creates_database_and_tables(settings, tmp_path):
    db_file = tmp_path / "test.db"
    assert not db_file.exists()
    with TestClient(create_app(settings)):
        assert db_file.exists()
    tables = {r[0] for r in sqlite3.connect(db_file).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tasks", "executions", "execution_transitions", "versions", "evaluations",
            "evaluation_operational_metrics", "critic_feedback", "agent_memories"} <= tables


def test_startup_creates_missing_database_directories(tmp_path):
    nested = tmp_path / "does" / "not" / "exist" / "yet" / "app.db"
    s = Settings(_env_file=None, database_url=f"sqlite:///{nested.as_posix()}")
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").status_code == 200
    assert nested.exists()


def test_explicit_database_init_command_creates_the_schema(tmp_path):
    """`python -m app.init_db` is documented in the README. Run as a real subprocess: an earlier
    version ran init inside app/database.py, where -m makes the module `__main__` (a second copy
    with its own Base) and left the schema empty."""
    import os
    import subprocess
    import sys

    from app.config import BACKEND_DIR

    db_file = tmp_path / "cli" / "init.db"
    env = {k: v for k, v in os.environ.items() if not k.startswith("FEATHERLESS_")}
    env["DATABASE_URL"] = f"sqlite:///{db_file.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "app.init_db"], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert db_file.exists()
    tables = {r[0] for r in sqlite3.connect(db_file).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tasks", "executions", "versions", "evaluations", "critic_feedback", "agent_memories"} <= tables


def test_startup_is_idempotent_on_existing_database(settings):
    with TestClient(create_app(settings)) as c1:
        task = c1.post("/api/tasks", json={"title": "t", "description": "d",
                                           "evaluation_suite_id": "python-merge-intervals-v1"}).json()["data"]
    with TestClient(create_app(settings)) as c2:  # restart against the same file keeps data
        assert c2.get(f"/api/tasks/{task['id']}").status_code == 200


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "connected"
    assert body["data"]["environment"] == "test"


def test_health_reports_database_failure_without_leaking_details(client, monkeypatch):
    from sqlalchemy.orm import Session

    def boom(self, *a, **k):
        raise OperationalError("SELECT 1", {}, Exception("secret internal path C:/x/y.db"))

    monkeypatch.setattr(Session, "execute", boom)
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "secret" not in r.text and "y.db" not in r.text and "SELECT" not in r.text


def test_database_connectivity_and_foreign_keys_enabled(db):
    assert db.execute(text("SELECT 1")).scalar() == 1
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_api_docs_are_served(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_settings_defaults_and_optional_ai_configuration():
    s = Settings(_env_file=None)
    assert s.featherless_api_key is None  # optional in this milestone
    assert s.featherless_generator_model == "Qwen/Qwen2.5-7B-Instruct"
    assert s.featherless_critic_model is None  # no Critic model is approved
    assert s.api_timeout_seconds == 60
    assert s.database_url.startswith("sqlite:///")


def test_settings_read_environment_and_treat_blank_as_unset(monkeypatch):
    monkeypatch.setenv("FEATHERLESS_CRITIC_MODEL", "some/critic-model")
    monkeypatch.setenv("FEATHERLESS_GENERATOR_MODEL", "some/generator-model")
    monkeypatch.setenv("FEATHERLESS_API_KEY", "")
    s = Settings(_env_file=None)
    assert s.featherless_critic_model == "some/critic-model"
    assert s.featherless_generator_model == "some/generator-model"
    assert s.featherless_api_key is None


def test_api_key_is_never_exposed(monkeypatch, tmp_path):
    secret = "test-secret-value-123"
    monkeypatch.setenv("FEATHERLESS_API_KEY", secret)
    s = Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'k.db').as_posix()}")
    assert s.featherless_api_key.get_secret_value() == secret
    assert secret not in repr(s) and secret not in str(s)
    with TestClient(create_app(s)) as c:
        assert secret not in c.get("/api/health").text
        assert secret not in c.get("/openapi.json").text


def test_non_sqlite_database_url_is_rejected():
    with pytest.raises(ValueError):
        Settings(_env_file=None, database_url="postgresql://u:p@host/db")

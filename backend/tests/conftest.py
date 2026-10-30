"""Every test gets its own app and its own temporary SQLite file; the development DB is never touched."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    """Tests must not depend on a developer's shell (a real FEATHERLESS_API_KEY, DATABASE_URL, ...)."""
    for name in ("APP_ENV", "DATABASE_URL", "FEATHERLESS_API_KEY", "FEATHERLESS_BASE_URL",
                 "FEATHERLESS_GENERATOR_MODEL", "FEATHERLESS_CRITIC_MODEL", "API_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path):
    # _env_file=None: tests must not read a developer's real backend/.env
    return Settings(_env_file=None, app_env="test", database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:  # entering the context runs the lifespan (creates tables)
        yield c


@pytest.fixture
def db(client):
    """A session on the same temp database, for service-level and constraint tests."""
    session = client.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def task_payload():
    return {
        "title": "Merge intervals",
        "description": "Implement merge_intervals(intervals).",
        "requirements": ["Merge overlapping intervals", "Do not mutate the input"],
        "language": "python",
        "category": "algorithms",
    }


@pytest.fixture
def make_task(client, task_payload):
    def _make(**overrides):
        r = client.post("/api/tasks", json={**task_payload, **overrides})
        assert r.status_code == 201, r.text
        return r.json()["data"]

    return _make


@pytest.fixture
def make_execution(client, make_task):
    def _make(task_id=None):
        task_id = task_id or make_task()["id"]
        r = client.post(f"/api/tasks/{task_id}/executions")
        assert r.status_code == 201, r.text
        return r.json()["data"]

    return _make

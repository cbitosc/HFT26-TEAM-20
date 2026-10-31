"""Every test gets its own app and its own temporary SQLite file; the development DB is never touched."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    """Tests must not depend on a developer's shell (a real FEATHERLESS_API_KEY, DATABASE_URL, ...)."""
    for name in ("APP_ENV", "DATABASE_URL", "FEATHERLESS_API_KEY", "FEATHERLESS_BASE_URL",
                 "FEATHERLESS_GENERATOR_MODEL", "FEATHERLESS_CRITIC_MODEL", "API_TIMEOUT_SECONDS",
                 "EVALUATION_TIMEOUT_SECONDS", "EVALUATION_TOTAL_TIMEOUT_SECONDS", "ALLOW_UNSANDBOXED_EVALUATION",
                 "LLM_MAX_RETRIES", "LLM_BACKOFF_SECONDS", "LLM_MAX_TOKENS", "GENERATOR_MAX_CODE_CHARS",
                 "LLM_MAX_CALLS_PER_EXECUTION", "LLM_MAX_TOTAL_TOKENS_PER_EXECUTION",
                 "HIDDEN_SUITE_KEY", "HIDDEN_SUITE_KEY_FILE", "CORS_ALLOWED_ORIGINS",
                 "EVALUATOR_TEMP_MAX_AGE_SECONDS"):
        monkeypatch.delenv(name, raising=False)


def pytest_configure(config):
    """A session backstop: if the whole run wedges, dump every thread's stack after 600s instead of
    stalling silently. The per-test timeout (pytest.ini) catches a single hung test first, at 120s.
    Also sweep any evaluator temp directories orphaned by an earlier hard-killed run (counts only)."""
    import faulthandler

    from app.evaluation.execution import sweep_stale_eval_dirs

    faulthandler.dump_traceback_later(600, exit=True)
    removed = sweep_stale_eval_dirs(3600.0)
    if removed:
        print(f"\n[session start] removed {removed} stale evaluator temp directories")


def pytest_unconfigure(config):
    import faulthandler

    faulthandler.cancel_dump_traceback_later()


@pytest.fixture(autouse=True)
def _no_evaluator_artifacts_survive_a_test():
    """After every test: no evaluator child process is still running, and no evaluator working directory
    created during the test survives. The decrypted hidden-suite file lives inside that working directory
    (written only for the child's lifetime), so this also proves no decrypted hidden tests are left on disk."""
    import tempfile
    from pathlib import Path

    from app.evaluation.execution import EVAL_DIR_PREFIX, live_eval_children

    root = Path(tempfile.gettempdir())

    def eval_dirs() -> set[str]:
        try:
            return {p.name for p in root.iterdir() if p.name.startswith(EVAL_DIR_PREFIX) and p.is_dir()}
        except OSError:
            return set()

    before = eval_dirs()
    yield
    leaked_dirs = eval_dirs() - before
    live = live_eval_children()
    assert not live, f"evaluator child process(es) still running after the test: {live}"
    assert not leaked_dirs, f"evaluator temp directory(ies) left behind by the test: {leaked_dirs}"


@pytest.fixture(autouse=True)
def _no_hidden_test_data_in_any_bundle(tmp_path):
    """After EVERY test, scan every evidence bundle that test wrote for hidden test ids, names and
    inputs. Candidate source (`code`, `diff`) is generator output, not suite data, and is skipped."""
    yield
    from tests.bundle_scan import scan_database

    database = tmp_path / "test.db"
    if database.exists():
        leaks = scan_database(database)
        assert leaks == [], f"hidden test data found in evidence bundles: {leaks}"


@pytest.fixture
def settings(tmp_path):
    # _env_file=None: tests must not read a developer's real backend/.env. A generated key gives every
    # test hidden-suite encryption without touching a key file; the key-file and production-refusal
    # paths have their own dedicated tests.
    from cryptography.fernet import Fernet

    return Settings(_env_file=None, app_env="test",
                    database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
                    hidden_suite_key=Fernet.generate_key().decode(),
                    hidden_suite_key_file=str(tmp_path / ".hidden_suite_key"))


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
        # A run can only start for a task with public + hidden tests (PRD Step 1).
        "evaluation_suite_id": "python-merge-intervals-v1",
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

"""Error responses are uniform and never leak internals."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import create_app


def _assert_envelope(r, status, code):
    assert r.status_code == status
    body = r.json()
    assert set(body) == {"success", "data", "error"}
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == code and body["error"]["message"]
    return body


def test_unknown_route_uses_the_envelope(client):
    _assert_envelope(client.get("/api/nothing-here"), 404, "NOT_FOUND")


def test_wrong_method_uses_the_envelope(client):
    _assert_envelope(client.delete("/api/tasks"), 405, "METHOD_NOT_ALLOWED")


def test_missing_record_messages_name_the_resource_only(client):
    body = _assert_envelope(client.get("/api/tasks/abc"), 404, "TASK_NOT_FOUND")
    assert "abc" in body["error"]["message"]


def test_validation_details_do_not_echo_submitted_values(client):
    r = client.post("/api/tasks", json={"title": "ok", "description": "d", "requirements": "SENSITIVE-INPUT"})
    body = _assert_envelope(r, 422, "VALIDATION_ERROR")
    assert "SENSITIVE-INPUT" not in r.text
    assert all(set(d) == {"field", "message"} for d in body["error"]["details"])


def test_successful_responses_use_the_envelope(client, make_task):
    task = make_task()
    for path in ("/api/health", "/api/tasks", f"/api/tasks/{task['id']}"):
        body = client.get(path).json()
        assert set(body) == {"success", "data", "error"} and body["success"] is True and body["error"] is None


def test_unhandled_exception_returns_generic_500_without_a_traceback(app, monkeypatch):
    from app.services import task_service

    def explode(*a, **k):
        raise RuntimeError("database password is hunter2 at C:\\secret\\path")

    monkeypatch.setattr(task_service, "list_tasks", explode)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/tasks")
    body = _assert_envelope(r, 500, "INTERNAL_ERROR")
    assert "hunter2" not in r.text and "secret" not in r.text and "Traceback" not in r.text
    assert body["error"]["message"] == "An internal error occurred."


def test_integrity_errors_become_a_generic_409(app, monkeypatch):
    from app.services import task_service

    def conflict(*a, **k):
        raise IntegrityError("INSERT INTO tasks ...", {}, Exception("UNIQUE constraint failed: tasks.secret_col"))

    monkeypatch.setattr(task_service, "list_tasks", conflict)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/tasks")
    _assert_envelope(r, 409, "CONFLICT")
    assert "INSERT" not in r.text and "secret_col" not in r.text

"""Execution creation, listing, retrieval and the cancel endpoint."""
import pytest


def test_create_execution_is_queued_and_does_nothing_else(client, make_task):
    task = make_task()
    r = client.post(f"/api/tasks/{task['id']}/executions")
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["task_id"] == task["id"]
    assert data["status"] == "queued"
    assert data["started_at"] is None and data["completed_at"] is None
    assert data["best_version_id"] is None and data["error"] is None
    # No pipeline stage ran: no versions exist.
    assert client.get(f"/api/executions/{data['id']}/versions").json()["data"] == []


def test_create_execution_for_missing_task_is_404(client):
    r = client.post("/api/tasks/does-not-exist/executions")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_get_execution_returns_lifecycle_history(client, make_execution):
    ex = make_execution()
    r = client.get(f"/api/executions/{ex['id']}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == ex["id"] and data["status"] == "queued"
    assert [(t["from_status"], t["to_status"]) for t in data["transitions"]] == [(None, "queued")]
    assert data["transitions"][0]["occurred_at"].endswith("Z")


def test_get_missing_execution_is_404(client):
    r = client.get("/api/executions/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "EXECUTION_NOT_FOUND"


def test_multiple_executions_per_task_have_distinct_ids(client, make_task):
    task = make_task()
    a = client.post(f"/api/tasks/{task['id']}/executions").json()["data"]
    b = client.post(f"/api/tasks/{task['id']}/executions").json()["data"]
    assert a["id"] != b["id"] and a["task_id"] == b["task_id"] == task["id"]


def test_list_executions_filters_and_pagination(client, make_task, make_execution):
    t1, t2 = make_task(), make_task()
    e1, e2, e3 = make_execution(t1["id"]), make_execution(t1["id"]), make_execution(t2["id"])
    assert client.post(f"/api/executions/{e2['id']}/cancel").status_code == 200

    page = client.get("/api/executions").json()["data"]
    assert page["total"] == 3
    assert {e["id"] for e in page["items"]} == {e1["id"], e2["id"], e3["id"]}

    by_task = client.get(f"/api/executions?task_id={t1['id']}").json()["data"]
    assert by_task["total"] == 2
    by_status = client.get("/api/executions?status=cancelled").json()["data"]
    assert [e["id"] for e in by_status["items"]] == [e2["id"]]
    assert client.get("/api/executions?limit=1").json()["data"]["items"].__len__() == 1


def test_list_executions_rejects_unknown_status_filter(client):
    r = client.get("/api/executions?status=bogus")
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cancel_queued_execution(client, make_execution):
    ex = make_execution()
    r = client.post(f"/api/executions/{ex['id']}/cancel")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "cancelled"
    assert data["completed_at"] is not None and data["started_at"] is None
    assert [t["to_status"] for t in data["transitions"]] == ["queued", "cancelled"]


def test_cancelling_twice_is_a_conflict(client, make_execution):
    ex = make_execution()
    client.post(f"/api/executions/{ex['id']}/cancel")
    r = client.post(f"/api/executions/{ex['id']}/cancel")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"


def test_cancel_missing_execution_is_404(client):
    assert client.post("/api/executions/nope/cancel").status_code == 404


@pytest.mark.parametrize("method,path", [("post", "/api/executions"), ("put", "/api/executions/x"), ("delete", "/api/executions/x")])
def test_clients_cannot_create_or_edit_executions_directly(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"

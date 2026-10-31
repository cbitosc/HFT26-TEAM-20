"""Task creation, listing, retrieval and input validation."""
import pytest


def test_create_task(client, task_payload):
    r = client.post("/api/tasks", json=task_payload)
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["title"] == task_payload["title"]
    assert data["requirements"] == task_payload["requirements"]
    assert data["language"] == "python" and data["category"] == "algorithms"
    assert data["status"] == "active"
    assert len(data["id"]) == 36
    assert data["created_at"].endswith("Z") and data["updated_at"].endswith("Z")


def test_create_task_minimal_and_trims_whitespace(client):
    r = client.post("/api/tasks", json={"title": "  Hello  ", "description": " body ", "language": "  ",
                                        "evaluation_suite_id": "python-merge-intervals-v1"})
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["title"] == "Hello" and data["description"] == "body"
    assert data["requirements"] == [] and data["language"] is None


def test_a_task_needs_a_suite(client):
    r = client.post("/api/tasks", json={"title": "t", "description": "d"})
    assert r.status_code == 422 and "needs a suite" in r.text


def test_a_task_cannot_set_both_a_registered_and_an_inline_suite(client):
    r = client.post("/api/tasks", json={"title": "t", "description": "d",
                                        "evaluation_suite_id": "python-merge-intervals-v1",
                                        "suite": {"entrypoint": "f", "contract": {"arity": 1, "smoke_args": "(1,)",
                                                  "smoke_type": "int"}, "public_tests": [], "hidden_tests": []}})
    assert r.status_code == 422


def test_task_ids_are_unique(make_task):
    assert make_task()["id"] != make_task()["id"]


def test_get_task_roundtrip(client, make_task):
    created = make_task()
    r = client.get(f"/api/tasks/{created['id']}")
    assert r.status_code == 200
    assert r.json()["data"] == created


def test_list_tasks_with_pagination(client, make_task):
    ids = [make_task(title=f"task {i}")["id"] for i in range(5)]
    r = client.get("/api/tasks")
    page = r.json()["data"]
    assert page["total"] == 5 and len(page["items"]) == 5
    assert {t["id"] for t in page["items"]} == set(ids)
    page = client.get("/api/tasks?limit=2&offset=1").json()["data"]
    assert page["total"] == 5 and len(page["items"]) == 2 and page["limit"] == 2 and page["offset"] == 1
    assert client.get("/api/tasks?offset=50").json()["data"]["items"] == []


def test_list_tasks_empty(client):
    page = client.get("/api/tasks").json()["data"]
    assert page == {"items": [], "total": 0, "limit": 50, "offset": 0}


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing everything
        {"description": "d"},  # missing title
        {"title": "t"},  # missing description
        {"title": "", "description": "d"},
        {"title": "   ", "description": "d"},
        {"title": "t", "description": ""},
        {"title": "x" * 201, "description": "d"},
        {"title": "t", "description": "d", "requirements": "not a list"},
        {"title": "t", "description": "d", "requirements": [""]},
        {"title": "t", "description": "d", "requirements": ["ok"] * 51},
        {"title": "t", "description": "d", "status": "archived"},  # client cannot set server-owned fields
        {"title": "t", "description": "d", "id": "abc"},
        {"title": 123, "description": "d"},
    ],
)
def test_invalid_task_input_is_rejected(client, payload):
    r = client.post("/api/tasks", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]
    assert client.get("/api/tasks").json()["data"]["total"] == 0  # nothing was stored


def test_malformed_json_body_is_rejected(client):
    r = client.post("/api/tasks", content="{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=abc", "offset=-1"])
def test_invalid_pagination_is_rejected(client, query):
    assert client.get(f"/api/tasks?{query}").status_code == 422

"""Deleting a task removes its entire run subtree, and is refused when evidence was exported."""
import pytest
from sqlalchemy import select

from app.errors import ConflictError, NotFoundError
from app.models import AgentMemory, EvidenceRecord, Execution, Version
from app.services import bundle_service, memory_service, task_service
from tests.helpers import grant_improvement


def test_delete_task_removes_task_and_all_runs(db, make_task, make_execution):
    task = make_task()
    execution = make_execution(task["id"])
    _v1, v2 = grant_improvement(db, execution["id"])
    memory_service.store_lesson(db, v2.id)  # agent memory referencing the execution

    task_service.delete_task(db, task["id"])

    with pytest.raises(NotFoundError):
        task_service.get_task(db, task["id"])
    assert db.get(Execution, execution["id"]) is None
    assert db.scalars(select(Version).where(Version.execution_id == execution["id"])).first() is None
    assert db.scalars(
        select(EvidenceRecord).where(EvidenceRecord.execution_id == execution["id"])
    ).first() is None
    assert db.scalars(
        select(AgentMemory).where(AgentMemory.source_execution_id == execution["id"])
    ).first() is None


def test_delete_task_refused_when_evidence_bundle_exported(db, make_task, make_execution):
    task = make_task()
    execution = make_execution(task["id"])
    _v1, v2 = grant_improvement(db, execution["id"])
    record = db.scalar(select(EvidenceRecord).where(EvidenceRecord.candidate_version_id == v2.id))
    bundle_service.build_or_get_bundle(db, record.id, include_code=True)

    with pytest.raises(ConflictError):
        task_service.delete_task(db, task["id"])
    assert task_service.get_task(db, task["id"]) is not None  # still there


def test_delete_task_endpoint(client, make_task):
    task = make_task()
    r = client.delete(f"/api/tasks/{task['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"] is True
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404

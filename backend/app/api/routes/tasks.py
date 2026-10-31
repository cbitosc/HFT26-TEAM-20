from fastapi import APIRouter, Request

from app.api.deps import DbSession, Limit, Offset
from app.schemas.common import Envelope, Page, ok
from app.schemas.execution import ExecutionRead
from app.schemas.task import TaskCreate, TaskRead
from app.services import execution_service, task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=201, response_model=Envelope[TaskRead])
def create_task(body: TaskCreate, db: DbSession):
    return ok(TaskRead.model_validate(task_service.create_task(db, body)))


@router.get("", response_model=Envelope[Page[TaskRead]])
def list_tasks(db: DbSession, limit: Limit = 50, offset: Offset = 0):
    items, total = task_service.list_tasks(db, limit=limit, offset=offset)
    return ok(Page(items=[TaskRead.model_validate(t) for t in items], total=total, limit=limit, offset=offset))


@router.get("/{task_id}", response_model=Envelope[TaskRead])
def get_task(task_id: str, db: DbSession):
    return ok(TaskRead.model_validate(task_service.get_task(db, task_id)))


@router.post("/{task_id}/executions", status_code=201, response_model=Envelope[ExecutionRead])
def create_execution(task_id: str, request: Request, db: DbSession):
    """Creates a queued execution and records its commitment (suite hashes, evaluator configuration,
    scoring rule, delta) before anything is generated. Nothing runs: no worker or pipeline exists yet.
    Refused with 409 EVALUATION_SUITE_UNAVAILABLE when the task has no evaluation suite."""
    return ok(ExecutionRead.from_model(
        execution_service.create_execution(db, task_id, settings=request.app.state.settings)))

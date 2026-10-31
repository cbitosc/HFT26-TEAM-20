from fastapi import APIRouter, Request

from app.api.deps import DbSession, Limit, Offset
from app.schemas.common import Envelope, Page, ok
from app.schemas.execution import ExecutionRead
from app.schemas.task import TaskCreate, TaskRead
from app.services import dashboard_service, execution_service, task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _read(db, task) -> TaskRead:
    out = TaskRead.model_validate(task)
    out.suite = dashboard_service.suite_summary(db, task.evaluation_suite_id)
    return out


@router.post("", status_code=201, response_model=Envelope[TaskRead])
def create_task(body: TaskCreate, request: Request, db: DbSession):
    """Creates a task with either a registered `evaluation_suite_id` or an inline `suite` (public and
    hidden tests as data). Uploaded hidden tests are sealed before storage; the response returns the
    suite id, counts and hashes only, never hidden test contents."""
    return ok(_read(db, task_service.create_task(db, body, settings=request.app.state.settings)))


@router.get("", response_model=Envelope[Page[TaskRead]])
def list_tasks(db: DbSession, limit: Limit = 50, offset: Offset = 0):
    items, total = task_service.list_tasks(db, limit=limit, offset=offset)
    return ok(Page(items=[_read(db, t) for t in items], total=total, limit=limit, offset=offset))


@router.get("/{task_id}", response_model=Envelope[TaskRead])
def get_task(task_id: str, db: DbSession):
    return ok(_read(db, task_service.get_task(db, task_id)))


@router.post("/{task_id}/executions", status_code=201, response_model=Envelope[ExecutionRead])
def create_execution(task_id: str, request: Request, db: DbSession):
    """Creates a queued execution and records its commitment (suite hashes, evaluator configuration,
    scoring rule, delta) before anything is generated. Nothing runs: no worker or pipeline exists yet.
    Refused with 409 EVALUATION_SUITE_UNAVAILABLE when the task has no evaluation suite."""
    return ok(ExecutionRead.from_model(
        execution_service.create_execution(db, task_id, settings=request.app.state.settings)))

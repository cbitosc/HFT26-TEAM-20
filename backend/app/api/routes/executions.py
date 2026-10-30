from fastapi import APIRouter, Query

from app.api.deps import DbSession, Limit, Offset
from app.lifecycle import ExecutionStatus
from app.schemas.common import Envelope, Page, ok
from app.schemas.execution import ExecutionDetail, ExecutionRead
from app.schemas.version import VersionRead
from app.services import execution_service, version_service

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("", response_model=Envelope[Page[ExecutionRead]])
def list_executions(
    db: DbSession,
    limit: Limit = 50,
    offset: Offset = 0,
    status: ExecutionStatus | None = Query(default=None),
    task_id: str | None = Query(default=None, max_length=64),
):
    items, total = execution_service.list_executions(
        db, limit=limit, offset=offset, status=status.value if status else None, task_id=task_id
    )
    return ok(Page(items=[ExecutionRead.from_model(e) for e in items], total=total, limit=limit, offset=offset))


@router.get("/{execution_id}", response_model=Envelope[ExecutionDetail])
def get_execution(execution_id: str, db: DbSession):
    return ok(ExecutionDetail.from_model(execution_service.get_execution(db, execution_id)))


@router.post("/{execution_id}/cancel", response_model=Envelope[ExecutionDetail])
def cancel_execution(execution_id: str, db: DbSession):
    """Marks a non-terminal execution cancelled. No worker exists yet, so this only changes persisted state."""
    return ok(ExecutionDetail.from_model(execution_service.cancel_execution(db, execution_id)))


@router.get("/{execution_id}/versions", response_model=Envelope[list[VersionRead]])
def list_versions(execution_id: str, db: DbSession):
    return ok([VersionRead.model_validate(v) for v in version_service.list_versions(db, execution_id)])

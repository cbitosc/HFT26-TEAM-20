"""Read-only, hidden-safe endpoints the dashboard needs. None of these decrypts a suite or exposes a
hidden test id, name, input or per-test result; hidden tests appear only as aggregate counts."""
from fastapi import APIRouter, Query, Request

from app.api.deps import DbSession, Limit, Offset
from app.lifecycle import ExecutionStatus
from app.schemas.common import Envelope, Page, ok
from app.schemas.dashboard import ExecutionSummary, ExecutionTree, SystemStatus, VersionDiff
from app.sealing import encryption_available
from app.services import dashboard_service, execution_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/executions", response_model=Envelope[Page[ExecutionSummary]])
def list_execution_summaries(
    request: Request,
    db: DbSession,
    limit: Limit = 50,
    offset: Offset = 0,
    status: ExecutionStatus | None = Query(default=None),
    task_id: str | None = Query(default=None, max_length=64),
):
    """Executions with task title, status, stalled flag and best hidden accuracy, for the home list."""
    items, total = execution_service.list_executions(
        db, limit=limit, offset=offset, status=status.value if status else None, task_id=task_id)
    instance = request.app.state.instance_id
    return ok(Page(items=[dashboard_service.execution_summary(db, e, instance) for e in items],
                   total=total, limit=limit, offset=offset))


@router.get("/executions/{execution_id}/tree", response_model=Envelope[ExecutionTree])
def execution_tree(execution_id: str, request: Request, db: DbSession):
    """The version tree: public and hidden counts, decision, failed terms, parent links, generation
    metadata, and the Critic note flagged advisory."""
    return ok(dashboard_service.execution_tree(db, execution_id, request.app.state.instance_id))


@router.get("/versions/{version_id}/diff", response_model=Envelope[VersionDiff])
def version_diff(version_id: str, db: DbSession, against: str = Query(default="parent", max_length=32)):
    """The unified diff against the parent version and the deterministic changelog."""
    return ok(dashboard_service.version_diff(db, version_id, against))


@router.get("/status", response_model=Envelope[SystemStatus])
def system_status(request: Request):
    """Capability flags for the dashboard. Booleans only: no key, model id or secret is returned."""
    settings = request.app.state.settings
    return ok(SystemStatus(
        featherless_configured=settings.llm_configured,
        critic_configured=bool(settings.featherless_critic_model),
        evaluator_mode="subprocess" if settings.evaluation_execution_allowed else "disabled",
        hidden_suite_encryption_available=encryption_available(settings),
    ))

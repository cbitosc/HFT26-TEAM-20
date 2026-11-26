"""POST /api/executions/{id}/run: start the orchestrator for a queued execution (202, background).

The request body must be empty. The run's progress is read through the existing GET endpoints.
No endpoint accepts scores, verdicts or code claims.

Starting is a compare-and-swap on a "run claimed" marker, so two calls cannot start two runs. The
background task opens its own database sessions and never shares the request's session. A run is not
resumed after a server restart: it is reported as `stalled` instead."""
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbSession
from app.schemas.common import Envelope, ok
from app.schemas.execution import ExecutionRead
from app.services import orchestrator

router = APIRouter(prefix="/executions", tags=["executions"])
log = logging.getLogger("app.orchestrator")


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _run_in_background(app_state, execution_id: str) -> None:
    try:
        llm = app_state.llm_client_factory(app_state.settings)
        orchestrator.continue_run(app_state.session_factory, execution_id, llm, app_state.settings,
                                  app_state.instance_id)
    except Exception as exc:  # pragma: no cover - continue_run records its own failures
        log.error("background run of execution %s crashed (%s)", execution_id, type(exc).__name__)


@router.post("/{execution_id}/run", status_code=202, response_model=Envelope[ExecutionRead])
def run_execution(execution_id: str, request: Request, db: DbSession, background: BackgroundTasks,
                  body: RunRequest | None = None):
    """Claims the run (409 RUN_ALREADY_STARTED if one was ever claimed; 409 INVALID_TRANSITION if the
    execution is not queued), moves it queued -> generating_v1, then continues in the background.
    503 LLM_NOT_CONFIGURED without an API key; 403 when code execution is disabled."""
    state = request.app.state
    execution = orchestrator.start_run(db, execution_id, state.settings, state.instance_id)
    background.add_task(_run_in_background, state, execution.id)
    return ok(ExecutionRead.from_model(execution, state.instance_id))

"""Agent B: cross-agent memory and the transfer experiment (control vs treatment + attestation)."""
from fastapi import APIRouter, BackgroundTasks, Query, Request
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.routes.runs import _run_in_background
from app.models import Attestation
from app.schemas.agent_b import (
    AttestationRead,
    MemoryRead,
    TransferExperimentRead,
    TransferExperimentRequest,
)
from app.schemas.common import Envelope, ok
from app.services import memory_service, orchestrator, transfer_service

router = APIRouter(tags=["agent-b"])


def _attestation_read(db, experiment_id: str) -> AttestationRead | None:
    att = db.scalar(
        select(Attestation)
        .where(Attestation.experiment_id == experiment_id)
        .order_by(Attestation.created_at.desc(), Attestation.id.desc())
    )
    if att is None:
        return None
    check = transfer_service.verify_attestation(att)
    return AttestationRead(
        id=att.id, experiment_id=att.experiment_id, payload_sha256=att.payload_sha256,
        onchain=att.onchain, created_at=att.created_at, **check,
    )


def _read(db, experiment) -> TransferExperimentRead:
    return TransferExperimentRead(
        id=experiment.id,
        source_agent_id=experiment.source_agent_id,
        destination_agent_id=experiment.destination_agent_id,
        task_category=experiment.task_category,
        base_task_id=experiment.base_task_id,
        control_execution_id=experiment.control_execution_id,
        treatment_execution_id=experiment.treatment_execution_id,
        used_memory_ids=list(experiment.used_memory_ids or []),
        suite_hash=experiment.suite_hash,
        metrics=experiment.metrics,
        created_at=experiment.created_at,
        attestation=_attestation_read(db, experiment.id),
    )


@router.get("/memory", response_model=Envelope[list[MemoryRead]])
def list_memory(
    db: DbSession,
    category: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Stored, hidden-safe lessons (most recent first), optionally filtered by task category."""
    rows = memory_service.retrieve(db, task_category=category, limit=limit)
    return ok([MemoryRead.model_validate(r) for r in rows])


@router.post("/agent-b/transfer-experiment", status_code=201, response_model=Envelope[TransferExperimentRead])
def create_transfer_experiment(
    body: TransferExperimentRequest, request: Request, db: DbSession, background: BackgroundTasks
):
    """Prepare a control and a treatment execution on the base task's suite (lessons injected into the
    treatment description). With `start: true`, both runs begin in the background (needs the LLM)."""
    state = request.app.state
    experiment = transfer_service.prepare_experiment(db, body.base_task_id, settings=state.settings)
    if body.start:
        for execution_id in (experiment.control_execution_id, experiment.treatment_execution_id):
            orchestrator.start_run(db, execution_id, state.settings, state.instance_id)
            background.add_task(_run_in_background, state, execution_id)
    return ok(_read(db, experiment))


@router.get("/agent-b/experiments/{experiment_id}", response_model=Envelope[TransferExperimentRead])
def get_transfer_experiment(experiment_id: str, db: DbSession):
    """The experiment with its measured comparison and attestation (computed from live run data)."""
    experiment = transfer_service.get_experiment(db, experiment_id)
    transfer_service.finalize(db, experiment)
    return ok(_read(db, experiment))

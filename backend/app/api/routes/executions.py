from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app.api.deps import DbSession, Limit, Offset
from app.evaluation import policy
from app.lifecycle import ExecutionStatus
from app.models import CriticFeedback, Version
from app.schemas.acceptance import (
    BundleRef,
    CommitmentRead,
    EvidenceRead,
    ExecutionEvidenceRead,
    FailedTermRead,
    InvalidComparisonRead,
)
from app.schemas.common import Envelope, Page, ok
from app.schemas.execution import ExecutionDetail, ExecutionRead
from app.schemas.version import VersionRead
from app.services import acceptance_service, bundle_service, execution_service, version_service

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("", response_model=Envelope[Page[ExecutionRead]])
def list_executions(
    request: Request,
    db: DbSession,
    limit: Limit = 50,
    offset: Offset = 0,
    status: ExecutionStatus | None = Query(default=None),
    task_id: str | None = Query(default=None, max_length=64),
):
    items, total = execution_service.list_executions(
        db, limit=limit, offset=offset, status=status.value if status else None, task_id=task_id
    )
    instance = request.app.state.instance_id
    return ok(Page(items=[ExecutionRead.from_model(e, instance) for e in items], total=total, limit=limit,
                   offset=offset))


@router.get("/{execution_id}", response_model=Envelope[ExecutionDetail])
def get_execution(execution_id: str, request: Request, db: DbSession):
    return ok(ExecutionDetail.from_model(execution_service.get_execution(db, execution_id),
                                         request.app.state.instance_id))


@router.post("/{execution_id}/cancel", response_model=Envelope[ExecutionDetail])
def cancel_execution(execution_id: str, request: Request, db: DbSession):
    """Marks a non-terminal execution cancelled. A run in progress notices between steps and stops;
    this is also how a `stalled` execution is closed."""
    return ok(ExecutionDetail.from_model(execution_service.cancel_execution(db, execution_id),
                                         request.app.state.instance_id))


@router.get("/{execution_id}/versions", response_model=Envelope[list[VersionRead]])
def list_versions(execution_id: str, db: DbSession):
    return ok([VersionRead.model_validate(v) for v in version_service.list_versions(db, execution_id)])


@router.get("/{execution_id}/evidence", response_model=Envelope[ExecutionEvidenceRead])
def get_evidence(execution_id: str, db: DbSession):
    """Typed evidence for one execution: the commitment, validated improvements and rejected attempts
    (with the hashes of any bundles built for them), invalid comparisons (stored separately, not
    evidence) and a count of unvalidated Critic proposals."""
    execution = execution_service.get_execution(db, execution_id)
    records, invalid = acceptance_service.list_evidence(db, execution_id)
    bundles = bundle_service.bundles_for_records(db, [r.id for r in records])
    proposals = db.scalar(
        select(func.count()).select_from(CriticFeedback).join(Version, CriticFeedback.version_id == Version.id)
        .where(Version.execution_id == execution_id)
    ) or 0
    return ok(ExecutionEvidenceRead(
        execution_id=execution.id,
        commitment=CommitmentRead.from_execution(execution),
        best_version_id=execution.best_version_id,
        scoring_rule=policy.scoring_rule(),
        records=[EvidenceRead(
            id=r.id, status=r.status, candidate_version_id=r.candidate_version_id,
            previous_best_version_id=r.previous_best_version_id, candidate_evaluation_id=r.candidate_evaluation_id,
            previous_evaluation_id=r.previous_evaluation_id,
            failed_terms=[FailedTermRead(**t) for t in r.failed_terms], candidate_scores=r.candidate_scores,
            previous_scores=r.previous_scores, provenance=r.provenance, created_at=r.created_at,
            bundles=[BundleRef(id=b.id, include_code=b.include_code, bundle_sha256=b.bundle_sha256)
                     for b in bundles[r.id]],
        ) for r in records],
        invalid_comparisons=[InvalidComparisonRead(
            id=i.id, candidate_version_id=i.candidate_version_id, previous_best_version_id=i.previous_best_version_id,
            reasons=[FailedTermRead(**t) for t in i.reasons], created_at=i.created_at,
        ) for i in invalid],
        unvalidated_proposals=proposals,
    ))

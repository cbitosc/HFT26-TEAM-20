"""Versions, evaluations and Critic feedback. Clients can REQUEST an evaluation or an acceptance decision
but can never submit a score, a result or a verdict: the request bodies have no fields, and the numbers
come only from the backend evaluator. Responses never reveal hidden test names or per-test results."""
from fastapi import APIRouter, Request

from app.api.deps import DbSession
from app.evaluation.gate import scores
from app.schemas.acceptance import (
    AcceptanceDecisionRead,
    AcceptanceRequest,
    EvaluateRequest,
    FailedTermRead,
    ScoreSnapshot,
)
from app.schemas.common import Envelope, ok
from app.schemas.critic_feedback import CriticFeedbackRead
from app.schemas.evaluation import EvaluationRead
from app.schemas.version import VersionRead
from app.services import acceptance_service, evaluation_service, version_service

router = APIRouter(prefix="/versions", tags=["versions"])


@router.get("/{version_id}", response_model=Envelope[VersionRead])
def get_version(version_id: str, db: DbSession):
    return ok(VersionRead.model_validate(version_service.get_version(db, version_id)))


@router.get("/{version_id}/evaluations", response_model=Envelope[list[EvaluationRead]])
def list_evaluations(version_id: str, db: DbSession):
    return ok([EvaluationRead.from_model(e) for e in version_service.list_evaluations(db, version_id)])


@router.get("/{version_id}/critic-feedback", response_model=Envelope[list[CriticFeedbackRead]])
def list_critic_feedback(version_id: str, db: DbSession):
    return ok([CriticFeedbackRead.model_validate(f) for f in version_service.list_critic_feedback(db, version_id)])


@router.post("/{version_id}/evaluate", status_code=201, response_model=Envelope[EvaluationRead])
def evaluate_version(version_id: str, request: Request, db: DbSession, body: EvaluateRequest | None = None):
    """Runs the backend evaluator on the stored code. The body, if any, must be empty."""
    evaluation = evaluation_service.evaluate_version(db, version_id, request.app.state.settings)
    return ok(EvaluationRead.from_model(evaluation))


@router.post("/{version_id}/acceptance-decision", response_model=Envelope[AcceptanceDecisionRead])
def acceptance_decision(version_id: str, db: DbSession, body: AcceptanceRequest | None = None):
    """Applies the acceptance policy to persisted evaluations. The body, if any, must be empty."""
    d = acceptance_service.decide_acceptance(db, version_id)
    return ok(
        AcceptanceDecisionRead(
            version_id=d.version.id,
            label=d.version.label,
            outcome=d.outcome,
            acceptance_status=d.version.acceptance_status,
            reason=d.reason,
            failed_terms=[FailedTermRead(**t.as_dict()) for t in d.failed_terms],
            candidate=ScoreSnapshot(**scores(d.candidate)) if d.candidate else None,
            previous_best=ScoreSnapshot(**scores(d.previous_best)) if d.previous_best else None,
            best_version_id=d.best_version_id,
            evidence_id=d.evidence_id,
            invalid_comparison_id=d.invalid_comparison_id,
            decided_at=d.decided_at,
        )
    )

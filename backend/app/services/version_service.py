"""Versions, evaluation results and Critic feedback.

These functions store results produced by other components. The revision acceptance rule
(retain passed tests, no dimension regresses, strictly higher score) is NOT implemented here;
`decide_version` only records a decision that the future revision engine makes.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.errors import ConflictError, NotFoundError
from app.lifecycle import ExecutionStatus, TERMINAL_STATUSES
from app.models import (
    AcceptanceStatus,
    CriticFeedback,
    Evaluation,
    EvaluationOperationalMetrics,
    Execution,
    Version,
)
from app.schemas.critic_feedback import CriticFeedbackInput
from app.schemas.evaluation import EvaluationInput
from app.scoring import compute_overall_score, compute_test_pass_rate
from app.services.task_service import commit_or_rollback


def get_version(session: Session, version_id: str) -> Version:
    version = session.get(Version, version_id)
    if version is None:
        raise NotFoundError("version", version_id)
    return version


def create_version(
    session: Session,
    execution_id: str,
    code: str,
    *,
    parent_version_id: str | None = None,
    generator_model_id: str | None = None,
) -> Version:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise NotFoundError("execution", execution_id)
    if ExecutionStatus(execution.status) in TERMINAL_STATUSES:
        raise ConflictError(f"Cannot add a version to an execution that is {execution.status}.")
    if not code or not code.strip():
        raise ValueError("code must not be empty")
    if parent_version_id is not None:
        parent = session.get(Version, parent_version_id)
        if parent is None:
            raise NotFoundError("version", parent_version_id)
        if parent.execution_id != execution.id:
            raise ConflictError("The parent version belongs to a different execution.")
    sequence = (
        session.scalar(select(func.max(Version.sequence)).where(Version.execution_id == execution_id)) or 0
    ) + 1
    version = Version(
        execution_id=execution_id,
        sequence=sequence,
        label=f"V{sequence}",
        code=code,
        parent_version_id=parent_version_id,
        generator_model_id=generator_model_id,
    )
    session.add(version)
    commit_or_rollback(session)
    return version


def list_versions(session: Session, execution_id: str) -> list[Version]:
    if session.get(Execution, execution_id) is None:
        raise NotFoundError("execution", execution_id)
    return list(
        session.scalars(select(Version).where(Version.execution_id == execution_id).order_by(Version.sequence))
    )


def decide_version(
    session: Session, version_id: str, *, accepted: bool, rejection_reason: str | None = None
) -> Version:
    """Record the acceptance decision once. Decisions are final."""
    version = get_version(session, version_id)
    if version.acceptance_status != AcceptanceStatus.PENDING.value:
        raise ConflictError(f"Version already {version.acceptance_status}; decisions are final.")
    if accepted:
        if rejection_reason:
            raise ValueError("an accepted version cannot have a rejection reason")
        version.acceptance_status = AcceptanceStatus.ACCEPTED.value
    else:
        if not rejection_reason or not rejection_reason.strip():
            raise ValueError("a rejected version requires a rejection reason")
        version.acceptance_status = AcceptanceStatus.REJECTED.value
        version.rejection_reason = rejection_reason.strip()
    commit_or_rollback(session)
    return version


def record_evaluation(session: Session, version_id: str, data: EvaluationInput) -> Evaluation:
    """Persist an evaluator's output. The pass rate and overall score are derived here from the
    components with the approved weights, so a caller cannot store an arbitrary aggregate."""
    get_version(session, version_id)
    pass_rate = compute_test_pass_rate(data.tests_passed, data.tests_total)
    evaluation = Evaluation(
        version_id=version_id,
        tests_passed=data.tests_passed,
        tests_total=data.tests_total,
        test_pass_rate=pass_rate,
        correctness_score=data.correctness_score,
        code_quality_score=data.code_quality_score,
        overall_score=compute_overall_score(pass_rate, data.correctness_score, data.code_quality_score),
        failure_details=[d.model_dump() for d in data.failure_details],
        created_at=utcnow(),
    )
    session.add(evaluation)
    session.flush()
    if data.operational is not None:
        session.add(EvaluationOperationalMetrics(evaluation_id=evaluation.id, **data.operational.model_dump()))
    commit_or_rollback(session)
    return evaluation


def list_evaluations(session: Session, version_id: str) -> list[Evaluation]:
    get_version(session, version_id)
    return list(
        session.scalars(
            select(Evaluation).where(Evaluation.version_id == version_id).order_by(Evaluation.created_at, Evaluation.id)
        )
    )


def record_critic_feedback(session: Session, version_id: str, data: CriticFeedbackInput) -> CriticFeedback:
    get_version(session, version_id)
    feedback = CriticFeedback(version_id=version_id, **data.model_dump())
    session.add(feedback)
    commit_or_rollback(session)
    return feedback


def list_critic_feedback(session: Session, version_id: str) -> list[CriticFeedback]:
    get_version(session, version_id)
    return list(
        session.scalars(
            select(CriticFeedback)
            .where(CriticFeedback.version_id == version_id)
            .order_by(CriticFeedback.created_at, CriticFeedback.id)
        )
    )

"""Versions, evaluation results and Critic feedback.

These functions store results produced by other components. The acceptance rule lives in
`acceptance_service` (gate: `app.evaluation.gate`). `decide_version` is a low-level recorder kept for
tests; pipeline code must not use it.
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
from app.changelog import revision_changelog
from app.hashing import code_sha256
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
    generator_prompt_sha256: str | None = None,
    generation_latency_seconds: float | None = None,
    generation_prompt_tokens: int | None = None,
    generation_completion_tokens: int | None = None,
) -> Version:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise NotFoundError("execution", execution_id)
    if ExecutionStatus(execution.status) in TERMINAL_STATUSES:
        raise ConflictError(f"Cannot add a version to an execution that is {execution.status}.")
    if not code or not code.strip():
        raise ValueError("code must not be empty")
    parent = None
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
        code_sha256=code_sha256(code),  # computed by the backend, never supplied by a caller
        parent_version_id=parent_version_id,
        generator_model_id=generator_model_id,
        generator_prompt_sha256=generator_prompt_sha256,
        generation_latency_seconds=generation_latency_seconds,
        generation_prompt_tokens=generation_prompt_tokens,
        generation_completion_tokens=generation_completion_tokens,
        changelog=revision_changelog(parent.code, code, parent.label, f"V{sequence}") if parent else [],
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
    """LOW-LEVEL recorder of a decision made elsewhere. Decisions are final.

    It applies no rule. Pipeline code must NOT use it to accept a revision: acceptance is decided by
    `acceptance_service.decide_acceptance`, which compares persisted evaluations and moves the
    best-version pointer atomically. This function remains only so tests can build specific states."""
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
    version.decided_at = utcnow()
    commit_or_rollback(session)
    return version


def latest_evaluation(session: Session, version_id: str) -> Evaluation | None:
    """The most recent evaluation of a version (re-evaluation supersedes earlier ones)."""
    return session.scalars(
        select(Evaluation)
        .where(Evaluation.version_id == version_id)
        .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
        .limit(1)
    ).first()


def record_evaluation(session: Session, version_id: str, data: EvaluationInput) -> Evaluation:
    """Low-level persistence of an evaluator's output (internal; there is no API route to it).

    The only production caller is `evaluation_service.evaluate_version`, which measures the
    components itself. The pass rate and overall score are derived here from those components with
    the approved weights, so a stored aggregate can never be arbitrary. Tests also use it to
    construct specific stored evaluations when exercising the acceptance gate."""
    version = get_version(session, version_id)
    pass_rate = compute_test_pass_rate(data.tests_passed, data.tests_total)
    evaluation = Evaluation(
        version_id=version_id,
        # The evaluator passes the hash of the exact code it ran; other internal callers default to
        # the version's stored hash.
        code_sha256=data.code_sha256 or version.code_sha256,
        tests_passed=data.tests_passed,
        tests_total=data.tests_total,
        public_tests_passed=data.public_tests_passed,
        public_tests_total=data.public_tests_total,
        test_pass_rate=pass_rate,
        correctness_score=data.correctness_score,
        code_quality_score=data.code_quality_score,
        overall_score=compute_overall_score(pass_rate, data.correctness_score, data.code_quality_score),
        failure_details=[d.model_dump() for d in data.failure_details],
        suite_id=data.suite_id,
        suite_hash=data.suite_hash,
        evaluator_version=data.evaluator_version,
        evaluator_config_hash=data.evaluator_config_hash,
        scoring_rule_version=data.scoring_rule_version,
        provenance=data.provenance,
        test_results=[t.model_dump() for t in data.test_results],
        score_breakdown=data.score_breakdown,
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

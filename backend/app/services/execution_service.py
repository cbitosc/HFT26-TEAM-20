"""Execution persistence and lifecycle transitions.

Nothing here performs a pipeline stage. A transition records that the execution moved to a
state, together with when. Pipeline workers (later milestones) call `transition_execution`
only after they have really done the work.
"""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import utcnow
from app.errors import ConflictError, EvaluationSuiteUnavailableError, InvalidTransitionError, NotFoundError
from app.evaluation import policy
from app.evaluation.execution import RunLimits
from app.evaluation.provenance import evaluator_config_hash
from app.evaluation.suites import get_suite
from app.lifecycle import (
    DEFAULT_MAX_REVISIONS,
    MAX_REVISIONS,
    MIN_REVISIONS,
    TERMINAL_STATUSES,
    ExecutionStatus,
    allowed_transitions,
)
from app.models import AcceptanceStatus, Evaluation, Execution, ExecutionTransition, Task, Version
from app.services.task_service import commit_or_rollback

MAX_ERROR_CODE = 64
MAX_ERROR_MESSAGE = 2000


def get_execution(session: Session, execution_id: str) -> Execution:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise NotFoundError("execution", execution_id)
    return execution


def create_execution(
    session: Session,
    task_id: str,
    *,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    settings: Settings | None = None,
) -> Execution:
    """`max_revisions` is how many revision attempts (V2, V3) the execution is permitted. It is
    chosen by backend code, not by API clients.

    The commitment (suite hashes, evaluator configuration hash, scoring-rule version, delta) is
    recorded here, before any version exists. If it cannot be recorded, the execution is not created
    (PRD: "Hash recording fails: the run does not start"). `settings` supplies the evaluator time
    limits; None means the defaults, which the evaluator then must also use."""
    if not MIN_REVISIONS <= max_revisions <= MAX_REVISIONS:
        raise ValueError(f"max_revisions must be between {MIN_REVISIONS} and {MAX_REVISIONS}")
    task = session.get(Task, task_id)
    if task is None:
        raise NotFoundError("task", task_id)
    from app.services import suite_service  # lazy: avoids an import cycle

    suite = suite_service.suite_commitment(session, task.evaluation_suite_id)
    if suite is None:
        raise EvaluationSuiteUnavailableError(
            "This task has no available evaluation suite (public and hidden tests), so a run cannot start."
        )
    from app.services.evaluation_service import limits_from  # lazy: avoids an import cycle

    limits = limits_from(settings) if settings is not None else RunLimits()
    now = utcnow()
    execution = Execution(
        task_id=task_id,
        status=ExecutionStatus.QUEUED.value,
        max_revisions=max_revisions,
        created_at=now,
        updated_at=now,
        suite_id=suite.id,
        suite_hash=suite.suite_hash,
        public_suite_hash=suite.public_suite_hash,
        hidden_suite_hash=suite.hidden_suite_hash,
        evaluator_config_hash=evaluator_config_hash(limits),
        scoring_rule_version=policy.SCORING_RULE_VERSION,
        delta=policy.DELTA,
        committed_at=now,
    )
    session.add(execution)
    session.flush()
    session.add(
        ExecutionTransition(
            execution_id=execution.id, from_status=None, to_status=ExecutionStatus.QUEUED.value, occurred_at=now
        )
    )
    commit_or_rollback(session)
    return execution


def list_executions(
    session: Session,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    task_id: str | None = None,
) -> tuple[list[Execution], int]:
    conditions = []
    if status is not None:
        conditions.append(Execution.status == status)
    if task_id is not None:
        conditions.append(Execution.task_id == task_id)
    total = session.scalar(select(func.count()).select_from(Execution).where(*conditions)) or 0
    items = session.scalars(
        select(Execution)
        .where(*conditions)
        .order_by(Execution.created_at.desc(), Execution.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def transition_execution(
    session: Session,
    execution_id: str,
    to_status: ExecutionStatus | str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> Execution:
    """Move an execution to `to_status` if the lifecycle allows it.

    The UPDATE only matches while the row still has the status we validated against, so two
    racing transitions cannot both succeed (the loser gets a ConflictError).
    """
    target = ExecutionStatus(to_status)  # ValueError for an unknown status (programmer error)
    if target is ExecutionStatus.FAILED:
        if not error_code or not error_message:
            raise ValueError("a failed transition requires error_code and error_message")
    elif error_code is not None or error_message is not None:
        raise ValueError("error information is only valid when transitioning to 'failed'")

    execution = get_execution(session, execution_id)
    current = ExecutionStatus(execution.status)
    if target not in allowed_transitions(current):
        raise InvalidTransitionError(f"Cannot move an execution from '{current.value}' to '{target.value}'.")
    if target in (ExecutionStatus.CRITIQUING_V2, ExecutionStatus.GENERATING_V3) and execution.max_revisions < 2:
        raise InvalidTransitionError("A third version is not permitted for this execution (max_revisions=1).")
    if target is ExecutionStatus.CRITIQUING_V2:
        _require_no_accepted_revision(session, execution)
    if target is ExecutionStatus.COMPLETED_NO_IMPROVEMENT:
        _require_revisions_exhausted_without_improvement(session, execution, current)
    # Entering the proof stage, or completing straight from an evaluation state, both require a
    # verified accepted improvement. (blockchain_register -> completed was already guarded at zk_proof.)
    if target is ExecutionStatus.ZK_PROOF or (
        target is ExecutionStatus.COMPLETED
        and current in (ExecutionStatus.EVALUATING_V2, ExecutionStatus.EVALUATING_V3)
    ):
        from app.services import acceptance_service  # lazy: avoids an import cycle

        acceptance_service.require_verified_improvement(session, execution)

    now = utcnow()
    values: dict = {"status": target.value, "updated_at": now}
    if current is ExecutionStatus.QUEUED and target is ExecutionStatus.GENERATING_V1:
        values["started_at"] = now
    if target in TERMINAL_STATUSES:
        values["completed_at"] = now
    if target is ExecutionStatus.FAILED:
        values["error_code"] = error_code[:MAX_ERROR_CODE]
        values["error_message"] = error_message[:MAX_ERROR_MESSAGE]
        values["error_stage"] = current.value

    result = session.execute(
        update(Execution)
        .where(Execution.id == execution_id, Execution.status == current.value)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise ConflictError("The execution changed state concurrently; reload it and retry.")
    session.add(
        ExecutionTransition(
            execution_id=execution_id, from_status=current.value, to_status=target.value, occurred_at=now
        )
    )
    commit_or_rollback(session)
    session.refresh(execution)
    return execution


def _require_no_accepted_revision(session: Session, execution: Execution) -> None:
    """A second critique (towards V3) only makes sense if no revision was accepted: an accepted
    revision means the run stops and completes."""
    accepted = session.scalar(
        select(func.count()).select_from(Version).where(
            Version.execution_id == execution.id, Version.sequence >= 2,
            Version.acceptance_status == AcceptanceStatus.ACCEPTED.value)
    )
    if accepted:
        raise InvalidTransitionError("A revision was already accepted; the run must complete instead of revising again.")


def _require_revisions_exhausted_without_improvement(
    session: Session, execution: Execution, current: ExecutionStatus
) -> None:
    """`completed_no_improvement` is only a truthful conclusion when every permitted revision
    exists, was evaluated, and was rejected. This reads decisions that were already recorded;
    it decides nothing itself (the acceptance rule belongs to the future revision engine)."""
    attempts_made = 1 if current is ExecutionStatus.EVALUATING_V2 else 2
    if attempts_made < execution.max_revisions:
        raise InvalidTransitionError(
            f"Another permitted revision remains ({attempts_made} of {execution.max_revisions} attempted)."
        )
    revisions = session.scalars(
        select(Version)
        .where(Version.execution_id == execution.id, Version.sequence >= 2)
        .order_by(Version.sequence)
    ).all()
    if [v.sequence for v in revisions] != list(range(2, attempts_made + 2)):
        raise InvalidTransitionError("Not every permitted revision attempt has been recorded.")
    for version in revisions:
        if version.acceptance_status == AcceptanceStatus.ACCEPTED.value:
            raise InvalidTransitionError(f"{version.label} was accepted as an improvement.")
        if version.acceptance_status != AcceptanceStatus.REJECTED.value:
            raise InvalidTransitionError(f"{version.label} has no recorded decision.")
        evaluated = session.scalar(
            select(func.count()).select_from(Evaluation).where(Evaluation.version_id == version.id)
        )
        if not evaluated:
            raise InvalidTransitionError(f"{version.label} has not been evaluated.")


def fail_execution(session: Session, execution_id: str, code: str, message: str) -> Execution:
    return transition_execution(
        session, execution_id, ExecutionStatus.FAILED, error_code=code, error_message=message
    )


def cancel_execution(session: Session, execution_id: str) -> Execution:
    return transition_execution(session, execution_id, ExecutionStatus.CANCELLED)


def set_best_version(session: Session, execution_id: str, version_id: str) -> Execution:
    """Record the current best (accepted) version. The acceptance decision itself is made elsewhere."""
    execution = get_execution(session, execution_id)
    version = session.get(Version, version_id)
    if version is None:
        raise NotFoundError("version", version_id)
    if version.execution_id != execution.id:
        raise ConflictError("The version does not belong to this execution.")
    if version.acceptance_status != AcceptanceStatus.ACCEPTED.value:
        raise ConflictError("Only an accepted version can be the best version.")
    execution.best_version_id = version.id
    execution.updated_at = utcnow()
    commit_or_rollback(session)
    return execution

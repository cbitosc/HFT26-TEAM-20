from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models import (
    AgentMemory,
    Attestation,
    CriticFeedback,
    Evaluation,
    EvaluationOperationalMetrics,
    EvidenceBundle,
    EvidenceRecord,
    Execution,
    ExecutionTransition,
    InvalidComparison,
    LLMCall,
    Task,
    TransferExperiment,
    UploadedSuite,
    Version,
)
from app.schemas.task import TaskCreate


def commit_or_rollback(session: Session) -> None:
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def create_task(session: Session, data: TaskCreate, settings=None) -> Task:
    """A task references either a registered suite (`evaluation_suite_id`) or an uploaded one. When a
    suite is uploaded, its hidden tests are sealed and stored first, and the task points at it."""
    suite_id = data.evaluation_suite_id
    if data.suite is not None:
        from app.services import suite_service  # lazy: avoids an import cycle

        row = suite_service.create_uploaded_suite(session, data.suite.to_upload_dict(), settings)
        suite_id = row.id
    task = Task(
        title=data.title,
        description=data.description,
        requirements=list(data.requirements),
        language=data.language,
        category=data.category,
        evaluation_suite_id=suite_id,
        starter_code=data.starter_code or None,
    )
    session.add(task)
    commit_or_rollback(session)
    return task


def get_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise NotFoundError("task", task_id)
    return task


def list_tasks(session: Session, *, limit: int, offset: int) -> tuple[list[Task], int]:
    total = session.scalar(select(func.count()).select_from(Task)) or 0
    items = session.scalars(
        select(Task).order_by(Task.created_at.desc(), Task.id).limit(limit).offset(offset)
    ).all()
    return list(items), total


def delete_task(session: Session, task_id: str) -> None:
    """Delete a task and its entire run subtree (executions, versions, evaluations, evidence,
    critic feedback, LLM calls, transitions, and any Agent-B memory/experiments that reference it) in
    one transaction. Refused with 409 if an evidence bundle was exported for a run — bundles are
    immutable (hash-addressed), so deleting them would break that guarantee."""
    task = get_task(session, task_id)

    exec_ids = list(session.scalars(select(Execution.id).where(Execution.task_id == task_id)))
    version_ids = list(session.scalars(select(Version.id).where(Version.execution_id.in_(exec_ids))))
    eval_ids = list(session.scalars(select(Evaluation.id).where(Evaluation.version_id.in_(version_ids))))
    evidence_ids = list(session.scalars(select(EvidenceRecord.id).where(EvidenceRecord.execution_id.in_(exec_ids))))
    experiment_ids = list(
        session.scalars(
            select(TransferExperiment.id).where(
                or_(
                    TransferExperiment.base_task_id == task_id,
                    TransferExperiment.control_execution_id.in_(exec_ids),
                    TransferExperiment.treatment_execution_id.in_(exec_ids),
                )
            )
        )
    )

    # Immutable evidence bundles cannot be deleted; refuse rather than leave the DB half-deleted.
    if evidence_ids:
        bundle_count = session.scalar(
            select(func.count()).select_from(EvidenceBundle).where(
                EvidenceBundle.evidence_record_id.in_(evidence_ids)
            )
        )
        if bundle_count:
            raise ConflictError(
                "Cannot delete: evidence has been exported for this task's runs and is immutable."
            )

    def _del(model, condition) -> None:
        session.execute(delete(model).where(condition).execution_options(synchronize_session=False))

    try:
        # children first; self-referential FKs (version.parent, execution.best_version) are nulled.
        _del(Attestation, Attestation.experiment_id.in_(experiment_ids))
        _del(TransferExperiment, TransferExperiment.id.in_(experiment_ids))
        _del(AgentMemory, AgentMemory.source_execution_id.in_(exec_ids))
        _del(EvidenceRecord, EvidenceRecord.id.in_(evidence_ids))
        _del(InvalidComparison, InvalidComparison.execution_id.in_(exec_ids))
        _del(EvaluationOperationalMetrics, EvaluationOperationalMetrics.evaluation_id.in_(eval_ids))
        _del(LLMCall, LLMCall.execution_id.in_(exec_ids))
        _del(CriticFeedback, CriticFeedback.version_id.in_(version_ids))
        _del(Evaluation, Evaluation.id.in_(eval_ids))
        session.execute(
            update(Execution).where(Execution.id.in_(exec_ids)).values(best_version_id=None)
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(Version).where(Version.id.in_(version_ids)).values(parent_version_id=None)
            .execution_options(synchronize_session=False)
        )
        _del(Version, Version.id.in_(version_ids))
        _del(ExecutionTransition, ExecutionTransition.execution_id.in_(exec_ids))
        _del(Execution, Execution.id.in_(exec_ids))
        _del(Task, Task.id == task_id)

        # Remove an uploaded suite only if no other task still points at it.
        suite_id = task.evaluation_suite_id
        if suite_id and session.get(UploadedSuite, suite_id) is not None:
            still_used = session.scalar(
                select(func.count()).select_from(Task).where(Task.evaluation_suite_id == suite_id)
            )
            if not still_used:
                _del(UploadedSuite, UploadedSuite.id == suite_id)

        session.commit()
    except Exception:
        session.rollback()
        raise

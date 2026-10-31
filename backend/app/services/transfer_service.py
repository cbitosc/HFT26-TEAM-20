"""Agent B transfer experiment: control vs treatment on the same suite, with an attestation.

The ONLY difference between the two runs is that the treatment task's description carries prior
lessons (injected through the normal task-description channel the Generator already reads), so no
generator/orchestrator change is needed and the suite — hence the hidden tests and the commitment —
is identical, which keeps the two runs comparable. All measured numbers come from real evaluations;
hidden results appear only as the aggregate pass-rate.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.egress import OUTCOME_BLOCKED, scan_bundle, suite_hidden_tokens
from app.errors import ConflictError, LessonRejectedError, NotFoundError
from app.hashing import canonical_json, sha256_hex
from app.lifecycle import TERMINAL_STATUSES, ExecutionStatus
from app.models import Attestation, Execution, TransferExperiment, Version
from app.schemas.task import TaskCreate
from app.services import execution_service, memory_service, task_service, version_service

SOURCE_AGENT = "agent-a"
DEST_AGENT = "agent-b"


def _commit(session: Session) -> None:
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def build_treatment_description(base_description: str, lessons: list[str]) -> str:
    """Append prior lessons to the task description. Refuses (raises) if a lesson would leak hidden
    test data — defence in depth over store-time scanning."""
    if not lessons:
        return base_description
    block = "\n\nLessons from prior agents (advisory, apply if relevant):\n" + "\n".join(
        f"- {lesson}" for lesson in lessons
    )
    desc = base_description + block
    report = scan_bundle({"d": desc}, forbidden_tokens=suite_hidden_tokens())
    if report.outcome == OUTCOME_BLOCKED:
        raise LessonRejectedError("Retrieved lessons contained hidden test data; experiment aborted.")
    return report.redacted_bundle["d"]


def prepare_experiment(session: Session, base_task_id: str, *, limit: int = 5, settings=None) -> TransferExperiment:
    """Create the control and treatment tasks+executions (both queued) and record the experiment.
    Does not start the runs."""
    base = task_service.get_task(session, base_task_id)
    if not base.evaluation_suite_id:
        raise ConflictError("The transfer experiment supports tasks with a registered evaluation suite for now.")
    category = base.category
    lessons = memory_service.retrieve(session, task_category=category, limit=limit)
    lesson_texts = [m.content for m in lessons]

    control_task = task_service.create_task(
        session,
        TaskCreate(
            title=(base.title + " (control)")[:200],
            description=base.description,
            language=base.language,
            category=category,
            evaluation_suite_id=base.evaluation_suite_id,
            starter_code=base.starter_code,
        ),
        settings,
    )
    treatment_task = task_service.create_task(
        session,
        TaskCreate(
            title=(base.title + " (treatment)")[:200],
            description=build_treatment_description(base.description, lesson_texts),
            language=base.language,
            category=category,
            evaluation_suite_id=base.evaluation_suite_id,
            starter_code=base.starter_code,
        ),
        settings,
    )

    control_exec = execution_service.create_execution(session, control_task.id)
    treatment_exec = execution_service.create_execution(session, treatment_task.id)

    experiment = TransferExperiment(
        source_agent_id=SOURCE_AGENT,
        destination_agent_id=DEST_AGENT,
        task_category=category,
        base_task_id=base.id,
        control_task_id=control_task.id,
        treatment_task_id=treatment_task.id,
        control_execution_id=control_exec.id,
        treatment_execution_id=treatment_exec.id,
        used_memory_ids=[m.id for m in lessons],
        suite_hash=control_exec.suite_hash,
    )
    session.add(experiment)
    _commit(session)
    session.refresh(experiment)
    return experiment


def get_experiment(session: Session, experiment_id: str) -> TransferExperiment:
    experiment = session.get(TransferExperiment, experiment_id)
    if experiment is None:
        raise NotFoundError("transfer_experiment", experiment_id)
    return experiment


def _hidden_rate(session: Session, version: Version | None) -> float | None:
    if version is None:
        return None
    evaluation = version_service.latest_evaluation(session, version.id)
    return evaluation.test_pass_rate if evaluation else None


def _execution_metrics(session: Session, execution_id: str) -> dict:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise NotFoundError("execution", execution_id)
    versions = list(
        session.scalars(select(Version).where(Version.execution_id == execution_id).order_by(Version.sequence))
    )
    v1 = next((v for v in versions if v.sequence == 1), versions[0] if versions else None)
    best = session.get(Version, execution.best_version_id) if execution.best_version_id else None
    return {
        "status": execution.status,
        "terminal": ExecutionStatus(execution.status) in TERMINAL_STATUSES,
        "num_versions": len(versions),
        "v1_hidden_accuracy": _hidden_rate(session, v1),
        "best_hidden_accuracy": _hidden_rate(session, best),
        "accepted_improvement": bool(best and best.sequence > 1),
    }


def summarize(session: Session, experiment: TransferExperiment) -> dict:
    control = _execution_metrics(session, experiment.control_execution_id)
    treatment = _execution_metrics(session, experiment.treatment_execution_id)
    delta = None
    if control["best_hidden_accuracy"] is not None and treatment["best_hidden_accuracy"] is not None:
        delta = treatment["best_hidden_accuracy"] - control["best_hidden_accuracy"]
    return {
        "control": control,
        "treatment": treatment,
        "delta_best_hidden_accuracy": delta,
        "memory_used": len(experiment.used_memory_ids or []),
    }


def finalize(session: Session, experiment: TransferExperiment) -> tuple[TransferExperiment, Attestation]:
    """Compute the comparison and ensure an attestation exists. Idempotent for the attestation: the
    first call snapshots and hashes the result."""
    metrics = summarize(session, experiment)
    experiment.metrics = metrics
    attestation = session.scalar(
        select(Attestation).where(Attestation.experiment_id == experiment.id)
    )
    if attestation is None:
        payload = {
            "kind": "autoevolve.transfer_attestation",
            "version": "1",
            "experiment_id": experiment.id,
            "source_agent": experiment.source_agent_id,
            "destination_agent": experiment.destination_agent_id,
            "task_category": experiment.task_category,
            "suite_hash": experiment.suite_hash,
            "used_memory_ids": sorted(experiment.used_memory_ids or []),
            "control_execution_id": experiment.control_execution_id,
            "treatment_execution_id": experiment.treatment_execution_id,
            "metrics": metrics,
        }
        text = canonical_json(payload)
        attestation = Attestation(
            experiment_id=experiment.id,
            payload_json=text,
            payload_sha256=sha256_hex(text.encode("utf-8")),
        )
        session.add(attestation)
    _commit(session)
    session.refresh(experiment)
    return experiment, attestation


def verify_attestation(attestation: Attestation) -> dict:
    recomputed = sha256_hex(attestation.payload_json.encode("utf-8"))
    return {"recomputed_sha256": recomputed, "hash_valid": recomputed == attestation.payload_sha256}

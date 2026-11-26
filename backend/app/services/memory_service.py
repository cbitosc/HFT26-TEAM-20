"""Cross-agent memory (Agent B, slice A): store and retrieve transferable lessons.

A lesson is recorded only from a version that was accepted as a `validated_improvement` — i.e. a
change that actually worked. The lesson text prefers the Critic's natural-language insight (from the
critique that informed the revision); when no Critic ran, a deterministic, data-derived summary is
used instead. Every lesson passes the egress gate before storage: if it contains any hidden test id
or literal it is REFUSED (never stored, never transferred). Hidden results only ever appear as the
aggregate pass-rate.

No schema change: lessons use the existing `agent_memories` columns
(source_agent_id, destination_agent_id, source_execution_id, content, task_category).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.egress import OUTCOME_BLOCKED, scan_bundle, suite_hidden_tokens
from app.errors import LessonRejectedError, NotFoundError
from app.models import AgentMemory, CriticFeedback, EvidenceRecord, Execution, Task, Version

DEFAULT_SOURCE_AGENT = "agent-a"
VALIDATED = "validated_improvement"


def _critic_lesson(session: Session, version_id: str | None) -> tuple[str | None, dict | None]:
    """The lesson/suggestion from the latest Critic feedback on a version (the critique that informed
    the next revision), if any."""
    if version_id is None:
        return None, None
    feedback = session.scalars(
        select(CriticFeedback)
        .where(CriticFeedback.version_id == version_id)
        .order_by(CriticFeedback.created_at.desc(), CriticFeedback.id.desc())
        .limit(1)
    ).first()
    if feedback is None:
        return None, None
    structured = feedback.structured_feedback or {}
    lesson = structured.get("lesson") or structured.get("suggestion")
    return (lesson or None), (structured or None)


def _rate(scores: dict | None) -> float | None:
    if not scores:
        return None
    value = scores.get("test_pass_rate")
    return float(value) if value is not None else None


def _compose(category: str | None, lesson: str | None, before: float | None, after: float | None) -> str:
    parts: list[str] = []
    if category:
        parts.append(f"[category: {category}]")
    if lesson:
        parts.append(f"Lesson: {lesson}")
    else:
        parts.append("Lesson: revising the solution improved the hidden-suite pass rate.")
    if before is not None and after is not None:
        parts.append(f"(hidden accuracy {before:g}% -> {after:g}% on the source run)")
    return " ".join(parts)


def store_lesson(
    session: Session,
    version_id: str,
    *,
    source_agent_id: str = DEFAULT_SOURCE_AGENT,
) -> AgentMemory | None:
    """Record a transferable lesson from an accepted improvement. Returns the row, or None when the
    version is not a validated improvement (nothing was learned). Raises LessonRejectedError if the
    composed lesson would leak hidden test data."""
    version = session.get(Version, version_id)
    if version is None:
        raise NotFoundError("version", version_id)

    evidence = session.scalar(
        select(EvidenceRecord).where(EvidenceRecord.candidate_version_id == version_id)
    )
    if evidence is None or evidence.status != VALIDATED:
        return None  # only changes that actually worked become memory

    execution = session.get(Execution, version.execution_id)
    task = session.get(Task, execution.task_id) if execution else None
    category = task.category if task else None

    lesson, _structured = _critic_lesson(session, version.parent_version_id)
    before = _rate(evidence.previous_scores)
    after = _rate(evidence.candidate_scores)
    content = _compose(category, lesson, before, after)

    # Egress gate: never store (or later transfer) a lesson that carries hidden test data.
    report = scan_bundle({"content": content}, forbidden_tokens=suite_hidden_tokens())
    if report.outcome == OUTCOME_BLOCKED:
        raise LessonRejectedError(
            "The lesson was refused because it contained hidden test data; nothing was stored."
        )
    safe_content = report.redacted_bundle["content"]

    memory = AgentMemory(
        source_agent_id=source_agent_id,
        destination_agent_id=None,
        source_execution_id=execution.id,
        content=safe_content,
        task_category=category,
    )
    session.add(memory)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(memory)
    return memory


def retrieve(
    session: Session,
    *,
    task_category: str | None = None,
    limit: int = 5,
    exclude_execution_id: str | None = None,
) -> list[AgentMemory]:
    """Lessons for a category (most recent first). `exclude_execution_id` omits an agent's own run so
    a run never 'learns' from itself."""
    limit = max(1, min(int(limit), 50))
    stmt = select(AgentMemory)
    if task_category:
        stmt = stmt.where(AgentMemory.task_category == task_category)
    if exclude_execution_id:
        stmt = stmt.where(AgentMemory.source_execution_id != exclude_execution_id)
    stmt = stmt.order_by(AgentMemory.created_at.desc(), AgentMemory.id.desc()).limit(limit)
    return list(session.scalars(stmt))

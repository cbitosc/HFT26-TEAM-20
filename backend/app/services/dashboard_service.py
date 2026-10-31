"""Assemble the hidden-safe, read-only views the dashboard needs. Hidden tests appear only as counts.

No function here decrypts a suite or reads hidden test contents: per-version hidden numbers come from
stored evaluation counts, never from the suite. Critic notes are passed through flagged "advisory".
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.changelog import revision_changelog
from app.errors import NotFoundError
from app.models import CriticFeedback, Execution, Task, UploadedSuite, Version
from app.schemas.dashboard import (
    ExecutionSummary,
    ExecutionTree,
    SuiteSummary,
    TestCounts,
    VersionDiff,
    VersionNode,
)
from app.schemas.execution import is_stalled
from app.services import version_service


def suite_summary(session: Session, suite_id: str | None) -> SuiteSummary | None:
    from app.evaluation.suites import get_suite

    registered = get_suite(suite_id)
    if registered is not None:
        return SuiteSummary(id=registered.id, source="registered",
                            public_test_count=len(registered.public_tests),
                            hidden_test_count=len(registered.hidden_tests),
                            suite_hash=registered.suite_hash, public_suite_hash=registered.public_suite_hash,
                            hidden_suite_hash=registered.hidden_suite_hash)
    row = session.get(UploadedSuite, suite_id) if suite_id else None
    if row is None:
        return None
    return SuiteSummary(id=row.id, source="uploaded", public_test_count=row.public_test_count,
                        hidden_test_count=row.hidden_test_count, suite_hash=row.suite_hash,
                        public_suite_hash=row.public_suite_hash, hidden_suite_hash=row.hidden_suite_hash)


def _best_hidden_accuracy(session: Session, execution: Execution) -> float | None:
    """The hidden-suite pass rate of the best version's latest evaluation, or None."""
    if execution.best_version_id is None:
        return None
    evaluation = version_service.latest_evaluation(session, execution.best_version_id)
    return evaluation.test_pass_rate if evaluation else None


def execution_summary(session: Session, execution: Execution, instance_id: str | None) -> ExecutionSummary:
    task = session.get(Task, execution.task_id)
    return ExecutionSummary(
        id=execution.id, task_id=execution.task_id, task_title=task.title if task else "",
        status=execution.status, stalled=is_stalled(execution, instance_id),
        best_version_id=execution.best_version_id,
        best_hidden_accuracy=_best_hidden_accuracy(session, execution),
        created_at=execution.created_at, updated_at=execution.updated_at,
    )


def _latest_critic_note(session: Session, version_id: str) -> str | None:
    feedback = session.scalars(
        select(CriticFeedback).where(CriticFeedback.version_id == version_id)
        .order_by(CriticFeedback.created_at.desc(), CriticFeedback.id.desc()).limit(1)
    ).first()
    if feedback is None:
        return None
    structured = feedback.structured_feedback or {}
    note = structured.get("suggestion") or feedback.raw_feedback
    return (note or "")[:1000]


def _version_node(session: Session, version: Version) -> VersionNode:
    evaluation = version_service.latest_evaluation(session, version.id)
    hidden = public = overall = None
    if evaluation is not None:
        hidden = TestCounts(passed=evaluation.tests_passed, total=evaluation.tests_total)
        public = TestCounts(passed=evaluation.public_tests_passed or 0, total=evaluation.public_tests_total or 0)
        overall = evaluation.overall_score
    details = version.decision_details or {}
    failed = details.get("failed_terms", []) if isinstance(details, dict) else []
    return VersionNode(
        id=version.id, label=version.label, sequence=version.sequence,
        parent_version_id=version.parent_version_id, acceptance_status=version.acceptance_status,
        decided=version.decided_at is not None, hidden=hidden, public=public, overall_score=overall,
        failed_terms=failed, generator_model_id=version.generator_model_id,
        generation_prompt_tokens=version.generation_prompt_tokens,
        generation_completion_tokens=version.generation_completion_tokens,
        critic_note=_latest_critic_note(session, version.id),
    )


def execution_tree(session: Session, execution_id: str, instance_id: str | None) -> ExecutionTree:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise NotFoundError("execution", execution_id)
    task = session.get(Task, execution.task_id)
    versions = version_service.list_versions(session, execution_id)
    return ExecutionTree(
        execution_id=execution.id, task_id=execution.task_id, task_title=task.title if task else "",
        status=execution.status, stalled=is_stalled(execution, instance_id),
        best_version_id=execution.best_version_id,
        best_hidden_accuracy=_best_hidden_accuracy(session, execution),
        versions=[_version_node(session, v) for v in versions],
    )


def version_diff(session: Session, version_id: str, against: str) -> VersionDiff:
    version = version_service.get_version(session, version_id)
    if against != "parent":
        raise NotFoundError("comparison", against)  # only parent comparison is supported today
    parent = session.get(Version, version.parent_version_id) if version.parent_version_id else None
    if parent is None:
        return VersionDiff(version_id=version.id, label=version.label, against="parent", against_version_id=None,
                           unified_diff="", changelog=[f"{version.label} has no parent version to compare against."])
    from app.changelog import unified_diff

    return VersionDiff(
        version_id=version.id, label=version.label, against=parent.label, against_version_id=parent.id,
        unified_diff=unified_diff(parent.code, version.code, parent.label, version.label),
        changelog=version.changelog or revision_changelog(parent.code, version.code, parent.label, version.label),
    )

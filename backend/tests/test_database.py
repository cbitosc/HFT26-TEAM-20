"""Foreign keys, CHECK constraints, indexes, JSON/timestamp round-trips and transaction behaviour.

These go straight to the ORM so the *database* is shown to enforce its own invariants,
independent of the service layer.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError

from app.database import UTCDateTime, utcnow
from app.errors import InvalidTransitionError
from app.lifecycle import ExecutionStatus as S
from app.models import (
    AgentMemory, CriticFeedback, Evaluation, EvaluationOperationalMetrics, Execution,
    ExecutionTransition, Task, Version,
)
from app.schemas.evaluation import EvaluationInput
from app.services import execution_service as exe
from app.services import version_service as ver
from tests.helpers import consistent_evaluation


@pytest.fixture
def task(db):
    t = Task(title="t", description="d", requirements=["a", "b"])
    db.add(t)
    db.commit()
    return t


@pytest.fixture
def execution(db, task):
    e = Execution(task_id=task.id)
    db.add(e)
    db.commit()
    return e


@pytest.fixture
def version(db, execution):
    v = Version(execution_id=execution.id, sequence=1, label="V1", code="x")
    db.add(v)
    db.commit()
    return v


def _insert_fails(db, obj, constraint=None):
    """The insert must be rejected by the database. With `constraint`, it must be rejected by
    that named constraint, so a test cannot pass because some unrelated rule fired."""
    db.add(obj)
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    db.rollback()
    if constraint is not None:
        assert constraint in str(exc.value.orig), str(exc.value.orig)


# ---- foreign keys ----------------------------------------------------------------------------
def test_execution_requires_an_existing_task(db):
    _insert_fails(db, Execution(task_id="no-such-task"))


def test_version_requires_an_existing_execution(db):
    _insert_fails(db, Version(execution_id="no-such-execution", sequence=1, label="V1", code="x"))


def test_parent_version_must_exist(db, execution):
    _insert_fails(db, Version(execution_id=execution.id, sequence=1, label="V1", code="x", parent_version_id="ghost"))


def test_evaluation_requires_an_existing_version(db):
    _insert_fails(db, consistent_evaluation("ghost"), "FOREIGN KEY")


def test_critic_feedback_requires_an_existing_version(db):
    _insert_fails(db, CriticFeedback(version_id="ghost", critic_model_id="m", raw_feedback="x"))


def test_agent_memory_requires_an_existing_execution(db):
    _insert_fails(db, AgentMemory(source_agent_id="a", source_execution_id="ghost", content="lesson"))


def test_transition_requires_an_existing_execution(db):
    _insert_fails(db, ExecutionTransition(execution_id="ghost", from_status=None, to_status="queued"))


def test_best_version_must_reference_an_existing_version(db, execution):
    execution.best_version_id = "ghost"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_referenced_rows_cannot_be_deleted(db, task, execution, version):
    """ON DELETE RESTRICT is enforced by the database. Core DELETEs bypass the ORM, which would
    otherwise try to NULL the children's foreign keys first."""
    db.add(consistent_evaluation(version.id))
    db.commit()
    for model, row in ((Version, version), (Execution, execution), (Task, task)):
        # version has an evaluation, execution has a version, task has an execution
        with pytest.raises(IntegrityError):
            db.execute(delete(model).where(model.id == row.id))
        db.rollback()
    assert db.get(Task, task.id) is not None and db.get(Version, version.id) is not None


def test_unreferenced_rows_can_be_deleted(db, task):
    db.execute(delete(Task).where(Task.id == task.id))  # no executions reference it yet
    db.commit()
    assert db.get(Task, task.id) is None


def test_agent_memory_roundtrip(db, execution):
    m = AgentMemory(source_agent_id="agent-1", destination_agent_id="agent-2",
                    source_execution_id=execution.id, content="Never sort the caller's list in place.",
                    task_category="algorithms")
    db.add(m)
    db.commit()
    got = db.get(AgentMemory, m.id)
    assert got.source_execution_id == execution.id and got.destination_agent_id == "agent-2"
    assert got.task_category == "algorithms" and got.created_at.tzinfo is not None
    m2 = AgentMemory(source_agent_id="agent-1", source_execution_id=execution.id, content="x")  # destination optional
    db.add(m2)
    db.commit()
    assert m2.destination_agent_id is None


# ---- uniqueness and CHECK constraints --------------------------------------------------------
def test_version_sequence_is_unique_per_execution(db, execution, version):
    _insert_fails(db, Version(execution_id=execution.id, sequence=1, label="V1", code="dup"))


@pytest.mark.parametrize("kw", [
    dict(sequence=0, label="V0"),
    dict(sequence=2, label="V3"),  # label must match the sequence
    dict(sequence=2, label="V2", acceptance_status="maybe"),
    dict(sequence=2, label="V2", acceptance_status="rejected"),  # rejection needs a reason
    dict(sequence=2, label="V2", acceptance_status="accepted", rejection_reason="why"),  # reason only when rejected
])
def test_version_check_constraints(db, execution, kw):
    _insert_fails(db, Version(execution_id=execution.id, code="x", **kw))


def test_version_cannot_be_its_own_parent(db, version):
    version.parent_version_id = version.id
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize("kw", [
    dict(status="exploding"),
    dict(status="failed"),  # failed requires error information
    dict(error_code="X", error_message="m", error_stage="queued"),  # error info only valid when failed
    dict(status="completed"),  # terminal requires completed_at
    dict(completed_at=utcnow()),  # completed_at only valid for terminal states
    dict(status="generating_v1"),  # a started status requires started_at
])
def test_execution_check_constraints(db, task, kw):
    _insert_fails(db, Execution(task_id=task.id, **kw))


@pytest.mark.parametrize("kw,constraint", [
    # Each case changes one thing from a consistent baseline (5 of 10 passed, scores 50/50 -> overall 50).
    # SQLite reports the first failing CHECK, so each case is built so that only its own rule is violated,
    # or its rule is the first one that fires.
    (dict(tests_total=0), "ck_evaluations_tests_total"),
    (dict(tests_passed=11, test_pass_rate=110.0, overall_score=0.5 * 110 + 0.3 * 50 + 0.2 * 50),
     "ck_evaluations_tests_passed"),
    (dict(tests_passed=-1, test_pass_rate=-10.0, overall_score=0.5 * -10 + 0.3 * 50 + 0.2 * 50),
     "ck_evaluations_tests_passed"),
    (dict(test_pass_rate=101.0, overall_score=0.5 * 101 + 0.3 * 50 + 0.2 * 50), "ck_evaluations_pass_rate"),
    (dict(correctness_score=-1.0, overall_score=0.5 * 50 + 0.3 * -1 + 0.2 * 50), "ck_evaluations_correctness"),
    (dict(code_quality_score=100.1, overall_score=0.5 * 50 + 0.3 * 50 + 0.2 * 100.1), "ck_evaluations_code_quality"),
    (dict(overall_score=101.0), "ck_evaluations_overall"),
])
def test_evaluation_range_constraints(db, version, kw, constraint):
    _insert_fails(db, consistent_evaluation(version.id, 5, 10, 50, 50, **kw), constraint)


def test_a_consistent_baseline_row_is_accepted(db, version):
    db.add(consistent_evaluation(version.id, 5, 10, 50, 50))
    db.commit()  # the negative cases above differ from this row in exactly one respect
    assert db.scalars(select(Evaluation)).one().overall_score == pytest.approx(50.0)


def test_operational_cost_always_has_a_source(db, version):
    ev = consistent_evaluation(version.id)
    db.add(ev)
    db.commit()
    _insert_fails(db, EvaluationOperationalMetrics(evaluation_id=ev.id, api_cost_usd=0.5))
    _insert_fails(db, EvaluationOperationalMetrics(evaluation_id=ev.id, api_cost_usd=0.5, api_cost_source="guessed"))
    _insert_fails(db, EvaluationOperationalMetrics(evaluation_id=ev.id, execution_time_seconds=-1))


def test_critic_confidence_range_is_enforced_by_the_database(db, version):
    _insert_fails(db, CriticFeedback(version_id=version.id, critic_model_id="m", raw_feedback="x", confidence=1.2))


# ---- indexes, JSON and timestamps ------------------------------------------------------------
def test_expected_indexes_exist(db):
    insp = inspect(db.get_bind())

    def indexed(table):
        return {tuple(ix["column_names"]) for ix in insp.get_indexes(table)}

    assert ("task_id",) in indexed("executions") and ("status",) in indexed("executions")
    assert ("task_id", "created_at") in indexed("executions")
    assert ("execution_id",) in indexed("versions") and ("execution_id",) in indexed("execution_transitions")
    assert ("version_id",) in indexed("evaluations") and ("version_id",) in indexed("critic_feedback")
    assert ("source_execution_id",) in indexed("agent_memories")
    uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("versions")}
    assert ("execution_id", "sequence") in uniques


def test_json_columns_roundtrip_as_structured_data(db, version):
    details = [{"test_name": "t", "expected": "a", "actual": "b", "exception": None, "traceback_excerpt": ["x", "y"]}]
    ev = consistent_evaluation(version.id, 1, 2, 1, 1, failure_details=details)
    fb = CriticFeedback(version_id=version.id, critic_model_id="m", raw_feedback="r",
                        structured_feedback={"a": {"b": [1, 2]}}, identified_issues=[{"k": "v"}], suggested_changes=["s"])
    db.add_all([ev, fb])
    db.commit()
    db.expire_all()
    assert db.get(Evaluation, ev.id).failure_details == details
    got = db.get(CriticFeedback, fb.id)
    assert got.structured_feedback == {"a": {"b": [1, 2]}} and got.identified_issues == [{"k": "v"}]
    t = db.scalars(select(Task)).first()
    assert t.requirements == ["a", "b"] and isinstance(t.requirements, list)


def test_timestamps_are_timezone_aware_utc_and_consistent(db, task):
    db.expire_all()
    got = db.get(Task, task.id)
    assert got.created_at.tzinfo is not None and got.created_at.utcoffset() == timedelta(0)
    assert abs(utcnow() - got.created_at) < timedelta(minutes=1)


def test_naive_datetimes_are_refused(db, task):
    with pytest.raises(Exception):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), None)
    plus5 = timezone(timedelta(hours=5))
    stored = UTCDateTime().process_bind_param(datetime(2026, 1, 1, 12, tzinfo=plus5), None)
    assert stored == datetime(2026, 1, 1, 7)  # normalised to UTC


# ---- transaction behaviour -------------------------------------------------------------------
def test_failed_commit_rolls_back_the_whole_unit_of_work(db, task):
    """A violating row in the same transaction discards the valid rows added alongside it."""
    good = Execution(task_id=task.id)
    bad = Execution(task_id="ghost-task")
    db.add_all([good, bad])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.scalars(select(Execution)).all() == []


def test_evaluation_and_its_metrics_are_written_atomically(db, version, monkeypatch):
    from app.models import evaluation as ev_module

    original = ev_module.EvaluationOperationalMetrics

    def broken_metrics(**kw):
        return original(**{**kw, "api_cost_usd": 1.0, "api_cost_source": None})  # violates ck_ops_cost_has_source

    monkeypatch.setattr(ver, "EvaluationOperationalMetrics", broken_metrics)
    data = EvaluationInput(tests_passed=1, tests_total=2, correctness_score=1, code_quality_score=1,
                           operational={"execution_time_seconds": 1.0})
    with pytest.raises(IntegrityError):
        ver.record_evaluation(db, version.id, data)
    assert db.scalars(select(Evaluation)).all() == []  # the evaluation row was rolled back too
    assert db.scalars(select(EvaluationOperationalMetrics)).all() == []


def test_a_failed_transition_leaves_no_partial_state(db, execution, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("history table unavailable")

    monkeypatch.setattr(exe, "ExecutionTransition", boom)
    with pytest.raises(RuntimeError):
        exe.transition_execution(db, execution.id, S.GENERATING_V1)
    db.rollback()
    db.expire_all()
    ex = db.get(Execution, execution.id)
    assert ex.status == "queued" and ex.started_at is None  # the UPDATE was not committed


def test_invalid_transition_makes_no_changes(db, execution):
    with pytest.raises(InvalidTransitionError):
        exe.transition_execution(db, execution.id, S.COMPLETED)
    db.expire_all()
    assert db.get(Execution, execution.id).status == "queued"
    assert db.scalars(select(ExecutionTransition)).all() == []

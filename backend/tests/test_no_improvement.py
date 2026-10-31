"""The `completed_no_improvement` terminal state.

It means: every permitted revision was recorded, evaluated and rejected, so nothing qualified as an
improvement. It is not a failure, not a cancellation, never carries error information, and has no
outgoing transitions. The revision engine that decides acceptance is a later milestone; these tests
record decisions through `decide_version` the way that engine eventually will.
"""
import pytest

from app.errors import ConflictError, InvalidTransitionError
from app.lifecycle import (
    ExecutionStatus as S,
    TERMINAL_STATUSES,
    allowed_transitions,
    can_transition,
    is_terminal,
)
from app.models import Execution, ExecutionTransition
from app.schemas.evaluation import EvaluationInput
from app.services import execution_service as exe
from app.services import version_service as ver
from sqlalchemy import select
from tests.helpers import advance

NI = S.COMPLETED_NO_IMPROVEMENT
CODE = "def merge_intervals(x):\n    return x\n"

TO_E2 = [S.GENERATING_V1, S.EVALUATING_V1, S.CRITIQUING, S.GENERATING_V2, S.EVALUATING_V2]
TO_E3 = TO_E2 + [S.CRITIQUING_V2, S.GENERATING_V3, S.EVALUATING_V3]


def _evaluation(**kw):
    return EvaluationInput(**{"tests_passed": 7, "tests_total": 10, "correctness_score": 80,
                              "code_quality_score": 90, **kw})


@pytest.fixture
def task_id(make_task):
    return make_task()["id"]


def new_execution(db, task_id, max_revisions=2):
    return exe.create_execution(db, task_id, max_revisions=max_revisions).id


def walk(db, eid, path):
    for status in path:
        advance(db, eid, status)


def record_revisions(db, eid, count, *, decision="rejected", evaluate=True):
    """V1 (accepted baseline) plus `count` revisions, each evaluated and given `decision`."""
    v1 = ver.create_version(db, eid, CODE)
    ver.decide_version(db, v1.id, accepted=True)
    ver.record_evaluation(db, v1.id, _evaluation())
    revisions = []
    for _ in range(count):
        v = ver.create_version(db, eid, CODE + "# revision\n", parent_version_id=v1.id)
        if evaluate:
            ver.record_evaluation(db, v.id, _evaluation(tests_passed=6))
        if decision == "rejected":
            ver.decide_version(db, v.id, accepted=False, rejection_reason="regressed a passing test")
        elif decision == "accepted":
            ver.decide_version(db, v.id, accepted=True)
        revisions.append(v)
    return v1, revisions


def reach_no_improvement_after_v2(db, task_id):
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, TO_E2)
    record_revisions(db, eid, 1)
    return eid


def reach_no_improvement_after_v3(db, task_id):
    eid = new_execution(db, task_id, max_revisions=2)
    walk(db, eid, TO_E3)
    record_revisions(db, eid, 2)
    return eid


# ---- the state in the transition table -------------------------------------------------------
def test_it_is_a_distinct_terminal_state():
    assert NI.value == "completed_no_improvement"
    assert NI in TERMINAL_STATUSES and is_terminal(NI)
    assert NI not in (S.COMPLETED, S.FAILED, S.CANCELLED)


def test_it_has_no_outgoing_transitions():
    assert allowed_transitions(NI) == frozenset()
    assert not any(can_transition(NI, target) for target in S)


def test_the_raw_table_has_no_entries_for_any_terminal_state():
    """allowed_transitions() short-circuits terminal states, which would hide a stray table entry.
    Check the table itself so the two can never disagree."""
    from app import lifecycle

    for terminal in TERMINAL_STATUSES:
        assert lifecycle._FORWARD[terminal] == frozenset(), terminal.value


def test_the_only_incoming_transitions_are_from_the_two_final_evaluation_states():
    sources = {a for a in S if can_transition(a, NI)}
    assert sources == {S.EVALUATING_V2, S.EVALUATING_V3}


# ---- valid entry, persistence, no failure information ----------------------------------------
def test_valid_entry_after_v3_with_both_revisions_rejected(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    ex = exe.transition_execution(db, eid, NI)
    assert ex.status == "completed_no_improvement"


def test_valid_entry_after_v2_when_only_one_revision_is_permitted(client, db, task_id):
    eid = reach_no_improvement_after_v2(db, task_id)
    assert exe.transition_execution(db, eid, NI).status == "completed_no_improvement"


def test_completion_timestamp_and_history_are_persisted(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    before = exe.get_execution(db, eid)
    assert before.completed_at is None
    ex = exe.transition_execution(db, eid, NI)
    assert ex.completed_at is not None and ex.started_at is not None
    assert ex.started_at <= ex.completed_at
    data = client.get(f"/api/executions/{eid}").json()["data"]
    assert data["status"] == "completed_no_improvement"
    assert data["completed_at"] is not None and data["completed_at"].endswith("Z")
    last = data["transitions"][-1]
    assert (last["from_status"], last["to_status"]) == ("evaluating_v3", "completed_no_improvement")
    assert last["occurred_at"] == data["completed_at"]


def test_no_failure_information_is_required_or_stored(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    ex = exe.transition_execution(db, eid, NI)  # no error arguments needed
    assert (ex.error_code, ex.error_message, ex.error_stage) == (None, None, None)
    assert client.get(f"/api/executions/{eid}").json()["data"]["error"] is None


def test_error_information_is_refused_on_this_transition(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    with pytest.raises(ValueError):
        exe.transition_execution(db, eid, NI, error_code="X", error_message="not a failure")
    assert exe.get_execution(db, eid).status == "evaluating_v3"


def test_it_is_not_reported_as_failed_or_cancelled(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    exe.transition_execution(db, eid, NI)
    for status, expected_total in (("failed", 0), ("cancelled", 0), ("completed", 0), ("completed_no_improvement", 1)):
        page = client.get(f"/api/executions?status={status}").json()["data"]
        assert page["total"] == expected_total, status


def test_it_can_be_filtered_by_status_through_the_api(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    exe.transition_execution(db, eid, NI)
    page = client.get("/api/executions?status=completed_no_improvement").json()["data"]
    assert [e["id"] for e in page["items"]] == [eid]


# ---- no premature entry ----------------------------------------------------------------------
def test_not_after_v2_while_a_third_version_is_still_permitted(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=2)
    walk(db, eid, TO_E2)
    record_revisions(db, eid, 1)  # V2 rejected, but V3 is still permitted
    with pytest.raises(InvalidTransitionError, match="Another permitted revision remains"):
        exe.transition_execution(db, eid, NI)
    assert exe.get_execution(db, eid).status == "evaluating_v2"


def test_a_third_version_is_refused_when_only_one_revision_is_permitted(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, TO_E2)
    with pytest.raises(InvalidTransitionError, match="not permitted"):
        exe.transition_execution(db, eid, S.CRITIQUING_V2)
    with pytest.raises(InvalidTransitionError):  # V3 is only reachable through the second critique
        exe.transition_execution(db, eid, S.GENERATING_V3)


@pytest.mark.parametrize("stage", [S.QUEUED, S.GENERATING_V1, S.EVALUATING_V1, S.CRITIQUING, S.GENERATING_V2],
                         ids=lambda s: s.value)
def test_not_from_stages_before_the_final_evaluations(client, db, task_id, stage):
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, {S.QUEUED: [], S.GENERATING_V1: TO_E2[:1], S.EVALUATING_V1: TO_E2[:2],
                   S.CRITIQUING: TO_E2[:3], S.GENERATING_V2: TO_E2[:4]}[stage])
    with pytest.raises(InvalidTransitionError):
        exe.transition_execution(db, eid, NI)
    assert exe.get_execution(db, eid).status == stage.value


@pytest.mark.parametrize("path", [
    TO_E3 + [S.ZK_PROOF],
    TO_E3 + [S.ZK_PROOF, S.IPFS_PUBLISH],
    TO_E3 + [S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER],
], ids=["zk_proof", "ipfs_publish", "blockchain_register"])
def test_not_from_the_publication_stages(client, db, task_id, path):
    eid = new_execution(db, task_id)
    walk(db, eid, path)
    record_revisions(db, eid, 2)
    with pytest.raises(InvalidTransitionError):
        exe.transition_execution(db, eid, NI)


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_not_from_other_terminal_states(client, db, task_id, terminal):
    eid = new_execution(db, task_id)
    if terminal == "cancelled":
        exe.cancel_execution(db, eid)
    elif terminal == "failed":
        exe.fail_execution(db, eid, "TEST", "boom")
    else:
        walk(db, eid, TO_E2 + [S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER, S.COMPLETED])
    with pytest.raises(InvalidTransitionError):
        exe.transition_execution(db, eid, NI)
    assert exe.get_execution(db, eid).status == terminal


# ---- no fabrication: it requires recorded, evaluated, rejected revisions ---------------------
def test_refused_when_no_revision_was_recorded(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, TO_E2)
    with pytest.raises(InvalidTransitionError, match="recorded"):
        exe.transition_execution(db, eid, NI)


def test_refused_when_only_some_permitted_revisions_were_recorded(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=2)
    walk(db, eid, TO_E3)
    record_revisions(db, eid, 1)  # V3 was never recorded
    with pytest.raises(InvalidTransitionError, match="recorded"):
        exe.transition_execution(db, eid, NI)


def test_refused_when_a_revision_was_accepted_as_an_improvement(client, db, task_id):
    """An accepted revision means there WAS an improvement: this state must never be claimed."""
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, TO_E2)
    record_revisions(db, eid, 1, decision="accepted")
    with pytest.raises(InvalidTransitionError, match="accepted as an improvement"):
        exe.transition_execution(db, eid, NI)
    assert exe.get_execution(db, eid).status == "evaluating_v2"


def test_refused_when_the_last_revision_was_accepted_even_if_earlier_ones_were_rejected(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=2)
    walk(db, eid, TO_E3)
    v1, _ = record_revisions(db, eid, 1)
    v3 = ver.create_version(db, eid, CODE + "# v3\n", parent_version_id=v1.id)
    ver.record_evaluation(db, v3.id, _evaluation(tests_passed=10))
    ver.decide_version(db, v3.id, accepted=True)
    with pytest.raises(InvalidTransitionError, match="V3 was accepted"):
        exe.transition_execution(db, eid, NI)


def test_refused_when_a_revision_has_no_decision_yet(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, TO_E2)
    record_revisions(db, eid, 1, decision=None)
    with pytest.raises(InvalidTransitionError, match="no recorded decision"):
        exe.transition_execution(db, eid, NI)


def test_refused_when_a_revision_was_never_evaluated(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, TO_E2)
    record_revisions(db, eid, 1, evaluate=False)
    with pytest.raises(InvalidTransitionError, match="not been evaluated"):
        exe.transition_execution(db, eid, NI)


def test_a_refused_entry_changes_nothing(client, db, task_id):
    eid = new_execution(db, task_id, max_revisions=2)
    walk(db, eid, TO_E2)
    record_revisions(db, eid, 1)
    history_before = len(db.scalars(select(ExecutionTransition).where(ExecutionTransition.execution_id == eid)).all())
    with pytest.raises(InvalidTransitionError):
        exe.transition_execution(db, eid, NI)
    db.expire_all()
    ex = db.get(Execution, eid)
    assert ex.status == "evaluating_v2" and ex.completed_at is None
    assert len(db.scalars(select(ExecutionTransition).where(ExecutionTransition.execution_id == eid)).all()) == history_before


def test_nothing_in_this_milestone_marks_an_execution_improved(client, db, task_id):
    """Reaching the state sets no best version and creates no acceptance on its own."""
    eid = reach_no_improvement_after_v3(db, task_id)
    exe.transition_execution(db, eid, NI)
    ex = exe.get_execution(db, eid)
    assert ex.best_version_id is None
    assert all(v.acceptance_status != "accepted" or v.sequence == 1 for v in ver.list_versions(db, eid))


# ---- terminal: nothing leaves it -------------------------------------------------------------
@pytest.mark.parametrize("target", list(S), ids=lambda s: s.value)
def test_every_transition_out_of_it_is_rejected(client, db, task_id, target):
    eid = reach_no_improvement_after_v3(db, task_id)
    exe.transition_execution(db, eid, NI)
    kwargs = {"error_code": "X", "error_message": "y"} if target is S.FAILED else {}
    with pytest.raises(InvalidTransitionError):
        exe.transition_execution(db, eid, target, **kwargs)
    ex = exe.get_execution(db, eid)
    assert ex.status == "completed_no_improvement" and ex.error_code is None


def test_it_cannot_be_cancelled_through_the_api(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    exe.transition_execution(db, eid, NI)
    r = client.post(f"/api/executions/{eid}/cancel")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_TRANSITION"
    assert client.get(f"/api/executions/{eid}").json()["data"]["status"] == "completed_no_improvement"


def test_no_new_versions_can_be_added_after_it(client, db, task_id):
    eid = reach_no_improvement_after_v3(db, task_id)
    exe.transition_execution(db, eid, NI)
    with pytest.raises(ConflictError):
        ver.create_version(db, eid, CODE)


# ---- concurrency -----------------------------------------------------------------------------
def test_two_racing_entries_only_one_wins(client, db, task_id, monkeypatch):
    """Both workers validated 'evaluating_v3 -> completed_no_improvement'; only one UPDATE may win."""
    eid = reach_no_improvement_after_v3(db, task_id)
    loser = client.app.state.session_factory()
    real_get = exe.get_execution
    try:
        def get_then_let_the_winner_commit(session, execution_id):
            execution = real_get(session, execution_id)
            if session is loser:
                exe.transition_execution(db, eid, NI)
            return execution

        monkeypatch.setattr(exe, "get_execution", get_then_let_the_winner_commit)
        with pytest.raises(ConflictError) as exc:
            exe.transition_execution(loser, eid, NI)
        assert exc.value.code == "CONFLICT" and not isinstance(exc.value, InvalidTransitionError)
    finally:
        loser.close()
    db.expire_all()
    ex = real_get(db, eid)
    assert ex.status == "completed_no_improvement"
    history = [t.to_status for t in ex.transitions]
    assert history.count("completed_no_improvement") == 1  # no duplicate history row


def test_cancel_racing_against_entry_leaves_exactly_one_outcome(client, db, task_id, monkeypatch):
    eid = reach_no_improvement_after_v3(db, task_id)
    loser = client.app.state.session_factory()
    real_get = exe.get_execution
    try:
        def get_then_let_cancel_win(session, execution_id):
            execution = real_get(session, execution_id)
            if session is loser:
                exe.cancel_execution(db, eid)
            return execution

        monkeypatch.setattr(exe, "get_execution", get_then_let_cancel_win)
        with pytest.raises(ConflictError):
            exe.transition_execution(loser, eid, NI)
    finally:
        loser.close()
    db.expire_all()
    ex = real_get(db, eid)
    assert ex.status == "cancelled" and ex.completed_at is not None


# ---- existing terminal behaviour is unchanged ------------------------------------------------
def test_completed_failed_and_cancelled_still_behave_as_before(client, db, task_id):
    a = new_execution(db, task_id)
    walk(db, a, TO_E2 + [S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER, S.COMPLETED])
    done = exe.get_execution(db, a)
    assert done.status == "completed" and done.completed_at is not None and done.error_code is None

    b = new_execution(db, task_id)
    failed = exe.fail_execution(db, b, "BOOM", "it broke")
    assert failed.status == "failed" and failed.error_code == "BOOM" and failed.error_stage == "queued"
    assert failed.completed_at is not None

    c = new_execution(db, task_id)
    cancelled = exe.cancel_execution(db, c)
    assert cancelled.status == "cancelled" and cancelled.completed_at is not None and cancelled.error_code is None


def test_a_normal_improvement_path_still_works_without_the_new_state(client, db, task_id):
    """An accepted revision proceeds to zk_proof exactly as before."""
    eid = new_execution(db, task_id, max_revisions=1)
    walk(db, eid, TO_E2)
    for status in (S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER, S.COMPLETED):
        advance(db, eid, status)
    assert exe.get_execution(db, eid).status == "completed"


# ---- max_revisions policy --------------------------------------------------------------------
def test_the_default_policy_permits_two_revisions(client, make_execution):
    ex = make_execution()
    assert ex["max_revisions"] == 2


@pytest.mark.parametrize("bad", [0, 3, -1])
def test_invalid_revision_policy_is_rejected(client, db, task_id, bad):
    with pytest.raises(ValueError):
        exe.create_execution(db, task_id, max_revisions=bad)


def test_clients_cannot_choose_the_revision_policy(client, task_id):
    r = client.post(f"/api/tasks/{task_id}/executions", json={"max_revisions": 1})
    assert r.status_code == 201 and r.json()["data"]["max_revisions"] == 2  # a body is ignored, never trusted


def test_the_database_enforces_the_policy_range(db, task_id):
    from sqlalchemy.exc import IntegrityError

    for bad in (0, 3):
        db.add(Execution(task_id=task_id, max_revisions=bad))
        with pytest.raises(IntegrityError) as exc:
            db.commit()
        db.rollback()
        assert "ck_executions_max_revisions" in str(exc.value.orig)


# ---- the database knows the new state too ----------------------------------------------------
def test_database_requires_completed_at_for_the_new_state(db, task_id):
    from datetime import timedelta

    from sqlalchemy.exc import IntegrityError

    from app.database import utcnow

    now = utcnow()
    db.add(Execution(task_id=task_id, status="completed_no_improvement", started_at=now - timedelta(seconds=5)))
    with pytest.raises(IntegrityError) as exc:  # terminal but no completion timestamp
        db.commit()
    db.rollback()
    assert "ck_executions_completed_at_iff_terminal" in str(exc.value.orig)

    ok = Execution(task_id=task_id, status="completed_no_improvement", started_at=now - timedelta(seconds=5), completed_at=now)
    db.add(ok)
    db.commit()  # with a completion timestamp and no error fields it is valid
    assert ok.error_code is None


def test_database_forbids_error_fields_on_the_new_state(db, task_id):
    from datetime import timedelta

    from sqlalchemy.exc import IntegrityError

    from app.database import utcnow

    now = utcnow()
    db.add(Execution(task_id=task_id, status="completed_no_improvement", started_at=now, completed_at=now,
                     error_code="X", error_message="y", error_stage="evaluating_v3"))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    db.rollback()
    assert "ck_executions_error_iff_failed" in str(exc.value.orig)

"""Lifecycle transition table and persisted transitions."""
import pytest

from app.errors import ConflictError, InvalidTransitionError, NotFoundError
from app.models import Execution
from app.lifecycle import (
    ExecutionStatus as S,
    TERMINAL_STATUSES,
    allowed_transitions,
    can_transition,
    is_terminal,
)
from app.services import execution_service as svc

HAPPY_PATH = [
    S.GENERATING_V1, S.EVALUATING_V1, S.CRITIQUING, S.GENERATING_V2, S.EVALUATING_V2,
    S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER, S.COMPLETED,
]
PATH_WITH_V3 = [
    S.GENERATING_V1, S.EVALUATING_V1, S.CRITIQUING, S.GENERATING_V2, S.EVALUATING_V2,
    S.GENERATING_V3, S.EVALUATING_V3, S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER, S.COMPLETED,
]
NON_TERMINAL = [s for s in S if s not in TERMINAL_STATUSES]


# ---- pure transition table -------------------------------------------------------------------
def test_terminal_states_have_no_outgoing_transitions():
    assert TERMINAL_STATUSES == {S.COMPLETED, S.COMPLETED_NO_IMPROVEMENT, S.FAILED, S.CANCELLED}
    for s in TERMINAL_STATUSES:
        assert is_terminal(s) and allowed_transitions(s) == frozenset()


@pytest.mark.parametrize("status", NON_TERMINAL)
def test_every_non_terminal_state_can_fail_or_be_cancelled(status):
    assert S.FAILED in allowed_transitions(status) and S.CANCELLED in allowed_transitions(status)


def test_table_matches_the_approved_lifecycle_exactly():
    forward = {(a, b) for a in S for b in allowed_transitions(a) if b not in (S.FAILED, S.CANCELLED)}
    expected = set(zip([S.QUEUED] + HAPPY_PATH[:-1], HAPPY_PATH))
    expected |= {(S.EVALUATING_V2, S.GENERATING_V3), (S.GENERATING_V3, S.EVALUATING_V3), (S.EVALUATING_V3, S.ZK_PROOF)}
    # the only addition since the original lifecycle: no-improvement is reachable from the two final evaluation states
    expected |= {(S.EVALUATING_V2, S.COMPLETED_NO_IMPROVEMENT), (S.EVALUATING_V3, S.COMPLETED_NO_IMPROVEMENT)}
    assert forward == expected


def test_every_state_is_reachable_from_queued():
    seen, frontier = {S.QUEUED}, [S.QUEUED]
    while frontier:
        for nxt in allowed_transitions(frontier.pop()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert seen == set(S)


def test_no_state_transitions_to_itself():
    assert not any(can_transition(s, s) for s in S)


# ---- persisted transitions -------------------------------------------------------------------
def _new_execution(client, make_execution, db):
    ex = make_execution()
    return ex["id"]


@pytest.mark.parametrize("path", [HAPPY_PATH, PATH_WITH_V3], ids=["without_v3", "with_v3"])
def test_full_path_is_persisted_with_history(client, make_execution, db, path):
    eid = _new_execution(client, make_execution, db)
    for status in path:
        ex = svc.transition_execution(db, eid, status)
        assert ex.status == status.value
    data = client.get(f"/api/executions/{eid}").json()["data"]
    assert data["status"] == "completed"
    assert [t["to_status"] for t in data["transitions"]] == ["queued"] + [s.value for s in path]
    assert data["transitions"][0]["from_status"] is None
    for prev, cur in zip(data["transitions"], data["transitions"][1:]):
        assert cur["from_status"] == prev["to_status"]
    times = [t["occurred_at"] for t in data["transitions"]]
    assert times == sorted(times)  # timestamps never go backwards
    assert data["started_at"] is not None and data["completed_at"] is not None
    assert data["started_at"] <= data["completed_at"]
    assert data["error"] is None


def test_started_at_is_set_when_work_begins_not_at_creation(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    assert svc.get_execution(db, eid).started_at is None
    ex = svc.transition_execution(db, eid, S.GENERATING_V1)
    assert ex.started_at is not None
    started = ex.started_at
    svc.transition_execution(db, eid, S.EVALUATING_V1)
    assert svc.get_execution(db, eid).started_at == started  # unchanged by later transitions


BASE_PATH = [S.GENERATING_V1, S.EVALUATING_V1, S.CRITIQUING, S.GENERATING_V2, S.EVALUATING_V2]
TAIL_PATH = [S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER]


def _path_to(target):
    """Valid sequence of transitions from `queued` up to and including `target` (non-terminal)."""
    if target is S.QUEUED:
        return []
    full = BASE_PATH + TAIL_PATH if target in TAIL_PATH else BASE_PATH + [S.GENERATING_V3, S.EVALUATING_V3]
    return full[: full.index(target) + 1]


def _walk_to(db, eid, target):
    for s in _path_to(target):
        svc.transition_execution(db, eid, s)


INVALID_FROM_QUEUED = [s for s in S if s not in (S.GENERATING_V1, S.FAILED, S.CANCELLED, S.QUEUED)]


@pytest.mark.parametrize("target", INVALID_FROM_QUEUED, ids=lambda s: s.value)
def test_cannot_skip_ahead_from_queued(client, make_execution, db, target):
    eid = _new_execution(client, make_execution, db)
    with pytest.raises(InvalidTransitionError):
        svc.transition_execution(db, eid, target)
    ex = svc.get_execution(db, eid)
    assert ex.status == "queued"  # unchanged
    assert len(ex.transitions) == 1  # and no history row was written


def test_cannot_move_backwards(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    _walk_to(db, eid, S.CRITIQUING)
    for back in (S.QUEUED, S.GENERATING_V1, S.EVALUATING_V1):
        with pytest.raises(InvalidTransitionError):
            svc.transition_execution(db, eid, back)
    assert svc.get_execution(db, eid).status == "critiquing"


def test_cannot_skip_the_critique_or_the_proof_stage(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    _walk_to(db, eid, S.EVALUATING_V1)
    with pytest.raises(InvalidTransitionError):
        svc.transition_execution(db, eid, S.GENERATING_V2)  # critiquing is required first
    for s in (S.CRITIQUING, S.GENERATING_V2, S.EVALUATING_V2):
        svc.transition_execution(db, eid, s)
    with pytest.raises(InvalidTransitionError):
        svc.transition_execution(db, eid, S.IPFS_PUBLISH)  # zk_proof is required first
    with pytest.raises(InvalidTransitionError):
        svc.transition_execution(db, eid, S.COMPLETED)


@pytest.mark.parametrize("terminal", [S.COMPLETED, S.FAILED, S.CANCELLED], ids=lambda s: s.value)
def test_terminal_states_reject_every_further_transition(client, make_execution, db, terminal):
    # completed_no_improvement is covered by tests/test_no_improvement.py
    eid = _new_execution(client, make_execution, db)
    if terminal is S.CANCELLED:
        svc.cancel_execution(db, eid)
    elif terminal is S.FAILED:
        svc.fail_execution(db, eid, "TEST", "boom")
    else:
        for s in HAPPY_PATH:
            svc.transition_execution(db, eid, s)
    for target in S:
        kwargs = {"error_code": "X", "error_message": "y"} if target is S.FAILED else {}
        with pytest.raises(InvalidTransitionError):
            svc.transition_execution(db, eid, target, **kwargs)
    assert svc.get_execution(db, eid).status == terminal.value


def test_unknown_status_is_rejected(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    with pytest.raises(ValueError):
        svc.transition_execution(db, eid, "teleporting")
    assert svc.get_execution(db, eid).status == "queued"


def test_transition_of_missing_execution(db):
    with pytest.raises(NotFoundError):
        svc.transition_execution(db, "missing", S.GENERATING_V1)


# ---- failure handling ------------------------------------------------------------------------
@pytest.mark.parametrize("stage", NON_TERMINAL, ids=lambda s: s.value)
def test_failure_from_any_stage_preserves_error_information(client, make_execution, db, stage):
    eid = _new_execution(client, make_execution, db)
    _walk_to(db, eid, stage)
    ex = svc.fail_execution(db, eid, "GENERATOR_TIMEOUT", "The generator did not respond in time.")
    assert ex.status == "failed"
    assert (ex.error_code, ex.error_message, ex.error_stage) == (
        "GENERATOR_TIMEOUT", "The generator did not respond in time.", stage.value,
    )
    assert ex.completed_at is not None
    data = client.get(f"/api/executions/{eid}").json()["data"]
    assert data["error"] == {
        "code": "GENERATOR_TIMEOUT", "message": "The generator did not respond in time.", "stage": stage.value,
    }
    assert data["transitions"][-1]["to_status"] == "failed"


def test_failure_requires_error_information(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    with pytest.raises(ValueError):
        svc.transition_execution(db, eid, S.FAILED)
    with pytest.raises(ValueError):
        svc.fail_execution(db, eid, "", "message")
    assert svc.get_execution(db, eid).status == "queued"


def test_error_information_is_rejected_on_non_failure_transitions(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    with pytest.raises(ValueError):
        svc.transition_execution(db, eid, S.GENERATING_V1, error_code="X", error_message="y")


def test_overlong_error_message_is_truncated_not_rejected(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    ex = svc.fail_execution(db, eid, "X" * 200, "m" * 10_000)
    assert len(ex.error_code) == svc.MAX_ERROR_CODE and len(ex.error_message) == svc.MAX_ERROR_MESSAGE


def test_cancelled_execution_has_no_error_information(client, make_execution, db):
    eid = _new_execution(client, make_execution, db)
    ex = svc.cancel_execution(db, eid)
    assert ex.error_code is None and ex.error_message is None and ex.error_stage is None


# ---- concurrency -----------------------------------------------------------------------------
def test_stale_transition_loses_the_race_and_changes_nothing(client, make_execution, db, monkeypatch):
    """Two workers both validated 'queued -> generating_v1'; only one UPDATE may win.

    The check-then-update window is reproduced deterministically: the loser's pre-check sees
    'queued', then the winner commits before the loser's UPDATE runs. Only the compare-and-swap
    guard in the UPDATE can stop the loser (the transition table would allow it).
    """
    eid = _new_execution(client, make_execution, db)
    loser = client.app.state.session_factory()
    real_get = svc.get_execution
    try:
        def stale_get(session, execution_id):
            execution = real_get(session, execution_id)
            if session is loser:  # the winner commits right after the loser has validated
                svc.transition_execution(db, eid, S.GENERATING_V1)
            return execution

        monkeypatch.setattr(svc, "get_execution", stale_get)
        with pytest.raises(ConflictError) as exc:
            svc.transition_execution(loser, eid, S.GENERATING_V1)
        assert exc.value.code == "CONFLICT" and not isinstance(exc.value, InvalidTransitionError)
    finally:
        loser.close()
    ex = real_get(db, eid)
    db.refresh(ex)
    assert ex.status == "generating_v1"
    assert [t.to_status for t in ex.transitions] == ["queued", "generating_v1"]  # no duplicate history


def test_transition_table_is_not_accidentally_widened():
    # 14 forward edges (evaluating_v2 has three: generating_v3, zk_proof, completed_no_improvement;
    # evaluating_v3 has two: zk_proof, completed_no_improvement) plus failed/cancelled from each of the
    # 11 non-terminal states = 36 allowed transitions in total.
    fan_out = {s: len(allowed_transitions(s) - {S.FAILED, S.CANCELLED}) for s in NON_TERMINAL}
    assert fan_out[S.EVALUATING_V2] == 3 and fan_out[S.EVALUATING_V3] == 2
    assert all(v == 1 for k, v in fan_out.items() if k not in (S.EVALUATING_V2, S.EVALUATING_V3))
    assert sum(len(allowed_transitions(s)) for s in S) == 36

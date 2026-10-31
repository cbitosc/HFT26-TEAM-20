"""Execution lifecycle: the states and the only transitions allowed between them.

This module only defines state and legality. The orchestrator (services/orchestrator.py) drives the
generation, evaluation and critique states. Nothing yet performs the publishing states (`zk_proof`,
`ipfs_publish`, `blockchain_register`).
"""
from enum import Enum


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    GENERATING_V1 = "generating_v1"
    EVALUATING_V1 = "evaluating_v1"
    CRITIQUING = "critiquing"
    GENERATING_V2 = "generating_v2"
    EVALUATING_V2 = "evaluating_v2"
    CRITIQUING_V2 = "critiquing_v2"  # optional: second critique, after a rejected V2, before V3
    GENERATING_V3 = "generating_v3"  # optional
    EVALUATING_V3 = "evaluating_v3"  # optional
    ZK_PROOF = "zk_proof"
    IPFS_PUBLISH = "ipfs_publish"
    BLOCKCHAIN_REGISTER = "blockchain_register"
    COMPLETED = "completed"
    # A valid, finished run in which every permitted revision was evaluated and none was accepted
    # as an improvement. It is not a failure and not a cancellation, and it never carries error info.
    COMPLETED_NO_IMPROVEMENT = "completed_no_improvement"
    FAILED = "failed"
    CANCELLED = "cancelled"


S = ExecutionStatus

TERMINAL_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {S.COMPLETED, S.COMPLETED_NO_IMPROVEMENT, S.FAILED, S.CANCELLED}
)

# Revisions (V2, V3, ...) an execution may attempt. V1 is the baseline and is not a revision.
# `max_revisions` is stored per execution; the lifecycle table alone cannot know it, so the
# service layer enforces it (see execution_service).
MIN_REVISIONS = 1
MAX_REVISIONS = 2
DEFAULT_MAX_REVISIONS = 2

# Forward path only. failed/cancelled are reachable from every non-terminal state (see below).
#
# Completion is decoupled from publishing (Milestone 07B): evaluating_v2/v3 -> completed is allowed
# when the best version is a verified accepted improvement (guard in execution_service). The
# publishing states zk_proof -> ipfs_publish -> blockchain_register remain reachable and guarded, as a
# separate path that completion does not require; they will move to their own workflow later.
#
# critiquing_v2 is the second critique, after a rejected V2 and before V3. The service layer requires
# max_revisions = 2 and that no revision was accepted (an accepted V2 must complete instead).
# completed_no_improvement is reachable only from the final evaluation states; the service layer
# additionally requires the permitted revisions to be exhausted and rejected.
_FORWARD: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    S.QUEUED: frozenset({S.GENERATING_V1}),
    S.GENERATING_V1: frozenset({S.EVALUATING_V1}),
    S.EVALUATING_V1: frozenset({S.CRITIQUING}),
    S.CRITIQUING: frozenset({S.GENERATING_V2}),
    S.GENERATING_V2: frozenset({S.EVALUATING_V2}),
    S.EVALUATING_V2: frozenset({S.COMPLETED, S.CRITIQUING_V2, S.ZK_PROOF, S.COMPLETED_NO_IMPROVEMENT}),
    S.CRITIQUING_V2: frozenset({S.GENERATING_V3}),
    S.GENERATING_V3: frozenset({S.EVALUATING_V3}),
    S.EVALUATING_V3: frozenset({S.COMPLETED, S.ZK_PROOF, S.COMPLETED_NO_IMPROVEMENT}),
    S.ZK_PROOF: frozenset({S.IPFS_PUBLISH}),
    S.IPFS_PUBLISH: frozenset({S.BLOCKCHAIN_REGISTER}),
    S.BLOCKCHAIN_REGISTER: frozenset({S.COMPLETED}),
    S.COMPLETED: frozenset(),
    S.COMPLETED_NO_IMPROVEMENT: frozenset(),
    S.FAILED: frozenset(),
    S.CANCELLED: frozenset(),
}


def is_terminal(status: ExecutionStatus) -> bool:
    return status in TERMINAL_STATUSES


def allowed_transitions(status: ExecutionStatus) -> frozenset[ExecutionStatus]:
    if is_terminal(status):
        return frozenset()
    return _FORWARD[status] | {S.FAILED, S.CANCELLED}


def can_transition(current: ExecutionStatus, target: ExecutionStatus) -> bool:
    return target in allowed_transitions(current)


def status_values() -> list[str]:
    return [s.value for s in ExecutionStatus]

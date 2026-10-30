"""Execution lifecycle: the states and the only transitions allowed between them.

This module only defines state and legality. It does not run any pipeline stage. A status
such as `zk_proof` or `ipfs_publish` describes where an execution is, and nothing in this
milestone performs that work.
"""
from enum import Enum


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    GENERATING_V1 = "generating_v1"
    EVALUATING_V1 = "evaluating_v1"
    CRITIQUING = "critiquing"
    GENERATING_V2 = "generating_v2"
    EVALUATING_V2 = "evaluating_v2"
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
# completed_no_improvement is reachable only from the final evaluation states; the service layer
# additionally requires the permitted revisions to be exhausted and rejected.
_FORWARD: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    S.QUEUED: frozenset({S.GENERATING_V1}),
    S.GENERATING_V1: frozenset({S.EVALUATING_V1}),
    S.EVALUATING_V1: frozenset({S.CRITIQUING}),
    S.CRITIQUING: frozenset({S.GENERATING_V2}),
    S.GENERATING_V2: frozenset({S.EVALUATING_V2}),
    S.EVALUATING_V2: frozenset({S.GENERATING_V3, S.ZK_PROOF, S.COMPLETED_NO_IMPROVEMENT}),
    S.GENERATING_V3: frozenset({S.EVALUATING_V3}),
    S.EVALUATING_V3: frozenset({S.ZK_PROOF, S.COMPLETED_NO_IMPROVEMENT}),
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

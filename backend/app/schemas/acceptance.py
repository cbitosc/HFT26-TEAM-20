"""Request and response models for evaluation, acceptance and evidence.

The request models have NO fields and forbid extras: a caller can ask for an evaluation or a
decision, but any attempt to send scores, a verdict, an improvement claim or a ZK status is a 422.
Every response is hidden-test safe: hidden tests appear only as counts.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Outcome = Literal["baseline", "validated_improvement", "rejected_attempt", "invalid_comparison"]


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreSnapshot(BaseModel):
    version_id: str
    label: str
    evaluation_id: str
    code_sha256: str
    tests_passed: int  # hidden suite
    tests_total: int  # hidden suite
    public_tests_passed: int
    public_tests_total: int
    test_pass_rate: float  # hidden suite
    correctness_score: float
    code_quality_score: float
    overall_score: float


class FailedTermRead(BaseModel):
    term: str
    message: str


class AcceptanceDecisionRead(BaseModel):
    version_id: str
    label: str
    outcome: Outcome
    acceptance_status: str  # the version's status after this request (pending after invalid_comparison)
    reason: str
    failed_terms: list[FailedTermRead]
    candidate: ScoreSnapshot | None
    previous_best: ScoreSnapshot | None
    best_version_id: str | None  # the best version AFTER this request
    evidence_id: str | None
    invalid_comparison_id: str | None
    decided_at: datetime | None


class CommitmentRead(BaseModel):
    suite_id: str
    suite_hash: str
    public_suite_hash: str
    hidden_suite_hash: str
    evaluator_config_hash: str
    scoring_rule_version: str
    delta: float
    committed_at: datetime
    onchain: Literal["planned"] = "planned"  # no Sepolia commitment exists yet

    @classmethod
    def from_execution(cls, ex) -> "CommitmentRead | None":
        if ex.suite_hash is None:
            return None
        return cls(suite_id=ex.suite_id, suite_hash=ex.suite_hash, public_suite_hash=ex.public_suite_hash,
                   hidden_suite_hash=ex.hidden_suite_hash, evaluator_config_hash=ex.evaluator_config_hash,
                   scoring_rule_version=ex.scoring_rule_version, delta=ex.delta, committed_at=ex.committed_at)


class BundleRequest(BaseModel):
    """No fields: a client can ask for a bundle to be built but cannot supply content, scores or hashes."""

    model_config = ConfigDict(extra="forbid")


class BundleRef(BaseModel):
    id: str
    include_code: bool
    bundle_sha256: str


class EvidenceBundleRead(BaseModel):
    id: str
    evidence_record_id: str
    status: Literal["validated_improvement", "rejected_attempt"]
    include_code: bool
    bundle_sha256: str  # as stored
    recomputed_sha256: str  # recomputed now over bundle_json
    hash_valid: bool
    canonical: bool
    bundle_json: str  # the exact canonical text the hash covers (verify over its UTF-8 bytes)
    bundle: dict
    created_at: datetime


class EvidenceRead(BaseModel):
    id: str
    status: Literal["validated_improvement", "rejected_attempt"]
    candidate_version_id: str
    previous_best_version_id: str
    candidate_evaluation_id: str
    previous_evaluation_id: str
    failed_terms: list[FailedTermRead]
    candidate_scores: dict
    previous_scores: dict
    provenance: dict
    created_at: datetime
    bundles: list[BundleRef] = []


class InvalidComparisonRead(BaseModel):
    id: str
    status: Literal["invalid_comparison"] = "invalid_comparison"
    candidate_version_id: str
    previous_best_version_id: str | None
    reasons: list[FailedTermRead]
    note: str = "Not evidence about the revision: the comparison could not validly occur."
    created_at: datetime


class ExecutionEvidenceRead(BaseModel):
    execution_id: str
    commitment: CommitmentRead | None
    best_version_id: str | None
    scoring_rule: dict
    records: list[EvidenceRead]
    invalid_comparisons: list[InvalidComparisonRead]
    unvalidated_proposals: int  # Critic feedback rows: advisory only, never evidence

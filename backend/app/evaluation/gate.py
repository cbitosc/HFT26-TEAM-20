"""The acceptance policy (app.evaluation.policy) as pure functions.

`preconditions` decides whether a comparison may happen at all; a failure is an invalid_comparison.
`compare` applies the predicate; a failure is a rejected_attempt, and EVERY failed term is reported
(not only the first), each with a stable term id from app.evaluation.policy.

A higher aggregate never excuses breaking a previously passing test or a drop in any dimension.
Comparisons use the 1e-9 tolerance of the database score constraints, so float noise is neither an
improvement nor a regression.

Messages are hidden-test safe: they name public tests and only COUNT hidden ones. This module reads
numbers and test ids only; it cannot see Critic feedback, confidence, or any caller-supplied value.
"""
from dataclasses import dataclass

from app.evaluation import policy
from app.hashing import code_sha256
from app.scoring import SCORE_TOLERANCE


@dataclass(frozen=True)
class FailedTerm:
    term: str
    message: str

    def as_dict(self) -> dict:
        return {"term": self.term, "message": self.message}


@dataclass(frozen=True)
class Commitment:
    suite_hash: str
    evaluator_config_hash: str
    scoring_rule_version: str
    delta: float


@dataclass(frozen=True)
class EvalSnapshot:
    version_id: str
    execution_id: str
    label: str
    evaluation_id: str
    suite_hash: str
    evaluator_version: str
    evaluator_config_hash: str
    scoring_rule_version: str
    code_sha256: str  # recorded by the evaluation: the code it ran
    stored_code_sha256: str  # the version's recorded hash
    current_code_sha256: str  # recomputed now from the version's stored code
    passed_tests: frozenset[str]
    hidden_ids: frozenset[str]
    tests_passed: int  # hidden
    tests_total: int  # hidden
    public_tests_passed: int
    public_tests_total: int
    test_pass_rate: float  # hidden
    correctness_score: float
    code_quality_score: float
    overall_score: float


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    failed_terms: tuple[FailedTerm, ...]

    @property
    def violations(self) -> tuple[str, ...]:
        return tuple(t.message for t in self.failed_terms)


def snapshot(version, evaluation) -> EvalSnapshot:
    results = evaluation.test_results
    return EvalSnapshot(
        version_id=version.id,
        execution_id=version.execution_id,
        label=version.label,
        evaluation_id=evaluation.id,
        suite_hash=evaluation.suite_hash,
        evaluator_version=evaluation.evaluator_version,
        evaluator_config_hash=evaluation.evaluator_config_hash,
        scoring_rule_version=evaluation.scoring_rule_version,
        code_sha256=evaluation.code_sha256,
        stored_code_sha256=version.code_sha256,
        current_code_sha256=code_sha256(version.code),
        passed_tests=frozenset(r["test_id"] for r in results if r["passed"]),
        hidden_ids=frozenset(r["test_id"] for r in results if r.get("visibility") == "hidden"),
        tests_passed=evaluation.tests_passed,
        tests_total=evaluation.tests_total,
        public_tests_passed=evaluation.public_tests_passed or 0,
        public_tests_total=evaluation.public_tests_total or 0,
        test_pass_rate=evaluation.test_pass_rate,
        correctness_score=evaluation.correctness_score,
        code_quality_score=evaluation.code_quality_score,
        overall_score=evaluation.overall_score,
    )


def scores(snap: EvalSnapshot) -> dict:
    """Hidden-safe summary of a snapshot (no test ids)."""
    return {
        "version_id": snap.version_id, "label": snap.label, "evaluation_id": snap.evaluation_id,
        "code_sha256": snap.code_sha256,
        "tests_passed": snap.tests_passed, "tests_total": snap.tests_total,
        "public_tests_passed": snap.public_tests_passed, "public_tests_total": snap.public_tests_total,
        "test_pass_rate": snap.test_pass_rate, "correctness_score": snap.correctness_score,
        "code_quality_score": snap.code_quality_score, "overall_score": snap.overall_score,
    }


def _fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def preconditions(commitment: Commitment, previous: EvalSnapshot, candidate: EvalSnapshot) -> tuple[FailedTerm, ...]:
    """Both snapshots must come from complete evaluations (checked by the caller, which reports
    missing/incomplete evaluations with the same term ids)."""
    failed: list[FailedTerm] = []
    if previous.execution_id != candidate.execution_id:
        failed.append(FailedTerm(policy.PRE_SAME_EXECUTION, "the versions belong to different executions"))
    for snap in (previous, candidate):
        if snap.suite_hash != commitment.suite_hash:
            failed.append(FailedTerm(policy.PRE_SAME_SUITE,
                                     f"{snap.label} was evaluated with a suite other than the committed one"))
        if snap.evaluator_config_hash != commitment.evaluator_config_hash:
            failed.append(FailedTerm(policy.PRE_SAME_CONFIG,
                                     f"{snap.label} was evaluated with an evaluator configuration other than the committed one"))
        if snap.scoring_rule_version != commitment.scoring_rule_version:
            failed.append(FailedTerm(policy.PRE_SAME_RULE,
                                     f"{snap.label} was scored under scoring rule {snap.scoring_rule_version}, "
                                     f"not the committed {commitment.scoring_rule_version}"))
        if not code_matches(snap):
            failed.append(FailedTerm(policy.PRE_SAME_CODE,
                                     f"the evaluation of {snap.label} does not belong to the code currently stored "
                                     "for it (code SHA-256 mismatch)"))
    return tuple(failed)


def code_matches(snap: EvalSnapshot) -> bool:
    """The evaluation ran exactly the code now stored, and the version's recorded hash is intact."""
    return snap.code_sha256 == snap.current_code_sha256 == snap.stored_code_sha256


def compare(previous: EvalSnapshot, candidate: EvalSnapshot, delta: float = policy.DELTA) -> GateResult:
    failed: list[FailedTerm] = []
    regressed = previous.passed_tests - candidate.passed_tests
    if regressed:
        public = sorted(regressed - previous.hidden_ids)
        hidden = len(regressed & previous.hidden_ids)
        parts = ([f"public test(s) {', '.join(public)}"] if public else []) + ([f"{hidden} hidden test(s)"] if hidden else [])
        failed.append(FailedTerm(policy.TERM_TEST_REGRESSION,
                                 f"{' and '.join(parts)} passed in {previous.label} but fail in {candidate.label}"))
    for term, name, before, after in (
        (policy.TERM_PASS_RATE, "hidden-suite pass rate", previous.test_pass_rate, candidate.test_pass_rate),
        (policy.TERM_CORRECTNESS, "correctness", previous.correctness_score, candidate.correctness_score),
        (policy.TERM_QUALITY, "code quality", previous.code_quality_score, candidate.code_quality_score),
    ):
        if after < before - SCORE_TOLERANCE:
            failed.append(FailedTerm(term, f"{name} regressed from {_fmt(before)} to {_fmt(after)}"))
    if not candidate.overall_score >= previous.overall_score + delta - SCORE_TOLERANCE:
        failed.append(FailedTerm(
            policy.TERM_DELTA,
            f"aggregate score {_fmt(candidate.overall_score)} is not at least {previous.label}'s "
            f"{_fmt(previous.overall_score)} + delta {_fmt(delta)}",
        ))
    return GateResult(accepted=not failed, failed_terms=tuple(failed))

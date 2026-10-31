"""Shared test builders. Rows built here satisfy every database constraint, including the
score-consistency checks, so a test that expects a rejection changes exactly one thing."""
from app.hashing import code_sha256
from app.models import Evaluation
from app.scoring import compute_overall_score, compute_test_pass_rate

X_SHA256 = code_sha256("x")


def consistent_evaluation(
    version_id: str,
    passed: int = 1,
    total: int = 1,
    correctness: float = 100.0,
    quality: float = 100.0,
    **overrides,
) -> Evaluation:
    """An Evaluation ORM row whose stored pass rate and overall score match the approved formula.

    Positional values are the *inputs*; `overrides` are column names (tests_passed, tests_total,
    test_pass_rate, correctness_score, code_quality_score, overall_score) applied afterwards, so a
    test can break exactly one stored value."""
    rate = compute_test_pass_rate(passed, total) if total else 0.0
    fields = dict(
        version_id=version_id,
        code_sha256=X_SHA256,  # the hash of "x", the code the constraint tests' versions store
        tests_passed=passed,
        tests_total=total,
        test_pass_rate=rate,
        correctness_score=correctness,
        code_quality_score=quality,
        overall_score=compute_overall_score(rate, correctness, quality),
    )
    fields.update(overrides)
    return Evaluation(**fields)


# ---- complete evaluations and legitimately accepted versions, built through the real services ----
# Stored evaluations for gate tests carry the SAME provenance an execution commits to (the real suite
# hash, the default evaluator configuration hash, the current scoring rule), so they are comparable.
# Their per-test outcomes are synthetic ids: these tests exercise the gate, not the engine.
from app.evaluation import policy  # noqa: E402
from app.evaluation.execution import RunLimits  # noqa: E402
from app.evaluation.provenance import evaluator_config_hash  # noqa: E402
from app.evaluation.suites import get_suite  # noqa: E402

SUITE_ID = "python-merge-intervals-v1"
SUITE_HASH = get_suite(SUITE_ID).suite_hash
CONFIG_HASH = evaluator_config_hash(RunLimits())
OTHER_HASH = "b" * 64


def complete_input(passed: int = 5, *, passed_ids=None, correctness: float = 80.0, quality: float = 80.0,
                   suite_hash: str = SUITE_HASH, config_hash: str = CONFIG_HASH,
                   rule: str = policy.SCORING_RULE_VERSION, total: int = 10,
                   public_passed_ids=None, public_total: int = 0):
    """An EvaluationInput with full provenance and per-test outcomes (what the gate requires).
    Hidden tests are t0..t{total-1}; by default the first `passed` pass. Public tests are p0.. ."""
    from app.schemas.evaluation import EvaluationInput, TestOutcome

    ids = [f"t{i}" for i in range(total)]
    ok = set(passed_ids) if passed_ids is not None else set(ids[:passed])
    public_ids = [f"p{i}" for i in range(public_total)]
    public_ok = set(public_passed_ids) if public_passed_ids is not None else set(public_ids)
    return EvaluationInput(
        tests_passed=len(ok), tests_total=total, correctness_score=correctness, code_quality_score=quality,
        public_tests_passed=len(public_ok), public_tests_total=public_total,
        suite_id=SUITE_ID, suite_hash=suite_hash, evaluator_version="1", evaluator_config_hash=config_hash,
        scoring_rule_version=rule,
        test_results=[TestOutcome(test_id=i, visibility="public", passed=i in public_ok) for i in public_ids]
        + [TestOutcome(test_id=i, visibility="hidden", passed=i in ok) for i in ids],
    )


def grant_improvement(db, execution_id: str):
    """Create V1 and V2 with complete evaluations and have the real acceptance service accept both
    (V2 strictly better, nothing regressing). Returns (v1, v2)."""
    from app.services import acceptance_service as acc
    from app.services import version_service as ver

    v1 = ver.create_version(db, execution_id, "def merge_intervals(x):\n    return x\n")
    ver.record_evaluation(db, v1.id, complete_input(5))
    acc.decide_acceptance(db, v1.id)
    v2 = ver.create_version(db, execution_id, "def merge_intervals(x):\n    return list(x)\n", parent_version_id=v1.id)
    ver.record_evaluation(db, v2.id, complete_input(8))
    acc.decide_acceptance(db, v2.id)
    return v1, v2


def advance(db, execution_id: str, status):
    """Transition via the real service. Entering `zk_proof` needs a real accepted improvement, so one is
    created through the real services first (once)."""
    from app.lifecycle import ExecutionStatus
    from app.services import execution_service as exe

    if ExecutionStatus(status) is ExecutionStatus.ZK_PROOF and exe.get_execution(db, execution_id).best_version_id is None:
        grant_improvement(db, execution_id)
    return exe.transition_execution(db, execution_id, status)

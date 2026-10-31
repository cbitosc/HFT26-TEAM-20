"""Turn a candidate's source code into deterministic evaluation results.

hidden pass rate = hidden tests passed / hidden tests * 100  (from actual execution; this is P)
public results   = recorded per test, never part of the score (they guard against regressions)
correctness      = 100 * contract checks passed / 5          (interface conformance; see below)
code quality     = static_quality.analyze(...)               (AST checks; see static_quality.py)

Correctness is deliberately NOT the test pass rate. It is the share of these five interface-contract
checks that hold, so the two dimensions can disagree:
  compiles                                the source compiles
  imports_cleanly                         executing the module raises nothing
  entrypoint_defined                      the required callable exists after import
  entrypoint_accepts_expected_arguments   its signature accepts the required number of arguments
  smoke_call_returns_expected_type        a trivially valid call returns exactly the expected built-in type
Limitation: a solution can score 100 here and fail every behavioural test, and a solution that passes
tests while violating the contract scores low here. It says nothing about general correctness. In
practice almost any code that defines the entry point scores 100, so C mostly separates "broken
module" from "loads"; it rarely separates two working revisions.

No LLM is involved at any step, and the same source + suite + evaluator configuration gives the same
result. Wall-clock time is measured but is reported separately and never enters a score.

Hidden-test confidentiality: `test_results` and `failure_details` carry a `visibility` field; API
schemas strip hidden entries. The breakdown below contains no hidden test ids.
"""
import time
from dataclasses import dataclass, field

from app.evaluation.execution import SMOKE_ID, RunLimits, run_candidate
from app.evaluation.static_quality import analyze
from app.evaluation.suite import EVALUATOR_VERSION, EvaluationSuite

CORRECTNESS_CHECK_IDS = (
    "compiles",
    "imports_cleanly",
    "entrypoint_defined",
    "entrypoint_accepts_expected_arguments",
    "smoke_call_returns_expected_type",
)


@dataclass(frozen=True)
class EvaluationOutcome:
    suite_id: str
    suite_hash: str
    public_suite_hash: str
    hidden_suite_hash: str
    evaluator_version: str
    tests_passed: int  # hidden
    tests_total: int  # hidden
    public_tests_passed: int
    public_tests_total: int
    test_results: list[dict]  # [{"test_id", "visibility", "passed"}] in suite order (internal)
    failure_details: list[dict]  # each carries "visibility" (internal)
    correctness_score: float
    code_quality_score: float
    breakdown: dict  # hidden-safe
    elapsed_seconds: float  # operational; never part of a score
    timed_out_items: list[str] = field(default_factory=list)  # internal; may contain hidden ids


def evaluate_source(source: str, suite: EvaluationSuite, limits: RunLimits) -> EvaluationOutcome:
    if not suite.tests:
        raise ValueError("an evaluation suite must contain at least one test")
    if not suite.hidden_tests:
        raise ValueError("an evaluation suite must contain at least one hidden test (the score uses hidden tests)")
    started = time.perf_counter()
    report = run_candidate(source, suite, limits)
    quality = analyze(source, suite.entrypoint, suite.quality)

    test_results, failures = [], []
    for test in suite.tests:
        outcome = report.outcomes[test.id]
        test_results.append({"test_id": test.id, "visibility": test.visibility, "passed": outcome.passed})
        if not outcome.passed:
            failures.append({
                "test_name": test.id,
                "visibility": test.visibility,
                "expected": outcome.expected,
                "actual": outcome.actual,
                "exception": outcome.exception,
                "traceback_excerpt": outcome.trace,
            })
    hidden = [r for r in test_results if r["visibility"] == "hidden"]
    public = [r for r in test_results if r["visibility"] == "public"]

    smoke = report.outcomes.get(SMOKE_ID)
    info = report.import_info
    contract = {
        "compiles": report.compiles,
        "imports_cleanly": info.imports_cleanly,
        "entrypoint_defined": info.entrypoint_defined,
        "entrypoint_accepts_expected_arguments": info.arity_ok,
        "smoke_call_returns_expected_type": bool(smoke and smoke.passed),
    }
    correctness = 100.0 * sum(contract.values()) / len(CORRECTNESS_CHECK_IDS)
    elapsed = time.perf_counter() - started

    public_ids = {t.id for t in suite.public_tests}
    hidden_ids = {t.id for t in suite.hidden_tests}
    breakdown = {
        "correctness": {
            "definition": "percentage of interface-contract checks passed (not the test pass rate)",
            "checks": [{"id": cid, "passed": contract[cid]} for cid in CORRECTNESS_CHECK_IDS],
            "import_error": info.error,
        },
        "code_quality": {
            "definition": "mean of five structural AST checks, scaled to 0-100",
            "checks": [{"id": c.id, "score": c.score, "detail": c.detail} for c in quality.checks],
            "max_cyclomatic_complexity": quality.max_complexity,
        },
        "execution": {
            "interpreter_runs": report.processes_started,
            "timed_out_public_tests": [i for i in report.timed_out_items if i in public_ids],
            "timed_out_hidden_tests_count": sum(1 for i in report.timed_out_items if i in hidden_ids),
            "import_timed_out": "__import__" in report.timed_out_items,
        },
    }
    return EvaluationOutcome(
        suite_id=suite.id,
        suite_hash=suite.suite_hash,
        public_suite_hash=suite.public_suite_hash,
        hidden_suite_hash=suite.hidden_suite_hash,
        evaluator_version=EVALUATOR_VERSION,
        tests_passed=sum(1 for r in hidden if r["passed"]),
        tests_total=len(hidden),
        public_tests_passed=sum(1 for r in public if r["passed"]),
        public_tests_total=len(public),
        test_results=test_results,
        failure_details=failures,
        correctness_score=correctness,
        code_quality_score=quality.score,
        breakdown=breakdown,
        elapsed_seconds=elapsed,
        timed_out_items=report.timed_out_items,
    )

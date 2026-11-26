"""The acceptance policy (scoring rule) in force: weights, delta, tolerance, and how they were chosen.

Scoring rule version 2 (PRD Section 5):

  S = 0.5 * P + 0.3 * C + 0.2 * Q          (app.scoring; unchanged)
    P = HIDDEN-suite pass rate (0-100). Public tests are recorded and must not regress, but they do
        not enter S, so a revision cannot raise its score by fitting the tests it was shown.
    C = interface-contract correctness (5 checks, 20 points each; independent of P's pass/fail data)
    Q = structural quality (5 AST checks, 20 points each; complexity graded in steps of 1/limit)

  Preconditions (failure => invalid_comparison, nothing is decided):
    same execution; both evaluations complete; both match the execution's commitment
    (suite hash, evaluator configuration hash, scoring-rule version); and each evaluation's
    code_sha256 equals the hash of the code currently stored for its version
    (same_code_hash_as_evaluated).
  Predicate (failure => rejected_attempt, with every failed term recorded):
    no_test_regression   every test (public or hidden) passing in the best version still passes
    no_dimension_regression   P, C and Q are each non-decreasing (ties allowed, any drop rejects)
    aggregate_delta      S_new >= S_old + DELTA

Why DELTA = 1.0 aggregate point
  * It must exceed floating-point noise: SCORE_TOLERANCE is 1e-9, so 1.0 is far above it.
  * It must not exceed the smallest *meaningful* improvement:
      one hidden test   = 50 / n_hidden points (5.0 for the 10 hidden merge-intervals tests)
      one contract check = 0.3 * 20 = 6.0 points
      one quality check  = 0.2 * 20 = 4.0 points
    `register()` refuses any suite whose single-hidden-test increment is not strictly above DELTA
    (so at most 49 hidden tests at DELTA = 1.0).
  * Deliberately excluded: reducing cyclomatic complexity by one step is worth 0.2 * 20 / limit
    (0.4 points at limit 10). A revision whose ONLY gain is that is rejected as "delta not met".
  * It is an integer, which the existing Circom circuit requires (integer scores 0-100, delta 1-50).
    With S_new >= S_old + 1, floor(S_new) >= floor(S_old) + 1 always holds, so the integer encoding
    `zk_integer_score` below can never turn an accepted improvement into an unprovable one.
"""
import hashlib
import json
import math

from app.scoring import SCORE_TOLERANCE, WEIGHT_CODE_QUALITY, WEIGHT_CORRECTNESS, WEIGHT_TEST_PASS_RATE

SCORING_RULE_VERSION = "2"
DELTA = 1.0

TERM_TEST_REGRESSION = "no_test_regression"
TERM_PASS_RATE = "no_dimension_regression:hidden_pass_rate"
TERM_CORRECTNESS = "no_dimension_regression:correctness"
TERM_QUALITY = "no_dimension_regression:code_quality"
TERM_DELTA = "aggregate_delta"
PREDICATE_TERMS = (TERM_TEST_REGRESSION, TERM_PASS_RATE, TERM_CORRECTNESS, TERM_QUALITY, TERM_DELTA)

PRE_SAME_EXECUTION = "same_execution"
PRE_CANDIDATE_COMPLETE = "candidate_evaluation_complete"
PRE_PREVIOUS_COMPLETE = "previous_best_evaluation_complete"
PRE_SAME_SUITE = "same_suite"
PRE_SAME_CONFIG = "same_evaluator_configuration"
PRE_SAME_RULE = "same_scoring_rule"
PRE_SAME_CODE = "same_code_hash_as_evaluated"
PRECONDITIONS = (PRE_SAME_EXECUTION, PRE_CANDIDATE_COMPLETE, PRE_PREVIOUS_COMPLETE, PRE_SAME_SUITE,
                 PRE_SAME_CONFIG, PRE_SAME_RULE, PRE_SAME_CODE)


def scoring_rule() -> dict:
    return {
        "version": SCORING_RULE_VERSION,
        "formula": "S = 0.5*P + 0.3*C + 0.2*Q",
        "weights": {"hidden_pass_rate": WEIGHT_TEST_PASS_RATE, "correctness": WEIGHT_CORRECTNESS,
                    "code_quality": WEIGHT_CODE_QUALITY},
        "pass_rate_source": "hidden tests only",
        "delta": DELTA,
        "tolerance": SCORE_TOLERANCE,
        "preconditions": list(PRECONDITIONS),
        "predicate": list(PREDICATE_TERMS),
    }


def scoring_rule_hash() -> str:
    return hashlib.sha256(json.dumps(scoring_rule(), sort_keys=True).encode()).hexdigest()


def hidden_test_increment(n_hidden: int) -> float:
    """Aggregate points gained by passing one more hidden test."""
    return WEIGHT_TEST_PASS_RATE * 100.0 / n_hidden


def check_suite_against_policy(suite) -> None:
    """A suite is usable only if one more passing hidden test is always an improvement above DELTA."""
    hidden = len(suite.hidden_tests)
    if hidden < 1:
        raise ValueError(f"suite {suite.id!r} has no hidden tests; the score is computed from hidden tests")
    if not suite.public_tests:
        raise ValueError(f"suite {suite.id!r} has no public tests")
    if hidden_test_increment(hidden) <= DELTA + SCORE_TOLERANCE:
        raise ValueError(
            f"suite {suite.id!r}: one hidden test is worth {hidden_test_increment(hidden):.4f} points, "
            f"not more than DELTA={DELTA}; use fewer hidden tests or change the score representation"
        )


def meets_delta(previous: float, candidate: float) -> bool:
    return candidate >= previous + DELTA - SCORE_TOLERANCE


def zk_integer_score(score: float) -> int:
    """Integer encoding for the existing circuit (inputs 0-100). The tolerance absorbs float noise
    such as 56.99999999999. Not used by any stage yet; the ZK integration is a later milestone."""
    return int(math.floor(score + SCORE_TOLERANCE))

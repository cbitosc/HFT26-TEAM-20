"""Approved aggregation of deterministic evaluation components.

This is only the weighted sum of component scores that an evaluator will supply. It
performs no evaluation. Operational measurements (time, tokens, cost) are deliberately
not inputs here, and Critic confidence never enters a score.

All components and the result are on a 0-100 scale.

Numeric semantics (shared with the database CHECK constraints, see models/evaluation.py):
  * No rounding anywhere. Full-precision IEEE doubles are computed and stored (REAL columns).
  * Operations are evaluated left to right in the order written below.
  * The database accepts a stored value within SCORE_TOLERANCE of the recomputed value. Exact
    bit equality between Python and SQLite is not guaranteed across builds (compilers may fuse
    multiply-add), so exact equality would risk rejecting valid rows. 1e-9 is about four orders
    of magnitude above the largest possible double rounding error for values in 0-100, and far
    below any score difference an evaluator can produce.
"""

WEIGHT_TEST_PASS_RATE = 0.50
WEIGHT_CORRECTNESS = 0.30
WEIGHT_CODE_QUALITY = 0.20

SCORE_TOLERANCE = 1e-9


def compute_test_pass_rate(tests_passed: int, tests_total: int) -> float:
    """Percentage (0-100) of tests passed."""
    return tests_passed / tests_total * 100.0


def compute_overall_score(test_pass_rate: float, correctness: float, code_quality: float) -> float:
    return (
        WEIGHT_TEST_PASS_RATE * test_pass_rate
        + WEIGHT_CORRECTNESS * correctness
        + WEIGHT_CODE_QUALITY * code_quality
    )


def overall_score_sql(pass_rate: str, correctness: str, code_quality: str) -> str:
    """The same weighted sum as `compute_overall_score`, as a SQL expression over column names."""
    return (
        f"{WEIGHT_TEST_PASS_RATE!r} * {pass_rate} + {WEIGHT_CORRECTNESS!r} * {correctness}"
        f" + {WEIGHT_CODE_QUALITY!r} * {code_quality}"
    )


def test_pass_rate_sql(tests_passed: str, tests_total: str) -> str:
    """The same expression as `compute_test_pass_rate`, in the same operation order.
    `* 1.0` forces real division, because SQLite divides integers as integers."""
    return f"{tests_passed} * 1.0 / {tests_total} * 100.0"


# pytest must not collect the helper above because of its name
test_pass_rate_sql.__test__ = False

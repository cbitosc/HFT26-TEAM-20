"""Shared test builders. Rows built here satisfy every database constraint, including the
score-consistency checks, so a test that expects a rejection changes exactly one thing."""
from app.models import Evaluation
from app.scoring import compute_overall_score, compute_test_pass_rate


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
        tests_passed=passed,
        tests_total=total,
        test_pass_rate=rate,
        correctness_score=correctness,
        code_quality_score=quality,
        overall_score=compute_overall_score(rate, correctness, quality),
    )
    fields.update(overrides)
    return Evaluation(**fields)

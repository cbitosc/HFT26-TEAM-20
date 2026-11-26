"""Registry of trusted evaluation suites, keyed by suite id."""
from app.evaluation.suite import EvaluationSuite

SUITES: dict[str, EvaluationSuite] = {}


def register(suite: EvaluationSuite) -> None:
    from app.evaluation.policy import check_suite_against_policy

    suite.validate()
    check_suite_against_policy(suite)
    SUITES[suite.id] = suite


def get_suite(suite_id: str | None) -> EvaluationSuite | None:
    return SUITES.get(suite_id) if suite_id else None


def suite_ids() -> list[str]:
    return sorted(SUITES)


from app.evaluation.suites import merge_intervals  # noqa: E402  (registered below)

register(merge_intervals.SUITE)

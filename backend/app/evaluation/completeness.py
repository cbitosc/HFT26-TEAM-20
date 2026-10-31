"""What makes a stored evaluation usable by the acceptance gate."""
from app.evaluation.suite import VISIBILITIES


def is_complete(evaluation) -> bool:
    """Complete = full provenance present, and exactly one well-formed outcome per configured test
    (hidden and public), agreeing with the stored counts. Timeouts and errors are recorded as failures,
    so they still count as outcomes. Re-checked here even though the database enforces most of it,
    because the gate must not rely on a flag alone."""
    if not (evaluation.suite_id and evaluation.suite_hash and evaluation.evaluator_version
            and evaluation.evaluator_config_hash and evaluation.scoring_rule_version):
        return False
    results = evaluation.test_results or []
    public_total = evaluation.public_tests_total or 0
    if len(results) != evaluation.tests_total + public_total:
        return False
    ids = []
    counts = {"hidden": [0, 0], "public": [0, 0]}  # [total, passed]
    for entry in results:
        if (not isinstance(entry, dict) or not isinstance(entry.get("test_id"), str)
                or not isinstance(entry.get("passed"), bool) or entry.get("visibility") not in VISIBILITIES):
            return False
        ids.append(entry["test_id"])
        counts[entry["visibility"]][0] += 1
        counts[entry["visibility"]][1] += entry["passed"]
    if len(set(ids)) != len(ids):
        return False
    return (counts["hidden"] == [evaluation.tests_total, evaluation.tests_passed]
            and counts["public"] == [public_total, evaluation.public_tests_passed or 0])

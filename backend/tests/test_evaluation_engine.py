"""The deterministic evaluator: it runs real candidate code in real subprocesses (nothing is mocked),
scores it, and persists the result. Every score here comes from the engine, never from the test."""
import dataclasses
import os
import time
from pathlib import Path

import pytest

from app.config import Settings
from app.errors import (
    ConflictError,
    EvaluationExecutionDisabledError,
    EvaluationSuiteUnavailableError,
    NotFoundError,
)
from app.evaluation import execution as execution_module
from app.evaluation.engine import evaluate_source
from app.evaluation.execution import MAX_SOURCE_BYTES, RunLimits
from app.evaluation.static_quality import analyze, cyclomatic_complexity
from app.evaluation.suite import EVALUATOR_VERSION, QualitySpec
from app.evaluation.suites import SUITES, get_suite
from app.models import Evaluation
from app.scoring import compute_overall_score, compute_test_pass_rate
from app.services import evaluation_service as evs
from app.services import execution_service as exe
from app.services import version_service as ver

FIXTURES = Path(__file__).parent / "fixtures"
SUITE = get_suite("python-merge-intervals-v1")
FAST = RunLimits(per_run_timeout=5.0, total_timeout=30.0)


def source(name: str) -> str:
    return (FIXTURES / f"{name}.py").read_text(encoding="utf-8")


GOOD = source("reference_good")


def run(code: str, limits: RunLimits = FAST):
    return evaluate_source(code, SUITE, limits)


def failed_ids(outcome) -> set[str]:
    return {r["test_id"] for r in outcome.test_results if not r["passed"]}


# ---- scoring ---------------------------------------------------------------------------------
def test_a_correct_solution_passes_every_test():
    o = run(GOOD)
    assert (o.tests_passed, o.tests_total) == (10, 10) and not failed_ids(o)
    assert (o.public_tests_passed, o.public_tests_total) == (5, 5)
    assert o.correctness_score == 100.0 and o.evaluator_version == EVALUATOR_VERSION


def test_the_suite_is_split_into_public_and_hidden_tests():
    assert (len(SUITE.public_tests), len(SUITE.hidden_tests)) == (5, 10)
    assert SUITE.public_suite_hash != SUITE.hidden_suite_hash != SUITE.suite_hash
    o = run(GOOD)
    assert [r["visibility"] for r in o.test_results].count("hidden") == 10


def test_the_score_counts_hidden_tests_only():
    """gen_coder fails one public and one hidden test: only the hidden one lowers tests_passed."""
    o = run(source("gen_coder"))
    assert (o.tests_passed, o.tests_total) == (9, 10)
    assert (o.public_tests_passed, o.public_tests_total) == (4, 5)
    assert failed_ids(o) == {"unsorted_input", "typeerror_non_int_values"}
    assert [(f["test_name"], f["visibility"]) for f in o.failure_details] == [
        ("unsorted_input", "public"), ("typeerror_non_int_values", "hidden")]


def test_a_mostly_wrong_solution_scores_low_and_is_not_a_total_failure():
    o = run(source("flawed"))
    assert (o.tests_passed, o.public_tests_passed) == (2, 2) and len(failed_ids(o)) == 11
    assert o.correctness_score == 100.0  # the interface is fine; behaviour is not (documented limitation)


def test_the_breakdown_never_contains_hidden_test_ids():
    code = GOOD + "\n_orig = merge_intervals\ndef merge_intervals(x):\n    if x == [(4, 4)]:\n        while True:\n            pass\n    return _orig(x)\n"
    o = run(code, RunLimits(per_run_timeout=1.0, total_timeout=20.0))
    assert failed_ids(o) == {"single_point"}  # a hidden test
    assert o.breakdown["execution"]["timed_out_hidden_tests_count"] == 1
    hidden_ids = {t.id for t in SUITE.hidden_tests}
    assert not [i for i in hidden_ids if i in str(o.breakdown)]


def test_a_solution_that_always_fails_scores_zero_on_tests():
    o = run("def merge_intervals(x):\n    raise KeyError(x)\n")
    assert o.tests_passed == 0 and o.public_tests_passed == 0 and len(failed_ids(o)) == 15
    # the smoke call fails too, so correctness is not silently 100
    assert o.correctness_score == 80.0


def test_a_do_nothing_function_earns_only_the_vacuous_non_mutation_test():
    # Documented limitation: 'the input was not mutated' holds trivially for code that does nothing.
    o = run("def merge_intervals(x):\n    return None\n")
    assert o.tests_passed == 1 and "input_not_mutated" not in failed_ids(o)


def test_a_syntax_error_scores_zero_everywhere():
    o = run("def merge_intervals(x:\n")
    assert o.tests_passed == 0 and o.correctness_score == 0.0 and o.code_quality_score == 0.0
    assert o.breakdown["correctness"]["checks"][0] == {"id": "compiles", "passed": False}
    assert o.failure_details and all(f["actual"] == "source does not compile" for f in o.failure_details)


def test_an_exception_at_import_time_fails_everything_without_crashing_the_evaluator():
    o = run("raise RuntimeError('boom at import')\n")
    assert o.tests_passed == 0
    assert o.correctness_score == 20.0  # only "compiles" holds
    assert "RuntimeError" in (o.breakdown["correctness"]["import_error"] or "")


def test_a_missing_entry_point_fails_everything():
    o = run("x = 1\n")
    assert o.tests_passed == 0 and o.code_quality_score == 0.0
    assert o.correctness_score == 40.0  # compiles + imports cleanly


def test_a_runtime_exception_fails_only_that_test():
    code = GOOD + "\n_orig = merge_intervals\ndef merge_intervals(x):\n    if x == [(4, 4)]:\n        raise ZeroDivisionError('x')\n    return _orig(x)\n"
    o = run(code)
    assert failed_ids(o) == {"single_point"}
    detail = next(f for f in o.failure_details if f["test_name"] == "single_point")
    assert "ZeroDivisionError" in detail["exception"]


def test_a_hanging_test_times_out_and_the_rest_still_run():
    code = GOOD + "\n_orig = merge_intervals\ndef merge_intervals(x):\n    if x == []:\n        while True:\n            pass\n    return _orig(x)\n"
    started = time.monotonic()
    o = run(code, RunLimits(per_run_timeout=1.0, total_timeout=20.0))
    assert failed_ids(o) == {"empty"} and (o.tests_passed, o.public_tests_passed) == (10, 4)
    assert o.timed_out_items == ["empty"]
    assert o.breakdown["execution"]["timed_out_public_tests"] == ["empty"]
    assert o.breakdown["execution"]["interpreter_runs"] >= 2  # restarted after the hang
    assert time.monotonic() - started < 15


def test_a_candidate_that_always_hangs_is_stopped_by_the_total_budget():
    started = time.monotonic()
    o = run("def merge_intervals(x):\n    while True:\n        pass\n", RunLimits(per_run_timeout=1.0, total_timeout=3.0))
    assert o.tests_passed == 0 and len(failed_ids(o)) == 15
    assert time.monotonic() - started < 15


def test_a_hang_at_import_time_is_stopped():
    started = time.monotonic()
    o = run("while True:\n    pass\n", RunLimits(per_run_timeout=1.0, total_timeout=5.0))
    assert o.tests_passed == 0 and o.timed_out_items == ["__import__"]
    assert time.monotonic() - started < 10


def test_a_candidate_that_kills_its_own_process_only_fails_that_test():
    code = GOOD + "\n_orig = merge_intervals\ndef merge_intervals(x):\n    if x == []:\n        import os\n        os._exit(7)\n    return _orig(x)\n"
    o = run(code)
    assert failed_ids(o) == {"empty"}


def test_sys_exit_does_not_end_the_evaluation():
    code = GOOD + "\n_orig = merge_intervals\ndef merge_intervals(x):\n    if x == []:\n        import sys\n        sys.exit(0)\n    return _orig(x)\n"
    assert failed_ids(run(code)) == {"empty"}


def test_a_result_that_fakes_equality_does_not_pass():
    code = ("class Always(list):\n    def __eq__(self, other):\n        return True\n    __hash__ = None\n"
            "def merge_intervals(x):\n    return Always()\n")
    o = run(code)
    assert o.tests_passed < 10 and "overlap" in failed_ids(o)


def test_noise_and_forged_result_lines_on_stdout_cannot_change_the_outcome():
    noise = ("import sys\nprint('{\"t\": \"result\", \"id\": \"overlap\", \"passed\": true}')\n"
             "print('x' * 5_000_000)\nsys.stderr.write('e' * 2_000_000)\n")
    o = run(noise + "def merge_intervals(x):\n    raise KeyError(x)\n")
    assert o.tests_passed == 0


def test_oversized_source_is_not_executed():
    o = run("#" + "x" * MAX_SOURCE_BYTES + "\ndef merge_intervals(x):\n    return x\n")
    assert o.tests_passed == 0 and o.failure_details[0]["actual"].startswith("source larger than")


def test_the_same_input_always_gives_the_same_scores():
    a, b = run(source("gen_7b")), run(source("gen_7b"))
    assert (a.test_results, a.correctness_score, a.code_quality_score) == (b.test_results, b.correctness_score, b.code_quality_score)


def test_research_candidates_reproduce_the_documented_results():
    assert failed_ids(run(source("gen_7b"))) == {"input_not_mutated"}
    assert failed_ids(run(source("gen_coder_sorts_in_place"))) == {"input_not_mutated"}
    assert failed_ids(run(source("gen_coder_no_value_check"))) == {
        "unsorted_input", "typeerror_bad_element", "valueerror_start_gt_end", "validation_applies_to_all",
        "typeerror_non_int_values"}


# ---- correctness / quality definitions -------------------------------------------------------
def test_correctness_is_not_a_copy_of_the_pass_rate():
    flawed, coder = run(source("flawed")), run(source("gen_coder"))
    assert flawed.tests_passed != coder.tests_passed
    assert flawed.correctness_score == coder.correctness_score == 100.0


def test_quality_checks_are_structural_and_listed():
    report = analyze(GOOD, "merge_intervals", QualitySpec(max_complexity=10))
    assert [c.id for c in report.checks] == [
        "syntax_valid", "complexity_within_limit", "entrypoint_documented",
        "entrypoint_type_annotated", "no_hazardous_constructs",
    ]


@pytest.mark.parametrize("code,expected_zero", [
    ("def f(:\n", True),
    ("x = 1\n", True),  # parses but has no entry point: no partial credit
])
def test_quality_is_zero_without_a_parsable_entry_point(code, expected_zero):
    assert (analyze(code, "merge_intervals", QualitySpec()).score == 0.0) is expected_zero


def test_quality_penalises_hazards_missing_docs_and_missing_annotations():
    clean = analyze('def merge_intervals(x: list) -> list:\n    """Doc."""\n    return x\n', "merge_intervals", QualitySpec())
    assert clean.score == 100.0
    bare = analyze('def merge_intervals(x: list) -> list:\n    """Doc."""\n    try:\n        return x\n    except:\n        return []\n', "merge_intervals", QualitySpec())
    undocumented = analyze("def merge_intervals(x: list) -> list:\n    return x\n", "merge_intervals", QualitySpec())
    unannotated = analyze('def merge_intervals(x):\n    """Doc."""\n    return x\n', "merge_intervals", QualitySpec())
    mutable = analyze('def merge_intervals(x: list = []) -> list:\n    """Doc."""\n    return x\n', "merge_intervals", QualitySpec())
    wildcard = analyze('from os import *\ndef merge_intervals(x: list) -> list:\n    """Doc."""\n    return x\n', "merge_intervals", QualitySpec())
    evil = analyze('def merge_intervals(x: list) -> list:\n    """Doc."""\n    return eval("x")\n', "merge_intervals", QualitySpec())
    for report in (bare, undocumented, unannotated, mutable, wildcard, evil):
        assert report.score == 80.0


def test_complexity_is_graded_not_binary():
    def with_branches(n):
        body = "".join(f"    if x == {i}:\n        return {i}\n" for i in range(n))
        return f'def merge_intervals(x: int) -> int:\n    """Doc."""\n{body}    return -1\n'
    low = analyze(with_branches(3), "merge_intervals", QualitySpec(max_complexity=10)).score
    slightly = analyze(with_branches(10), "merge_intervals", QualitySpec(max_complexity=10)).score  # complexity 11
    very = analyze(with_branches(40), "merge_intervals", QualitySpec(max_complexity=10)).score
    assert low == 100.0 and very < slightly < low


def test_cyclomatic_complexity_counts_decision_points():
    import ast

    fn = ast.parse("def f(a, b):\n    if a and b:\n        return [x for x in a if x]\n    for i in b:\n        pass\n").body[0]
    assert cyclomatic_complexity(fn) == 1 + 1 + 1 + 2 + 1  # if, and, comprehension+if, for


# ---- suites ----------------------------------------------------------------------------------
def test_suite_is_hashed_and_registered():
    assert "python-merge-intervals-v1" in SUITES and len(SUITE.suite_hash) == 64
    changed = dataclasses.replace(SUITE, tests=SUITE.tests[:-1])  # drops a hidden test
    assert changed.suite_hash != SUITE.suite_hash and changed.hidden_suite_hash != SUITE.hidden_suite_hash
    assert changed.public_suite_hash == SUITE.public_suite_hash


def test_moving_a_test_between_public_and_hidden_changes_the_hashes():
    first = SUITE.tests[0]
    moved = dataclasses.replace(SUITE, tests=(dataclasses.replace(first, visibility="hidden"), *SUITE.tests[1:]))
    assert moved.suite_hash != SUITE.suite_hash and moved.public_suite_hash != SUITE.public_suite_hash


def test_registration_requires_public_and_hidden_tests():
    from app.evaluation.policy import check_suite_against_policy

    only_public = dataclasses.replace(SUITE, tests=SUITE.public_tests)
    only_hidden = dataclasses.replace(SUITE, tests=SUITE.hidden_tests)
    with pytest.raises(ValueError, match="no hidden tests"):
        check_suite_against_policy(only_public)
    with pytest.raises(ValueError, match="no public tests"):
        check_suite_against_policy(only_hidden)


def test_registration_refuses_a_suite_where_one_hidden_test_is_worth_less_than_delta():
    from app.evaluation.policy import DELTA, check_suite_against_policy, hidden_test_increment
    from app.evaluation.suite import Check, TestCase

    many = tuple(TestCase(f"h{i}", "x", (Check("returns", ([],), []),)) for i in range(50))
    big = dataclasses.replace(SUITE, tests=(*SUITE.public_tests, *many))
    assert hidden_test_increment(50) == DELTA
    with pytest.raises(ValueError, match="DELTA"):
        check_suite_against_policy(big)
    check_suite_against_policy(dataclasses.replace(big, tests=big.tests[:-1]))  # 49 hidden tests are fine


def test_evaluator_configuration_hash_covers_the_time_limits():
    from app.evaluation.provenance import evaluator_config_hash

    assert evaluator_config_hash(RunLimits()) == evaluator_config_hash(RunLimits())
    assert evaluator_config_hash(RunLimits()) != evaluator_config_hash(RunLimits(per_run_timeout=9.0))


# ---- the service: persistence, separation of operational data, refusal paths ------------------
@pytest.fixture
def settings_for_service(client):
    return client.app.state.settings


@pytest.fixture
def make_version(client, db, make_task):
    def _make(code, *, suite_id="python-merge-intervals-v1", max_revisions=2, parent=None, execution_id=None):
        if execution_id is None:
            task_id = make_task(**({"evaluation_suite_id": suite_id} if suite_id else {}))["id"]
            execution_id = exe.create_execution(db, task_id, max_revisions=max_revisions).id
        return ver.create_version(db, execution_id, code, parent_version_id=parent)

    return _make


def test_evaluation_values_are_persisted_exactly_as_measured(db, make_version, settings_for_service):
    v = make_version(source("gen_coder"))
    stored = evs.evaluate_version(db, v.id, settings_for_service)
    direct = run(source("gen_coder"))
    rate = compute_test_pass_rate(9, 10)
    assert (stored.tests_passed, stored.tests_total) == (9, 10)
    assert (stored.public_tests_passed, stored.public_tests_total) == (4, 5)
    assert stored.test_pass_rate == rate
    assert stored.correctness_score == direct.correctness_score
    assert stored.code_quality_score == direct.code_quality_score
    assert stored.overall_score == compute_overall_score(rate, direct.correctness_score, direct.code_quality_score)
    assert (stored.suite_id, stored.suite_hash, stored.evaluator_version) == (SUITE.id, SUITE.suite_hash, EVALUATOR_VERSION)
    assert stored.test_results == direct.test_results
    assert {f["test_name"] for f in stored.failure_details} == failed_ids(direct)
    assert "correctness" in stored.score_breakdown and "code_quality" in stored.score_breakdown


def test_every_evaluation_carries_a_provenance_record_matching_the_commitment(db, make_version, settings_for_service):
    from app.evaluation import policy

    v = make_version(GOOD)
    stored = evs.evaluate_version(db, v.id, settings_for_service)
    execution = exe.get_execution(db, v.execution_id)
    p = stored.provenance
    assert stored.evaluator_config_hash == execution.evaluator_config_hash == p["evaluator_config_hash"]
    assert stored.scoring_rule_version == execution.scoring_rule_version == policy.SCORING_RULE_VERSION
    assert p["hidden_suite_hash"] == execution.hidden_suite_hash == SUITE.hidden_suite_hash
    assert p["public_suite_hash"] == execution.public_suite_hash
    assert p["delta"] == execution.delta == policy.DELTA
    assert p["execution_id"] == execution.id and p["version_id"] == v.id and p["evaluated_at"]
    assert p["environment"]["runner_image_digest"] is None  # no container: not invented
    assert "NOT a security sandbox" in p["environment"]["isolation"]
    assert p["matches_commitment"] == {"suite": True, "evaluator_config": True, "scoring_rule": True}


def test_a_changed_evaluator_configuration_is_recorded_as_not_matching(db, make_version, tmp_path):
    v = make_version(GOOD)
    other = Settings(_env_file=None, app_env="test", evaluation_timeout_seconds=7.0,
                     database_url=f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    stored = evs.evaluate_version(db, v.id, other)
    assert stored.provenance["matches_commitment"]["evaluator_config"] is False
    assert stored.evaluator_config_hash != exe.get_execution(db, v.execution_id).evaluator_config_hash


def test_operational_metrics_are_stored_apart_and_never_change_the_score(db, make_version, settings_for_service):
    v = make_version(GOOD)
    first = evs.evaluate_version(db, v.id, settings_for_service)
    second = evs.evaluate_version(db, v.id, settings_for_service)
    assert first.operational.execution_time_seconds > 0
    assert first.operational.prompt_tokens is None and first.operational.api_cost_usd is None  # nothing invented
    assert (first.overall_score, first.test_results) == (second.overall_score, second.test_results)
    assert "execution_time" not in str(first.score_breakdown) and "elapsed" not in str(first.score_breakdown)
    assert first.id != second.id and len(ver.list_evaluations(db, v.id)) == 2  # history is kept


def test_temporary_directories_are_removed_in_every_outcome(monkeypatch):
    created = []
    real = execution_module.tempfile.mkdtemp

    def recording(*args, **kwargs):
        path = real(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr(execution_module.tempfile, "mkdtemp", recording)
    run(GOOD)
    run("def merge_intervals(x:\n")  # never reaches the interpreter
    run("while True:\n    pass\n", RunLimits(per_run_timeout=1.0, total_timeout=3.0))
    run(GOOD + "\nimport os\n_o = merge_intervals\ndef merge_intervals(x):\n    os._exit(1)\n")
    assert len(created) == 3  # the syntax error never needed a directory
    assert not [p for p in created if os.path.exists(p)]


def test_a_run_cannot_start_without_a_suite(db, make_task):
    """PRD: Start Run needs public and hidden tests; if the commitment cannot be recorded, no run starts."""
    from app.models import Execution

    task_id = make_task(evaluation_suite_id=None)["id"]
    with pytest.raises(EvaluationSuiteUnavailableError):
        exe.create_execution(db, task_id)
    assert db.query(Execution).filter(Execution.task_id == task_id).count() == 0


def test_a_suite_changed_after_the_commitment_is_refused(db, make_version, settings_for_service, monkeypatch):
    v = make_version(GOOD)
    monkeypatch.setitem(SUITES, SUITE.id, dataclasses.replace(SUITE, tests=SUITE.tests[:-1]))
    with pytest.raises(EvaluationSuiteUnavailableError, match="committed"):
        evs.evaluate_version(db, v.id, settings_for_service)
    assert ver.list_evaluations(db, v.id) == []


def test_a_suite_that_is_no_longer_registered_is_refused(db, make_version, settings_for_service, monkeypatch):
    v = make_version(GOOD)
    monkeypatch.delitem(SUITES, "python-merge-intervals-v1")
    with pytest.raises(EvaluationSuiteUnavailableError):
        evs.evaluate_version(db, v.id, settings_for_service)


def test_a_suite_with_zero_tests_can_never_produce_a_score(db, make_version, settings_for_service):
    v = make_version(GOOD)
    empty = dataclasses.replace(SUITE, tests=())
    with pytest.raises(EvaluationSuiteUnavailableError, match="no hidden tests"):
        evs.evaluate_version(db, v.id, settings_for_service, suite=empty)
    with pytest.raises(ValueError):
        evaluate_source(GOOD, empty, FAST)
    assert ver.list_evaluations(db, v.id) == []


def test_the_database_also_refuses_zero_total_tests(db, make_version):
    from sqlalchemy.exc import IntegrityError

    from tests.helpers import consistent_evaluation

    v = make_version(GOOD)
    db.add(consistent_evaluation(v.id, 0, 0, tests_total=0, test_pass_rate=100.0, overall_score=100.0))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_unknown_version_and_finished_executions(db, make_version, settings_for_service):
    with pytest.raises(NotFoundError):
        evs.evaluate_version(db, "missing", settings_for_service)
    v = make_version(GOOD)
    exe.cancel_execution(db, v.execution_id)
    with pytest.raises(ConflictError):
        evs.evaluate_version(db, v.id, settings_for_service)


def test_production_refuses_to_run_candidate_code_unless_opted_in(db, make_version, tmp_path):
    v = make_version(GOOD)
    base = dict(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    with pytest.raises(EvaluationExecutionDisabledError):
        evs.evaluate_version(db, v.id, Settings(app_env="production", **base))
    assert ver.list_evaluations(db, v.id) == []
    assert Settings(app_env="production", allow_unsandboxed_evaluation=True, **base).evaluation_execution_allowed
    assert not Settings(app_env="test", allow_unsandboxed_evaluation=False, **base).evaluation_execution_allowed
    assert Settings(app_env="development", **base).evaluation_execution_allowed


def test_persisted_evaluations_are_complete_and_inconsistent_rows_are_rejected_by_the_database(db, make_version, settings_for_service):
    from sqlalchemy.exc import IntegrityError

    v = make_version(GOOD)
    ev = evs.evaluate_version(db, v.id, settings_for_service)
    ev.test_results = ev.test_results[:-1]  # counts no longer agree with the outcomes
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert isinstance(db.get(Evaluation, ev.id).test_results, list)

"""The database itself enforces that stored evaluation scores match the approved formula.

Everything here talks to SQLite through a raw `sqlite3` connection, bypassing SQLAlchemy, the
ORM and the service layer, so a rejection can only come from the database's own CHECK constraints.
"""
import random
import re
import sqlite3
import uuid

import pytest

from app import scoring
from app.models import Evaluation
from app.schemas.evaluation import EvaluationInput, OperationalMetricsInput
from app.scoring import compute_overall_score, compute_test_pass_rate
from app.services import version_service as ver
from sqlalchemy import select

INSERT = (
    "INSERT INTO evaluations (id, version_id, tests_passed, tests_total, test_pass_rate, "
    "correctness_score, code_quality_score, overall_score, failure_details, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', '2026-10-30 12:00:00')"
)


@pytest.fixture
def version_id(db, make_execution):
    execution_id = make_execution()["id"]
    return ver.create_version(db, execution_id, "def f():\n    pass\n").id


@pytest.fixture
def raw(settings, version_id):
    """A raw sqlite3 connection with foreign keys on, as any other SQLite client could open."""
    path = settings.database_url.removeprefix("sqlite:///")
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    yield con
    con.close()


def row(version_id, passed=7, total=10, correctness=80.0, quality=90.0, *, rate=None, overall=None):
    """Values for INSERT. rate/overall default to the correct derived values."""
    rate = compute_test_pass_rate(passed, total) if rate is None else rate
    overall = compute_overall_score(rate, correctness, quality) if overall is None else overall
    return (str(uuid.uuid4()), version_id, passed, total, rate, correctness, quality, overall)


def accepted(con, values):
    con.execute(INSERT, values)
    con.commit()
    return True


def rejected_by(con, values, constraint):
    with pytest.raises(sqlite3.IntegrityError) as exc:
        con.execute(INSERT, values)
    con.rollback()
    assert constraint in str(exc.value), str(exc.value)


def count(con):
    return con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]


# ---- the constraints exist and use the approved formula --------------------------------------
def test_constraints_are_present_in_the_live_schema(raw):
    ddl = raw.execute("SELECT sql FROM sqlite_master WHERE name='evaluations'").fetchone()[0]
    assert "ck_evaluations_overall_consistent" in ddl and "ck_evaluations_pass_rate_consistent" in ddl
    overall = re.search(r"ck_evaluations_overall_consistent CHECK \((.*)\)", ddl).group(1)
    assert "0.5 * test_pass_rate" in overall
    assert "0.3 * correctness_score" in overall
    assert "0.2 * code_quality_score" in overall
    assert "1e-09" in overall and "COALESCE" in overall


def test_constraint_weights_come_from_the_application_constants():
    sql = scoring.overall_score_sql("a", "b", "c")
    assert sql == f"{scoring.WEIGHT_TEST_PASS_RATE!r} * a + {scoring.WEIGHT_CORRECTNESS!r} * b + {scoring.WEIGHT_CODE_QUALITY!r} * c"
    assert (scoring.WEIGHT_TEST_PASS_RATE, scoring.WEIGHT_CORRECTNESS, scoring.WEIGHT_CODE_QUALITY) == (0.5, 0.3, 0.2)
    assert pytest.approx(1.0) == scoring.WEIGHT_TEST_PASS_RATE + scoring.WEIGHT_CORRECTNESS + scoring.WEIGHT_CODE_QUALITY


# ---- valid records stay valid ----------------------------------------------------------------
@pytest.mark.parametrize(
    "passed,total,correctness,quality",
    [
        (0, 1, 0.0, 0.0),            # lowest possible: overall 0
        (1, 1, 100.0, 100.0),        # highest possible: overall 100
        (0, 10, 100.0, 100.0),
        (10, 10, 0.0, 0.0),
        (7, 10, 80.0, 90.0),         # a typical case
        (1, 3, 33.3, 66.7),          # 33.333... pass rate: repeating decimal
        (2, 3, 10.1, 20.2),          # 66.666...
        (1, 7, 14.285714285714286, 85.71428571428571),
        (999, 1000, 99.99, 0.01),
        (1, 1_000_000, 0.1, 99.9),   # very large denominator
        (333_333, 1_000_000, 33.3333, 66.6667),
    ],
)
def test_valid_records_including_boundaries_and_repeating_decimals_are_accepted(raw, version_id, passed, total, correctness, quality):
    assert accepted(raw, row(version_id, passed, total, correctness, quality))
    assert count(raw) == 1


def test_database_and_python_agree_on_many_random_valid_rows(raw, version_id):
    """No false rejections: 2,000 random valid combinations, computed by the application's own functions."""
    rng = random.Random(20261030)
    values = []
    for _ in range(2000):
        total = rng.randint(1, 5000)
        passed = rng.randint(0, total)
        correctness = round(rng.uniform(0, 100), rng.randint(0, 12))
        quality = round(rng.uniform(0, 100), rng.randint(0, 12))
        values.append(row(version_id, passed, total, correctness, quality))
    raw.executemany(INSERT, values)  # one statement per row; any inconsistency would raise
    raw.commit()
    assert count(raw) == 2000


def test_the_service_layer_output_is_always_accepted_by_the_database(db, version_id):
    rng = random.Random(7)
    for _ in range(25):
        total = rng.randint(1, 200)
        data = EvaluationInput(tests_passed=rng.randint(0, total), tests_total=total,
                               correctness_score=rng.uniform(0, 100), code_quality_score=rng.uniform(0, 100))
        ver.record_evaluation(db, version_id, data)
    assert len(db.scalars(select(Evaluation)).all()) == 25


# ---- inconsistent aggregates are rejected by SQLite itself -----------------------------------
def test_baseline_is_accepted_and_one_changed_value_is_rejected(raw, version_id):
    good = row(version_id)  # 7/10, 80, 90 -> overall 77
    assert good[7] == pytest.approx(77.0)
    assert accepted(raw, good)
    bad = list(row(version_id))
    bad[7] = 77.5  # the only difference from `good`
    rejected_by(raw, tuple(bad), "ck_evaluations_overall_consistent")
    assert count(raw) == 1  # the bad row was not stored


@pytest.mark.parametrize("overall", [0.0, 50.0, 76.999, 77.001, 78.0, 100.0, 76.99999])
def test_wrong_overall_scores_are_rejected(raw, version_id, overall):
    rejected_by(raw, row(version_id, overall=overall), "ck_evaluations_overall_consistent")
    assert count(raw) == 0


def test_a_perfect_overall_cannot_be_claimed_for_poor_components(raw, version_id):
    rejected_by(raw, row(version_id, 0, 10, 0.0, 0.0, overall=100.0), "ck_evaluations_overall_consistent")


def test_a_forged_pass_rate_cannot_carry_a_forged_overall(raw, version_id):
    """Overall is internally consistent with a pass rate of 100, but 3 of 10 tests passed."""
    forged_rate = 100.0
    values = row(version_id, 3, 10, 80.0, 90.0, rate=forged_rate)  # overall derived from the forged rate
    rejected_by(raw, values, "ck_evaluations_pass_rate_consistent")


@pytest.mark.parametrize("field,index", [("correctness", 5), ("quality", 6)])
def test_components_cannot_be_changed_to_disagree_with_the_overall(raw, version_id, field, index):
    values = list(row(version_id))
    values[index] = values[index] - 5  # overall left as originally computed
    rejected_by(raw, tuple(values), "ck_evaluations_overall_consistent")


# ---- UPDATE paths ----------------------------------------------------------------------------
def test_updating_the_overall_score_to_a_wrong_value_is_rejected(raw, version_id):
    values = row(version_id)
    accepted(raw, values)
    with pytest.raises(sqlite3.IntegrityError, match="ck_evaluations_overall_consistent"):
        raw.execute("UPDATE evaluations SET overall_score = 99.0 WHERE id = ?", (values[0],))
    raw.rollback()
    assert raw.execute("SELECT overall_score FROM evaluations").fetchone()[0] == pytest.approx(77.0)


def test_updating_a_component_without_the_overall_is_rejected(raw, version_id):
    values = row(version_id)
    accepted(raw, values)
    with pytest.raises(sqlite3.IntegrityError, match="ck_evaluations_overall_consistent"):
        raw.execute("UPDATE evaluations SET correctness_score = 0 WHERE id = ?", (values[0],))
    raw.rollback()


def test_updating_tests_passed_alone_is_rejected(raw, version_id):
    values = row(version_id)
    accepted(raw, values)
    with pytest.raises(sqlite3.IntegrityError, match="ck_evaluations_pass_rate_consistent"):
        raw.execute("UPDATE evaluations SET tests_passed = 10 WHERE id = ?", (values[0],))
    raw.rollback()


def test_a_consistent_update_of_all_affected_columns_is_accepted(raw, version_id):
    values = row(version_id)
    accepted(raw, values)
    new = row(version_id, 10, 10, 80.0, 90.0)
    raw.execute(
        "UPDATE evaluations SET tests_passed=?, test_pass_rate=?, overall_score=? WHERE id=?",
        (new[2], new[4], new[7], values[0]),
    )
    raw.commit()
    assert raw.execute("SELECT overall_score FROM evaluations").fetchone()[0] == pytest.approx(0.5 * 100 + 0.3 * 80 + 0.2 * 90)


# ---- tolerance edge and NULL handling --------------------------------------------------------
def test_tolerance_boundary_is_tiny_and_documented(raw, version_id):
    assert scoring.SCORE_TOLERANCE == 1e-9
    base = compute_overall_score(70.0, 80.0, 90.0)
    assert accepted(raw, row(version_id, overall=base + 5e-10))      # float noise level: accepted
    rejected_by(raw, row(version_id, overall=base + 5e-9), "ck_evaluations_overall_consistent")  # 5x the tolerance
    rejected_by(raw, row(version_id, overall=base - 5e-9), "ck_evaluations_overall_consistent")


def test_the_smallest_meaningful_score_difference_is_far_above_the_tolerance():
    """With at most 10^6 tests, adjacent pass rates differ by 100/10^6 = 1e-4 -> overall by 5e-5."""
    smallest = 0.5 * (compute_test_pass_rate(1, 1_000_000) - compute_test_pass_rate(0, 1_000_000))
    assert smallest / scoring.SCORE_TOLERANCE > 10_000


def test_zero_tests_total_is_rejected_not_waved_through_as_null(raw, version_id):
    """Division by zero yields NULL in SQLite and a bare NULL would pass a CHECK. COALESCE closes that."""
    values = (str(uuid.uuid4()), version_id, 0, 0, 0.0, 50.0, 50.0, 25.0)
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute(INSERT, values)
    raw.rollback()
    # and the consistency constraint on its own treats the NULL as a failure
    got = raw.execute("SELECT COALESCE(ABS(0.0 - (0 * 1.0 / 0 * 100.0)) <= 1e-09, 0)").fetchone()[0]
    assert got == 0


# ---- existing constraints are not weakened ---------------------------------------------------
@pytest.mark.parametrize(
    "mutate,constraint",
    [
        (lambda v: v[:5] + (-0.5,) + v[6:], "ck_evaluations_correctness"),
        (lambda v: v[:6] + (100.5,) + v[7:], "ck_evaluations_code_quality"),
        (lambda v: v[:7] + (100.1,), "ck_evaluations_overall"),
        (lambda v: v[:2] + (11,) + v[3:], "ck_evaluations_tests_passed"),
    ],
)
def test_range_constraints_still_reject_out_of_range_values(raw, version_id, mutate, constraint):
    # whichever CHECK SQLite evaluates first may be a range rule or a consistency rule; both must refuse the row
    values = mutate(row(version_id))
    with pytest.raises(sqlite3.IntegrityError) as exc:
        raw.execute(INSERT, values)
    raw.rollback()
    assert "CHECK constraint failed" in str(exc.value)
    assert count(raw) == 0


# ---- operational metrics stay out of the score -----------------------------------------------
def test_operational_metrics_are_stored_apart_and_do_not_change_the_score(db, version_id):
    base = ver.record_evaluation(db, version_id, EvaluationInput(tests_passed=7, tests_total=10,
                                                                 correctness_score=80, code_quality_score=90))
    heavy = ver.record_evaluation(
        db, version_id,
        EvaluationInput(tests_passed=7, tests_total=10, correctness_score=80, code_quality_score=90,
                        operational=OperationalMetricsInput(execution_time_seconds=9999, total_tokens=10**7,
                                                            api_cost_usd=500, api_cost_source="estimated")),
    )
    assert base.overall_score == heavy.overall_score
    evaluation_columns = {c.name for c in Evaluation.__table__.columns}
    assert not evaluation_columns & {"execution_time_seconds", "prompt_tokens", "completion_tokens",
                                     "total_tokens", "api_cost_usd", "api_cost_source"}

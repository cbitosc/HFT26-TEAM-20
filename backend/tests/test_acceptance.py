"""The acceptance policy (PRD Section 5), typed evidence, the lifecycle guards built on them, and the API.

Gate arithmetic is tested with evaluations stored through the real service (`complete_input`, which
carries the same provenance the execution committed to). The end-to-end cases run the real engine on
real candidate sources. Nothing here lets a caller pick a score.
"""
import random
import threading
from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.errors import (
    BaselineRequiredError,
    ConflictError,
    EvaluationNotComparableError,
    EvaluationRequiredError,
    InvalidTransitionError,
)
from app.evaluation import policy
from app.evaluation.gate import EvalSnapshot, compare
from app.evaluation.suites import get_suite
from app.lifecycle import ExecutionStatus as S
from app.models import Evaluation, EvidenceRecord, Execution, InvalidComparison, Version
from app.schemas.evaluation import EvaluationInput
from app.services import acceptance_service as acc
from app.services import evaluation_service as evs
from app.services import execution_service as exe
from app.services import version_service as ver
from tests.helpers import OTHER_HASH, SUITE_ID, advance, complete_input, grant_improvement

FIXTURES = Path(__file__).parent / "fixtures"
HIDDEN_IDS = [t.id for t in get_suite(SUITE_ID).hidden_tests]
TO_E2 = [S.GENERATING_V1, S.EVALUATING_V1, S.CRITIQUING, S.GENERATING_V2, S.EVALUATING_V2]
TO_E3 = TO_E2 + [S.CRITIQUING_V2, S.GENERATING_V3, S.EVALUATING_V3]


def source(name):
    return (FIXTURES / f"{name}.py").read_text(encoding="utf-8")


@pytest.fixture
def eid(db, make_task):
    return exe.create_execution(db, make_task()["id"], max_revisions=2).id


def code(n):  # distinct, valid-looking sources for gate-arithmetic tests
    return f"def merge_intervals(x):\n    return list(x)  # {n}\n"


def version_with(db, eid, n, **kw):
    """A version whose evaluation is stored through the real service (not via any API)."""
    v = ver.create_version(db, eid, code(n), parent_version_id=kw.pop("parent", None))
    if kw.pop("evaluate", True):
        ver.record_evaluation(db, v.id, complete_input(**kw))
    return v


@pytest.fixture
def baseline(db, eid):
    v1 = version_with(db, eid, 1, passed=5)
    assert acc.decide_acceptance(db, v1.id).baseline
    return v1


def reload(db, model, pk):
    db.expire_all()
    return db.get(model, pk)


def terms(decision):
    return [t.term for t in decision.failed_terms]


# ---- the pure gate ---------------------------------------------------------------------------
def snap(passed=("a", "b"), hidden=("a", "b", "c"), rate=66.0, correct=80.0, quality=80.0, overall=70.0, **kw):
    base = dict(version_id="v", execution_id="e", label="V1", evaluation_id="ev", suite_hash="h", evaluator_version="1",
                evaluator_config_hash="c", scoring_rule_version="2", code_sha256="h1", stored_code_sha256="h1",
                current_code_sha256="h1", passed_tests=frozenset(passed),
                hidden_ids=frozenset(hidden), tests_passed=len(passed), tests_total=len(hidden),
                public_tests_passed=0, public_tests_total=0, test_pass_rate=rate, correctness_score=correct,
                code_quality_score=quality, overall_score=overall)
    base.update(kw)
    return EvalSnapshot(**base)


def test_gate_accepts_a_gain_of_at_least_delta_with_nothing_regressing():
    assert compare(snap(), snap(passed=("a", "b", "c"), overall=71.0, label="V2"), delta=1.0).accepted


def test_gate_applies_delta_at_the_boundary():
    assert compare(snap(), snap(overall=71.0), delta=1.0).accepted  # exactly delta: S_new >= S_old + delta
    assert compare(snap(), snap(overall=71.0 - 1e-12), delta=1.0).accepted  # float noise is not a shortfall
    assert not compare(snap(), snap(overall=70.6), delta=1.0).accepted  # e.g. a complexity-only gain of 0.4
    assert not compare(snap(), snap(overall=70.0), delta=1.0).accepted  # equal
    assert not compare(snap(), snap(overall=69.0), delta=1.0).accepted  # lower


def test_gate_reports_every_failed_term_not_only_the_first():
    result = compare(snap(), snap(passed=("a",), rate=33.0, correct=70.0, quality=70.0, overall=50.0))
    assert [t.term for t in result.failed_terms] == [
        policy.TERM_TEST_REGRESSION, policy.TERM_PASS_RATE, policy.TERM_CORRECTNESS, policy.TERM_QUALITY,
        policy.TERM_DELTA]


def test_gate_messages_count_hidden_tests_and_name_public_ones():
    previous = snap(passed=("pub", "secret"), hidden=("secret",))
    result = compare(previous, snap(passed=(), hidden=("secret",), overall=90.0))
    message = result.failed_terms[0].message
    assert "pub" in message and "1 hidden test(s)" in message and "secret" not in message


def test_zk_integer_encoding_never_breaks_an_accepted_improvement():
    rng = random.Random(7)
    for _ in range(5000):
        old = rng.uniform(0, 99)
        new = min(100.0, old + policy.DELTA + rng.uniform(-1e-10, 5))
        if policy.meets_delta(old, new):
            assert policy.zk_integer_score(new) >= policy.zk_integer_score(old) + int(policy.DELTA)


# ---- service: validated_improvement and rejected_attempt -------------------------------------
def test_baseline_is_accepted_sets_the_pointer_and_writes_no_evidence(db, eid, baseline):
    assert reload(db, Version, baseline.id).acceptance_status == "accepted"
    assert reload(db, Execution, eid).best_version_id == baseline.id
    assert reload(db, Version, baseline.id).decision_details["outcome"] == "baseline"
    assert db.scalars(select(EvidenceRecord)).all() == []


def test_validated_improvement_moves_the_pointer_and_writes_evidence_atomically(db, eid, baseline):
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    d = acc.decide_acceptance(db, v2.id)
    assert d.outcome == "validated_improvement" and d.best_version_id == v2.id and d.evidence_id
    assert reload(db, Execution, eid).best_version_id == v2.id
    stored = reload(db, Version, v2.id)
    assert stored.acceptance_status == "accepted" and stored.rejection_reason is None and stored.decided_at
    record = db.get(EvidenceRecord, d.evidence_id)
    assert record.status == "validated_improvement" and record.failed_terms == []
    assert record.candidate_version_id == v2.id and record.previous_best_version_id == baseline.id
    assert record.provenance["delta"] == policy.DELTA


@pytest.mark.parametrize("kwargs,expected", [
    (dict(passed=5), [policy.TERM_DELTA]),  # equal
    (dict(passed=4), [policy.TERM_TEST_REGRESSION, policy.TERM_PASS_RATE, policy.TERM_DELTA]),  # lower
    (dict(passed_ids=["t0", "t1", "t2", "t3", "t5", "t6", "t7", "t8"]), [policy.TERM_TEST_REGRESSION]),
    (dict(passed=8, correctness=70.0), [policy.TERM_CORRECTNESS]),
    (dict(passed=8, quality=70.0), [policy.TERM_QUALITY]),
    (dict(passed=5, quality=82.0), [policy.TERM_DELTA]),  # +0.4: real but below delta
], ids=["equal", "lower", "test_regression", "correctness_regression", "quality_regression", "below_delta"])
def test_rejected_attempts_record_the_failed_terms_and_keep_the_best(db, eid, baseline, kwargs, expected):
    v2 = version_with(db, eid, 2, parent=baseline.id, **kwargs)
    d = acc.decide_acceptance(db, v2.id)
    assert d.outcome == "rejected_attempt" and terms(d) == expected
    stored = reload(db, Version, v2.id)
    assert stored.acceptance_status == "rejected" and stored.rejection_reason
    record = db.get(EvidenceRecord, d.evidence_id)
    assert record.status == "rejected_attempt" and [t["term"] for t in record.failed_terms] == expected
    assert reload(db, Execution, eid).best_version_id == baseline.id  # the pointer did not move
    assert reload(db, Version, baseline.id).acceptance_status == "accepted"


def test_a_higher_aggregate_does_not_excuse_a_test_regression(db, eid, baseline):
    v2 = version_with(db, eid, 2, passed_ids=["t0", "t1", "t2", "t3", "t5", "t6", "t7", "t8", "t9"], parent=baseline.id)
    assert ver.latest_evaluation(db, v2.id).overall_score >= ver.latest_evaluation(db, baseline.id).overall_score + 1
    d = acc.decide_acceptance(db, v2.id)
    assert d.outcome == "rejected_attempt" and terms(d) == [policy.TERM_TEST_REGRESSION]
    assert "1 hidden test(s)" in d.reason and "t4" not in d.reason  # hidden ids are never named


def test_public_tests_must_not_regress_even_though_they_do_not_score(db, eid):
    v1 = version_with(db, eid, 1, passed=5, public_total=2)
    acc.decide_acceptance(db, v1.id)
    v2 = version_with(db, eid, 2, passed=8, public_total=2, public_passed_ids=["p0"], parent=v1.id)
    d = acc.decide_acceptance(db, v2.id)
    assert d.outcome == "rejected_attempt" and terms(d) == [policy.TERM_TEST_REGRESSION]
    assert "public test(s) p1" in d.reason


def test_public_gains_alone_do_not_raise_the_score(db, eid):
    v1 = version_with(db, eid, 1, passed=5, public_total=2, public_passed_ids=[])
    acc.decide_acceptance(db, v1.id)
    v2 = version_with(db, eid, 2, passed=5, public_total=2, parent=v1.id)  # both public tests now pass
    d = acc.decide_acceptance(db, v2.id)
    assert d.outcome == "rejected_attempt" and terms(d) == [policy.TERM_DELTA]


def test_decisions_are_final(db, eid, baseline):
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    acc.decide_acceptance(db, v2.id)
    with pytest.raises(ConflictError, match="final"):
        acc.decide_acceptance(db, v2.id)
    with pytest.raises(ConflictError):
        acc.decide_acceptance(db, baseline.id)


def test_pointer_only_moves_on_acceptance(db, eid, baseline):
    best = baseline.id
    for n, passed in enumerate([4, 5, 8, 6], start=2):  # worse, equal, better, worse than the new best
        v = version_with(db, eid, n, passed=passed, parent=baseline.id)
        if acc.decide_acceptance(db, v.id).accepted:
            best = v.id
        assert reload(db, Execution, eid).best_version_id == best
    assert len(db.scalars(select(EvidenceRecord)).all()) == 4


# ---- service: invalid_comparison (stored separately, decides nothing) -------------------------
def assert_invalid(db, d, version_id, expected_terms, best_id):
    assert d.outcome == "invalid_comparison" and terms(d) == expected_terms and d.invalid_comparison_id
    assert reload(db, Version, version_id).acceptance_status == "pending"  # can still be judged later
    assert reload(db, Execution, d.version.execution_id).best_version_id == best_id
    row = db.get(InvalidComparison, d.invalid_comparison_id)
    assert [r["term"] for r in row.reasons] == expected_terms
    assert db.scalars(select(EvidenceRecord).where(EvidenceRecord.candidate_version_id == version_id)).all() == []
    assert "not a judgement" in d.reason


def test_an_unevaluated_candidate_is_an_invalid_comparison_and_can_be_judged_later(db, eid, baseline):
    v2 = version_with(db, eid, 2, evaluate=False, parent=baseline.id)
    assert_invalid(db, acc.decide_acceptance(db, v2.id), v2.id, [policy.PRE_CANDIDATE_COMPLETE], baseline.id)
    ver.record_evaluation(db, v2.id, complete_input(8))
    assert acc.decide_acceptance(db, v2.id).outcome == "validated_improvement"


def test_an_incomplete_candidate_evaluation_is_an_invalid_comparison(db, eid, baseline):
    v2 = ver.create_version(db, eid, code(2), parent_version_id=baseline.id)
    ver.record_evaluation(db, v2.id, EvaluationInput(tests_passed=9, tests_total=10, correctness_score=100, code_quality_score=100))
    d = acc.decide_acceptance(db, v2.id)
    assert_invalid(db, d, v2.id, [policy.PRE_CANDIDATE_COMPLETE], baseline.id)
    assert "incomplete" in d.reason


def test_a_previous_best_without_a_valid_evaluation_is_an_invalid_comparison(db, eid, baseline):
    db.execute(update(Evaluation).where(Evaluation.version_id == baseline.id).values(
        suite_id=None, suite_hash=None, evaluator_version=None, evaluator_config_hash=None,
        scoring_rule_version=None, test_results=[]))
    db.commit()
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    assert_invalid(db, acc.decide_acceptance(db, v2.id), v2.id, [policy.PRE_PREVIOUS_COMPLETE], baseline.id)


@pytest.mark.parametrize("kwargs,term", [
    (dict(suite_hash=OTHER_HASH), policy.PRE_SAME_SUITE),
    (dict(config_hash=OTHER_HASH), policy.PRE_SAME_CONFIG),
    (dict(rule="1"), policy.PRE_SAME_RULE),
], ids=["suite", "evaluator_config", "scoring_rule"])
def test_evaluations_that_do_not_match_the_commitment_are_not_compared(db, eid, baseline, kwargs, term):
    v2 = version_with(db, eid, 2, passed=9, parent=baseline.id, **kwargs)
    assert_invalid(db, acc.decide_acceptance(db, v2.id), v2.id, [term], baseline.id)


def test_a_best_pointer_into_another_execution_is_an_invalid_comparison(db, make_task, eid, baseline):
    other = exe.create_execution(db, make_task()["id"]).id
    foreign = version_with(db, other, 99, passed=5)
    acc.decide_acceptance(db, foreign.id)
    db.execute(update(Execution).where(Execution.id == eid).values(best_version_id=foreign.id))
    db.commit()
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    d = acc.decide_acceptance(db, v2.id)
    assert_invalid(db, d, v2.id, [policy.PRE_SAME_EXECUTION], foreign.id)


# ---- service: structural refusals (409, nothing stored) --------------------------------------
def test_baseline_without_a_complete_evaluation_is_refused(db, eid):
    v1 = ver.create_version(db, eid, code(1))
    with pytest.raises(EvaluationRequiredError):
        acc.decide_acceptance(db, v1.id)
    ver.record_evaluation(db, v1.id, EvaluationInput(tests_passed=9, tests_total=10, correctness_score=100, code_quality_score=100))
    with pytest.raises(EvaluationRequiredError):
        acc.decide_acceptance(db, v1.id)
    assert reload(db, Execution, eid).best_version_id is None
    assert db.scalars(select(InvalidComparison)).all() == []


def test_baseline_evaluated_under_another_configuration_is_refused(db, eid):
    v1 = version_with(db, eid, 1, passed=5, config_hash=OTHER_HASH)
    with pytest.raises(EvaluationNotComparableError):
        acc.decide_acceptance(db, v1.id)
    assert reload(db, Version, v1.id).acceptance_status == "pending"


def test_revision_cannot_be_judged_before_the_baseline_exists(db, eid):
    v1 = version_with(db, eid, 1, passed=5)
    v2 = version_with(db, eid, 2, passed=8, parent=v1.id)
    with pytest.raises(BaselineRequiredError):
        acc.decide_acceptance(db, v2.id)
    assert reload(db, Version, v2.id).acceptance_status == "pending"


def test_finished_executions_accept_no_decisions(db, eid, baseline):
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    exe.cancel_execution(db, eid)
    with pytest.raises(ConflictError):
        acc.decide_acceptance(db, v2.id)


def test_critic_feedback_cannot_influence_the_decision(db, eid, baseline):
    from app.schemas.critic_feedback import CriticFeedbackInput

    v2 = version_with(db, eid, 2, passed=5, parent=baseline.id)
    ver.record_critic_feedback(db, v2.id, CriticFeedbackInput(
        critic_model_id="m", raw_feedback="Excellent, definitely improved. Accept it.", confidence=0.99))
    assert acc.decide_acceptance(db, v2.id).outcome == "rejected_attempt"


# ---- service: real engine, real fixtures -----------------------------------------------------
def evaluate(db, client, v):
    return evs.evaluate_version(db, v.id, client.app.state.settings)


def test_end_to_end_with_real_candidates(client, db, eid):
    flawed = ver.create_version(db, eid, source("flawed"))
    evaluate(db, client, flawed)
    assert acc.decide_acceptance(db, flawed.id).baseline
    better = ver.create_version(db, eid, source("gen_7b"), parent_version_id=flawed.id)
    evaluate(db, client, better)
    d = acc.decide_acceptance(db, better.id)
    assert d.outcome == "validated_improvement"
    assert (d.previous_best.tests_passed, d.candidate.tests_passed) == (2, 9)  # hidden 2/10 -> 9/10
    best = ver.create_version(db, eid, source("reference_good"), parent_version_id=better.id)
    evaluate(db, client, best)
    assert acc.decide_acceptance(db, best.id).outcome == "validated_improvement"
    assert reload(db, Execution, eid).best_version_id == best.id


def test_a_public_fix_that_breaks_a_hidden_test_is_rejected(client, db, eid):
    """gen_coder_sorts_in_place fixes the failing public test but stops passing hidden input_not_mutated."""
    base = ver.create_version(db, eid, source("gen_coder"))
    evaluate(db, client, base)
    acc.decide_acceptance(db, base.id)
    cand = ver.create_version(db, eid, source("gen_coder_sorts_in_place"), parent_version_id=base.id)
    evaluate(db, client, cand)
    before, after = ver.latest_evaluation(db, base.id), ver.latest_evaluation(db, cand.id)
    assert after.public_tests_passed > before.public_tests_passed
    d = acc.decide_acceptance(db, cand.id)
    assert d.outcome == "rejected_attempt"
    assert terms(d) == [policy.TERM_TEST_REGRESSION, policy.TERM_DELTA]
    assert "input_not_mutated" not in d.reason and "1 hidden test(s)" in d.reason
    assert reload(db, Execution, eid).best_version_id == base.id


def test_a_worse_real_revision_is_rejected_with_every_failed_term(client, db, eid):
    base = ver.create_version(db, eid, source("gen_coder"))
    evaluate(db, client, base)
    acc.decide_acceptance(db, base.id)
    worse = ver.create_version(db, eid, source("gen_coder_no_value_check"), parent_version_id=base.id)
    evaluate(db, client, worse)
    d = acc.decide_acceptance(db, worse.id)
    assert terms(d) == [policy.TERM_TEST_REGRESSION, policy.TERM_PASS_RATE, policy.TERM_DELTA]


def test_identical_code_is_not_an_improvement(client, db, eid):
    base = ver.create_version(db, eid, source("gen_coder"))
    evaluate(db, client, base)
    acc.decide_acceptance(db, base.id)
    same = ver.create_version(db, eid, source("gen_coder"), parent_version_id=base.id)
    evaluate(db, client, same)
    assert terms(acc.decide_acceptance(db, same.id)) == [policy.TERM_DELTA]


# ---- concurrency -----------------------------------------------------------------------------
def test_two_decisions_on_one_version_only_one_wins(client, db, eid, baseline, monkeypatch):
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    loser = client.app.state.session_factory()
    real_compare = acc.compare
    try:
        def compare_then_let_the_winner_commit(previous, candidate, delta):
            result = real_compare(previous, candidate, delta)
            monkeypatch.setattr(acc, "compare", real_compare)  # only interleave once
            acc.decide_acceptance(db, v2.id)
            return result

        monkeypatch.setattr(acc, "compare", compare_then_let_the_winner_commit)
        with pytest.raises(ConflictError):
            acc.decide_acceptance(loser, v2.id)
    finally:
        loser.close()
    assert reload(db, Execution, eid).best_version_id == v2.id
    assert reload(db, Version, v2.id).acceptance_status == "accepted"
    assert len(db.scalars(select(EvidenceRecord)).all()) == 1  # no duplicate evidence


def test_a_rival_candidate_cannot_win_on_an_outdated_comparison(client, db, eid, baseline, monkeypatch):
    """V3 was compared against V1, but V2 became the best before V3's decision was written."""
    v2 = version_with(db, eid, 2, passed=7, parent=baseline.id)
    v3 = version_with(db, eid, 3, passed=8, parent=baseline.id)
    loser = client.app.state.session_factory()
    real_compare = acc.compare
    try:
        def compare_then_let_v2_win(previous, candidate, delta):
            result = real_compare(previous, candidate, delta)
            monkeypatch.setattr(acc, "compare", real_compare)
            assert acc.decide_acceptance(db, v2.id).accepted
            return result

        monkeypatch.setattr(acc, "compare", compare_then_let_v2_win)
        with pytest.raises(ConflictError):
            acc.decide_acceptance(loser, v3.id)
    finally:
        loser.close()
    assert reload(db, Execution, eid).best_version_id == v2.id
    assert reload(db, Version, v3.id).acceptance_status == "pending"  # undecided, so it can be judged again
    assert db.scalars(select(EvidenceRecord).where(EvidenceRecord.candidate_version_id == v3.id)).all() == []
    assert acc.decide_acceptance(db, v3.id).accepted  # against V2 now: 8 > 7 by 5 points
    assert reload(db, Execution, eid).best_version_id == v3.id


def test_parallel_attempts_leave_exactly_one_consistent_outcome(client, db, eid, baseline):
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    results, barrier = [], threading.Barrier(6)

    def attempt():
        session = client.app.state.session_factory()
        try:
            barrier.wait()
            results.append(acc.decide_acceptance(session, v2.id).accepted)
        except ConflictError:
            results.append("conflict")
        except Exception as exc:  # pragma: no cover - would fail the assertions below
            results.append(repr(exc))
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    assert results.count(True) == 1 and results.count("conflict") == 5, results
    assert reload(db, Execution, eid).best_version_id == v2.id
    assert len(db.scalars(select(EvidenceRecord)).all()) == 1


# ---- API -------------------------------------------------------------------------------------
def test_api_evaluate_decide_and_read_the_evidence(client, db, eid):
    commitment = client.get(f"/api/executions/{eid}").json()["data"]["commitment"]
    assert commitment["hidden_suite_hash"] == get_suite(SUITE_ID).hidden_suite_hash
    assert commitment["delta"] == policy.DELTA and commitment["onchain"] == "planned"

    v1 = ver.create_version(db, eid, source("flawed"))
    r = client.post(f"/api/versions/{v1.id}/evaluate")
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["complete"] and data["deterministic"]["tests_total"] == 10 and data["public"]["tests_total"] == 5
    assert data["deterministic"]["tests_passed"] == 2 and data["hidden_tests_failed"] == 8
    assert len(data["test_results"]) == 5 and {t["visibility"] for t in data["test_results"]} == {"public"}
    assert data["provenance"]["evaluator_config_hash"] == commitment["evaluator_config_hash"]

    d = client.post(f"/api/versions/{v1.id}/acceptance-decision").json()["data"]
    assert d["outcome"] == "baseline" and d["acceptance_status"] == "accepted"

    v2 = ver.create_version(db, eid, source("gen_7b"), parent_version_id=v1.id)
    client.post(f"/api/versions/{v2.id}/evaluate")
    d2 = client.post(f"/api/versions/{v2.id}/acceptance-decision").json()["data"]
    assert d2["outcome"] == "validated_improvement" and d2["best_version_id"] == v2.id and d2["evidence_id"]

    v3 = ver.create_version(db, eid, source("gen_7b"), parent_version_id=v2.id)
    invalid = client.post(f"/api/versions/{v3.id}/acceptance-decision").json()["data"]  # not evaluated yet
    assert invalid["outcome"] == "invalid_comparison" and invalid["acceptance_status"] == "pending"
    client.post(f"/api/versions/{v3.id}/evaluate")
    d3 = client.post(f"/api/versions/{v3.id}/acceptance-decision").json()["data"]
    assert d3["outcome"] == "rejected_attempt" and [t["term"] for t in d3["failed_terms"]] == [policy.TERM_DELTA]

    evidence = client.get(f"/api/executions/{eid}/evidence").json()["data"]
    assert [r["status"] for r in evidence["records"]] == ["validated_improvement", "rejected_attempt"]
    assert len(evidence["invalid_comparisons"]) == 1 and evidence["invalid_comparisons"][0]["candidate_version_id"] == v3.id
    assert evidence["best_version_id"] == v2.id and evidence["scoring_rule"]["delta"] == policy.DELTA
    assert evidence["unvalidated_proposals"] == 0


def test_hidden_test_names_never_appear_in_any_api_response(client, db, eid):
    v1 = ver.create_version(db, eid, source("gen_coder"))
    bodies = [client.post(f"/api/versions/{v1.id}/evaluate").text,
              client.post(f"/api/versions/{v1.id}/acceptance-decision").text]
    v2 = ver.create_version(db, eid, source("gen_coder_sorts_in_place"), parent_version_id=v1.id)
    bodies += [client.post(f"/api/versions/{v2.id}/evaluate").text,
               client.post(f"/api/versions/{v2.id}/acceptance-decision").text,
               client.get(f"/api/versions/{v2.id}").text,
               client.get(f"/api/versions/{v2.id}/evaluations").text,
               client.get(f"/api/executions/{eid}/versions").text,
               client.get(f"/api/executions/{eid}/evidence").text]
    leaked = [h for h in HIDDEN_IDS for body in bodies if f'"{h}"' in body or f" {h}" in body or f"{h}," in body]
    assert leaked == []
    assert "unsorted_input" in bodies[0]  # public tests are shown


def test_critic_feedback_is_labelled_an_unvalidated_proposal(client, db, eid):
    from app.schemas.critic_feedback import CriticFeedbackInput

    v1 = ver.create_version(db, eid, source("gen_coder"))
    ver.record_critic_feedback(db, v1.id, CriticFeedbackInput(critic_model_id="m", raw_feedback="looks fine"))
    feedback = client.get(f"/api/versions/{v1.id}/critic-feedback").json()["data"]
    assert feedback[0]["evidence_status"] == "unvalidated_proposal"
    assert client.get(f"/api/executions/{eid}/evidence").json()["data"]["unvalidated_proposals"] == 1


@pytest.mark.parametrize("path", ["evaluate", "acceptance-decision"])
@pytest.mark.parametrize("forged", [
    {"overall_score": 100}, {"tests_passed": 10, "tests_total": 10}, {"accepted": True}, {"force": True},
    {"outcome": "validated_improvement"}, {"zk_status": "verified"}, {"improved": True}, {"best_version_id": "x"},
    {"delta": 0}, {"suite_hash": "x"},
])
def test_clients_cannot_submit_scores_verdicts_or_proof_status(client, db, eid, path, forged):
    v = ver.create_version(db, eid, source("gen_coder"))
    assert client.post(f"/api/versions/{v.id}/{path}", json=forged).status_code == 422
    assert ver.list_evaluations(db, v.id) == []
    assert reload(db, Version, v.id).acceptance_status == "pending"


def test_there_is_no_route_that_accepts_evaluation_results(client):
    paths = client.app.openapi()["paths"]
    writers = {p for p, ops in paths.items() if set(ops) & {"post", "put", "patch", "delete"}}
    assert {p for p in writers if "version" in p or "evidence" in p} == {
        "/api/versions/{version_id}/evaluate", "/api/versions/{version_id}/acceptance-decision",
        "/api/evidence/{record_id}/bundle"}


def test_api_errors(client, db, eid, make_task):
    assert client.post("/api/versions/missing/evaluate").status_code == 404
    assert client.post("/api/versions/missing/acceptance-decision").status_code == 404
    assert client.get("/api/executions/missing/evidence").status_code == 404
    v = ver.create_version(db, eid, source("gen_coder"))
    r = client.post(f"/api/versions/{v.id}/acceptance-decision")
    assert r.status_code == 409 and r.json()["error"]["code"] == "EVALUATION_REQUIRED"  # baseline not evaluated
    no_suite = make_task(evaluation_suite_id=None)["id"]
    r = client.post(f"/api/tasks/{no_suite}/executions")
    assert r.status_code == 409 and r.json()["error"]["code"] == "EVALUATION_SUITE_UNAVAILABLE"


def test_api_refuses_to_run_code_when_disabled(client, db, eid):
    from app.config import Settings

    client.app.state.settings = Settings(_env_file=None, app_env="production", database_url=client.app.state.settings.database_url)
    v = ver.create_version(db, eid, source("gen_coder"))
    r = client.post(f"/api/versions/{v.id}/evaluate")
    assert r.status_code == 403 and r.json()["error"]["code"] == "EVALUATION_EXECUTION_DISABLED"
    assert ver.list_evaluations(db, v.id) == []


def test_unknown_suite_ids_are_rejected_when_creating_a_task(client, task_payload):
    r = client.post("/api/tasks", json={**task_payload, "evaluation_suite_id": "does-not-exist"})
    assert r.status_code == 422
    ok = client.post("/api/tasks", json={**task_payload, "evaluation_suite_id": SUITE_ID})
    assert ok.status_code == 201 and ok.json()["data"]["evaluation_suite_id"] == SUITE_ID


# ---- lifecycle guards ------------------------------------------------------------------------
def walk(db, eid, path):
    for status in path:
        exe.transition_execution(db, eid, status)


def test_zk_proof_needs_an_accepted_improvement(db, eid):
    walk(db, eid, TO_E2)
    with pytest.raises(InvalidTransitionError, match="no best version"):
        exe.transition_execution(db, eid, S.ZK_PROOF)
    assert exe.get_execution(db, eid).status == "evaluating_v2"


def test_the_baseline_alone_is_not_an_improvement(db, eid, baseline):
    walk(db, eid, TO_E2)
    with pytest.raises(InvalidTransitionError, match="baseline"):
        exe.transition_execution(db, eid, S.ZK_PROOF)


def test_a_rejected_revision_does_not_open_the_proof_stage(db, eid, baseline):
    v2 = version_with(db, eid, 2, passed=4, parent=baseline.id)
    acc.decide_acceptance(db, v2.id)
    walk(db, eid, TO_E2)
    with pytest.raises(InvalidTransitionError):
        exe.transition_execution(db, eid, S.ZK_PROOF)


def test_forged_flags_cannot_open_the_proof_stage(db, eid, baseline):
    """A revision marked accepted and made the best through the internal primitives, with a GOOD evaluation,
    but without a validated_improvement evidence record."""
    v2 = version_with(db, eid, 2, passed=9, parent=baseline.id)
    ver.decide_version(db, v2.id, accepted=True)
    exe.set_best_version(db, eid, v2.id)
    walk(db, eid, TO_E2)
    with pytest.raises(InvalidTransitionError, match="validated_improvement evidence"):
        exe.transition_execution(db, eid, S.ZK_PROOF)


def test_tampered_evaluations_cannot_open_the_proof_stage(db, eid, baseline):
    """A real accepted improvement whose stored evaluation is later made worse fails the re-check."""
    v2 = version_with(db, eid, 2, passed=8, parent=baseline.id)
    assert acc.decide_acceptance(db, v2.id).accepted
    ver.record_evaluation(db, v2.id, complete_input(3))  # a newer, worse evaluation supersedes the old one
    walk(db, eid, TO_E2)
    with pytest.raises(InvalidTransitionError, match="No verified improvement"):
        exe.transition_execution(db, eid, S.ZK_PROOF)


def test_an_accepted_improvement_opens_the_proof_stage(db, eid):
    walk(db, eid, TO_E2)
    grant_improvement(db, eid)
    assert exe.transition_execution(db, eid, S.ZK_PROOF).status == "zk_proof"


def test_an_improvement_accepted_in_the_third_attempt_opens_the_proof_stage(db, eid, baseline):
    walk(db, eid, TO_E3)
    v2 = version_with(db, eid, 2, passed=4, parent=baseline.id)
    assert not acc.decide_acceptance(db, v2.id).accepted
    v3 = version_with(db, eid, 3, passed=8, parent=baseline.id)
    assert acc.decide_acceptance(db, v3.id).accepted
    assert exe.transition_execution(db, eid, S.ZK_PROOF).status == "zk_proof"


def test_all_revisions_rejected_by_the_gate_allows_no_improvement(db, eid):
    walk(db, eid, TO_E3)
    v1 = version_with(db, eid, 1, passed=5)
    acc.decide_acceptance(db, v1.id)
    for n in (2, 3):
        v = version_with(db, eid, n, passed=5, parent=v1.id)
        assert not acc.decide_acceptance(db, v.id).accepted
    assert exe.transition_execution(db, eid, S.COMPLETED_NO_IMPROVEMENT).status == "completed_no_improvement"
    assert exe.get_execution(db, eid).best_version_id == v1.id


def test_no_improvement_is_refused_while_a_revision_is_undecided_or_only_invalidly_compared(db, make_task):
    eid = exe.create_execution(db, make_task()["id"], max_revisions=1).id
    walk(db, eid, TO_E2)
    v1 = version_with(db, eid, 1, passed=5)
    acc.decide_acceptance(db, v1.id)
    with pytest.raises(InvalidTransitionError, match="recorded"):
        exe.transition_execution(db, eid, S.COMPLETED_NO_IMPROVEMENT)  # no revision yet
    v2 = version_with(db, eid, 2, evaluate=False, parent=v1.id)
    assert acc.decide_acceptance(db, v2.id).outcome == "invalid_comparison"
    with pytest.raises(InvalidTransitionError, match="no recorded decision"):
        exe.transition_execution(db, eid, S.COMPLETED_NO_IMPROVEMENT)  # an invalid comparison decides nothing
    ver.record_evaluation(db, v2.id, complete_input(4))
    with pytest.raises(InvalidTransitionError, match="no recorded decision"):
        exe.transition_execution(db, eid, S.COMPLETED_NO_IMPROVEMENT)  # evaluated but undecided
    assert exe.get_execution(db, eid).status == "evaluating_v2"


def test_no_improvement_is_refused_when_the_gate_accepted_a_revision(db, make_task):
    eid = exe.create_execution(db, make_task()["id"], max_revisions=1).id
    walk(db, eid, TO_E2)
    grant_improvement(db, eid)
    with pytest.raises(InvalidTransitionError, match="accepted as an improvement"):
        exe.transition_execution(db, eid, S.COMPLETED_NO_IMPROVEMENT)


def test_terminal_states_stay_terminal_after_a_real_improvement(db, eid):
    for status in TO_E2 + [S.ZK_PROOF, S.IPFS_PUBLISH, S.BLOCKCHAIN_REGISTER, S.COMPLETED]:
        advance(db, eid, status)
    for target in S:
        kwargs = {"error_code": "X", "error_message": "y"} if target is S.FAILED else {}
        with pytest.raises(InvalidTransitionError):
            exe.transition_execution(db, eid, target, **kwargs)

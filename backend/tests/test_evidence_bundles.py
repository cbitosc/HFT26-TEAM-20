"""Milestone 07A: code-hash binding, evidence bundles, negative-evidence export.

Real-candidate flows run the real engine. Every bundle written by ANY test is also scanned for hidden
test data by the autouse fixture in conftest.py (tests/bundle_scan.py)."""
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

import pytest
from sqlalchemy import select, text, update

from app.errors import CodeHashMismatchError, InvalidTransitionError
from app.evaluation import policy
from app.evaluation.suites import get_suite
from app.hashing import canonical_json, canonical_sha256, code_sha256, is_canonical
from app.lifecycle import ExecutionStatus as S
from app.models import Evaluation, EvidenceBundle, EvidenceRecord, Version
from app.schemas.critic_feedback import CriticFeedbackInput
from app.services import acceptance_service as acc
from app.services import bundle_service as bun
from app.services import evaluation_service as evs
from app.services import execution_service as exe
from app.services import version_service as ver
from tests.bundle_scan import scan_bundle
from tests.helpers import SUITE_ID, complete_input

FIXTURES = Path(__file__).parent / "fixtures"
HIDDEN_IDS = [t.id for t in get_suite(SUITE_ID).hidden_tests]
TO_E2 = [S.GENERATING_V1, S.EVALUATING_V1, S.CRITIQUING, S.GENERATING_V2, S.EVALUATING_V2]


def source(name):
    return (FIXTURES / f"{name}.py").read_text(encoding="utf-8")


@pytest.fixture
def eid(db, make_task):
    return exe.create_execution(db, make_task()["id"]).id


def raw(settings):
    con = sqlite3.connect(settings.database_url.removeprefix("sqlite:///"))
    con.execute("PRAGMA foreign_keys=ON")
    return con


def reload(db, model, pk):
    db.expire_all()
    return db.get(model, pk)


def real_flow(client, db, eid, *names):
    """Create, evaluate (real engine) and decide each source in order. Returns the decisions."""
    decisions, parent = [], None
    for name in names:
        v = ver.create_version(db, eid, source(name), parent_version_id=parent)
        evs.evaluate_version(db, v.id, client.app.state.settings)
        decisions.append(acc.decide_acceptance(db, v.id))
        parent = v.id
    return decisions


def synthetic_rejection(db, eid):
    v1 = ver.create_version(db, eid, "def merge_intervals(x):\n    return x\n")
    ver.record_evaluation(db, v1.id, complete_input(5))
    acc.decide_acceptance(db, v1.id)
    v2 = ver.create_version(db, eid, "def merge_intervals(x):\n    return list(x)\n", parent_version_id=v1.id)
    ver.record_evaluation(db, v2.id, complete_input(passed_ids=["t0", "t1", "t2", "t3", "t5", "t6", "t7", "t8"]))
    return acc.decide_acceptance(db, v2.id)


# ---- 1. code hash ----------------------------------------------------------------------------
def test_versions_and_evaluations_carry_the_sha256_of_the_exact_code(client, db, eid):
    code = "def merge_intervals(x):\n    return sorted(x)  # é\n"  # non-ASCII: hashed as UTF-8 bytes
    v = ver.create_version(db, eid, code)
    assert v.code_sha256 == hashlib.sha256(code.encode("utf-8")).hexdigest() == code_sha256(code)
    ev = evs.evaluate_version(db, v.id, client.app.state.settings)
    assert ev.code_sha256 == v.code_sha256 == ev.provenance["code_sha256"]
    api_version = client.get(f"/api/versions/{v.id}").json()["data"]
    api_eval = client.get(f"/api/versions/{v.id}/evaluations").json()["data"][0]
    assert api_version["code_sha256"] == api_eval["code_sha256"] == v.code_sha256


def test_clients_cannot_supply_a_code_hash():
    from app.schemas.evaluation import EvaluationInput

    with pytest.raises(ValueError):
        EvaluationInput(tests_passed=1, tests_total=1, correctness_score=1, code_quality_score=1, code_sha256="NOT-HEX")


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "g" * 64, ""])
def test_the_database_requires_a_64_char_lowercase_hex_hash(client, db, eid, settings, bad):
    v = ver.create_version(db, eid, "def merge_intervals(x):\n    return x\n")
    con = raw(settings)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="ck_versions_code_sha256"):
            con.execute("UPDATE versions SET code_sha256 = ? WHERE id = ?", (bad, v.id))
        with pytest.raises(sqlite3.IntegrityError, match="ck_evaluations_code_sha256"):
            con.execute(
                "INSERT INTO evaluations (id, version_id, code_sha256, tests_passed, tests_total, test_pass_rate, "
                "correctness_score, code_quality_score, overall_score, failure_details, created_at) "
                "VALUES ('e1', ?, ?, 1, 1, 100.0, 100.0, 100.0, 100.0, '[]', '2026-10-30 12:00:00')", (v.id, bad))
    finally:
        con.close()


def test_evaluations_always_have_a_code_hash(client, db, eid, settings):
    v = ver.create_version(db, eid, "def merge_intervals(x):\n    return x\n")
    con = raw(settings)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            con.execute(
                "INSERT INTO evaluations (id, version_id, tests_passed, tests_total, test_pass_rate, "
                "correctness_score, code_quality_score, overall_score, failure_details, created_at) "
                "VALUES ('e1', ?, 1, 1, 100.0, 100.0, 100.0, 100.0, '[]', '2026-10-30 12:00:00')", (v.id,))
    finally:
        con.close()


def test_code_edited_after_creation_is_refused_by_the_evaluator(client, db, eid):
    v = ver.create_version(db, eid, source("gen_coder"))
    db.execute(update(Version).where(Version.id == v.id).values(code=source("reference_good")))
    db.commit()
    with pytest.raises(CodeHashMismatchError):
        evs.evaluate_version(db, v.id, client.app.state.settings)
    r = client.post(f"/api/versions/{v.id}/evaluate")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CODE_HASH_MISMATCH"
    assert ver.list_evaluations(db, v.id) == []


def test_the_evaluator_hashes_the_code_in_the_database_not_a_cached_copy(client, db, eid, settings):
    """Another writer changes the code while this session still holds the version (sessions use
    expire_on_commit=False). The evaluator must notice instead of hashing its cached copy."""
    v = ver.create_version(db, eid, source("gen_coder"))
    assert db.get(Version, v.id).code == source("gen_coder")  # loaded into this session's identity map
    con = raw(settings)
    try:
        con.execute("UPDATE versions SET code = ? WHERE id = ?", (source("reference_good"), v.id))
        con.commit()
    finally:
        con.close()
    with pytest.raises(CodeHashMismatchError):
        evs.evaluate_version(db, v.id, client.app.state.settings)


def test_code_edited_after_evaluation_is_an_invalid_comparison(client, db, eid):
    """Code and stored hash rewritten consistently after V2 was evaluated: the evaluation no longer
    belongs to the stored code, so the gate does not compare it."""
    v1, v2 = None, None
    decisions = real_flow(client, db, eid, "flawed")
    v1 = decisions[0].version
    v2 = ver.create_version(db, eid, source("gen_7b"), parent_version_id=v1.id)
    evs.evaluate_version(db, v2.id, client.app.state.settings)
    swapped = source("reference_good")
    db.execute(update(Version).where(Version.id == v2.id).values(code=swapped, code_sha256=code_sha256(swapped)))
    db.commit()
    d = acc.decide_acceptance(db, v2.id)
    assert d.outcome == "invalid_comparison"
    assert [t.term for t in d.failed_terms] == [policy.PRE_SAME_CODE]
    assert reload(db, Version, v2.id).acceptance_status == "pending"


def test_a_tampered_previous_best_is_an_invalid_comparison(client, db, eid):
    v1 = real_flow(client, db, eid, "flawed")[0].version
    db.execute(text("UPDATE versions SET code = code || '# edited' WHERE id = :i"), {"i": v1.id})
    db.commit()
    v2 = ver.create_version(db, eid, source("gen_7b"), parent_version_id=v1.id)
    evs.evaluate_version(db, v2.id, client.app.state.settings)
    d = acc.decide_acceptance(db, v2.id)
    assert d.outcome == "invalid_comparison" and [t.term for t in d.failed_terms] == [policy.PRE_SAME_CODE]


def test_a_tampered_baseline_cannot_become_the_baseline(client, db, eid):
    v1 = ver.create_version(db, eid, source("flawed"))
    evs.evaluate_version(db, v1.id, client.app.state.settings)
    other = source("gen_7b")
    db.execute(update(Version).where(Version.id == v1.id).values(code=other, code_sha256=code_sha256(other)))
    db.commit()
    r = client.post(f"/api/versions/{v1.id}/acceptance-decision")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CODE_HASH_MISMATCH"


def test_tampering_the_best_version_closes_the_proof_stage(client, db, eid):
    for status in TO_E2:
        exe.transition_execution(db, eid, status)
    _, d2 = real_flow(client, db, eid, "flawed", "gen_7b")
    assert d2.accepted
    db.execute(text("UPDATE versions SET code = code || '\n# edited' WHERE id = :i"), {"i": d2.version.id})
    db.commit()
    with pytest.raises(InvalidTransitionError, match="code SHA-256"):
        exe.transition_execution(db, eid, S.ZK_PROOF)


# ---- 2/3. bundles: contents, negative evidence -----------------------------------------------
def test_validated_improvement_bundle_from_real_candidates(client, db, eid):
    _, d2 = real_flow(client, db, eid, "flawed", "gen_7b")
    assert d2.outcome == "validated_improvement"
    r = client.post(f"/api/evidence/{d2.evidence_id}/bundle")
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["hash_valid"] and data["canonical"] and data["status"] == "validated_improvement"
    assert data["bundle_sha256"] == hashlib.sha256(data["bundle_json"].encode("utf-8")).hexdigest()
    b = data["bundle"]
    assert b["kind"] == "autoevolve.evidence_bundle" and b["bundle_schema_version"] == "1" and b["include_code"]
    assert b["evidence"]["status"] == "validated_improvement" and b["evidence"]["failed_terms"] == []
    execution = exe.get_execution(db, eid)
    assert b["commitment"] == {
        "suite_id": execution.suite_id, "suite_hash": execution.suite_hash,
        "public_suite_hash": execution.public_suite_hash, "hidden_suite_hash": execution.hidden_suite_hash,
        "evaluator_config_hash": execution.evaluator_config_hash,
        "scoring_rule_version": execution.scoring_rule_version, "delta": execution.delta,
        "committed_at": b["commitment"]["committed_at"]}
    assert b["execution"]["task_category"] == "algorithms"
    for side, name, hidden in (("previous", "flawed", (2, 10)), ("candidate", "gen_7b", (9, 10))):
        assert b[side]["code"] == source(name) and b[side]["code_sha256"] == code_sha256(source(name))
        assert (b[side]["hidden_counts"]["passed"], b[side]["hidden_counts"]["total"]) == hidden
        assert len(b[side]["public_tests"]) == 5
        assert set(b[side]["scores"]) == {"hidden_pass_rate", "correctness", "code_quality", "overall"}
    assert b["diff"].startswith("--- V1\n+++ V2")
    assert any(line.startswith("Hidden tests: 7 now passing, 0 now failing") for line in b["changelog"])
    assert b["parent_bundle_sha256"] is None  # the previous best is the baseline V1
    assert b["provenance"]["candidate_evaluation"]["code_sha256"] == code_sha256(source("gen_7b"))


def test_rejected_attempt_exports_as_negative_evidence(client, db, eid):
    _, d2 = real_flow(client, db, eid, "gen_coder", "gen_coder_sorts_in_place")
    assert d2.outcome == "rejected_attempt"
    data = client.post(f"/api/evidence/{d2.evidence_id}/bundle").json()["data"]
    terms = data["bundle"]["evidence"]["failed_terms"]
    assert [t["term"] for t in terms] == [policy.TERM_TEST_REGRESSION, policy.TERM_DELTA]
    assert "1 hidden test(s) passed in V1 but fail in V2" in terms[0]["message"]
    assert "input_not_mutated" not in data["bundle_json"].replace(source("gen_coder"), "")
    assert any("Public tests now passing: unsorted_input" in line for line in data["bundle"]["changelog"])
    assert any("Failed terms: no_test_regression, aggregate_delta" in line for line in data["bundle"]["changelog"])


def test_bundles_chain_through_the_parent_bundle_hash(client, db, eid):
    _, d2, d3 = real_flow(client, db, eid, "flawed", "gen_7b", "reference_good")
    assert d3.outcome == "validated_improvement"
    third = client.post(f"/api/evidence/{d3.evidence_id}/bundle").json()["data"]  # builds the parent first
    second = client.get(f"/api/evidence/{d2.evidence_id}/bundle").json()["data"]
    assert third["bundle"]["parent_bundle_sha256"] == second["bundle_sha256"]


def test_include_code_false_exports_hashes_only(client, db, eid):
    _, d2 = real_flow(client, db, eid, "flawed", "gen_7b")
    with_code = client.post(f"/api/evidence/{d2.evidence_id}/bundle").json()["data"]
    without = client.post(f"/api/evidence/{d2.evidence_id}/bundle?include_code=false").json()["data"]
    b = without["bundle"]
    assert b["include_code"] is False and b["diff"] is None
    assert "code" not in b["previous"] and "code" not in b["candidate"]
    assert b["candidate"]["code_sha256"] == with_code["bundle"]["candidate"]["code_sha256"]
    assert source("gen_7b") not in without["bundle_json"]
    assert any(line.startswith("Definitions added/removed/changed:") for line in b["changelog"])
    assert without["bundle_sha256"] != with_code["bundle_sha256"]


def test_critic_text_is_never_included(client, db, eid):
    d = synthetic_rejection(db, eid)
    ver.record_critic_feedback(db, d.version.id, CriticFeedbackInput(
        critic_model_id="critic-x", raw_feedback="CRITIC_SECRET_OPINION accept this", confidence=0.99))
    bundle, _ = bun.build_or_get_bundle(db, d.evidence_id)
    assert "CRITIC_SECRET_OPINION" not in bundle.bundle_json and "critic-x" not in bundle.bundle_json


# ---- determinism and canonical form -----------------------------------------------------------
def test_the_hash_is_stable_across_repeated_builds(client, db, eid):
    _, d2 = real_flow(client, db, eid, "flawed", "gen_7b")
    stored, created = bun.build_or_get_bundle(db, d2.evidence_id)
    record = db.get(EvidenceRecord, d2.evidence_id)
    for _ in range(3):
        rebuilt = canonical_json(bun.bundle_content(db, record, include_code=True))
        assert rebuilt == stored.bundle_json
        assert hashlib.sha256(rebuilt.encode("utf-8")).hexdigest() == stored.bundle_sha256
    assert is_canonical(stored.bundle_json)
    assert stored.bundle_json == canonical_json(json.loads(stored.bundle_json))


def test_the_hash_changes_if_any_field_changes(client, db, eid):
    d = synthetic_rejection(db, eid)
    content = bun.bundle_content(db, db.get(EvidenceRecord, d.evidence_id), include_code=True)
    base = canonical_sha256(content)
    leaves = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [i])
        else:
            leaves.append(path)

    walk(content, [])
    assert len(leaves) > 50
    for path in leaves:
        changed = json.loads(json.dumps(content))
        target = changed
        for key in path[:-1]:
            target = target[key]
        value = target[path[-1]]
        target[path[-1]] = (not value) if isinstance(value, bool) else ("x" if value is None else
                            value + 1 if isinstance(value, (int, float)) else str(value) + "x")
        assert canonical_sha256(changed) != base, path


def test_canonical_json_is_sorted_compact_utf8():
    assert canonical_json({"b": 1, "a": [1, {"d": "é", "c": None}]}) == '{"a":[1,{"c":null,"d":"é"}],"b":1}'
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


# ---- idempotency and immutability -------------------------------------------------------------
def test_post_is_idempotent(client, db, eid):
    d = synthetic_rejection(db, eid)
    first = client.post(f"/api/evidence/{d.evidence_id}/bundle")
    second = client.post(f"/api/evidence/{d.evidence_id}/bundle")
    got = client.get(f"/api/evidence/{d.evidence_id}/bundle")
    assert (first.status_code, second.status_code, got.status_code) == (201, 200, 200)
    assert first.json()["data"]["bundle_sha256"] == second.json()["data"]["bundle_sha256"] == got.json()["data"]["bundle_sha256"]
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert len(db.scalars(select(EvidenceBundle)).all()) == 1


def test_concurrent_builds_leave_one_bundle(client, db, eid):
    d = synthetic_rejection(db, eid)
    hashes, barrier = [], threading.Barrier(5)

    def build():
        session = client.app.state.session_factory()
        try:
            barrier.wait()
            hashes.append(bun.build_or_get_bundle(session, d.evidence_id)[0].bundle_sha256)
        except Exception as exc:  # pragma: no cover
            hashes.append(repr(exc))
        finally:
            session.close()

    threads = [threading.Thread(target=build) for _ in range(5)]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    assert len(set(hashes)) == 1 and len(hashes) == 5, hashes
    assert len(db.scalars(select(EvidenceBundle)).all()) == 1


def test_stored_bundles_are_immutable(client, db, eid, settings):
    d = synthetic_rejection(db, eid)
    bundle, _ = bun.build_or_get_bundle(db, d.evidence_id)
    con = raw(settings)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute("UPDATE evidence_bundles SET bundle_json = '{}' WHERE id = ?", (bundle.id,))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute("DELETE FROM evidence_bundles WHERE id = ?", (bundle.id,))
    finally:
        con.close()


@pytest.mark.parametrize("column", ["bundle_json", "bundle_sha256"])
def test_tampering_is_detected_by_recomputing_the_hash(client, db, eid, settings, column):
    d = synthetic_rejection(db, eid)
    bundle, _ = bun.build_or_get_bundle(db, d.evidence_id)
    con = raw(settings)
    try:  # an attacker with raw database access removes the guard and edits the row
        con.execute("DROP TRIGGER trg_evidence_bundles_no_update")
        if column == "bundle_json":
            con.execute("UPDATE evidence_bundles SET bundle_json = replace(bundle_json, 'rejected_attempt', "
                        "'validated_improvement') WHERE id = ?", (bundle.id,))
        else:
            con.execute("UPDATE evidence_bundles SET bundle_sha256 = ? WHERE id = ?", ("0" * 64, bundle.id))
        con.commit()
    finally:
        con.close()
    data = client.get(f"/api/evidence/{d.evidence_id}/bundle").json()["data"]
    assert data["hash_valid"] is False and data["recomputed_sha256"] != data["bundle_sha256"]


# ---- eligibility and refusal paths --------------------------------------------------------------
def test_invalid_comparisons_and_critic_proposals_are_not_exportable(client, db, eid):
    v1 = ver.create_version(db, eid, "def merge_intervals(x):\n    return x\n")
    ver.record_evaluation(db, v1.id, complete_input(5))
    acc.decide_acceptance(db, v1.id)
    v2 = ver.create_version(db, eid, "def merge_intervals(x):\n    return list(x)\n", parent_version_id=v1.id)
    invalid = acc.decide_acceptance(db, v2.id)  # not evaluated
    assert invalid.outcome == "invalid_comparison"
    feedback = ver.record_critic_feedback(db, v2.id, CriticFeedbackInput(critic_model_id="m", raw_feedback="ok"))
    for record_id in (invalid.invalid_comparison_id, feedback.id):
        for r in (client.post(f"/api/evidence/{record_id}/bundle"), client.get(f"/api/evidence/{record_id}/bundle")):
            assert r.status_code == 409 and r.json()["error"]["code"] == "EVIDENCE_NOT_EXPORTABLE"
    assert db.scalars(select(EvidenceBundle)).all() == []


def test_unknown_records_and_unbuilt_bundles(client, db, eid):
    r = client.post("/api/evidence/missing/bundle")
    assert r.status_code == 404 and r.json()["error"]["code"] == "EVIDENCE_RECORD_NOT_FOUND"
    d = synthetic_rejection(db, eid)
    r = client.get(f"/api/evidence/{d.evidence_id}/bundle")
    assert r.status_code == 404 and r.json()["error"]["code"] == "EVIDENCE_BUNDLE_NOT_FOUND"


def test_code_tampered_after_the_decision_cannot_be_exported(client, db, eid):
    d = synthetic_rejection(db, eid)
    db.execute(text("UPDATE versions SET code = code || '# x' WHERE id = :i"), {"i": d.version.id})
    db.commit()
    r = client.post(f"/api/evidence/{d.evidence_id}/bundle")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CODE_HASH_MISMATCH"


@pytest.mark.parametrize("forged", [
    {"bundle_json": "{}"}, {"bundle_sha256": "0" * 64}, {"bundle": {}}, {"overall_score": 100},
    {"status": "validated_improvement"}, {"include_code": False},
])
def test_clients_cannot_send_bundle_content_scores_or_hashes(client, db, eid, forged):
    d = synthetic_rejection(db, eid)
    assert client.post(f"/api/evidence/{d.evidence_id}/bundle", json=forged).status_code == 422
    assert db.scalars(select(EvidenceBundle)).all() == []


def test_execution_evidence_lists_bundle_hashes(client, db, eid):
    d = synthetic_rejection(db, eid)
    a = client.post(f"/api/evidence/{d.evidence_id}/bundle").json()["data"]
    b = client.post(f"/api/evidence/{d.evidence_id}/bundle?include_code=false").json()["data"]
    records = client.get(f"/api/executions/{eid}/evidence").json()["data"]["records"]
    assert {(x["include_code"], x["bundle_sha256"]) for x in records[0]["bundles"]} == {
        (True, a["bundle_sha256"]), (False, b["bundle_sha256"])}


# ---- 4. hidden-data leak scan -----------------------------------------------------------------
def test_the_scanner_finds_planted_hidden_data():
    """Guards the guard: the scanner used after every test must catch each kind of leak."""
    suite = get_suite(SUITE_ID)
    hidden = suite.hidden_tests[0]
    assert scan_bundle({"changelog": [f"fixed {hidden.id}"]})
    assert scan_bundle({"evidence": {"failed_terms": [{"term": "x", "message": "t3 broke"}]}})
    assert scan_bundle({"candidate": {"public_tests": [{"test_id": "p0", "visibility": "hidden"}]}})
    assert scan_bundle({"note": hidden.description})
    assert scan_bundle({hidden.id: 1})
    assert scan_bundle({"candidate": {"code": f"# {hidden.id}"}}) == []  # source is generator output


def test_no_bundle_or_api_response_contains_hidden_test_ids(client, db, eid):
    _, d2 = real_flow(client, db, eid, "gen_coder", "gen_coder_sorts_in_place")
    responses = [client.post(f"/api/evidence/{d2.evidence_id}/bundle").json()["data"],
                 client.post(f"/api/evidence/{d2.evidence_id}/bundle?include_code=false").json()["data"],
                 client.get(f"/api/evidence/{d2.evidence_id}/bundle").json()["data"]]
    for data in responses:
        assert scan_bundle(data["bundle"]) == []  # every field except the candidate source
        assert data["bundle"] == json.loads(data["bundle_json"])  # the text form carries nothing else
        envelope = {k: v for k, v in data.items() if k not in ("bundle", "bundle_json")}
        assert scan_bundle(envelope) == []
    # whole-word match: "chain" is a hidden id, but also a substring of the commitment's "onchain" field
    assert scan_bundle(client.get(f"/api/executions/{eid}/evidence").json()["data"]) == []
    for bundle in db.scalars(select(EvidenceBundle)):
        assert scan_bundle(json.loads(bundle.bundle_json)) == []

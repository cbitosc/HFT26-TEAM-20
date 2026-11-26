"""Local, hidden-safe, hash-addressed evidence bundles (nothing is uploaded anywhere).

A bundle exports ONE EvidenceRecord (validated_improvement or rejected_attempt). Rejected attempts are
first-class negative evidence: they carry the exact failed term ids and their hidden-safe messages.

Contents are built only from stored, immutable data (the record, the two evaluations, the two
versions' code, the execution's commitment), then serialised with `canonical_json`. The same record
and the same `include_code` flag therefore always produce the same bytes and the same bundle_sha256.

Never included: hidden test ids, names, inputs, expected values or per-test hidden results (hidden
tests appear as counts only); Critic text; invalid comparisons; anything a client sent.
"""
import ast
import difflib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import utcnow
from app.errors import CodeHashMismatchError, EvidenceNotExportableError, NotFoundError
from app.hashing import canonical_json, code_sha256, is_canonical, sha256_hex
from app.models import (
    CriticFeedback,
    Evaluation,
    EvidenceBundle,
    EvidenceRecord,
    Execution,
    InvalidComparison,
    Task,
    Version,
)

BUNDLE_SCHEMA_VERSION = "1"
BUNDLE_KIND = "autoevolve.evidence_bundle"
EXPORTABLE = ("validated_improvement", "rejected_attempt")


# ---- resolution ------------------------------------------------------------------------------
def get_exportable_record(session: Session, record_id: str) -> EvidenceRecord:
    record = session.get(EvidenceRecord, record_id)
    if record is None:
        if session.get(InvalidComparison, record_id) is not None:
            raise EvidenceNotExportableError(
                "An invalid comparison is not evidence about a revision and cannot be exported as a bundle."
            )
        if session.get(CriticFeedback, record_id) is not None:
            raise EvidenceNotExportableError(
                "Critic feedback is an unvalidated proposal, not evidence, and cannot be exported as a bundle."
            )
        raise NotFoundError("evidence_record", record_id)
    if record.status not in EXPORTABLE:
        raise EvidenceNotExportableError(f"Evidence with status '{record.status}' cannot be exported.")
    return record


def find_bundle(session: Session, record_id: str, include_code: bool) -> EvidenceBundle | None:
    return session.scalars(
        select(EvidenceBundle).where(EvidenceBundle.evidence_record_id == record_id,
                                     EvidenceBundle.include_code.is_(include_code))
    ).first()


def bundles_for_records(session: Session, record_ids: list[str]) -> dict[str, list[EvidenceBundle]]:
    out: dict[str, list[EvidenceBundle]] = {rid: [] for rid in record_ids}
    if record_ids:
        for b in session.scalars(select(EvidenceBundle).where(EvidenceBundle.evidence_record_id.in_(record_ids))
                                 .order_by(EvidenceBundle.include_code.desc(), EvidenceBundle.id)):
            out[b.evidence_record_id].append(b)
    return out


# ---- verification ----------------------------------------------------------------------------
def verify(bundle: EvidenceBundle) -> dict:
    """Recompute the hash over the stored canonical bytes. Any edit to bundle_json or bundle_sha256 shows."""
    recomputed = sha256_hex(bundle.bundle_json.encode("utf-8"))
    return {"recomputed_sha256": recomputed, "hash_valid": recomputed == bundle.bundle_sha256,
            "canonical": is_canonical(bundle.bundle_json)}


# ---- building --------------------------------------------------------------------------------
def build_or_get_bundle(session: Session, record_id: str, *, include_code: bool = True) -> tuple[EvidenceBundle, bool]:
    """Returns (bundle, created). Idempotent: an existing bundle for (record, include_code) is returned unchanged."""
    record = get_exportable_record(session, record_id)
    existing = find_bundle(session, record.id, include_code)
    if existing is not None:
        return existing, False
    content = bundle_content(session, record, include_code=include_code)
    text = canonical_json(content)
    bundle = EvidenceBundle(
        evidence_record_id=record.id, include_code=include_code, bundle_json=text,
        bundle_sha256=sha256_hex(text.encode("utf-8")), created_at=utcnow(),
    )
    session.add(bundle)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()  # a concurrent request built it first: return that one
        existing = find_bundle(session, record.id, include_code)
        if existing is None:
            raise
        return existing, False
    return bundle, True


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _checked(session: Session, version: Version, evaluation: Evaluation) -> None:
    session.refresh(version)  # hash the code in the database, never a cached copy
    current = code_sha256(version.code)
    if not (current == version.code_sha256 == evaluation.code_sha256):
        raise CodeHashMismatchError(
            f"The stored code of {version.label} no longer matches the code that was evaluated; the evidence "
            "cannot be exported."
        )


def _side(version: Version, evaluation: Evaluation, include_code: bool) -> dict:
    results = evaluation.test_results or []
    side = {
        "version_id": version.id,
        "label": version.label,
        "sequence": version.sequence,
        "code_sha256": version.code_sha256,
        "evaluation_id": evaluation.id,
        "scores": {
            "hidden_pass_rate": evaluation.test_pass_rate,
            "correctness": evaluation.correctness_score,
            "code_quality": evaluation.code_quality_score,
            "overall": evaluation.overall_score,
        },
        # public tests: per-test results in suite order. Hidden tests: COUNTS ONLY.
        "public_tests": [{"test_id": r["test_id"], "passed": r["passed"]}
                         for r in results if r.get("visibility") == "public"],
        "public_counts": {"passed": evaluation.public_tests_passed, "total": evaluation.public_tests_total},
        "hidden_counts": {"passed": evaluation.tests_passed, "total": evaluation.tests_total},
    }
    if include_code:
        side["code"] = version.code
    return side


def _diff(previous: Version, candidate: Version) -> str:
    return "\n".join(difflib.unified_diff(previous.code.splitlines(), candidate.code.splitlines(),
                                          fromfile=previous.label, tofile=candidate.label, lineterm=""))


def _top_level_definitions(code: str) -> dict[str, str] | None:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _changelog(record, previous, candidate, prev_eval, cand_eval, include_code) -> list[str]:
    """Deterministic, data-derived changelog (no model involved)."""
    diff_lines = _diff(previous, candidate).splitlines()
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    outcome = "accepted as a validated improvement" if record.status == "validated_improvement" else "rejected"
    log = [f"{candidate.label} compared with the best version {previous.label}: {outcome}.",
           f"Source lines: +{added} / -{removed}."]

    before, after = _top_level_definitions(previous.code), _top_level_definitions(candidate.code)
    if before is not None and after is not None:
        new = sorted(set(after) - set(before))
        gone = sorted(set(before) - set(after))
        changed = sorted(n for n in set(before) & set(after) if before[n] != after[n])
        if include_code:
            for label, names in (("added", new), ("removed", gone), ("changed", changed)):
                if names:
                    log.append(f"Definitions {label}: {', '.join(names)}.")
        else:
            log.append(f"Definitions added/removed/changed: {len(new)}/{len(gone)}/{len(changed)}.")
    else:
        log.append("Definitions: not compared (one version does not parse).")

    def outcomes(evaluation, visibility):
        return {r["test_id"]: r["passed"] for r in (evaluation.test_results or []) if r.get("visibility") == visibility}

    pub_before, pub_after = outcomes(prev_eval, "public"), outcomes(cand_eval, "public")
    fixed = sorted(t for t, ok in pub_after.items() if ok and not pub_before.get(t, False))
    broke = sorted(t for t, ok in pub_after.items() if not ok and pub_before.get(t, False))
    if fixed:
        log.append(f"Public tests now passing: {', '.join(fixed)}.")
    if broke:
        log.append(f"Public tests now failing: {', '.join(broke)}.")
    hid_before, hid_after = outcomes(prev_eval, "hidden"), outcomes(cand_eval, "hidden")
    hidden_fixed = sum(1 for t, ok in hid_after.items() if ok and not hid_before.get(t, False))
    hidden_broke = sum(1 for t, ok in hid_after.items() if not ok and hid_before.get(t, False))
    log.append(f"Hidden tests: {hidden_fixed} now passing, {hidden_broke} now failing "
               f"({prev_eval.tests_passed}/{prev_eval.tests_total} -> {cand_eval.tests_passed}/{cand_eval.tests_total}).")

    for name, a, b in (("Hidden pass rate", prev_eval.test_pass_rate, cand_eval.test_pass_rate),
                       ("Correctness", prev_eval.correctness_score, cand_eval.correctness_score),
                       ("Code quality", prev_eval.code_quality_score, cand_eval.code_quality_score),
                       ("Aggregate score", prev_eval.overall_score, cand_eval.overall_score)):
        sign = "+" if b - a >= 0 else "-"
        log.append(f"{name}: {_fmt(a)} -> {_fmt(b)} ({sign}{_fmt(abs(b - a))}).")
    if record.failed_terms:
        log.append("Failed terms: " + ", ".join(t["term"] for t in record.failed_terms) + ".")
    return log


def bundle_content(session: Session, record: EvidenceRecord, *, include_code: bool) -> dict:
    execution = session.get(Execution, record.execution_id)
    task = session.get(Task, execution.task_id)
    candidate = session.get(Version, record.candidate_version_id)
    previous = session.get(Version, record.previous_best_version_id)
    cand_eval = session.get(Evaluation, record.candidate_evaluation_id)
    prev_eval = session.get(Evaluation, record.previous_evaluation_id)
    _checked(session, candidate, cand_eval)
    _checked(session, previous, prev_eval)

    # Parent: the bundle of the decision that made the previous best version the best (none for V1).
    parent_record = session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.candidate_version_id == previous.id,
                                     EvidenceRecord.status == "validated_improvement")
    ).first()
    parent_hash = None
    if parent_record is not None:
        parent_hash = build_or_get_bundle(session, parent_record.id, include_code=include_code)[0].bundle_sha256

    return {
        "kind": BUNDLE_KIND,
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "include_code": include_code,
        "evidence": {
            "record_id": record.id,
            "status": record.status,
            "failed_terms": [{"term": t["term"], "message": t["message"]} for t in record.failed_terms],
            "decided_at": _iso(record.created_at),
            "decision_provenance": record.provenance,
        },
        "execution": {"id": execution.id, "task_id": execution.task_id,
                      "task_category": task.category if task else None},
        "commitment": {
            "suite_id": execution.suite_id,
            "suite_hash": execution.suite_hash,
            "public_suite_hash": execution.public_suite_hash,
            "hidden_suite_hash": execution.hidden_suite_hash,
            "evaluator_config_hash": execution.evaluator_config_hash,
            "scoring_rule_version": execution.scoring_rule_version,
            "delta": execution.delta,
            "committed_at": _iso(execution.committed_at) if execution.committed_at else None,
        },
        "previous": _side(previous, prev_eval, include_code),
        "candidate": _side(candidate, cand_eval, include_code),
        "diff": _diff(previous, candidate) if include_code else None,
        "changelog": _changelog(record, previous, candidate, prev_eval, cand_eval, include_code),
        "provenance": {"previous_evaluation": prev_eval.provenance or {},
                       "candidate_evaluation": cand_eval.provenance or {}},
        "parent_bundle_sha256": parent_hash,
    }

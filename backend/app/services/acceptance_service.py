"""Evaluator-led acceptance of a version (PRD Section 5). Persisted evaluations are the only input.

Outcomes:
  baseline               V1 with a complete evaluation matching the execution's commitment becomes the
                         first best version. Nothing is compared, so no evidence record is written.
  validated_improvement  preconditions hold and every predicate term holds. The version is accepted, an
                         EvidenceRecord is written, and best_version_id moves, all in ONE transaction.
  rejected_attempt       preconditions hold but at least one predicate term failed. The version is
                         rejected (final), an EvidenceRecord lists every failed term, the best is kept.
  invalid_comparison     a precondition failed (missing/incomplete evaluation, suite/config/rule not the
                         committed one, versions from different executions). An InvalidComparison row is
                         stored separately; the version stays PENDING so it can be re-evaluated and judged
                         later. It is not evidence that the revision is bad.

Structural problems that are not comparisons at all (version already decided, finished execution, no
baseline yet, V1 decided twice, inconsistent best pointer) are refused with a 409 and record nothing.

Acceptance updates the version and the execution's best_version_id each with a compare-and-swap, so
concurrent attempts cannot leave them inconsistent. This service never reads Critic feedback or any
caller-supplied score.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.database import utcnow
from app.errors import (
    BaselineRequiredError,
    CodeHashMismatchError,
    ConflictError,
    EvaluationNotComparableError,
    EvaluationRequiredError,
    InvalidTransitionError,
    NotFoundError,
)
from app.evaluation import policy
from app.evaluation.completeness import is_complete
from app.evaluation.gate import (
    Commitment,
    EvalSnapshot,
    FailedTerm,
    code_matches,
    compare,
    preconditions,
    scores,
    snapshot,
)
from app.lifecycle import TERMINAL_STATUSES, ExecutionStatus
from app.models import AcceptanceStatus, Evaluation, EvidenceRecord, Execution, InvalidComparison, Version
from app.services import version_service

MAX_REASON = 1000

BASELINE = "baseline"
VALIDATED = "validated_improvement"
REJECTED = "rejected_attempt"
INVALID = "invalid_comparison"


@dataclass(frozen=True)
class AcceptanceDecision:
    version: Version
    outcome: str
    reason: str
    failed_terms: tuple[FailedTerm, ...]
    candidate: EvalSnapshot | None
    previous_best: EvalSnapshot | None
    best_version_id: str | None
    decided_at: datetime | None
    evidence_id: str | None = None
    invalid_comparison_id: str | None = None

    @property
    def accepted(self) -> bool:
        return self.outcome in (BASELINE, VALIDATED)

    @property
    def baseline(self) -> bool:
        return self.outcome == BASELINE

    @property
    def violations(self) -> tuple[str, ...]:
        return tuple(t.message for t in self.failed_terms)


def commitment_of(execution: Execution) -> Commitment | None:
    if not (execution.suite_hash and execution.evaluator_config_hash and execution.scoring_rule_version
            and execution.delta):
        return None
    return Commitment(execution.suite_hash, execution.evaluator_config_hash, execution.scoring_rule_version,
                      execution.delta)


def _evaluation_term(session: Session, version: Version, term: str, role: str) -> tuple[Evaluation | None, FailedTerm | None]:
    evaluation = version_service.latest_evaluation(session, version.id)
    if evaluation is None:
        return None, FailedTerm(term, f"{role} {version.label} has not been evaluated")
    if not is_complete(evaluation):
        return None, FailedTerm(term, f"the latest evaluation of {role.lower()} {version.label} is incomplete "
                                      "(missing provenance or per-test outcomes)")
    return evaluation, None


def _load(session: Session, version_id: str) -> tuple[Version, Execution]:
    version = version_service.get_version(session, version_id)
    session.refresh(version)  # never judge from a stale identity-map copy
    if version.acceptance_status != AcceptanceStatus.PENDING.value:
        raise ConflictError(f"Version already {version.acceptance_status}; decisions are final.")
    execution = session.get(Execution, version.execution_id)
    if execution is None:
        raise NotFoundError("execution", version.execution_id)
    session.refresh(execution)
    if ExecutionStatus(execution.status) in TERMINAL_STATUSES:
        raise ConflictError(f"The execution is {execution.status}; no further decisions can be made.")
    return version, execution


def decide_acceptance(session: Session, version_id: str) -> AcceptanceDecision:
    version, execution = _load(session, version_id)
    commitment = commitment_of(execution)
    if execution.best_version_id is None:
        return _decide_baseline(session, version, execution, commitment)
    if version.sequence == 1:
        raise ConflictError("The baseline is already established; V1 cannot be decided again.")

    previous_id = execution.best_version_id
    best = session.get(Version, previous_id)
    if best is None:
        raise ConflictError("The recorded best version does not exist; the execution is inconsistent.")
    session.refresh(best)  # its code is hashed below: read it from the database, not the cache
    failed: list[FailedTerm] = []
    if best.execution_id != version.execution_id:
        failed.append(FailedTerm(policy.PRE_SAME_EXECUTION, "the execution's best version belongs to another execution"))
    else:
        if best.acceptance_status != AcceptanceStatus.ACCEPTED.value:
            raise ConflictError("The recorded best version is not an accepted version; the execution is inconsistent.")
        if version.sequence <= best.sequence:
            raise ConflictError(f"{version.label} is not newer than the current best {best.label}.")
    if commitment is None:
        failed.append(FailedTerm(policy.PRE_SAME_SUITE, "the execution has no recorded commitment to compare against"))

    candidate_eval, term = _evaluation_term(session, version, policy.PRE_CANDIDATE_COMPLETE, "Candidate")
    if term:
        failed.append(term)
    previous_eval, term = _evaluation_term(session, best, policy.PRE_PREVIOUS_COMPLETE, "Previous best")
    if term:
        failed.append(term)
    candidate = snapshot(version, candidate_eval) if candidate_eval else None
    previous = snapshot(best, previous_eval) if previous_eval else None
    if candidate and previous and commitment:
        seen = {t.term for t in failed}
        failed.extend(t for t in preconditions(commitment, previous, candidate)
                      if t.term != policy.PRE_SAME_EXECUTION or t.term not in seen)

    if failed:
        return _record_invalid(session, version, execution, previous_id, candidate, previous, failed)

    result = compare(previous, candidate, commitment.delta)
    outcome = VALIDATED if result.accepted else REJECTED
    reason = (
        f"{version.label} accepted: aggregate {candidate.overall_score:g} >= {previous.label} "
        f"{previous.overall_score:g} + delta {commitment.delta:g}, with no test or dimension regression."
        if result.accepted
        else f"{version.label} rejected: " + "; ".join(t.message for t in result.failed_terms) + "."
    )[:MAX_REASON]
    return _commit_decision(session, version, execution, previous_id, outcome, reason, result.failed_terms,
                            candidate, previous, commitment)


def _decide_baseline(session, version, execution, commitment) -> AcceptanceDecision:
    if version.sequence != 1:
        raise BaselineRequiredError(f"{version.label} cannot be judged before the baseline V1 has been accepted.")
    if commitment is None:
        raise EvaluationNotComparableError("The execution has no recorded commitment; its baseline cannot be established.")
    evaluation, term = _evaluation_term(session, version, policy.PRE_CANDIDATE_COMPLETE, "Candidate")
    if term:
        raise EvaluationRequiredError(term.message[0].upper() + term.message[1:] + ".")
    candidate = snapshot(version, evaluation)
    if not code_matches(candidate):
        raise CodeHashMismatchError(
            f"The latest evaluation of {version.label} does not belong to the code currently stored for it; "
            "the baseline cannot be established."
        )
    if (candidate.suite_hash, candidate.evaluator_config_hash, candidate.scoring_rule_version) != (
            commitment.suite_hash, commitment.evaluator_config_hash, commitment.scoring_rule_version):
        raise EvaluationNotComparableError(
            "The baseline was evaluated with a suite, evaluator configuration or scoring rule other than the "
            "committed one. Evaluate it again."
        )
    reason = f"{version.label} accepted as the baseline: complete evaluation, aggregate {candidate.overall_score:g}."
    return _commit_decision(session, version, execution, None, BASELINE, reason, (), candidate, None, commitment)


def _record_invalid(session, version, execution, previous_id, candidate, previous, failed) -> AcceptanceDecision:
    row = InvalidComparison(
        execution_id=execution.id,
        candidate_version_id=version.id,
        previous_best_version_id=previous_id,
        reasons=[t.as_dict() for t in failed],
        created_at=utcnow(),
    )
    session.add(row)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    reason = (f"{version.label} could not be compared (this is not a judgement of the revision): "
              + "; ".join(t.message for t in failed) + ".")[:MAX_REASON]
    return AcceptanceDecision(
        version=version, outcome=INVALID, reason=reason, failed_terms=tuple(failed), candidate=candidate,
        previous_best=previous, best_version_id=previous_id, decided_at=None, invalid_comparison_id=row.id,
    )


def _commit_decision(session, version, execution, previous_id, outcome, reason, failed_terms,
                     candidate, previous, commitment) -> AcceptanceDecision:
    accepted = outcome in (BASELINE, VALIDATED)
    now = utcnow()
    provenance = {
        "suite_hash": commitment.suite_hash,
        "evaluator_config_hash": commitment.evaluator_config_hash,
        "scoring_rule_version": commitment.scoring_rule_version,
        "delta": commitment.delta,
        "candidate_code_sha256": candidate.code_sha256,
        "previous_code_sha256": previous.code_sha256 if previous else None,
    }
    details = {
        "rule": f"scoring-rule-{commitment.scoring_rule_version}",
        "outcome": outcome,
        "baseline": outcome == BASELINE,
        "reason": reason,
        "failed_terms": [t.as_dict() for t in failed_terms],
        "candidate": scores(candidate),
        "previous_best": scores(previous) if previous else None,
        "provenance": provenance,
    }
    evidence_id = None
    try:
        changed = session.execute(
            update(Version)
            .where(Version.id == version.id, Version.acceptance_status == AcceptanceStatus.PENDING.value)
            .values(
                acceptance_status=(AcceptanceStatus.ACCEPTED if accepted else AcceptanceStatus.REJECTED).value,
                rejection_reason=None if accepted else reason,
                decided_at=now,
                decision_details=details,
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        # The pointer only moves on acceptance; on rejection the same guard proves the basis of the
        # comparison (the previous best) was still current when the decision was recorded.
        best_filter = Execution.best_version_id.is_(None) if previous_id is None else Execution.best_version_id == previous_id
        values = {"updated_at": now}
        if accepted:
            values["best_version_id"] = version.id
        moved = session.execute(
            update(Execution)
            .where(Execution.id == execution.id, best_filter)
            .values(**values)
            .execution_options(synchronize_session=False)
        ).rowcount
        if changed != 1 or moved != 1:
            session.rollback()
            raise ConflictError("A concurrent decision changed this execution; reload it and request the decision again.")
        if outcome != BASELINE:
            record = EvidenceRecord(
                execution_id=execution.id,
                candidate_version_id=version.id,
                previous_best_version_id=previous.version_id,
                candidate_evaluation_id=candidate.evaluation_id,
                previous_evaluation_id=previous.evaluation_id,
                status=outcome,
                failed_terms=[t.as_dict() for t in failed_terms],
                candidate_scores=scores(candidate),
                previous_scores=scores(previous),
                provenance=provenance,
                created_at=now,
            )
            session.add(record)
            session.flush()
            evidence_id = record.id
        session.commit()
    except ConflictError:
        raise
    except (OperationalError, IntegrityError) as exc:
        session.rollback()
        raise ConflictError("The decision could not be recorded because of a concurrent update; retry.") from exc
    except Exception:
        session.rollback()
        raise
    session.refresh(version)
    session.refresh(execution)
    return AcceptanceDecision(
        version=version, outcome=outcome, reason=reason, failed_terms=tuple(failed_terms), candidate=candidate,
        previous_best=previous, best_version_id=version.id if accepted else previous_id, decided_at=now,
        evidence_id=evidence_id,
    )


def list_evidence(session: Session, execution_id: str) -> tuple[list[EvidenceRecord], list[InvalidComparison]]:
    records = session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.execution_id == execution_id)
        .order_by(EvidenceRecord.created_at, EvidenceRecord.id)
    ).all()
    invalid = session.scalars(
        select(InvalidComparison).where(InvalidComparison.execution_id == execution_id)
        .order_by(InvalidComparison.created_at, InvalidComparison.id)
    ).all()
    return list(records), list(invalid)


def require_verified_improvement(session: Session, execution: Execution) -> None:
    """Guard for the proof stage: entering `zk_proof` needs a real, re-verified improvement.

    Stored flags are not trusted on their own. The best version must be an accepted REVISION with a
    validated_improvement evidence record, and the policy is re-applied (preconditions against the
    commitment, then the predicate with the committed delta) from the persisted evaluations of the
    baseline and the best version. Every accepted step is monotone and gains at least delta, so
    best-vs-baseline passes whenever the chain was legitimate."""
    session.refresh(execution)
    if execution.best_version_id is None:
        raise InvalidTransitionError("No accepted improvement: the execution has no best version.")
    commitment = commitment_of(execution)
    if commitment is None:
        raise InvalidTransitionError("No verified improvement: the execution has no recorded commitment.")
    best = session.get(Version, execution.best_version_id)
    if best is None or best.execution_id != execution.id:
        raise InvalidTransitionError("The recorded best version does not belong to this execution.")
    session.refresh(best)
    if best.acceptance_status != AcceptanceStatus.ACCEPTED.value:
        raise InvalidTransitionError("The recorded best version is not accepted.")
    if best.sequence < 2:
        raise InvalidTransitionError("No accepted improvement: the best version is the baseline.")
    evidence = session.scalar(select(EvidenceRecord).where(EvidenceRecord.candidate_version_id == best.id))
    if evidence is None or evidence.status != VALIDATED:
        raise InvalidTransitionError("No verified improvement: the best version has no validated_improvement evidence.")
    baseline = session.scalars(
        select(Version).where(Version.execution_id == execution.id, Version.sequence == 1)
    ).one_or_none()
    if baseline is None:
        raise InvalidTransitionError("No accepted improvement: the execution has no baseline version.")
    session.refresh(baseline)
    baseline_eval, t1 = _evaluation_term(session, baseline, policy.PRE_PREVIOUS_COMPLETE, "Baseline")
    best_eval, t2 = _evaluation_term(session, best, policy.PRE_CANDIDATE_COMPLETE, "Best version")
    if t1 or t2:
        raise InvalidTransitionError("No verified improvement: " + (t1 or t2).message + ".")
    base_snap, best_snap = snapshot(baseline, baseline_eval), snapshot(best, best_eval)
    failed = list(preconditions(commitment, base_snap, best_snap))
    if not failed:
        failed = list(compare(base_snap, best_snap, commitment.delta).failed_terms)
    if failed:
        raise InvalidTransitionError("No verified improvement over the baseline: "
                                     + "; ".join(t.message for t in failed) + ".")

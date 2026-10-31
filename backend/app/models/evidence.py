"""Typed evidence (PRD Section 5).

  validated_improvement  EvidenceRecord: passed every precondition and every predicate term
  rejected_attempt       EvidenceRecord: valid comparison, failed >= 1 predicate term (all recorded)
  invalid_comparison     InvalidComparison (separate table): the comparison could not validly occur.
                         It is NOT evidence about the revision, and it decides nothing.
  unvalidated_proposal   CriticFeedback (separate table): advisory only, never evidence.

An EvidenceRecord is written in the same transaction as the version's decision and the best-version
pointer update. Records never contain hidden test ids: only public ids and hidden counts.
"""
from datetime import datetime

from sqlalchemy import DDL, JSON, Boolean, CheckConstraint, ForeignKey, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, new_id, utcnow
from app.hashing import SHA256_SQL

EVIDENCE_STATUSES = ("validated_improvement", "rejected_attempt")


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    __table_args__ = (
        CheckConstraint("status IN ('validated_improvement', 'rejected_attempt')", name="ck_evidence_status"),
        # Accepted exactly when no predicate term failed.
        CheckConstraint(
            "(status = 'validated_improvement') = (json_array_length(failed_terms) = 0)",
            name="ck_evidence_failed_terms",
        ),
        UniqueConstraint("candidate_version_id", name="uq_evidence_candidate"),  # one decision per version
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"), index=True)
    candidate_version_id: Mapped[str] = mapped_column(ForeignKey("versions.id", ondelete="RESTRICT"))
    previous_best_version_id: Mapped[str] = mapped_column(ForeignKey("versions.id", ondelete="RESTRICT"))
    candidate_evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id", ondelete="RESTRICT"))
    previous_evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(32))
    failed_terms: Mapped[list[dict]] = mapped_column(JSON, default=list)  # [{"term", "message"}]
    candidate_scores: Mapped[dict] = mapped_column(JSON)
    previous_scores: Mapped[dict] = mapped_column(JSON)
    # suite/config/rule hashes and delta the decision was made under
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EvidenceBundle(Base):
    """A hidden-safe, hash-addressed export of one EvidenceRecord (local only; nothing is uploaded).

    `bundle_json` holds the exact canonical bytes (as text) that `bundle_sha256` was computed over.
    Rows are immutable: SQLite triggers (below) abort any UPDATE or DELETE. If the triggers are
    bypassed, recomputing the hash over `bundle_json` exposes the change."""

    __tablename__ = "evidence_bundles"
    __table_args__ = (
        UniqueConstraint("evidence_record_id", "include_code", name="uq_evidence_bundles_record_variant"),
        CheckConstraint(SHA256_SQL.format(col="bundle_sha256"), name="ck_evidence_bundles_sha256"),
        CheckConstraint("immutable = 1", name="ck_evidence_bundles_immutable"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_record_id: Mapped[str] = mapped_column(ForeignKey("evidence_records.id", ondelete="RESTRICT"), index=True)
    include_code: Mapped[bool] = mapped_column(Boolean)
    bundle_json: Mapped[str] = mapped_column(Text)
    bundle_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


for _op in ("UPDATE", "DELETE"):
    event.listen(
        EvidenceBundle.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER IF NOT EXISTS trg_evidence_bundles_no_{_op.lower()} BEFORE {_op} ON evidence_bundles "
            "BEGIN SELECT RAISE(ABORT, 'evidence bundles are immutable'); END"
        ),
    )


class InvalidComparison(Base):
    __tablename__ = "invalid_comparisons"
    __table_args__ = (
        CheckConstraint("json_array_length(reasons) >= 1", name="ck_invalid_comparisons_reasons"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"), index=True)
    candidate_version_id: Mapped[str] = mapped_column(ForeignKey("versions.id", ondelete="RESTRICT"), index=True)
    previous_best_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # may be corrupt
    reasons: Mapped[list[dict]] = mapped_column(JSON)  # [{"term", "message"}], failed preconditions
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

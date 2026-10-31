import enum
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, new_id, utcnow
from app.hashing import SHA256_SQL, code_sha256


def _default_code_sha256(context) -> str:
    """Column default for ORM/Core inserts that do not set the hash: computed from the inserted code."""
    return code_sha256(context.get_current_parameters()["code"])


class AcceptanceStatus(str, enum.Enum):
    PENDING = "pending"  # candidate exists, the evaluator-led decision has not been recorded yet
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Version(Base):
    __tablename__ = "versions"
    __table_args__ = (
        UniqueConstraint("execution_id", "sequence", name="uq_versions_execution_sequence"),
        CheckConstraint("sequence >= 1", name="ck_versions_sequence"),
        CheckConstraint("label = 'V' || CAST(sequence AS TEXT)", name="ck_versions_label"),
        CheckConstraint("acceptance_status IN ('pending', 'accepted', 'rejected')", name="ck_versions_acceptance"),
        CheckConstraint(
            "(acceptance_status = 'rejected' AND rejection_reason IS NOT NULL) OR "
            "(acceptance_status != 'rejected' AND rejection_reason IS NULL)",
            name="ck_versions_rejection_reason",
        ),
        CheckConstraint("parent_version_id IS NULL OR parent_version_id != id", name="ck_versions_not_own_parent"),
        CheckConstraint(SHA256_SQL.format(col="code_sha256"), name="ck_versions_code_sha256"),
        CheckConstraint(
            f"generator_prompt_sha256 IS NULL OR ({SHA256_SQL.format(col='generator_prompt_sha256')})",
            name="ck_versions_prompt_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(16))  # V1, V2, V3, ...
    code: Mapped[str] = mapped_column(Text)
    # SHA-256 of the UTF-8 code bytes, computed by the backend when the version is created. Every
    # evaluation records the hash of the code it ran; the gate refuses to compare mismatches.
    code_sha256: Mapped[str] = mapped_column(String(64), default=_default_code_sha256, index=True)
    generator_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    acceptance_status: Mapped[str] = mapped_column(
        String(16), default=AcceptanceStatus.PENDING.value, index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When and why the acceptance decision was made, with the numbers it was based on.
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    decision_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Generation metadata (Generator calls only; null for versions created another way).
    # generator_model_id above is the model id the API RETURNED, not only the one requested.
    generator_prompt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Deterministic changelog against the parent version, derived from the unified diff (no LLM).
    changelog: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    execution: Mapped["Execution"] = relationship(back_populates="versions", foreign_keys=[execution_id])  # noqa: F821
    evaluations: Mapped[list["Evaluation"]] = relationship(  # noqa: F821
        back_populates="version", order_by="Evaluation.created_at, Evaluation.id"
    )
    critic_feedback: Mapped[list["CriticFeedback"]] = relationship(  # noqa: F821
        back_populates="version", order_by="CriticFeedback.created_at, CriticFeedback.id"
    )

"""One row per LLM call attempt series (Generator or Critic), successful or not.

This is the partial record kept when the provider is down: a failed call is stored with its error code.
Prompts and replies are NOT stored here (the Generator's reply becomes a version; the Critic's reply
becomes critic_feedback); only their SHA-256, so a prompt can be matched without being kept twice.
The API key is never stored anywhere.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, new_id, utcnow
from app.hashing import SHA256_SQL


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint("role IN ('generator', 'critic')", name="ck_llm_calls_role"),
        CheckConstraint("outcome IN ('ok', 'error')", name="ck_llm_calls_outcome"),
        CheckConstraint("(outcome = 'error') = (error_code IS NOT NULL)", name="ck_llm_calls_error_iff_failed"),
        CheckConstraint(SHA256_SQL.format(col="prompt_sha256"), name="ck_llm_calls_prompt_sha256"),
        CheckConstraint("attempts >= 1", name="ck_llm_calls_attempts"),
        CheckConstraint("(error_class IS NULL) = (error_code IS NULL)", name="ck_llm_calls_error_class"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"), index=True)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("versions.id", ondelete="RESTRICT"), nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str] = mapped_column(String(32))  # execution status when the call was made
    requested_model: Mapped[str] = mapped_column(String(200))
    returned_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(8))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(100), nullable=True)  # exception class name only
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

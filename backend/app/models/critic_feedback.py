"""Stored Critic responses. Advisory only: this is not an evaluation result, and the
self-reported confidence is never an improvement metric."""
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, new_id, utcnow


class CriticFeedback(Base):
    __tablename__ = "critic_feedback"
    __table_args__ = (
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_critic_confidence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id", ondelete="RESTRICT"), index=True)
    # The model id the API returned (falls back to the requested id when the API reports none).
    critic_model_id: Mapped[str] = mapped_column(String(200))
    raw_feedback: Mapped[str] = mapped_column(Text)
    structured_feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    identified_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggested_changes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    version: Mapped["Version"] = relationship(back_populates="critic_feedback")  # noqa: F821

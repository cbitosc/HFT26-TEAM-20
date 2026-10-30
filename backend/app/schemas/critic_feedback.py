"""Critic feedback schemas. Advisory only; never an evaluation result."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CriticFeedbackInput(BaseModel):
    """Internal, service-level input (no public write endpoint exists in this milestone)."""

    model_config = ConfigDict(extra="forbid")

    critic_model_id: str = Field(min_length=1, max_length=200)
    raw_feedback: str = Field(min_length=1, max_length=200_000)
    structured_feedback: dict[str, Any] | None = None
    identified_issues: list[Any] | None = None
    suggested_changes: list[Any] | None = None
    # Self-reported by the model. Not evidence of correctness and never an improvement metric.
    confidence: float | None = Field(default=None, ge=0, le=1)


class CriticFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_id: str
    critic_model_id: str
    raw_feedback: str
    structured_feedback: dict[str, Any] | None
    identified_issues: list[Any] | None
    suggested_changes: list[Any] | None
    confidence: float | None
    created_at: datetime

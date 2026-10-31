from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.evaluation import suites

Requirement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class TaskCreate(BaseModel):
    # Unknown fields (for example a client-supplied `status`) are rejected, not ignored.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    requirements: list[Requirement] = Field(default_factory=list, max_length=50)
    language: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=64)
    # Chooses one of the backend's trusted suites. It cannot define tests, only select a known suite.
    evaluation_suite_id: str | None = Field(default=None, max_length=64)
    # Optional starting code for the Generator.
    starter_code: str | None = Field(default=None, max_length=50_000)

    @field_validator("language", "category", "evaluation_suite_id")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("evaluation_suite_id")
    @classmethod
    def _known_suite(cls, value: str | None) -> str | None:
        if value is not None and value not in suites.SUITES:
            raise ValueError(f"unknown evaluation suite; available: {', '.join(suites.suite_ids()) or 'none'}")
        return value


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    requirements: list[str]
    language: str | None
    category: str | None
    evaluation_suite_id: str | None
    starter_code: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

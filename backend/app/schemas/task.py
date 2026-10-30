from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Requirement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class TaskCreate(BaseModel):
    # Unknown fields (for example a client-supplied `status`) are rejected, not ignored.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    requirements: list[Requirement] = Field(default_factory=list, max_length=50)
    language: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=64)

    @field_validator("language", "category")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return value or None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    requirements: list[str]
    language: str | None
    category: str | None
    status: str
    created_at: datetime
    updated_at: datetime

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.evaluation import suites

Requirement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

MAX_TESTS_PER_PART = 100
LiteralStr = Annotated[str, StringConstraints(max_length=4000)]


class CheckUpload(BaseModel):
    """One check as data. `args` is a Python-literal tuple string (parsed with ast.literal_eval, never
    executed), for example '([(1, 3), (2, 6)],)'. `expected` is a literal string for `returns`, a
    built-in exception name for `raises`, a type name for `all_items_of_type`, and omitted otherwise."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["returns", "raises", "unchanged_input", "all_items_of_type"]
    args: LiteralStr
    expected: LiteralStr | None = None


class TestUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    checks: list[CheckUpload] = Field(min_length=1, max_length=20)


class ContractUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arity: int = Field(ge=0, le=10)
    smoke_args: LiteralStr
    smoke_type: str = Field(max_length=16)


class SuiteUpload(BaseModel):
    """A user-supplied suite as data. Public tests may be shown to agents and clients; hidden tests are
    sealed and only their count ever leaves the backend."""

    model_config = ConfigDict(extra="forbid")

    entrypoint: str = Field(min_length=1, max_length=64)
    language: str = Field(default="python", max_length=32)
    description: str = Field(default="", max_length=1000)
    contract: ContractUpload
    max_complexity: int = Field(default=10, ge=1, le=100)
    public_tests: list[TestUpload] = Field(min_length=1, max_length=MAX_TESTS_PER_PART)
    hidden_tests: list[TestUpload] = Field(min_length=1, max_length=MAX_TESTS_PER_PART)

    def to_upload_dict(self) -> dict:
        return {
            "entrypoint": self.entrypoint, "language": self.language, "description": self.description,
            "contract": {"arity": self.contract.arity, "smoke_args": self.contract.smoke_args,
                         "smoke_type": self.contract.smoke_type},
            "quality": {"max_complexity": self.max_complexity},
            "public_tests": [t.model_dump() for t in self.public_tests],
            "hidden_tests": [t.model_dump() for t in self.hidden_tests],
        }


class TaskCreate(BaseModel):
    # Unknown fields (for example a client-supplied `status`) are rejected, not ignored.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    requirements: list[Requirement] = Field(default_factory=list, max_length=50)
    language: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=64)
    # EITHER choose one of the backend's registered suites (cannot define tests, only select a known id)
    evaluation_suite_id: str | None = Field(default=None, max_length=64)
    # OR upload your own public and hidden tests as data (parsed as literals, never executed).
    suite: SuiteUpload | None = None
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

    @model_validator(mode="after")
    def _one_suite_source(self):
        if self.evaluation_suite_id and self.suite is not None:
            raise ValueError("provide either evaluation_suite_id or an inline suite, not both")
        if not self.evaluation_suite_id and self.suite is None:
            raise ValueError("a task needs a suite: set evaluation_suite_id, or upload public and hidden tests")
        return self


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
    # Counts and hashes of the task's suite (uploaded or registered). Never hidden test contents.
    suite: "SuiteSummary | None" = None


from app.schemas.dashboard import SuiteSummary  # noqa: E402  (avoids a circular import at module top)

TaskRead.model_rebuild()

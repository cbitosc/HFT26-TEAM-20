"""Evaluation schemas.

`EvaluationInput` is an internal, service-level input for the future evaluator. It is not
exposed as an API request body: clients cannot submit scores. The overall score is always
computed from the components (app.scoring), never accepted from the caller.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TestFailureDetail(BaseModel):
    __test__ = False  # not a pytest class

    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(min_length=1)
    expected: str | None = None
    actual: str | None = None
    exception: str | None = None
    traceback_excerpt: list[str] = Field(default_factory=list)


class OperationalMetricsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_time_seconds: float | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    api_cost_usd: float | None = Field(default=None, ge=0)
    api_cost_source: Literal["provider_reported", "estimated"] | None = None

    @model_validator(mode="after")
    def _cost_needs_source(self):
        if (self.api_cost_usd is None) != (self.api_cost_source is None):
            raise ValueError("api_cost_usd and api_cost_source must be provided together")
        return self


class EvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tests_passed: int = Field(ge=0)
    tests_total: int = Field(ge=1)
    correctness_score: float = Field(ge=0, le=100)
    code_quality_score: float = Field(ge=0, le=100)
    failure_details: list[TestFailureDetail] = Field(default_factory=list)
    operational: OperationalMetricsInput | None = None

    @model_validator(mode="after")
    def _passed_not_above_total(self):
        if self.tests_passed > self.tests_total:
            raise ValueError("tests_passed cannot exceed tests_total")
        return self


class DeterministicScores(BaseModel):
    tests_passed: int
    tests_total: int
    test_pass_rate: float
    correctness_score: float
    code_quality_score: float
    overall_score: float


class OperationalMetricsRead(BaseModel):
    execution_time_seconds: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    api_cost_usd: float | None
    api_cost_source: str | None


class EvaluationRead(BaseModel):
    id: str
    version_id: str
    created_at: datetime
    deterministic: DeterministicScores
    failure_details: list[TestFailureDetail]
    operational: OperationalMetricsRead | None

    @classmethod
    def from_model(cls, ev) -> "EvaluationRead":
        op = ev.operational
        return cls(
            id=ev.id,
            version_id=ev.version_id,
            created_at=ev.created_at,
            deterministic=DeterministicScores(
                tests_passed=ev.tests_passed,
                tests_total=ev.tests_total,
                test_pass_rate=ev.test_pass_rate,
                correctness_score=ev.correctness_score,
                code_quality_score=ev.code_quality_score,
                overall_score=ev.overall_score,
            ),
            failure_details=[TestFailureDetail(**d) for d in (ev.failure_details or [])],
            operational=None
            if op is None
            else OperationalMetricsRead(
                execution_time_seconds=op.execution_time_seconds,
                prompt_tokens=op.prompt_tokens,
                completion_tokens=op.completion_tokens,
                total_tokens=op.total_tokens,
                api_cost_usd=op.api_cost_usd,
                api_cost_source=op.api_cost_source,
            ),
        )

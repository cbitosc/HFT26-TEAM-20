"""Evaluation schemas.

`EvaluationInput` is an internal, service-level input produced by the evaluator. It is not exposed as
an API request body: clients cannot submit scores. The overall score is always computed from the
components (app.scoring), never accepted from the caller.

`EvaluationRead` is hidden-test safe: per-test outcomes and failure details are returned for PUBLIC
tests only. For hidden tests the API returns aggregate counts, never names, contents or per-test results.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.completeness import is_complete

Visibility = Literal["public", "hidden"]


class TestFailureDetail(BaseModel):
    __test__ = False  # not a pytest class
    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(min_length=1)
    visibility: Visibility = "hidden"  # unlabelled detail is treated as confidential
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


class TestOutcome(BaseModel):
    __test__ = False  # not a pytest class
    model_config = ConfigDict(extra="forbid")

    test_id: str = Field(min_length=1, max_length=64)
    visibility: Visibility = "hidden"
    passed: bool


class EvaluationInput(BaseModel):
    """Internal input, produced only by backend code (the evaluation engine). Never a request body.
    tests_passed / tests_total are HIDDEN-suite counts; public counts are separate."""

    model_config = ConfigDict(extra="forbid")

    tests_passed: int = Field(ge=0)
    tests_total: int = Field(ge=1)
    # SHA-256 of the code that was evaluated. None = the version's stored hash (internal callers only).
    code_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    public_tests_passed: int = Field(default=0, ge=0)
    public_tests_total: int = Field(default=0, ge=0)
    correctness_score: float = Field(ge=0, le=100)
    code_quality_score: float = Field(ge=0, le=100)
    failure_details: list[TestFailureDetail] = Field(default_factory=list)
    operational: OperationalMetricsInput | None = None
    # Provenance and per-test outcomes. All-or-nothing: an evaluation without them is "incomplete"
    # and cannot be used by the acceptance gate.
    suite_id: str | None = Field(default=None, max_length=64)
    suite_hash: str | None = Field(default=None, min_length=64, max_length=64)
    evaluator_version: str | None = Field(default=None, max_length=16)
    evaluator_config_hash: str | None = Field(default=None, min_length=64, max_length=64)
    scoring_rule_version: str | None = Field(default=None, max_length=16)
    provenance: dict = Field(default_factory=dict)
    test_results: list[TestOutcome] = Field(default_factory=list)
    score_breakdown: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self):
        if self.tests_passed > self.tests_total:
            raise ValueError("tests_passed cannot exceed tests_total")
        if self.public_tests_passed > self.public_tests_total:
            raise ValueError("public_tests_passed cannot exceed public_tests_total")
        provenance = (self.suite_id, self.suite_hash, self.evaluator_version, self.evaluator_config_hash,
                      self.scoring_rule_version)
        if any(p is None for p in provenance) != all(p is None for p in provenance):
            raise ValueError("suite_id, suite_hash, evaluator_version, evaluator_config_hash and "
                             "scoring_rule_version must be provided together")
        if (self.suite_id is None) != (not self.test_results):
            raise ValueError("test_results are required with suite provenance, and only then")
        if self.test_results:
            ids = [t.test_id for t in self.test_results]
            if len(set(ids)) != len(ids):
                raise ValueError("test_results contain a duplicate test id")
            hidden = [t for t in self.test_results if t.visibility == "hidden"]
            public = [t for t in self.test_results if t.visibility == "public"]
            if len(hidden) != self.tests_total or len(public) != self.public_tests_total:
                raise ValueError("test_results must contain exactly one outcome per hidden and public test")
            if sum(t.passed for t in hidden) != self.tests_passed:
                raise ValueError("tests_passed does not match the hidden test_results")
            if sum(t.passed for t in public) != self.public_tests_passed:
                raise ValueError("public_tests_passed does not match the public test_results")
        return self


class DeterministicScores(BaseModel):
    tests_passed: int  # hidden suite
    tests_total: int  # hidden suite
    test_pass_rate: float  # hidden suite; this is P in the score
    correctness_score: float
    code_quality_score: float
    overall_score: float


class PublicResults(BaseModel):
    tests_passed: int
    tests_total: int
    test_pass_rate: float | None  # None when the evaluation has no public tests


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
    code_sha256: str
    created_at: datetime
    deterministic: DeterministicScores
    public: PublicResults
    hidden_tests_failed: int
    failure_details: list[TestFailureDetail]  # public tests only
    operational: OperationalMetricsRead | None
    suite_id: str | None = None
    suite_hash: str | None = None
    evaluator_version: str | None = None
    evaluator_config_hash: str | None = None
    scoring_rule_version: str | None = None
    provenance: dict = Field(default_factory=dict)
    complete: bool = False  # usable by the acceptance gate
    test_results: list[TestOutcome] = Field(default_factory=list)  # public tests only
    score_breakdown: dict = Field(default_factory=dict)

    @classmethod
    def from_model(cls, ev) -> "EvaluationRead":
        op = ev.operational
        public_total = ev.public_tests_total or 0
        public_passed = ev.public_tests_passed or 0
        return cls(
            id=ev.id,
            version_id=ev.version_id,
            code_sha256=ev.code_sha256,
            created_at=ev.created_at,
            suite_id=ev.suite_id,
            suite_hash=ev.suite_hash,
            evaluator_version=ev.evaluator_version,
            evaluator_config_hash=ev.evaluator_config_hash,
            scoring_rule_version=ev.scoring_rule_version,
            provenance=ev.provenance or {},
            complete=is_complete(ev),
            test_results=[TestOutcome(**r) for r in (ev.test_results or []) if r.get("visibility") == "public"],
            score_breakdown=ev.score_breakdown or {},
            deterministic=DeterministicScores(
                tests_passed=ev.tests_passed,
                tests_total=ev.tests_total,
                test_pass_rate=ev.test_pass_rate,
                correctness_score=ev.correctness_score,
                code_quality_score=ev.code_quality_score,
                overall_score=ev.overall_score,
            ),
            public=PublicResults(
                tests_passed=public_passed,
                tests_total=public_total,
                test_pass_rate=public_passed / public_total * 100.0 if public_total else None,
            ),
            hidden_tests_failed=ev.tests_total - ev.tests_passed,
            failure_details=[TestFailureDetail(**d) for d in (ev.failure_details or [])
                             if d.get("visibility") == "public"],
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

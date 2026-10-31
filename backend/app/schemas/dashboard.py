"""Read-only, hidden-safe response models for the dashboard. Hidden tests appear only as counts;
no hidden test id, name, input or per-test result is ever present in any of these."""
from datetime import datetime

from pydantic import BaseModel

from app.schemas.acceptance import FailedTermRead


class SuiteSummary(BaseModel):
    id: str
    source: str  # "registered" or "uploaded"
    public_test_count: int
    hidden_test_count: int
    suite_hash: str
    public_suite_hash: str
    hidden_suite_hash: str


class TestCounts(BaseModel):
    passed: int
    total: int


class VersionNode(BaseModel):
    id: str
    label: str
    sequence: int
    parent_version_id: str | None
    acceptance_status: str
    decided: bool
    hidden: TestCounts | None  # None before the version is evaluated
    public: TestCounts | None
    overall_score: float | None
    failed_terms: list[FailedTermRead]
    generator_model_id: str | None
    generation_prompt_tokens: int | None
    generation_completion_tokens: int | None
    critic_note: str | None  # advisory only; the Critic never scores or approves
    critic_note_kind: str = "advisory"


class ExecutionTree(BaseModel):
    execution_id: str
    task_id: str
    task_title: str
    status: str
    stalled: bool
    best_version_id: str | None
    best_hidden_accuracy: float | None
    versions: list[VersionNode]


class ExecutionSummary(BaseModel):
    id: str
    task_id: str
    task_title: str
    status: str
    stalled: bool
    best_version_id: str | None
    best_hidden_accuracy: float | None  # hidden pass rate of the best version, or None
    created_at: datetime
    updated_at: datetime


class VersionDiff(BaseModel):
    version_id: str
    label: str
    against: str  # the version compared against (e.g. the parent's label)
    against_version_id: str | None
    unified_diff: str
    changelog: list[str]


class SystemStatus(BaseModel):
    featherless_configured: bool
    critic_configured: bool
    evaluator_mode: str  # "subprocess" (not a security sandbox) or "disabled"
    hidden_suite_encryption_available: bool
    publishing: str = "not available"

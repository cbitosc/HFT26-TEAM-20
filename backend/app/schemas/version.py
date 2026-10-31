from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    execution_id: str
    sequence: int
    label: str
    code: str
    code_sha256: str
    generator_model_id: str | None
    parent_version_id: str | None
    acceptance_status: str
    rejection_reason: str | None
    decided_at: datetime | None = None
    decision_details: dict | None = None
    generator_prompt_sha256: str | None = None
    generation_latency_seconds: float | None = None
    generation_prompt_tokens: int | None = None
    generation_completion_tokens: int | None = None
    changelog: list[str] = []
    created_at: datetime

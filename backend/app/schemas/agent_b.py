"""Agent B read/request schemas."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_agent_id: str
    destination_agent_id: str | None = None
    source_execution_id: str
    content: str
    task_category: str | None = None
    created_at: datetime


class AttestationRead(BaseModel):
    id: str
    experiment_id: str
    payload_sha256: str
    recomputed_sha256: str
    hash_valid: bool
    onchain: str
    created_at: datetime


class TransferExperimentRead(BaseModel):
    id: str
    source_agent_id: str
    destination_agent_id: str
    task_category: str | None = None
    base_task_id: str
    control_execution_id: str
    treatment_execution_id: str
    used_memory_ids: list[str]
    suite_hash: str | None = None
    metrics: dict[str, Any] | None = None
    created_at: datetime
    attestation: AttestationRead | None = None


class TransferExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_task_id: str = Field(min_length=1, max_length=64)
    # Start both runs immediately (needs the LLM). False just prepares the two queued executions.
    start: bool = False

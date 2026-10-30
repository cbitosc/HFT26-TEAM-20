from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    execution_id: str
    sequence: int
    label: str
    code: str
    generator_model_id: str | None
    parent_version_id: str | None
    acceptance_status: str
    rejection_reason: str | None
    created_at: datetime

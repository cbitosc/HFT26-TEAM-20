from datetime import datetime

from pydantic import BaseModel


class ExecutionError(BaseModel):
    code: str
    message: str
    stage: str  # the status the execution was in when it failed


class TransitionRead(BaseModel):
    from_status: str | None
    to_status: str
    occurred_at: datetime


class ExecutionRead(BaseModel):
    id: str
    task_id: str
    status: str
    max_revisions: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    best_version_id: str | None
    error: ExecutionError | None

    @classmethod
    def from_model(cls, ex) -> "ExecutionRead":
        error = (
            ExecutionError(code=ex.error_code, message=ex.error_message, stage=ex.error_stage)
            if ex.error_code is not None
            else None
        )
        return cls(
            id=ex.id,
            task_id=ex.task_id,
            status=ex.status,
            max_revisions=ex.max_revisions,
            created_at=ex.created_at,
            updated_at=ex.updated_at,
            started_at=ex.started_at,
            completed_at=ex.completed_at,
            best_version_id=ex.best_version_id,
            error=error,
        )


class ExecutionDetail(ExecutionRead):
    transitions: list[TransitionRead]

    @classmethod
    def from_model(cls, ex) -> "ExecutionDetail":
        base = ExecutionRead.from_model(ex).model_dump()
        transitions = [
            TransitionRead(from_status=t.from_status, to_status=t.to_status, occurred_at=t.occurred_at)
            for t in ex.transitions
        ]
        return cls(**base, transitions=transitions)

"""Agent B: cross-agent transfer experiments and their attestations (new tables).

A transfer experiment pairs a CONTROL execution (Agent B's suite, no injected memory) with a
TREATMENT execution (same suite, prior lessons injected into the task description the Generator
sees). The measured comparison is stored in `metrics`. An Attestation is a hash-addressed snapshot of
that result (local now; an on-chain copy is planned).
"""
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, new_id, utcnow


class TransferExperiment(Base):
    __tablename__ = "transfer_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_agent_id: Mapped[str] = mapped_column(String(64), default="agent-a")
    destination_agent_id: Mapped[str] = mapped_column(String(64), default="agent-b")
    task_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    base_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    control_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    treatment_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    control_execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"))
    treatment_execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"))
    used_memory_ids: Mapped[list] = mapped_column(JSON, default=list)
    suite_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Attestation(Base):
    __tablename__ = "attestations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("transfer_experiments.id", ondelete="RESTRICT"), index=True
    )
    payload_json: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64), index=True)
    onchain: Mapped[str] = mapped_column(String(16), default="planned")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

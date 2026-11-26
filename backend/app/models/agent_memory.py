"""Minimal structure for future cross-agent learning. No retrieval or matching exists yet."""
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, new_id, utcnow


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_agent_id: Mapped[str] = mapped_column(String(64), index=True)
    destination_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.id", ondelete="RESTRICT"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    task_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

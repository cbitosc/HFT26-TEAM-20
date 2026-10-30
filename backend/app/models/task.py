import enum
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, new_id, utcnow


class TaskStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_tasks_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.ACTIVE.value, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    executions: Mapped[list["Execution"]] = relationship(back_populates="task")  # noqa: F821

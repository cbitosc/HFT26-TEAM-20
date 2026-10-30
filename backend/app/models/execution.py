from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, new_id, utcnow
from app.lifecycle import (
    DEFAULT_MAX_REVISIONS,
    MAX_REVISIONS,
    MIN_REVISIONS,
    TERMINAL_STATUSES,
    ExecutionStatus,
    status_values,
)

_ALL = ", ".join(f"'{v}'" for v in status_values())
# Derived from the lifecycle so the database and the application can never disagree about
# which states are terminal.
_TERMINAL = ", ".join(f"'{s.value}'" for s in sorted(TERMINAL_STATUSES, key=lambda s: s.value))


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        CheckConstraint(f"status IN ({_ALL})", name="ck_executions_status"),
        # Error information exists exactly when the execution has failed.
        CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL AND error_message IS NOT NULL "
            "AND error_stage IS NOT NULL) OR "
            "(status != 'failed' AND error_code IS NULL AND error_message IS NULL AND error_stage IS NULL)",
            name="ck_executions_error_iff_failed",
        ),
        # completed_at is set exactly for terminal states.
        CheckConstraint(
            f"(completed_at IS NOT NULL) = (status IN ({_TERMINAL}))",
            name="ck_executions_completed_at_iff_terminal",
        ),
        # An execution that was never started can only be queued, failed or cancelled.
        CheckConstraint(
            "started_at IS NOT NULL OR status IN ('queued', 'failed', 'cancelled')",
            name="ck_executions_started_at",
        ),
        CheckConstraint(
            f"max_revisions BETWEEN {MIN_REVISIONS} AND {MAX_REVISIONS}", name="ck_executions_max_revisions"
        ),
        Index("ix_executions_task_id_created_at", "task_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=ExecutionStatus.QUEUED.value, index=True)
    # How many revision attempts (V2, V3) this execution may make. Decides when "no improvement"
    # is a legitimate conclusion; see execution_service.
    max_revisions: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_MAX_REVISIONS, server_default=str(DEFAULT_MAX_REVISIONS)
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Circular reference with versions; "same execution" and "accepted" are enforced in the service.
    best_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("versions.id", ondelete="SET NULL", use_alter=True, name="fk_executions_best_version"),
        nullable=True,
    )

    task: Mapped["Task"] = relationship(back_populates="executions")  # noqa: F821
    transitions: Mapped[list["ExecutionTransition"]] = relationship(
        back_populates="execution", order_by="ExecutionTransition.occurred_at, ExecutionTransition.id"
    )
    versions: Mapped[list["Version"]] = relationship(  # noqa: F821
        back_populates="execution",
        foreign_keys="Version.execution_id",
        order_by="Version.sequence",
    )


class ExecutionTransition(Base):
    """Append-only history of status changes (the first row has from_status NULL)."""

    __tablename__ = "execution_transitions"
    __table_args__ = (
        CheckConstraint(f"to_status IN ({_ALL})", name="ck_transitions_to_status"),
        CheckConstraint(f"from_status IS NULL OR from_status IN ({_ALL})", name="ck_transitions_from_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    execution: Mapped["Execution"] = relationship(back_populates="transitions")

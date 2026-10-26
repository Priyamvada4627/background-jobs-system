import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Text, DateTime, JSON, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    task_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="DEFAULT", nullable=False, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    result_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    attempts = relationship("JobAttempt", back_populates="job", cascade="all, delete-orphan", order_by="JobAttempt.attempt_number")
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan", order_by="JobEvent.created_at")
    outbox_events = relationship("OutboxEvent", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_jobs_status_priority_created", "status", "priority", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} task_type={self.task_type} status={self.status} priority={self.priority}>"

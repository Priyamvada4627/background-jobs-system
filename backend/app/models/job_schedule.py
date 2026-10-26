import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, DateTime, JSON, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class JobSchedule(Base, TimestampMixin):
    __tablename__ = "job_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_job_schedules_next_run_enabled", "next_run_at", "enabled"),
    )

    def __repr__(self) -> str:
        return f"<JobSchedule id={self.id} name={self.name} cron={self.cron_expression} enabled={self.enabled}>"

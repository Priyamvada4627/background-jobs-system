import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Worker(Base):
    __tablename__ = "workers"

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="ALIVE", nullable=False, index=True)
    current_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    capabilities_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("idx_workers_status_heartbeat", "status", "last_heartbeat_at"),
    )

    def __repr__(self) -> str:
        return f"<Worker id={self.worker_id} hostname={self.hostname} status={self.status}>"

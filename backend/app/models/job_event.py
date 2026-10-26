import uuid
from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy import BigInteger, Integer, String, DateTime, JSON, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    details_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), default="SYSTEM", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    job = relationship("Job", back_populates="events")

    __table_args__ = (
        Index("idx_job_events_job_id_created", "job_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<JobEvent id={self.id} job_id={self.job_id} type={self.event_type} actor={self.actor}>"

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
from app.services.state_machine import JobPriority, JobStatus
from app.schemas.common import PaginatedResponse


class JobCreate(BaseModel):
    task_type: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.]+$",
        description="Allowed task type identifier, e.g. send_email or generate_report",
        examples=["compute_hash"],
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON serializable arguments payload for the task handler",
    )
    priority: JobPriority = Field(
        default=JobPriority.DEFAULT,
        description="Job priority lane: HIGH, DEFAULT, or LOW",
    )
    idempotency_key: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional unique idempotency key to prevent duplicate job creation",
    )
    scheduled_at: Optional[datetime] = Field(
        None,
        description="Optional future execution timestamp in UTC. If omitted, job runs immediately.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=20,
        description="Maximum retry attempts allowed on failure (0 to 20)",
    )
    timeout_seconds: int = Field(
        default=300,
        ge=1,
        le=86400,
        description="Execution timeout in seconds (1s to 24h)",
    )


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_type: str
    payload_json: Dict[str, Any]
    status: str
    priority: str
    idempotency_key: Optional[str] = None
    scheduled_at: datetime
    max_retries: int
    attempt_count: int
    timeout_seconds: int
    result_json: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(PaginatedResponse[JobResponse]):
    pass

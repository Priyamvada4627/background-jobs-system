import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.services.state_machine import AttemptOutcome


class JobAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    attempt_number: int
    worker_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    outcome: str
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    traceback_text: Optional[str] = None
    duration_ms: Optional[int] = None

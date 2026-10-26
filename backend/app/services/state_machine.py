from enum import Enum
from typing import Dict, Set, Optional, Any
from datetime import datetime, timezone
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.job import Job
from app.models.job_event import JobEvent


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_WAIT = "RETRY_WAIT"
    DEAD = "DEAD"
    CANCELLED = "CANCELLED"
    RECOVERY_PENDING = "RECOVERY_PENDING"


class JobPriority(str, Enum):
    HIGH = "HIGH"
    DEFAULT = "DEFAULT"
    LOW = "LOW"


class AttemptOutcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"


# Finite State Machine valid transitions mapping
VALID_TRANSITIONS: Dict[JobStatus, Set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.SUCCEEDED,
        JobStatus.RETRY_WAIT,
        JobStatus.DEAD,
        JobStatus.CANCELLED,
        JobStatus.RECOVERY_PENDING,
    },
    JobStatus.RETRY_WAIT: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.RECOVERY_PENDING: {JobStatus.QUEUED, JobStatus.DEAD},
    JobStatus.DEAD: {JobStatus.QUEUED},  # Allowed only via manual operator retry
    JobStatus.SUCCEEDED: set(),          # Terminal state
    JobStatus.CANCELLED: set(),          # Terminal state
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal job lifecycle state transition is attempted."""
    def __init__(self, from_state: Any, to_state: Any, job_id: Optional[uuid.UUID] = None):
        self.from_state = from_state.value if isinstance(from_state, JobStatus) else str(from_state)
        self.to_state = to_state.value if isinstance(to_state, JobStatus) else str(to_state)
        self.job_id = job_id
        super().__init__(
            f"Invalid state transition for job {job_id or 'unknown'}: "
            f"cannot transition from '{self.from_state}' to '{self.to_state}'"
        )


def can_transition(from_state: str | JobStatus, to_state: str | JobStatus) -> bool:
    """Returns True if the transition is allowed according to the lifecycle state machine."""
    try:
        from_enum = JobStatus(from_state)
        to_enum = JobStatus(to_state)
    except ValueError:
        return False

    return to_enum in VALID_TRANSITIONS.get(from_enum, set())


def validate_transition(from_state: str | JobStatus, to_state: str | JobStatus, job_id: Optional[uuid.UUID] = None) -> None:
    """Validates the transition, raising InvalidStateTransitionError if illegal."""
    if not can_transition(from_state, to_state):
        raise InvalidStateTransitionError(from_state, to_state, job_id=job_id)



async def transition_job_status(
    db: AsyncSession,
    job: Job,
    new_status: str | JobStatus,
    actor: str = "SYSTEM",
    details: Optional[Dict[str, Any]] = None,
) -> Job:
    """
    Centrally validates and applies a state transition to a job within an active database session.
    Also emits an immutable JobEvent audit record within the same transaction.
    """
    to_enum = JobStatus(new_status)
    from_status = job.status

    validate_transition(from_status, to_enum, job_id=job.id)

    # Apply state change
    job.status = to_enum.value
    job.updated_at = datetime.now(timezone.utc)

    # Record audit event
    event = JobEvent(
        job_id=job.id,
        event_type=f"STATE_CHANGED_TO_{to_enum.value}",
        details_json={
            "from_state": from_status,
            "to_state": to_enum.value,
            **(details or {}),
        },
        actor=actor,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.flush()

    return job

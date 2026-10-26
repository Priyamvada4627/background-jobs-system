import pytest
import uuid
from app.services.state_machine import (
    JobStatus,
    VALID_TRANSITIONS,
    can_transition,
    validate_transition,
    InvalidStateTransitionError,
    transition_job_status,
)
from app.models.job import Job
from app.models.job_event import JobEvent


def test_valid_transitions_completeness():
    # Verify expected allowed transitions
    assert can_transition(JobStatus.QUEUED, JobStatus.RUNNING) is True
    assert can_transition(JobStatus.QUEUED, JobStatus.CANCELLED) is True

    assert can_transition(JobStatus.RUNNING, JobStatus.SUCCEEDED) is True
    assert can_transition(JobStatus.RUNNING, JobStatus.RETRY_WAIT) is True
    assert can_transition(JobStatus.RUNNING, JobStatus.DEAD) is True
    assert can_transition(JobStatus.RUNNING, JobStatus.CANCELLED) is True
    assert can_transition(JobStatus.RUNNING, JobStatus.RECOVERY_PENDING) is True

    assert can_transition(JobStatus.RETRY_WAIT, JobStatus.QUEUED) is True
    assert can_transition(JobStatus.RETRY_WAIT, JobStatus.CANCELLED) is True

    assert can_transition(JobStatus.RECOVERY_PENDING, JobStatus.QUEUED) is True
    assert can_transition(JobStatus.RECOVERY_PENDING, JobStatus.DEAD) is True

    assert can_transition(JobStatus.DEAD, JobStatus.QUEUED) is True


def test_invalid_transitions_rejected():
    # Terminal states cannot transition to anything
    assert can_transition(JobStatus.SUCCEEDED, JobStatus.RUNNING) is False
    assert can_transition(JobStatus.SUCCEEDED, JobStatus.QUEUED) is False
    assert can_transition(JobStatus.CANCELLED, JobStatus.RUNNING) is False
    assert can_transition(JobStatus.CANCELLED, JobStatus.QUEUED) is False

    # Cannot skip lifecycle phases directly
    assert can_transition(JobStatus.QUEUED, JobStatus.SUCCEEDED) is False
    assert can_transition(JobStatus.QUEUED, JobStatus.DEAD) is False
    assert can_transition(JobStatus.QUEUED, JobStatus.RETRY_WAIT) is False
    assert can_transition(JobStatus.DEAD, JobStatus.RUNNING) is False
    assert can_transition(JobStatus.DEAD, JobStatus.SUCCEEDED) is False

    # Unknown state strings
    assert can_transition("UNKNOWN_STATE", JobStatus.QUEUED) is False
    assert can_transition(JobStatus.QUEUED, "UNKNOWN_STATE") is False


def test_validate_transition_raises_error():
    job_id = uuid.uuid4()
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        validate_transition(JobStatus.SUCCEEDED, JobStatus.RUNNING, job_id=job_id)

    assert "cannot transition from 'SUCCEEDED' to 'RUNNING'" in str(exc_info.value)
    assert exc_info.value.from_state == "SUCCEEDED"
    assert exc_info.value.to_state == "RUNNING"
    assert exc_info.value.job_id == job_id


@pytest.mark.asyncio
async def test_transition_job_status_success(db_session):
    job = Job(
        id=uuid.uuid4(),
        task_type="test_task",
        payload_json={"key": "val"},
        status=JobStatus.QUEUED.value,
        priority="DEFAULT",
    )
    db_session.add(job)
    await db_session.flush()

    # Transition to RUNNING
    updated_job = await transition_job_status(
        db_session,
        job,
        JobStatus.RUNNING,
        actor="WORKER_1",
        details={"worker_id": "worker-123"},
    )

    assert updated_job.status == JobStatus.RUNNING.value

    # Check that audit JobEvent was added
    from sqlalchemy import select
    res = await db_session.execute(select(JobEvent).where(JobEvent.job_id == job.id))
    events = list(res.scalars().all())
    assert len(events) == 1
    assert events[0].event_type == "STATE_CHANGED_TO_RUNNING"
    assert events[0].actor == "WORKER_1"
    assert events[0].details_json["from_state"] == "QUEUED"
    assert events[0].details_json["to_state"] == "RUNNING"
    assert events[0].details_json["worker_id"] == "worker-123"


@pytest.mark.asyncio
async def test_transition_job_status_illegal_raises(db_session):
    job = Job(
        id=uuid.uuid4(),
        task_type="test_task",
        payload_json={},
        status=JobStatus.SUCCEEDED.value,
        priority="DEFAULT",
    )
    db_session.add(job)
    await db_session.flush()

    with pytest.raises(InvalidStateTransitionError):
        await transition_job_status(db_session, job, JobStatus.RUNNING)

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.models.job import Job
from app.models.job_attempt import JobAttempt
from app.models.job_event import JobEvent
from app.models.outbox_event import OutboxEvent
from app.schemas.job import JobCreate, JobPriority
from app.services.job_service import JobService
from app.services.state_machine import JobStatus
from app.workers.engine import WorkerEngine


@pytest.mark.asyncio
async def test_job_failure_retry_wait_backoff_delay(db_session: AsyncSession):
    """
    Verifies that a failing job whose attempt_count < max_retries transitions
    to RETRY_WAIT and has scheduled_at delayed into the future with an audit event.
    """
    now = datetime.now(timezone.utc)
    job, _ = await JobService.create_job(
        db_session,
        JobCreate(
            task_type="simulate_failure",
            payload={"error_type": "ValueError", "error_message": "Transient network issue"},
            max_retries=3,
        ),
    )

    worker = WorkerEngine(worker_id="test-retry-worker")
    await worker.register_worker(db_session)

    # Claim and execute
    claimed = await worker.claim_job(db_session)
    assert claimed is not None
    assert claimed.id == job.id

    attempt = await worker.execute_job(db_session, claimed)
    assert attempt.outcome == "FAILED"
    assert attempt.error_type == "ValueError"

    # Verify job state and backoff schedule
    await db_session.refresh(job)
    assert job.status == JobStatus.RETRY_WAIT.value
    assert job.attempt_count == 1
    assert "ValueError: Transient network issue" in job.last_error
    # scheduled_at must be delayed into the future (at least 1 second after execution)
    scheduled_utc = job.scheduled_at if job.scheduled_at.tzinfo else job.scheduled_at.replace(tzinfo=timezone.utc)
    assert scheduled_utc > now

    # Verify audit event recorded retry delay
    stmt = (
        select(JobEvent)
        .where(JobEvent.job_id == job.id, JobEvent.event_type == "JOB_RETRY_WAIT")
    )
    event = (await db_session.execute(stmt)).scalar_one()
    assert "retry_delay_seconds" in event.details_json
    assert event.details_json["retry_delay_seconds"] >= 1.0


@pytest.mark.asyncio
async def test_job_max_retries_transitions_to_dead(db_session: AsyncSession):
    """
    Verifies that once attempt_count reaches max_retries, the job transitions to DEAD (DLQ),
    stores full error traces, and records a JOB_DEAD audit event.
    """
    job, _ = await JobService.create_job(
        db_session,
        JobCreate(
            task_type="simulate_failure",
            payload={"error_type": "RuntimeError", "error_message": "Persistent failure"},
            max_retries=2,
        ),
    )

    worker = WorkerEngine(worker_id="test-dlq-worker")
    await worker.register_worker(db_session)

    # Execution 1 (attempt_count becomes 1 < 2 -> RETRY_WAIT)
    claimed1 = await worker.claim_job(db_session)
    await worker.execute_job(db_session, claimed1)
    await db_session.refresh(job)
    assert job.status == JobStatus.RETRY_WAIT.value
    assert job.attempt_count == 1

    # Manually reset status to QUEUED and scheduled_at to NOW for 2nd execution
    job.status = JobStatus.QUEUED.value
    job.scheduled_at = datetime.now(timezone.utc)
    await db_session.commit()

    # Execution 2 (attempt_count becomes 2 >= 2 -> DEAD)
    claimed2 = await worker.claim_job(db_session)
    attempt2 = await worker.execute_job(db_session, claimed2)
    assert attempt2.outcome == "FAILED"
    assert attempt2.traceback_text is not None
    assert "RuntimeError: Persistent failure" in attempt2.traceback_text

    await db_session.refresh(job)
    assert job.status == JobStatus.DEAD.value
    assert job.attempt_count == 2
    assert "RuntimeError: Persistent failure" in job.last_error

    # Verify audit event
    stmt = select(JobEvent).where(JobEvent.job_id == job.id, JobEvent.event_type == "JOB_DEAD")
    dead_event = (await db_session.execute(stmt)).scalar_one()
    assert dead_event.details_json["attempt_number"] == 2


@pytest.mark.asyncio
async def test_manual_retry_dead_job_api_success(async_client: AsyncClient, db_session: AsyncSession):
    """
    Verifies that calling POST /jobs/{job_id}/retry on a DEAD job successfully revives it:
    - Status transitions back to QUEUED
    - scheduled_at set to NOW()
    - attempt_count reset to 0 and last_error cleared
    - Emits an outbox event (event_type=JOB_RETRIED) for queue re-publishing
    - Records an audit event with actor='OPERATOR'
    """
    # 1. Create a job and transition it directly to DEAD
    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        task_type="compute_hash",
        payload_json={"data": "retry-target"},
        status=JobStatus.DEAD.value,
        priority="HIGH",
        scheduled_at=now - timedelta(hours=1),
        max_retries=3,
        attempt_count=3,
        last_error="Simulated fatal error",
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )
    db_session.add(job)
    await db_session.commit()

    # 2. Call POST /jobs/{job_id}/retry
    res = await async_client.post(f"/jobs/{job_id}/retry")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(job_id)
    assert data["status"] == "QUEUED"
    assert data["attempt_count"] == 0
    assert data["last_error"] is None

    # 3. Verify PostgreSQL outbox event was created for publishing
    stmt_out = select(OutboxEvent).where(OutboxEvent.job_id == job_id, OutboxEvent.event_type == "JOB_RETRIED")
    outbox_ev = (await db_session.execute(stmt_out)).scalar_one_or_none()
    assert outbox_ev is not None
    assert outbox_ev.payload_json["priority"] == "HIGH"
    assert outbox_ev.published_at is None

    # 4. Verify audit trail in job_events
    stmt_audit = select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.actor == "OPERATOR")
    audit_ev = (await db_session.execute(stmt_audit)).scalar_one_or_none()
    assert audit_ev is not None
    assert audit_ev.details_json["from_state"] == "DEAD"
    assert audit_ev.details_json["to_state"] == "QUEUED"
    assert audit_ev.details_json["reason"] == "MANUAL_RETRY"


@pytest.mark.asyncio
async def test_manual_retry_non_dead_job_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies that calling POST /jobs/{id}/retry on a job NOT in DEAD state returns HTTP 400."""
    job, _ = await JobService.create_job(
        db_session,
        JobCreate(task_type="compute_hash", payload={"data": "active"}),
    )
    assert job.status == "QUEUED"

    # Attempt retry on QUEUED job
    res = await async_client.post(f"/jobs/{job.id}/retry")
    assert res.status_code == 400
    assert "Invalid state transition" in res.json()["detail"]


@pytest.mark.asyncio
async def test_manual_retry_nonexistent_job_returns_404(async_client: AsyncClient):
    """Verifies that calling POST /jobs/{id}/retry for a non-existent ID returns HTTP 404."""
    random_id = uuid.uuid4()
    res = await async_client.post(f"/jobs/{random_id}/retry")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

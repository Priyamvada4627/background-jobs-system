import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from app.models.job import Job
from app.models.job_attempt import JobAttempt
from app.models.job_event import JobEvent
from app.models.worker import Worker
from app.workers.engine import WorkerEngine
from app.services.state_machine import JobStatus


@pytest.mark.asyncio
async def test_worker_registration(test_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    worker = WorkerEngine(worker_id="test-worker-alpha", session_factory=factory)

    await worker.register_worker(db_session)

    res = await db_session.execute(select(Worker).where(Worker.worker_id == "test-worker-alpha"))
    record = res.scalar_one_or_none()
    assert record is not None
    assert record.status == "ALIVE"
    assert "compute_hash" in record.capabilities_json
    assert record.pid == worker.pid


@pytest.mark.asyncio
async def test_worker_claims_highest_priority_job(test_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    worker = WorkerEngine(worker_id="test-worker-priority", session_factory=factory)
    await worker.register_worker(db_session)

    now = datetime.now(timezone.utc)
    low_job = Job(id=uuid.uuid4(), task_type="compute_hash", status="QUEUED", priority="LOW", scheduled_at=now)
    high_job = Job(id=uuid.uuid4(), task_type="compute_hash", status="QUEUED", priority="HIGH", scheduled_at=now)
    default_job = Job(id=uuid.uuid4(), task_type="compute_hash", status="QUEUED", priority="DEFAULT", scheduled_at=now)

    db_session.add_all([low_job, default_job, high_job])
    await db_session.commit()

    # Claim job: HIGH priority job must be claimed first
    claimed = await worker.claim_job(db_session)
    assert claimed is not None
    assert claimed.id == high_job.id
    assert claimed.priority == "HIGH"
    assert claimed.status == "RUNNING"
    assert claimed.attempt_count == 1


@pytest.mark.asyncio
async def test_worker_executes_job_successfully(test_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    worker = WorkerEngine(worker_id="test-worker-exec", session_factory=factory)

    # Insert a queued job
    job = Job(
        id=uuid.uuid4(),
        task_type="compute_hash",
        payload_json={"data": "hello test world"},
        status="QUEUED",
        priority="DEFAULT",
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    # Worker executes cycle
    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.outcome == "SUCCEEDED"
    assert attempt.duration_ms is not None
    assert attempt.worker_id == "test-worker-exec"

    # Verify job state in DB
    await db_session.refresh(job)
    assert job.status == "SUCCEEDED"
    assert job.attempt_count == 1
    assert "hash" in job.result_json

    # Verify JobEvent audit
    res = await db_session.execute(
        select(JobEvent).where(JobEvent.job_id == job.id, JobEvent.event_type == "JOB_SUCCEEDED")
    )
    assert res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_worker_executes_failing_job_retry_wait(test_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    worker = WorkerEngine(worker_id="test-worker-fail", session_factory=factory)

    # Job with max_retries = 3 (should go to RETRY_WAIT on attempt 1)
    job = Job(
        id=uuid.uuid4(),
        task_type="simulate_failure",
        payload_json={"error_message": "transient network glitch"},
        status="QUEUED",
        priority="DEFAULT",
        max_retries=3,
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.outcome == "FAILED"
    assert attempt.error_type == "ValueError"
    assert "transient network glitch" in attempt.error_message
    assert attempt.traceback_text is not None

    # Job should be in RETRY_WAIT
    await db_session.refresh(job)
    assert job.status == "RETRY_WAIT"
    assert job.attempt_count == 1
    assert "ValueError: transient network glitch" in job.last_error


@pytest.mark.asyncio
async def test_worker_executes_failing_job_dead(test_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    worker = WorkerEngine(worker_id="test-worker-dead", session_factory=factory)

    # Job with max_retries = 1 (should transition to DEAD immediately on attempt 1)
    job = Job(
        id=uuid.uuid4(),
        task_type="simulate_failure",
        payload_json={"error_message": "fatal unrecoverable issue"},
        status="QUEUED",
        priority="DEFAULT",
        max_retries=1,
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.outcome == "FAILED"

    # Job should be DEAD
    await db_session.refresh(job)
    assert job.status == "DEAD"
    assert job.attempt_count == 1


@pytest.mark.asyncio
async def test_worker_handles_timeout(test_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    worker = WorkerEngine(worker_id="test-worker-timeout", session_factory=factory)

    # Job sleeps for 1.2 seconds with a 1 second timeout
    job = Job(
        id=uuid.uuid4(),
        task_type="sleep_task",
        payload_json={"duration_seconds": 1.2},
        timeout_seconds=1,
        max_retries=1,
        status="QUEUED",
        priority="DEFAULT",
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.outcome == "TIMED_OUT"
    assert attempt.error_type == "TimeoutError"

    await db_session.refresh(job)
    assert job.status == "DEAD"


@pytest.mark.asyncio
async def test_worker_handles_unregistered_task(test_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    worker = WorkerEngine(worker_id="test-worker-unreg", session_factory=factory)

    # Inject an unregistered task type
    job = Job(
        id=uuid.uuid4(),
        task_type="non_existent_arbitrary_task",
        payload_json={},
        status="QUEUED",
        priority="DEFAULT",
        max_retries=3,
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.outcome == "FAILED"
    assert attempt.error_type == "UnregisteredTaskError"

    # Unregistered tasks should fail immediately into DEAD to avoid retry loops
    await db_session.refresh(job)
    assert job.status == "DEAD"



@pytest.mark.asyncio
async def test_api_submission_not_executed_inline(async_client, test_engine, db_session):
    """
    Demonstrates that the API process accepts and queues the job,
    and does NOT execute it inline. Only the worker executes it.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Client submits job to API
    res = await async_client.post(
        "/jobs",
        json={"task_type": "compute_hash", "payload": {"data": "async decoupling proof"}},
    )
    assert res.status_code == 201
    job_id = uuid.UUID(res.json()["id"])
    assert res.json()["status"] == "QUEUED"

    # 2. Verify job is strictly in QUEUED state in DB (API did not run it inline)
    db_job = await db_session.get(Job, job_id)
    assert db_job.status == "QUEUED"
    assert db_job.attempt_count == 0
    assert db_job.result_json is None

    # 3. Independent worker process runs
    worker = WorkerEngine(worker_id="background-worker-1", session_factory=factory)
    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.job_id == job_id
    assert attempt.outcome == "SUCCEEDED"

    # 4. Now verify job transitioned to SUCCEEDED and result is available
    await db_session.refresh(db_job)
    assert db_job.status == "SUCCEEDED"
    assert db_job.attempt_count == 1
    assert "hash" in db_job.result_json

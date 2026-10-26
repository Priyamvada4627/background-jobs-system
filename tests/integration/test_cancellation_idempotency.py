import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from httpx import AsyncClient

from app.models.job import Job
from app.models.job_event import JobEvent
from app.models.job_attempt import JobAttempt
from app.schemas.job import JobCreate, JobPriority
from app.services.job_service import JobService
from app.services.state_machine import JobStatus
from app.queue.redis_queue import RedisQueue
from app.workers.engine import WorkerEngine


@pytest.mark.asyncio
async def test_job_submission_idempotency_returns_original(async_client: AsyncClient, db_session: AsyncSession):
    """
    Verifies that submitting identical requests with the same idempotency_key returns
    HTTP 201 on first call and HTTP 200 on subsequent calls with the identical job ID.
    """
    idemp_key = f"idemp-key-{uuid.uuid4().hex}"
    payload = {
        "task_type": "compute_hash",
        "payload": {"data": "idempotent-data"},
        "idempotency_key": idemp_key,
        "priority": "HIGH",
    }

    # 1. First submission
    res1 = await async_client.post("/jobs", json=payload)
    assert res1.status_code == 201
    job1_id = res1.json()["id"]

    # 2. Second submission with same idempotency key
    res2 = await async_client.post("/jobs", json=payload)
    assert res2.status_code == 200
    job2_id = res2.json()["id"]

    # Both responses reference the same job record
    assert job1_id == job2_id

    # Verify only 1 record in database
    stmt = select(Job).where(Job.idempotency_key == idemp_key)
    jobs = (await db_session.execute(stmt)).scalars().all()
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_cancel_queued_job_api_success(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies that calling POST /jobs/{id}/cancel on a QUEUED job transitions it immediately to CANCELLED."""
    job, _ = await JobService.create_job(
        db_session,
        JobCreate(task_type="compute_hash", payload={"data": "cancel-me"}),
    )
    job_id = job.id
    assert job.status == "QUEUED"

    res = await async_client.post(f"/jobs/{job_id}/cancel")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CANCELLED"

    # Verify in DB
    await db_session.refresh(job)
    assert job.status == "CANCELLED"

    # Verify audit event
    stmt = select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.event_type == "JOB_CANCELLED")
    audit_ev = (await db_session.execute(stmt)).scalar_one_or_none()
    assert audit_ev is not None
    assert audit_ev.actor == "CLIENT"


@pytest.mark.asyncio
async def test_cancel_running_job_cooperative(test_engine, fake_redis):
    """
    Verifies that cancelling a RUNNING job:
      1. Sets the cooperative cancellation flag in Redis.
      2. The executing worker detects the cancellation flag.
      3. The attempt finishes with outcome CANCELLED and job status is CANCELLED.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)

    # 1. Create a job and enqueue to Redis
    async with session_factory() as session:
        job, _ = await JobService.create_job(
            session,
            JobCreate(task_type="sleep_task", payload={"duration_seconds": 0.05}),
        )
        job_id = job.id
        await redis_queue.enqueue(job_id, priority="DEFAULT")

    # 2. Worker claims job (becomes RUNNING)
    worker = WorkerEngine(worker_id="worker-canceller", session_factory=session_factory, redis_queue=redis_queue)
    async with session_factory() as session:
        await worker.register_worker(session)
        claimed = await worker.claim_job(session)
        assert claimed is not None
        assert claimed.status == "RUNNING"

    # 3. Client cancels the running job
    async with session_factory() as session:
        await JobService.cancel_job(session, job_id, redis_queue=redis_queue)

    # Verify Redis cancellation flag is set
    assert await redis_queue.is_cancelled(job_id) is True

    # 4. Worker executes and checks cancellation
    async with session_factory() as session:
        attempt = await worker.execute_job(session, claimed)
        assert attempt.outcome == "CANCELLED"

        stmt = select(Job).where(Job.id == job_id)
        final_job = (await session.execute(stmt)).scalar_one()
        assert final_job.status == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_terminal_job_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies that attempting to cancel a job in SUCCEEDED or DEAD state returns HTTP 400."""
    now = datetime.now(timezone.utc)
    job = Job(
        id=uuid.uuid4(),
        task_type="compute_hash",
        payload_json={"data": "terminal"},
        status="SUCCEEDED",
        priority="DEFAULT",
        scheduled_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(job)
    await db_session.commit()

    res = await async_client.post(f"/jobs/{job.id}/cancel")
    assert res.status_code == 400
    assert "Cannot cancel job in terminal state" in res.json()["detail"]

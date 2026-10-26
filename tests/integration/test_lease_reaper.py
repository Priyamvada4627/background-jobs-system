import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.job import Job
from app.models.worker import Worker
from app.models.job_event import JobEvent
from app.models.job_attempt import JobAttempt
from app.schemas.job import JobCreate, JobPriority
from app.services.job_service import JobService
from app.services.state_machine import JobStatus
from app.queue.redis_queue import RedisQueue
from app.workers.engine import WorkerEngine
from app.services.lease_reaper import LeaseReaper


@pytest.mark.asyncio
async def test_lease_reaper_recovers_abandoned_job(test_engine, fake_redis):
    """
    Verifies that when a worker crashes and its Redis lease expires:
      1. LeaseReaper detects the missing lease for a RUNNING job.
      2. It transitions the job back to QUEUED and pushes it back to Redis.
      3. Another worker can pick up the recovered job and execute it to SUCCEEDED.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)

    # 1. Create a job and enqueue to Redis
    async with session_factory() as session:
        job, _ = await JobService.create_job(
            session,
            JobCreate(task_type="compute_hash", payload={"data": "reap-recovery"}, max_retries=3),
        )
        job_id = job.id
        await redis_queue.enqueue(job_id, priority="DEFAULT")

    # 2. Worker 1 claims the job
    worker1 = WorkerEngine(worker_id="worker-crash-victim", session_factory=session_factory, redis_queue=redis_queue)
    async with session_factory() as session:
        await worker1.register_worker(session)
        claimed_job = await worker1.claim_job(session)
        assert claimed_job is not None
        assert claimed_job.status == "RUNNING"

    # Verify lease is active in Redis
    owner = await redis_queue.get_lease_owner(job_id)
    assert owner == "worker-crash-victim"

    # 3. Simulate Worker 1 crash: lease expires in Redis
    await redis_queue.release_lease(job_id)
    assert await redis_queue.get_lease_owner(job_id) is None

    # 4. Run LeaseReaper
    reaper = LeaseReaper(session_factory=session_factory, redis_queue=redis_queue)
    async with session_factory() as session:
        reaped_count = await reaper.reap_abandoned_jobs(session)
        assert reaped_count == 1

        # Check job status is now QUEUED in PostgreSQL
        stmt = select(Job).where(Job.id == job_id)
        reaped_job = (await session.execute(stmt)).scalar_one()
        assert reaped_job.status == "QUEUED"
        assert "Lease expired" in reaped_job.last_error

    # Verify job is back in Redis ready queue
    depths = await redis_queue.get_all_queue_depths()
    assert depths["TOTAL"] == 1

    # 5. Worker 2 picks up the job and finishes it
    worker2 = WorkerEngine(worker_id="worker-healthy-survivor", session_factory=session_factory, redis_queue=redis_queue)
    attempt = await worker2.run_once()
    assert attempt is not None
    assert attempt.job_id == job_id
    assert attempt.outcome == "SUCCEEDED"

    async with session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        final_job = (await session.execute(stmt)).scalar_one()
        assert final_job.status == "SUCCEEDED"
        assert final_job.attempt_count == 2


@pytest.mark.asyncio
async def test_zombie_worker_fenced_out(test_engine, fake_redis):
    """
    Simulates a split-brain / zombie scenario:
      1. Worker 1 claims Job (attempt 1).
      2. Network partition occurs; lease expires; Reaper requeues the job.
      3. Worker 2 claims Job (attempt 2) and finishes successfully.
      4. Zombie Worker 1 awakens and tries to commit attempt 1.
      5. Fencing token check blocks Worker 1 from overwriting Worker 2's SUCCEEDED state.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)

    # Create job and enqueue
    async with session_factory() as session:
        job, _ = await JobService.create_job(
            session,
            JobCreate(task_type="compute_hash", payload={"data": "zombie-test"}, max_retries=3),
        )
        job_id = job.id
        await redis_queue.enqueue(job_id, priority="HIGH")

    # Worker 1 claims job
    worker1 = WorkerEngine(worker_id="worker-zombie-1", session_factory=session_factory, redis_queue=redis_queue)
    async with session_factory() as session:
        await worker1.register_worker(session)
        job_worker1 = await worker1.claim_job(session)
        assert job_worker1.attempt_count == 1

    # Worker 1's lease expires while it is "frozen"
    await redis_queue.release_lease(job_id)

    # Reaper recovers job
    reaper = LeaseReaper(session_factory=session_factory, redis_queue=redis_queue)
    async with session_factory() as session:
        await reaper.reap_abandoned_jobs(session)

    # Worker 2 claims and successfully completes attempt 2
    worker2 = WorkerEngine(worker_id="worker-legit-2", session_factory=session_factory, redis_queue=redis_queue)
    attempt2 = await worker2.run_once()
    assert attempt2 is not None
    assert attempt2.worker_id == "worker-legit-2"

    async with session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        curr_job = (await session.execute(stmt)).scalar_one()
        assert curr_job.status == "SUCCEEDED"
        assert curr_job.attempt_count == 2

    # Now zombie Worker 1 awakens and tries to execute its stale job
    async with session_factory() as session:
        zombie_attempt = await worker1.execute_job(session, job_worker1)

    # Fencing check kicked in! Verify:
    # 1. Job status is STILL SUCCEEDED (not corrupted by zombie)
    # 2. Audit trail records ZOMBIE_WORKER_FENCED_OUT
    async with session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        final_job = (await session.execute(stmt)).scalar_one()
        assert final_job.status == "SUCCEEDED"
        assert final_job.attempt_count == 2

        stmt_ev = select(JobEvent).where(
            JobEvent.job_id == job_id,
            JobEvent.event_type == "ZOMBIE_WORKER_FENCED_OUT",
        )
        fenced_event = (await session.execute(stmt_ev)).scalar_one_or_none()
        assert fenced_event is not None
        assert fenced_event.actor == "worker-zombie-1"


@pytest.mark.asyncio
async def test_lease_reaper_exhausted_retries_moves_to_dead(test_engine, fake_redis):
    """Verifies that if an abandoned job has reached max_retries, Reaper moves it to DEAD (DLQ)."""
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)

    async with session_factory() as session:
        job, _ = await JobService.create_job(
            session,
            JobCreate(task_type="compute_hash", payload={"data": "dead-reap"}, max_retries=1),
        )
        job_id = job.id
        await redis_queue.enqueue(job_id, priority="DEFAULT")

    worker = WorkerEngine(worker_id="worker-one-shot", session_factory=session_factory, redis_queue=redis_queue)
    async with session_factory() as session:
        await worker.register_worker(session)
        await worker.claim_job(session)

    # Lease expires
    await redis_queue.release_lease(job_id)

    # Reaper runs
    reaper = LeaseReaper(session_factory=session_factory, redis_queue=redis_queue)
    async with session_factory() as session:
        await reaper.reap_abandoned_jobs(session)

        stmt = select(Job).where(Job.id == job_id)
        dead_job = (await session.execute(stmt)).scalar_one()
        assert dead_job.status == "DEAD"
        assert "max retries (1) exhausted" in dead_job.last_error

        stmt_ev = select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.event_type == "JOB_REAPED_DEAD")
        assert (await session.execute(stmt_ev)).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_reap_dead_workers(test_engine, fake_redis):
    """Verifies that workers whose heartbeat timestamp has lapsed are marked DEAD."""
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        w_alive = Worker(
            worker_id="worker-active-1",
            hostname="host",
            pid=1001,
            started_at=now,
            last_heartbeat_at=now,
            status="ALIVE",
        )
        w_dead = Worker(
            worker_id="worker-ghost-2",
            hostname="host",
            pid=1002,
            started_at=now - timedelta(minutes=10),
            last_heartbeat_at=now - timedelta(minutes=5),  # 5 minutes ago
            status="ALIVE",
        )
        session.add(w_alive)
        session.add(w_dead)
        await session.commit()

    reaper = LeaseReaper(session_factory=session_factory, redis_queue=RedisQueue(client=fake_redis))
    async with session_factory() as session:
        dead_count = await reaper.reap_dead_workers(session, heartbeat_timeout_seconds=60.0)
        assert dead_count == 1

        res = await session.execute(select(Worker).where(Worker.worker_id == "worker-ghost-2"))
        assert res.scalar_one().status == "DEAD"

        res_alive = await session.execute(select(Worker).where(Worker.worker_id == "worker-active-1"))
        assert res_alive.scalar_one().status == "ALIVE"

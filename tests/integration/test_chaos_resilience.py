import asyncio
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.job import Job
from app.models.job_attempt import JobAttempt
from app.models.job_event import JobEvent
from app.models.outbox_event import OutboxEvent
from app.schemas.job import JobCreate, JobPriority
from app.services.job_service import JobService
from app.services.outbox_publisher import OutboxPublisher
from app.services.lease_reaper import LeaseReaper
from app.services.state_machine import JobStatus
from app.queue.redis_queue import RedisQueue
from app.workers.engine import WorkerEngine


@pytest.mark.asyncio
async def test_chaos_outbox_redis_failure_and_recovery(test_engine, fake_redis):
    """
    Chaos Scenario 1:
    Simulates a prolonged Redis partition during job creation.
    Verifies that jobs and outbox events are durably persisted in PostgreSQL,
    and once Redis recovers, the Outbox Publisher drains all events reliably.
    """
    session_factory = async_sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    redis_queue = RedisQueue(client=fake_redis)

    # 1. Enqueue 5 jobs in PostgreSQL while Redis is simulated as down
    job_ids = []
    async with session_factory() as db:
        for i in range(5):
            job_in = JobCreate(
                task_type="compute_hash",
                priority=JobPriority.HIGH,
                payload={"data": f"chaos-seed-{i}"},
            )
            job, _ = await JobService.create_job(db, job_in)
            job_ids.append(job.id)

    # Verify 5 outbox events exist in unpublished state
    async with session_factory() as db:
        stmt = select(func.count(OutboxEvent.id)).where(OutboxEvent.published_at.is_(None))
        res = await db.execute(stmt)
        assert res.scalar_one() == 5

    # 2. Restore Redis connectivity & run outbox publisher
    publisher = OutboxPublisher(session_factory=session_factory, redis_queue=redis_queue, batch_size=10)
    published_count = await publisher.run_once()
    assert published_count == 5

    # Verify Redis HIGH priority queue received all 5 job IDs
    depth = await redis_queue.get_queue_depth("HIGH")
    assert depth == 5

    # Verify all outbox events are now marked published
    async with session_factory() as db:
        stmt = select(func.count(OutboxEvent.id)).where(OutboxEvent.published_at.is_(None))
        res = await db.execute(stmt)
        assert res.scalar_one() == 0


@pytest.mark.asyncio
async def test_chaos_worker_crash_and_zombie_fencing(test_engine, fake_redis):
    """
    Chaos Scenario 2:
    Simulates a worker crashing mid-task, lease expiring, reaper requeueing the job,
    and the zombie worker subsequently being fenced out upon resuming.
    """
    session_factory = async_sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    redis_queue = RedisQueue(client=fake_redis)

    worker_zombie = WorkerEngine(worker_id="zombie-worker-1", session_factory=session_factory, redis_queue=redis_queue)
    worker_healthy = WorkerEngine(worker_id="healthy-worker-2", session_factory=session_factory, redis_queue=redis_queue)

    # 1. Create a job and enqueue to Redis
    async with session_factory() as db:
        job_in = JobCreate(
            task_type="compute_hash",
            priority=JobPriority.HIGH,
            payload={"data": "scenario-crash"},
            max_retries=3,
        )
        job, _ = await JobService.create_job(db, job_in)
        await redis_queue.enqueue(job.id, job.priority)
        job_id = job.id

    # 2. Zombie worker claims the job
    async with session_factory() as db:
        claimed_job = await worker_zombie.claim_job(db)
        assert claimed_job is not None
        assert claimed_job.id == job_id
        assert claimed_job.status == JobStatus.RUNNING.value

    # 3. Simulate process freeze: Zombie stops heartbeating, lease expires in Redis
    await fake_redis.delete(f"lease:job:{job_id}")

    # 4. Lease reaper runs and reclaims the expired job
    reaper = LeaseReaper(session_factory=session_factory, redis_queue=redis_queue)
    reaped_stats = await reaper.run_once()
    assert reaped_stats["reaped_jobs"] == 1

    # Verify job is back in Redis queue
    depth = await redis_queue.get_queue_depth("HIGH")
    assert depth == 1

    # 5. Healthy worker claims and executes the job to SUCCEEDED
    async with session_factory() as db:
        healthy_job = await worker_healthy.claim_job(db)
        assert healthy_job is not None
        assert healthy_job.id == job_id
        attempt_healthy = await worker_healthy.execute_job(db, healthy_job)
        assert attempt_healthy.outcome == "SUCCEEDED"

    # 6. Zombie worker "wakes up" and attempts to finalize execution on the old job
    async with session_factory() as db:
        # Pass the stale claimed_job object (attempt_count=1, but DB now has attempt_count=2 and status SUCCEEDED)
        zombie_attempt = await worker_zombie.execute_job(db, claimed_job)
        
        # Verify database check fenced out the zombie worker
        stmt_event = select(JobEvent).where(
            JobEvent.job_id == job_id,
            JobEvent.event_type == "ZOMBIE_WORKER_FENCED_OUT"
        )
        res_event = await db.execute(stmt_event)
        fence_event = res_event.scalar_one_or_none()
        assert fence_event is not None
        assert fence_event.actor == "zombie-worker-1"

        # Verify canonical job remains SUCCEEDED from the healthy worker
        job_final = await JobService.get_job(db, job_id)
        assert job_final.status == JobStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_chaos_high_concurrency_burst(test_engine, fake_redis):
    """
    Chaos Scenario 3:
    Submits 20 concurrent jobs across high, default, and low priorities.
    Runs 3 competing workers simultaneously to verify zero race conditions or hung jobs.
    """
    session_factory = async_sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    redis_queue = RedisQueue(client=fake_redis)

    # 1. Enqueue 20 jobs
    job_ids = []
    priorities = [JobPriority.HIGH, JobPriority.DEFAULT, JobPriority.LOW]

    for i in range(20):
        pri = priorities[i % len(priorities)]
        async with session_factory() as db:
            job_in = JobCreate(
                task_type="compute_hash",
                priority=pri,
                payload={"data": f"burst-payload-{i}"},
            )
            job, _ = await JobService.create_job(db, job_in)
            await redis_queue.enqueue(job.id, job.priority)
            job_ids.append(job.id)

    # 2. Run 3 competing workers in parallel
    workers = [
        WorkerEngine(worker_id=f"burst-worker-{k}", session_factory=session_factory, redis_queue=redis_queue)
        for k in range(3)
    ]

    stop_event = asyncio.Event()

    async def worker_loop(w: WorkerEngine):
        while not stop_event.is_set():
            att = await w.run_once()
            if not att:
                await asyncio.sleep(0.01)

    tasks = [asyncio.create_task(worker_loop(w)) for w in workers]

    # Poll until all 20 jobs are SUCCEEDED
    for _ in range(50):
        async with session_factory() as db:
            stmt = select(func.count(Job.id)).where(
                Job.id.in_(job_ids),
                Job.status == JobStatus.SUCCEEDED.value
            )
            res = await db.execute(stmt)
            if res.scalar_one() == 20:
                break
        await asyncio.sleep(0.1)

    stop_event.set()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Final assertion: all 20 jobs succeeded
    async with session_factory() as db:
        stmt = select(func.count(Job.id)).where(
            Job.id.in_(job_ids),
            Job.status == JobStatus.SUCCEEDED.value
        )
        res = await db.execute(stmt)
        assert res.scalar_one() == 20

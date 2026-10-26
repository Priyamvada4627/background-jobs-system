import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.job import Job
from app.models.job_attempt import JobAttempt
from app.models.job_event import JobEvent
from app.queue.redis_queue import RedisQueue
from app.workers.engine import WorkerEngine
from app.services.state_machine import JobStatus


@pytest.mark.asyncio
async def test_competing_workers_no_duplicate_claims(test_engine, fake_redis):
    """
    Spawns multiple concurrent workers racing to claim 30 queued jobs.
    Proves that atomic Redis claiming + leases prevents duplicate claims.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)

    num_jobs = 30
    num_workers = 5
    job_ids = []

    # 1. Insert 30 jobs into PostgreSQL and enqueue into Redis
    async with session_factory() as session:
        for i in range(num_jobs):
            priority = "HIGH" if i < 10 else ("DEFAULT" if i < 20 else "LOW")
            job_id = uuid.uuid4()
            job = Job(
                id=job_id,
                task_type="compute_hash",
                payload_json={"data": f"payload-seed-{i}"},
                status="QUEUED",
                priority=priority,
                scheduled_at=datetime.now(timezone.utc),
            )
            session.add(job)
            job_ids.append(job_id)
            await redis_queue.enqueue(job_id, priority=priority)

        await session.commit()

    # Verify queue depth
    depths = await redis_queue.get_all_queue_depths()
    assert depths["TOTAL"] == num_jobs

    # 2. Create 5 competing worker instances
    workers = [
        WorkerEngine(
            worker_id=f"worker-concurrent-{w}",
            session_factory=session_factory,
            redis_queue=redis_queue,
        )
        for w in range(num_workers)
    ]

    # Register all workers
    async with session_factory() as session:
        for w in workers:
            await w.register_worker(session)

    # 3. Concurrent worker execution loop
    async def worker_runner(w: WorkerEngine):
        consecutive_empty = 0
        while consecutive_empty < 5:
            attempt = await w.run_once()
            if attempt is None:
                depths = await redis_queue.get_all_queue_depths()
                if depths["TOTAL"] == 0:
                    consecutive_empty += 1
                await asyncio.sleep(0.02)
            else:
                consecutive_empty = 0

    # Run all 5 workers concurrently
    await asyncio.gather(*[worker_runner(w) for w in workers])

    # 4. Verify outcomes and guarantees
    async with session_factory() as session:
        # Verify all jobs reached SUCCEEDED
        stmt = select(Job).where(Job.id.in_(job_ids))
        res = await session.execute(stmt)
        processed_jobs = list(res.scalars().all())

        assert len(processed_jobs) == num_jobs
        for job in processed_jobs:
            assert job.status == "SUCCEEDED"
            assert job.attempt_count == 1
            assert "hash" in job.result_json

        # Verify attempts: exactly 30 attempts, each tied to exactly 1 job
        stmt_att = select(JobAttempt).where(JobAttempt.job_id.in_(job_ids))
        res_att = await session.execute(stmt_att)
        attempts = list(res_att.scalars().all())

        assert len(attempts) == num_jobs
        attempt_job_ids = [att.job_id for att in attempts]
        # No duplicate claims: length of set must equal length of list
        assert len(set(attempt_job_ids)) == num_jobs

        # Verify multiple workers actually participated
        worker_ids_used = {att.worker_id for att in attempts}
        assert len(worker_ids_used) > 1

    # Verify Redis queues are completely drained and leases released
    final_depths = await redis_queue.get_all_queue_depths()
    assert final_depths["TOTAL"] == 0
    for job_id in job_ids:
        assert await redis_queue.get_lease_owner(job_id) is None


@pytest.mark.asyncio
async def test_inconsistency_recovery_skips_cancelled_job(test_engine, fake_redis):
    """
    Tests recovery when Redis queue contains a job ID that was already CANCELLED in the database.
    The worker must safely detect the inconsistency, discard the queue entry, release the lease,
    and proceed without error.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)
    worker = WorkerEngine(worker_id="worker-recovery", session_factory=session_factory, redis_queue=redis_queue)

    cancelled_id = uuid.uuid4()
    legit_id = uuid.uuid4()

    async with session_factory() as session:
        # Job 1: Cancelled in DB, but lingering in Redis queue
        job_cancelled = Job(
            id=cancelled_id,
            task_type="compute_hash",
            payload_json={},
            status=JobStatus.CANCELLED.value,
            priority="HIGH",
            scheduled_at=datetime.now(timezone.utc),
        )
        # Job 2: Legitimate queued job
        job_legit = Job(
            id=legit_id,
            task_type="compute_hash",
            payload_json={"data": "legit"},
            status=JobStatus.QUEUED.value,
            priority="HIGH",
            scheduled_at=datetime.now(timezone.utc),
        )
        session.add_all([job_cancelled, job_legit])
        await session.commit()

    # Enqueue cancelled job first, then legit job
    await redis_queue.enqueue(cancelled_id, priority="HIGH")
    await redis_queue.enqueue(legit_id, priority="HIGH")

    # Worker runs once: should detect cancelled_id, skip it, and execute legit_id
    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.job_id == legit_id
    assert attempt.outcome == "SUCCEEDED"

    # Cancelled job was NOT executed
    async with session_factory() as session:
        j1 = await session.get(Job, cancelled_id)
        assert j1.status == JobStatus.CANCELLED.value
        assert j1.attempt_count == 0

        j2 = await session.get(Job, legit_id)
        assert j2.status == JobStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_inconsistency_recovery_skips_missing_job(test_engine, fake_redis):
    """
    Tests recovery when Redis queue contains a UUID that does not exist in the database.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)
    worker = WorkerEngine(worker_id="worker-ghost", session_factory=session_factory, redis_queue=redis_queue)

    ghost_id = uuid.uuid4()
    await redis_queue.enqueue(ghost_id, priority="DEFAULT")

    # Worker runs once: claims ghost ID, detects absence in DB, discards it, returns None
    attempt = await worker.run_once()
    assert attempt is None
    assert await redis_queue.get_lease_owner(ghost_id) is None

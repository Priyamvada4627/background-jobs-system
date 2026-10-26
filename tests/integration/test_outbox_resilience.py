import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
import redis.exceptions

from app.models.job import Job
from app.models.outbox_event import OutboxEvent
from app.models.job_attempt import JobAttempt
from app.services.job_service import JobService
from app.schemas.job import JobCreate, JobPriority
from app.queue.redis_queue import RedisQueue
from app.services.outbox_publisher import OutboxPublisher
from app.workers.engine import WorkerEngine


@pytest.mark.asyncio
async def test_redis_outage_retains_jobs_and_drains_on_recovery(test_engine, fake_redis):
    """
    Integration resilience test simulating a Redis outage during job submission.
    Guarantees:
      1. Zero committed jobs are lost during Redis downtime (retained in PostgreSQL outbox).
      2. Publisher retries safely with backoff without losing or corrupting state.
      3. Once Redis recovers, publisher automatically drains all pending jobs.
      4. Competing workers claim and execute all recovered jobs to SUCCEEDED.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    real_redis_queue = RedisQueue(client=fake_redis)

    num_jobs = 10
    created_job_ids = []

    # ---------------------------------------------------------
    # Step 1: Client submits jobs to PostgreSQL while Redis is completely down
    # ---------------------------------------------------------
    async with session_factory() as session:
        for i in range(num_jobs):
            priority = JobPriority.HIGH if i < 3 else (JobPriority.DEFAULT if i < 7 else JobPriority.LOW)
            job, created = await JobService.create_job(
                session,
                JobCreate(
                    task_type="compute_hash",
                    payload={"data": f"resilience-seed-{i}"},
                    priority=priority,
                ),
            )
            assert created is True
            created_job_ids.append(job.id)

    # Verify all 10 jobs exist in PostgreSQL in QUEUED state
    async with session_factory() as session:
        stmt = select(Job).where(Job.id.in_(created_job_ids))
        jobs = (await session.execute(stmt)).scalars().all()
        assert len(jobs) == num_jobs
        for j in jobs:
            assert j.status == "QUEUED"

        # Verify all 10 outbox events exist and are UNPUBLISHED
        stmt_outbox = select(OutboxEvent).where(OutboxEvent.job_id.in_(created_job_ids))
        outbox_events = (await session.execute(stmt_outbox)).scalars().all()
        assert len(outbox_events) == num_jobs
        for ev in outbox_events:
            assert ev.published_at is None
            assert ev.publish_attempts == 0

    # ---------------------------------------------------------
    # Step 2: Outbox publisher runs while Redis is offline (simulated outage)
    # ---------------------------------------------------------
    broken_redis_queue = RedisQueue(client=fake_redis)
    # Mock enqueue to simulate Redis connection failure
    broken_redis_queue.enqueue = AsyncMock(
        side_effect=redis.exceptions.ConnectionError("Connection refused: Redis server is unreachable")
    )

    failing_publisher = OutboxPublisher(
        session_factory=session_factory,
        redis_queue=broken_redis_queue,
        base_backoff_seconds=0.1,
        max_backoff_seconds=1.0,
    )

    # Publisher tries to publish but encounters connection failure
    with pytest.raises(redis.exceptions.ConnectionError):
        async with session_factory() as session:
            await failing_publisher.publish_batch(session)

    # Verify that ZERO outbox events were marked published and backoff increased
    async with session_factory() as session:
        stmt_outbox = select(OutboxEvent).where(OutboxEvent.job_id.in_(created_job_ids))
        outbox_events = (await session.execute(stmt_outbox)).scalars().all()
        for ev in outbox_events:
            assert ev.published_at is None
        assert failing_publisher._current_backoff > failing_publisher.base_backoff_seconds

    # Also test that run_once() safely catches the exception without crashing
    count = await failing_publisher.run_once()
    assert count == 0

    # ---------------------------------------------------------
    # Step 3: Redis recovers! Healthy publisher drains the outbox
    # ---------------------------------------------------------
    healthy_publisher = OutboxPublisher(
        session_factory=session_factory,
        redis_queue=real_redis_queue,
    )

    published_total = await healthy_publisher.run_once()
    assert published_total == num_jobs

    # Verify all outbox events in PostgreSQL are now marked published
    async with session_factory() as session:
        stmt_outbox = select(OutboxEvent).where(OutboxEvent.job_id.in_(created_job_ids))
        outbox_events = (await session.execute(stmt_outbox)).scalars().all()
        assert len(outbox_events) == num_jobs
        for ev in outbox_events:
            assert ev.published_at is not None
            assert ev.publish_attempts == 1

    # Verify Redis queues received all jobs
    depths = await real_redis_queue.get_all_queue_depths()
    assert depths["TOTAL"] == num_jobs
    assert depths["HIGH"] == 3
    assert depths["DEFAULT"] == 4
    assert depths["LOW"] == 3

    # ---------------------------------------------------------
    # Step 4: Competing workers claim and process all recovered jobs
    # ---------------------------------------------------------
    workers = [
        WorkerEngine(
            worker_id=f"worker-resilience-{w}",
            session_factory=session_factory,
            redis_queue=real_redis_queue,
        )
        for w in range(3)
    ]

    async def worker_runner(w: WorkerEngine):
        consecutive_empty = 0
        while consecutive_empty < 5:
            attempt = await w.run_once()
            if attempt is None:
                d = await real_redis_queue.get_all_queue_depths()
                if d["TOTAL"] == 0:
                    consecutive_empty += 1
                await asyncio.sleep(0.02)
            else:
                consecutive_empty = 0

    await asyncio.gather(*[worker_runner(w) for w in workers])

    # ---------------------------------------------------------
    # Step 5: Verify all jobs reached terminal SUCCEEDED state
    # ---------------------------------------------------------
    async with session_factory() as session:
        stmt = select(Job).where(Job.id.in_(created_job_ids))
        jobs = (await session.execute(stmt)).scalars().all()
        assert len(jobs) == num_jobs
        for job in jobs:
            assert job.status == "SUCCEEDED"
            assert job.attempt_count == 1
            assert "hash" in job.result_json

        stmt_att = select(JobAttempt).where(JobAttempt.job_id.in_(created_job_ids))
        attempts = (await session.execute(stmt_att)).scalars().all()
        assert len(attempts) == num_jobs

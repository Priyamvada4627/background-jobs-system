import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.job import Job
from app.models.job_schedule import JobSchedule
from app.models.job_attempt import JobAttempt
from app.schemas.job import JobCreate
from app.schemas.schedule import ScheduleCreate
from app.services.job_service import JobService
from app.services.schedule_service import ScheduleService
from app.services.state_machine import JobStatus
from app.queue.redis_queue import RedisQueue
from app.scheduler.cron_scheduler import CronScheduler
from app.workers.engine import WorkerEngine


@pytest.mark.asyncio
async def test_delayed_job_promotion_when_due(test_engine, fake_redis):
    """
    Verifies that:
      1. A job in RETRY_WAIT with scheduled_at in the future is not promoted.
      2. Once scheduled_at <= NOW(), CronScheduler promotes it to QUEUED and pushes it to Redis.
      3. A worker can immediately claim and execute the promoted job.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)
    scheduler = CronScheduler(session_factory=session_factory, redis_queue=redis_queue)

    now = datetime.now(timezone.utc)
    future_time = now + timedelta(hours=1)

    # 1. Insert a job stuck in RETRY_WAIT scheduled 1 hour in the future
    job_id = uuid.uuid4()
    async with session_factory() as session:
        job = Job(
            id=job_id,
            task_type="compute_hash",
            payload_json={"data": "delayed-test"},
            status=JobStatus.RETRY_WAIT.value,
            priority="HIGH",
            scheduled_at=future_time,
            max_retries=3,
            attempt_count=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        await session.commit()

    # 2. Run scheduler: should NOT promote future job
    async with session_factory() as session:
        promoted = await scheduler.promote_due_retries(session)
        assert promoted == 0

    depths = await redis_queue.get_all_queue_depths()
    assert depths["TOTAL"] == 0

    # 3. Simulate time passing: update scheduled_at to past
    async with session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        j = (await session.execute(stmt)).scalar_one()
        j.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    # 4. Run scheduler: should promote job to QUEUED and Redis
    async with session_factory() as session:
        promoted = await scheduler.promote_due_retries(session)
        assert promoted == 1

        stmt = select(Job).where(Job.id == job_id)
        promoted_job = (await session.execute(stmt)).scalar_one()
        assert promoted_job.status == "QUEUED"

    depths = await redis_queue.get_all_queue_depths()
    assert depths["HIGH"] == 1
    assert depths["TOTAL"] == 1

    # 5. Worker claims and executes the promoted job
    worker = WorkerEngine(worker_id="test-scheduler-worker", session_factory=session_factory, redis_queue=redis_queue)
    attempt = await worker.run_once()
    assert attempt is not None
    assert attempt.job_id == job_id
    assert attempt.outcome == "SUCCEEDED"


@pytest.mark.asyncio
async def test_cron_schedule_evaluation_and_idempotency(test_engine, fake_redis):
    """
    Verifies that:
      1. Active schedules with next_run_at <= NOW() create child jobs.
      2. The schedule's last_run_at and next_run_at are updated into the future.
      3. Repeated evaluation does not create duplicate child jobs due to idempotency keys.
    """
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)
    scheduler = CronScheduler(session_factory=session_factory, redis_queue=redis_queue)

    now = datetime.now(timezone.utc)
    due_time = now - timedelta(hours=1)

    # 1. Create a schedule whose next_run_at is due (1 hour ago)
    async with session_factory() as session:
        schedule = JobSchedule(
            id=uuid.uuid4(),
            name="daily-eval-test",
            task_type="compute_hash",
            payload_json={"message": "hello-cron"},
            cron_expression="0 0 * * *",
            timezone="UTC",
            enabled=True,
            next_run_at=due_time,
            created_at=now,
            updated_at=now,
        )
        session.add(schedule)
        await session.commit()
        schedule_id = schedule.id

    # 2. First evaluation: generates 1 child job and advances next_run_at
    async with session_factory() as session:
        created_count = await scheduler.evaluate_schedules(session)
        assert created_count == 1

        # Check updated schedule
        stmt_s = select(JobSchedule).where(JobSchedule.id == schedule_id)
        updated_s = (await session.execute(stmt_s)).scalar_one()
        assert updated_s.last_run_at is not None
        # next_run_at is now advanced beyond due_time
        next_run_utc = updated_s.next_run_at if updated_s.next_run_at.tzinfo else updated_s.next_run_at.replace(tzinfo=timezone.utc)
        assert next_run_utc > due_time

    # Verify the child job exists
    async with session_factory() as session:
        stmt_j = select(Job).where(Job.task_type == "compute_hash", Job.payload_json == {"message": "hello-cron"})
        child_jobs = (await session.execute(stmt_j)).scalars().all()
        assert len(child_jobs) == 1
        assert child_jobs[0].status == "QUEUED"

    # 3. Second evaluation immediately: 0 jobs generated (next_run_at is now in future)
    async with session_factory() as session:
        second_count = await scheduler.evaluate_schedules(session)
        assert second_count == 0


@pytest.mark.asyncio
async def test_distributed_leader_locking(fake_redis, test_engine):
    """Verifies that competing scheduler instances use Redis leader locks to avoid duplicate evaluations."""
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    redis_queue = RedisQueue(client=fake_redis)

    s1 = CronScheduler(scheduler_id="scheduler-leader-1", session_factory=session_factory, redis_queue=redis_queue)
    s2 = CronScheduler(scheduler_id="scheduler-leader-2", session_factory=session_factory, redis_queue=redis_queue)

    # 1. S1 acquires lock
    assert await s1.acquire_leader_lock() is True

    # 2. S2 cannot acquire lock while S1 holds it
    assert await s2.acquire_leader_lock() is False

    # 3. S2 cannot release S1's lock
    assert await s2.release_leader_lock() is False

    # 4. S1 releases lock
    assert await s1.release_leader_lock() is True

    # 5. S2 can now acquire lock
    assert await s2.acquire_leader_lock() is True
    assert await s2.release_leader_lock() is True

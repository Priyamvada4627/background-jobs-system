import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.outbox_event import OutboxEvent
from app.schemas.job import JobCreate, JobPriority
from app.services.job_service import JobService
from app.services.outbox_publisher import OutboxPublisher
from app.queue.redis_queue import RedisQueue


@pytest.mark.asyncio
async def test_publish_batch_immediate_jobs(db_session: AsyncSession, fake_redis):
    """Verifies that immediate jobs are drained from outbox_events to Redis priority queues."""
    redis_queue = RedisQueue(client=fake_redis)
    publisher = OutboxPublisher(redis_queue=redis_queue)

    # 1. Create 3 jobs with different priorities
    priorities = [JobPriority.HIGH, JobPriority.DEFAULT, JobPriority.LOW]
    for p in priorities:
        await JobService.create_job(
            db_session,
            JobCreate(task_type="compute_hash", payload={"val": p.value}, priority=p),
        )

    # Verify 3 unpublished outbox events exist
    stmt = select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
    events = (await db_session.execute(stmt)).scalars().all()
    assert len(events) == 3

    # 2. Publish batch
    published_count = await publisher.publish_batch(db_session)
    assert published_count == 3

    # Verify outbox rows are marked published
    events_after = (await db_session.execute(stmt)).scalars().all()
    assert len(events_after) == 0

    stmt_all = select(OutboxEvent)
    all_events = (await db_session.execute(stmt_all)).scalars().all()
    for ev in all_events:
        assert ev.published_at is not None
        assert ev.publish_attempts == 1

    # 3. Verify Redis queue depths
    depths = await redis_queue.get_all_queue_depths()
    assert depths["HIGH"] == 1
    assert depths["DEFAULT"] == 1
    assert depths["LOW"] == 1
    assert depths["TOTAL"] == 3


@pytest.mark.asyncio
async def test_publish_batch_delayed_jobs_not_pushed_to_ready_queue(db_session: AsyncSession, fake_redis):
    """
    Verifies that jobs scheduled in the future have their creation outbox event acknowledged,
    but are NOT pushed to the immediate Redis ready queues (reserved for the Delayed Scheduler).
    """
    redis_queue = RedisQueue(client=fake_redis)
    publisher = OutboxPublisher(redis_queue=redis_queue)

    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    await JobService.create_job(
        db_session,
        JobCreate(
            task_type="compute_hash",
            payload={"key": "future"},
            priority=JobPriority.HIGH,
            scheduled_at=future_time,
        ),
    )

    published_count = await publisher.publish_batch(db_session)
    assert published_count == 1

    # Verify Redis queues are still empty
    depths = await redis_queue.get_all_queue_depths()
    assert depths["TOTAL"] == 0

    # Verify outbox event is marked published
    stmt = select(OutboxEvent)
    event = (await db_session.execute(stmt)).scalar_one()
    assert event.published_at is not None


@pytest.mark.asyncio
async def test_publish_batch_empty_outbox(db_session: AsyncSession, fake_redis):
    """Verifies that running publisher on an empty table returns 0 without errors."""
    redis_queue = RedisQueue(client=fake_redis)
    publisher = OutboxPublisher(redis_queue=redis_queue)

    count = await publisher.publish_batch(db_session)
    assert count == 0


@pytest.mark.asyncio
async def test_outbox_publisher_batching_limit(db_session: AsyncSession, fake_redis):
    """Verifies that publisher respects batch_size limit and drains incrementally across cycles."""
    redis_queue = RedisQueue(client=fake_redis)
    publisher = OutboxPublisher(redis_queue=redis_queue, batch_size=4)

    # Create 10 jobs
    for i in range(10):
        await JobService.create_job(
            db_session,
            JobCreate(task_type="compute_hash", payload={"i": i}),
        )

    # First cycle: publishes 4
    c1 = await publisher.publish_batch(db_session, limit=4)
    assert c1 == 4
    depths1 = await redis_queue.get_all_queue_depths()
    assert depths1["TOTAL"] == 4

    # Second cycle: publishes 4
    c2 = await publisher.publish_batch(db_session, limit=4)
    assert c2 == 4
    depths2 = await redis_queue.get_all_queue_depths()
    assert depths2["TOTAL"] == 8

    # Third cycle: publishes remaining 2
    c3 = await publisher.publish_batch(db_session, limit=4)
    assert c3 == 2
    depths3 = await redis_queue.get_all_queue_depths()
    assert depths3["TOTAL"] == 10

    # Fourth cycle: 0 left
    c4 = await publisher.publish_batch(db_session, limit=4)
    assert c4 == 0

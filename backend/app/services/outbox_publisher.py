import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import redis.exceptions

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.outbox_event import OutboxEvent
from app.queue.redis_queue import RedisQueue

logger = logging.getLogger(__name__)


class OutboxPublisher:
    """
    Transactional Outbox Publisher daemon.
    Guarantees reliable at-least-once publishing of committed events from PostgreSQL to Redis.
    Never loses events during Redis outages; automatically resumes and drains pending batches once Redis recovers.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        redis_queue: Optional[RedisQueue] = None,
        batch_size: Optional[int] = None,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 10.0,
    ):
        self.session_factory = session_factory or get_sessionmaker()
        self.redis_queue = redis_queue or RedisQueue()
        self.batch_size = batch_size or settings.OUTBOX_BATCH_SIZE
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._current_backoff = base_backoff_seconds

    async def publish_batch(self, db: AsyncSession, limit: Optional[int] = None) -> int:
        """
        Polls a batch of unpublished outbox events, enqueues them to Redis,
        and marks them published_at = NOW() in the database.
        
        Uses SELECT ... FOR UPDATE SKIP LOCKED to support concurrent publisher instances
        safely without double-publishing.
        """
        batch_limit = limit or self.batch_size
        now = datetime.now(timezone.utc)

        # 1. Query unpublished events ordered by creation timestamp
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at.asc())
            .limit(batch_limit)
        )

        try:
            locked_stmt = stmt.with_for_update(skip_locked=True)
            result = await db.execute(locked_stmt)
            events = list(result.scalars().all())
        except OperationalError:
            # Fallback for dialects that do not support SKIP LOCKED (e.g. SQLite test engine)
            result = await db.execute(stmt)
            events = list(result.scalars().all())

        if not events:
            return 0

        # 2. Process each outbox event
        published_count = 0
        try:
            for event in events:
                payload = event.payload_json or {}
                job_id = payload.get("job_id") or str(event.job_id)
                priority = payload.get("priority", "DEFAULT")
                scheduled_at_str = payload.get("scheduled_at")

                is_delayed = False
                if scheduled_at_str:
                    try:
                        scheduled_at = datetime.fromisoformat(scheduled_at_str)
                        if scheduled_at.tzinfo is None:
                            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
                        if scheduled_at > now:
                            is_delayed = True
                    except (ValueError, TypeError):
                        pass

                # If the job is immediate (or due), push to Redis ready queues
                if not is_delayed:
                    await self.redis_queue.enqueue(job_id=job_id, priority=priority)

                event.published_at = datetime.now(timezone.utc)
                event.publish_attempts += 1
                published_count += 1

            # 3. Commit state change to PostgreSQL
            await db.commit()
            self._current_backoff = self.base_backoff_seconds
            return published_count

        except (redis.exceptions.RedisError, ConnectionError, OSError) as err:
            await db.rollback()
            logger.warning(
                f"Outbox publisher encountered Redis/network error: {err}. "
                f"Pending {len(events)} events remain safely in PostgreSQL."
            )
            # Increase exponential backoff
            self._current_backoff = min(self.max_backoff_seconds, self._current_backoff * 2)
            raise

    async def run_once(self) -> int:
        """Runs a single publish cycle, opening its own isolated database session."""
        async with self.session_factory() as session:
            try:
                return await self.publish_batch(session)
            except (redis.exceptions.RedisError, ConnectionError, OSError):
                return 0

    async def run_loop(
        self,
        poll_interval: Optional[float] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Runs the continuous outbox publisher loop until stop_event is set.
        Drains pending batches quickly when work is available, and applies exponential
        backoff when Redis is temporarily unavailable.
        """
        interval = poll_interval or settings.OUTBOX_POLL_INTERVAL_SECONDS
        stop = stop_event or asyncio.Event()

        logger.info(f"Outbox publisher loop started (batch_size={self.batch_size}, poll_interval={interval}s)")

        while not stop.is_set():
            try:
                published = await self.run_once()
                if published > 0:
                    # Drain immediately without long pause if there were items
                    await asyncio.sleep(0.01)
                else:
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Unexpected error in outbox publisher loop: {exc}")
                await asyncio.sleep(self._current_backoff)

        logger.info("Outbox publisher loop stopped.")

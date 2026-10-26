import asyncio
import logging
import uuid
import socket
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.job import Job
from app.models.job_schedule import JobSchedule
from app.models.job_event import JobEvent
from app.models.outbox_event import OutboxEvent
from app.schemas.job import JobCreate, JobPriority
from app.services.state_machine import JobStatus
from app.services.job_service import JobService
from app.queue.redis_queue import RedisQueue

logger = logging.getLogger(__name__)


RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


class CronScheduler:
    """
    Scheduler daemon responsible for:
      1. Promoting due delayed and retrying jobs (scheduled_at <= NOW()) to ready queues.
      2. Evaluating recurring cron schedules idempotently with timezone precision.
      3. Distributed leader locking via Redis to ensure single execution across replicas.
    """

    LOCK_KEY = "lock:scheduler:leader"

    def __init__(
        self,
        scheduler_id: Optional[str] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        redis_queue: Optional[RedisQueue] = None,
        lock_ttl_seconds: int = 15,
    ):
        self.scheduler_id = scheduler_id or f"scheduler-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.session_factory = session_factory or get_sessionmaker()
        self.redis_queue = redis_queue or RedisQueue()
        self.lock_ttl_seconds = lock_ttl_seconds
        self._release_lock_script = None

    async def acquire_leader_lock(self) -> bool:
        """Attempts to acquire the exclusive distributed scheduler lock in Redis."""
        try:
            acquired = await self.redis_queue.client.set(
                self.LOCK_KEY,
                self.scheduler_id,
                nx=True,
                ex=self.lock_ttl_seconds,
            )
            return bool(acquired)
        except Exception as exc:
            logger.warning(f"Could not connect to Redis for scheduler lock: {exc}")
            # If Redis is offline, allow single local fallback or return False
            return False

    async def release_leader_lock(self) -> bool:
        """Safely releases the distributed scheduler lock only if held by this instance."""
        try:
            if self._release_lock_script is None:
                self._release_lock_script = self.redis_queue.client.register_script(RELEASE_LOCK_LUA)
            res = await self._release_lock_script(keys=[self.LOCK_KEY], args=[self.scheduler_id])
            return bool(res == 1)
        except Exception:
            return False

    async def promote_due_retries(self, db: AsyncSession, limit: int = 100) -> int:
        """
        Scans for jobs in RETRY_WAIT whose backoff delay has expired (scheduled_at <= NOW()).
        Promotes them to QUEUED, writes an audit trail, and enqueues to Redis.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.RETRY_WAIT.value,
                Job.scheduled_at <= now,
            )
            .order_by(Job.scheduled_at.asc())
            .limit(limit)
        )

        try:
            res = await db.execute(stmt.with_for_update(skip_locked=True))
            due_jobs = list(res.scalars().all())
        except OperationalError:
            res = await db.execute(stmt)
            due_jobs = list(res.scalars().all())

        if not due_jobs:
            return 0

        promoted_count = 0
        for job in due_jobs:
            from_status = job.status
            job.status = JobStatus.QUEUED.value
            job.updated_at = now

            # Enqueue to Redis priority lane
            await self.redis_queue.enqueue(job.id, priority=job.priority)

            # Audit event
            audit_event = JobEvent(
                job_id=job.id,
                event_type="STATE_CHANGED_TO_QUEUED",
                details_json={
                    "from_state": from_status,
                    "to_state": "QUEUED",
                    "reason": "RETRY_DELAY_EXPIRED",
                },
                actor="SCHEDULER",
                created_at=now,
            )
            db.add(audit_event)
            promoted_count += 1

        await db.commit()
        return promoted_count

    async def evaluate_schedules(self, db: AsyncSession, limit: int = 50) -> int:
        """
        Evaluates active cron schedules where next_run_at <= NOW().
        Creates child jobs idempotently and advances next_run_at.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(JobSchedule)
            .where(
                JobSchedule.enabled.is_(True),
                JobSchedule.next_run_at <= now,
            )
            .order_by(JobSchedule.next_run_at.asc())
            .limit(limit)
        )

        try:
            res = await db.execute(stmt.with_for_update(skip_locked=True))
            due_schedules = list(res.scalars().all())
        except OperationalError:
            res = await db.execute(stmt)
            due_schedules = list(res.scalars().all())

        if not due_schedules:
            return 0

        created_jobs_count = 0
        for schedule in due_schedules:
            tz = ZoneInfo(schedule.timezone)
            scheduled_run_time = schedule.next_run_at
            if scheduled_run_time.tzinfo is None:
                scheduled_run_time = scheduled_run_time.replace(tzinfo=timezone.utc)

            # Calculate next execution timestamp after current next_run_at
            ref_dt = scheduled_run_time.astimezone(tz)
            cron = croniter(schedule.cron_expression, ref_dt)
            next_run_local = cron.get_next(datetime)
            next_run_utc = next_run_local.astimezone(timezone.utc)

            # Advance schedule timestamps
            schedule.last_run_at = scheduled_run_time
            schedule.next_run_at = next_run_utc
            schedule.updated_at = now

            # Create child job idempotently
            idempotency_key = f"schedule:{schedule.id}:{scheduled_run_time.isoformat()}"
            job_in = JobCreate(
                task_type=schedule.task_type,
                payload=schedule.payload_json,
                priority=JobPriority.DEFAULT,
                idempotency_key=idempotency_key,
                scheduled_at=scheduled_run_time,
            )

            # Creates job and outbox event
            _, created = await JobService.create_job(db, job_in)
            if created:
                created_jobs_count += 1

        await db.commit()
        return created_jobs_count

    async def run_once(self) -> Dict[str, int]:
        """
        Executes a single scheduler cycle under distributed leader lock.
        Returns a dictionary with counts of promoted retries and evaluated schedules.
        """
        has_lock = await self.acquire_leader_lock()
        if not has_lock:
            return {"promoted_retries": 0, "evaluated_schedules": 0, "is_leader": 0}

        try:
            async with self.session_factory() as db:
                retries = await self.promote_due_retries(db)
                schedules = await self.evaluate_schedules(db)
                return {
                    "promoted_retries": retries,
                    "evaluated_schedules": schedules,
                    "is_leader": 1,
                }
        finally:
            await self.release_leader_lock()

    async def run_loop(
        self,
        poll_interval: Optional[float] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Continuous scheduler daemon loop."""
        interval = poll_interval or settings.SCHEDULER_POLL_INTERVAL_SECONDS
        stop = stop_event or asyncio.Event()

        logger.info(f"CronScheduler {self.scheduler_id} loop started (poll_interval={interval}s)")

        while not stop.is_set():
            try:
                result = await self.run_once()
                total_work = result.get("promoted_retries", 0) + result.get("evaluated_schedules", 0)
                if total_work > 0:
                    await asyncio.sleep(0.05)
                else:
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in CronScheduler loop: {exc}")
                await asyncio.sleep(interval)

        logger.info(f"CronScheduler {self.scheduler_id} loop stopped.")

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.job import Job
from app.models.worker import Worker
from app.models.job_event import JobEvent
from app.services.state_machine import JobStatus
from app.queue.redis_queue import RedisQueue

logger = logging.getLogger(__name__)


class LeaseReaper:
    """
    Lease Reaper daemon responsible for:
      1. Scanning for RUNNING jobs whose worker lease in Redis has expired.
      2. Employing monotonic fencing tokens to safely requeue retryable jobs or transition dead jobs to DEAD.
      3. Detecting abandoned workers and marking their database status DEAD.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        redis_queue: Optional[RedisQueue] = None,
    ):
        self.session_factory = session_factory or get_sessionmaker()
        self.redis_queue = redis_queue or RedisQueue()

    async def reap_abandoned_jobs(self, db: AsyncSession, limit: int = 50) -> int:
        """
        Finds jobs marked RUNNING in PostgreSQL whose lease has expired in Redis.
        If attempts remain under max_retries, transitions to QUEUED and re-inserts into Redis;
        otherwise transitions to DEAD (DLQ).
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.RUNNING.value)
            .order_by(Job.updated_at.asc())
            .limit(limit)
        )

        try:
            res = await db.execute(stmt.with_for_update(skip_locked=True))
            running_jobs = list(res.scalars().all())
        except OperationalError:
            res = await db.execute(stmt)
            running_jobs = list(res.scalars().all())

        if not running_jobs:
            return 0

        reaped_count = 0
        for job in running_jobs:
            # Check lease ownership in Redis
            lease_owner = await self.redis_queue.get_lease_owner(job.id)
            if lease_owner is not None:
                # Active lease held by a living worker: do not reap
                continue

            # Lease expired! Worker crashed, died, or lost network connectivity.
            fencing_token = job.attempt_count
            if job.attempt_count < job.max_retries:
                job.status = JobStatus.QUEUED.value
                job.last_error = f"Lease expired (worker presumed dead). Reaped and requeued."
                job.updated_at = now
                event_type = "JOB_REAPED_REQUEUED"
                details = {
                    "from_state": "RUNNING",
                    "to_state": "QUEUED",
                    "attempt_number": fencing_token,
                    "reason": "LEASE_EXPIRED_REQUEUED",
                }
                # Re-enqueue into Redis priority queue
                await self.redis_queue.enqueue(job.id, priority=job.priority)
            else:
                job.status = JobStatus.DEAD.value
                job.last_error = f"Lease expired and max retries ({job.max_retries}) exhausted."
                job.updated_at = now
                event_type = "JOB_REAPED_DEAD"
                details = {
                    "from_state": "RUNNING",
                    "to_state": "DEAD",
                    "attempt_number": fencing_token,
                    "reason": "LEASE_EXPIRED_MAX_RETRIES",
                }

            audit_event = JobEvent(
                job_id=job.id,
                event_type=event_type,
                details_json=details,
                actor="LEASE_REAPER",
                created_at=now,
            )
            db.add(audit_event)
            reaped_count += 1

        if reaped_count > 0:
            await db.commit()

        return reaped_count

    async def reap_dead_workers(
        self,
        db: AsyncSession,
        heartbeat_timeout_seconds: float = 60.0,
    ) -> int:
        """Marks workers as DEAD if their last heartbeat timestamp exceeds the timeout threshold."""
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(seconds=heartbeat_timeout_seconds)

        stmt = select(Worker).where(
            Worker.status == "ALIVE",
            Worker.last_heartbeat_at < threshold,
        )
        res = await db.execute(stmt)
        dead_workers = list(res.scalars().all())

        if not dead_workers:
            return 0

        for w in dead_workers:
            w.status = "DEAD"
            w.current_job_id = None

        await db.commit()
        return len(dead_workers)

    async def run_once(self, heartbeat_timeout_seconds: float = 60.0) -> Dict[str, int]:
        """Executes a single reaping cycle for abandoned jobs and dead workers."""
        async with self.session_factory() as db:
            reaped_jobs = await self.reap_abandoned_jobs(db)
            dead_workers = await self.reap_dead_workers(db, heartbeat_timeout_seconds=heartbeat_timeout_seconds)
            return {"reaped_jobs": reaped_jobs, "dead_workers": dead_workers}

    async def run_loop(
        self,
        poll_interval: Optional[float] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Continuous reaper daemon loop."""
        interval = poll_interval or settings.REAPER_POLL_INTERVAL_SECONDS
        stop = stop_event or asyncio.Event()

        logger.info(f"LeaseReaper loop started (poll_interval={interval}s)")

        while not stop.is_set():
            try:
                stats = await self.run_once()
                if stats["reaped_jobs"] > 0:
                    logger.warning(f"LeaseReaper recovered {stats['reaped_jobs']} abandoned jobs.")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in LeaseReaper loop: {exc}")
                await asyncio.sleep(interval)

        logger.info("LeaseReaper loop stopped.")

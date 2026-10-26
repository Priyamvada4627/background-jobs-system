import os
import sys
import socket
import uuid
import time
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, case, func
from sqlalchemy.exc import OperationalError

from app.models.job import Job
from app.models.job_attempt import JobAttempt
from app.models.job_event import JobEvent
from app.models.worker import Worker
from app.services.state_machine import JobStatus, AttemptOutcome
from app.services.retry_policy import calculate_backoff_delay
from app.tasks.registry import get_task_handler, execute_task_handler, UnregisteredTaskError, list_registered_tasks
from app.db.session import get_sessionmaker
from app.queue.redis_queue import RedisQueue
from app.core.config import settings


class WorkerEngine:
    def __init__(
        self,
        worker_id: Optional[str] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        redis_queue: Optional[RedisQueue] = None,
    ):
        self.worker_id = worker_id or f"worker-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.session_factory = session_factory or get_sessionmaker()
        self.redis_queue = redis_queue
        self.capabilities = list_registered_tasks()
        self.hostname = socket.gethostname()
        self.pid = os.getpid()

    async def register_worker(self, db: AsyncSession) -> Worker:
        """Registers or updates this worker's record in the database."""
        now = datetime.now(timezone.utc)

        stmt = select(Worker).where(Worker.worker_id == self.worker_id)
        res = await db.execute(stmt)
        worker = res.scalar_one_or_none()

        if not worker:
            worker = Worker(
                worker_id=self.worker_id,
                hostname=self.hostname,
                pid=self.pid,
                started_at=now,
                last_heartbeat_at=now,
                status="ALIVE",
                current_job_id=None,
                capabilities_json=self.capabilities,
                metadata_json={"python_version": sys.version.split()[0]},
            )
            db.add(worker)
        else:
            worker.last_heartbeat_at = now
            worker.status = "ALIVE"

        await db.commit()
        await db.refresh(worker)
        return worker



    async def claim_job(self, db: AsyncSession) -> Optional[Job]:
        """
        Atomically queries and claims a single QUEUED job whose scheduled_at <= NOW().
        If redis_queue is configured, claims from Redis priority lanes using an atomic Lua script
        with lease acquisition and safe inconsistency recovery.
        Otherwise falls back to direct database query.
        """
        now = datetime.now(timezone.utc)

        # 1. Redis-backed priority queue claiming
        if self.redis_queue is not None:
            while True:
                claimed_pop = await self.redis_queue.claim_job_atomic(
                    worker_id=self.worker_id,
                    lease_ttl_seconds=settings.WORKER_LEASE_TTL_SECONDS,
                )
                if claimed_pop is None:
                    return None

                job_id_str, queue_name = claimed_pop
                job_uuid = uuid.UUID(job_id_str)

                # Fetch canonical job state from PostgreSQL
                res = await db.execute(select(Job).where(Job.id == job_uuid))
                job = res.scalar_one_or_none()

                # Inconsistency check: if job missing or not in QUEUED state, release lease and discard
                if not job or job.status != JobStatus.QUEUED.value:
                    await self.redis_queue.release_lease(job_uuid, self.worker_id)
                    continue

                # Atomically transition to RUNNING in database
                job.status = JobStatus.RUNNING.value
                job.attempt_count += 1
                job.updated_at = now

                audit_event = JobEvent(
                    job_id=job.id,
                    event_type="STATE_CHANGED_TO_RUNNING",
                    details_json={
                        "from_state": "QUEUED",
                        "to_state": "RUNNING",
                        "attempt_number": job.attempt_count,
                        "worker_id": self.worker_id,
                        "claimed_from_queue": queue_name,
                    },
                    actor=self.worker_id,
                    created_at=now,
                )
                db.add(audit_event)

                stmt_w = select(Worker).where(Worker.worker_id == self.worker_id)
                res_w = await db.execute(stmt_w)
                worker = res_w.scalar_one_or_none()
                if worker:
                    worker.current_job_id = job.id
                    worker.last_heartbeat_at = now

                await db.commit()
                return job



        # 2. Direct database query fallback
        priority_order = case(
            (Job.priority == "HIGH", 1),
            (Job.priority == "DEFAULT", 2),
            (Job.priority == "LOW", 3),
            else_=4,
        )

        query = (
            select(Job)
            .where(
                Job.status == JobStatus.QUEUED.value,
                Job.scheduled_at <= now,
            )
            .order_by(priority_order.asc(), Job.scheduled_at.asc(), Job.created_at.asc())
            .limit(1)
        )

        try:
            locked_query = query.with_for_update(skip_locked=True)
            result = await db.execute(locked_query)
            job = result.scalar_one_or_none()
        except OperationalError:
            result = await db.execute(query)
            job = result.scalar_one_or_none()

        if not job:
            return None

        job.status = JobStatus.RUNNING.value
        job.attempt_count += 1
        job.updated_at = now

        audit_event = JobEvent(
            job_id=job.id,
            event_type="STATE_CHANGED_TO_RUNNING",
            details_json={
                "from_state": "QUEUED",
                "to_state": "RUNNING",
                "attempt_number": job.attempt_count,
                "worker_id": self.worker_id,
            },
            actor=self.worker_id,
            created_at=now,
        )
        db.add(audit_event)

        stmt_w = select(Worker).where(Worker.worker_id == self.worker_id)
        res_w = await db.execute(stmt_w)
        worker = res_w.scalar_one_or_none()
        if worker:
            worker.current_job_id = job.id
            worker.last_heartbeat_at = now

        await db.commit()
        return job




    async def execute_job(self, db: AsyncSession, job: Job) -> JobAttempt:
        """
        Executes the registered handler for the given job with timeout enforcement,
        persisting execution attempts and transitioning job state upon completion.
        """
        started_at = datetime.now(timezone.utc)
        outcome: str
        result: Any = None
        error_type: Optional[str] = None
        error_message: Optional[str] = None
        traceback_text: Optional[str] = None

        try:
            # 1. Retrieve registered task handler
            handler = get_task_handler(job.task_type)

            # 2. Execute task handler with timeout
            result = await asyncio.wait_for(
                execute_task_handler(handler, job.payload_json),
                timeout=float(job.timeout_seconds),
            )
            outcome = AttemptOutcome.SUCCEEDED.value

        except UnregisteredTaskError as err:
            outcome = AttemptOutcome.FAILED.value
            error_type = "UnregisteredTaskError"
            error_message = str(err)
            traceback_text = traceback.format_exc()

        except asyncio.TimeoutError:
            outcome = AttemptOutcome.TIMED_OUT.value
            error_type = "TimeoutError"
            error_message = f"Job execution timed out after {job.timeout_seconds} seconds"
            traceback_text = traceback.format_exc()

        except Exception as exc:
            outcome = AttemptOutcome.FAILED.value
            error_type = exc.__class__.__name__
            error_message = str(exc)
            traceback_text = traceback.format_exc()

        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        # 3. Create JobAttempt record
        attempt = JobAttempt(
            id=uuid.uuid4(),
            job_id=job.id,
            attempt_number=job.attempt_count,
            worker_id=self.worker_id,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            error_type=error_type,
            error_message=error_message,
            traceback_text=traceback_text,
            duration_ms=duration_ms,
        )
        db.add(attempt)

        # 4. Update Job terminal / retry status
        job.updated_at = finished_at
        extra_details: Dict[str, Any] = {}

        if outcome == AttemptOutcome.SUCCEEDED.value:
            job.status = JobStatus.SUCCEEDED.value
            job.result_json = result if isinstance(result, dict) else {"result": result}
            job.last_error = None
            next_event_type = "JOB_SUCCEEDED"
        else:
            job.last_error = f"{error_type}: {error_message}"
            if job.attempt_count >= job.max_retries or error_type == "UnregisteredTaskError":
                job.status = JobStatus.DEAD.value
                next_event_type = "JOB_DEAD"
                extra_details = {}
            else:
                delay_seconds = calculate_backoff_delay(job.attempt_count)
                job.scheduled_at = finished_at + timedelta(seconds=delay_seconds)
                job.status = JobStatus.RETRY_WAIT.value
                next_event_type = "JOB_RETRY_WAIT"
                extra_details = {
                    "retry_delay_seconds": delay_seconds,
                    "scheduled_at": job.scheduled_at.isoformat(),
                }

        # 5. Record audit event
        audit_event = JobEvent(
            job_id=job.id,
            event_type=next_event_type,
            details_json={
                "outcome": outcome,
                "attempt_number": job.attempt_count,
                "duration_ms": duration_ms,
                "worker_id": self.worker_id,
                "error": error_message,
                **extra_details,
            },
            actor=self.worker_id,
            created_at=finished_at,
        )
        db.add(audit_event)

        # 6. Reset worker's active job
        stmt_w = select(Worker).where(Worker.worker_id == self.worker_id)
        res_w = await db.execute(stmt_w)
        worker = res_w.scalar_one_or_none()
        if worker:
            worker.current_job_id = None
            worker.last_heartbeat_at = finished_at

        await db.commit()


        # 7. Release Redis lease if using Redis queue
        if self.redis_queue is not None:
            await self.redis_queue.release_lease(job.id, self.worker_id)

        return attempt



    async def run_once(self) -> Optional[JobAttempt]:
        """Runs a single claim-and-execute cycle. Returns the attempt or None if no jobs are ready."""
        async with self.session_factory() as db:
            await self.register_worker(db)
            job = await self.claim_job(db)
            if not job:
                return None
            return await self.execute_job(db, job)

    async def run_loop(self, poll_interval: float = 1.0, stop_event: Optional[asyncio.Event] = None) -> None:
        """Runs the continuous polling and execution loop until stop_event is signaled."""
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                attempt = await self.run_once()
                if not attempt:
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"Worker {self.worker_id} encountered unexpected loop error: {exc}", file=sys.stderr)
                await asyncio.sleep(poll_interval)

import uuid
import math
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models.job import Job
from app.models.outbox_event import OutboxEvent
from app.models.job_event import JobEvent
from app.models.job_attempt import JobAttempt
from app.schemas.job import JobCreate
from app.services.state_machine import JobStatus, validate_transition


class JobService:
    @staticmethod
    async def create_job(db: AsyncSession, job_in: JobCreate) -> Tuple[Job, bool]:
        """
        Creates a new job and enqueues an outbox event in the same atomic database transaction.
        If an idempotency key is provided and a job already exists with that key, returns the existing job.
        
        Returns:
            Tuple[Job, bool]: The job model and a boolean indicating whether it was newly created.
        """
        # 1. Idempotency check
        if job_in.idempotency_key:
            stmt = select(Job).where(Job.idempotency_key == job_in.idempotency_key)
            result = await db.execute(stmt)
            existing_job = result.scalar_one_or_none()
            if existing_job:
                return existing_job, False

        # 2. Build new Job model
        now = datetime.now(timezone.utc)
        scheduled_at = job_in.scheduled_at if job_in.scheduled_at is not None else now

        new_job = Job(
            id=uuid.uuid4(),
            task_type=job_in.task_type,
            payload_json=job_in.payload,
            status=JobStatus.QUEUED.value,
            priority=job_in.priority.value,
            idempotency_key=job_in.idempotency_key,
            scheduled_at=scheduled_at,
            max_retries=job_in.max_retries,
            attempt_count=0,
            timeout_seconds=job_in.timeout_seconds,
            created_at=now,
            updated_at=now,
        )

        # 3. Create OutboxEvent in the same transaction
        outbox_entry = OutboxEvent(
            id=uuid.uuid4(),
            job_id=new_job.id,
            event_type="JOB_CREATED",
            payload_json={
                "job_id": str(new_job.id),
                "task_type": new_job.task_type,
                "priority": new_job.priority,
                "scheduled_at": scheduled_at.isoformat(),
            },
            created_at=now,
            published_at=None,
            publish_attempts=0,
        )

        # 4. Create JobEvent audit record
        audit_event = JobEvent(
            job_id=new_job.id,
            event_type="JOB_CREATED",
            details_json={
                "task_type": new_job.task_type,
                "priority": new_job.priority,
                "max_retries": new_job.max_retries,
                "timeout_seconds": new_job.timeout_seconds,
                "scheduled_at": scheduled_at.isoformat(),
            },
            actor="CLIENT",
            created_at=now,
        )

        db.add(new_job)
        db.add(outbox_entry)
        db.add(audit_event)

        try:
            await db.commit()
            await db.refresh(new_job)
            return new_job, True
        except IntegrityError:
            # Handle concurrent race condition for the same idempotency key
            await db.rollback()
            if job_in.idempotency_key:
                stmt = select(Job).where(Job.idempotency_key == job_in.idempotency_key)
                result = await db.execute(stmt)
                existing_job = result.scalar_one_or_none()
                if existing_job:
                    return existing_job, False
            raise

    @staticmethod
    async def get_job(db: AsyncSession, job_id: uuid.UUID) -> Optional[Job]:
        """Fetches a single job by UUID."""
        stmt = select(Job).where(Job.id == job_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        task_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Job], int, int]:
        """
        Lists jobs with optional status/priority/task_type filtering and pagination.
        
        Returns:
            Tuple[List[Job], int, int]: (items, total_count, total_pages)
        """
        query = select(Job)
        count_query = select(func.count(Job.id))

        if status:
            query = query.where(Job.status == status)
            count_query = count_query.where(Job.status == status)
        if priority:
            query = query.where(Job.priority == priority)
            count_query = count_query.where(Job.priority == priority)
        if task_type:
            query = query.where(Job.task_type == task_type)
            count_query = count_query.where(Job.task_type == task_type)

        # Get total count
        total_res = await db.execute(count_query)
        total = total_res.scalar_one()

        # Apply sorting and pagination
        offset = (page - 1) * page_size
        query = query.order_by(Job.created_at.desc()).offset(offset).limit(page_size)
        items_res = await db.execute(query)
        items = list(items_res.scalars().all())

        pages = math.ceil(total / page_size) if total > 0 else 0
        return items, total, pages

    @staticmethod
    async def get_job_attempts(db: AsyncSession, job_id: uuid.UUID) -> List[JobAttempt]:
        """Fetches all execution attempts for a job ordered by attempt number."""
        stmt = (
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def retry_job(db: AsyncSession, job_id: uuid.UUID) -> Job:
        """
        Manually revives a DEAD job:
        - Validates the job exists and is in DEAD state.
        - Transitions state to QUEUED.
        - Resets scheduled_at = NOW(), attempt_count = 0, last_error = None.
        - Emits an atomic OutboxEvent to guarantee re-enqueueing to Redis.
        - Emits an immutable JobEvent audit record with actor='OPERATOR'.
        """
        job = await JobService.get_job(db, job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        # Validates transition from current status to QUEUED (allowed from DEAD)
        validate_transition(job.status, JobStatus.QUEUED, job_id=job.id)

        now = datetime.now(timezone.utc)
        from_status = job.status
        job.status = JobStatus.QUEUED.value
        job.scheduled_at = now
        job.attempt_count = 0
        job.last_error = None
        job.updated_at = now

        # Create outbox event to push to Redis
        outbox_entry = OutboxEvent(
            id=uuid.uuid4(),
            job_id=job.id,
            event_type="JOB_RETRIED",
            payload_json={
                "job_id": str(job.id),
                "task_type": job.task_type,
                "priority": job.priority,
                "scheduled_at": now.isoformat(),
            },
            created_at=now,
            published_at=None,
            publish_attempts=0,
        )

        # Create audit trail event
        audit_event = JobEvent(
            job_id=job.id,
            event_type="STATE_CHANGED_TO_QUEUED",
            details_json={
                "from_state": from_status,
                "to_state": "QUEUED",
                "reason": "MANUAL_RETRY",
            },
            actor="OPERATOR",
            created_at=now,
        )

        db.add(outbox_entry)
        db.add(audit_event)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def cancel_job(db: AsyncSession, job_id: uuid.UUID, redis_queue: Optional[Any] = None) -> Job:
        """
        Cancels a job in QUEUED, RETRY_WAIT, or RUNNING status:
        - If RUNNING, sets a Redis cancellation flag to notify cooperative workers.
        - Transitions job to CANCELLED in database.
        - Emits an immutable audit event in job_events.
        """
        job = await JobService.get_job(db, job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        if job.status in [JobStatus.SUCCEEDED.value, JobStatus.DEAD.value, JobStatus.CANCELLED.value]:
            raise ValueError(f"Cannot cancel job in terminal state '{job.status}'.")

        now = datetime.now(timezone.utc)
        from_status = job.status

        # If RUNNING, notify via Redis cooperative cancellation flag
        if job.status == JobStatus.RUNNING.value and redis_queue is not None:
            await redis_queue.set_cancellation_flag(job.id)

        job.status = JobStatus.CANCELLED.value
        job.updated_at = now

        audit_event = JobEvent(
            job_id=job.id,
            event_type="JOB_CANCELLED",
            details_json={
                "from_state": from_status,
                "to_state": "CANCELLED",
                "reason": "CLIENT_REQUESTED_CANCELLATION",
            },
            actor="CLIENT",
            created_at=now,
        )
        db.add(audit_event)
        await db.commit()
        await db.refresh(job)
        return job


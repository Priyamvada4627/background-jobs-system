import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_schedule import JobSchedule
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate


class ScheduleService:
    @staticmethod
    async def create_schedule(db: AsyncSession, schedule_in: ScheduleCreate) -> JobSchedule:
        """Creates and calculates the initial next_run_at timestamp for a new recurring schedule."""
        tz = ZoneInfo(schedule_in.timezone)
        now_local = datetime.now(tz)
        cron = croniter(schedule_in.cron_expression, now_local)
        next_local = cron.get_next(datetime)
        next_run_utc = next_local.astimezone(timezone.utc)

        schedule = JobSchedule(
            id=uuid.uuid4(),
            name=schedule_in.name,
            task_type=schedule_in.task_type,
            payload_json=schedule_in.payload,
            cron_expression=schedule_in.cron_expression,
            timezone=schedule_in.timezone,
            enabled=schedule_in.enabled,
            next_run_at=next_run_utc,
            last_run_at=None,
        )

        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)
        return schedule

    @staticmethod
    async def list_schedules(db: AsyncSession, enabled: Optional[bool] = None) -> List[JobSchedule]:
        """Lists recurring schedules, optionally filtered by active/enabled status."""
        stmt = select(JobSchedule)
        if enabled is not None:
            stmt = stmt.where(JobSchedule.enabled == enabled)
        stmt = stmt.order_by(JobSchedule.created_at.desc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_schedule(db: AsyncSession, schedule_id: uuid.UUID) -> Optional[JobSchedule]:
        """Retrieves a recurring schedule by ID."""
        stmt = select(JobSchedule).where(JobSchedule.id == schedule_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def update_schedule(
        db: AsyncSession,
        schedule_id: uuid.UUID,
        schedule_in: ScheduleUpdate,
    ) -> Optional[JobSchedule]:
        """Updates schedule properties, recomputing next_run_at if cron or timezone changes."""
        schedule = await ScheduleService.get_schedule(db, schedule_id)
        if not schedule:
            return None

        update_data = schedule_in.model_dump(exclude_unset=True)

        cron_changed = "cron_expression" in update_data and update_data["cron_expression"] != schedule.cron_expression
        tz_changed = "timezone" in update_data and update_data["timezone"] != schedule.timezone

        for field, value in update_data.items():
            if field == "payload":
                schedule.payload_json = value
            else:
                setattr(schedule, field, value)

        if cron_changed or tz_changed:
            tz = ZoneInfo(schedule.timezone)
            now_local = datetime.now(tz)
            cron = croniter(schedule.cron_expression, now_local)
            next_local = cron.get_next(datetime)
            schedule.next_run_at = next_local.astimezone(timezone.utc)

        schedule.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(schedule)
        return schedule

    @staticmethod
    async def delete_schedule(db: AsyncSession, schedule_id: uuid.UUID) -> bool:
        """Deletes a recurring schedule."""
        schedule = await ScheduleService.get_schedule(db, schedule_id)
        if not schedule:
            return False
        await db.delete(schedule)
        await db.commit()
        return True

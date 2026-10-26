import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleResponse,
    ScheduleListResponse,
)
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post(
    "",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a recurring job schedule",
    description="Registers a new cron schedule with timezone evaluation and sets the initial next_run_at timestamp.",
)
async def create_schedule(
    schedule_in: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    try:
        schedule = await ScheduleService.create_schedule(db, schedule_in)
        return ScheduleResponse.model_validate(schedule)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A schedule with the name '{schedule_in.name}' already exists.",
        )


@router.get(
    "",
    response_model=List[ScheduleResponse],
    summary="List recurring schedules",
    description="Retrieves registered cron schedules, optionally filtered by active status.",
)
async def list_schedules(
    enabled: Optional[bool] = Query(None, description="Filter by enabled/disabled status"),
    db: AsyncSession = Depends(get_db),
) -> List[ScheduleResponse]:
    items = await ScheduleService.list_schedules(db, enabled=enabled)
    return [ScheduleResponse.model_validate(item) for item in items]


@router.get(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Get schedule by ID",
    description="Retrieves a specific schedule including cron expression, next_run_at, and last_run_at.",
)
async def get_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    schedule = await ScheduleService.get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule with ID '{schedule_id}' not found.",
        )
    return ScheduleResponse.model_validate(schedule)


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Update a schedule",
    description="Updates cron expression, payload, enabled status, or timezone, recalculating next_run_at if needed.",
)
async def update_schedule(
    schedule_id: uuid.UUID,
    schedule_in: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    schedule = await ScheduleService.update_schedule(db, schedule_id, schedule_in)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule with ID '{schedule_id}' not found.",
        )
    return ScheduleResponse.model_validate(schedule)


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule",
    description="Deletes a recurring schedule permanently.",
)
async def delete_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await ScheduleService.delete_schedule(db, schedule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule with ID '{schedule_id}' not found.",
        )

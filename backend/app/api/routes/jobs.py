import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.job import JobCreate, JobResponse, JobListResponse
from app.schemas.attempt import JobAttemptResponse
from app.schemas.common import JobStatus, JobPriority
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a background job",
    description="Validates and persists a new background job and its outbox event inside a single atomic database transaction.",
)
async def submit_job(
    job_in: JobCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    job, created = await JobService.create_job(db, job_in)
    if not created:
        # If returning an existing job due to idempotency key, return HTTP 200 OK
        response.status_code = status.HTTP_200_OK
    return JobResponse.model_validate(job)


@router.get(
    "",
    response_model=JobListResponse,
    summary="List background jobs",
    description="Retrieve paginated list of jobs filtered optionally by status, priority, or task type.",
)
async def list_jobs(
    status: Optional[JobStatus] = Query(None, description="Filter by job status"),
    priority: Optional[JobPriority] = Query(None, description="Filter by priority lane"),
    task_type: Optional[str] = Query(None, description="Filter by task type identifier"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    items, total, pages = await JobService.list_jobs(
        db,
        status=status.value if status else None,
        priority=priority.value if priority else None,
        task_type=task_type,
        page=page,
        page_size=page_size,
    )
    return JobListResponse(
        items=[JobResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job by ID",
    description="Fetches current status, metadata, and results for a job.",
)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    job = await JobService.get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    return JobResponse.model_validate(job)


@router.get(
    "/{job_id}/attempts",
    response_model=List[JobAttemptResponse],
    summary="Get job execution attempts",
    description="Retrieves execution attempts, outcomes, duration, and error traces for a job.",
)
async def get_job_attempts(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[JobAttemptResponse]:
    job = await JobService.get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    attempts = await JobService.get_job_attempts(db, job_id)
    return [JobAttemptResponse.model_validate(att) for att in attempts]


@router.post(
    "/{job_id}/retry",
    response_model=JobResponse,
    summary="Manually retry a dead job",
    description="Revives a job in DEAD status, resetting its attempts and enqueueing an outbox event to re-process.",
)
async def retry_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    try:
        retried_job = await JobService.retry_job(db, job_id)
        return JobResponse.model_validate(retried_job)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(err),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a job",
    description="Transitions a QUEUED, RETRY_WAIT, or RUNNING job to CANCELLED and signals cooperative workers.",
)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    try:
        from app.queue.redis_queue import RedisQueue
        from app.queue.connection import get_redis_client
        redis_queue = RedisQueue(client=get_redis_client())
        cancelled_job = await JobService.cancel_job(db, job_id, redis_queue=redis_queue)
        return JobResponse.model_validate(cancelled_job)
    except ValueError as err:
        if "not found" in str(err).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(err),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


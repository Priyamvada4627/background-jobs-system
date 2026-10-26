from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db
from app.models.job import Job
from app.models.worker import Worker
from app.models.job_schedule import JobSchedule
from app.queue.redis_queue import RedisQueue
from app.queue.connection import get_redis_client

router = APIRouter(prefix="/stats", tags=["System Stats"])


@router.get(
    "",
    summary="Get aggregated system and dashboard statistics",
    description="Returns real-time queue depths, job counts grouped by status, and active worker counts.",
)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    # 1. Query Redis queue depths
    redis_client = get_redis_client()
    redis_queue = RedisQueue(client=redis_client)
    try:
        queue_depths = await redis_queue.get_all_queue_depths()
    except Exception:
        queue_depths = {"HIGH": 0, "DEFAULT": 0, "LOW": 0, "TOTAL": 0}

    # 2. Query Job counts by status from PostgreSQL
    status_stmt = select(Job.status, func.count(Job.id)).group_by(Job.status)
    status_res = await db.execute(status_stmt)
    status_counts = dict(status_res.all())

    all_statuses = ["QUEUED", "RUNNING", "SUCCEEDED", "RETRY_WAIT", "DEAD", "CANCELLED"]
    jobs_by_status = {s: status_counts.get(s, 0) for s in all_statuses}
    jobs_by_status["TOTAL"] = sum(jobs_by_status.values())

    # 3. Query Active Workers
    worker_stmt = select(Worker).where(Worker.status == "ALIVE").order_by(Worker.last_heartbeat_at.desc())
    worker_res = await db.execute(worker_stmt)
    active_workers = list(worker_res.scalars().all())

    # 4. Query Enabled Schedules count
    sched_stmt = select(func.count(JobSchedule.id)).where(JobSchedule.enabled.is_(True))
    sched_res = await db.execute(sched_stmt)
    enabled_schedules_count = sched_res.scalar_one()

    return {
        "queue_depths": queue_depths,
        "jobs_by_status": jobs_by_status,
        "active_workers_count": len(active_workers),
        "active_workers": [
            {
                "worker_id": w.worker_id,
                "hostname": w.hostname,
                "pid": w.pid,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "last_heartbeat_at": w.last_heartbeat_at.isoformat() if w.last_heartbeat_at else None,
                "current_job_id": str(w.current_job_id) if w.current_job_id else None,
                "capabilities": w.capabilities_json,
            }
            for w in active_workers
        ],
        "enabled_schedules_count": enabled_schedules_count,
    }

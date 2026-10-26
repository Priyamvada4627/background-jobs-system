from fastapi import APIRouter
from app.api.routes import health, jobs, schedules, stats, ws, dashboard
from app.core import metrics

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(schedules.router)
api_router.include_router(stats.router)
api_router.include_router(ws.router)
api_router.include_router(dashboard.router)
api_router.include_router(metrics.router)


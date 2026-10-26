from fastapi import APIRouter, status, Response
from pydantic import BaseModel
from typing import Dict, Any
from app.core.config import settings
from app.db.session import check_db_health
from app.queue.connection import check_redis_health

router = APIRouter(prefix="/health", tags=["Health"])


class LivenessResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str


class ServiceHealthDetail(BaseModel):
    status: str
    latency_ms: float | None = None
    error: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    services: Dict[str, ServiceHealthDetail]


@router.get(
    "",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description="Returns 200 OK if the FastAPI process is alive and responsive.",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    description="Verifies operational connectivity to PostgreSQL and Redis. Returns 503 if any dependency is down.",
)
async def readiness(response: Response) -> ReadinessResponse:
    db_health = await check_db_health()
    redis_health = await check_redis_health()

    services = {
        "database": ServiceHealthDetail(**db_health),
        "redis": ServiceHealthDetail(**redis_health),
    }

    all_healthy = all(svc.status == "healthy" for svc in services.values())
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", services=services)

    return ReadinessResponse(status="ready", services=services)

import time
from typing import Dict, Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings

_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Returns the singleton Redis async client instance."""
    global _redis_client
    if _redis_client is None:
        redis_url = settings.get_redis_url()
        extra_kwargs = {}
        if redis_url.startswith("rediss://"):
            extra_kwargs["ssl_cert_reqs"] = "none"

        _redis_client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=10.0,
            retry_on_timeout=True,
            **extra_kwargs,
        )
    return _redis_client


async def check_redis_health(timeout: float = 2.0) -> Dict[str, Any]:
    """Checks Redis connectivity by sending a PING command."""
    import asyncio
    client = get_redis_client()
    start_time = time.perf_counter()
    try:
        response = await asyncio.wait_for(client.ping(), timeout=timeout)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if response is True or response == "PONG":
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "error": None,
            }
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": f"Unexpected ping response: {response}",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(exc),
        }



async def close_redis_connection() -> None:
    """Closes the Redis connection pool on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None

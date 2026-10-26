import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "version" in data
    assert data["documentation"] == "/docs"


@pytest.mark.asyncio
async def test_liveness_endpoint(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Background Job System"
    assert "environment" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_healthy(async_client):
    with patch(
        "app.api.routes.health.check_db_health",
        new=AsyncMock(return_value={"status": "healthy", "latency_ms": 1.25, "error": None}),
    ), patch(
        "app.api.routes.health.check_redis_health",
        new=AsyncMock(return_value={"status": "healthy", "latency_ms": 0.82, "error": None}),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["services"]["database"]["status"] == "healthy"
        assert data["services"]["database"]["latency_ms"] == 1.25
        assert data["services"]["redis"]["status"] == "healthy"
        assert data["services"]["redis"]["latency_ms"] == 0.82


@pytest.mark.asyncio
async def test_readiness_db_failure(async_client):
    with patch(
        "app.api.routes.health.check_db_health",
        new=AsyncMock(return_value={"status": "unhealthy", "latency_ms": 50.0, "error": "Connection refused"}),
    ), patch(
        "app.api.routes.health.check_redis_health",
        new=AsyncMock(return_value={"status": "healthy", "latency_ms": 0.5, "error": None}),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["services"]["database"]["status"] == "unhealthy"
        assert data["services"]["database"]["error"] == "Connection refused"
        assert data["services"]["redis"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_redis_failure(async_client):
    with patch(
        "app.api.routes.health.check_db_health",
        new=AsyncMock(return_value={"status": "healthy", "latency_ms": 1.1, "error": None}),
    ), patch(
        "app.api.routes.health.check_redis_health",
        new=AsyncMock(return_value={"status": "unhealthy", "latency_ms": 25.0, "error": "Redis timeout"}),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["services"]["database"]["status"] == "healthy"
        assert data["services"]["redis"]["status"] == "unhealthy"
        assert data["services"]["redis"]["error"] == "Redis timeout"


@pytest.mark.asyncio
async def test_direct_db_health_success():
    from unittest.mock import MagicMock
    from app.db.session import check_db_health
    with patch("app.db.session.get_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        mock_cm.__aexit__.return_value = None
        mock_engine.connect.return_value = mock_cm
        mock_get_engine.return_value = mock_engine

        result = await check_db_health()
        assert result["status"] == "healthy"
        assert result["latency_ms"] is not None
        assert result["error"] is None


@pytest.mark.asyncio
async def test_direct_db_health_exception():
    from unittest.mock import MagicMock
    from app.db.session import check_db_health
    with patch("app.db.session.get_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("DB connection timeout")
        mock_get_engine.return_value = mock_engine

        result = await check_db_health()
        assert result["status"] == "unhealthy"
        assert "DB connection timeout" in result["error"]



@pytest.mark.asyncio
async def test_direct_redis_health_success():
    from app.queue.connection import check_redis_health
    with patch("app.queue.connection.get_redis_client") as mock_get_redis:
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_get_redis.return_value = mock_client

        result = await check_redis_health()
        assert result["status"] == "healthy"
        assert result["latency_ms"] is not None
        assert result["error"] is None


@pytest.mark.asyncio
async def test_direct_redis_health_exception():
    from app.queue.connection import check_redis_health
    with patch("app.queue.connection.get_redis_client") as mock_get_redis:
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("Redis unreachable")
        mock_get_redis.return_value = mock_client

        result = await check_redis_health()
        assert result["status"] == "unhealthy"
        assert "Redis unreachable" in result["error"]


@pytest.mark.asyncio
async def test_shutdown_cleanup():
    from app.db.session import close_db_connection, get_engine
    from app.queue.connection import close_redis_connection, get_redis_client

    # Initialize and then cleanly dispose
    get_engine()
    get_redis_client()
    await close_db_connection()
    await close_redis_connection()


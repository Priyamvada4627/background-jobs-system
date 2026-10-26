import pytest
from starlette.testclient import TestClient
from app.main import app
from app.api.ws_manager import ws_manager
from app.services.job_service import JobService
from app.schemas.job import JobCreate, JobPriority
from app.models.worker import Worker
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_get_system_stats(async_client, db_session):
    """Verifies GET /stats returns valid aggregated statistics matching database counts."""
    # Create two sample jobs in DB
    job1_in = JobCreate(task_type="email.send", priority=JobPriority.HIGH, payload={"to": "a@test.com"})
    job2_in = JobCreate(task_type="report.generate", priority=JobPriority.DEFAULT, payload={})
    await JobService.create_job(db_session, job1_in)
    await JobService.create_job(db_session, job2_in)

    # Register an active worker
    worker = Worker(
        worker_id="test-worker-stats-1",
        hostname="test-host",
        pid=1234,
        status="ALIVE",
        started_at=datetime.now(timezone.utc),
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    db_session.add(worker)
    await db_session.commit()

    resp = await async_client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert "queue_depths" in data
    assert "jobs_by_status" in data
    assert "active_workers_count" in data
    assert data["active_workers_count"] >= 1
    assert data["jobs_by_status"]["QUEUED"] >= 2
    assert data["jobs_by_status"]["TOTAL"] >= 2


@pytest.mark.asyncio
async def test_get_dashboard_html(async_client):
    """Verifies GET /dashboard returns self-contained operational HTML."""
    resp = await async_client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Background Job System" in resp.text
    assert "Active Workers" in resp.text


def test_websocket_connection_and_events():
    """Verifies WebSocket /ws lifecycle, greeting, ping-pong, and real-time broadcasts."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # 1. Verify greeting message
            greeting = ws.receive_json()
            assert greeting["event"] == "connected"
            assert "Background Job System stream" in greeting["data"]["message"]

            # 2. Verify ping / pong
            ws.send_text("ping")
            pong = ws.receive_text()
            assert pong == "pong"


@pytest.mark.asyncio
async def test_websocket_broadcast_integration():
    """Verifies ws_manager broadcasts to connected clients asynchronously."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # Consume greeting
            _ = ws.receive_json()

            # Broadcast an event
            await ws_manager.broadcast("test_event", {"job_id": "test-123", "status": "RUNNING"})

            # Client receives the broadcasted event
            msg = ws.receive_json()
            assert msg["event"] == "test_event"
            assert msg["data"]["job_id"] == "test-123"
            assert msg["data"]["status"] == "RUNNING"

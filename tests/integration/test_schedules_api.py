import pytest
import uuid
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_schedule(async_client: AsyncClient):
    """Verifies creating a new recurring schedule and fetching it by ID."""
    payload = {
        "name": f"hourly-hash-{uuid.uuid4().hex[:6]}",
        "task_type": "compute_hash",
        "payload": {"data": "scheduled-payload"},
        "cron_expression": "0 * * * *",
        "timezone": "UTC",
        "enabled": True,
    }

    res = await async_client.post("/schedules", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == payload["name"]
    assert data["cron_expression"] == "0 * * * *"
    assert data["next_run_at"] is not None
    assert data["enabled"] is True

    schedule_id = data["id"]

    # Fetch by ID
    get_res = await async_client.get(f"/schedules/{schedule_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == schedule_id


@pytest.mark.asyncio
async def test_create_schedule_duplicate_name_conflict(async_client: AsyncClient):
    """Verifies that creating two schedules with identical names returns HTTP 409 Conflict."""
    name = f"duplicate-name-{uuid.uuid4().hex[:6]}"
    payload = {
        "name": name,
        "task_type": "compute_hash",
        "cron_expression": "*/10 * * * *",
    }

    res1 = await async_client.post("/schedules", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/schedules", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_and_update_schedule(async_client: AsyncClient):
    """Verifies listing schedules, filtering by enabled status, and updating fields."""
    name = f"updatable-sched-{uuid.uuid4().hex[:6]}"
    create_res = await async_client.post(
        "/schedules",
        json={
            "name": name,
            "task_type": "compute_hash",
            "cron_expression": "0 0 * * *",
            "enabled": True,
        },
    )
    assert create_res.status_code == 201
    schedule_id = create_res.json()["id"]
    orig_next_run = create_res.json()["next_run_at"]

    # List schedules
    list_res = await async_client.get("/schedules?enabled=true")
    assert list_res.status_code == 200
    schedules = list_res.json()
    assert any(s["id"] == schedule_id for s in schedules)

    # Patch schedule (disable and change cron)
    patch_res = await async_client.patch(
        f"/schedules/{schedule_id}",
        json={"cron_expression": "*/5 * * * *", "enabled": False},
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["enabled"] is False
    assert patched["cron_expression"] == "*/5 * * * *"
    assert patched["next_run_at"] != orig_next_run


@pytest.mark.asyncio
async def test_delete_schedule(async_client: AsyncClient):
    """Verifies deleting a schedule by ID."""
    name = f"deletable-sched-{uuid.uuid4().hex[:6]}"
    create_res = await async_client.post(
        "/schedules",
        json={"name": name, "task_type": "compute_hash", "cron_expression": "0 12 * * *"},
    )
    schedule_id = create_res.json()["id"]

    del_res = await async_client.delete(f"/schedules/{schedule_id}")
    assert del_res.status_code == 204

    # Subsequent GET returns 404
    get_res = await async_client.get(f"/schedules/{schedule_id}")
    assert get_res.status_code == 404

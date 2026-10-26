import pytest
import uuid
from sqlalchemy import select
from app.models.outbox_event import OutboxEvent
from app.models.job_event import JobEvent
from app.models.job_attempt import JobAttempt


@pytest.mark.asyncio
async def test_create_job_success(async_client, db_session):
    payload = {
        "task_type": "send_welcome_email",
        "payload": {"user_id": "usr-123", "template": "welcome"},
        "priority": "HIGH",
        "max_retries": 5,
        "timeout_seconds": 120,
    }
    response = await async_client.post("/jobs", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["task_type"] == "send_welcome_email"
    assert data["status"] == "QUEUED"
    assert data["priority"] == "HIGH"
    assert data["max_retries"] == 5
    assert data["timeout_seconds"] == 120
    assert data["attempt_count"] == 0
    job_id = uuid.UUID(data["id"])

    # Verify that an OutboxEvent was created in the database atomically
    outbox_res = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.job_id == job_id)
    )
    outbox_events = list(outbox_res.scalars().all())
    assert len(outbox_events) == 1
    assert outbox_events[0].event_type == "JOB_CREATED"
    assert outbox_events[0].payload_json["job_id"] == str(job_id)
    assert outbox_events[0].payload_json["priority"] == "HIGH"

    # Verify that an initial audit JobEvent was recorded
    event_res = await db_session.execute(
        select(JobEvent).where(JobEvent.job_id == job_id)
    )
    audit_events = list(event_res.scalars().all())
    assert len(audit_events) == 1
    assert audit_events[0].event_type == "JOB_CREATED"
    assert audit_events[0].actor == "CLIENT"


@pytest.mark.asyncio
async def test_create_job_idempotency(async_client, db_session):
    idempotency_key = "idemp-unique-token-999"
    payload = {
        "task_type": "deduplicated_task",
        "payload": {"counter": 1},
        "idempotency_key": idempotency_key,
    }

    # First request: Creates the job (201 Created)
    res1 = await async_client.post("/jobs", json=payload)
    assert res1.status_code == 201
    job1 = res1.json()

    # Second request: Returns the existing job without creating a duplicate (200 OK)
    res2 = await async_client.post(
        "/jobs",
        json={
            "task_type": "deduplicated_task",
            "payload": {"counter": 2},  # Different payload
            "idempotency_key": idempotency_key,
        },
    )
    assert res2.status_code == 200
    job2 = res2.json()

    # IDs must match
    assert job1["id"] == job2["id"]
    assert job2["payload_json"] == {"counter": 1}  # Original payload preserved

    # Verify only 1 OutboxEvent exists
    outbox_res = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.job_id == uuid.UUID(job1["id"]))
    )
    assert len(list(outbox_res.scalars().all())) == 1


@pytest.mark.asyncio
async def test_get_job_by_id(async_client):
    # Create job
    create_res = await async_client.post(
        "/jobs", json={"task_type": "lookup_task", "payload": {"foo": "bar"}}
    )
    assert create_res.status_code == 201
    created_job = create_res.json()
    job_id = created_job["id"]

    # Fetch existing job
    get_res = await async_client.get(f"/jobs/{job_id}")
    assert get_res.status_code == 200
    fetched_job = get_res.json()
    assert fetched_job["id"] == job_id
    assert fetched_job["task_type"] == "lookup_task"
    assert fetched_job["status"] == "QUEUED"

    # Non-existent UUID
    fake_id = str(uuid.uuid4())
    missing_res = await async_client.get(f"/jobs/{fake_id}")
    assert missing_res.status_code == 404
    assert f"Job with ID '{fake_id}' not found." in missing_res.json()["detail"]


@pytest.mark.asyncio
async def test_list_jobs_filtering_and_pagination(async_client):
    # Create 3 distinct jobs
    await async_client.post("/jobs", json={"task_type": "sync_user", "priority": "HIGH"})
    await async_client.post("/jobs", json={"task_type": "sync_user", "priority": "LOW"})
    await async_client.post("/jobs", json={"task_type": "backup_db", "priority": "HIGH"})

    # 1. List all jobs
    res_all = await async_client.get("/jobs")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total"] == 3
    assert len(data_all["items"]) == 3
    assert data_all["pages"] == 1

    # 2. Filter by task_type
    res_task = await async_client.get("/jobs?task_type=sync_user")
    data_task = res_task.json()
    assert data_task["total"] == 2
    assert all(item["task_type"] == "sync_user" for item in data_task["items"])

    # 3. Filter by priority
    res_pri = await async_client.get("/jobs?priority=HIGH")
    data_pri = res_pri.json()
    assert data_pri["total"] == 2
    assert all(item["priority"] == "HIGH" for item in data_pri["items"])

    # 4. Filter by priority and task_type
    res_both = await async_client.get("/jobs?priority=HIGH&task_type=sync_user")
    data_both = res_both.json()
    assert data_both["total"] == 1
    assert data_both["items"][0]["task_type"] == "sync_user"
    assert data_both["items"][0]["priority"] == "HIGH"

    # 5. Pagination
    page_1 = await async_client.get("/jobs?page=1&page_size=2")
    data_p1 = page_1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["total"] == 3
    assert data_p1["pages"] == 2

    page_2 = await async_client.get("/jobs?page=2&page_size=2")
    data_p2 = page_2.json()
    assert len(data_p2["items"]) == 1
    assert data_p2["total"] == 3


@pytest.mark.asyncio
async def test_get_job_attempts(async_client, db_session):
    # Create job
    create_res = await async_client.post("/jobs", json={"task_type": "attempt_task"})
    job_id = uuid.UUID(create_res.json()["id"])

    # Insert 2 attempts directly into DB
    attempt1 = JobAttempt(
        job_id=job_id,
        attempt_number=1,
        worker_id="worker-node-1",
        outcome="FAILED",
        error_type="TimeoutError",
        error_message="Network timed out",
        duration_ms=5000,
    )
    attempt2 = JobAttempt(
        job_id=job_id,
        attempt_number=2,
        worker_id="worker-node-2",
        outcome="SUCCEEDED",
        duration_ms=1200,
    )
    db_session.add(attempt1)
    db_session.add(attempt2)
    await db_session.commit()

    # Query attempts endpoint
    res = await async_client.get(f"/jobs/{job_id}/attempts")
    assert res.status_code == 200
    attempts = res.json()
    assert len(attempts) == 2
    assert attempts[0]["attempt_number"] == 1
    assert attempts[0]["outcome"] == "FAILED"
    assert attempts[0]["error_type"] == "TimeoutError"
    assert attempts[1]["attempt_number"] == 2
    assert attempts[1]["outcome"] == "SUCCEEDED"

    # Query attempts for non-existent job
    missing_res = await async_client.get(f"/jobs/{uuid.uuid4()}/attempts")
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_create_job_validation_rejection(async_client):
    # Invalid task type containing invalid punctuation
    res = await async_client.post("/jobs", json={"task_type": "bad task name!"})
    assert res.status_code == 422

    # Negative timeout
    res = await async_client.post("/jobs", json={"task_type": "valid_task", "timeout_seconds": -5})
    assert res.status_code == 422

    # Invalid priority
    res = await async_client.post("/jobs", json={"task_type": "valid_task", "priority": "SUPER_HIGH"})
    assert res.status_code == 422

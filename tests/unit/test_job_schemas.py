import pytest
from pydantic import ValidationError
from app.schemas.job import JobCreate
from app.schemas.common import JobPriority


def test_valid_job_create():
    job = JobCreate(
        task_type="send_email",
        payload={"to": "user@example.com"},
        priority=JobPriority.HIGH,
        idempotency_key="unique-key-123",
        max_retries=5,
        timeout_seconds=600,
    )
    assert job.task_type == "send_email"
    assert job.payload == {"to": "user@example.com"}
    assert job.priority == JobPriority.HIGH
    assert job.idempotency_key == "unique-key-123"
    assert job.max_retries == 5
    assert job.timeout_seconds == 600


def test_job_create_defaults():
    job = JobCreate(task_type="default_task")
    assert job.payload == {}
    assert job.priority == JobPriority.DEFAULT
    assert job.idempotency_key is None
    assert job.max_retries == 3
    assert job.timeout_seconds == 300
    assert job.scheduled_at is None


def test_invalid_task_type_characters():
    # Disallowed characters: spaces, slashes, punctuation
    invalid_types = ["task with space", "task;injection", "task/slash", "task@email", ""]
    for t in invalid_types:
        with pytest.raises(ValidationError):
            JobCreate(task_type=t)


def test_invalid_timeout_seconds():
    # Less than 1 second
    with pytest.raises(ValidationError):
        JobCreate(task_type="task", timeout_seconds=0)

    with pytest.raises(ValidationError):
        JobCreate(task_type="task", timeout_seconds=-10)

    # Greater than 86400 (24 hours)
    with pytest.raises(ValidationError):
        JobCreate(task_type="task", timeout_seconds=90000)


def test_invalid_max_retries():
    # Less than 0
    with pytest.raises(ValidationError):
        JobCreate(task_type="task", max_retries=-1)

    # Greater than 20
    with pytest.raises(ValidationError):
        JobCreate(task_type="task", max_retries=21)


def test_invalid_priority():
    with pytest.raises(ValidationError):
        JobCreate(task_type="task", priority="CRITICAL")

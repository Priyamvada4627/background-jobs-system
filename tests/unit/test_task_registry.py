import pytest
from app.tasks.registry import (
    register_task,
    get_task_handler,
    list_registered_tasks,
    execute_task_handler,
    UnregisteredTaskError,
)


def test_list_registered_tasks_contains_defaults():
    tasks = list_registered_tasks()
    assert "compute_hash" in tasks
    assert "mock_email" in tasks
    assert "sleep_task" in tasks
    assert "simulate_failure" in tasks


def test_get_registered_task_handler():
    handler = get_task_handler("compute_hash")
    assert callable(handler)


def test_get_unregistered_task_raises_error():
    with pytest.raises(UnregisteredTaskError) as exc_info:
        get_task_handler("malicious_arbitrary_code")

    assert "malicious_arbitrary_code" in str(exc_info.value)
    assert exc_info.value.task_type == "malicious_arbitrary_code"


def test_duplicate_registration_rejected():
    with pytest.raises(ValueError) as exc_info:
        @register_task("compute_hash")
        def duplicate_handler(payload):
            pass

    assert "already registered" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_sync_handler():
    def sync_add(payload):
        return payload["a"] + payload["b"]

    result = await execute_task_handler(sync_add, {"a": 10, "b": 25})
    assert result == 35


@pytest.mark.asyncio
async def test_execute_async_handler():
    async def async_concat(payload):
        return f"{payload['prefix']}-{payload['suffix']}"

    result = await execute_task_handler(async_concat, {"prefix": "job", "suffix": "123"})
    assert result == "job-123"

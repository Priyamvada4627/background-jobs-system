import pytest
import hashlib
from app.tasks.handlers.sample_tasks import compute_hash, mock_email, sleep_task, simulate_failure


def test_compute_hash():
    data = "hello world"
    expected = hashlib.sha256(data.encode("utf-8")).hexdigest()
    res = compute_hash({"data": data})

    assert res["algorithm"] == "sha256"
    assert res["hash"] == expected
    assert res["input_length"] == len(data)


@pytest.mark.asyncio
async def test_mock_email():
    res = await mock_email({
        "to": "alice@example.com",
        "subject": "System Alert",
        "body": "Your weekly batch finished.",
    })

    assert res["sent"] is True
    assert res["to"] == "alice@example.com"
    assert res["subject"] == "System Alert"
    assert "msg-" in res["message_id"]


@pytest.mark.asyncio
async def test_sleep_task():
    res = await sleep_task({"duration_seconds": 0.05})
    assert res["slept_seconds"] == 0.05
    assert res["status"] == "completed"


def test_simulate_failure_exceptions():
    with pytest.raises(ValueError) as exc:
        simulate_failure({"error_message": "custom failure"})
    assert "custom failure" in str(exc.value)

    with pytest.raises(RuntimeError):
        simulate_failure({"error_type": "RuntimeError", "error_message": "fatal error"})

    with pytest.raises(KeyError):
        simulate_failure({"error_type": "KeyError", "error_message": "missing key"})

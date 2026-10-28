import hashlib
import uuid
import asyncio
from typing import Dict, Any
from app.tasks.registry import register_task


@register_task("compute_hash")
def compute_hash(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Computes SHA-256 hash of provided data string."""
    text_data = str(payload.get("data") or payload.get("text") or "")
    hasher = hashlib.sha256()
    hasher.update(text_data.encode("utf-8"))
    hex_digest = hasher.hexdigest()
    return {
        "algorithm": "sha256",
        "hash": hex_digest,
        "input_length": len(text_data),
    }


@register_task("mock_email")
async def mock_email(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates asynchronous email dispatch."""
    recipient = payload.get("to", "user@example.com")
    subject = payload.get("subject", "Notification")
    body = payload.get("body", "")

    # Lightweight async pause simulating network latency
    await asyncio.sleep(0.01)

    message_id = f"msg-{uuid.uuid4().hex[:12]}"
    return {
        "sent": True,
        "to": recipient,
        "subject": subject,
        "body_preview": body[:50],
        "message_id": message_id,
    }


@register_task("sleep_task")
async def sleep_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronously sleeps for a bounded duration (up to 60s)."""
    duration = min(float(payload.get("duration_seconds", 0.1)), 60.0)
    await asyncio.sleep(duration)
    return {
        "slept_seconds": duration,
        "status": "completed",
    }


@register_task("simulate_failure")
def simulate_failure(payload: Dict[str, Any]) -> None:
    """Intentionally raises an exception for testing error handling and retries."""
    error_type = payload.get("error_type", "ValueError")
    message = payload.get("error_message", "Simulated task execution failure")

    if error_type == "RuntimeError":
        raise RuntimeError(message)
    elif error_type == "KeyError":
        raise KeyError(message)
    else:
        raise ValueError(message)


# =============================================================================
# Dashboard & Production Presets
# =============================================================================

@register_task("email.send")
async def email_send(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates email delivery."""
    recipient = payload.get("recipient") or payload.get("to", "user@example.com")
    subject = payload.get("subject", "System Notification")
    await asyncio.sleep(0.05)
    return {
        "status": "delivered",
        "recipient": recipient,
        "subject": subject,
        "message_id": f"msg-{uuid.uuid4().hex[:12]}",
    }


@register_task("report.generate")
async def report_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates PDF report generation."""
    report_type = payload.get("report_type", "monthly_summary")
    await asyncio.sleep(0.1)
    return {
        "report_id": f"rep-{uuid.uuid4().hex[:8]}",
        "report_type": report_type,
        "format": "PDF",
        "pages": 14,
    }


@register_task("data.export")
async def data_export(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates CSV/JSON dataset export."""
    dataset = payload.get("dataset", "users")
    await asyncio.sleep(0.1)
    return {
        "export_id": f"exp-{uuid.uuid4().hex[:8]}",
        "dataset": dataset,
        "record_count": 1250,
        "download_url": f"https://storage.internal/exports/{dataset}.csv",
    }


@register_task("thumbnail.generate")
def thumbnail_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates image thumbnail processing."""
    image_id = payload.get("image_id", str(uuid.uuid4()))
    return {
        "image_id": image_id,
        "dimensions": {"width": 200, "height": 200},
        "format": "jpeg",
        "status": "generated",
    }


@register_task("test.flaky_task")
def test_flaky_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates a task failure for testing retries and DLQ."""
    raise ValueError(payload.get("error_message", "Simulated transient failure for testing retries"))


@register_task("test.slow_task")
async def test_slow_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates a longer task execution for testing worker concurrency."""
    duration = min(float(payload.get("duration_seconds", 2.0)), 30.0)
    await asyncio.sleep(duration)
    return {"status": "completed", "duration_seconds": duration}

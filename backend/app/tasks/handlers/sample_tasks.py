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

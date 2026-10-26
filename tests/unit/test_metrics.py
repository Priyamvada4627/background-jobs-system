import pytest
from app.core.metrics import (
    JOB_SUBMISSIONS_TOTAL,
    JOB_EXECUTIONS_TOTAL,
    JOB_EXECUTION_DURATION_SECONDS,
)


@pytest.mark.asyncio
async def test_metrics_endpoint(async_client):
    """Verifies that GET /metrics returns 200 and standard Prometheus exposition format."""
    # Observe some metric values
    JOB_SUBMISSIONS_TOTAL.labels(task_type="test.metric_task", priority="DEFAULT").inc()
    JOB_EXECUTIONS_TOTAL.labels(task_type="test.metric_task", outcome="SUCCEEDED").inc()
    JOB_EXECUTION_DURATION_SECONDS.labels(task_type="test.metric_task").observe(0.125)

    resp = await async_client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text

    assert "job_submissions_total" in text
    assert "job_executions_total" in text
    assert "job_execution_duration_seconds" in text
    assert 'task_type="test.metric_task"' in text

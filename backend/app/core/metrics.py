from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    REGISTRY,
)
from fastapi import APIRouter, Response

# Central Prometheus Metrics Definitions

JOB_SUBMISSIONS_TOTAL = Counter(
    "job_submissions_total",
    "Total number of jobs submitted to the system",
    ["task_type", "priority"],
)

JOB_EXECUTIONS_TOTAL = Counter(
    "job_executions_total",
    "Total number of job execution attempts finished",
    ["task_type", "outcome"],
)

JOB_EXECUTION_DURATION_SECONDS = Histogram(
    "job_execution_duration_seconds",
    "Latency of job execution in seconds",
    ["task_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

REDIS_QUEUE_DEPTH = Gauge(
    "redis_queue_depth",
    "Number of jobs currently waiting in Redis priority queue lane",
    ["priority"],
)

ACTIVE_WORKERS_GAUGE = Gauge(
    "active_workers_total",
    "Number of currently alive worker processes",
)

OUTBOX_PUBLISHED_TOTAL = Counter(
    "outbox_published_events_total",
    "Total number of outbox events published to Redis queues",
)

LEASE_REAPER_REAPED_TOTAL = Counter(
    "lease_reaper_reaped_jobs_total",
    "Total expired running jobs reaped by lease reaper",
    ["action"],  # 'requeued' or 'marked_dead'
)

router = APIRouter(tags=["Metrics"])


@router.get(
    "/metrics",
    summary="Prometheus Metrics Exporter",
    description="Exposes real-time system, queue, and execution metrics in Prometheus exposition format.",
)
async def metrics() -> Response:
    """Returns Prometheus formatted metrics."""
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

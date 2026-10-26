# Background Job System — REST & WebSocket API Specification

This document provides a comprehensive reference for the Background Job Management System HTTP REST endpoints and real-time WebSocket protocol.

---

## 1. Base URL & Protocol

| Environment | Base URL | Protocol |
|:---|:---|:---|
| Local Development | `http://localhost:8000` | HTTP / WebSocket (`ws://localhost:8000/ws`) |
| Interactive Swagger Docs | `http://localhost:8000/docs` | OpenAPI 3.1 JSON: `/openapi.json` |
| ReDoc Reference | `http://localhost:8000/redoc` | Static Documentation |
| Operational Web Dashboard | `http://localhost:8000/dashboard` | HTML5 / Single-Page Application |

---

## 2. Health & Readiness

### `GET /health`
Liveness probe checking whether the application process is online and responsive.

- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development"
}
```

### `GET /health/ready`
Readiness probe verifying connectivity to both the PostgreSQL primary database and the Redis coordination layer.

- **Response `200 OK` (Healthy)**:
```json
{
  "status": "ready",
  "database": {
    "status": "connected",
    "latency_ms": 1.2
  },
  "redis": {
    "status": "connected",
    "latency_ms": 0.8
  }
}
```
- **Response `503 Service Unavailable`**: Returned if either PostgreSQL or Redis cannot be reached.

---

## 3. Jobs Management API

### `POST /jobs`
Submits a new task for asynchronous background execution. Atomically enqueues the job into PostgreSQL and records a transactional outbox event.

- **Request Headers**:
  - `Content-Type: application/json`
  - `Idempotency-Key: <string>` *(Optional, enforces deduplication)*
- **Request Body**:
```json
{
  "task_type": "email.send",
  "payload": {
    "recipient": "user@example.com",
    "subject": "Monthly Statement"
  },
  "priority": "HIGH",
  "max_retries": 3,
  "timeout_seconds": 60,
  "scheduled_at": "2026-10-26T22:30:00Z",
  "idempotency_key": "order-charge-98214"
}
```
- **Fields**:
  - `task_type` *(string, required)*: Identifier matching a handler registered with `@register_task`.
  - `payload` *(object, optional, default `{}`)*: JSON arguments passed to the task handler.
  - `priority` *(string, optional, default `"DEFAULT"`)*: `"HIGH"`, `"DEFAULT"`, or `"LOW"`.
  - `max_retries` *(int, optional, default `3`)*: Max retry attempts before entering `DEAD` (DLQ).
  - `timeout_seconds` *(int, optional, default `60`)*: Execution timeout in seconds.
  - `scheduled_at` *(ISO-8601 string, optional)*: Defer execution until specified time.
  - `idempotency_key` *(string, optional)*: Deduplication key. Duplicate submissions return the existing job.
- **Response `201 Created`**:
```json
{
  "id": "e4b9d0b8-9b88-4c3e-9086-42d449f87c2b",
  "task_type": "email.send",
  "payload": { "recipient": "user@example.com" },
  "status": "QUEUED",
  "priority": "HIGH",
  "idempotency_key": "order-charge-98214",
  "scheduled_at": "2026-10-26T22:30:00Z",
  "max_retries": 3,
  "attempt_count": 0,
  "timeout_seconds": 60,
  "last_error": null,
  "result": null,
  "created_at": "2026-10-26T22:00:00Z",
  "updated_at": "2026-10-26T22:00:00Z"
}
```

---

### `GET /jobs`
Lists jobs with pagination and filtering.

- **Query Parameters**:
  - `status`: Filter by state (`QUEUED`, `RUNNING`, `SUCCEEDED`, `RETRY_WAIT`, `DEAD`, `CANCELLED`).
  - `priority`: Filter by priority (`HIGH`, `DEFAULT`, `LOW`).
  - `task_type`: Filter by task identifier string.
  - `page`: Page number (default `1`).
  - `page_size`: Items per page (default `20`, max `100`).
- **Response `200 OK`**:
```json
{
  "items": [ ... ],
  "total": 482,
  "page": 1,
  "page_size": 20,
  "total_pages": 25
}
```

---

### `GET /jobs/{job_id}`
Retrieves canonical job details along with its complete historical execution attempts and audit event trail.

- **Response `200 OK`**:
```json
{
  "id": "e4b9d0b8-9b88-4c3e-9086-42d449f87c2b",
  "task_type": "email.send",
  "payload": { "recipient": "user@example.com" },
  "status": "SUCCEEDED",
  "priority": "HIGH",
  "attempt_count": 1,
  "max_retries": 3,
  "timeout_seconds": 60,
  "result": { "sent": true, "message_id": "msg-9821" },
  "last_error": null,
  "created_at": "2026-10-26T22:00:00Z",
  "updated_at": "2026-10-26T22:00:02Z",
  "attempts": [
    {
      "id": "787c88e1-5ef6-4df1-bc91-23d3876e5d8b",
      "attempt_number": 1,
      "worker_id": "worker-node-1",
      "started_at": "2026-10-26T22:00:01Z",
      "finished_at": "2026-10-26T22:00:02Z",
      "outcome": "SUCCEEDED",
      "duration_ms": 1140,
      "error_message": null,
      "traceback_text": null
    }
  ]
}
```

---

### `POST /jobs/{job_id}/retry`
Manually moves a `DEAD` or `CANCELLED` job back to `QUEUED` status, resetting attempt counts and enqueuing an outbox event.

- **Response `200 OK`**: Returns updated Job object with `status: "QUEUED"` and `attempt_count: 0`.

---

### `POST /jobs/{job_id}/cancel`
Requests cancellation of a `QUEUED`, `RUNNING`, or `RETRY_WAIT` job:
- If `QUEUED` or `RETRY_WAIT`: Immediately transitioned to `CANCELLED`.
- If `RUNNING`: Sets a Redis cooperative cancellation flag (`cancellation:job:{id}`). Workers check this flag and terminate gracefully without applying side effects.

- **Response `200 OK`**: Returns updated Job object with `status: "CANCELLED"`.

---

## 4. Recurring Schedules API

### `POST /schedules`
Creates a new recurring cron schedule.

- **Request Body**:
```json
{
  "name": "Hourly Cleanup",
  "cron_expression": "0 * * * *",
  "timezone": "UTC",
  "task_type": "system.cleanup",
  "payload": { "retention_days": 7 },
  "priority": "LOW",
  "max_retries": 2,
  "timeout_seconds": 300,
  "enabled": true
}
```

### `GET /schedules`
Lists all registered cron schedules.

### `PATCH /schedules/{id}`
Updates schedule attributes (e.g. `cron_expression`, `enabled`, `payload`).

### `DELETE /schedules/{id}`
Deletes a scheduled job definition.

---

## 5. Metrics & Dashboard

### `GET /stats`
Returns aggregated real-time system metrics:
- Queue depths across HIGH, DEFAULT, LOW lanes.
- Job counts grouped by status.
- Alive worker node details and capabilities.
- Active schedule counts.

### `GET /metrics`
Prometheus metrics exposition endpoint for scraping via Prometheus server.

---

## 6. Real-Time WebSocket Protocol

### Connection: `ws://localhost:8000/ws`
Streams live state transition events without polling overhead.

- **Initial Greeting Event**:
```json
{
  "event": "connected",
  "data": {
    "message": "Connected to real-time Background Job System stream.",
    "timestamp": "2026-10-26T22:00:00Z"
  }
}
```

- **Broadcast Events**:
  - `job_created`: Job accepted and queued.
  - `job_running`: Worker claimed job and commenced execution.
  - `job_finished`: Job concluded (`SUCCEEDED`, `RETRY_WAIT`, `DEAD`, or `CANCELLED`).
  - `job_cancelled`: Manual cancellation initiated.
  - `job_retried`: Manual retry initiated.

- **Heartbeat**: Client may send text `"ping"`; server responds with `"pong"`.

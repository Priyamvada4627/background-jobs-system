# Background Job Management System — Architecture Specification

## 1. System Overview

The **Background Job Management System** is a distributed task queue and execution engine designed for reliable, observable, and resilient background task processing. It provides durable job persistence, atomic queue coordination, transactional outbox publishing, worker heartbeat leasing, lease-reaping failure recovery, dead-letter queue (DLQ) inspection, and real-time dashboard visibility.

### 1.1 Core Design Tenets
1. **PostgreSQL as the Durable Source of Truth**: All job definitions, lifecycle states, attempts, audit logs, and recurring schedules reside in PostgreSQL with relational integrity.
2. **Redis as the Transient Coordination Engine**: Redis is used for high-throughput ready queues, priority lanes, worker leases, distributed locks, and rate-limiting buckets. A failure or flush of Redis never results in data loss; queue state can be reconstructed from PostgreSQL.
3. **At-Least-Once Execution Guarantees**: Exactly-once execution is physically impossible in distributed systems subject to arbitrary network partitions and crashes. Tasks are executed with at-least-once semantics, requiring task handlers to be idempotent or state-guarded.
4. **No Arbitrary Client Code Execution**: Handlers are registered in a trusted in-code registry. Clients submit structured task type identifiers and JSON payloads, strictly validated against predefined schemas.
5. **Decoupled Failure Domains**: API ingestion, outbox dispatching, worker execution, scheduled promotion, and dead lease reaping operate in isolated processes.

---

## 2. Architecture & Component Diagram

```
                             +-----------------------+
                             |   Client / Frontend   |
                             +-----------+-----------+
                                         | HTTP / WebSocket
                                         v
+-----------------------------------------------------------------------------------+
| FastAPI Application (Producer & Visibility)                                       |
|  - Validates request payload against Pydantic schema                              |
|  - Validates & locks idempotency key                                              |
|  - Enforces tenant & global rate limits                                           |
|  - Inserts job & outbox_event within single PostgreSQL transaction                |
|  - Exposes REST API, WebSocket streams, & Prometheus metrics                      |
+--------------------------+------------------------------------+-------------------+
                           |                                    ^
          Database Writes  |                                    | Live Queries / WS
                           v                                    |
+---------------------------------------------------------------+-------------------+
| PostgreSQL (Durable Source of Truth)                                              |
|  - Tables: jobs, job_attempts, job_schedules, outbox_events, workers, job_events  |
|  - ACID transactions, conditional transitions, state history                      |
+--------------------------+--------------------------------------------------------+
                           |
             Polls Unsent  |
             Outbox Rows   v
+-----------------------------------------------------------------------------------+
| Outbox Publisher Process                                                          |
|  - Reads pending outbox_events from PostgreSQL                                    |
|  - Atomically enqueues job references into Redis priority lanes                   |
|  - Marks outbox_events as published (idempotent, batch-capable)                   |
+--------------------------+--------------------------------------------------------+
                           |
          Pushes to Queues |
                           v
+-----------------------------------------------------------------------------------+
| Redis (Coordination & Ephemeral Queue Layer)                                      |
|  - Priority Ready Queues: queue:high, queue:default, queue:low                    |
|  - Delayed ZSET: jobs:delayed (sorted by target execution timestamp)              |
|  - Worker Leases & Heartbeats: worker:lease:{job_id}, worker:hb:{worker_id}       |
|  - Concurrency & Rate Limiting: token buckets & sliding windows                   |
+--------------------------+--------------------------------------------------------+
                           |
       Atomic Claim (BRPOP | or Lua script)
                           v
+-----------------------------------------------------------------------------------+
| Worker Pool (Custom Python Workers)                                               |
|  - Claims job from Redis atomically; acquires lease in Redis                      |
|  - Updates job status to RUNNING in PostgreSQL (guarded by attempt number)        |
|  - Spawns background heartbeat task to maintain lease                             |
|  - Invokes static registered handler with timeout and cancellation token          |
|  - Records attempt, output/traceback, and terminal state in PostgreSQL             |
+-----------------------------------------------------------------------------------+
                           ^
                           | Periodic Audit & State Checks
+--------------------------+--------------------------------------------------------+
| Maintenance Daemons                                                               |
|  1. Custom Scheduler:                                                             |
|     - Promotes due delayed jobs from PostgreSQL/Redis to ready queues             |
|     - Evaluates cron schedules idempotently with explicit timezone handling       |
|  2. Lease Reaper:                                                                 |
|     - Scans for RUNNING jobs with expired leases or dead worker heartbeats        |
|     - Uses attempt-fencing to avoid split-brain overwrites                         |
|     - Safely requeues or transitions abandoned jobs to DEAD                       |
+-----------------------------------------------------------------------------------+
```

---

## 3. Component Responsibilities

### 3.1 Producer (FastAPI API)
- Validates job submissions (task type, payload, priority, timeout, retry policy).
- Enforces idempotency via PostgreSQL unique constraints and Redis short-term keys.
- Writes the `jobs` row and corresponding `outbox_events` row inside the **same atomic database transaction**.
- Never pushes directly to Redis in the synchronous request path, eliminating dual-write divergence if Redis is temporarily unreachable.
- Serves queries, filtered lists, pagination, manual retries, cancellations, and real-time WebSocket updates.

### 3.2 Transactional Outbox Publisher
- Continually polls or listens for unpublished `outbox_events` in PostgreSQL.
- Pushes job identifiers to the appropriate Redis priority lane (`queue:high`, `queue:default`, `queue:low`).
- Updates `outbox_events.published_at` upon confirmation from Redis.
- If Redis is down, outbox entries accumulate safely in PostgreSQL and drain automatically once Redis recovers.

### 3.3 Redis Queue & Coordination Layer
- **Priority Queues**: List data structures for `queue:high`, `queue:default`, and `queue:low`.
- **Fairness Policy**: Workers employ a weighted dequeue strategy (e.g., 60% high, 30% default, 10% low) to guarantee low-priority tasks are not starved.
- **Worker Leases**: Key `lease:job:{job_id}` with TTL (e.g., 30s) refreshed periodically by the executing worker.
- **Worker Registry**: Hash/Set `workers:active` storing worker metadata and last heartbeat timestamp.

### 3.4 Worker Engine
- Independent processes separate from the web API.
- Executes registered handlers matching the requested `task_type`.
- Maintains a lease in Redis with an asynchronous heartbeat loop every $N$ seconds ($TTL / 3$).
- Enforces task-level timeouts using `asyncio.wait_for` or OS signals for synchronous tasks.
- Respects cooperative cancellation tokens checked by handlers during long iterations.
- Logs structured JSON events containing `job_id`, `attempt_id`, `worker_id`, `task_type`, and duration.

### 3.5 Lease Reaper
- Scans for jobs stuck in `RUNNING` or `RECOVERY_PENDING` whose worker lease has expired and worker heartbeat has lapsed.
- Uses conditional database queries with **fencing tokens** (checking `attempt_count` hasn't progressed) to prevent split-brain overwrites if a delayed worker resumes.
- If attempts remain under `max_retries`, transitions state back to `QUEUED` and re-inserts into Redis; otherwise moves job to `DEAD`.

### 3.6 Scheduler Process
- **Delayed Jobs**: Queries `jobs` where `status = 'QUEUED'` and `scheduled_at <= NOW()`, publishing them to Redis ready queues.
- **Recurring Jobs**: Parses cron expressions using `croniter` with explicit UTC or specified timezones. Evaluates `next_run_at`, acquires a distributed execution lock, creates the child job transactionally, and advances `job_schedules.next_run_at`.

### 3.7 Retry Engine & Dead Letter Queue (DLQ)
- Intercepts failed executions and calculates backoff:
  $$\text{delay} = \min(\text{max\_delay}, \text{base\_delay} \times 2^{\text{attempt}}) \pm \text{jitter}$$
- Retries are stored with `status = 'RETRY_WAIT'` and `scheduled_at = NOW() + delay`.
- When `attempt_count >= max_retries`, transitions job to `DEAD`.
- Dead jobs retain full error message, error type, stack trace, and execution history.
- API provides `POST /jobs/{job_id}/retry` to revive a dead job with audit history.

---

## 4. Job Lifecycle & State Machine

```
                   +------------------+
                   |  (Client Post)   |
                   +--------+---------+
                            |
                            v
                   +------------------+
          +------->|      QUEUED      |<--------------------+
          |        +--------+---------+                     |
          |                 |                               |
          |                 | Worker Claims Job             |
          |                 v                               |
          |        +------------------+                     |
          |        |     RUNNING      |                     |
          |        +---+----+----+----+                     |
          |            |    |    |                          |
          | Success    |    |    | Lease Expired            |
          |            |    |    v                          |
          |            |    |  +-----------------------+    |
          |            |    |  |   RECOVERY_PENDING    |    |
          |            |    |  +-----------+-----------+    |
          |            |    |              |                |
          |            |    |              +----------------+
          |            |    |              | (Retries left)
          |            |    |              |
          v            |    |              v (Retries exhausted)
+------------------+   |    |         +----------+
|    SUCCEEDED     |   |    |         |   DEAD   |
+------------------+   |    |         +----+-----+
                       |    |              ^
      Failure / Error  |    |              |
                       v    |              |
+------------------+        |              |
|    RETRY_WAIT    |--------+--------------+
+--------+---------+  (Attempts >= Max)
         |
         | Delay Expired
         v
     [ QUEUED ]
```

### 4.1 State Definitions
- `QUEUED`: Job is committed and waiting in Redis for worker pickup or waiting for scheduled time.
- `RUNNING`: Job is claimed by an active worker holding a valid lease.
- `SUCCEEDED`: Job handler completed successfully; return value stored in `result_json`.
- `RETRY_WAIT`: Job failed with a retryable error; waiting for backoff duration to elapse before re-entering `QUEUED`.
- `DEAD`: Job exceeded maximum retries or suffered a non-retryable fatal error. Retained for debugging and manual intervention.
- `CANCELLED`: Job was cancelled before or during execution.
- `RECOVERY_PENDING`: Worker lease expired without completion; flagged for reaper analysis.

### 4.2 Valid Transition Matrix
| From State | Allowed To States | Guard / Condition |
| :--- | :--- | :--- |
| `QUEUED` | `RUNNING`, `CANCELLED` | Conditional UPDATE matching status=`QUEUED` |
| `RUNNING` | `SUCCEEDED`, `RETRY_WAIT`, `DEAD`, `CANCELLED`, `RECOVERY_PENDING` | Must hold active lease and matching `attempt_count` |
| `RETRY_WAIT`| `QUEUED`, `CANCELLED` | Backoff delay elapsed (`scheduled_at <= NOW()`) |
| `RECOVERY_PENDING` | `QUEUED`, `DEAD` | Reaper verification with fencing token |
| `DEAD` | `QUEUED` | Manual operator retry API (`POST /jobs/{id}/retry`) |
| `SUCCEEDED` | None (Terminal) | Immutable terminal state |
| `CANCELLED` | None (Terminal) | Immutable terminal state |

---

## 5. Database Schema & Data Models

### 5.1 Tables

```sql
-- 1. Core Jobs Table
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type VARCHAR(128) NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
    priority VARCHAR(16) NOT NULL DEFAULT 'DEFAULT', -- HIGH, DEFAULT, LOW
    idempotency_key VARCHAR(255) UNIQUE,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    max_retries INT NOT NULL DEFAULT 3,
    attempt_count INT NOT NULL DEFAULT 0,
    timeout_seconds INT NOT NULL DEFAULT 300,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    result_json JSONB,
    last_error TEXT
);

CREATE INDEX idx_jobs_status_priority_created ON jobs(status, priority, created_at);
CREATE INDEX idx_jobs_scheduled_at ON jobs(scheduled_at) WHERE status = 'QUEUED' OR status = 'RETRY_WAIT';
CREATE INDEX idx_jobs_task_type ON jobs(task_type);

-- 2. Execution Attempts
CREATE TABLE job_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    attempt_number INT NOT NULL,
    worker_id VARCHAR(128) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(32) NOT NULL, -- SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, ABANDONED
    error_type VARCHAR(255),
    error_message TEXT,
    traceback_text TEXT,
    duration_ms INT,
    CONSTRAINT uq_job_attempt UNIQUE (job_id, attempt_number)
);

CREATE INDEX idx_job_attempts_job_id ON job_attempts(job_id);

-- 3. Recurring Schedules
CREATE TABLE job_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL UNIQUE,
    task_type VARCHAR(128) NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    cron_expression VARCHAR(64) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMPTZ NOT NULL,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_job_schedules_next_run ON job_schedules(next_run_at) WHERE enabled = TRUE;

-- 4. Transactional Outbox
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL, -- JOB_CREATED, JOB_RETRY, JOB_CANCEL
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    published_at TIMESTAMPTZ,
    publish_attempts INT NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_events_unpublished ON outbox_events(created_at) WHERE published_at IS NULL;

-- 5. Registered Workers
CREATE TABLE workers (
    worker_id VARCHAR(128) PRIMARY KEY,
    hostname VARCHAR(255) NOT NULL,
    pid INT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    status VARCHAR(32) NOT NULL DEFAULT 'ALIVE', -- ALIVE, DEAD, DRAINING
    current_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    capabilities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_workers_heartbeat ON workers(last_heartbeat_at);

-- 6. Job Lifecycle Audit Events
CREATE TABLE job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_job_events_job_id_created ON job_events(job_id, created_at);
```

---

## 6. Distributed Consistency, Leases & Fencing

### 6.1 Transactional Outbox (Dual-Write Prevention)
When an API client submits a job:
1. An open PostgreSQL transaction begins.
2. The `jobs` row is inserted.
3. The `outbox_events` row is inserted with the job ID and priority lane.
4. The transaction commits.

The separate `OutboxPublisher`:
1. Selects batches of unpublished outbox events using `FOR UPDATE SKIP LOCKED`.
2. Emits them to Redis priority queues.
3. Updates `published_at = clock_timestamp()`.
4. If Redis is temporarily down, the database transaction rolls back publication mark, retrying on the next tick. No jobs are lost.

### 6.2 Worker Leases and Monotonic Fencing
- When a worker claims a job, it acquires a lease in Redis: `SET lease:job:{job_id} {worker_id} EX 30 NX`.
- The worker increments `jobs.attempt_count` and records `started_at` in `job_attempts`.
- While executing, the worker extends the lease every 10 seconds.
- **Fencing Protection**: When updating the job state upon completion, the worker executes:
  ```sql
  UPDATE jobs 
  SET status = 'SUCCEEDED', result_json = :result, updated_at = NOW()
  WHERE id = :job_id AND attempt_count = :my_attempt_count AND status = 'RUNNING';
  ```
  If a zombie worker was paused by garbage collection or network isolation and the reaper already timed it out and started attempt #2, the query updates 0 rows. The zombie worker detects this fencing mismatch and safely discards its result.

---

## 7. Operational Visibility, Metrics & Observability

### 7.1 Prometheus Metrics
- `jobs_submitted_total{task_type, priority}`: Total jobs submitted.
- `jobs_completed_total{task_type, outcome}`: Outcomes (`succeeded`, `failed`, `cancelled`).
- `job_queue_depth{priority}`: Number of ready jobs pending in Redis.
- `job_execution_duration_seconds{task_type}`: Histogram of handler execution times.
- `job_queue_wait_duration_seconds{priority}`: Latency between creation and execution start.
- `worker_heartbeats_active`: Current live workers reporting healthy.
- `lease_reaper_recoveries_total`: Number of abandoned jobs recovered.

### 7.2 Structured JSON Logging
Every log entry emits structured fields:
```json
{
  "timestamp": "2026-10-26T14:15:22.102Z",
  "level": "INFO",
  "logger": "app.workers.engine",
  "message": "Job execution finished",
  "job_id": "7d9b92e7-91a6-4299-9137-567c9d10e5d0",
  "attempt": 1,
  "worker_id": "worker-prod-01-pid-4912",
  "task_type": "send_welcome_email",
  "duration_ms": 245,
  "status": "SUCCEEDED"
}
```

---

## 8. Summary of Architectural Guarantees
- **Durable Persistence**: All job definitions and execution states survive complete process and queue crashes.
- **Fair Priority Processing**: High-priority jobs are prioritized without completely starving lower-priority queues.
- **Safe Recovery**: Abandoned tasks are reliably detected and reclaimed without duplicate execution of subsequent attempts.
- **Idempotency Protection**: Enforced both at API ingestion and via recommended idempotent task handler patterns.
- **Extensibility**: Clean abstraction separating API, Storage, Queue, Scheduler, and Execution.

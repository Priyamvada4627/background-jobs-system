# Background Job System — Operational Runbooks & Architecture Guide

This guide covers production operations, runbooks for common incidents, disaster recovery procedures, and capacity tuning recommendations.

---

## 1. System Architecture & Responsibilities

```
                      +-----------------------------+
                      |   FastAPI REST / WS API     |
                      |  - Job Ingestion (Outbox)   |
                      |  - Live WebSocket Stream    |
                      +--------------+--------------+
                                     |
               +---------------------+---------------------+
               |                                           |
               v                                           v
    +--------------------+                       +-------------------+
    |    PostgreSQL      |                       |       Redis       |
    |  Durable Source of |                       | Transient Queues  |
    |      Truth         |                       | & Lease Manager   |
    +---------+----------+                       +---------+---------+
              ^                                            ^
              |                                            |
    +---------+----------+                       +---------+---------+
    |  Outbox Publisher  +---------------------->| Priority Queues   |
    |  (Reliable Drain)  |                       | (6:3:1 Weighted)  |
    +--------------------+                       +---------+---------+
                                                           |
                                                           v
                                                 +-------------------+
                                                 | Worker Engines    |
                                                 | - Heartbeat Lease |
                                                 | - Fencing Check   |
                                                 +-------------------+
```

### Core Tenets
1. **PostgreSQL is the durable source of truth**: No job state change or execution attempt is deemed committed unless recorded in PostgreSQL.
2. **Redis is transient coordination**: Redis manages instant queue popping, renewable worker leases, rate limiters, and scheduler leader locks.
3. **At-Least-Once Execution**: Handlers MUST be idempotent. Never assume exactly-once processing across network boundaries.

---

## 2. Operational Runbooks

### Runbook 1: Redis Crash, Failover, or Network Partition
- **Symptoms**:
  - API logs show `RedisConnectionError` on job creation or `/stats`.
  - Workers log errors claiming tasks from Redis.
- **System Behavior**:
  - Ingestion continues smoothly! Jobs and Outbox events are committed durably to PostgreSQL.
  - The Transactional Outbox Publisher pauses with exponential backoff without dropping events.
- **Recovery Procedure**:
  1. Restart or failover Redis:
     ```bash
     docker compose restart redis
     ```
  2. Verify Redis connectivity:
     ```bash
     docker compose exec redis redis-cli ping
     ```
  3. Ensure the Outbox Publisher is active. It will automatically drain all buffered PostgreSQL events into the newly recovered Redis queues:
     ```bash
     python -m app.services.outbox_cli
     ```
  4. Inspect queue depths via `GET /stats` or the `/dashboard` UI to confirm queues are draining.

---

### Runbook 2: Zombie Worker & Expired Lease Detection
- **Symptoms**:
  - A long-running task freezes or a worker process is terminated (`SIGKILL`).
  - Job remains in `RUNNING` status without heartbeats.
- **Root Cause**:
  - Worker died before releasing lease or reporting final outcome.
- **System Behavior**:
  - The Redis lease TTL (30s) expires.
  - The `LeaseReaper` daemon periodically scans `RUNNING` jobs in PostgreSQL lacking an active lease in Redis.
  - If retries remain (`attempt_count < max_retries`), the reaper resets `status = QUEUED` and re-inserts the job into Redis.
  - If the dead worker awakens as a zombie and tries to write back its result, the **monotonic fencing token check** (`Job.attempt_count == attempt_number and Job.status == 'RUNNING'`) detects the state advance, aborts the write, and emits a `ZOMBIE_WORKER_FENCED_OUT` audit event.
- **Recovery / Verification**:
  1. Trigger or verify the Lease Reaper daemon:
     ```bash
     python -m app.services.reaper_cli
     ```
  2. Query `job_events` for fencing alerts:
     ```sql
     SELECT * FROM job_events WHERE event_type = 'ZOMBIE_WORKER_FENCED_OUT' ORDER BY created_at DESC;
     ```

---

### Runbook 3: Dead Letter Queue (DLQ) Reprocessing
- **Symptoms**:
  - `metricDead` counter increases on the dashboard or Prometheus alerts fire for `job_executions_total{outcome="FAILED"}`.
- **Procedure**:
  1. Open `/dashboard` and filter jobs by `status = DEAD`.
  2. Click **View** on a dead job to inspect:
     - The input payload.
     - The error type, message, and full traceback from each attempt.
  3. Resolve the underlying upstream issue (e.g. invalid credentials, external API downtime, schema mismatch).
  4. Manually retry the job:
     - Via UI: Click the **Retry** button on the job row.
     - Via CLI / REST API:
       ```bash
       curl -X POST http://localhost:8000/jobs/<JOB_ID>/retry
       ```
  5. The job transitions back to `QUEUED` and an outbox event immediately re-enqueues it to Redis.

---

### Runbook 4: Priority Starvation Prevention
- **Design Safeguard**:
  - The Redis Queue employs a **6:3:1 Weighted Fair Schedule** rotation across `HIGH`, `DEFAULT`, and `LOW` priority queues.
  - Even under an infinite flood of `HIGH` priority jobs, 10% of worker capacity is guaranteed to process `LOW` priority jobs, and 30% to `DEFAULT`.
- **Tuning**:
  - To increase high priority bias (e.g., 8:1:1), modify `RedisQueue.FAIRNESS_SCHEDULE` in `app/queue/redis_queue.py`.

---

## 3. Worker Scaling & Sizing Guidelines

| Metric | Recommendation |
|:---|:---|
| CPU / Concurrency Ratio | 1 worker process per CPU core for CPU-bound tasks; 4-10 coroutines per worker for I/O-bound tasks |
| DB Connection Pool | Set `pool_size` in `app/core/config.py` to `workers * 2 + 10` |
| Lease Heartbeat Interval | Heartbeat every `TTL / 3` (e.g. 10s heartbeat for 30s lease) |
| Outbox Batch Size | Default 50 items; increase to 200 for high-throughput bursts (>1,000 jobs/sec) |

---

## 4. Periodic Maintenance Tasks

1. **Purge Completed Audit Logs**:
   ```sql
   DELETE FROM job_events WHERE created_at < NOW() - INTERVAL '30 days';
   ```
2. **Vacuum PostgreSQL Tables**:
   ```sql
   VACUUM ANALYZE jobs;
   VACUUM ANALYZE job_attempts;
   VACUUM ANALYZE outbox_events;
   ```

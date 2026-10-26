# Background Job Management System — Implementation Plan

This document outlines the phased build plan for the Background Job Management System. Each phase builds sequentially on prior work, prioritizes correctness and failure recovery, includes targeted tests, and must pass its acceptance criteria before progressing.

---

## Phase Overview

| Phase | Title | Core Objective | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **0** | **Discovery & Planning** | Baseline architecture and phased roadmap | `docs/architecture.md`, `docs/implementation-plan.md`, base layout |
| **1** | **Foundation & Environment** | Runnable skeleton, config, and dependency baseline | FastAPI app, DB/Redis config, health endpoints, Pytest config, Docker Compose |
| **2** | **Schema & Job API** | Durable models, migrations, and CRUD/state machine | Alembic migrations, SQLAlchemy models, Pydantic schemas, `JobService`, State Machine |
| **3** | **Task Registry & Worker** | Safe task execution engine outside the API | Task registry, standalone worker loop, attempt recorder, sample handlers |
| **4** | **Redis Queue & Atomic Claiming** | Atomic job distribution with priority lanes | Redis priority queues (`high`, `default`, `low`), Lua claim script, competing worker tests |
| **5** | **Transactional Outbox** | Zero data loss between PostgreSQL and Redis | Outbox table, background publisher process, at-least-once enqueue tests |
| **6** | **Retries & Dead Letter Queue** | Exponential backoff, jitter, and DLQ inspection | Backoff calculator, DLQ state transition, manual retry endpoint, audit events |
| **7** | **Delayed & Recurring Schedules** | Time-based scheduling and cron automation | Delayed queue poller, cron expression evaluator, distributed scheduler lock |
| **8** | **Leases, Heartbeats & Reaper** | Abandoned job recovery and zombie fencing | Worker heartbeat daemon, Redis lease TTL, reaper process, monotonic fencing checks |
| **9** | **Idempotency, Throttling & Cancel** | Duplicate prevention, rate limits, and cancellation | Idempotency middleware/table, Redis token-bucket rate limiter, cooperative cancellation |
| **10**| **Frontend Dashboard & WebSockets** | Real-time administrative visibility and controls | React + TypeScript SPA, WebSocket stream, job inspector, queue charts, action buttons |
| **11**| **Observability & Benchmarks** | Metrics, structured telemetry, and load testing | Prometheus metrics, Grafana dashboards, structured JSON logger, benchmark script |
| **12**| **Hardening, CI & Documentation** | Production readiness and test verification | GitHub Actions CI workflow, chaos/failure tests, API reference, deployment guide |

---

## Detailed Phase Specifications

### Phase 0: Repository Discovery & Plan (Current)
- **Goal**: Establish the repository layout, architectural blueprint, and staged plan.
- **Scope**:
  - Inspect repository (empty initially).
  - Create directory layout: `backend/`, `frontend/`, `tests/`, `infra/`, `docs/`.
  - Author `docs/architecture.md` and `docs/implementation-plan.md`.
  - Create `.gitignore` and `.env.example`.
- **Acceptance Criteria**:
  - System architecture, component responsibilities, state transitions, and phased implementation steps are fully documented.
  - Zero code changes from later phases are introduced prematurely.

---

### Phase 1: Project Foundation & Local Environment
- **Goal**: Establish a runnable Python backend environment with configuration, dependency management, health checks, and container infrastructure.
- **Scope**:
  - `backend/pyproject.toml` with pinned dependencies (`fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `asyncpg` / `psycopg2-binary`, `redis`, `pydantic-settings`, `pytest`, `pytest-asyncio`, `httpx`).
  - Configuration management in `backend/app/core/config.py` using `pydantic_settings.BaseSettings` reading environment variables.
  - Database session lifecycle in `backend/app/db/session.py` (engine, async session factory, connection health test).
  - Redis connection client in `backend/app/queue/connection.py`.
  - Health check endpoints in `backend/app/api/routes/health.py`:
    - `GET /health` (liveness check)
    - `GET /health/ready` (readiness check verifying PostgreSQL and Redis connections)
  - `infra/docker-compose.yml` for PostgreSQL 16 and Redis 7 with persistent volumes and health checks.
  - Initial tests in `tests/unit/test_health.py` and `tests/unit/test_config.py`.
- **Acceptance Criteria**:
  - Application starts with `uvicorn app.main:app`.
  - `GET /health` returns 200 OK.
  - `GET /health/ready` checks DB and Redis readiness.
  - Pytest runs and passes cleanly.

---

### Phase 2: Schema, Migrations & Job API
- **Goal**: Implement durable database models, migration scripts, centralized state transition logic, and REST endpoints for job submission and inspection.
- **Scope**:
  - SQLAlchemy models in `backend/app/models/`:
    - `Job`, `JobAttempt`, `JobSchedule`, `OutboxEvent`, `Worker`, `JobEvent`.
  - Alembic configuration and initial migration in `backend/alembic/`.
  - Centralized state machine in `backend/app/services/state_machine.py`:
    - Enforces valid state transitions: `QUEUED -> RUNNING -> SUCCEEDED / RETRY_WAIT / DEAD / CANCELLED`.
    - Prevents arbitrary, out-of-order status updates.
  - Pydantic schemas in `backend/app/schemas/`:
    - `JobCreate`, `JobResponse`, `JobAttemptResponse`, `JobListParams`.
  - API Routes in `backend/app/api/routes/jobs.py`:
    - `POST /jobs`: Create a new job.
    - `GET /jobs`: Filter and paginate jobs by status, priority, task_type.
    - `GET /jobs/{job_id}`: Retrieve job status and details.
    - `GET /jobs/{job_id}/attempts`: Retrieve execution attempts.
- **Acceptance Criteria**:
  - Alembic migration executes successfully on a clean database.
  - Tests verify valid state transitions and reject illegal transitions (e.g. `SUCCEEDED -> RUNNING`).
  - API endpoints correctly persist and return jobs with input validation.

---

### Phase 3: Registered Task Handlers & Single Worker Process
- **Goal**: Build a standalone worker process that claims a job from the database, executes an authorized registered handler, and persists the execution attempt and result.
- **Scope**:
  - Task registry in `backend/app/tasks/registry.py`:
    - Decorator `@register_task(name)` for registering safe Python callables.
    - Explicit rejection of unregistered or arbitrary code execution.
    - Sample tasks: `compute_hash`, `send_mock_email`, `simulate_failure`.
  - Worker execution engine in `backend/app/workers/engine.py`:
    - Loop claiming single `QUEUED` job.
    - Updates job status to `RUNNING` conditionally.
    - Records start time and attempt in `job_attempts`.
    - Executes task handler with timeout.
    - On success: updates status to `SUCCEEDED`, stores `result_json`.
    - On exception: updates status to `FAILED`/`RETRY_WAIT`, stores error details and traceback.
- **Acceptance Criteria**:
  - API process and worker process run independently.
  - Submitting a job via API is processed and completed by the worker.
  - Execution outcome, duration, and attempts are persisted to PostgreSQL.

---

### Phase 4: Redis Queue & Atomic Claiming
- **Goal**: Move ready job dispatching to Redis with priority lanes and atomic claim semantics.
- **Scope**:
  - Redis queue manager in `backend/app/queue/redis_queue.py`:
    - Lanes: `queue:high`, `queue:default`, `queue:low`.
    - Weighted or priority BRPOP claiming script.
    - Atomic pop-and-lease coordination via Lua scripts.
  - Fair queue dequeue strategy to avoid starvation of low-priority tasks.
  - Integration tests with multiple concurrent workers competing for the same queue entries.
- **Acceptance Criteria**:
  - Concurrent workers never claim the same job entry twice.
  - High-priority jobs are executed before default/low priority jobs under load, without starving low priority.

---

### Phase 5: Transactional Outbox Publisher & Consistency Recovery
- **Goal**: Guarantee zero loss of jobs between PostgreSQL writes and Redis queue publishing using the Transactional Outbox Pattern.
- **Scope**:
  - `POST /jobs` writes `jobs` and `outbox_events` in the same database transaction.
  - Outbox Publisher daemon in `backend/app/services/outbox_publisher.py`:
    - Polls unpublished outbox rows using `SELECT ... FOR UPDATE SKIP LOCKED`.
    - Enqueues jobs to Redis.
    - Marks `published_at = NOW()` on successful Redis write.
    - Exponential backoff if Redis is unavailable.
- **Acceptance Criteria**:
  - Simulating a Redis outage during job creation retains the job in PostgreSQL outbox.
  - When Redis comes back online, the publisher automatically enqueues all pending jobs without duplication.

---

### Phase 6: Retries, Backoff & Dead Letter Queue (DLQ)
- **Goal**: Implement resilient error handling with exponential backoff, bounded jitter, DLQ transitions, and manual recovery.
- **Scope**:
  - Backoff algorithm in `backend/app/services/retry_policy.py`:
    $$\text{delay} = \min(\text{max\_delay}, \text{base\_delay} \times 2^{\text{attempt}}) + \text{uniform}(0, \text{jitter})$$
  - Failed job transitions to `RETRY_WAIT` until `scheduled_at`.
  - Jobs with `attempt_count >= max_retries` transition to `DEAD`.
  - API endpoint: `POST /jobs/{job_id}/retry` to revive a dead job, resetting attempt count or incrementing retry generation with an audit trail in `job_events`.
- **Acceptance Criteria**:
  - Retries follow exponential delay schedule with jitter.
  - Terminal failures transition to `DEAD` with full stack traces.
  - Manual retry successfully re-enqueues the job and logs an audit event.

---

### Phase 7: Delayed & Recurring Jobs
- **Goal**: Support one-off future execution and recurring cron schedules.
- **Scope**:
  - Delayed job promotion:
    - Jobs with `scheduled_at > NOW()` remain in `QUEUED` / `RETRY_WAIT`.
    - Scheduler poller promotes due jobs to Redis ready queues.
  - Recurring schedule manager in `backend/app/scheduler/cron_scheduler.py`:
    - Evaluates cron expressions with timezone handling via `zoneinfo`.
    - Employs distributed locking (`scheduler:lock`) to ensure only one instance generates recurring occurrences.
    - Creates recurring job instances idempotently.
  - API routes: `POST /schedules`, `GET /schedules`, `PATCH /schedules/{id}`.
- **Acceptance Criteria**:
  - Delayed jobs do not run before their scheduled timestamp.
  - Cron schedules generate exactly one job per interval across scheduler restarts and concurrent replicas.

---

### Phase 8: Worker Heartbeat, Leases & Reaper
- **Goal**: Recover abandoned tasks when workers crash or suffer network isolation, using renewable leases and monotonic fencing tokens.
- **Scope**:
  - Worker heartbeat daemon:
    - Periodically renews `worker:lease:{job_id}` in Redis and updates `workers.last_heartbeat_at` in PostgreSQL.
  - Lease Reaper process:
    - Scans for jobs stuck in `RUNNING` whose lease expired.
    - Checks fencing token (`attempt_count`).
    - If retryable, requeues the job; otherwise moves to `DEAD`.
  - Zombie protection:
    - If a delayed worker wakes up after lease expiry, its completion write fails conditional database fencing checks.
- **Acceptance Criteria**:
  - Killing a worker process (`kill -9`) triggers lease expiration and reaper re-enqueue.
  - Resumed zombie worker cannot overwrite newer attempt results.

---

### Phase 9: Idempotency, Cancellation & Throttling
- **Goal**: Prevent duplicate job submissions, support safe task cancellation, and enforce concurrency and rate limits.
- **Scope**:
  - Idempotency key handling in `POST /jobs`:
    - Returns existing job if submitted with the same idempotency key.
  - Cancellation:
    - `POST /jobs/{job_id}/cancel`.
    - Queued jobs immediately transition to `CANCELLED`.
    - Running jobs have cancellation flag set in Redis; workers cooperatively check token during execution.
  - Rate limiting & concurrency throttles:
    - Token-bucket algorithm in Redis per tenant or global task type.
- **Acceptance Criteria**:
  - Duplicate submissions return the original job without creating duplicate records.
  - Cancelled jobs do not run; running cooperative tasks stop promptly when cancellation is requested.
  - Concurrency limits are strictly respected under load.

---

### Phase 10: Frontend Dashboard & WebSockets
- **Goal**: Provide an operational web interface for queue inspection, job drill-down, attempt history, and manual controls.
- **Scope**:
  - React + TypeScript SPA in `frontend/`:
    - Overview cards: active workers, queue depth by priority, failure rates.
    - Jobs table with status filtering, task type search, pagination.
    - Job detail modal: payload, result, execution timeline, attempt tracebacks.
    - Action buttons: Retry dead job, Cancel running/queued job.
  - WebSocket integration in FastAPI:
    - Emits state transition events (`job:created`, `job:started`, `job:completed`, `job:failed`).
    - Frontend auto-updates without manual page refresh, with graceful fallback to HTTP polling.
- **Acceptance Criteria**:
  - UI renders correctly, connects to API and WebSocket stream.
  - Manual retry/cancel triggered from UI executes and updates status in real time.

---

### Phase 11: Observability & Benchmarks
- **Goal**: Instrument the entire system with Prometheus metrics, structured JSON logging, and reproducible performance benchmarks.
- **Scope**:
  - Prometheus metrics exporter at `GET /metrics`:
    - Queue depths, execution latency histograms, throughput counters, error rates.
  - Grafana dashboard JSON in `infra/grafana/dashboards/`.
  - Structured JSON logger formatted for ingestion (e.g. Datadog, Loki, Elasticsearch).
  - Benchmark script in `backend/scripts/benchmark.py`:
    - Measures sustained throughput (jobs/sec), p50/p95 latency across varying worker counts.
- **Acceptance Criteria**:
  - Metrics endpoint returns valid Prometheus formatted data.
  - Benchmark script executes and outputs throughput and latency metrics under load.

---

### Phase 12: Hardening, CI & Documentation
- **Goal**: Finalize test coverage with failure injection, setup CI automation, and complete operational documentation.
- **Scope**:
  - GitHub Actions CI workflow in `.github/workflows/ci.yml`:
    - Code linting (Ruff/Black/Flake8), type checking (Mypy), test suite execution (Pytest).
  - Integration and chaos tests:
    - Sudden Redis restart, database disconnection recovery, high-load burst handling.
  - Documentation:
    - `docs/api.md`: Complete OpenAPI/REST specification.
    - `docs/operations.md`: Runbooks for common incidents, disaster recovery, tuning guidelines.
    - `README.md`: Quickstart, architecture overview, and running instructions.
- **Acceptance Criteria**:
  - All CI steps pass cleanly.
  - Failure recovery scenarios pass deterministically.
  - Documentation accurately describes system setup, operations, and architectural tradeoffs.

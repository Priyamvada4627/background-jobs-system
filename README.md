# Background Job Management System

A distributed, failure-resilient task queue and execution engine designed for reliable background job processing, atomic worker claiming, transactional outbox publishing, lease-based dead worker recovery, and real-time operational visibility.

---

## Key Capabilities

- **Durable State Machine**: PostgreSQL is the durable source of truth for jobs, execution attempts, recurring schedules, and audit trails.
- **Transactional Outbox Pattern**: Commits jobs and outbox events in a single PostgreSQL transaction; a dedicated publisher streams them to Redis with zero data loss.
- **Priority Queuing & Fairness**: Fast coordination via Redis with priority lanes (`high`, `default`, `low`) and weighted dequeue to prevent starvation.
- **Worker Leases & Fencing**: Renewable worker leases with monotonic attempt fencing tokens to prevent zombie workers from overwriting fresher state.
- **Lease Reaper**: Automated recovery of abandoned tasks following worker crashes or network isolation.
- **Retries with Exponential Backoff & Jitter**: Configurable retry policies with dead-letter queue (DLQ) containment and manual revival.
- **Registered Task Handlers**: Safe execution of pre-registered Python task handlers with timeouts and cancellation support (no arbitrary client code execution).
- **Delayed & Recurring Schedules**: Timezone-aware cron schedules and future-scheduled execution.
- **Real-Time Visibility**: Live WebSocket event streaming, Prometheus metrics, structured JSON logging, and a React + TypeScript dashboard.

---

## Architecture

Detailed architecture specifications, component diagrams, state transition models, and distributed consistency semantics are documented in [docs/architecture.md](docs/architecture.md).

```
Client / SDK → FastAPI → PostgreSQL + Outbox → Outbox Publisher → Redis Queues → Worker Pool → PostgreSQL
```

---

## Local Setup & Development

### 1. Prerequisites
- Python 3.11+
- Docker & Docker Compose (for PostgreSQL 16 and Redis 7)

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
All database credentials, Redis hosts, and worker tuning parameters are read dynamically from environment variables. No secrets or credentials are hardcoded.

### 3. Virtual Environment & Dependencies
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1   # On Windows PowerShell
# source .venv/bin/activate    # On Linux/macOS

# Install pinned dependencies and test tools
pip install -e backend[dev]
```

### 4. Start Infrastructure (PostgreSQL & Redis)
```powershell
docker compose -f infra/docker-compose.yml up -d
```
This launches:
- **PostgreSQL 16** on `localhost:5432` with health checks and persistent volume `pgdata`.
- **Redis 7** on `localhost:6379` with health checks and persistent volume `redisdata`.

### 5. Run FastAPI Application
```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000
```
- Interactive Swagger API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Liveness Probe: `GET http://localhost:8000/health`
- Readiness Probe: `GET http://localhost:8000/health/ready` (validates PostgreSQL and Redis connection)

### 6. Run Test Suite
```powershell
.\.venv\Scripts\pytest.exe -v
```

---

## Phased Implementation Plan

Implementation follows a staged 13-phase plan documented in [docs/implementation-plan.md](docs/implementation-plan.md):

- **Phase 0**: Repository Discovery and Plan *(Completed)*
- **Phase 1**: Project Foundation and Local Environment *(Completed)*
- **Phase 2**: Schema and Job API *(Up next)*
- **Phase 3**: Registered Task Handlers and Single Worker Process
- **Phase 4**: Redis Queue and Atomic Claiming
- **Phase 5**: Outbox Publisher and Consistency Recovery
- **Phase 6**: Retries, Backoff, and Dead-Letter Queue
- **Phase 7**: Delayed and Recurring Jobs
- **Phase 8**: Worker Heartbeat, Leases, and Reaper
- **Phase 9**: Idempotency, Cancellation, and Throttling
- **Phase 10**: Frontend Dashboard and WebSockets
- **Phase 11**: Observability and Benchmarks
- **Phase 12**: Hardening, CI, and Documentation


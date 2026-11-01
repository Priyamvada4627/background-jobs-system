# Background Job Management System

A distributed, failure-resilient task queue and execution engine designed for reliable background job processing. The system combines PostgreSQL durability, Redis-based coordination, transactional outbox publishing, lease-based worker recovery, and real-time operational visibility.

## 🚀 Key Capabilities

- **Durable Source of Truth:** PostgreSQL stores jobs, execution attempts, recurring schedules, and audit events.
- **Fast Transient Coordination:** Redis supports low-latency queue operations, worker leases, rate limiting, and scheduler leader locks.
- **Transactional Outbox Pattern:** Stores jobs and outbox events in a single PostgreSQL transaction, enabling reliable delivery attempts to Redis.
- **Priority Queuing and Fairness:** Supports `HIGH`, `DEFAULT`, and `LOW` priority lanes with a 6:3:1 weighted scheduling policy.
- **Worker Leases and Fencing Tokens:** Uses renewable leases and attempt fencing tokens to protect against stale workers updating newer execution state.
- **Automated Lease Reaper:** Detects abandoned work and recovers jobs after worker failures.
- **Retries and Dead-Letter Queue:** Supports retry policies with exponential backoff and jitter, dead-letter queue (DLQ) handling, and manual revival.
- **Registered Task Handlers:** Executes pre-registered Python handlers with timeouts and cooperative cancellation support, rather than arbitrary client-supplied code.
- **Delayed and Recurring Jobs:** Supports timezone-aware cron schedules and distributed scheduler coordination.
- **Operational Visibility:**
  - Live WebSocket event streaming (`/ws`)
  - Prometheus metrics (`/metrics`)
  - Grafana dashboards
  - Structured JSON logging
  - Built-in operational dashboard (`/dashboard`)
  - React and TypeScript frontend in `frontend/`

## 🏗️ Architecture

```text
                 +----------------------------+
                 |       FastAPI API          |
                 | REST / WebSocket / Metrics |
                 +-------------+--------------+
                               |
                  +------------+------------+
                  |                         |
                  v                         v
        +------------------+      +------------------+
        |   PostgreSQL     |      |      Redis       |
        | Durable Storage  |      | Queues and Leases|
        +--------+---------+      +--------+---------+
                 |                         ^
                 v                         |
        +------------------+               |
        | Outbox Publisher |-------------->|
        +------------------+      Priority Queues
                                           |
                                           v
                                 +------------------+
                                 | Worker Engines   |
                                 | Execute and Retry|
                                 +--------+---------+
                                          |
                                          v
                                 +------------------+
                                 | Lease Reaper and |
                                 | Scheduler Daemons|
                                 +------------------+
```

### Documentation

- [Architecture and Invariants](docs/architecture.md)
- [REST and WebSocket API Reference](docs/api.md)
- [Operational Runbooks and Incident Response](docs/operations.md)
- [Phase-by-Phase Implementation Plan](docs/implementation-plan.md)

## ⚡ Quickstart

### 1. Prerequisites

- Python 3.11 or later
- Docker Desktop with Docker Compose
- Git

Docker Compose starts PostgreSQL 16, Redis 7, Prometheus, and Grafana.

### 2. Configure Environment Variables

Create a `.env` file in the project root, next to `.gitignore`. This project uses a local `.env` file rather than a committed `.env.example`.

Add the following configuration, replacing the password placeholders with your chosen values:

```dotenv
# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=job_system
POSTGRES_PORT=5433

# Redis
REDIS_PORT=6379

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001
GRAFANA_ADMIN_PASSWORD=your_grafana_password
```

Preserve any additional variables required by your application.

**Security:** Keep `.env` out of Git. Commit configuration templates only if they contain placeholders and no real credentials.

### 3. Create a Virtual Environment and Install Dependencies

Run these commands from the project root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e "./backend[dev]"
```

If PowerShell blocks virtual environment activation, you can temporarily allow scripts in the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 4. Start the Infrastructure

From the project root:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d
```

This starts the following services:

| Service | Local address |
|---|---|
| PostgreSQL | `localhost:5433` |
| Redis | `localhost:6379` |
| Prometheus | [http://localhost:9090](http://localhost:9090) |
| Grafana | [http://localhost:3001](http://localhost:3001) |

PostgreSQL uses host port `5433`, mapped to port `5432` inside the container.

Grafana's default username is `admin`. Its initial password is configured through `GRAFANA_ADMIN_PASSWORD` in `.env`. If Grafana has already initialized its persistent data volume, changing the environment variable alone will not reset its existing login password.

### 5. Apply Database Migrations

From the project root:

```powershell
$env:PYTHONPATH = "backend"
python -m alembic -c backend/alembic.ini upgrade head
```

If your Alembic configuration uses a different location, use the configuration file present in your repository.

## 💻 Running System Components

Keep each long-running component in a separate terminal. Activate `.venv` in each terminal and run commands from the project root.

Set the Python import path in each terminal:

```powershell
$env:PYTHONPATH = "backend"
```

### 1. API Server and Dashboard

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints:

- **Operational Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **Interactive API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Readiness Check:** [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

### 2. Transactional Outbox Publisher

```powershell
python -m app.services.outbox_cli --poll-interval 0.5
```

The publisher polls pending outbox events and attempts to deliver them to the configured queue.

### 3. Worker Engine

```powershell
python -m app.workers.cli --worker-id worker-1 --poll-interval 0.5
```

Workers claim and execute jobs using the registered task handlers.

### 4. Lease Reaper

```powershell
python -m app.services.reaper_cli --poll-interval 5.0
```

The reaper checks for abandoned or expired worker leases and initiates recovery according to the configured job state transitions.

### 5. Cron and Periodic Scheduler

```powershell
python -m app.scheduler.cli --poll-interval 1.0
```

The scheduler checks for due recurring jobs and coordinates scheduling through the configured distributed locking mechanism.

## 📊 Performance Benchmarks

Run the benchmark suite from the project root:

```powershell
$env:PYTHONPATH = "backend"
python -m scripts.benchmark --jobs 200 --workers 4 --priority DEFAULT --task-type compute_hash
```

The benchmark can help evaluate:

- Job submission throughput
- Job processing throughput
- Execution duration
- Average and percentile latency, including p50, p90, p95, and p99

Record actual results from your environment. Performance depends on hardware, workload, database configuration, worker concurrency, and infrastructure. Do not treat example figures as guaranteed throughput.

## 🧪 Testing

Run the test suite from the project root with the virtual environment activated:

```powershell
$env:PYTHONPATH = "backend"
pytest -v
```

The project test plan covers the following areas, where implemented:

- **Unit Tests:** Configuration, health checks, schemas, job state transitions, task registry, handlers, retry policies, queue operations, rate limiting, outbox publishing, metrics, and structured logging.
- **Integration Tests:** Worker contention, jobs and schedules APIs, cron scheduling, retry and DLQ behavior, lease recovery, WebSockets, system statistics, and benchmark execution.
- **Resilience Tests:** Redis interruption and recovery, worker crashes, stale-worker fencing, and high-concurrency worker contention.

## 🔒 Security and Configuration

- Never commit `.env`, credentials, or production secrets.
- Use strong passwords for PostgreSQL and Grafana.
- Keep the `.env` file excluded through `.gitignore`.
- Use registered task handlers rather than executing arbitrary client-supplied code.
- Restrict exposed service ports and configure authentication appropriately before deploying outside a trusted development environment.

## 📜 License

MIT License. A production-minded educational project exploring durable background processing, distributed coordination, failure recovery, and operational observability.

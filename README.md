# Background Job Management System

A distributed, failure-resilient task queue and execution engine designed for reliable background job processing, atomic worker claiming, transactional outbox publishing, lease-based dead worker recovery, and real-time operational visibility.

---

## 🚀 Key Capabilities

- **Durable Source of Truth**: PostgreSQL durably tracks jobs, execution attempts, recurring cron schedules, and immutable audit trails.
- **Fast Transient Coordination**: Redis delivers low-latency atomic queue popping, renewable worker leases, rate limiters, and scheduler leader locks.
- **Transactional Outbox Pattern**: Commits jobs and outbox events in a single PostgreSQL transaction; a dedicated publisher streams them to Redis with zero data loss even during network partitions or Redis outages.
- **Priority Queuing & Fairness**: Fast coordination via Redis with priority lanes (`HIGH`, `DEFAULT`, `LOW`) and 6:3:1 weighted fair scheduling to eliminate starvation.
- **Worker Leases & Fencing Tokens**: Renewable worker leases with monotonic attempt fencing tokens to prevent zombie workers from overwriting fresher state.
- **Automated Lease Reaper**: Automated recovery of abandoned tasks following worker crashes or network isolation.
- **Retries with Exponential Backoff & Jitter**: Configurable retry policies with dead-letter queue (DLQ) containment and manual revival.
- **Registered Task Handlers**: Safe execution of pre-registered Python task handlers with timeouts and cooperative cancellation support (no arbitrary client code execution).
- **Delayed & Recurring Schedules**: Timezone-aware cron schedules with distributed leader locking via Redis.
- **Real-Time Operational Visibility**:
  - Live WebSocket event streaming (`/ws`).
  - Prometheus metrics exporter (`GET /metrics`).
  - Pre-configured Grafana dashboard in `infra/grafana/dashboards/`.
  - Structured JSON logging formatter.
  - Zero-dependency built-in operational web dashboard (`GET /dashboard`).
  - Modular React + TypeScript frontend SPA in `frontend/`.

---

## 🏗️ Architecture

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

Detailed specifications:
- [Architecture & Invariants Document](docs/architecture.md)
- [REST & WebSocket API Reference](docs/api.md)
- [Operational Runbooks & Incident Response](docs/operations.md)
- [Phase-by-Phase Implementation Plan](docs/implementation-plan.md)

---

## ⚡ Quickstart

### 1. Prerequisites
- Python 3.11+
- Docker & Docker Compose (for PostgreSQL 16, Redis 7, Prometheus, and Grafana)

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 3. Install Dependencies
```bash
# Activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # On Windows PowerShell
# source .venv/bin/activate     # On Linux / macOS

# Install backend dependencies
pip install -e "./backend[dev]"
```

### 4. Start Infrastructure Stack
```bash
docker compose -f infra/docker-compose.yml up -d
```
This launches:
- **PostgreSQL 16**: `localhost:5432`
- **Redis 7**: `localhost:6379`
- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3001` (Credentials: `admin` / `admin`)

Apply database migrations:
```bash
cd backend
alembic upgrade head
cd ..
```

---

## 💻 Running System Components

### 1. API Server & Dashboard
```bash
$env:PYTHONPATH="backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- **Operational Web Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Metrics**: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **System Health**: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

### 2. Transactional Outbox Publisher Daemon
```bash
$env:PYTHONPATH="backend"
python -m app.services.outbox_cli --poll-interval 0.5
```

### 3. Worker Engine Processes
```bash
$env:PYTHONPATH="backend"
python -m app.workers.cli --worker-id worker-1 --poll-interval 0.5
```

### 4. Lease Reaper Daemon
```bash
$env:PYTHONPATH="backend"
python -m app.services.reaper_cli --poll-interval 5.0
```

### 5. Cron & Periodic Scheduler
```bash
$env:PYTHONPATH="backend"
python -m app.scheduler.cli --poll-interval 1.0
```

---

## 📊 Performance Benchmarks

Run the built-in asynchronous load generator and benchmark suite:

```bash
$env:PYTHONPATH="backend"
python -m scripts.benchmark --jobs 200 --workers 4 --priority DEFAULT --task-type compute_hash
```

Example Output:
```
===========================================================
  BACKGROUND JOB SYSTEM - PERFORMANCE BENCHMARK
===========================================================
Target Jobs:    200
Worker Count:   4
Task Type:      compute_hash
Priority:       DEFAULT
===========================================================

[*] Submitting 200 jobs...
[+] Ingestion completed in 0.142s (1408.5 jobs/sec)
[*] Spawning 4 concurrent worker engines...
    Processed: 200/200 jobs (100%)...

===========================================================
  BENCHMARK RESULTS SUMMARY
===========================================================
Submission Throughput:  1408.5 jobs/sec
Processing Throughput:  312.4 jobs/sec
Execution Duration:     0.640s
Latencies (ms):
  Min: 1 ms | Avg: 4.8 ms | Max: 19 ms
  p50: 4 ms | p90: 9 ms | p95: 12 ms | p99: 18 ms
===========================================================
```

---

## 🧪 Test Suite

The system includes comprehensive unit, integration, and chaos resilience tests:

```bash
pytest -v
```

Test coverage includes:
- **Unit**: Config, Health, Schemas, State Machine, Task Registry, Handlers, Retry Policy, Redis Priority Queue, Rate Limiter, Outbox Publisher, Metrics, Structured Logging.
- **Integration**: Competing Workers, Jobs API, Schedules API, Cron Scheduler, Retry DLQ, Lease Reaper, WebSockets, System Stats, Benchmark Runner.
- **Chaos Resilience**: Redis network partition & recovery, Worker hard crash & zombie fencing, High-concurrency competing worker burst.

---

## 📜 License

MIT License. Designed as a production-minded educational task queue and distributed execution engine.

import argparse
import asyncio
import statistics
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.db.session import get_sessionmaker, get_engine
from app.queue.connection import get_redis_client
from app.queue.redis_queue import RedisQueue
from app.models.job import Job
from app.services.job_service import JobService
from app.schemas.job import JobCreate, JobPriority
from app.workers.engine import WorkerEngine
from app.services.state_machine import JobStatus


async def run_benchmark(
    num_jobs: int = 100,
    num_workers: int = 4,
    task_type: str = "email.send",
    priority: str = "DEFAULT",
    session_factory: Any = None,
    redis_queue: Any = None,
) -> Dict[str, Any]:
    """
    Executes a high-throughput performance benchmark:
    1. Concurrently generates and enqueues `num_jobs` jobs.
    2. Spawns `num_workers` worker engines to consume and execute them concurrently.
    3. Gathers precise duration, latency percentiles, and throughput metrics.
    """
    if session_factory is None:
        session_factory = get_sessionmaker()
    if redis_queue is None:
        redis_client = get_redis_client()
        redis_queue = RedisQueue(client=redis_client)

    print(f"\n===========================================================")
    print(f"  BACKGROUND JOB SYSTEM - PERFORMANCE BENCHMARK")
    print(f"===========================================================")
    print(f"Target Jobs:    {num_jobs}")
    print(f"Worker Count:   {num_workers}")
    print(f"Task Type:      {task_type}")
    print(f"Priority:       {priority}")
    print(f"===========================================================\n")

    # Phase 1: Ingestion / Submission Benchmark
    print(f"[*] Submitting {num_jobs} jobs...")
    submit_start = time.perf_counter()

    job_ids: List[uuid.UUID] = []

    async def submit_single(idx: int) -> uuid.UUID:
        async with session_factory() as db:
            job_in = JobCreate(
                task_type=task_type,
                priority=JobPriority(priority),
                payload={"benchmark_idx": idx, "timestamp": time.time()},
                max_retries=1,
                timeout_seconds=30,
            )
            job, _ = await JobService.create_job(db, job_in)
            # Enqueue directly into Redis priority lane
            await redis_queue.enqueue(job.id, job.priority)
            return job.id

    # Batch submission with concurrency
    submission_tasks = [submit_single(i) for i in range(num_jobs)]
    job_ids = await asyncio.gather(*submission_tasks)
    submit_duration = time.perf_counter() - submit_start
    submit_rate = num_jobs / submit_duration if submit_duration > 0 else 0

    print(f"[+] Ingestion completed in {submit_duration:.3f}s ({submit_rate:.1f} jobs/sec)")

    # Phase 2: Concurrent Worker Processing Benchmark
    print(f"[*] Spawning {num_workers} concurrent worker engines...")
    process_start = time.perf_counter()

    stop_event = asyncio.Event()
    completed_count = 0
    worker_engines = [
        WorkerEngine(
            worker_id=f"bench-worker-{i+1}",
            session_factory=session_factory,
            redis_queue=redis_queue,
        )
        for i in range(num_workers)
    ]

    async def worker_runner(engine: WorkerEngine):
        while not stop_event.is_set():
            attempt = await engine.run_once()
            if attempt is None:
                await asyncio.sleep(0.01)

    worker_tasks = [asyncio.create_task(worker_runner(e)) for e in worker_engines]

    # Monitor queue drain until all jobs reach terminal state
    while True:
        async with session_factory() as db:
            from sqlalchemy import select, func
            stmt = select(func.count(Job.id)).where(
                Job.id.in_(job_ids),
                Job.status.in_([JobStatus.SUCCEEDED.value, JobStatus.DEAD.value, JobStatus.CANCELLED.value]),
            )
            res = await db.execute(stmt)
            done = res.scalar_one()

            print(f"\r    Processed: {done}/{num_jobs} jobs ({int(done/num_jobs*100)}%)...", end="", flush=True)
            if done >= num_jobs:
                break
        await asyncio.sleep(0.1)

    print()
    process_duration = time.perf_counter() - process_start
    stop_event.set()

    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)

    process_throughput = num_jobs / process_duration if process_duration > 0 else 0

    # Phase 3: Gather Latency Statistics
    async with session_factory() as db:
        from app.models.job_attempt import JobAttempt
        stmt_att = select(JobAttempt.duration_ms).where(JobAttempt.job_id.in_(job_ids))
        res_att = await db.execute(stmt_att)
        latencies: List[int] = list(res_att.scalars().all())

    if latencies:
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p90 = latencies[int(len(latencies) * 0.90)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) >= 100 else latencies[-1]
        avg_lat = statistics.mean(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
    else:
        p50 = p90 = p95 = p99 = avg_lat = min_lat = max_lat = 0

    report = {
        "num_jobs": num_jobs,
        "num_workers": num_workers,
        "task_type": task_type,
        "submission_duration_sec": round(submit_duration, 4),
        "submission_rate_jobs_sec": round(submit_rate, 2),
        "execution_duration_sec": round(process_duration, 4),
        "throughput_jobs_sec": round(process_throughput, 2),
        "latency_ms": {
            "min": min_lat,
            "avg": round(avg_lat, 2),
            "p50": p50,
            "p90": p90,
            "p95": p95,
            "p99": p99,
            "max": max_lat,
        },
    }

    print(f"\n===========================================================")
    print(f"  BENCHMARK RESULTS SUMMARY")
    print(f"===========================================================")
    print(f"Submission Throughput:  {report['submission_rate_jobs_sec']} jobs/sec")
    print(f"Processing Throughput:  {report['throughput_jobs_sec']} jobs/sec")
    print(f"Execution Duration:     {report['execution_duration_sec']}s")
    print(f"Latencies (ms):")
    print(f"  Min: {min_lat} ms | Avg: {round(avg_lat, 1)} ms | Max: {max_lat} ms")
    print(f"  p50: {p50} ms | p90: {p90} ms | p95: {p95} ms | p99: {p99} ms")
    print(f"===========================================================\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="Background Job System Benchmark")
    parser.add_argument("--jobs", type=int, default=100, help="Number of jobs to submit")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker processes")
    parser.add_argument("--task-type", type=str, default="email.send", help="Task type to execute")
    parser.add_argument("--priority", type=str, default="DEFAULT", choices=["HIGH", "DEFAULT", "LOW"])
    args = parser.parse_args()

    asyncio.run(
        run_benchmark(
            num_jobs=args.jobs,
            num_workers=args.workers,
            task_type=args.task_type,
            priority=args.priority,
        )
    )


if __name__ == "__main__":
    main()

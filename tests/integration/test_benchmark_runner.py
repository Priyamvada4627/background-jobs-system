import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.queue.redis_queue import RedisQueue
from scripts.benchmark import run_benchmark


@pytest.mark.asyncio
async def test_benchmark_execution(test_engine, fake_redis):
    """Verifies that the benchmark runner executes end-to-end and outputs valid throughput & latency stats."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    redis_queue = RedisQueue(client=fake_redis)

    report = await run_benchmark(
        num_jobs=6,
        num_workers=2,
        task_type="email.send",
        priority="DEFAULT",
        session_factory=session_factory,
        redis_queue=redis_queue,
    )

    assert report["num_jobs"] == 6
    assert report["num_workers"] == 2
    assert report["submission_rate_jobs_sec"] > 0
    assert report["throughput_jobs_sec"] > 0
    assert "p50" in report["latency_ms"]
    assert "p95" in report["latency_ms"]

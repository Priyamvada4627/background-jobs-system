import pytest
import asyncio
from app.services.rate_limiter import TokenBucketRateLimiter, ConcurrencyLimiter


@pytest.mark.asyncio
async def test_token_bucket_burst_and_exhaustion(fake_redis):
    """Verifies that token bucket allows bursts up to capacity and blocks once empty."""
    limiter = TokenBucketRateLimiter(client=fake_redis)
    key = "tenant:customer-123"

    capacity = 3.0
    refill = 0.5  # 1 token every 2 seconds

    # Burst of 3 should all succeed
    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is True
    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is True
    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is True

    # 4th request must be rejected (exhausted)
    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is False


@pytest.mark.asyncio
async def test_token_bucket_refill(fake_redis):
    """Verifies that tokens refill smoothly over elapsed time."""
    limiter = TokenBucketRateLimiter(client=fake_redis)
    key = "tenant:fast-refill"

    capacity = 2.0
    refill = 10.0  # 10 tokens per second = 1 token per 100ms

    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is True
    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is True
    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is False

    # Sleep 150ms to allow at least 1 token to refill
    await asyncio.sleep(0.15)
    assert await limiter.acquire(key, capacity=capacity, refill_rate=refill) is True


@pytest.mark.asyncio
async def test_concurrency_limiter_strict_cap(fake_redis):
    """Verifies that ConcurrencyLimiter strictly enforces max active slots."""
    limiter = ConcurrencyLimiter(client=fake_redis)
    resource = "task:heavy_compute"
    max_slots = 2

    # Worker 1 & 2 acquire slots
    assert await limiter.acquire(resource, max_concurrency=max_slots, worker_id="w1") is True
    assert await limiter.acquire(resource, max_concurrency=max_slots, worker_id="w2") is True
    assert await limiter.get_current_concurrency(resource) == 2

    # Worker 3 is blocked by concurrency limit
    assert await limiter.acquire(resource, max_concurrency=max_slots, worker_id="w3") is False

    # Worker 1 releases slot
    assert await limiter.release(resource, worker_id="w1") is True
    assert await limiter.get_current_concurrency(resource) == 1

    # Worker 3 can now acquire
    assert await limiter.acquire(resource, max_concurrency=max_slots, worker_id="w3") is True
    assert await limiter.get_current_concurrency(resource) == 2

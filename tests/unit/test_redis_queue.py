import pytest
import uuid
from app.queue.redis_queue import RedisQueue


@pytest.mark.asyncio
async def test_enqueue_and_queue_depth(fake_redis):
    queue = RedisQueue(client=fake_redis)

    # Empty queue depths
    depths = await queue.get_all_queue_depths()
    assert depths["TOTAL"] == 0

    # Enqueue into different lanes
    await queue.enqueue(uuid.uuid4(), priority="HIGH")
    await queue.enqueue(uuid.uuid4(), priority="HIGH")
    await queue.enqueue(uuid.uuid4(), priority="DEFAULT")
    await queue.enqueue(uuid.uuid4(), priority="LOW")

    depths = await queue.get_all_queue_depths()
    assert depths["HIGH"] == 2
    assert depths["DEFAULT"] == 1
    assert depths["LOW"] == 1
    assert depths["TOTAL"] == 4


@pytest.mark.asyncio
async def test_atomic_claim_and_lease_creation(fake_redis):
    queue = RedisQueue(client=fake_redis)
    job_id = str(uuid.uuid4())
    await queue.enqueue(job_id, priority="HIGH")

    # Worker claims the job
    worker_id = "worker-alpha"
    claimed = await queue.claim_job_atomic(worker_id=worker_id, lease_ttl_seconds=45, fair=False)

    assert claimed is not None
    claimed_id, queue_name = claimed
    assert claimed_id == job_id
    assert queue_name == RedisQueue.QUEUE_HIGH

    # Verify queue is now empty
    assert await queue.get_queue_depth("HIGH") == 0

    # Verify lease was created in Redis
    lease_owner = await queue.get_lease_owner(job_id)
    assert lease_owner == worker_id

    # Verify lease TTL is active
    ttl = await fake_redis.ttl(f"lease:job:{job_id}")
    assert 0 < ttl <= 45


@pytest.mark.asyncio
async def test_lease_renewal_and_release(fake_redis):
    queue = RedisQueue(client=fake_redis)
    job_id = str(uuid.uuid4())
    worker_id = "worker-owner"

    # Acquire lease by claiming
    await queue.enqueue(job_id, priority="DEFAULT")
    await queue.claim_job_atomic(worker_id=worker_id, lease_ttl_seconds=30)

    # Valid owner can renew
    renewed = await queue.renew_lease(job_id, worker_id=worker_id, ttl_seconds=60)
    assert renewed is True
    ttl = await fake_redis.ttl(f"lease:job:{job_id}")
    assert ttl > 30

    # Unauthorized worker cannot renew
    imposter_renewed = await queue.renew_lease(job_id, worker_id="imposter-worker", ttl_seconds=60)
    assert imposter_renewed is False

    # Imposter cannot release
    imposter_released = await queue.release_lease(job_id, worker_id="imposter-worker")
    assert imposter_released is False
    assert await queue.get_lease_owner(job_id) == worker_id

    # Valid owner releases
    released = await queue.release_lease(job_id, worker_id=worker_id)
    assert released is True
    assert await queue.get_lease_owner(job_id) is None


@pytest.mark.asyncio
async def test_queue_fairness_prevents_low_priority_starvation(fake_redis):
    queue = RedisQueue(client=fake_redis)

    # Populate 20 HIGH jobs and 1 LOW job
    for i in range(20):
        await queue.enqueue(f"high-job-{i}", priority="HIGH")
    await queue.enqueue("low-priority-job-1", priority="LOW")

    claimed_ids = []
    # Pop 10 jobs using the fair schedule
    for _ in range(10):
        claimed = await queue.claim_job_atomic(worker_id="worker-fair", fair=True)
        if claimed:
            claimed_ids.append(claimed[0])

    # The LOW priority job must have been picked up within the 10 pops!
    assert "low-priority-job-1" in claimed_ids

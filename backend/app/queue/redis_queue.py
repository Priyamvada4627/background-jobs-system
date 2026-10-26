import uuid
import itertools
from typing import Optional, Tuple, Dict, Any, List
import redis.asyncio as aioredis
from app.queue.connection import get_redis_client


# Atomic Lua script for claiming a job from priority lanes and establishing an active lease
# KEYS: [queue1, queue2, queue3] (ordered by priority or fairness)
# ARGV: [worker_id, lease_ttl_seconds]
# Returns: {job_id, queue_name} or nil
CLAIM_JOB_LUA_SCRIPT = """
local worker_id = ARGV[1]
local lease_ttl = tonumber(ARGV[2])

for i = 1, #KEYS do
    local q_key = KEYS[i]
    local job_id = redis.call('RPOP', q_key)
    if job_id then
        local lease_key = 'lease:job:' .. job_id
        redis.call('SET', lease_key, worker_id, 'EX', lease_ttl)
        return {job_id, q_key}
    end
end

return nil
"""

# Atomic Lua script to renew a lease only if the calling worker currently holds it
# KEYS: [lease_key]
# ARGV: [worker_id, ttl_seconds]
RENEW_LEASE_LUA_SCRIPT = """
local lease_key = KEYS[1]
local worker_id = ARGV[1]
local ttl = tonumber(ARGV[2])

local current_owner = redis.call('GET', lease_key)
if current_owner == worker_id then
    redis.call('EXPIRE', lease_key, ttl)
    return 1
else
    return 0
end
"""

# Atomic Lua script to release a lease only if the calling worker currently holds it
# KEYS: [lease_key]
# ARGV: [worker_id]
RELEASE_LEASE_LUA_SCRIPT = """
local lease_key = KEYS[1]
local worker_id = ARGV[1]

local current_owner = redis.call('GET', lease_key)
if current_owner == worker_id then
    redis.call('DEL', lease_key)
    return 1
else
    return 0
end
"""


class RedisQueue:
    """
    Manages Redis priority queues, atomic claiming with Lua scripts,
    lease-based locking, and starvation-free fair queue draining.
    """

    QUEUE_HIGH = "queue:jobs:HIGH"
    QUEUE_DEFAULT = "queue:jobs:DEFAULT"
    QUEUE_LOW = "queue:jobs:LOW"

    # Fairness sequence (Ratio 6:3:1 for HIGH:DEFAULT:LOW)
    # Guaranteed rotation ensures lower priority tasks are never starved under constant high-priority load.
    FAIRNESS_SCHEDULE: List[List[str]] = [
        [QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW],    # 1: High first
        [QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW],    # 2: High first
        [QUEUE_DEFAULT, QUEUE_HIGH, QUEUE_LOW],    # 3: Default first
        [QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW],    # 4: High first
        [QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW],    # 5: High first
        [QUEUE_DEFAULT, QUEUE_HIGH, QUEUE_LOW],    # 6: Default first
        [QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW],    # 7: High first
        [QUEUE_LOW, QUEUE_HIGH, QUEUE_DEFAULT],    # 8: Low first! Prevents starvation
        [QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW],    # 9: High first
        [QUEUE_DEFAULT, QUEUE_HIGH, QUEUE_LOW],    # 10: Default first
    ]

    def __init__(self, client: Optional[aioredis.Redis] = None):
        self._client = client
        self._fairness_counter = 0
        self._claim_script = None
        self._renew_script = None
        self._release_script = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = get_redis_client()
        return self._client

    def _get_queue_key(self, priority: str) -> str:
        priority_norm = priority.upper()
        if priority_norm == "HIGH":
            return self.QUEUE_HIGH
        elif priority_norm == "LOW":
            return self.QUEUE_LOW
        return self.QUEUE_DEFAULT

    async def enqueue(self, job_id: str | uuid.UUID, priority: str = "DEFAULT") -> int:
        """Pushes a job ID to the designated priority queue list in Redis (LPUSH)."""
        queue_key = self._get_queue_key(priority)
        job_id_str = str(job_id)
        return await self.client.lpush(queue_key, job_id_str)

    def _get_fair_queue_order(self) -> List[str]:
        """Returns queue key evaluation order according to the weighted fairness schedule."""
        order = self.FAIRNESS_SCHEDULE[self._fairness_counter % len(self.FAIRNESS_SCHEDULE)]
        self._fairness_counter += 1
        return order

    async def claim_job_atomic(
        self,
        worker_id: str,
        lease_ttl_seconds: int = 30,
        fair: bool = True,
    ) -> Optional[Tuple[str, str]]:
        """
        Atomically pops a job ID from the Redis priority queues and creates an exclusive lease
        using an atomic Lua script.
        
        Returns:
            Tuple[job_id, queue_name] or None if all queues are empty.
        """
        if fair:
            keys = self._get_fair_queue_order()
        else:
            keys = [self.QUEUE_HIGH, self.QUEUE_DEFAULT, self.QUEUE_LOW]

        if self._claim_script is None:
            self._claim_script = self.client.register_script(CLAIM_JOB_LUA_SCRIPT)

        res = await self._claim_script(keys=keys, args=[worker_id, lease_ttl_seconds])
        if res:
            job_id, queue_name = res[0], res[1]
            return str(job_id), str(queue_name)
        return None

    async def renew_lease(self, job_id: str | uuid.UUID, worker_id: str, ttl_seconds: int = 30) -> bool:
        """Extends the lease TTL if and only if the specified worker currently holds the lease."""
        lease_key = f"lease:job:{job_id}"
        if self._renew_script is None:
            self._renew_script = self.client.register_script(RENEW_LEASE_LUA_SCRIPT)

        result = await self._renew_script(keys=[lease_key], args=[worker_id, ttl_seconds])
        return bool(result == 1)

    async def release_lease(self, job_id: str | uuid.UUID, worker_id: Optional[str] = None) -> bool:
        """Releases the worker lease for a job."""
        lease_key = f"lease:job:{job_id}"
        if worker_id:
            if self._release_script is None:
                self._release_script = self.client.register_script(RELEASE_LEASE_LUA_SCRIPT)
            result = await self._release_script(keys=[lease_key], args=[worker_id])
            return bool(result == 1)
        else:
            del_count = await self.client.delete(lease_key)
            return bool(del_count > 0)

    async def get_lease_owner(self, job_id: str | uuid.UUID) -> Optional[str]:
        """Returns the worker_id currently holding the lease for the job, or None."""
        lease_key = f"lease:job:{job_id}"
        return await self.client.get(lease_key)

    async def get_queue_depth(self, priority: str = "DEFAULT") -> int:
        """Returns the number of ready jobs in a specific priority queue."""
        queue_key = self._get_queue_key(priority)
        return await self.client.llen(queue_key)

    async def get_all_queue_depths(self) -> Dict[str, int]:
        """Returns ready job counts across all priority lanes."""
        pipe = self.client.pipeline()
        pipe.llen(self.QUEUE_HIGH)
        pipe.llen(self.QUEUE_DEFAULT)
        pipe.llen(self.QUEUE_LOW)
        high, default, low = await pipe.execute()
        return {
            "HIGH": int(high),
            "DEFAULT": int(default),
            "LOW": int(low),
            "TOTAL": int(high + default + low),
        }

    async def clear_queues(self) -> None:
        """Flushes all queue lists and active leases (useful for testing)."""
        keys = [self.QUEUE_HIGH, self.QUEUE_DEFAULT, self.QUEUE_LOW]
        for key in keys:
            await self.client.delete(key)

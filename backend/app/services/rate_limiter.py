import time
import math
from typing import Optional
import redis.asyncio as aioredis
from app.queue.connection import get_redis_client


TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_updated')
local tokens = tonumber(data[1])
local last_updated = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_updated = now
else
    local elapsed = math.max(0, now - last_updated)
    tokens = math.min(capacity, tokens + (elapsed * refill_rate))
    last_updated = now
end

if tokens >= cost then
    tokens = tokens - cost
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', last_updated)
    redis.call('EXPIRE', key, math.ceil((capacity / refill_rate) * 2))
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', last_updated)
    redis.call('EXPIRE', key, math.ceil((capacity / refill_rate) * 2))
    return 0
end
"""


CONCURRENCY_ACQUIRE_LUA = """
local key = KEYS[1]
local max_concurrency = tonumber(ARGV[1])
local worker_token = ARGV[2]
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

-- 1. Remove expired entries older than (now - ttl)
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - ttl)

-- 2. Check current active count
local current_count = redis.call('ZCARD', key)
if current_count < max_concurrency then
    redis.call('ZADD', key, now, worker_token)
    redis.call('EXPIRE', key, ttl * 2)
    return 1
else
    return 0
end
"""


class TokenBucketRateLimiter:
    """
    High-performance distributed Token-Bucket rate limiter implemented with atomic Redis Lua scripts.
    Guarantees strict throughput limits per tenant, client IP, or task type without race conditions.
    """

    def __init__(self, client: Optional[aioredis.Redis] = None):
        self._client = client
        self._script = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = get_redis_client()
        return self._client

    async def acquire(
        self,
        bucket_key: str,
        capacity: float,
        refill_rate: float,
        cost: float = 1.0,
    ) -> bool:
        """
        Attempts to consume `cost` tokens from the bucket.
        Returns True if tokens were available and deducted; False if rate limited.
        """
        key = f"ratelimit:{bucket_key}"
        now_ts = time.time()

        if self._script is None:
            self._script = self.client.register_script(TOKEN_BUCKET_LUA)

        res = await self._script(
            keys=[key],
            args=[capacity, refill_rate, cost, now_ts],
        )
        return bool(res == 1)


class ConcurrencyLimiter:
    """
    Distributed concurrency limiter preventing more than N simultaneous executions
    of a specific task type or tenant workload.
    """

    def __init__(self, client: Optional[aioredis.Redis] = None):
        self._client = client
        self._script = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = get_redis_client()
        return self._client

    async def acquire(
        self,
        resource_key: str,
        max_concurrency: int,
        worker_id: str,
        ttl_seconds: int = 60,
    ) -> bool:
        """
        Attempts to acquire a concurrency slot for the resource.
        Returns True if acquired; False if concurrency limit is reached.
        """
        key = f"concurrency:{resource_key}"
        now_ts = time.time()

        if self._script is None:
            self._script = self.client.register_script(CONCURRENCY_ACQUIRE_LUA)

        res = await self._script(
            keys=[key],
            args=[max_concurrency, worker_id, now_ts, ttl_seconds],
        )
        return bool(res == 1)

    async def release(self, resource_key: str, worker_id: str) -> bool:
        """Releases the concurrency slot held by worker_id."""
        key = f"concurrency:{resource_key}"
        del_count = await self.client.zrem(key, worker_id)
        return bool(del_count > 0)

    async def get_current_concurrency(self, resource_key: str, ttl_seconds: int = 60) -> int:
        """Returns the number of currently active concurrency slots."""
        key = f"concurrency:{resource_key}"
        now_ts = time.time()
        await self.client.zremrangebyscore(key, "-inf", now_ts - ttl_seconds)
        return await self.client.zcard(key)

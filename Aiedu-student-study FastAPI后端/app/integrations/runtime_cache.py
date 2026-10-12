from __future__ import annotations

from contextlib import contextmanager
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable, Iterator
import uuid

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])
local current = redis.call('TIME')
local now_ms = current[1] * 1000 + math.floor(current[2] / 1000)
local values = redis.call('HMGET', key, 'tokens', 'updated_at_ms')
local tokens = tonumber(values[1])
local updated_at_ms = tonumber(values[2])

if tokens == nil or updated_at_ms == nil then
    tokens = capacity
    updated_at_ms = now_ms
end
if now_ms < updated_at_ms then
    updated_at_ms = now_ms
end

tokens = math.min(capacity, tokens + (now_ms - updated_at_ms) * refill_per_ms)
local allowed = 0
if tokens + 0.000000001 >= cost then
    tokens = tokens - cost
    allowed = 1
end

redis.call('HSET', key, 'tokens', tostring(tokens), 'updated_at_ms', tostring(now_ms))
redis.call('PEXPIRE', key, ttl_ms)
return allowed
"""


class RuntimeCache:
    def __init__(self, client: Redis | None = None,
                 clock: Callable[[], float] = monotonic) -> None:
        self.client = client or Redis.from_url(
            get_settings().redis_url, decode_responses=True,
            socket_connect_timeout=0.2, socket_timeout=0.2,
        )
        self._clock = clock
        self._fallback_lock = Lock()
        self._fallback_buckets: dict[str, tuple[float, float, float]] = {}

    def _allow_local(self, key: str, *, capacity: int, refill_per_second: float,
                     cost: int) -> bool:
        """Bound calls per API process while Redis is unavailable."""
        now = self._clock()
        idle_ttl = max(1.0, capacity / refill_per_second * 2)
        with self._fallback_lock:
            if len(self._fallback_buckets) >= 10_000:
                self._fallback_buckets = {
                    bucket_key: value for bucket_key, value in self._fallback_buckets.items()
                    if value[2] > now
                }
            tokens, updated_at, _ = self._fallback_buckets.get(
                key, (float(capacity), now, now + idle_ttl)
            )
            tokens = min(float(capacity), tokens + max(0.0, now - updated_at) * refill_per_second)
            allowed = tokens + 1e-9 >= cost
            if allowed:
                tokens -= cost
            self._fallback_buckets[key] = (tokens, now, now + idle_ttl)
            return allowed

    def allow(self, scope: str, user_id: int, limit: int, window_seconds: int, *,
              capacity: int | None = None, cost: int = 1) -> bool:
        """Consume one or more tokens from an atomic Redis token bucket.

        ``limit / window_seconds`` controls the sustained refill rate, while
        ``capacity`` controls the short burst independently.
        """
        if limit <= 0 or window_seconds <= 0 or cost <= 0:
            raise ValueError("Token bucket parameters must be positive")
        bucket_capacity = capacity if capacity is not None else limit
        if bucket_capacity <= 0 or cost > bucket_capacity:
            raise ValueError("Token bucket capacity must cover the request cost")
        key = f"rate:v2:{scope}:{user_id}"
        refill_per_second = limit / window_seconds
        refill_per_ms = refill_per_second / 1000
        # Keep an idle bucket until at least two complete refill periods pass.
        ttl_ms = max(1000, ceil((bucket_capacity / refill_per_second) * 2000))
        try:
            allowed = self.client.eval(
                _TOKEN_BUCKET_SCRIPT, 1, key, bucket_capacity,
                refill_per_ms, cost, ttl_ms,
            )
            return bool(int(allowed))
        except RedisError:
            return self._allow_local(
                key, capacity=bucket_capacity,
                refill_per_second=refill_per_second, cost=cost,
            )

    @contextmanager
    def lock(self, name: str, ttl_seconds: int = 60) -> Iterator[bool]:
        token = uuid.uuid4().hex
        key = f"lock:{name}"
        acquired = False
        try:
            acquired = bool(self.client.set(key, token, nx=True, ex=ttl_seconds))
        except RedisError:
            acquired = True
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    if self.client.get(key) == token:
                        self.client.delete(key)
                except RedisError:
                    pass


runtime_cache = RuntimeCache()

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from redis.exceptions import RedisError

from app.integrations.runtime_cache import RuntimeCache


class RecordingRedis:
    def __init__(self, result: int = 1) -> None:
        self.result = result
        self.calls: list[tuple] = []

    def eval(self, *args):
        self.calls.append(args)
        return self.result


class BrokenRedis:
    def eval(self, *args):
        raise RedisError("redis unavailable")


def test_token_bucket_uses_versioned_key_and_separate_burst_capacity():
    client = RecordingRedis()
    cache = RuntimeCache(client=client)

    assert cache.allow("chat", 7, 30, 60, capacity=6)

    _, key_count, key, capacity, refill_per_ms, cost, ttl_ms = client.calls[0]
    assert key_count == 1
    assert key == "rate:v2:chat:7"
    assert capacity == 6
    assert refill_per_ms == pytest.approx(0.0005)
    assert cost == 1
    assert ttl_ms == 24_000


def test_redis_failure_falls_back_to_local_token_bucket():
    now = [100.0]
    cache = RuntimeCache(client=BrokenRedis(), clock=lambda: now[0])

    assert cache.allow("agent-job", 9, 10, 60, capacity=2)
    assert cache.allow("agent-job", 9, 10, 60, capacity=2)
    assert not cache.allow("agent-job", 9, 10, 60, capacity=2)

    now[0] += 6
    assert cache.allow("agent-job", 9, 10, 60, capacity=2)
    assert not cache.allow("agent-job", 9, 10, 60, capacity=2)


def test_local_fallback_is_atomic_within_one_api_process():
    cache = RuntimeCache(client=BrokenRedis(), clock=lambda: 100.0)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(
            lambda _: cache.allow("grading-job", 3, 30, 60, capacity=10),
            range(40),
        ))

    assert sum(results) == 10


@pytest.mark.parametrize(
    ("limit", "window", "capacity", "cost"),
    [(0, 60, 1, 1), (1, 0, 1, 1), (1, 60, 0, 1), (1, 60, 1, 0), (1, 60, 1, 2)],
)
def test_invalid_token_bucket_parameters_are_rejected(limit, window, capacity, cost):
    cache = RuntimeCache(client=RecordingRedis())

    with pytest.raises(ValueError):
        cache.allow("chat", 1, limit, window, capacity=capacity, cost=cost)

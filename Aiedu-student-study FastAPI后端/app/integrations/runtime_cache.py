from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
import uuid

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


class RuntimeCache:
    def __init__(self) -> None:
        self.client = Redis.from_url(get_settings().redis_url, decode_responses=True,
                                     socket_connect_timeout=0.2, socket_timeout=0.2)

    def allow(self, scope: str, user_id: int, limit: int, window_seconds: int) -> bool:
        key = f"rate:{scope}:{user_id}"
        try:
            value = self.client.incr(key)
            if value == 1:
                self.client.expire(key, window_seconds)
            return value <= limit
        except RedisError:
            return True

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

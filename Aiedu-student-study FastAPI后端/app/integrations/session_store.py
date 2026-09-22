from __future__ import annotations

from datetime import datetime, timezone

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


class SessionStore:
    def __init__(self) -> None:
        self._redis = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
        self._memory: dict[str, float] = {}

    def _ttl(self, expires_at: datetime) -> int:
        return max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))

    def allow_refresh(self, jti: str, expires_at: datetime) -> None:
        ttl = self._ttl(expires_at)
        try:
            self._redis.set(f"session:refresh:{jti}", "1", ex=ttl)
        except RedisError:
            if get_settings().env == "production":
                raise
            self._memory[f"refresh:{jti}"] = expires_at.timestamp()

    def refresh_exists(self, jti: str) -> bool:
        try:
            return bool(self._redis.exists(f"session:refresh:{jti}"))
        except RedisError:
            expiry = self._memory.get(f"refresh:{jti}", 0)
            return expiry > datetime.now(timezone.utc).timestamp()

    def revoke(self, jti: str, expires_at: datetime, token_type: str) -> None:
        ttl = self._ttl(expires_at)
        try:
            if token_type == "refresh":
                self._redis.delete(f"session:refresh:{jti}")
            self._redis.set(f"session:revoked:{jti}", "1", ex=ttl)
        except RedisError:
            if get_settings().env == "production":
                raise
            self._memory[f"revoked:{jti}"] = expires_at.timestamp()

    def is_revoked(self, jti: str) -> bool:
        try:
            return bool(self._redis.exists(f"session:revoked:{jti}"))
        except RedisError:
            expiry = self._memory.get(f"revoked:{jti}", 0)
            return expiry > datetime.now(timezone.utc).timestamp()


session_store = SessionStore()

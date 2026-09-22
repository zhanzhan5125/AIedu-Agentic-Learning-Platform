from __future__ import annotations

import json

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


def publish_message(user_ids: list[int] | set[int], payload: dict) -> None:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True,
                            socket_connect_timeout=0.2, socket_timeout=0.2)
    try:
        value = json.dumps(payload, ensure_ascii=False, default=str)
        for user_id in set(user_ids):
            client.publish(f"realtime:messages:{user_id}", value)
    except RedisError:
        # MySQL remains the durable source; connected clients catch up by ID.
        return
    finally:
        try:
            client.close()
        except RedisError:
            pass

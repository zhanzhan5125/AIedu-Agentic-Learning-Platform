from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import get_settings


logger = logging.getLogger(__name__)


@contextmanager
def _sdk_log_directory(directory: str) -> Iterator[None]:
    """Redirect the SDK's hard-coded ~/logs path without changing HOME."""
    original_expanduser = os.path.expanduser
    target = str(Path(directory).resolve())

    def expanduser(path: str) -> str:
        normalized = path.replace("\\", "/")
        if normalized.startswith("~/logs/rocketmq_python"):
            return target
        return original_expanduser(path)

    os.path.expanduser = expanduser
    try:
        yield
    finally:
        os.path.expanduser = original_expanduser


def _client_types(log_dir: str):
    # rocketmq-python-client 5.1.2 configures a rotating file handler at
    # import time and does not expose a log-directory setting on Windows.
    with _sdk_log_directory(log_dir):
        from rocketmq import (
            ClientConfiguration,
            Credentials,
            FilterExpression,
            Message,
            Producer,
            SimpleConsumer,
        )

    return ClientConfiguration, Credentials, FilterExpression, Message, Producer, SimpleConsumer


class RocketMQAdapter:
    def __init__(self) -> None:
        self.settings = get_settings()

    def publish(self, topic: str, tag: str, key: str, payload: dict) -> None:
        if not self.settings.enable_mq:
            return
        ClientConfiguration, Credentials, _, Message, Producer, _ = _client_types(
            self.settings.rocketmq_log_dir
        )

        config = ClientConfiguration(self.settings.rocketmq_endpoint, Credentials())
        producer = Producer(config, (topic,))
        producer.startup()
        try:
            message = Message()
            message.topic = topic
            message.tag = tag
            # The v5 Python client's property setter accepts one string per
            # assignment; assigning a tuple is treated as one invalid key.
            message.keys = key
            message.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            producer.send(message)
        finally:
            producer.shutdown()

    def consume_forever(self, handler: Callable[[dict], None]) -> None:
        if not self.settings.enable_mq:
            raise RuntimeError("RocketMQ is disabled")
        ClientConfiguration, Credentials, FilterExpression, _, _, SimpleConsumer = _client_types(
            self.settings.rocketmq_log_dir
        )

        config = ClientConfiguration(self.settings.rocketmq_endpoint, Credentials())
        consumer = SimpleConsumer(
            config,
            "aiedu-ai-worker",
            {self.settings.rocketmq_topic: FilterExpression()},
        )
        consumer.startup()
        try:
            # The v5 Python client publishes its subscription settings to the
            # Proxy asynchronously.  Receiving immediately after startup can
            # therefore hit the Proxy before those settings are visible and
            # trigger ReceiveMessageActivity's settings-null error (50001).
            # The first settings refresh happens after roughly one second.
            time.sleep(2)
            concurrency = max(1, self.settings.rocketmq_worker_concurrency)
            invisible_duration = max(60, self.settings.rocketmq_invisible_duration_seconds)
            with ThreadPoolExecutor(max_workers=concurrency,
                                    thread_name_prefix="aiedu-resource-worker") as executor:
                while True:
                    try:
                        messages = consumer.receive(concurrency, invisible_duration)
                    except Exception as exc:
                        # A clean broker has no route for the topic until the first
                        # producer send (or an administrator creates it). Keep the
                        # worker alive while RocketMQ becomes ready/topic appears.
                        logger.warning("RocketMQ receive unavailable; retrying: %s", exc)
                        time.sleep(5)
                        continue
                    futures = {
                        executor.submit(
                            handler, json.loads(bytes(message.body).decode("utf-8"))
                        ): message
                        for message in messages
                    }
                    for future in as_completed(futures):
                        message = futures[future]
                        try:
                            future.result()
                        except Exception:
                            # Do not acknowledge: RocketMQ will redeliver according to broker policy.
                            logger.exception("RocketMQ event failed; waiting for redelivery")
                            continue
                        try:
                            consumer.ack(message)
                        except Exception as exc:
                            # Processing is idempotent through ConsumerInbox. An expired
                            # receipt handle must not terminate the entire worker; the
                            # redelivered message will be acknowledged on its next pass.
                            logger.warning("RocketMQ acknowledgement failed; message will redeliver: %s", exc)
        finally:
            consumer.shutdown()


rocketmq = RocketMQAdapter()

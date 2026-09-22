from __future__ import annotations

import json
import threading

import pytest

from app.integrations.rocketmq import RocketMQAdapter


class _Dummy:
    def __init__(self, *_, **__):
        pass


class _Message:
    def __init__(self, value: int):
        self.body = json.dumps({"value": value}).encode()


def test_consumer_processes_a_batch_concurrently_and_survives_ack_failure(monkeypatch):
    barrier = threading.Barrier(2)
    handled: list[int] = []
    acknowledged: list[int] = []

    class FakeConsumer:
        instance = None

        def __init__(self, *_, **__):
            self.receive_count = 0
            self.shutdown_called = False
            FakeConsumer.instance = self

        def startup(self):
            pass

        def receive(self, max_message_num, invisible_duration):
            assert max_message_num == 2
            assert invisible_duration == 1800
            self.receive_count += 1
            if self.receive_count == 1:
                return [_Message(1), _Message(2)]
            raise KeyboardInterrupt

        def ack(self, message):
            value = json.loads(message.body)["value"]
            acknowledged.append(value)
            if value == 1:
                raise RuntimeError("expired receipt handle")

        def shutdown(self):
            self.shutdown_called = True

    adapter = RocketMQAdapter()
    monkeypatch.setattr(adapter.settings, "enable_mq", True)
    monkeypatch.setattr(adapter.settings, "rocketmq_worker_concurrency", 2)
    monkeypatch.setattr(adapter.settings, "rocketmq_invisible_duration_seconds", 1800)
    monkeypatch.setattr("app.integrations.rocketmq.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "app.integrations.rocketmq._client_types",
        lambda _: (_Dummy, _Dummy, _Dummy, _Dummy, _Dummy, FakeConsumer),
    )

    def handler(payload):
        barrier.wait(timeout=2)
        handled.append(payload["value"])

    with pytest.raises(KeyboardInterrupt):
        adapter.consume_forever(handler)

    assert sorted(handled) == [1, 2]
    assert sorted(acknowledged) == [1, 2]
    assert FakeConsumer.instance.shutdown_called is True

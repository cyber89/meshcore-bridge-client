from __future__ import annotations

import asyncio
from collections import deque
from functools import lru_cache
from typing import Any


class MqttTelemetryBroadcaster:
    def __init__(self, *, backlog_size: int = 200, subscriber_queue_size: int = 200) -> None:
        self._history: deque[dict[str, Any]] = deque(maxlen=max(1, backlog_size))
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._subscriber_queue_size = max(1, subscriber_queue_size)

    def publish(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        self._history.append(payload)
        for queue in list(self._subscribers):
            self._push_to_queue(queue, payload)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        for event in self._history:
            self._push_to_queue(queue, event)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def reset(self) -> None:
        self._history.clear()
        self._subscribers.clear()

    @staticmethod
    def _push_to_queue(queue: asyncio.Queue[dict[str, Any]], payload: dict[str, Any]) -> None:
        try:
            queue.put_nowait(dict(payload))
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                queue.put_nowait(dict(payload))
            except asyncio.QueueFull:
                return


@lru_cache(maxsize=1)
def get_mqtt_telemetry_broadcaster() -> MqttTelemetryBroadcaster:
    return MqttTelemetryBroadcaster()

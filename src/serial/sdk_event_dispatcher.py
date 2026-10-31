"""sdk_event_dispatcher.py: Cola acotada, despacho determinista y handoff seguro de eventos del SDK."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from meshcore import EventType

logger = logging.getLogger(__name__)


class SdkEventDispatcher:
    """Administra la recepción asíncrona, descarte ordenado y despacho de eventos del SDK."""

    def __init__(
        self,
        mc_provider: Callable[[], Any],
        is_connected_provider: Callable[[], bool],
        heartbeat_callback: Callable[[], None],
        companion_frame_sink: Callable[[bytes], None],
        event_processor: Callable[[Any, Any], Awaitable[None]],
        add_task: Callable[[asyncio.Task[None]], None],
        discard_task: Callable[[asyncio.Task[None]], None],
        loop_provider: Callable[[], asyncio.AbstractEventLoop | None],
        serialize_sdk_response_waits: Callable[[], None],
        capacity: int = 256,
    ) -> None:
        self.mc_provider = mc_provider
        self.is_connected_provider = is_connected_provider
        self.heartbeat_callback = heartbeat_callback
        self.companion_frame_sink = companion_frame_sink
        self.event_processor = event_processor
        self.add_task = add_task
        self.discard_task = discard_task
        self.loop_provider = loop_provider
        self.serialize_sdk_response_waits = serialize_sdk_response_waits
        self.capacity = capacity

        self.pending_events: deque[tuple[Any, Any, Any, str | None]] = deque()
        self.worker: asyncio.Task[None] | None = None
        self.schedule_lock: threading.Lock = threading.Lock()
        self.scheduled_callbacks: int = 0
        self.overflow_count: int = 0

    def clear(self) -> None:
        """Limpia los eventos pendientes."""
        self.pending_events.clear()

    def register_event_handlers(self) -> None:
        """Registra suscripciones de eventos en la instancia activa del SDK MeshCore."""
        mc = self.mc_provider()
        if not mc:
            return
        owning_mc = mc
        self.serialize_sdk_response_waits()

        # Hook para interceptar tramas binarias de la radio y difundirlas a clientes companion
        if hasattr(mc, "_reader") and hasattr(mc._reader, "handle_rx"):
            original_handle_rx = mc._reader.handle_rx

            async def _hooked_handle_rx(data: bytearray) -> None:
                if self.is_connected_provider() and self.mc_provider() is owning_mc:
                    self.heartbeat_callback()
                    self.companion_frame_sink(bytes(data))
                await original_handle_rx(data)

            mc._reader.handle_rx = _hooked_handle_rx

        if not hasattr(mc, "subscribe"):
            return

        def _make_handler(et: Any) -> Callable[[Any], None]:
            def _handler(event: Any) -> None:
                try:
                    loop = self.loop_provider()
                    if loop is None or loop.is_closed():
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            pass
                    if loop and loop.is_running():

                        def schedule() -> None:
                            if (
                                not self.is_connected_provider()
                                or self.mc_provider() is not owning_mc
                                or loop is None
                                or loop.is_closed()
                            ):
                                return
                            self.enqueue_sdk_event(owning_mc, et, event)

                        try:
                            running = asyncio.get_running_loop()
                            if running is loop:
                                schedule()
                                return
                        except RuntimeError:
                            pass

                        rejected = False
                        with self.schedule_lock:
                            if self.scheduled_callbacks >= self.capacity:
                                self.overflow_count += 1
                                rejected = True
                            else:
                                self.scheduled_callbacks += 1

                        if rejected:
                            logging.error(
                                "[SDK-RX-OVERFLOW] cross-thread handoff full; event rejected",
                                extra={"skip_broadcast": True},
                            )
                            return

                        def scheduled() -> None:
                            try:
                                schedule()
                            finally:
                                with self.schedule_lock:
                                    self.scheduled_callbacks -= 1

                        try:
                            loop.call_soon_threadsafe(scheduled)
                        except RuntimeError:
                            with self.schedule_lock:
                                self.scheduled_callbacks -= 1
                except Exception as ex:
                    logging.debug("Error despachando evento SDK %s: %s", et, ex)

            return _handler

        if EventType:
            for ev_type in EventType:
                try:
                    mc.subscribe(ev_type, _make_handler(ev_type))
                except Exception as e:
                    logging.debug("Suscripción a evento %s: %s", ev_type, e)

    def enqueue_sdk_event(self, owning_mc: Any, event_type: Any, event: Any) -> None:
        """Encola notificaciones acotando memoria y deduplicando anuncios."""
        key: str | None = None
        if str(getattr(event_type, "name", event_type)).upper() == "ADVERTISEMENT":
            payload = getattr(event, "payload", event)
            if isinstance(payload, dict):
                identity = payload.get("public_key", payload.get("key"))
                if identity:
                    key = f"advert:{identity}"

        if key is not None:
            for index, (_, _, _, old_key) in enumerate(self.pending_events):
                if old_key == key:
                    self.pending_events[index] = (owning_mc, event_type, event, key)
                    return

        if len(self.pending_events) >= self.capacity:
            observation = next(
                (
                    index
                    for index, (_, _, _, old_key) in enumerate(self.pending_events)
                    if old_key is not None
                ),
                None,
            )
            with self.schedule_lock:
                self.overflow_count += 1
            logging.error(
                "[SDK-RX-OVERFLOW] capacity=%d count=%d critical=%s",
                self.capacity,
                self.overflow_count,
                key is None and observation is None,
                extra={"skip_broadcast": True},
            )
            if key is not None or observation is None:
                return
            del self.pending_events[observation]

        self.pending_events.append((owning_mc, event_type, event, key))
        self.ensure_worker()

    def ensure_worker(self) -> None:
        """Asegura que exista un worker en ejecución para vaciar la cola de eventos."""
        if not self.pending_events or (self.worker is not None and not self.worker.done()):
            return
        task = asyncio.create_task(self.drain_events(), name="CompanionSdkEvents")
        self.worker = task
        self.add_task(task)
        task.add_done_callback(self._worker_done)

    def _worker_done(self, task: asyncio.Task[None]) -> None:
        self.discard_task(task)
        if self.worker is task:
            self.worker = None
        if not task.cancelled():
            error = task.exception()
            if error:
                logging.debug("Evento SDK falló: %s", type(error).__name__)
            if self.is_connected_provider():
                self.ensure_worker()

    async def drain_events(self) -> None:
        """Drena y procesa secuencialmente los eventos encolados."""
        while self.pending_events:
            owning_mc, event_type, event, _ = self.pending_events.popleft()
            if self.is_connected_provider() and self.mc_provider() is owning_mc:
                try:
                    await self.event_processor(event_type, event)
                except Exception as error:
                    logging.debug("Evento SDK falló: %s", type(error).__name__)

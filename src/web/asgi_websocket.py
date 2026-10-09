"""Connection logging, abort and idle ping policy for Uvicorn 0.54.0 SansIO.

The upstream backend logs upgrade paths including queries even when HTTP access
logging is disabled. Keep authentication inputs intact and sanitize only the
instance's log arguments; no logger handlers or process-wide levels are changed.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, cast

from uvicorn import Config
from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol
from uvicorn.server import ServerState
from websockets.http11 import Request

from src.web.asgi_logging import SafeProtocolLogger
from src.web.asgi_security import WS_ABORT_EXTENSION


class BridgeWebSocketProtocol(WebSocketsSansIOProtocol):
    """Version-specific abort and passive idle ping seams, with private logs.

    Native idle pings use an empty payload and require no pong acknowledgement.
    Resetting on transport chunks differs from the native complete-frame reader;
    SansIO accepts fragmentation and has no native per-frame 10-second deadline.
    These differences remain acceptance gates, not claims of protocol parity.
    """

    def __init__(
        self,
        config: Config,
        server_state: ServerState,
        app_state: dict[str, Any],
        _loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__(config, server_state, app_state, _loop)
        safe_logger = SafeProtocolLogger(self.logger, {})
        # Upstream annotates self.logger as Logger but uses this adapter's .level,
        # .info/.error/.exception and .log interfaces. The cast confines that
        # version-specific annotation boundary; it does not change the object.
        self.logger = cast(logging.Logger, safe_logger)
        self.conn.logger = safe_logger
        # websockets 16.1.1 caches DEBUG availability in its constructor, before
        # the private adapter can replace the logger assigned by Uvicorn.
        self.conn.debug = False
        self._idle_timer: asyncio.TimerHandle | None = None
        self._idle_task: asyncio.Task[None] | None = None
        self._idle_enabled = False
        self._idle_interval = float(os.getenv("WS_IDLE_TIMEOUT_SEC", "30.0"))

    def handle_connect(self, event: Request) -> None:
        # Upstream schedules run_asgi without yielding. Attach the callback to
        # its newly created scope before that task can run perimeter/endpoint.
        super().handle_connect(event)
        scope = getattr(self, "scope", None)
        if scope is not None:
            scope.setdefault("extensions", {})[WS_ABORT_EXTENSION] = self._abort_peer

    def _abort_peer(self) -> None:
        self.stop_keepalive()
        self.transport.abort()

    def start_keepalive(self) -> None:
        """Reuse native idle interval; do not enable upstream pong-timeout policy."""
        self._idle_enabled = True
        self._schedule_idle_ping()

    def stop_keepalive(self) -> None:
        self._idle_enabled = False
        super().stop_keepalive()
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None
        task = self._idle_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _schedule_idle_ping(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None
        if (
            self._idle_enabled
            and self.handshake_complete
            and not self.close_sent
            and not self.disconnected
        ):
            self._idle_timer = self.loop.call_later(
                self._idle_interval, self._begin_idle_ping
            )

    def data_received(self, data: bytes) -> None:
        super().data_received(data)
        # Incoming control frames and message chunks are activity. This never
        # calls the radio, router, MQTT bus or an administrative handler.
        self._schedule_idle_ping()

    def _begin_idle_ping(self) -> None:
        self._idle_timer = None
        if self._idle_task is not None and not self._idle_task.done():
            return
        task = self.loop.create_task(
            self._send_idle_ping(), name="MeshCoreASGIIdlePing"
        )
        self._idle_task = task
        self.tasks.add(task)
        task.add_done_callback(self._idle_ping_done)

    def _idle_ping_done(self, task: asyncio.Task[None]) -> None:
        self.tasks.discard(task)
        if self._idle_task is task:
            self._idle_task = None
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                self.logger.warning(
                    "WebSocket idle ping failed with %s", type(error).__name__
                )
        if not self.close_sent and not self.disconnected:
            self._schedule_idle_ping()

    async def _send_idle_ping(self) -> None:
        deadline = self.loop.time() + 2.0
        try:
            # Native control-frame writes already allow two seconds. Writable
            # wait is ASGI flow control, not an asserted StreamWriter.drain match.
            await asyncio.wait_for(
                self.writable.wait(), timeout=max(0.0, deadline - self.loop.time())
            )
            if self.close_sent or self.disconnected:
                return
            self.conn.send_ping(b"")
            self.transport.write(b"".join(self.conn.data_to_send()))
            await asyncio.wait_for(
                self.writable.wait(), timeout=max(0.0, deadline - self.loop.time())
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._abort_peer()

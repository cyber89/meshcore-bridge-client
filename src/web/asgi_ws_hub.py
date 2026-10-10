"""Inactive WebSocket application adapter borrowing the existing router state.

The protocol backend owns RFC 6455 control frames; this hub handles only the
existing JSON heartbeat and event delivery. ASGI message limits and send pressure
are not asserted to be equivalent to the native frame reader and writer.drain.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from src.web.asgi_security import WS_ABORT_EXTENSION
from src.web.security_inspector import SecurityTrafficInspector

if TYPE_CHECKING:
    from src.web.api_router import WebAPIRouter

logger = logging.getLogger(__name__)

# The native broadcast writer already uses this budget. No new queue, retry,
# capacity, radio interval or delivery acknowledgement is introduced here.
WS_SEND_TIMEOUT_SEC = 2.0


@dataclass(slots=True)
class _Peer:
    socket: WebSocket
    task: asyncio.Task[Any]
    client_ip: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ready: bool = False
    logged: bool = False


class WebSocketHub:
    """Own web tasks and peers, never the bridge, router or map tile service."""

    def __init__(self, router: WebAPIRouter) -> None:
        self.router = router
        self.bridge = router.bridge
        self.running = False
        self._start_time = time.time()
        self._peers: dict[WebSocket, _Peer] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._metrics_task: asyncio.Task[None] | None = None
        self._shutdown_deadline: float | None = None

    def _retain(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._consume)

    def _consume(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                # Raw exception values may contain SDK/configuration secrets.
                logger.warning("WebSocket task ended with %s", type(error).__name__)

    def owned_tasks(self) -> set[asyncio.Task[Any]]:
        """Give the server owner pending tasks for its common shutdown deadline."""
        return {task for task in self._tasks if not task.done()}

    async def start(self) -> None:
        """Start the existing passive metrics timer once per web lifespan."""
        if self.running:
            return
        if self.owned_tasks():
            raise RuntimeError("Previous WebSocket lifecycle has not finished")
        self._shutdown_deadline = None
        self.running = True
        self._metrics_task = asyncio.create_task(
            self._metrics_loop(), name="MeshCoreASGIWebSocketMetrics"
        )
        self._retain(self._metrics_task)

    @staticmethod
    def _abort(peer: _Peer) -> bool:
        extensions = peer.socket.scope.get("extensions", {})
        abort = extensions.get(WS_ABORT_EXTENSION)
        if callable(abort):
            try:
                abort()
                return True
            except Exception:
                logger.warning("WebSocket transport abort failed")
        return False

    def force_stop(self, *, deadline: float | None = None) -> None:
        """Synchronously release transports and cancel only this hub's tasks."""
        if deadline is not None:
            self._shutdown_deadline = deadline
        self.running = False
        current = asyncio.current_task()
        for peer in list(self._peers.values()):
            self._abort(peer)
        for task in self.owned_tasks():
            if task is not current:
                task.cancel()

    async def stop(self, deadline: float) -> None:
        """Use the server owner's absolute loop deadline, never a second budget."""
        self.force_stop(deadline=deadline)
        current = asyncio.current_task()
        tasks = {task for task in self.owned_tasks() if task is not current}
        if tasks:
            _, pending = await asyncio.wait(
                tasks,
                timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
            )
            for task in pending:
                task.cancel()
            if pending:
                logger.warning("WebSocket tasks exceeded owner shutdown budget: %s", len(pending))
        # Cancellation-resistant tasks remain retained and prevent a restart.

    def _remove_peer(self, peer: _Peer) -> None:
        self._peers.pop(peer.socket, None)
        peer.ready = False
        if peer.logged:
            peer.logged = False
            try:
                SecurityTrafficInspector.log_websocket_connection(
                    client_ip=peer.client_ip,
                    event="Conexión WebSocket cerrada",
                    active_count=len(self._peers),
                )
            except Exception:
                # A failing log handler must not prevent connection cleanup.
                pass

    async def _close_socket(self, peer: _Peer) -> None:
        async with peer.lock:
            if peer.socket.application_state == WebSocketState.CONNECTED:
                await peer.socket.close()

    async def _close_peer(self, peer: _Peer) -> None:
        if peer.socket.application_state != WebSocketState.CONNECTED:
            # An earlier close may already have armed the backend close timer.
            self._abort(peer)
            return
        budget = WS_SEND_TIMEOUT_SEC
        if self._shutdown_deadline is not None:
            budget = min(
                budget,
                max(0.0, self._shutdown_deadline - asyncio.get_running_loop().time()),
            )
        if budget <= 0.0:
            self._abort(peer)
            return
        close_task = asyncio.create_task(
            self._close_socket(peer), name="MeshCoreASGIWebSocketClose"
        )
        self._retain(close_task)
        try:
            _, pending = await asyncio.wait({close_task}, timeout=budget)
            if pending:
                close_task.cancel()
            else:
                await close_task
        except asyncio.CancelledError:
            close_task.cancel()
            raise
        except Exception:
            pass
        finally:
            # The native endpoint closes its writer immediately after the
            # best-effort close acknowledgement. Do not retain a transport for
            # the backend's 10 s close timer after releasing admission capacity.
            # The ASGI close frame may still be buffered when abort is requested;
            # delivery and acknowledgement are not guaranteed here.
            self._abort(peer)

    async def endpoint(self, websocket: WebSocket) -> None:
        """Accept after perimeter checks; send welcome then initial metrics first."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("WebSocket endpoint requires an asyncio task")
        self._retain(task)
        client = websocket.client
        client_ip = client.host if client is not None else "unknown"
        if client_ip.startswith("::ffff:"):
            client_ip = client_ip[7:]
        peer = _Peer(websocket, task, client_ip)
        self._peers[websocket] = peer
        try:
            if not self.running:
                await websocket.close()
                return
            async with peer.lock:
                await websocket.accept()
                peer.logged = True
                try:
                    SecurityTrafficInspector.log_websocket_connection(
                        client_ip=client_ip,
                        event="Conexión WebSocket establecida",
                        active_count=len(self._peers),
                    )
                except Exception:
                    pass
                await websocket.send_text(json.dumps({
                    "event_type": "ws_connected",
                    "message": "Conectado al servidor WebSocket en vivo de MeshCore Bridge",
                    "timestamp": int(time.time()),
                }, default=str))
                await websocket.send_text(json.dumps(self._metrics(initial=True), default=str))
                peer.ready = True
            while self.running and websocket in self._peers:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if not isinstance(text, str):
                    # Native opcode 2 is ignored, including JSON binary frames.
                    continue
                try:
                    payload = json.loads(text)
                except Exception:
                    continue
                if isinstance(payload, dict) and payload.get("type") == "ping":
                    async with peer.lock:
                        await websocket.send_text(json.dumps({
                            "type": "pong", "timestamp": int(time.time())
                        }))
        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            pass
        except Exception as error:
            logger.debug("WebSocket endpoint ended with %s", type(error).__name__)
        finally:
            self._remove_peer(peer)
            await self._close_peer(peer)

    async def _send_to_peer(self, peer: _Peer, text: str) -> None:
        async with peer.lock:
            if self.running and peer.ready and peer.socket in self._peers:
                await peer.socket.send_text(text)

    async def _deliver_to_peer(self, peer: _Peer, text: str) -> None:
        if not self.running:
            return
        send_task = asyncio.create_task(
            self._send_to_peer(peer, text), name="MeshCoreASGIWebSocketSend"
        )
        self._retain(send_task)
        try:
            _, pending = await asyncio.wait({send_task}, timeout=WS_SEND_TIMEOUT_SEC)
            if pending:
                send_task.cancel()
                raise TimeoutError
            if send_task.cancelled() and not self.running:
                # Shutdown cancelled this hub's child, not the bridge caller.
                return
            await send_task
        except asyncio.CancelledError:
            send_task.cancel()
            raise
        except Exception:
            self._remove_peer(peer)
            self._abort(peer)
            peer.task.cancel()

    async def broadcast_event(self, event_data: dict[str, Any]) -> None:
        """Record history exactly once, including when no clients are connected."""
        self.router.record_incoming_event(event_data)
        peers = [peer for peer in self._peers.values() if peer.ready]
        if not peers or not self.running:
            return
        text = json.dumps(event_data, default=str)
        delivery_tasks = [self._deliver_to_peer(peer, text) for peer in peers]
        await asyncio.gather(*delivery_tasks, return_exceptions=True)

    def _metrics(self, *, initial: bool) -> dict[str, Any]:
        """Preserve native initial/periodic field differences and tracker defaults."""
        total_rx = getattr(self.bridge, "rx_count", 0)
        total_tx = getattr(self.bridge, "tx_count", 0)
        total_err = getattr(self.bridge, "tx_error_count", 0) + getattr(self.bridge, "err_count", 0)
        total_pkts = total_rx + total_tx
        node_cnt = self.bridge.node_registry.get_count() if hasattr(self.bridge, "node_registry") else 0
        q_depth = self.bridge.rate_limiter.get_queue_depth() if hasattr(self.bridge, "rate_limiter") else 0
        serial = getattr(self.bridge, "serial_adapter", None)
        if serial and hasattr(serial, "is_hardware_alive"):
            radio_ok = bool(serial.is_hardware_alive())
        else:
            radio_ok = getattr(serial, "is_connected", False) if serial else False
            if initial:
                radio_ok = bool(radio_ok)
        bridge_start = getattr(self.bridge, "start_time", None)
        start = float(bridge_start) if isinstance(bridge_start, (int, float)) else self._start_time
        uptime = max(0, int(time.time() - start))
        days, hours, mins = uptime // 86400, (uptime % 86400) // 3600, (uptime % 3600) // 60
        uptime_str = f"{days}d {hours}h {mins}m" if days > 0 else (f"{hours}h {mins}m" if hours > 0 else f"{mins}m")
        limiter = getattr(self.bridge, "rate_limiter", None)
        airtime = limiter.airtime_tracker.get_stats() if limiter and hasattr(limiter, "airtime_tracker") else {}
        result: dict[str, Any] = {
            "event": "metrics_update", "type": "metrics_update",
            "node_count": node_cnt, "rx_count": total_rx, "tx_count": total_tx,
            "error_rate": round(total_err / total_pkts * 100.0, 1) if total_pkts > 0 else 0.0,
            "queue_depth": q_depth, "serial_connected": radio_ok, "radio_connected": radio_ok,
            "uptime": uptime, "uptime_str": uptime_str,
            "airtime_ms": airtime.get("hourly_used_ms", 0),
            "duty_cycle_pct": airtime.get("hourly_duty_cycle_pct", 0.0),
            "hourly_limit_pct": airtime.get("hourly_limit_pct", 1.0),
            "warn_threshold_pct": airtime.get("warn_threshold_pct", 80.0),
            "is_warning": airtime.get("is_warning", False),
            "is_critical": airtime.get("is_critical", False),
            "status_level": airtime.get("status_level", "normal"),
            "channel_stats": airtime.get("channel_stats", {}), "airtime": airtime,
            "duplicate_packets": getattr(self.bridge, "dup_count", 0), "packet_errors": total_err,
        }
        if initial:
            result["radio_port"] = getattr(serial, "port", "") if serial else ""
        return result

    async def _metrics_loop(self) -> None:
        interval = float(os.getenv("WS_METRICS_INTERVAL_SEC", "5.0"))
        while self.running:
            try:
                await asyncio.sleep(interval)
                if any(peer.ready for peer in self._peers.values()):
                    await self.broadcast_event(self._metrics(initial=False))
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.warning("WebSocket metrics failed with %s", type(error).__name__)

"""companion_proxy.py: Proxy de socket TCP Companion, arbitraje RF y puente para aplicaciones clientes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.rate_limiter import TxItem, TxPriority
from src.serial.companion_protocol import companion_command_kind

logger = logging.getLogger(__name__)


class CompanionProxy:
    """Gestiona el reenvío de tramas Companion sobre TCP y coordina comandos administrativos RF."""

    def __init__(
        self,
        tcp_server_provider: Callable[[], Any],
        is_running_provider: Callable[[], bool],
        schedule_bg_fn: Callable[[Callable[[], Any]], None],
        rate_limiter_provider: Callable[[], Any],
        node_registry_provider: Callable[[], Any],
        serial_adapter_provider: Callable[[], Any],
        packet_buffer_provider: Callable[[], Any],
        on_metrics_tx: Callable[[bool], Awaitable[None]] | None = None,
    ) -> None:
        self.tcp_server_provider = tcp_server_provider
        self.is_running_provider = is_running_provider
        self.schedule_bg_fn = schedule_bg_fn
        self.rate_limiter_provider = rate_limiter_provider
        self.node_registry_provider = node_registry_provider
        self.serial_adapter_provider = serial_adapter_provider
        self.packet_buffer_provider = packet_buffer_provider
        self.on_metrics_tx = on_metrics_tx

    def on_raw_companion_frame_rx(self, payload: bytes) -> None:
        """Difunde tramas binarias de la radio hacia clientes TCP Companion en estricto orden FIFO."""
        tcp_srv = self.tcp_server_provider()
        if tcp_srv is not None and self.is_running_provider():
            owner = tcp_srv.get_response_owner() if hasattr(tcp_srv, "get_response_owner") else None
            if payload and payload[0] < 0x80:
                if owner is None:
                    return
                if hasattr(tcp_srv, "note_response_received"):
                    tcp_srv.note_response_received(owner)
                if hasattr(tcp_srv, "queue_companion_frame_sync"):
                    tcp_srv.queue_companion_frame_sync(payload, response_owner=owner)
                else:
                    self.schedule_bg_fn(
                        lambda: tcp_srv.broadcast_companion_frame(payload, response_owner=owner)
                    )
            else:
                if hasattr(tcp_srv, "queue_companion_frame_sync"):
                    tcp_srv.queue_companion_frame_sync(payload)
                else:
                    self.schedule_bg_fn(lambda: tcp_srv.broadcast_companion_frame(payload))

    async def handle_tcp_companion_command(
        self, payload: bytes, client_writer: Any = None, timeout: float = 30.0
    ) -> bool:
        """Maneja comandos binarios enviados por apps móviles o CLI a través del socket TCP Companion."""
        kind = companion_command_kind(payload)
        if kind is None:
            return False
        serial_adapter = self.serial_adapter_provider()
        if kind == "rf":
            rate_limiter = self.rate_limiter_provider()
            if (
                rate_limiter
                and hasattr(rate_limiter, "is_cutoff_active")
                and rate_limiter.is_cutoff_active()
            ):
                return False
            target, channel_idx = self.companion_rf_destination(payload)
            node_reg = self.node_registry_provider()
            if target and node_reg:
                is_local = getattr(node_reg, "is_local_key", lambda k: False)(target)
                is_rep = getattr(node_reg, "is_repeater_key", lambda k: False)(target)
                is_user_chat = payload[0] == 2 and (len(payload) < 2 or payload[1] != 1)
                if is_local or (is_rep and is_user_chat):
                    return False
            if payload[0] in (2, 3) and len(payload) < (14 if payload[0] == 2 else 8):
                return False
            if rate_limiter and hasattr(rate_limiter, "submit"):
                try:
                    future = await rate_limiter.submit(
                        payload=payload,
                        priority=TxPriority.NORMAL,
                        target=target,
                        channel_idx=channel_idx,
                    )
                    async with asyncio.timeout(timeout):
                        result = await future
                    return isinstance(result, dict) and str(result.get("status", "")).lower() in (
                        "sent",
                        "ok",
                        "success",
                    )
                except TimeoutError:
                    logging.warning(
                        "Timeout esperando transmisión TCP Companion en rate limiter",
                        extra={"skip_broadcast": True},
                    )
                    return False
                except Exception:
                    logging.warning(
                        "No se pudo enviar comando TCP por la cola TX",
                        extra={"skip_broadcast": True},
                    )
                    return False
            elif rate_limiter is None:
                if serial_adapter and hasattr(serial_adapter, "send_raw_companion_frame"):
                    return bool(await serial_adapter.send_raw_companion_frame(payload))
                return False
        if serial_adapter and hasattr(serial_adapter, "send_raw_companion_frame"):
            return bool(await serial_adapter.send_raw_companion_frame(payload))
        return False

    @staticmethod
    def companion_rf_destination(payload: bytes) -> tuple[str | None, int]:
        """Obtiene el destino y canal decodificados de la trama Companion según layout oficial."""
        opcode = payload[0]
        if opcode == 2 and len(payload) >= 14:
            return payload[7:13].hex(), 0
        if opcode == 3 and len(payload) >= 8:
            return None, payload[2]
        if opcode in (26, 27, 50, 57) and len(payload) >= 33:
            return payload[1:33].hex(), 0
        if opcode == 39 and len(payload) >= 36:
            return payload[4:36].hex(), 0
        if opcode == 52 and len(payload) >= 34:
            return payload[2:34].hex(), 0
        if opcode == 62 and len(payload) >= 4:
            return None, payload[1]
        return None, 0

    async def execute_companion_control_tx(self, item: TxItem) -> dict[str, Any]:
        """Envía comandos administrativos o de infraestructura sin convertirlos en mensajes de chat."""
        node_reg = self.node_registry_provider()
        if item.target and node_reg and node_reg.is_local_key(item.target):
            return {"status": "error", "error": "Destino local no permitido"}
        serial_adapter = self.serial_adapter_provider()
        success = False
        try:
            if serial_adapter and hasattr(serial_adapter, "send_raw_companion_frame"):
                success = bool(await serial_adapter.send_raw_companion_frame(item.payload))
        except Exception as error:
            logging.warning(
                "Fallo TX Companion administrativo: %s",
                type(error).__name__,
                extra={"skip_broadcast": True},
            )
        if self.on_metrics_tx is not None:
            await self.on_metrics_tx(success)
        pkt_buf = self.packet_buffer_provider()
        if success and pkt_buf is not None:
            pkt_buf.record(
                direction="tx",
                channel_idx=item.channel_idx,
                packet_type="ADMIN",
                target=item.target or "broadcast",
                raw_bytes=item.payload,
                redact_content=True,
            )
        return {"status": "sent" if success else "error", "request_id": item.request_id}

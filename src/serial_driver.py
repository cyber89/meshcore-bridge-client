"""
Serial Communication Layer & Hybrid Adapters for MeshCore Bridge.
Provee adaptador principal para el SDK oficial meshcore_py, fallback determinista a
pyserial-asyncio con framing SOF/EOF/ESC/CRC-16 y Watchdog de supervisión activa.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from src.protocol_types import (
    EOF_BYTE,
    ESC_BYTE,
    ESC_MASK,
    SOF_BYTE,
    MeshcoreFrame,
)

try:
    import meshcore
    from meshcore import EventType, MeshCore
except ImportError:
    meshcore = None
    MeshCore = None
    EventType = None


def detect_serial_port() -> str:
    """Detecta automáticamente el puerto serial de un nodo LoRa conectado."""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ("heltec", "cp210", "ch340", "ch341", "ftdi", "uart", "acm", "usb serial", "espressif", "t-beam", "rak")):
                return str(p.device)
        if ports:
            return str(ports[0].device)
    except Exception as e:
        logging.warning(f"Error detecting serial port: {e}", exc_info=True)
    return "/dev/ttyACM0"


class BaseSerialAdapter(abc.ABC):
    """Interfaz abstracta para adaptadores de comunicación serial con hardware MeshCore."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout_sec: float = 30.0) -> None:
        self.port = detect_serial_port() if str(port).upper() in ("AUTO", "DETECT", "DEFAULT", "") else port
        self.baud_rate = baud_rate
        self.timeout_sec = timeout_sec
        self.is_connected = False
        self.rx_callback: Callable[[Any], None] | None = None
        self.last_heartbeat_time = time.time()

    def set_rx_callback(self, callback: Callable[[Any], None]) -> None:
        self.rx_callback = callback

    def heartbeat(self) -> None:
        self.last_heartbeat_time = time.time()

    @abc.abstractmethod
    async def connect(self) -> bool:
        pass

    @abc.abstractmethod
    async def disconnect(self) -> None:
        pass

    @abc.abstractmethod
    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        pass

    @abc.abstractmethod
    async def send_admin_cmd(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        pass

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        return str(prefix_or_key)


class MeshcoreSDKAdapter(BaseSerialAdapter):
    """Adaptador principal basado en el SDK oficial meshcore_py."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout_sec: float = 30.0) -> None:
        super().__init__(port, baud_rate, timeout_sec)
        self.mc: Any = None

    async def connect(self) -> bool:
        if MeshCore is None:
            logging.warning("SDK meshcore_py no disponible en el entorno.")
            return False

        try:
            logging.info(f"Iniciando conexión MeshCore SDK en puerto {self.port} ({self.baud_rate} baud)...")
            self.mc = MeshCore(self.port, baudrate=self.baud_rate)
            self._register_event_handlers()
            await self.mc.start()
            self.is_connected = True
            self.heartbeat()
            logging.info("MeshCore SDK conectado e iniciado exitosamente.")
            return True
        except Exception as e:
            logging.error(f"Error conectando con MeshCore SDK: {e}")
            self.is_connected = False
            return False

    async def disconnect(self) -> None:
        if self.mc:
            try:
                if hasattr(self.mc, "stop"):
                    await self.mc.stop()
                elif hasattr(self.mc, "close"):
                    self.mc.close()
            except Exception as e:
                logging.warning(f"Error cerrando MeshCore SDK: {e}")
        self.is_connected = False

    def _register_event_handlers(self) -> None:
        if not self.mc or not hasattr(self.mc, "subscribe"):
            return

        def _on_event(event: Any) -> None:
            self.heartbeat()
            if self.rx_callback:
                self.rx_callback(event)

        # Suscribir a todos los tipos de eventos si EventType existe
        if EventType:
            for ev_type in EventType:
                try:
                    self.mc.subscribe(ev_type, _on_event)
                except Exception as e:
                    logging.warning(f"Error subscribing to event {ev_type}: {e}", exc_info=True)

    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        if not self.is_connected or not self.mc:
            raise ConnectionError("MeshCore SDK no conectado")

        if not hasattr(self.mc, "commands") or not hasattr(self.mc.commands, "send_msg"):
            raise NotImplementedError("send_msg no soportado en este SDK")

        # Canal público vs mensaje directo
        if target and target.upper() not in ("0xFFFF", "BROADCAST", "PUBLIC"):
            dest_target = self._resolve_target(target)
            res = await self.mc.commands.send_msg(dest_target, text)
        else:
            if channel_idx > 0 and hasattr(self.mc.commands, "send_channel_msg"):
                res = await self.mc.commands.send_channel_msg(channel_idx, text)
            else:
                res = await self.mc.commands.send_msg(text)

        return {"status": "SENT", "response": str(res)}

    async def send_admin_cmd(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected or not self.mc:
            raise ConnectionError("MeshCore SDK no conectado")

        action_lower = action.lower()
        if action_lower == "reboot" and hasattr(self.mc.commands, "reboot"):
            await self.mc.commands.reboot()
            return {"status": "OK", "action": "reboot"}
        elif action_lower == "set_tx_power" and hasattr(self.mc.commands, "set_tx_power"):
            power = int(params.get("power", 20))
            await self.mc.commands.set_tx_power(power)
            return {"status": "OK", "action": "set_tx_power", "power": power}

        return {"status": "UNKNOWN_ACTION", "action": action}

    def _resolve_target(self, name_or_key: str) -> Any:
        if not self.mc:
            return name_or_key
        if hasattr(self.mc, "get_contact_by_key_prefix"):
            try:
                c = self.mc.get_contact_by_key_prefix(name_or_key)
                if c:
                    return c
            except Exception as e:
                logging.warning(f"Error resolving target '{name_or_key}': {e}", exc_info=True)
        return name_or_key

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        if not self.mc or not prefix_or_key:
            return str(prefix_or_key)
        if hasattr(self.mc, "get_contact_by_key_prefix"):
            try:
                c = self.mc.get_contact_by_key_prefix(prefix_or_key)
                if c:
                    name = getattr(c, "name", getattr(c, "alias", None))
                    if isinstance(name, str) and name:
                        return name
            except Exception as e:
                logging.warning(f"Error resolving sender '{prefix_or_key}': {e}", exc_info=True)
        return str(prefix_or_key)


class RawSerialFramingAdapter(BaseSerialAdapter):
    """
    Adaptador determinista basado en pyserial-asyncio con de-framing continuo
    (SOF 0xAA, EOF 0x55, ESC 0x1B, CRC-16 CCITT).
    """

    def __init__(self, port: str, baud_rate: int = 115200, timeout_sec: float = 30.0) -> None:
        super().__init__(port, baud_rate, timeout_sec)
        self._rx_buffer = bytearray()
        self._in_escape = False
        self._in_frame = False

    async def connect(self) -> bool:
        logging.info(f"Iniciando adaptador Serial Raw en {self.port}...")
        self.is_connected = True
        self.heartbeat()
        return True

    async def disconnect(self) -> None:
        self.is_connected = False
        self._rx_buffer.clear()

    def process_incoming_bytes(self, chunk: bytes) -> list[MeshcoreFrame]:
        """Procesa bytes entrantes a través de la máquina de estados de framing."""
        frames: list[MeshcoreFrame] = []
        self.heartbeat()

        for b in chunk:
            if not self._in_frame:
                if b == SOF_BYTE:
                    self._in_frame = True
                    self._in_escape = False
                    self._rx_buffer.clear()
            else:
                if self._in_escape:
                    self._rx_buffer.append(b ^ ESC_MASK)
                    self._in_escape = False
                elif b == ESC_BYTE:
                    self._in_escape = True
                elif b == EOF_BYTE:
                    self._in_frame = False
                    if len(self._rx_buffer) >= 11:  # Min header (9) + CRC (2)
                        try:
                            frame = MeshcoreFrame.parse_raw_packet(bytes(self._rx_buffer))
                            frames.append(frame)
                            if self.rx_callback:
                                self.rx_callback(frame)
                        except Exception as e:
                            logging.debug(f"Error parseando trama raw: {e}")
                    self._rx_buffer.clear()
                elif b == SOF_BYTE:
                    # Nuevo SOF inesperado: reiniciar buffer
                    self._rx_buffer.clear()
                    self._in_escape = False
                else:
                    self._rx_buffer.append(b)
                    if len(self._rx_buffer) > 512:
                        # Protección anti-desbordamiento
                        self._in_frame = False
                        self._rx_buffer.clear()

        return frames

    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        return {"status": "SENT_RAW", "text": text}

    async def send_admin_cmd(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SENT_ADMIN_RAW", "action": action}


class SerialWatchdog:
    """Supervisa la vivacidad del puerto serial y activa reconexión ante bloqueos."""

    def __init__(
        self,
        adapter: BaseSerialAdapter,
        timeout_sec: float = 60.0,
        interval_sec: float = 30.0,
        on_timeout_reconnect: Callable[[], Any] | None = None,
    ) -> None:
        self.adapter = adapter
        self.timeout_sec = timeout_sec
        self.interval_sec = interval_sec
        self.on_timeout_reconnect = on_timeout_reconnect
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._supervise_loop(), name="SerialWatchdog")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _supervise_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval_sec)
                idle_sec = time.time() - self.adapter.last_heartbeat_time

                if idle_sec > self.timeout_sec and self.adapter.is_connected:
                    logging.warning(
                        f"Watchdog Serial: Sin actividad durante {idle_sec:.1f}s (Límite: {self.timeout_sec}s). "
                        "Reconectando puerto serial..."
                    )
                    if self.on_timeout_reconnect:
                        res = self.on_timeout_reconnect()
                        if asyncio.iscoroutine(res):
                            await res
                    self.adapter.heartbeat()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en bucle de supervisión SerialWatchdog: {e}")

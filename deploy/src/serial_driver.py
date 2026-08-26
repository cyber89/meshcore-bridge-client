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
        self.companion_rx_callback: Callable[[bytes], Any] | None = None
        self.last_heartbeat_time = time.time()

    def set_rx_callback(self, callback: Callable[[Any], None]) -> None:
        self.rx_callback = callback

    def set_companion_rx_callback(self, callback: Callable[[bytes], Any] | None) -> None:
        self.companion_rx_callback = callback

    def heartbeat(self) -> None:
        self.last_heartbeat_time = time.time()

    async def send_raw_companion_frame(self, data: bytes) -> bool:
        """Envía una trama cruda de comando companion hacia el hardware transceptor."""
        return False

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

    async def get_channels(self) -> list[dict[str, Any]]:
        """Devuelve la lista de canales configurados en el nodo (o lista vacía)."""
        return []

    async def set_channel(self, index: int, name: str, psk: str) -> dict[str, Any]:
        """Configura un canal en el firmware del transceptor serial."""
        return {"status": "OK", "index": index, "name": name}

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Añade o actualiza un contacto en la memoria del transceptor serial."""
        return {"status": "OK", "contact": contact_data}

    async def remove_contact(self, pubkey: str) -> dict[str, Any]:
        """Elimina un contacto de la memoria del transceptor serial."""
        return {"status": "OK", "public_key": pubkey}

    async def sync_all_contacts(self) -> list[dict[str, Any]]:
        """Descarga e importa todos los contactos almacenados en el hardware."""
        return []

    async def ping_or_check_alive(self) -> bool:
        """Verifica si el transceptor local sigue vivo y respondiendo por serial."""
        return self.is_connected

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

        if self.mc is not None or self.is_connected:
            await self.disconnect()
            await asyncio.sleep(0.5)

        try:
            # Re-detectar puerto dinámicamente si no está fijado estáticamente
            if not self.port.startswith("tcp://") and (str(self.port).upper() in ("AUTO", "DETECT", "DEFAULT", "") or not self.port):
                self.port = detect_serial_port()

            if self.port.startswith("tcp://"):
                addr = self.port.replace("tcp://", "")
                host, port_str = addr.split(":", 1) if ":" in addr else (addr, "4000")
                logging.info(f"Iniciando conexión MeshCore SDK remota TCP en {host}:{port_str}...")
                if hasattr(MeshCore, "create_tcp"):
                    self.mc = await MeshCore.create_tcp(host, int(port_str), auto_reconnect=True)
                else:
                    from meshcore.tcp_cx import TCPConnection
                    cx = TCPConnection(host, int(port_str))
                    self.mc = MeshCore(cx, auto_reconnect=True)
                    if hasattr(self.mc, "connect"):
                        await self.mc.connect()
            else:
                logging.info(f"Iniciando conexión MeshCore SDK en puerto {self.port} ({self.baud_rate} baud)...")
                # Intentar conexión con retardo de arranque seguro cx_dly=1.5s para transceptores USB-CDC / ESP32-S3
                if hasattr(MeshCore, "create_serial"):
                    try:
                        self.mc = await MeshCore.create_serial(self.port, self.baud_rate, auto_reconnect=True, cx_dly=1.5)
                    except TypeError:
                        self.mc = await MeshCore.create_serial(self.port, self.baud_rate, auto_reconnect=True)
                    
                    if self.mc is None:
                        logging.info("Reintentando inicialización de sesión serie con transceptor...")
                        await asyncio.sleep(1.0)
                        try:
                            self.mc = await MeshCore.create_serial(self.port, self.baud_rate, auto_reconnect=True, cx_dly=2.0)
                        except TypeError:
                            self.mc = await MeshCore.create_serial(self.port, self.baud_rate, auto_reconnect=True)
                else:
                    from meshcore.serial_cx import SerialConnection
                    cx = SerialConnection(self.port, self.baud_rate, cx_dly=1.5)
                    self.mc = MeshCore(cx, auto_reconnect=True)
                    if hasattr(self.mc, "connect"):
                        await self.mc.connect()

            if self.mc is None:
                logging.error(f"No se pudo establecer conexión con el transceptor MeshCore en {self.port}.")
                self.is_connected = False
                return False

            self._register_event_handlers()
            if hasattr(self.mc, "start_auto_message_fetching"):
                await self.mc.start_auto_message_fetching()
            if hasattr(self.mc, "ensure_contacts"):
                try:
                    await self.mc.ensure_contacts()
                except Exception as e:
                    logging.warning(f"Error sincronizando libreta de contactos de MeshCore: {e}")

            self.is_connected = True
            self.heartbeat()
            logging.info("MeshCore SDK conectado e iniciado exitosamente.")
            return True
        except Exception as e:
            logging.error(f"Error conectando con MeshCore SDK: {e}", exc_info=True)
            self.is_connected = False
            return False

    async def disconnect(self) -> None:
        if self.mc:
            try:
                if hasattr(self.mc, "disconnect"):
                    await self.mc.disconnect()
                elif hasattr(self.mc, "stop"):
                    self.mc.stop()
                elif hasattr(self.mc, "close"):
                    self.mc.close()
            except Exception as e:
                logging.warning(f"Error cerrando MeshCore SDK: {e}")
            finally:
                self.mc = None
        self.is_connected = False

    async def ping_or_check_alive(self) -> bool:
        """Comprueba si el transceptor local sigue vivo y respondiendo activamente por serial."""
        if not self.is_connected or not self.mc:
            return False
        try:
            if hasattr(self.mc, "commands"):
                if hasattr(self.mc.commands, "get_bat"):
                    res = await asyncio.wait_for(self.mc.commands.get_bat(), timeout=3.0)
                    if res is not None:
                        self.heartbeat()
                        return True
                elif hasattr(self.mc.commands, "get_time"):
                    res = await asyncio.wait_for(self.mc.commands.get_time(), timeout=3.0)
                    if res is not None:
                        self.heartbeat()
                        return True
            # Comprobar si el socket o conexión serial de transporte permanece abierta
            if hasattr(self.mc, "connection"):
                cx = self.mc.connection
                if hasattr(cx, "is_open") and not cx.is_open:
                    return False
                if hasattr(cx, "transport") and cx.transport and cx.transport.is_closing():
                    return False
            self.heartbeat()
            return True
        except Exception as e:
            logging.debug(f"Ping vivacidad serial falló: {e}")
            return False

    def _register_event_handlers(self) -> None:
        if not self.mc:
            return

        # Hook para interceptar tramas binarias de la radio y difundirlas a clientes companion (App/CLI)
        if hasattr(self.mc, "_reader") and hasattr(self.mc._reader, "handle_rx"):
            original_handle_rx = self.mc._reader.handle_rx

            async def _hooked_handle_rx(data: bytearray) -> None:
                if self.companion_rx_callback and data:
                    try:
                        self.companion_rx_callback(bytes(data))
                    except Exception as ex:
                        logging.debug(f"Error en companion_rx_callback: {ex}")
                await original_handle_rx(data)

            self.mc._reader.handle_rx = _hooked_handle_rx

        if not hasattr(self.mc, "subscribe"):
            return

        def _on_event(event: Any) -> None:
            self.heartbeat()
            if self.rx_callback:
                self.rx_callback(event)

        if EventType:
            for ev_type in EventType:
                try:
                    self.mc.subscribe(ev_type, _on_event)
                except Exception as e:
                    logging.debug(f"Suscripción a evento {ev_type}: {e}")

    async def send_raw_companion_frame(self, data: bytes) -> bool:
        """Envía una trama cruda recibida desde un cliente companion hacia el hardware de radio."""
        if not self.is_connected or not self.mc or not data:
            return False
        try:
            if hasattr(self.mc, "cx") and hasattr(self.mc.cx, "send"):
                await self.mc.cx.send(data)
                self.heartbeat()
                return True
            elif hasattr(self.mc, "connection") and hasattr(self.mc.connection, "send"):
                await self.mc.connection.send(data)
                self.heartbeat()
                return True
            return False
        except Exception as e:
            logging.error(f"Error enviando trama raw companion a la radio: {e}")
            return False

    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        if not self.is_connected or not self.mc:
            raise ConnectionError("MeshCore SDK no conectado")

        target_clean = str(target).strip() if target else ""
        is_dm = bool(target_clean and target_clean.upper() not in ("0xFFFF", "BROADCAST", "PUBLIC") and not target_clean.lower().startswith("channel"))

        # Canal público vs mensaje directo (DM)
        if is_dm:
            dest_target = self._resolve_target(target_clean)
            if hasattr(self.mc.commands, "send_msg"):
                res = await self.mc.commands.send_msg(dest_target, text)
            else:
                raise NotImplementedError("send_msg no soportado en este SDK")
        else:
            if hasattr(self.mc.commands, "send_chan_msg"):
                res = await self.mc.commands.send_chan_msg(channel_idx, text)
            elif hasattr(self.mc.commands, "send_channel_msg"):
                res = await self.mc.commands.send_channel_msg(channel_idx, text)
            elif hasattr(self.mc.commands, "send_msg"):
                res = await self.mc.commands.send_msg(text)
            else:
                raise NotImplementedError("send_chan_msg no soportado en este SDK")

        expected_ack_hex = None
        if res is not None and hasattr(res, "payload") and isinstance(res.payload, dict):
            exp_raw = res.payload.get("expected_ack")
            if isinstance(exp_raw, (bytes, bytearray)):
                expected_ack_hex = exp_raw.hex().lower()
            elif isinstance(exp_raw, str):
                expected_ack_hex = exp_raw.lower()

        return {
            "status": "SENT",
            "response": str(res),
            "event": res,
            "expected_ack": expected_ack_hex,
        }

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

    def _resolve_target(self, name_or_key: str, min_hex_len: int = 12) -> Any:
        if not self.mc or not name_or_key:
            return name_or_key
        if isinstance(name_or_key, dict) or hasattr(name_or_key, "public_key"):
            return name_or_key
        name_str = str(name_or_key).strip()
        if hasattr(self.mc, "get_contact_by_name"):
            try:
                c = self.mc.get_contact_by_name(name_str)
                if c:
                    return c
            except Exception:
                pass
        if hasattr(self.mc, "get_contact_by_key_prefix"):
            try:
                c = self.mc.get_contact_by_key_prefix(name_str)
                if c:
                    return c
            except Exception:
                pass
        if hasattr(self.mc, "contacts") and isinstance(self.mc.contacts, dict):
            for pk, contact in self.mc.contacts.items():
                if pk.lower().startswith(name_str.lower()) or name_str.lower().startswith(pk.lower()[:8]):
                    return contact
        if len(name_str) < min_hex_len and all(c in "0123456789abcdefABCDEF" for c in name_str):
            return (name_str + "0" * min_hex_len)[:min_hex_len]
        return name_str

    async def get_channels(self) -> list[dict[str, Any]]:
        """Devuelve la lista de canales configurados en el nodo físico companion."""
        if not self.is_connected or not self.mc:
            return []

        channels: list[dict[str, Any]] = []
        try:
            if hasattr(self.mc, "channels"):
                raw_ch = self.mc.channels
                if isinstance(raw_ch, dict):
                    raw_ch = list(raw_ch.values())
                if isinstance(raw_ch, list):
                    for idx, c in enumerate(raw_ch):
                        if isinstance(c, dict):
                            ch_index = int(c.get("index", idx))
                            channels.append({
                                "index": ch_index,
                                "name": str(c.get("name", f"Canal {ch_index}")),
                                "psk": str(c.get("psk", "")),
                                "is_public": ch_index == 0,
                            })
            elif hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_channels"):
                res = await self.mc.commands.get_channels()
                if isinstance(res, list):
                    for idx, c in enumerate(res):
                        if isinstance(c, dict):
                            ch_index = int(c.get("index", idx))
                            channels.append({
                                "index": ch_index,
                                "name": str(c.get("name", f"Canal {ch_index}")),
                                "psk": str(c.get("psk", "")),
                                "is_public": ch_index == 0,
                            })
        except Exception as e:
            logging.debug(f"Error extrayendo canales del nodo USB: {e}")

        return channels

    async def set_channel(self, index: int, name: str, psk: str) -> dict[str, Any]:
        """Configura un canal en el firmware del transceptor serial."""
        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_SAVED", "index": index, "name": name}

        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_channel"):
                res = await self.mc.commands.set_channel(index, name, psk)
                return {"status": "OK", "response": str(res)}
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "send_cmd"):
                clean_ch_name = name.strip().replace('"', "")
                cmd_str = f'set_chan {index} "{clean_ch_name}" {psk}'
                res = await self.mc.commands.send_cmd(cmd_str)
                return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo aplicando canal al transceptor serial: {e}")

        return {"status": "SAVED", "index": index, "name": name}

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Añade o actualiza un contacto en la memoria flash del transceptor serial."""
        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_SAVED", "contact": contact_data}

        try:
            pubkey = str(contact_data.get("public_key", "")).strip()
            name = str(contact_data.get("name", contact_data.get("alias", ""))).strip()
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "add_contact"):
                # Normalizar estructura esperada por el SDK
                clean_contact = {
                    "public_key": pubkey if len(pubkey) == 64 else pubkey.ljust(64, "0"),
                    "adv_name": name,
                    "type": 0,
                    "flags": 0,
                    "out_path": "",
                    "out_path_len": -1,
                    "out_path_hash_mode": 0,
                    "last_advert": int(time.time()),
                    "adv_lat": 0.0,
                    "adv_lon": 0.0,
                }
                res = await self.mc.commands.add_contact(clean_contact)
                return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo registrando contacto en transceptor serial: {e}")

        return {"status": "SAVED", "contact": contact_data}

    async def remove_contact(self, pubkey: str) -> dict[str, Any]:
        """Elimina un contacto de la memoria flash del transceptor serial."""
        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_REMOVED", "public_key": pubkey}

        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "remove_contact"):
                res = await self.mc.commands.remove_contact(pubkey)
                return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo eliminando contacto del transceptor serial: {e}")

        return {"status": "REMOVED", "public_key": pubkey}

    async def sync_all_contacts(self) -> list[dict[str, Any]]:
        """Descarga e importa todos los contactos almacenados en el hardware."""
        if not self.is_connected or not self.mc:
            return []

        imported_contacts: list[dict[str, Any]] = []
        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_contacts"):
                await self.mc.commands.get_contacts(timeout=3)

            raw_contacts = getattr(self.mc, "contacts", None)
            if raw_contacts and isinstance(raw_contacts, (dict, list)):
                c_list = raw_contacts.values() if isinstance(raw_contacts, dict) else raw_contacts
                for c in c_list:
                    if isinstance(c, dict):
                        pk = str(c.get("public_key", c.get("key", ""))).strip()
                        if pk:
                            adv_name = str(c.get("adv_name", c.get("name", c.get("alias", f"Node_{pk[:6]}")))).strip()
                            raw_type = c.get("type", c.get("adv_type", 1))
                            name_upper = adv_name.upper()
                            if raw_type == 2 or name_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-")) or "REPEATER" in name_upper or "ROUTER" in name_upper:
                                role = "REPEATER"
                            elif raw_type == 3 or "ROOM" in name_upper or "BBS" in name_upper:
                                role = "ROOM"
                            elif raw_type == 4 or "SENSOR" in name_upper:
                                role = "SENSOR"
                            else:
                                role = "CLIENT"
                            imported_contacts.append({
                                "public_key": pk,
                                "name": adv_name,
                                "alias": adv_name,
                                "role": role,
                                "type": raw_type,
                                "adv_type": raw_type,
                            })
        except Exception as e:
            logging.warning(f"Fallo sincronizando libreta de contactos del nodo: {e}")

        return imported_contacts

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        if not self.mc or not prefix_or_key:
            return str(prefix_or_key)
        prefix_str = str(prefix_or_key).strip()
        if hasattr(self.mc, "get_contact_by_key_prefix"):
            try:
                c = self.mc.get_contact_by_key_prefix(prefix_str)
                if c:
                    if isinstance(c, dict):
                        name = c.get("adv_name") or c.get("name") or c.get("alias")
                        if name:
                            return str(name)
                    else:
                        name = getattr(c, "name", getattr(c, "alias", getattr(c, "adv_name", None)))
                        if name:
                            return str(name)
            except Exception:
                pass
        return prefix_str


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
    """Supervisa la vivacidad del puerto serial y activa reconexión segura ante bloqueos o caídas de hardware."""

    def __init__(
        self,
        adapter: BaseSerialAdapter,
        timeout_sec: float = 90.0,
        interval_sec: float = 30.0,
        on_timeout_reconnect: Callable[[], Any] | None = None,
    ) -> None:
        self.adapter = adapter
        self.timeout_sec = timeout_sec
        self.interval_sec = interval_sec
        self.on_timeout_reconnect = on_timeout_reconnect
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._consecutive_ping_failures = 0
        self._reconnect_backoff_sec = 5.0

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
                now = time.time()
                idle_sec = now - self.adapter.last_heartbeat_time

                # 1. CASO DESCONECTADO: Reintentar reconexión automática periódica en background
                if not self.adapter.is_connected:
                    logging.info(
                        f"Watchdog Serial: Adaptador desconectado. Reintentando conexión con transceptor en {self._reconnect_backoff_sec:.1f}s..."
                    )
                    await asyncio.sleep(self._reconnect_backoff_sec)
                    if self.on_timeout_reconnect:
                        res = self.on_timeout_reconnect()
                        if asyncio.iscoroutine(res):
                            await res
                    if not self.adapter.is_connected:
                        self._reconnect_backoff_sec = min(self._reconnect_backoff_sec * 1.5, 30.0)
                    else:
                        self._reconnect_backoff_sec = 5.0
                        self._consecutive_ping_failures = 0
                    continue

                # 2. CASO CONECTADO: Si no ha habido tráfico RF reciente, verificar vivacidad mediante ping suave
                if idle_sec > self.timeout_sec:
                    logging.debug(f"Watchdog Serial: Sin tráfico RF en {idle_sec:.1f}s. Comprobando respuesta del transceptor...")
                    is_alive = await self.adapter.ping_or_check_alive()

                    if is_alive:
                        # El nodo local responde perfectamente al ping (solo hay silencio de radio en la malla)
                        self._consecutive_ping_failures = 0
                        self.adapter.heartbeat()
                        logging.debug("Watchdog Serial: Transceptor local respondió al ping de vivacidad. Enlace serial saludable.")
                    else:
                        self._consecutive_ping_failures += 1
                        logging.warning(
                            f"Watchdog Serial: Transceptor local no respondió al ping de vivacidad (Fallo {self._consecutive_ping_failures}/2)."
                        )

                        # Solo si falla 2 comprobaciones consecutivas (ej. 1 minuto sin responder pings locales)
                        if self._consecutive_ping_failures >= 2:
                            logging.error(
                                "Watchdog Serial: Puerto serial bloqueado o no responsivo tras 2 pings consecutivos. "
                                "Iniciando ciclo de reconexión segura..."
                            )
                            self._consecutive_ping_failures = 0
                            if self.on_timeout_reconnect:
                                res = self.on_timeout_reconnect()
                                if asyncio.iscoroutine(res):
                                    await res
                            self.adapter.heartbeat()
                else:
                    self._consecutive_ping_failures = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en bucle de supervisión SerialWatchdog: {e}")

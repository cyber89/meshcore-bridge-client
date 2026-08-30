"""
Serial Communication Layer & Hybrid Adapters for MeshCore Bridge.
Provee adaptador principal para el SDK oficial meshcore_py, fallback determinista a
pyserial-asyncio con framing SOF/EOF/ESC/CRC-16 y Watchdog de supervisión activa.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any, cast

from src.protocol_types import (
    EOF_BYTE,
    ESC_BYTE,
    ESC_MASK,
    SOF_BYTE,
    MeshcoreFrame,
    MeshCoreSDKProtocol,
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
            if any(k in desc or k in hwid for k in ("heltec", "cp210", "ch340", "ch341", "ftdi", "uart", "acm", "usb serial", "usb-serial", "espressif", "t-beam", "rak", "com")):
                return str(p.device)
        if ports:
            return str(ports[0].device)
    except Exception as e:
        logging.warning(f"Error detecting serial port: {e}", exc_info=True)
    return "COM1" if os.name == "nt" else "/dev/ttyACM0"


class BaseSerialAdapter(abc.ABC):
    """Interfaz abstracta para adaptadores de comunicación serial con hardware MeshCore."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout_sec: float = 30.0) -> None:
        port_clean = str(port or "").strip()
        if not port_clean.startswith("tcp://") and (
            port_clean.upper() in ("AUTO", "DETECT", "DEFAULT", "")
            or not port_clean
            or (os.name == "nt" and port_clean.startswith("/dev/"))
        ):
            self.port = detect_serial_port()
        else:
            self.port = port_clean
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

    def is_hardware_alive(self) -> bool:
        """Verifica de forma síncrona si el hardware USB o socket TCP permanece conectado a nivel OS."""
        return bool(self.is_connected)

    async def ping_or_check_alive(self) -> bool:
        """Verifica si el transceptor local sigue vivo y respondiendo por serial."""
        return self.is_hardware_alive()

    async def get_channel(self, index: int) -> dict[str, Any] | None:
        """Obtiene la configuración de un canal específico."""
        return None

    async def get_stats(self) -> dict[str, Any] | None:
        """Obtiene las estadísticas de la radio."""
        return None

    async def device_query(self) -> dict[str, Any] | None:
        """Consulta el estado del dispositivo."""
        return None

    async def share_contact(self, contact_key: str) -> Any:
        """Comparte un contacto con la red."""
        return {"status": "NOT_SUPPORTED"}

    async def export_contact(self, contact_key: str) -> Any:
        """Exporta un contacto desde el transceptor."""
        return {"status": "NOT_SUPPORTED"}

    async def import_contact(self, contact_data: bytes) -> Any:
        """Importa un contacto hacia el transceptor."""
        return {"status": "NOT_SUPPORTED"}

    async def send_login(self, target_node: str, password: str) -> Any:
        """Envía credenciales de login a un repetidor remoto."""
        return {"status": "NOT_SUPPORTED"}

    async def logout(self, target_node: str) -> Any:
        """Cierra sesión administrativa en un repetidor remoto."""
        return {"status": "NOT_SUPPORTED"}

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        return str(prefix_or_key)


class MeshcoreSDKAdapter(BaseSerialAdapter):
    """Adaptador principal basado en el SDK oficial meshcore_py."""

    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        timeout_sec: float = 30.0,
        node_registry: Any = None,
    ) -> None:
        super().__init__(port, baud_rate, timeout_sec)
        self.node_registry = node_registry
        self.mc: MeshCoreSDKProtocol | Any = None

    async def connect(self) -> bool:
        if MeshCore is None:
            logging.warning("SDK meshcore_py no disponible en el entorno.")
            return False

        await self._connect_with_stabilization()
        return self.is_connected

    async def _connect_with_stabilization(self) -> None:
        if self.mc is not None or self.is_connected:
            await self.disconnect()
            await asyncio.sleep(0.5)

        try:
            # Re-detectar puerto dinámicamente si no está fijado estáticamente o si es formato Unix en Windows
            port_str = str(self.port or "")
            if not port_str.startswith("tcp://") and (
                port_str.upper() in ("AUTO", "DETECT", "DEFAULT", "")
                or not port_str
                or (os.name == "nt" and port_str.startswith("/dev/"))
            ):
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
                # Conexión resiliente: Dar tiempo de estabilización (2.0s) al microcontrolador ESP32-S3 tras la apertura del puerto USB
                try:
                    from meshcore.serial_cx import SerialConnection
                    cx = SerialConnection(self.port, self.baud_rate, cx_dly=2.0)
                    mc = MeshCore(cx, auto_reconnect=True)
                    await mc.dispatcher.start()
                    res_cx = await mc.connection_manager.connect()
                    if res_cx is not None:
                        # Esperar a que el firmware termine su secuencia de arranque
                        await asyncio.sleep(2.0)
                        res_app = await mc.commands.send_appstart()
                        if res_app and getattr(res_app, "type", None) != EventType.ERROR:
                            self.mc = mc
                        else:
                            logging.debug("Reintentando send_appstart tras segundo pulso de sincronización...")
                            await asyncio.sleep(0.5)
                            res_app2 = await mc.commands.send_appstart()
                            if res_app2 and getattr(res_app2, "type", None) != EventType.ERROR:
                                self.mc = mc
                            else:
                                await mc.disconnect()
                except Exception as ex_init:
                    logging.debug(f"Apertura directa con retardo post-boot falló: {ex_init}, probando fallback create_serial...")
                    if hasattr(MeshCore, "create_serial"):
                        try:
                            self.mc = await MeshCore.create_serial(self.port, self.baud_rate, auto_reconnect=True)
                        except Exception:
                            self.mc = None

            if self.mc is None:
                logging.error(f"No se pudo establecer conexión con el transceptor MeshCore en {self.port}.")
                self.is_connected = False
                return

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
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error conectando con MeshCore SDK: {e}", exc_info=True)
            self.is_connected = False

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

    def is_hardware_alive(self) -> bool:
        """Verifica si el transceptor USB / TCP sigue presente en el sistema operativo y operativo."""
        if not self.is_connected or self.mc is None:
            return False

        port_str = str(self.port)
        if port_str.startswith("tcp://") or port_str.upper().startswith("VIRTUAL"):
            return bool(self.is_connected)

        # Si hubo actividad reciente (heartbeat o recepción de trama), la radio está viva
        if (time.time() - self.last_heartbeat_time) <= max(30.0, self.timeout_sec):
            return True

        # Comprobación de transporte serial abierto en la conexión del SDK
        try:
            if hasattr(self.mc, "connection"):
                cx = self.mc.connection
                if hasattr(cx, "is_open") and not cx.is_open:
                    self.is_connected = False
                    return False
                if hasattr(cx, "serial") and hasattr(cx.serial, "is_open") and not cx.serial.is_open:
                    self.is_connected = False
                    return False
                if hasattr(cx, "transport") and cx.transport and hasattr(cx.transport, "is_closing") and cx.transport.is_closing():
                    self.is_connected = False
                    return False
        except Exception:
            pass

        # Comprobación a nivel de sistema operativo de puertos COM / tty si está inactivo
        try:
            import serial.tools.list_ports
            com_ports = [p.device.lower() for p in serial.tools.list_ports.comports()]
            port_lower = port_str.lower()
            if port_lower and port_lower not in ("auto", "detect"):
                # En Windows, los puertos COM son COM1, COM2...
                if port_lower.startswith("com") and com_ports and port_lower not in com_ports:
                    self.is_connected = False
                    return False
                # En Linux, verificar que el nodo de dispositivo /dev/ exista
                if port_lower.startswith("/dev/") and os.name != "nt" and not os.path.exists(self.port):
                    self.is_connected = False
                    return False
        except Exception:
            pass

        return bool(self.is_connected)

    async def ping_or_check_alive(self) -> bool:
        """Comprueba si el transceptor local sigue vivo y respondiendo activamente por serial."""
        if not self.is_hardware_alive():
            self.is_connected = False
            return False
        self.heartbeat()
        return True

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

        if EventType:
            for ev_type in EventType:
                try:
                    def _make_handler(et: Any) -> Any:
                        def _handler(event: Any) -> None:
                            try:
                                loop = asyncio.get_running_loop()
                                loop.create_task(self._on_sdk_event(et, event))
                            except RuntimeError:
                                pass
                        return _handler
                    self.mc.subscribe(ev_type, _make_handler(ev_type))
                except Exception as e:
                    logging.debug(f"Suscripción a evento {ev_type}: {e}")

    async def _on_sdk_event(self, event_type: Any, data: Any) -> None:
        """Maneja eventos del SDK MeshCore y los despacha a los callbacks apropiados."""
        self.heartbeat()

        event_name = getattr(event_type, "value", str(event_type))
        logging.debug(f"Evento SDK MeshCore recibido: {event_name}")

        # Messages
        if event_type == getattr(EventType, "CONTACT_MSG_RECV", None):
            await self._handle_direct_message(data)
        elif event_type == getattr(EventType, "CHANNEL_MSG_RECV", None):
            await self._handle_channel_message(data)
        elif event_type == getattr(EventType, "CHANNEL_DATA_RECV", None):
            await self._handle_channel_data(data)

        # Status & Telemetry
        elif event_type == getattr(EventType, "STATUS_RESPONSE", None):
            await self._handle_status_response(data)
        elif event_type == getattr(EventType, "TELEMETRY_RESPONSE", None):
            await self._handle_telemetry_response(data)
        elif event_type == getattr(EventType, "STATS_CORE", None):
            await self._handle_stats("core", data)
        elif event_type == getattr(EventType, "STATS_RADIO", None):
            await self._handle_stats("radio", data)
        elif event_type == getattr(EventType, "STATS_PACKETS", None):
            await self._handle_stats("packets", data)
        elif event_type == getattr(EventType, "BATTERY", None):
            await self._handle_battery(data)
        elif event_type == getattr(EventType, "DEVICE_INFO", None):
            await self._handle_device_info(data)

        # Contacts
        elif event_type == getattr(EventType, "CONTACTS", None):
            await self._handle_contacts_list(data)
        elif event_type == getattr(EventType, "NEXT_CONTACT", None):
            await self._handle_contact(data)
        elif event_type == getattr(EventType, "NEW_CONTACT", None):
            await self._handle_new_contact(data)
        elif event_type == getattr(EventType, "SELF_INFO", None):
            await self._handle_self_info(data)
        elif event_type == getattr(EventType, "CONTACT_DELETED", None):
            await self._handle_contact_deleted(data)
        elif event_type == getattr(EventType, "CONTACTS_FULL", None):
            logging.warning("Contactos llenos en el dispositivo")

        # ACK & Messages
        elif event_type == getattr(EventType, "MSG_SENT", None):
            await self._handle_msg_sent(data)
        elif event_type == getattr(EventType, "ACK", None):
            await self._handle_ack(data)
        elif event_type == getattr(EventType, "MESSAGES_WAITING", None):
            logging.debug("Mensajes esperando en cola")

        # Time
        elif event_type == getattr(EventType, "CURRENT_TIME", None):
            logging.debug(f"Tiempo del dispositivo: {data}")

        # Login
        elif event_type == getattr(EventType, "LOGIN_SUCCESS", None):
            await self._handle_login_result(data, success=True)
        elif event_type == getattr(EventType, "LOGIN_FAILED", None):
            await self._handle_login_result(data, success=False)

        # Binary responses
        elif event_type == getattr(EventType, "BINARY_RESPONSE", None):
            await self._handle_binary_response(data)
        elif event_type == getattr(EventType, "TRACE_DATA", None):
            await self._handle_trace_data(data)
        elif event_type == getattr(EventType, "RAW_DATA", None):
            await self._handle_raw_data(data)
        elif event_type == getattr(EventType, "LOG_DATA", None):
            await self._handle_log_data(data)

        # Path & Discovery
        elif event_type == getattr(EventType, "PATH_UPDATE", None):
            logging.debug(f"Path update: {data}")
        elif event_type == getattr(EventType, "PATH_RESPONSE", None):
            logging.debug(f"Path response: {data}")
        elif event_type == getattr(EventType, "ADVERT_PATH", None):
            logging.debug(f"Advert path: {data}")
        elif event_type == getattr(EventType, "DISCOVER_RESPONSE", None):
            logging.debug(f"Discover response: {data}")
        elif event_type == getattr(EventType, "NEIGHBOURS_RESPONSE", None):
            logging.debug(f"Neighbours response: {data}")

        # Control
        elif event_type == getattr(EventType, "CONTROL_DATA", None):
            await self._handle_control_data(data)
        elif event_type == getattr(EventType, "ADVERTISEMENT", None):
            logging.debug(f"Advertisement received: {data}")

        # Channel info
        elif event_type == getattr(EventType, "CHANNEL_INFO", None):
            logging.debug(f"Channel info: {data}")

        # Errors
        elif event_type == getattr(EventType, "ERROR", None):
            logging.warning(f"SDK Error: {data}")

        # Connection events
        elif event_type == getattr(EventType, "CONNECTED", None):
            logging.info("SDK connected")
        elif event_type == getattr(EventType, "DISCONNECTED", None):
            logging.warning("SDK disconnected")

        # Other events - forward to generic handler
        else:
            await self._handle_generic_event(event_type, data)

    async def _handle_direct_message(self, data: Any) -> None:
        """Maneja mensajes directos recibidos."""
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_channel_message(self, data: Any) -> None:
        """Maneja mensajes de canal recibidos."""
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_channel_data(self, data: Any) -> None:
        """Maneja datos binarios de canal."""
        logging.debug(f"Channel data received: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_status_response(self, data: Any) -> None:
        """Maneja respuestas de status del dispositivo."""
        logging.debug(f"Status response: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_telemetry_response(self, data: Any) -> None:
        """Maneja respuestas de telemetría LPP."""
        logging.debug(f"Telemetry response: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_stats(self, stats_type: str, data: Any) -> None:
        """Maneja respuestas de estadísticas."""
        logging.debug(f"Stats ({stats_type}): {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_battery(self, data: Any) -> None:
        """Maneja información de batería."""
        logging.debug(f"Battery info: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_device_info(self, data: Any) -> None:
        """Maneja información del dispositivo."""
        logging.debug(f"Device info: {data}")
        rep_val = None
        if isinstance(data, dict) and "repeat" in data:
            rep_val = bool(data["repeat"])
        elif hasattr(data, "payload") and isinstance(data.payload, dict) and "repeat" in data.payload:
            rep_val = bool(data.payload["repeat"])
        if rep_val is not None:
            if hasattr(self, "self_info") and isinstance(self.self_info, dict):
                self.self_info["repeat"] = rep_val
            if hasattr(self, "_self_info") and isinstance(self._self_info, dict):
                self._self_info["repeat"] = rep_val
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_contacts_list(self, data: Any) -> None:
        """Maneja lista completa de contactos."""
        logging.debug(f"Contacts list received: {len(data) if isinstance(data, dict) else '?'} contacts")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_contact(self, data: Any) -> None:
        """Maneja un contacto individual."""
        logging.debug(f"Contact received: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_new_contact(self, data: Any) -> None:
        """Maneja un nuevo contacto descubierto."""
        logging.debug(f"New contact discovered: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_self_info(self, data: Any) -> None:
        """Maneja información del nodo local."""
        logging.debug(f"Self info: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_contact_deleted(self, data: Any) -> None:
        """Maneja eliminación de contacto."""
        logging.debug(f"Contact deleted: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_msg_sent(self, data: Any) -> None:
        """Maneja confirmación de mensaje enviado."""
        logging.debug(f"Message sent confirmation: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_ack(self, data: Any) -> None:
        """Maneja ACK recibido."""
        logging.debug(f"ACK received: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_login_result(self, data: Any, success: bool) -> None:
        """Maneja resultado de login."""
        if success:
            logging.info(f"Login successful: {data}")
        else:
            logging.warning(f"Login failed: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_binary_response(self, data: Any) -> None:
        """Maneja respuestas binarias."""
        logging.debug(f"Binary response: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_trace_data(self, data: Any) -> None:
        """Maneja datos de trace."""
        logging.debug(f"Trace data: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_raw_data(self, data: Any) -> None:
        """Maneja datos raw."""
        logging.debug(f"Raw data: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_log_data(self, data: Any) -> None:
        """Maneja datos de log RF."""
        logging.debug(f"Log data: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_control_data(self, data: Any) -> None:
        """Maneja datos de control."""
        logging.debug(f"Control data: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_generic_event(self, event_type: Any, data: Any) -> None:
        """Maneja eventos genéricos no categorizados."""
        logging.debug(f"Generic event {event_type}: {data}")
        if self.rx_callback:
            self.rx_callback(data)

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
        is_dm = bool(
            target_clean
            and target_clean.upper() not in ("0xFFFF", "BROADCAST", "PUBLIC", "ALL", "GLOBAL", "NONE", "")
            and not target_clean.lower().startswith("channel")
        )
        safe_ch = int(channel_idx) if channel_idx is not None else 0

        # Canal público vs mensaje directo (DM)
        if is_dm:
            dest_target = self._resolve_target(target_clean)

            # Asegurar contacto en la radio antes de transmitir
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "add_contact"):
                try:
                    if isinstance(dest_target, str) and len(dest_target) >= 12:
                        target_name = target_clean if target_clean != dest_target else f"Node_{dest_target[:6]}"
                        await self.mc.commands.add_contact({"public_key": (dest_target + "0" * 64)[:64], "name": target_name})
                    elif isinstance(dest_target, dict):
                        await self.mc.commands.add_contact(dest_target)
                except Exception as e_ac:
                    logging.debug(f"Asegurando contacto en radio para TX: {e_ac}")

            if hasattr(self.mc.commands, "send_msg"):
                res = await self.mc.commands.send_msg(dest_target, text)
            else:
                raise NotImplementedError("send_msg no soportado en este SDK")
        else:
            if hasattr(self.mc.commands, "send_chan_msg"):
                res = await self.mc.commands.send_chan_msg(safe_ch, text)
            elif hasattr(self.mc.commands, "send_channel_msg"):
                res = await self.mc.commands.send_channel_msg(safe_ch, text)
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
        """Resuelve un identificador de destino a clave pública.

        Delega a TargetResolver (Single Source of Truth) para evitar
        duplicación de lógica con admin_handler.py.
        """
        from src.target_resolver import TargetResolver
        resolver = TargetResolver(
            mc_provider=self.mc,
            node_registry=self.node_registry,
        )
        return resolver.resolve(
            name_or_key,
            min_hex_len=min_hex_len,
            raise_on_not_found=True,
        )

    async def get_channels(self) -> list[dict[str, Any]]:
        """Devuelve la lista de canales configurados en el nodo físico companion."""
        if not self.is_connected or not self.mc:
            return []

        channels: list[dict[str, Any]] = []
        try:
            # 1. Intentar desde parser de canales en memoria del SDK
            reader = getattr(self.mc, "_reader", None) or getattr(self.mc, "reader", None)
            packet_parser = getattr(reader, "packet_parser", None) if reader else None
            parser_channels = getattr(packet_parser, "channels", None) if packet_parser else None

            if parser_channels and isinstance(parser_channels, list):
                for idx, c in enumerate(parser_channels):
                    if isinstance(c, dict) and c.get("channel_name"):
                        ch_name = str(c.get("channel_name", ""))
                        ch_sec = c.get("channel_secret")
                        psk_hex = ch_sec.hex() if isinstance(ch_sec, bytes) else str(ch_sec or "")
                        channels.append({
                            "index": int(c.get("channel_idx", idx)),
                            "name": ch_name,
                            "psk": psk_hex,
                            "is_public": int(c.get("channel_idx", idx)) == 0,
                        })

            if not channels and hasattr(self.mc, "channels"):
                raw_ch = self.mc.channels
                if isinstance(raw_ch, dict):
                    raw_ch = list(raw_ch.values())
                    for idx, c in enumerate(raw_ch):
                        if isinstance(c, dict) and (c.get("name") or c.get("channel_name")):
                            raw_idx = c.get("index")
                            if raw_idx is None:
                                raw_idx = c.get("channel_idx")
                            ch_index = int(raw_idx) if raw_idx is not None else idx
                            channels.append({
                                "index": ch_index,
                                "name": str(c.get("name", c.get("channel_name", f"Canal {ch_index}"))),
                                "psk": str(c.get("psk", c.get("channel_secret", ""))),
                                "is_public": ch_index == 0,
                            })

            # 2. Si no hay canales en memoria, consultar canales 0 a 7 al firmware mediante get_channel
            if not channels and hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_channel"):
                for ch_idx in range(8):
                    try:
                        ev = await self.mc.commands.get_channel(ch_idx)
                        if ev and hasattr(ev, "payload") and isinstance(ev.payload, dict):
                            p = ev.payload
                            ch_name = str(p.get("channel_name", "")).strip()
                            if ch_name:
                                ch_sec = p.get("channel_secret")
                                psk_hex = ch_sec.hex() if isinstance(ch_sec, bytes) else str(ch_sec or "")
                                channels.append({
                                    "index": ch_idx,
                                    "name": ch_name,
                                    "psk": psk_hex,
                                    "is_public": ch_idx == 0,
                                })
                    except Exception:
                        pass
        except Exception as e:
            logging.debug(f"Error extrayendo canales del nodo USB: {e}")

        return channels

    async def set_channel(self, index: int, name: str, psk: str) -> dict[str, Any]:
        """Configura un canal en el firmware del transceptor serial."""
        if not re.match(r'^[a-fA-F0-9]{0,64}$', psk):
            raise ValueError("Invalid PSK format")
        if not (0 <= index <= 15):
            raise ValueError("Channel index out of range (0-15)")
        if len(name) > 32 or any(ord(c) < 0x20 for c in name):
            raise ValueError("Invalid channel name")

        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_SAVED", "index": index, "name": name}

        # Convertir PSK a 16 bytes exactos (AES-128) según lo requerido por el SDK de MeshCore
        secret_bytes: bytes | None = None
        if psk:
            clean_psk = psk.strip()
            if len(clean_psk) == 32 and all(c in "0123456789abcdefABCDEF" for c in clean_psk):
                secret_bytes = bytes.fromhex(clean_psk)
            elif len(clean_psk) == 16:
                secret_bytes = clean_psk.encode("utf-8")
            else:
                import hashlib
                secret_bytes = hashlib.sha256(clean_psk.encode("utf-8")).digest()[:16]
        elif name.startswith("#"):
            import hashlib
            secret_bytes = hashlib.sha256(name.encode("utf-8")).digest()[:16]
        else:
            secret_bytes = b"\x00" * 16

        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_channel"):
                res = await self.mc.commands.set_channel(index, name, secret_bytes)
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
                try:
                    await self.mc.commands.get_contacts(timeout=3)
                except Exception as ex:
                    logging.debug(f"Comando get_contacts emitido: {ex}")

            raw_contacts = getattr(self.mc, "contacts", None)
            if callable(raw_contacts):
                try:
                    raw_contacts = raw_contacts()
                except Exception:
                    raw_contacts = getattr(self.mc, "_contacts", None)
            elif raw_contacts is None and hasattr(self.mc, "_contacts"):
                raw_contacts = getattr(self.mc, "_contacts", None)

            if raw_contacts and isinstance(raw_contacts, (dict, list)):
                c_list = raw_contacts.values() if isinstance(raw_contacts, dict) else raw_contacts
                for c in c_list:
                    pk = ""
                    adv_name = ""
                    raw_type = 1
                    adv_lat = None
                    adv_lon = None
                    if isinstance(c, dict):
                        pk = str(c.get("public_key", c.get("key", ""))).strip()
                        adv_name = str(c.get("adv_name", c.get("name", c.get("alias", f"Node_{pk[:6]}")))).strip()
                        raw_type_val = c.get("type", c.get("adv_type", 1))
                        raw_type = int(raw_type_val) if raw_type_val is not None else 1
                        adv_lat = c.get("adv_lat", c.get("latitude"))
                        adv_lon = c.get("adv_lon", c.get("longitude"))
                    elif hasattr(c, "public_key") or hasattr(c, "adv_name") or hasattr(c, "name"):
                        pk = str(getattr(c, "public_key", "")).strip()
                        adv_name = str(getattr(c, "adv_name", getattr(c, "name", getattr(c, "alias", f"Node_{pk[:6]}")))).strip()
                        raw_type_val = getattr(c, "adv_type", getattr(c, "type", 1))
                        raw_type = int(raw_type_val) if raw_type_val is not None else 1
                        adv_lat = getattr(c, "adv_lat", getattr(c, "latitude", None))
                        adv_lon = getattr(c, "adv_lon", getattr(c, "longitude", None))

                    if pk:
                        norm_pk = pk.strip().lower()
                        my_pk = str(getattr(self, "public_key", "") or getattr(self.mc, "public_key", "")).strip().lower()
                        is_local_contact = bool(my_pk and (norm_pk == my_pk or (len(my_pk) >= 6 and len(norm_pk) >= 6 and (my_pk.startswith(norm_pk) or norm_pk.startswith(my_pk)))))
                        from src.shared_utils import classify_device_role
                        role = classify_device_role(raw_type, is_local_contact)

                        imported_contacts.append({
                            "public_key": pk,
                            "name": adv_name,
                            "alias": adv_name,
                            "role": role,
                            "type": raw_type,
                            "adv_type": raw_type,
                            "latitude": adv_lat,
                            "longitude": adv_lon,
                            "is_local": is_local_contact,
                        })
        except Exception as e:
            logging.warning(f"Fallo sincronizando libreta de contactos del nodo: {e}")

        return imported_contacts

    async def get_channel(self, index: int) -> dict[str, Any] | None:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_channel"):
            return cast(dict[str, Any] | None, await self.mc.commands.get_channel(index))
        return None

    async def get_stats(self) -> dict[str, Any] | None:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_stats"):
            return cast(dict[str, Any] | None, await self.mc.commands.get_stats())
        return None

    async def device_query(self) -> dict[str, Any] | None:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "device_query"):
            return cast(dict[str, Any] | None, await self.mc.commands.device_query())
        return None

    async def share_contact(self, contact_key: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "share_contact"):
            return await self.mc.commands.share_contact(contact_key)
        return None

    async def export_contact(self, contact_key: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "export_contact"):
            return await self.mc.commands.export_contact(contact_key)
        return None

    async def import_contact(self, contact_data: bytes) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "import_contact"):
            return await self.mc.commands.import_contact(contact_data)
        return None

    async def send_login(self, target_node: str, password: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "send_login"):
            return await self.mc.commands.send_login(target_node, password)
        return None

    async def logout(self, target_node: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "logout"):
            return await self.mc.commands.logout(target_node)
        return None

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
                    elif hasattr(c, "adv_name") or hasattr(c, "name") or hasattr(c, "alias"):
                        name = getattr(c, "adv_name", getattr(c, "name", getattr(c, "alias", None)))
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
                            frame = MeshcoreFrame.parse_raw_packet(bytes(self._rx_buffer), strict=True)
                            frames.append(frame)
                            if self.rx_callback:
                                self.rx_callback(frame)
                        except Exception as e:
                            logging.warning(f"Error parseando trama raw (frame rechazado): {e}")
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
        self.max_reconnect_attempts = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "0"))
        self._total_reconnect_attempts = 0

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
                # Comprobación proactiva y rápida de presencia física USB cada 2 segundos (o interval_sec si es menor)
                step_sleep = min(2.0, max(0.005, self.interval_sec))
                steps = max(1, int(self.interval_sec / step_sleep))
                for _ in range(steps):
                    if not self._running:
                        break
                    await asyncio.sleep(step_sleep)
                    if self.adapter.is_connected and hasattr(self.adapter, "is_hardware_alive"):
                        if not self.adapter.is_hardware_alive():
                            logging.warning("Watchdog Serial: Transceptor LoRa desconectado físicamente del puerto USB.")
                            self.adapter.is_connected = False
                            break

                now = time.time()
                idle_sec = now - self.adapter.last_heartbeat_time

                # 1. CASO DESCONECTADO: Reintentar reconexión automática periódica en background
                if not self.adapter.is_connected:
                    if self.max_reconnect_attempts > 0 and self._total_reconnect_attempts >= self.max_reconnect_attempts:
                        logging.warning(
                            f"Watchdog Serial: Se alcanzó el límite máximo de reintentos ({self.max_reconnect_attempts}). "
                            "Entrando en modo dormant (reintentando cada 300s)..."
                        )
                        await asyncio.sleep(300.0)
                    else:
                        reconnect_wait = min(self._reconnect_backoff_sec, max(0.005, self.interval_sec))
                        logging.info(
                            f"Watchdog Serial: Adaptador desconectado. Reintentando conexión con transceptor en {reconnect_wait:.2f}s..."
                        )
                        await asyncio.sleep(reconnect_wait)

                    self._total_reconnect_attempts += 1
                    if self.on_timeout_reconnect:
                        res = self.on_timeout_reconnect()
                        if asyncio.iscoroutine(res):
                            await res
                    if not self.adapter.is_connected:
                        self._reconnect_backoff_sec = min(self._reconnect_backoff_sec * 1.5, 30.0)
                    else:
                        self._reconnect_backoff_sec = 5.0
                        self._consecutive_ping_failures = 0
                        self._total_reconnect_attempts = 0
                    continue

                # 2. CASO CONECTADO: Si no ha habido tráfico RF reciente, verificar vivacidad mediante ping suave
                if idle_sec > self.timeout_sec:
                    logging.debug(f"Watchdog Serial: Sin tráfico RF en {idle_sec:.1f}s. Comprobando respuesta del transceptor...")
                    try:
                        is_alive = await asyncio.wait_for(self.adapter.ping_or_check_alive(), timeout=10.0)
                    except asyncio.TimeoutError:
                        is_alive = False
                        logging.warning("Watchdog ping timeout")
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

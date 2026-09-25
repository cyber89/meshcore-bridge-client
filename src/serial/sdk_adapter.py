"""
MeshCore Official SDK Adapter (meshcore_py) for MeshCore Bridge.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any, cast

from src.protocol_types import MeshCoreSDKProtocol
from src.serial.serial_base import BaseSerialAdapter, detect_serial_port
from src.target_resolver import TargetResolver

try:
    import meshcore
    from meshcore import EventType, MeshCore
    from meshcore.events import Event
except ImportError:
    meshcore = None
    MeshCore = None
    EventType = None
    Event = None

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
        self._initial_sync_task: asyncio.Task[None] | None = None
        self._self_info: dict[str, Any] | None = None
        self._sdk_dispatch_cache: dict[Any, Callable[[Any], Any]] | None = None

    @property
    def self_info(self) -> Any:
        """Información del nodo local obtenida del SDK."""
        if self._self_info is not None:
            return self._self_info
        return getattr(self.mc, "self_info", None) if self.mc else None

    @self_info.setter
    def self_info(self, value: Any) -> None:
        self._self_info = value

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
                # Solución definitiva: inyectamos el sleep de boot DENTRO del SerialConnection.connect()
                # mediante una subclase que añade la espera tras la apertura del puerto USB-CDC.
                # Así mc.connect() gestiona correctamente dispatcher, suscriptores y timeouts internos
                # sin conflictos con asyncio.wait_for externos.
                _BOOT_WAIT_SEC = 5.0    # espera post-apertura para boot del ESP32-S3 (reset vía DTR/RTS)
                _MC_TOTAL_TIMEOUT = 35.0  # timeout total = boot(5s) + SDK default_timeout(15s) + margen

                class _BootWaitSerialConnection:
                    """Wrapper de SerialConnection que añade espera de boot tras apertura del puerto."""
                    def __init__(self, inner: Any, boot_wait: float) -> None:
                        self._inner = inner
                        self._boot_wait = boot_wait
                        # Exponer todos los atributos del inner para que MeshCore funcione normalmente
                        self.transport = inner.transport
                        self.reader = inner.reader
                        self._connected_event = inner._connected_event
                        self._disconnect_callback: Any = None
                        self._background_tasks = inner._background_tasks

                    async def connect(self) -> Any:
                        result = await self._inner.connect()
                        if result is not None:
                            logging.debug(
                                f"Puerto {self._inner.port} abierto. "
                                f"Esperando {self._boot_wait}s de boot del ESP32-S3..."
                            )
                            await asyncio.sleep(self._boot_wait)
                        return result

                    async def disconnect(self) -> None:
                        await self._inner.disconnect()

                    async def send(self, data: Any) -> None:
                        # Mantener transport sincronizado (puede cambiar tras connect)
                        self._inner.transport = self._inner.transport
                        await self._inner.send(data)

                    def set_reader(self, reader: Any) -> None:
                        self._inner.set_reader(reader)
                        self.reader = reader

                    def set_disconnect_callback(self, callback: Any) -> None:
                        self._disconnect_callback = callback
                        self._inner.set_disconnect_callback(callback)

                _mc_raw: Any = None
                try:
                    from meshcore.serial_cx import SerialConnection
                    cx_inner = SerialConnection(self.port, self.baud_rate, cx_dly=0.0)
                    cx_wrapped = _BootWaitSerialConnection(cx_inner, _BOOT_WAIT_SEC)
                    _mc_raw = MeshCore(cx_wrapped, auto_reconnect=True)

                    # mc.connect() = dispatcher.start() + connection_manager.connect() + send_appstart()
                    # El wrapper añade el sleep de boot DENTRO de connection_manager.connect()
                    # antes de que mc.connect() llame a send_appstart() — sincronización perfecta.
                    res_app = await asyncio.wait_for(_mc_raw.connect(), timeout=_MC_TOTAL_TIMEOUT)

                    if res_app is not None and getattr(res_app, "type", None) != EventType.ERROR:
                        self.mc = _mc_raw
                        _mc_raw = None  # transferido — NOT cleaned up in finally
                        if hasattr(res_app, "payload") and isinstance(res_app.payload, dict):
                            self.self_info = res_app.payload
                            if hasattr(self.mc, "_self_info"):
                                self.mc._self_info = res_app.payload
                        elif hasattr(self.mc, "self_info") and isinstance(
                            getattr(self.mc, "self_info", None), dict
                        ):
                            self.self_info = self.mc.self_info
                    else:
                        reason = getattr(res_app, "payload", {}).get("reason", "sin respuesta") if res_app else "None"
                        logging.error(
                            f"Transceptor MeshCore en {self.port} no respondió al appstart "
                            f"tras {_BOOT_WAIT_SEC}s de espera de boot (motivo: {reason}). "
                            "Verifica: (1) firmware en Companion mode, "
                            "(2) baud rate 115200, (3) cable USB funcional."
                        )
                except asyncio.TimeoutError:
                    logging.error(
                        f"Timeout global ({_MC_TOTAL_TIMEOUT}s) esperando conexión con el "
                        f"transceptor MeshCore en {self.port}. "
                        "Posible causa: firmware bloqueado, cable USB defectuoso o puerto incorrecto."
                    )
                except ConnectionError as ce:
                    logging.error(f"Error de conexión al transceptor MeshCore en {self.port}: {ce}")
                except Exception as ex_init:
                    logging.error(f"Error inesperado conectando con MeshCore SDK en {self.port}: {ex_init}", exc_info=True)
                finally:
                    # Garantizar limpieza del dispatcher si la conexión no se completó
                    if _mc_raw is not None:
                        try:
                            await asyncio.wait_for(_mc_raw.disconnect(), timeout=1.5)
                        except Exception:
                            pass

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
            if self.self_info and self.rx_callback and Event and EventType:
                try:
                    self.rx_callback(Event(EventType.SELF_INFO, self.self_info))
                except Exception as ex_si:
                    logging.warning(f"Despacho inicial de self_info: {ex_si}")
            logging.info("MeshCore SDK conectado e iniciado exitosamente.")
            self._initial_sync_task = asyncio.create_task(self._initial_hardware_sync())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error conectando con MeshCore SDK: {e}", exc_info=True)
            self.is_connected = False

    async def disconnect(self) -> None:
        if self._initial_sync_task and not self._initial_sync_task.done():
            self._initial_sync_task.cancel()
            try:
                await asyncio.wait_for(self._initial_sync_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            self._initial_sync_task = None

        if self.mc:
            try:
                if hasattr(self.mc, "disconnect"):
                    await asyncio.wait_for(self.mc.disconnect(), timeout=1.5)
                elif hasattr(self.mc, "stop"):
                    self.mc.stop()
                elif hasattr(self.mc, "close"):
                    self.mc.close()
            except asyncio.TimeoutError:
                logging.warning("Timeout (1.5s) al desconectar MeshCore SDK; forzando detención.")
                try:
                    if hasattr(self.mc, "stop"):
                        self.mc.stop()
                except Exception:
                    pass
            except Exception as e:
                logging.warning(f"Error cerrando MeshCore SDK: {e}")
            finally:
                self.mc = None
        self._self_info = None
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

        # Comprobación de transporte serial abierto y estado de conexión en el SDK oficial
        try:
            # 1. Comprobación a nivel de objeto MeshCore principal
            if hasattr(self.mc, "is_connected"):
                is_mc_conn = self.mc.is_connected
                if callable(is_mc_conn):
                    is_mc_conn = is_mc_conn()
                if not is_mc_conn:
                    self.is_connected = False
                    return False

            # 2. Comprobación en connection_manager / cx
            cm = getattr(self.mc, "connection_manager", getattr(self.mc, "cx", None))
            if cm is not None:
                if hasattr(cm, "is_connected") and cm.is_connected is False:
                    self.is_connected = False
                    return False
                conn = getattr(cm, "connection", None)
                if conn is not None:
                    if hasattr(conn, "transport") and conn.transport:
                        is_closing_fn = getattr(conn.transport, "is_closing", None)
                        if callable(is_closing_fn):
                            try:
                                if is_closing_fn() is True:
                                    self.is_connected = False
                                    return False
                            except Exception:
                                pass
                    if hasattr(conn, "is_open") and conn.is_open is False:
                        self.is_connected = False
                        return False
                    if hasattr(conn, "serial") and hasattr(conn.serial, "is_open") and conn.serial.is_open is False:
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
                self.heartbeat()
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

    def _get_sdk_dispatch_map(self) -> dict[Any, Callable[[Any], Any]]:
        """Construye o retorna la tabla de despacho determinista para eventos del SDK."""
        if not hasattr(self, "_sdk_dispatch_cache") or self._sdk_dispatch_cache is None:
            if EventType is None:
                self._sdk_dispatch_cache = {}
            else:
                self._sdk_dispatch_cache = {
                    EventType.CONTACT_MSG_RECV: self._handle_direct_message,
                    EventType.CHANNEL_MSG_RECV: self._handle_channel_message,
                    EventType.CHANNEL_DATA_RECV: self._handle_channel_data,
                    EventType.STATUS_RESPONSE: self._handle_status_response,
                    EventType.TELEMETRY_RESPONSE: self._handle_telemetry_response,
                    EventType.STATS_CORE: lambda d: self._handle_stats("core", d),
                    EventType.STATS_RADIO: lambda d: self._handle_stats("radio", d),
                    EventType.STATS_PACKETS: lambda d: self._handle_stats("packets", d),
                    EventType.BATTERY: self._handle_battery,
                    EventType.DEVICE_INFO: self._handle_device_info,
                    EventType.CONTACTS: self._handle_contacts_list,
                    EventType.NEXT_CONTACT: self._handle_contact,
                    EventType.NEW_CONTACT: self._handle_new_contact,
                    EventType.SELF_INFO: self._handle_self_info,
                    EventType.CONTACT_DELETED: self._handle_contact_deleted,
                    EventType.MSG_SENT: self._handle_msg_sent,
                    EventType.ACK: self._handle_ack,
                    EventType.LOGIN_SUCCESS: lambda d: self._handle_login_result(d, success=True),
                    EventType.LOGIN_FAILED: lambda d: self._handle_login_result(d, success=False),
                    EventType.BINARY_RESPONSE: self._handle_binary_response,
                    EventType.TRACE_DATA: self._handle_trace_data,
                    EventType.RAW_DATA: self._handle_raw_data,
                    EventType.CONTROL_DATA: self._handle_control_data,
                }
                if hasattr(EventType, "LOG_DATA"):
                    self._sdk_dispatch_cache[EventType.LOG_DATA] = self._handle_log_data
                if hasattr(EventType, "RX_LOG_DATA"):
                    self._sdk_dispatch_cache[EventType.RX_LOG_DATA] = self._handle_log_data
        return self._sdk_dispatch_cache

    async def _on_sdk_event(self, event_type: Any, data: Any) -> None:
        """Maneja eventos del SDK MeshCore y los despacha a los callbacks apropiados."""
        self.heartbeat()

        event_name = getattr(event_type, "value", str(event_type))
        if event_name not in ("log_data", "rx_log_data"):
            logging.debug(f"Evento SDK MeshCore recibido: {event_name}")

        dispatch_map = self._get_sdk_dispatch_map()
        handler = dispatch_map.get(event_type)
        if handler is not None:
            res = handler(data)
            if asyncio.iscoroutine(res):
                await res
            return

        if EventType is not None:
            if event_type == getattr(EventType, "ADVERTISEMENT", None):
                pk_hint = ""
                if isinstance(data, dict):
                    pk_hint = str(data.get("public_key", data.get("key", "")))[:12]
                elif hasattr(data, "public_key"):
                    pk_hint = str(data.public_key)[:12]
                logging.info(f"Advertisement recibido: pk={pk_hint or '?'} data={data}")
                if self.rx_callback:
                    self.rx_callback(data)
                return

            if event_type in (
                getattr(EventType, "ADVERT_PATH", None),
                getattr(EventType, "DISCOVER_RESPONSE", None),
                getattr(EventType, "NEIGHBOURS_RESPONSE", None),
                getattr(EventType, "TUNING_PARAMS", None),
                getattr(EventType, "CUSTOM_VARS", None),
                getattr(EventType, "ALLOWED_REPEAT_FREQ", None),
                getattr(EventType, "PATH_HASH_MODE", None),
            ):
                if self.rx_callback:
                    self.rx_callback(data)
                return

            if event_type == getattr(EventType, "ERROR", None):
                logging.warning(f"SDK Error: {data}")
                return
            if event_type == getattr(EventType, "CONNECTED", None):
                logging.info("SDK connected")
                return
            if event_type == getattr(EventType, "DISCONNECTED", None):
                logging.warning("SDK disconnected")
                return

        # Otros eventos - enviar al handler genérico
        await self._handle_generic_event(event_type, data)

    async def _initial_hardware_sync(self) -> None:
        """Interroga parámetros extendidos y telemetría de hardware al conectar."""
        if not self.mc or not hasattr(self.mc, "commands"):
            return
        await asyncio.sleep(1.0)
        cmds = self.mc.commands
        for cmd_name in (
            "send_device_query",
            "get_bat",
            "get_stats_core",
            "get_stats_radio",
            "get_stats_packets",
            "get_tuning",
            "get_self_telemetry",
            "get_custom_vars",
        ):
            if hasattr(cmds, cmd_name):
                try:
                    fn = getattr(cmds, cmd_name)
                    await fn()
                    await asyncio.sleep(0.15)
                except Exception as e:
                    logging.warning(f"Aviso en sincronización inicial de radio ({cmd_name}): {e}")

        # Sincronizar automáticamente el reloj RTC del ESP32 con la hora del host para eliminar desfase
        if hasattr(cmds, "set_time"):
            try:
                import time
                await cmds.set_time(int(time.time()))
                await asyncio.sleep(0.15)
            except Exception as e:
                logging.debug(f"Aviso sincronizando reloj RTC inicial: {e}")

        if hasattr(cmds, "get_time"):
            try:
                await cmds.get_time()
                await asyncio.sleep(0.15)
            except Exception as e:
                logging.debug(f"Aviso consultando hora tras sincronización RTC: {e}")


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
        if isinstance(data, dict):
            if self._self_info is None or not isinstance(self._self_info, dict):
                self._self_info = dict(data)
            else:
                self._self_info.update(data)
        elif data is not None:
            self._self_info = data
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
        """Maneja datos de log del firmware de radio UART (PUSH_CODE_LOG_RX_DATA 0x88)."""
        # Descartar en silencio para evitar saturación de logs y de la interfaz web
        return

    async def _handle_control_data(self, data: Any) -> None:
        """Maneja datos de control."""
        logging.debug(f"Control data: {data}")
        if self.rx_callback:
            self.rx_callback(data)

    async def _handle_generic_event(self, event_type: Any, data: Any) -> None:
        """Maneja eventos genéricos no categorizados."""
        ev_str = str(event_type).upper()
        if "LOG" in ev_str or "DEBUG" in ev_str:
            return
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
            await self._ensure_contact_for_tx(dest_target, target_clean)

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

    async def _ensure_contact_for_tx(self, dest_target: Any, target_clean: str) -> None:
        """Asegura que el destinatario esté registrado en la memoria de la radio física antes de TX.

        El firmware de MeshCore exige que el destinatario de un mensaje directo (CMD_SEND_TXT_MSG)
        exista en su tabla interna de contactos (lookupContactByPubKey). De lo contrario,
        el firmware rechaza la transmisión con ERR_CODE_NOT_FOUND (código 2).
        """
        if not self.is_connected or not self.mc or not hasattr(self.mc, "commands"):
            return

        try:
            pubkey = ""
            name = target_clean
            out_path = ""
            out_path_len: int | None = None
            out_path_hash_mode: int | None = None
            node_type = 1  # ADV_TYPE_CHAT
            lat = 0.0
            lon = 0.0

            if isinstance(dest_target, dict):
                pubkey = str(dest_target.get("public_key", "")).strip()
                name = str(dest_target.get("adv_name", dest_target.get("name", target_clean))).strip()
                out_path = str(dest_target.get("out_path", ""))
                out_path_len = dest_target.get("out_path_len")
                out_path_hash_mode = dest_target.get("out_path_hash_mode")
                node_type = dest_target.get("type", 1)
                lat = float(dest_target.get("adv_lat", dest_target.get("latitude", 0.0)) or 0.0)
                lon = float(dest_target.get("adv_lon", dest_target.get("longitude", 0.0)) or 0.0)
            elif hasattr(dest_target, "public_key"):
                pubkey = str(getattr(dest_target, "public_key", "")).strip()
                name = getattr(dest_target, "name", "") or getattr(dest_target, "alias", target_clean)
                out_path = getattr(dest_target, "out_path", "") or ""
                out_path_len = getattr(dest_target, "out_path_len", None)
                out_path_hash_mode = getattr(dest_target, "out_path_hash_mode", None)
                lat = float(getattr(dest_target, "latitude", 0.0) or 0.0)
                lon = float(getattr(dest_target, "longitude", 0.0) or 0.0)
            elif isinstance(dest_target, str):
                pubkey = dest_target.strip()

            if not pubkey or len(pubkey) < 12:
                return

            # Enriquecer con NodeRegistry si está disponible
            if hasattr(self, "node_registry") and self.node_registry:
                reg_node = self.node_registry.get_contact(pubkey) or self.node_registry.get_by_key_or_prefix(pubkey)
                if reg_node:
                    pubkey = getattr(reg_node, "public_key", pubkey) or pubkey
                    reg_name = getattr(reg_node, "name", "") or getattr(reg_node, "alias", "")
                    if reg_name:
                        name = reg_name
                    if out_path_len is None:
                        out_path = getattr(reg_node, "out_path", "") or ""
                        out_path_len = getattr(reg_node, "out_path_len", None)
                        out_path_hash_mode = getattr(reg_node, "out_path_hash_mode", None)
                    lat = float(getattr(reg_node, "latitude", lat) or lat or 0.0)
                    lon = float(getattr(reg_node, "longitude", lon) or lon or 0.0)

            full_pk = pubkey.ljust(64, "0")[:64]
            clean_name = (name or f"Node_{full_pk[:6]}")[:32]
            contact_data = {
                "public_key": full_pk,
                "adv_name": clean_name,
                "type": int(node_type) if node_type is not None else 1,
                "flags": 0,
                "out_path": str(out_path or ""),
                "out_path_len": int(out_path_len) if out_path_len is not None else -1,
                "out_path_hash_mode": int(out_path_hash_mode) if out_path_hash_mode is not None else 0,
                "last_advert": int(time.time()),
                "adv_lat": lat,
                "adv_lon": lon,
            }

            await self.add_contact(contact_data)
        except Exception as e_ac:
            logging.debug(f"Asegurando contacto en radio para TX: {e_ac}")

    def _resolve_target(self, name_or_key: str, min_hex_len: int = 12) -> Any:
        """Resuelve un identificador de destino a clave pública.

        Delega a TargetResolver (Single Source of Truth) para evitar
        duplicación de lógica con admin_handler.py.
        """
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
            elif hasattr(self.mc, "commands") and hasattr(self.mc.commands, "send_cmd"):
                clean_ch_name = name.strip().replace('"', "")
                cmd_str = f'set_chan {index} "{clean_ch_name}" {psk}'
                res = await self.mc.commands.send_cmd(cmd_str)
            else:
                res = "OK"

            # Actualizar la memoria RAM del SDK de MeshCore para sincronización inmediata
            try:
                reader = getattr(self.mc, "_reader", None) or getattr(self.mc, "reader", None)
                packet_parser = getattr(reader, "packet_parser", None) if reader else None
                if packet_parser and hasattr(packet_parser, "channels"):
                    if isinstance(packet_parser.channels, list):
                        if len(packet_parser.channels) <= index:
                            packet_parser.channels.extend([{} for _ in range(1 + index - len(packet_parser.channels))])
                        packet_parser.channels[index] = {"channel_idx": index, "channel_name": name, "channel_secret": secret_bytes}
                if hasattr(self.mc, "channels"):
                    if isinstance(self.mc.channels, dict):
                        self.mc.channels[index] = {"index": index, "name": name, "psk": psk}
                    elif isinstance(self.mc.channels, list):
                        if len(self.mc.channels) <= index:
                            self.mc.channels.extend([{} for _ in range(1 + index - len(self.mc.channels))])
                        self.mc.channels[index] = {"index": index, "name": name, "psk": psk}
            except Exception as e:
                logging.debug(f"Error actualizando canal {index} en memoria del SDK: {e}")

            return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo aplicando canal al transceptor serial: {e}")

        return {"status": "SAVED", "index": index, "name": name}

    async def delete_channel(self, index: int) -> dict[str, Any]:
        """Elimina o vacía un canal en el firmware del transceptor serial enviando set_channel con nombre vacío y clave de ceros."""
        if not (1 <= index <= 15):
            raise ValueError("Channel index out of range for deletion (1-15)")

        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_DELETED", "index": index}

        # 1. Purgar inmediatamente la memoria RAM del SDK de MeshCore
        try:
            reader = getattr(self.mc, "_reader", None) or getattr(self.mc, "reader", None)
            packet_parser = getattr(reader, "packet_parser", None) if reader else None
            if packet_parser and hasattr(packet_parser, "channels"):
                if isinstance(packet_parser.channels, list) and 0 <= index < len(packet_parser.channels):
                    packet_parser.channels[index] = {}
            if hasattr(self.mc, "channels"):
                if isinstance(self.mc.channels, dict):
                    self.mc.channels.pop(index, None)
                    self.mc.channels.pop(str(index), None)
                elif isinstance(self.mc.channels, list) and 0 <= index < len(self.mc.channels):
                    self.mc.channels[index] = {}
        except Exception as e:
            logging.debug(f"Error limpiando canal {index} de la memoria del SDK: {e}")

        # 2. Enviar orden de vaciado al firmware
        zero_secret = b"\x00" * 16
        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_channel"):
                res = await self.mc.commands.set_channel(index, "", zero_secret)
                return {"status": "OK", "response": str(res)}
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "send_cmd"):
                cmd_str = f'remove_channel {index}'
                res = await self.mc.commands.send_cmd(cmd_str)
                return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo eliminando canal {index} en el transceptor serial: {e}")

        return {"status": "DELETED", "index": index}

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Añade o actualiza un contacto en la memoria flash del transceptor serial."""
        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_SAVED", "contact": contact_data}

        try:
            pubkey = str(contact_data.get("public_key", "")).strip()
            name = str(contact_data.get("adv_name", contact_data.get("name", contact_data.get("alias", "")))).strip()
            if not name and pubkey:
                name = f"Node_{pubkey[:6]}"

            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "add_contact"):
                full_pk = pubkey.ljust(64, "0")[:64]
                # Normalizar estructura completa requerida por el SDK y firmware
                clean_contact = {
                    "public_key": full_pk,
                    "adv_name": name[:32],
                    "type": int(contact_data.get("type", 1)),
                    "flags": int(contact_data.get("flags", 0)),
                    "out_path": str(contact_data.get("out_path", "")),
                    "out_path_len": int(contact_data.get("out_path_len", -1)) if contact_data.get("out_path_len") is not None else -1,
                    "out_path_hash_mode": int(contact_data.get("out_path_hash_mode", 0)) if contact_data.get("out_path_hash_mode") is not None else 0,
                    "last_advert": int(contact_data.get("last_advert", time.time())),
                    "adv_lat": float(contact_data.get("adv_lat", contact_data.get("latitude", 0.0)) or 0.0),
                    "adv_lon": float(contact_data.get("adv_lon", contact_data.get("longitude", 0.0)) or 0.0),
                }
                res = await self.mc.commands.add_contact(clean_contact)
                if hasattr(self.mc, "_contacts") and isinstance(self.mc._contacts, dict):
                    self.mc._contacts[full_pk] = clean_contact
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
                    last_advert = None
                    if isinstance(c, dict):
                        pk = str(c.get("public_key", c.get("key", ""))).strip()
                        adv_name = str(c.get("adv_name", c.get("name", c.get("alias", f"Node_{pk[:6]}")))).strip()
                        raw_type_val = c.get("type", c.get("adv_type", 1))
                        raw_type = int(raw_type_val) if raw_type_val is not None else 1
                        adv_lat = c.get("adv_lat", c.get("latitude"))
                        adv_lon = c.get("adv_lon", c.get("longitude"))
                        last_advert = c.get("last_advert")
                    elif hasattr(c, "public_key") or hasattr(c, "adv_name") or hasattr(c, "name"):
                        pk = str(getattr(c, "public_key", "")).strip()
                        adv_name = str(getattr(c, "adv_name", getattr(c, "name", getattr(c, "alias", f"Node_{pk[:6]}")))).strip()
                        raw_type_val = getattr(c, "adv_type", getattr(c, "type", 1))
                        raw_type = int(raw_type_val) if raw_type_val is not None else 1
                        adv_lat = getattr(c, "adv_lat", getattr(c, "latitude", None))
                        adv_lon = getattr(c, "adv_lon", getattr(c, "longitude", None))
                        last_advert = getattr(c, "last_advert", None)

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
                            "last_advert": last_advert,
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

    async def export_contact(self, contact_key: str | None = None) -> Any:
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



    async def get_stats_core(self) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_stats_core"):
            return await self.mc.commands.get_stats_core()
        return None

    async def get_stats_radio(self) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_stats_radio"):
            return await self.mc.commands.get_stats_radio()
        return None

    async def get_stats_packets(self) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_stats_packets"):
            return await self.mc.commands.get_stats_packets()
        return None

    async def get_autoadd_config(self) -> Any:
        # Note: the sdk doesn't have a direct get_autoadd_config, but we return from self_info
        if hasattr(self, "self_info") and isinstance(self.self_info, dict):
            return self.self_info.get("manual_add_contacts")
        return None

    async def set_autoadd_config(self, flag: bool) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_manual_add_contacts"):
            return await self.mc.commands.set_manual_add_contacts(flag)
        return None

    async def set_other_params_from_infos(self, infos: dict[str, Any]) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_other_params_from_infos"):
            return await self.mc.commands.set_other_params_from_infos(infos)
        return None

    async def get_advert_path(self, key: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_advert_path"):
            return await self.mc.commands.get_advert_path(key)
        return None

    async def get_contact_by_key(self, pubkey: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "get_contact_by_key"):
            return self.mc.get_contact_by_key(pubkey)
        return None

    async def send_path_discovery_sync(self, dst: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "send_path_discovery_sync"):
            return await self.mc.commands.send_path_discovery_sync(dst)
        return None

    async def set_flood_scope(self, scope: int) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_flood_scope"):
            return await self.mc.commands.set_flood_scope(scope)
        return None

    async def get_default_flood_scope(self) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_default_flood_scope"):
            return await self.mc.commands.get_default_flood_scope()
        return None

    async def set_devicepin(self, pin: int) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_devicepin"):
            return await self.mc.commands.set_devicepin(pin)
        return None

    async def set_time(self, val: int) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_time"):
            return await self.mc.commands.set_time(val)
        return None

    async def has_connection(self) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "has_connection"):
            return await self.mc.commands.has_connection()
        return None

    async def set_path_hash_mode(self, mode: int) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_path_hash_mode"):
            return await self.mc.commands.set_path_hash_mode(mode)
        return None

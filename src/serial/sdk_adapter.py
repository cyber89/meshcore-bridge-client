"""
MeshCore Official SDK Adapter (meshcore_py) for MeshCore Bridge.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from src.protocol_types import MeshCoreSDKProtocol, normalize_tx_power
from src.serial.serial_base import BaseSerialAdapter
from src.shared_utils import classify_device_role, is_empty_channel_slot
from src.target_resolver import TargetResolver

try:
    from meshcore import EventType, MeshCore
    from meshcore.events import Event
except ImportError:
    MeshCore = None
    EventType = None
    Event = None

__all__ = ["MeshcoreSDKAdapter", "MeshCore", "EventType", "Event"]

# Firmware BaseChatMesh.h: MAX_TEXT_LEN = 10 * CIPHER_BLOCK_SIZE (16).
MAX_TEXT_BYTES = 160
# Firmware stores channel names in char[32], with a trailing NUL.
MAX_CHANNEL_NAME_BYTES = 31

# Terminal synchronous response codes from Companion MyMesh.cpp. Pushes remain
# asynchronous; GET_CONTACTS additionally forwards START/CONTACT until END.
_RAW_OK_COMMANDS = (
    3, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 18, 21, 24, 25, 28, 29,
    32, 34, 37, 38, 41, 51, 54, 55, 58, 61, 62, 63, 65,
)
_RAW_REPLY_TYPES: dict[int, frozenset[int]] = {
    **{opcode: frozenset({0}) for opcode in _RAW_OK_COMMANDS},
    1: frozenset({5}),  # APP_START -> SELF_INFO
    2: frozenset({6}),  # SEND_TXT_MSG -> SENT (not delivery ACK)
    4: frozenset({4}),  # GET_CONTACTS -> END_OF_CONTACTS
    5: frozenset({9}),  # GET_DEVICE_TIME -> CURR_TIME
    10: frozenset({7, 8, 10, 16, 17}),  # SYNC_NEXT_MESSAGE
    17: frozenset({11}),  # EXPORT_CONTACT
    20: frozenset({12}),  # GET_BATT_AND_STORAGE
    22: frozenset({13}),  # DEVICE_QUERY
    23: frozenset({14}),  # EXPORT_PRIVATE_KEY
    26: frozenset({6}),  # SEND_LOGIN
    27: frozenset({6}),  # SEND_STATUS_REQ
    30: frozenset({3}),  # GET_CONTACT_BY_KEY
    31: frozenset({18}),  # GET_CHANNEL
    33: frozenset({19}),  # SIGN_START
    35: frozenset({20}),  # SIGN_FINISH
    36: frozenset({6}),  # SEND_TRACE_PATH
    39: frozenset({6}),  # Remote SEND_TELEMETRY_REQ; self telemetry is a push.
    40: frozenset({21}),  # GET_CUSTOM_VARS
    42: frozenset({22}),  # GET_ADVERT_PATH
    43: frozenset({23}),  # GET_TUNING_PARAMS
    50: frozenset({6}),  # SEND_BINARY_REQ
    52: frozenset({6}),  # SEND_PATH_DISCOVERY_REQ
    56: frozenset({24}),  # GET_STATS
    57: frozenset({6}),  # SEND_ANON_REQ
    59: frozenset({25}),  # GET_AUTOADD_CONFIG
    60: frozenset({26}),  # GET_ALLOWED_REPEAT_FREQ
    64: frozenset({28}),  # GET_DEFAULT_FLOOD_SCOPE
}


class _BootWaitSerialConnection:
    """Wrapper de SerialConnection que añade espera de boot tras apertura del puerto."""

    def __init__(self, inner: Any, boot_wait: float = 5.0) -> None:
        self._inner = inner
        self._boot_wait = boot_wait
        self._disconnect_callback: Any = None

    @property
    def transport(self) -> Any:
        return getattr(self._inner, "transport", None)

    @transport.setter
    def transport(self, val: Any) -> None:
        if hasattr(self._inner, "transport"):
            self._inner.transport = val

    @property
    def reader(self) -> Any:
        return getattr(self._inner, "reader", None)

    @reader.setter
    def reader(self, val: Any) -> None:
        if hasattr(self._inner, "reader"):
            self._inner.reader = val

    @property
    def _connected_event(self) -> Any:
        return getattr(self._inner, "_connected_event", None)

    @property
    def _background_tasks(self) -> Any:
        return getattr(self._inner, "_background_tasks", None)

    async def connect(self) -> Any:
        result = await self._inner.connect()
        if result is not None:
            logging.debug(
                f"Puerto {getattr(self._inner, 'port', '?')} abierto. "
                f"Esperando {self._boot_wait}s de boot del ESP32-S3..."
            )
            await asyncio.sleep(self._boot_wait)
        return result

    async def disconnect(self) -> None:
        await self._inner.disconnect()

    async def send(self, data: Any) -> None:
        await self._inner.send(data)

    def set_reader(self, reader: Any) -> None:
        self._inner.set_reader(reader)

    def set_disconnect_callback(self, callback: Any) -> None:
        self._disconnect_callback = callback
        self._inner.set_disconnect_callback(callback)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _safe_truncate_utf8(text: str, max_bytes: int = 32) -> str:
    """Trunca una cadena asegurando que su codificación UTF-8 no exceda max_bytes."""
    raw = str(text or "").encode("utf-8")
    if len(raw) <= max_bytes:
        return str(text or "")
    return raw[:max_bytes].decode("utf-8", "ignore")


def _copy_self_info_snapshot(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize observed fields without modifying a private SDK payload."""
    snapshot = dict(info)
    if "tx_power" in snapshot:
        power = normalize_tx_power(snapshot["tx_power"])
        if power is not None or snapshot["tx_power"] is None:
            snapshot["tx_power"] = power
        else:
            snapshot.pop("tx_power")
    return snapshot


class MeshcoreSDKAdapter(BaseSerialAdapter):
    """Adaptador principal basado en el SDK oficial meshcore_py."""

    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        timeout_sec: float = 30.0,
        node_registry: Any = None,
    ) -> None:
        super().__init__(port, baud_rate, timeout_sec, node_registry)
        self.mc: MeshCoreSDKProtocol | Any = None
        self._initial_sync_task: asyncio.Task[None] | None = None
        self._self_info: dict[str, Any] | None = None
        self._sdk_dispatch_cache: dict[Any, Callable[[Any], Any]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._is_syncing_hardware: bool = False
        self._command_lock = asyncio.Lock()
        self._serialized_commands: Any = None
        self._raw_command_future: asyncio.Future[bool] | None = None
        self._raw_command_opcode: int | None = None

    def _observe_companion_frame(self, data: bytes) -> None:
        """Route pushes and the current raw transaction, never internal SDK replies.

        The callback is called synchronously so the TCP response owner is captured
        before completing the future and releasing the transaction lock.
        """
        if not data:
            return
        pending = self._raw_command_future
        raw_active = pending is not None and not pending.done()
        response_type = data[0]
        terminal = _RAW_REPLY_TYPES.get(self._raw_command_opcode or 0, frozenset())
        failed = response_type in (1, 15)  # ERR / DISABLED
        stream_item = self._raw_command_opcode == 4 and response_type in (2, 3)
        matches_raw = raw_active and (failed or stream_item or response_type in terminal)
        if (response_type >= 0x80 or matches_raw) and self.companion_rx_callback:
            try:
                self.companion_rx_callback(data)
            except Exception as ex:
                logging.debug("Error en companion_rx_callback: %s", ex)
        if pending is not None and matches_raw and not stream_item:
            pending.set_result(not failed)

    def _raw_chat_permitted(self, data: bytes) -> bool:
        """Keep the same local identity and infrastructure guards on the raw path."""
        if data[0] == 2:
            if len(data) < 14:
                return False
            prefix = data[7:13].hex()
            local = str((self.self_info or {}).get("public_key", "")).lower()
            if local and local.startswith(prefix):
                return False
            if self.node_registry and self.node_registry.is_local_key(prefix):
                return False
            # MeshCore text type 1 is administrative CLI, not user chat.
            if data[1] != 1:
                if self.node_registry and self.node_registry.is_repeater_key(prefix):
                    return False
                contacts = getattr(self.mc, "contacts", {})
                if isinstance(contacts, dict):
                    for key, contact in contacts.items():
                        if str(key).lower().startswith(prefix) and isinstance(contact, dict):
                            if int(contact.get("type", -1)) == 2:
                                return False
            text = data[13:]
        elif data[0] == 3:
            if len(data) < 8:
                return False
            text = data[7:]
            name = str((self.self_info or {}).get("name", ""))
            if len(text) + len((name + ": ").encode("utf-8")) > MAX_TEXT_BYTES:
                return False
        else:
            return True
        return b"\x00" not in text and len(text) <= MAX_TEXT_BYTES

    async def run_sdk_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Serialize response waits: Companion OK/ERROR frames carry no request ID.

        Administrative callers use this same entry point to share the lock with
        message TX, local probes and initial synchronization.
        """
        if self.mc is None or not self.is_connected:
            raise ConnectionError("MeshCore SDK no conectado")
        commands = self.mc.commands
        if self._serialized_commands is commands:
            return await getattr(commands, command)(*args, **kwargs)
        async with self._command_lock:
            if self.mc is None or not self.is_connected:
                raise ConnectionError("MeshCore SDK no conectado")
            return await getattr(commands, command)(*args, **kwargs)

    def _serialize_sdk_response_waits(self) -> None:
        """Wrap only this SDK instance, including its internal auto-fetch calls.

        The SDK's high-level mesh request lock serves a different purpose and
        is never acquired here. One local response lock covers CommandHandler.send
        so unsolicited ERROR cannot satisfy several pending commands at once.
        """
        commands = getattr(self.mc, "commands", None)
        if commands is None:
            return
        original_send = getattr(commands, "send", None)
        if not callable(original_send):
            return
        if getattr(commands, "_meshcore_bridge_serialized_owner", None) is self:
            self._serialized_commands = commands
            return

        async def serialized_send(*args: Any, **kwargs: Any) -> Any:
            async with self._command_lock:
                return await original_send(*args, **kwargs)

        commands._meshcore_bridge_serialized_owner = self
        commands.send = serialized_send
        self._serialized_commands = commands

    @staticmethod
    def _command_error(response: Any) -> dict[str, Any] | None:
        if response is None or (
            EventType is not None and getattr(response, "type", None) == EventType.ERROR
        ):
            return {"status": "ERROR", "reason": str(getattr(response, "payload", "sin respuesta")), "response": str(response)}
        return None

    @property
    def self_info(self) -> Any:
        """Información del nodo local obtenida del SDK."""
        if self._self_info is not None:
            return self._self_info
        info = getattr(self.mc, "self_info", None) if self.mc else None
        if isinstance(info, dict):
            self._self_info = _copy_self_info_snapshot(info)
            return self._self_info
        return info

    @self_info.setter
    def self_info(self, value: Any) -> None:
        if isinstance(value, dict):
            self._self_info = _copy_self_info_snapshot(value)
        else:
            self._self_info = value

    async def connect(self) -> bool:
        if MeshCore is None:
            logging.warning("SDK meshcore_py no disponible en el entorno.")
            return False

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        await self._connect_with_stabilization()
        return self.is_connected

    async def _connect_with_stabilization(self) -> None:
        if self.mc is not None or self.is_connected:
            await self.disconnect()
            await asyncio.sleep(0.5)

        try:
            self.port = self.resolve_port(self.port)

            if self.port.startswith("tcp://"):
                addr = self.port.replace("tcp://", "")
                host, port_str = addr.split(":", 1) if ":" in addr else (addr, "4000")
                logging.info(f"Iniciando conexión MeshCore SDK remota TCP en {host}:{port_str}...")
                if hasattr(MeshCore, "create_tcp"):
                    self.mc = await MeshCore.create_tcp(host, int(port_str), auto_reconnect=False)
                else:
                    from meshcore.tcp_cx import TCPConnection
                    cx = TCPConnection(host, int(port_str))
                    self.mc = MeshCore(cx, auto_reconnect=False)
                    if hasattr(self.mc, "connect"):
                        await self.mc.connect()
            else:
                logging.info(f"Iniciando conexión MeshCore SDK en puerto {self.port} ({self.baud_rate} baud)...")
                _BOOT_WAIT_SEC = 5.0
                _MC_TOTAL_TIMEOUT = max(35.0, self.timeout_sec + 5.0)

                _mc_raw: Any = None
                try:
                    from meshcore.serial_cx import SerialConnection
                    cx_inner = SerialConnection(self.port, self.baud_rate, cx_dly=0.0)
                    cx_wrapped = _BootWaitSerialConnection(cx_inner, _BOOT_WAIT_SEC)
                    self.mc = None
                    _mc_raw = MeshCore(cx_wrapped, auto_reconnect=False)

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
                    if _mc_raw is not None:
                        try:
                            await asyncio.wait_for(_mc_raw.disconnect(), timeout=1.5)
                        except Exception:
                            pass

            if self.mc is None:
                logging.error(f"No se pudo establecer conexión con el transceptor MeshCore en {self.port}.")
                self.is_connected = False
                return

            self.is_connected = True
            self._register_event_handlers()
            if hasattr(self.mc, "start_auto_message_fetching"):
                await self.mc.start_auto_message_fetching()
            if hasattr(self.mc, "ensure_contacts"):
                try:
                    await self.mc.ensure_contacts()
                except Exception as e:
                    logging.warning(f"Error sincronizando libreta de contactos de MeshCore: {e}")

            self.heartbeat()
            if self.self_info and self.rx_callback and Event and EventType:
                try:
                    self.rx_callback(Event(EventType.SELF_INFO, self.self_info))
                except Exception as ex_si:
                    logging.warning(f"Despacho inicial de self_info: {ex_si}")
            logging.info("MeshCore SDK conectado e iniciado exitosamente.")
            self._initial_sync_task = asyncio.create_task(self._initial_hardware_sync())
        except asyncio.CancelledError:
            await self.disconnect()
            raise
        except Exception as e:
            logging.error(f"Error conectando con MeshCore SDK: {e}", exc_info=True)
            await self.disconnect()

    async def disconnect(self) -> None:
        self.is_connected = False
        if self._raw_command_future and not self._raw_command_future.done():
            self._raw_command_future.set_result(False)
        if self._initial_sync_task and not self._initial_sync_task.done():
            self._initial_sync_task.cancel()
            try:
                await asyncio.wait_for(self._initial_sync_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            self._initial_sync_task = None

        # Drenar y cancelar tareas en segundo plano
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._background_tasks, return_exceptions=True),
                    timeout=1.0
                )
            except Exception:
                pass
            self._background_tasks.clear()

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
        self._serialized_commands = None

    def is_hardware_alive(self) -> bool:
        """Verifica si el transceptor USB / TCP sigue presente en el sistema operativo y operativo."""
        if not self.is_connected or self.mc is None:
            return False

        port_str = str(self.port)
        if port_str.upper().startswith("VIRTUAL"):
            return bool(self.is_connected)

        # 1. Comprobación física de transporte serial abierto y estado de conexión en el SDK oficial
        try:
            if hasattr(self.mc, "is_connected"):
                is_mc_conn = self.mc.is_connected
                if callable(is_mc_conn):
                    is_mc_conn = is_mc_conn()
                if not is_mc_conn:
                    self.is_connected = False
                    return False

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
        except Exception as e:
            logging.debug(f"Excepción verificando transporte serial: {e}")

        return bool(self.is_connected)

    async def ping_or_check_alive(self) -> bool:
        """Comprueba si el transceptor local sigue vivo y respondiendo activamente por serial."""
        if not self.is_hardware_alive():
            self.is_connected = False
            return False

        # Si hay comandos disponibles, verificar vivacidad mediante comando canónico ligero (get_time / get_bat)
        if self.mc and hasattr(self.mc, "commands"):
            try:
                cmds = self.mc.commands
                if hasattr(cmds, "get_time"):
                    res = await asyncio.wait_for(self.run_sdk_command("get_time"), timeout=3.0)
                    if res is not None and getattr(res, "type", None) != getattr(EventType, "ERROR", None):
                        self.heartbeat()
                        return True
                elif hasattr(cmds, "get_bat"):
                    res = await asyncio.wait_for(self.run_sdk_command("get_bat"), timeout=3.0)
                    if res is not None and getattr(res, "type", None) != getattr(EventType, "ERROR", None):
                        self.heartbeat()
                        return True
                elif hasattr(cmds, "send_device_query"):
                    res = await asyncio.wait_for(self.run_sdk_command("send_device_query"), timeout=3.0)
                    if res is not None and getattr(res, "type", None) != getattr(EventType, "ERROR", None):
                        self.heartbeat()
                        return True
            except Exception as e_ping:
                logging.debug(f"Comprobación activa de vivacidad devolvió excepción: {e_ping}")
                return False
            if any(hasattr(cmds, name) for name in ("get_time", "get_bat", "send_device_query")):
                return False

        self.heartbeat()
        return bool(self.is_hardware_alive())

    def _register_event_handlers(self) -> None:
        if not self.mc:
            return
        owning_mc = self.mc
        self._serialize_sdk_response_waits()

        # Hook para interceptar tramas binarias de la radio y difundirlas a clientes companion (App/CLI)
        if hasattr(self.mc, "_reader") and hasattr(self.mc._reader, "handle_rx"):
            original_handle_rx = self.mc._reader.handle_rx

            async def _hooked_handle_rx(data: bytearray) -> None:
                self.heartbeat()
                self._observe_companion_frame(bytes(data))
                await original_handle_rx(data)

            self.mc._reader.handle_rx = _hooked_handle_rx

        if not hasattr(self.mc, "subscribe"):
            return

        def _make_handler(et: Any) -> Callable[[Any], None]:
            def _handler(event: Any) -> None:
                try:
                    loop = self._loop
                    if loop is None or loop.is_closed():
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            pass
                    if loop and loop.is_running():
                        def schedule() -> None:
                            if not self.is_connected or self.mc is not owning_mc or loop is None or loop.is_closed():
                                return
                            task = loop.create_task(self._on_sdk_event(et, event))
                            self._background_tasks.add(task)
                            def completed(done: asyncio.Task[Any]) -> None:
                                self._background_tasks.discard(done)
                                if not done.cancelled():
                                    error = done.exception()
                                    if error:
                                        logging.debug("Evento SDK falló: %s", type(error).__name__)
                            task.add_done_callback(completed)
                        try:
                            running = asyncio.get_running_loop()
                            if running is loop:
                                schedule()
                                return
                        except RuntimeError:
                            pass
                        loop.call_soon_threadsafe(schedule)
                except Exception as ex:
                    logging.debug(f"Error despachando evento SDK {et}: {ex}")
            return _handler

        if EventType:
            for ev_type in EventType:
                try:
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
                if hasattr(EventType, "CHANNEL_INFO"):
                    self._sdk_dispatch_cache[EventType.CHANNEL_INFO] = self._handle_channel_info
                if hasattr(EventType, "LOG_DATA"):
                    self._sdk_dispatch_cache[EventType.LOG_DATA] = self._handle_log_data
                if hasattr(EventType, "RX_LOG_DATA"):
                    self._sdk_dispatch_cache[EventType.RX_LOG_DATA] = self._handle_log_data
                def _make_generic_handler(ev_target: Any) -> Callable[[Any], Any]:
                    def _h(d: Any) -> Any:
                        return self._handle_generic_event(ev_target, d)
                    return _h

                for extra_name in (
                    "PATH_RESPONSE",
                    "MMA_RESPONSE",
                    "ACL_RESPONSE",
                    "AUTOADD_CONFIG",
                    "DEFAULT_FLOOD_SCOPE",
                    "CONTACTS_FULL",
                    "CURRENT_TIME",
                    "CONTACT_URI",
                ):
                    ev_val = getattr(EventType, extra_name, None)
                    if ev_val is not None:
                        self._sdk_dispatch_cache[ev_val] = _make_generic_handler(ev_val)
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
                elif hasattr(data, "payload") and isinstance(data.payload, dict):
                    pk_hint = str(data.payload.get("public_key", data.payload.get("key", "")))[:12]
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
                getattr(EventType, "PATH_RESPONSE", None),
                getattr(EventType, "MMA_RESPONSE", None),
                getattr(EventType, "ACL_RESPONSE", None),
                getattr(EventType, "AUTOADD_CONFIG", None),
                getattr(EventType, "DEFAULT_FLOOD_SCOPE", None),
                getattr(EventType, "CONTACTS_FULL", None),
                getattr(EventType, "CURRENT_TIME", None),
            ):
                if self.rx_callback:
                    self.rx_callback(data)
                return

            if event_type == getattr(EventType, "ERROR", None):
                payload: dict[str, Any] = {}
                if hasattr(data, "payload") and isinstance(data.payload, dict):
                    payload = data.payload
                elif isinstance(data, dict):
                    payload = data
                code_str = str(payload.get("code_string", ""))
                err_code = payload.get("error_code")
                if self._is_syncing_hardware and code_str == "ERR_CODE_UNSUPPORTED_CMD":
                    logging.debug(f"Capacidad de hardware opcional no soportada por el firmware: {data}")
                else:
                    logging.warning(f"Error SDK recibido desde la radio ({code_str or err_code or 'desconocido'}): {data}")
                return
            if event_type == getattr(EventType, "CONNECTED", None):
                logging.info("SDK connected")
                self.is_connected = True
                return
            if event_type == getattr(EventType, "DISCONNECTED", None):
                logging.warning("SDK disconnected")
                self.is_connected = False
                return

        # Otros eventos - enviar al handler genérico
        await self._handle_generic_event(event_type, data)

    async def _initial_hardware_sync(self) -> None:
        """Interroga parámetros extendidos y telemetría de hardware al conectar."""
        if not self.mc or not hasattr(self.mc, "commands"):
            return
        self._is_syncing_hardware = True
        try:
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
                        await self.run_sdk_command(cmd_name)
                        await asyncio.sleep(0.15)
                    except Exception as e:
                        logging.debug(f"Aviso en sincronización inicial de radio ({cmd_name}): {e}")

            # Sincronizar automáticamente el reloj RTC del ESP32 con la hora del host para eliminar desfase
            if hasattr(cmds, "set_time"):
                try:
                    await self.run_sdk_command("set_time", int(time.time()))
                    await asyncio.sleep(0.15)
                except Exception as e:
                    logging.debug(f"Aviso sincronizando reloj RTC inicial: {e}")

            if hasattr(cmds, "get_time"):
                try:
                    await self.run_sdk_command("get_time")
                    await asyncio.sleep(0.15)
                except Exception as e:
                    logging.debug(f"Aviso consultando hora tras sincronización RTC: {e}")
        finally:
            self._is_syncing_hardware = False


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

    async def _handle_channel_info(self, data: Any) -> None:
        """Maneja respuestas CHANNEL_INFO del transceptor serial y actualiza el caché de canales."""
        payload: dict[str, Any] = {}
        if hasattr(data, "payload") and isinstance(data.payload, dict):
            payload = data.payload
        elif isinstance(data, dict):
            payload = data

        idx_raw = payload.get("channel_idx")
        if idx_raw is None:
            return
        try:
            ch_idx = int(idx_raw)
        except (ValueError, TypeError):
            return

        ch_name = str(payload.get("channel_name", "")).strip()
        ch_sec = payload.get("channel_secret")
        psk_hex = ch_sec.hex() if isinstance(ch_sec, (bytes, bytearray)) else str(ch_sec or "")
        ch_hash = str(payload.get("channel_hash", ""))

        if is_empty_channel_slot(ch_name, ch_sec):
            logging.debug(f"Canal #{ch_idx} slot vacío en transceptor serial")
            if hasattr(self.mc, "channels"):
                if isinstance(self.mc.channels, dict):
                    self.mc.channels.pop(ch_idx, None)
                    self.mc.channels.pop(str(ch_idx), None)
                elif isinstance(self.mc.channels, list) and 0 <= ch_idx < len(self.mc.channels):
                    self.mc.channels[ch_idx] = {}
            return

        # Canal configurado legítimo
        logging.debug(f"Canal #{ch_idx} sincronizado desde radio: {ch_name} (hash: {ch_hash})")
        if hasattr(self.mc, "channels"):
            ch_entry = {
                "index": ch_idx,
                "name": ch_name,
                "psk": psk_hex,
                "channel_hash": ch_hash,
            }
            if isinstance(self.mc.channels, dict):
                self.mc.channels[ch_idx] = ch_entry
            elif isinstance(self.mc.channels, list):
                if len(self.mc.channels) <= ch_idx:
                    self.mc.channels.extend([{} for _ in range(1 + ch_idx - len(self.mc.channels))])
                self.mc.channels[ch_idx] = ch_entry

        if self.rx_callback:
            self.rx_callback({
                "type": "channel_info",
                "event_type": "channel_info",
                "is_local": True,
                "channel_idx": ch_idx,
                "channel_name": ch_name,
                "channel_hash": ch_hash,
            })

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
        info_dict: dict[str, Any] = {}
        if isinstance(data, dict):
            info_dict = data
        elif hasattr(data, "payload") and isinstance(data.payload, dict):
            info_dict = data.payload

        if info_dict:
            target_info: dict[str, Any] = {}
            if hasattr(self, "_self_info") and isinstance(self._self_info, dict):
                target_info = self._self_info
            elif hasattr(self, "self_info") and isinstance(self.self_info, dict):
                target_info = self.self_info
            else:
                self._self_info = {}
                target_info = self._self_info

            for k in ("repeat", "max_channels", "max_contacts", "model", "ver", "fw_build", "fw ver"):
                if k in info_dict:
                    target_info[k] = info_dict[k]
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
        payload = getattr(data, "payload", data)
        if isinstance(payload, dict):
            update = _copy_self_info_snapshot(payload)
            current = self._self_info if isinstance(self._self_info, dict) else {}
            self.self_info = {**current, **update}
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
        if self.rx_callback and data:
            if isinstance(data, dict):
                evt = dict(data)
                evt.setdefault("event_type", "RX_LOG_DATA")
                self.rx_callback(evt)
            elif hasattr(data, "payload"):
                self.rx_callback(data)
            else:
                self.rx_callback({"event_type": "RX_LOG_DATA", "data": data})

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
        """Serialize a raw transaction with SDK response waits; GET_CONTACTS is a stream.

        Companion responses have no request ID. After a timeout a late reply cannot
        be attributed with certainty; no automatic retransmission is introduced.
        """
        if not self.is_connected or not self.mc or not data or not self._raw_chat_permitted(data):
            return False
        try:
            async with self._command_lock:
                if not self.is_connected or not self.mc:
                    return False
                connection = getattr(self.mc, "cx", None) or getattr(self.mc, "connection", None)
                if connection is None or not hasattr(connection, "send"):
                    return False
                self._raw_command_opcode = data[0]
                pending = asyncio.get_running_loop().create_future()
                self._raw_command_future = pending
                try:
                    await connection.send(data)
                    if data[0] == 19:  # Official reboot is fire-and-forget.
                        return True
                    return bool(await asyncio.wait_for(pending, timeout=self.timeout_sec))
                finally:
                    if not pending.done():
                        pending.cancel()
                    self._raw_command_future = None
                    self._raw_command_opcode = None
        except asyncio.TimeoutError:
            logging.warning("Timeout de respuesta Companion raw (opcode=%s)", data[0])
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

        # 1. Validación estricta de MTU LoRa
        raw_bytes = text.encode("utf-8")
        if len(raw_bytes) > MAX_TEXT_BYTES:
            raise ValueError(f"Payload de mensaje excede límite oficial ({len(raw_bytes)} > {MAX_TEXT_BYTES} bytes)")
        if "\x00" in text:
            raise ValueError("El texto no puede contener NUL: el firmware usa cadenas terminadas en NUL")

        # 2. Validación estricta de rango de canal
        safe_ch = int(channel_idx) if channel_idx is not None else 0
        cap = self._channel_capacity()
        if not (0 <= safe_ch < cap):
            raise ValueError(f"Índice de canal inválido ({safe_ch}). Debe estar en el rango 0..{cap - 1}.")

        target_clean = str(target).strip() if target else ""
        is_dm = bool(
            target_clean
            and target_clean.upper() not in ("0XFFFF", "0xFFFF", "BROADCAST", "PUBLIC", "ALL", "GLOBAL", "NONE", "")
            and not target_clean.lower().startswith("channel")
        )

        # Canal público vs mensaje directo (DM)
        if is_dm:
            dest_target = self._resolve_target(target_clean)
            if isinstance(dest_target, dict):
                dest_target_str = str(dest_target.get("public_key", "")).strip().lower()
                target_role = classify_device_role(int(dest_target.get("type", dest_target.get("adv_type", 1)) or 0), False)
            else:
                dest_target_str = str(getattr(dest_target, "public_key", dest_target)).strip().lower()
                target_role = str(getattr(dest_target, "role", "")).upper()
            if target_role in ("REPEATER", "ROUTER"):
                raise ValueError("Envío de chat prohibido: el destinatario es un REPEATER de infraestructura")

            # AGENTS.md Regla 1.1: NUNCA permitir mensajería de chat hacia repetidores
            if self.node_registry:
                node = self.node_registry.get_by_key_or_prefix(dest_target_str) or self.node_registry.find_by_name(target_clean)
                if node and str(getattr(node, "role", "")).upper() in ("REPEATER", "ROUTER"):
                    raise ValueError(
                        f"Envío de chat prohibido: el nodo '{target_clean}' es un REPEATER de infraestructura (AGENTS.md Regla 1.1)"
                    )

            # AGENTS.md Regla 1.1: NUNCA permitir envío dirigido a la clave propia local (bucle local prohibido)
            local_pk = ""
            if self.self_info and isinstance(self.self_info, dict):
                local_pk = str(self.self_info.get("public_key", self.self_info.get("key", ""))).lower()
            if local_pk and dest_target_str and (dest_target_str.startswith(local_pk) or local_pk.startswith(dest_target_str)):
                raise ValueError("Bucle local prohibido: no se puede enviar mensaje al propio nodo local (AGENTS.md Regla 1.1)")

            # Asegurar contacto en la radio antes de transmitir
            await self._ensure_contact_for_tx(dest_target, target_clean)

            if hasattr(self.mc.commands, "send_msg"):
                res = await self.run_sdk_command("send_msg", dest_target, text)
            else:
                raise NotImplementedError("send_msg no soportado en este SDK")
        else:
            info = self.self_info
            name = str(info.get("name", "")) if isinstance(info, dict) else ""
            # BaseChatMesh::sendGroupMessage prepends '<sender>: ' within MAX_TEXT_LEN.
            prefix_bytes = len(name.encode("utf-8")) + 2
            max_channel_bytes = MAX_TEXT_BYTES - prefix_bytes
            if len(raw_bytes) > max_channel_bytes:
                raise ValueError(f"Texto de canal excede límite oficial con prefijo ({len(raw_bytes)} > {max_channel_bytes} bytes)")
            if hasattr(self.mc.commands, "send_chan_msg"):
                res = await self.run_sdk_command("send_chan_msg", safe_ch, text)
            elif hasattr(self.mc.commands, "send_channel_msg"):
                res = await self.run_sdk_command("send_channel_msg", safe_ch, text)
            elif hasattr(self.mc.commands, "send_msg"):
                raise NotImplementedError("send_chan_msg no soportado en este SDK")
            else:
                raise NotImplementedError("send_chan_msg no soportado en este SDK")

        error = self._command_error(res)
        if error:
            error["event"] = res
            return error

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

            cached_contacts = getattr(self.mc, "_contacts", None)
            if isinstance(cached_contacts, dict) and any(
                str(key).lower().startswith(pubkey.lower()) for key in cached_contacts
            ):
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

            # A 6-byte TX prefix identifies an existing firmware contact; it
            # cannot reconstruct the full 32-byte identity for CMD_ADD_CONTACT.
            if not re.fullmatch(r"[a-fA-F0-9]{64}", pubkey):
                return
            full_pk = pubkey.lower()
            clean_name = _safe_truncate_utf8(name or f"Node_{full_pk[:6]}", 32)
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

            # 2. Si no hay canales en memoria, consultar canales al firmware mediante get_channel
            if not channels and hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_channel"):
                max_ch = 8
                if isinstance(self.self_info, dict) and "max_channels" in self.self_info:
                    try:
                        max_ch = min(255, max(1, int(self.self_info["max_channels"])))
                    except (ValueError, TypeError):
                        max_ch = 8
                for ch_idx in range(max_ch):
                    try:
                        ev = await self.run_sdk_command("get_channel", ch_idx)
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
                    except Exception as ex:
                        logging.debug(f"Canal {ch_idx} no configurado o no responde: {ex}")
        except Exception as e:
            logging.debug(f"Error extrayendo canales del nodo USB: {e}")

        return channels

    def _channel_capacity(self) -> int:
        info = self.self_info
        if isinstance(info, dict) and "max_channels" in info:
            try:
                return min(255, max(1, int(info["max_channels"])))
            except (ValueError, TypeError):
                pass
        return 16  # Legacy firmware without a capacity announcement.

    async def set_channel(self, index: int, name: str, psk: str) -> dict[str, Any]:
        """Configura un canal en el firmware del transceptor serial."""
        if not re.match(r'^[a-fA-F0-9]{0,64}$', psk):
            raise ValueError("Invalid PSK format")
        if not (0 <= index < self._channel_capacity()):
            raise ValueError("Channel index outside firmware capacity")
        if len(name.encode("utf-8")) > MAX_CHANNEL_NAME_BYTES or any(ord(c) < 0x20 for c in name):
            raise ValueError("Invalid channel name")

        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_SAVED", "index": index, "name": name}

        # Convertir PSK a 16 bytes exactos (AES-128) según lo requerido por el SDK de MeshCore
        secret_bytes: bytes | None = None
        if name.startswith("#"):
            secret_bytes = hashlib.sha256(name.encode("utf-8")).digest()[:16]
        elif psk:
            clean_psk = psk.strip()
            if len(clean_psk) == 32 and all(c in "0123456789abcdefABCDEF" for c in clean_psk):
                secret_bytes = bytes.fromhex(clean_psk)
            elif len(clean_psk) == 16:
                secret_bytes = clean_psk.encode("utf-8")
            else:
                secret_bytes = hashlib.sha256(clean_psk.encode("utf-8")).digest()[:16]
        else:
            secret_bytes = b"\x00" * 16

        chan_hash_hex = hashlib.sha256(secret_bytes).hexdigest()[:2]

        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "set_channel"):
                res = await self.run_sdk_command("set_channel", index, name, secret_bytes)
            else:
                return {"status": "ERROR", "reason": "set_channel no soportado"}
            error = self._command_error(res)
            if error:
                return error

            # Actualizar la memoria RAM del SDK de MeshCore para sincronización inmediata
            try:
                reader = getattr(self.mc, "_reader", None) or getattr(self.mc, "reader", None)
                packet_parser = getattr(reader, "packet_parser", None) if reader else None
                if packet_parser and hasattr(packet_parser, "channels"):
                    if isinstance(packet_parser.channels, list):
                        if len(packet_parser.channels) <= index:
                            packet_parser.channels.extend([{} for _ in range(1 + index - len(packet_parser.channels))])
                        packet_parser.channels[index] = {
                            "channel_idx": index,
                            "channel_name": name,
                            "channel_secret": secret_bytes,
                            "channel_hash": chan_hash_hex,
                        }
                if hasattr(self.mc, "channels"):
                    if isinstance(self.mc.channels, dict):
                        self.mc.channels[index] = {
                            "index": index,
                            "name": name,
                            "psk": secret_bytes.hex(),
                            "channel_hash": chan_hash_hex,
                        }
                    elif isinstance(self.mc.channels, list):
                        if len(self.mc.channels) <= index:
                            self.mc.channels.extend([{} for _ in range(1 + index - len(self.mc.channels))])
                        self.mc.channels[index] = {
                            "index": index,
                            "name": name,
                            "psk": secret_bytes.hex(),
                            "channel_hash": chan_hash_hex,
                        }
            except Exception as e:
                logging.debug(f"Error actualizando canal {index} en memoria del SDK: {e}")

            return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo aplicando canal al transceptor serial: {e}")
            return {"status": "ERROR", "reason": str(e), "index": index}

    async def delete_channel(self, index: int) -> dict[str, Any]:
        """Elimina o vacía un canal en el firmware del transceptor serial enviando set_channel con nombre vacío y clave de ceros."""
        if not (1 <= index < self._channel_capacity()):
            raise ValueError("Channel index outside firmware capacity for deletion")

        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_DELETED", "index": index}

        # Firmware acknowledgement precedes committing the cached deletion.
        try:
            if not hasattr(self.mc, "commands") or not hasattr(self.mc.commands, "set_channel"):
                return {"status": "ERROR", "reason": "set_channel no soportado"}
            res = await self.run_sdk_command("set_channel", index, "", b"\x00" * 16)
            error = self._command_error(res)
            if error:
                return error
        except Exception as e:
            logging.warning(f"Fallo eliminando canal {index} en el transceptor serial: {e}")
            return {"status": "ERROR", "reason": str(e), "index": index}

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

        return {"status": "OK", "response": str(res)}

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Añade o actualiza un contacto en la memoria flash del transceptor serial."""
        pubkey = str(contact_data.get("public_key", "")).strip()
        if not re.fullmatch(r"[a-fA-F0-9]{64}", pubkey):
            raise ValueError("CMD_ADD_CONTACT requiere la clave pública completa de 32 bytes")
        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_SAVED", "contact": contact_data}

        try:
            pubkey = str(contact_data.get("public_key", "")).strip()
            name = str(contact_data.get("adv_name", contact_data.get("name", contact_data.get("alias", "")))).strip()
            if not name and pubkey:
                name = f"Node_{pubkey[:6]}"

            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "add_contact"):
                full_pk = pubkey.lower()
                # Normalizar estructura completa requerida por el SDK y firmware
                clean_contact = {
                    "public_key": full_pk,
                    "adv_name": _safe_truncate_utf8(name, 32),
                    "type": int(contact_data.get("type", 1)),
                    "flags": int(contact_data.get("flags", 0)),
                    "out_path": str(contact_data.get("out_path", "")),
                    "out_path_len": int(contact_data.get("out_path_len", -1)) if contact_data.get("out_path_len") is not None else -1,
                    "out_path_hash_mode": int(contact_data.get("out_path_hash_mode", 0)) if contact_data.get("out_path_hash_mode") is not None else 0,
                    "last_advert": int(contact_data.get("last_advert", time.time())),
                    "adv_lat": float(contact_data.get("adv_lat", contact_data.get("latitude", 0.0)) or 0.0),
                    "adv_lon": float(contact_data.get("adv_lon", contact_data.get("longitude", 0.0)) or 0.0),
                }
                res = await self.run_sdk_command("add_contact", clean_contact)
                error = self._command_error(res)
                if error:
                    return error
                if hasattr(self.mc, "_contacts") and isinstance(self.mc._contacts, dict):
                    self.mc._contacts[full_pk] = clean_contact
                return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo registrando contacto en transceptor serial: {e}")
            return {"status": "ERROR", "reason": str(e)}

        return {"status": "ERROR", "reason": "add_contact no soportado"}

    async def remove_contact(self, pubkey: str) -> dict[str, Any]:
        """Elimina un contacto de la memoria flash del transceptor serial."""
        if not self.is_connected or not self.mc:
            return {"status": "LOCAL_REMOVED", "public_key": pubkey}

        resolved_target: str = pubkey
        try:
            target_obj = self._resolve_target(pubkey)
            if isinstance(target_obj, dict):
                resolved_target = str(target_obj.get("public_key") or target_obj.get("key") or pubkey)
            elif hasattr(target_obj, "public_key"):
                resolved_target = str(target_obj.public_key or pubkey)
            elif isinstance(target_obj, str):
                resolved_target = target_obj
        except Exception as e_res:
            logging.debug(f"TargetResolver no pudo resolver contacto para eliminación: {e_res}")

        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "remove_contact"):
                res = await self.run_sdk_command("remove_contact", resolved_target)
                error = self._command_error(res)
                if error:
                    return error
                contacts = getattr(self.mc, "_contacts", None)
                if isinstance(contacts, dict):
                    contacts.pop(resolved_target, None)
                    contacts.pop(pubkey, None)
                return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo eliminando contacto del transceptor serial: {e}")
            return {"status": "ERROR", "reason": str(e)}

        return {"status": "ERROR", "reason": "remove_contact no soportado"}

    async def sync_all_contacts(self) -> list[dict[str, Any]]:
        """Descarga e importa todos los contactos almacenados en el hardware."""
        if not self.is_connected or not self.mc:
            return []

        imported_contacts: list[dict[str, Any]] = []
        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_contacts"):
                try:
                    await self.run_sdk_command("get_contacts", timeout=5)
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
                    flags = None
                    out_path = None
                    out_path_len = None
                    out_path_hash_mode = None
                    if isinstance(c, dict):
                        pk = str(c.get("public_key", c.get("key", ""))).strip()
                        adv_name = str(c.get("adv_name", c.get("name", c.get("alias", f"Node_{pk[:6]}")))).strip()
                        raw_type_val = c.get("type", c.get("adv_type", 1))
                        raw_type = int(raw_type_val) if raw_type_val is not None else 1
                        adv_lat = c.get("adv_lat", c.get("latitude"))
                        adv_lon = c.get("adv_lon", c.get("longitude"))
                        last_advert = c.get("last_advert")
                        flags = c.get("flags")
                        out_path = c.get("out_path")
                        out_path_len = c.get("out_path_len")
                        out_path_hash_mode = c.get("out_path_hash_mode")
                    elif hasattr(c, "public_key") or hasattr(c, "adv_name") or hasattr(c, "name"):
                        pk = str(getattr(c, "public_key", "")).strip()
                        adv_name = str(getattr(c, "adv_name", getattr(c, "name", getattr(c, "alias", f"Node_{pk[:6]}")))).strip()
                        raw_type_val = getattr(c, "adv_type", getattr(c, "type", 1))
                        raw_type = int(raw_type_val) if raw_type_val is not None else 1
                        adv_lat = getattr(c, "adv_lat", getattr(c, "latitude", None))
                        adv_lon = getattr(c, "adv_lon", getattr(c, "longitude", None))
                        last_advert = getattr(c, "last_advert", None)
                        flags = getattr(c, "flags", None)
                        out_path = getattr(c, "out_path", None)
                        out_path_len = getattr(c, "out_path_len", None)
                        out_path_hash_mode = getattr(c, "out_path_hash_mode", None)

                    if pk:
                        norm_pk = pk.strip().lower()
                        my_pk = ""
                        if isinstance(self.self_info, dict):
                            my_pk = str(self.self_info.get("public_key", self.self_info.get("key", ""))).strip().lower()
                        elif self.mc:
                            mc_info = getattr(self.mc, "self_info", None)
                            if isinstance(mc_info, dict):
                                my_pk = str(mc_info.get("public_key", mc_info.get("key", ""))).strip().lower()

                        is_local_contact = bool(
                            my_pk
                            and (
                                norm_pk == my_pk
                                or (len(my_pk) >= 6 and len(norm_pk) >= 6 and (my_pk.startswith(norm_pk) or norm_pk.startswith(my_pk)))
                            )
                        )
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
                            "adv_lat": adv_lat,
                            "adv_lon": adv_lon,
                            "last_advert": last_advert,
                            "flags": flags,
                            "out_path": out_path,
                            "out_path_len": out_path_len,
                            "out_path_hash_mode": out_path_hash_mode,
                            "is_local": is_local_contact,
                            "is_import": True,
                        })
        except Exception as e:
            logging.warning(f"Fallo sincronizando libreta de contactos del nodo: {e}")

        return imported_contacts

    async def share_contact(self, contact_key: str) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "share_contact"):
            try:
                target_key = contact_key
                try:
                    target = self._resolve_target(contact_key)
                    if isinstance(target, dict) and "public_key" in target:
                        target_key = str(target["public_key"])
                    elif hasattr(target, "public_key"):
                        target_key = str(target.public_key)
                    elif isinstance(target, str):
                        target_key = target
                except Exception as ex_res:
                    logging.debug(f"Target resolution for share_contact fallback to input: {ex_res}")

                if not isinstance(target_key, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", target_key):
                    raise ValueError("share_contact requiere una clave pública completa resuelta")

                return await asyncio.wait_for(self.run_sdk_command("share_contact", target_key), timeout=10.0)
            except Exception as e:
                logging.warning(f"Error compartiendo contacto en radio: {e}")
                return None
        return None

    async def export_contact(self, contact_key: str | None = None) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "export_contact"):
            try:
                target_key = None
                if contact_key:
                    target_key = contact_key
                    try:
                        target = self._resolve_target(contact_key)
                        if isinstance(target, dict) and "public_key" in target:
                            target_key = str(target["public_key"])
                        elif hasattr(target, "public_key"):
                            target_key = str(target.public_key)
                        elif isinstance(target, str):
                            target_key = target
                    except Exception as ex_res:
                        logging.debug(f"Target resolution for export_contact fallback to input: {ex_res}")

                    if not isinstance(target_key, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", target_key):
                        raise ValueError("export_contact requiere una clave pública completa resuelta")

                return await asyncio.wait_for(self.run_sdk_command("export_contact", target_key), timeout=10.0)
            except Exception as e:
                logging.warning(f"Error exportando contacto desde radio: {e}")
                return None
        return None

    async def import_contact(self, contact_data: bytes) -> Any:
        if not self.is_connected or not self.mc:
            return None
        if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "import_contact"):
            try:
                return await asyncio.wait_for(self.run_sdk_command("import_contact", contact_data), timeout=10.0)
            except Exception as e:
                logging.warning(f"Error importando contacto a radio: {e}")
                return None
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
            except Exception as ex:
                logging.debug(f"Error resolviendo nombre de contacto para prefijo {prefix_str}: {ex}")
        return prefix_str

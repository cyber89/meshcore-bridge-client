"""firmware_cli.py: Gestor de CLI y preferencias de firmware Companion de MeshCore."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from meshcore import EventType

from src.protocol_types import redact_command_str
from src.serial.companion_protocol import (
    _FIRMWARE_READ_COMMANDS,
    MAX_WIFI_PASSWORD_BYTES,
    MAX_WIFI_SSID_BYTES,
    ensure_meshcore_log_redaction,
)

logger = logging.getLogger(__name__)


class FirmwareCliHandler:
    """Encapsula el ciclo de vida, transacciones y preferencias del CLI de firmware."""

    def __init__(
        self,
        mc_provider: Callable[[], Any],
        is_connected_provider: Callable[[], bool],
        port_provider: Callable[[], str],
        timeout_provider: Callable[[], float],
        run_sdk_command: Callable[..., Awaitable[Any]],
    ) -> None:
        self.mc_provider = mc_provider
        self.is_connected_provider = is_connected_provider
        self.port_provider = port_provider
        self.timeout_provider = timeout_provider
        self.run_sdk_command = run_sdk_command

        self.device_info: dict[str, Any] = {}
        self.firmware_mc: Any = None
        self.firmware_identity: str | None = None
        self.generation: int = 0
        self.is_uncertain: bool = False
        self.lease: ContextVar[int | None] = ContextVar("firmware_cli_lease", default=None)

        try:
            self.sdk_version: str | None = version("meshcore")
        except PackageNotFoundError:
            self.sdk_version = None

    def reset_firmware_observations(self, *, new_session: bool = False) -> None:
        """Reinicia el estado de observaciones de firmware e incrementa la generación."""
        self.generation += 1
        self.device_info = {}
        self.firmware_mc = self.mc_provider()
        if new_session:
            self.is_uncertain = False
            self.firmware_identity = None

    def update_device_info(self, ver: Any, model: Any, protocol: Any) -> None:
        """Registra la información de versión y modelo observada."""
        current_mc = self.mc_provider()
        if self.firmware_mc is not current_mc:
            self.reset_firmware_observations(new_session=True)
        self.device_info = {
            "ver": ver,
            "model": model,
        }
        if protocol is not None:
            self.device_info["fw ver"] = protocol

    def update_identity(self, identity: str) -> None:
        """Actualiza la identidad observada; si cambia en la misma conexión, rota generación."""
        current_mc = self.mc_provider()
        if self.firmware_mc is not current_mc:
            self.reset_firmware_observations(new_session=True)
        if self.firmware_identity is not None and self.firmware_identity != identity:
            self.reset_firmware_observations()
        self.firmware_identity = identity

    @property
    def firmware_capabilities(self) -> dict[str, Any]:
        """Retorna las capacidades de firmware observadas en la sesión actual."""
        current_mc = self.mc_provider()
        if self.firmware_mc is not current_mc:
            self.reset_firmware_observations(new_session=True)
        is_connected = bool(self.is_connected_provider() and current_mc is not None)
        observed = self.device_info if is_connected else {}
        protocol = observed.get("fw ver")
        commands = getattr(current_mc, "commands", None)
        if not is_connected:
            state, reason = "unknown", "disconnected"
        elif self.is_uncertain:
            state, reason = "absent", "cli_timeout_reconnect_required"
        elif protocol is None:
            state, reason = "unknown", "awaiting_device_info"
        elif protocol < 14:
            state, reason = "absent", "protocol_unsupported"
        elif not callable(getattr(commands, "run_cli_command", None)):
            state, reason = "absent", "sdk_unsupported"
        else:
            state, reason = "present", "available"

        port = self.port_provider()
        return {
            "state": state,
            "reason": reason,
            "connected": is_connected,
            "companion_protocol": protocol,
            "firmware_version": observed.get("ver"),
            "sdk_version": self.sdk_version,
            "model": observed.get("model"),
            "transport": "tcp" if port.startswith("tcp://") else "serial",
            "safe_commands": list(_FIRMWARE_READ_COMMANDS) if state == "present" else [],
            "writable_preferences": ["cad", "wifi"] if state == "present" else [],
            "session_generation": self.generation,
        }

    def require_firmware_cli(self, generation: int) -> None:
        """Valida que la sesión de CLI esté disponible y coincida la generación."""
        capability = self.firmware_capabilities
        if not capability["connected"]:
            raise ConnectionError("disconnected")
        if generation != self.generation:
            raise ConnectionError("connection_changed")
        if capability["state"] != "present":
            raise NotImplementedError(capability["reason"])

    async def call_with_firmware_lease(self, call: Callable[[], Awaitable[Any]]) -> Any:
        """Chequea el lease de la tarea y envenena tiempos de espera antes de desbloquear el envío."""
        generation = self.lease.get()
        if generation is None:
            return await call()
        self.require_firmware_cli(generation)
        try:
            async with asyncio.timeout(self.timeout_provider()):
                response = await call()
        except (TimeoutError, asyncio.CancelledError):
            if generation == self.generation:
                self.is_uncertain = True
            raise
        except Exception:
            if generation == self.generation:
                self.is_uncertain = True
            raise ConnectionError("firmware_cli_failed") from None
        self.require_firmware_cli(generation)
        payload = getattr(response, "payload", None)
        if response is None or (
            getattr(response, "type", None) == getattr(EventType, "ERROR", None)
            and isinstance(payload, dict)
            and payload.get("reason") in ("timeout", "no_event_received")
        ):
            self.is_uncertain = True
            raise TimeoutError("firmware_cli_timeout")
        return response

    async def run_firmware_cli_command(self, command: str) -> dict[str, str]:
        """Ejecuta un comando raw mediante el CLI de firmware usando el lease de sesión."""
        ensure_meshcore_log_redaction()
        _ = self.firmware_capabilities
        generation = self.generation
        self.require_firmware_cli(generation)
        token = self.lease.set(generation)
        try:
            response = await self.run_sdk_command("run_cli_command", command)
            self.require_firmware_cli(generation)
        except TimeoutError:
            raise TimeoutError("firmware_cli_timeout") from None
        except (ConnectionError, NotImplementedError, asyncio.CancelledError):
            raise
        except Exception:
            raise RuntimeError("firmware_cli_failed") from None
        finally:
            self.lease.reset(token)
        payload = getattr(response, "payload", None)
        if getattr(response, "type", None) != getattr(EventType, "CLI_REPLY", None):
            raise RuntimeError("firmware_cli_rejected")
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("firmware_cli_invalid_reply")
        if (
            text.lstrip()
            .removeprefix(">")
            .lstrip()
            .lower()
            .startswith(("error", "err", "unknown command"))
        ):
            raise RuntimeError("firmware_cli_rejected")
        return {"command": redact_command_str(command), "text": text}

    async def run_firmware_cli(self, command: str) -> dict[str, str]:
        """Ejecuta un getter local verificado de firmware."""
        if type(command) is not str or command not in _FIRMWARE_READ_COMMANDS:
            raise ValueError("invalid_firmware_command")
        return await self.run_firmware_cli_command(command)

    async def set_firmware_preference(self, preference: str, value: bool) -> dict[str, str | bool]:
        """Acepta la preferencia CAD local sin certificar el driver físico."""
        if type(preference) is not str or preference != "cad" or type(value) is not bool:
            raise ValueError("invalid_firmware_preference")
        reply = await self.run_firmware_cli_command("set cad on" if value else "set cad off")
        if reply["text"].strip() != "OK":
            raise RuntimeError("firmware_preference_unconfirmed")
        return {
            "preference": preference,
            "value": value,
            "acknowledged": True,
            "hardware_verified": False,
        }

    @staticmethod
    def _validate_wifi_text_field(value: Any, *, max_bytes: int, trim_edges: bool) -> str:
        if type(value) is not str or not value or not value.strip():
            raise ValueError("invalid_firmware_wifi")
        if trim_edges and value != value.strip():
            raise ValueError("invalid_firmware_wifi")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
            raise ValueError("invalid_firmware_wifi")
        encoded = value.encode("utf-8")
        if not (1 <= len(encoded) <= max_bytes):
            raise ValueError("invalid_firmware_wifi")
        return value

    async def set_firmware_wifi(
        self,
        *,
        ssid: Any = None,
        password: Any = None,
        enabled: Any = None,
        clear: Any = False,
    ) -> dict[str, Any]:
        """Escribe preferencias WiFi Companion sin registrar credenciales sensibles."""
        if clear is None:
            clear = False
        if type(clear) is not bool:
            raise ValueError("invalid_firmware_wifi")
        if clear:
            if ssid is not None or password is not None or enabled is not None:
                raise ValueError("invalid_firmware_wifi")
            try:
                reply = await self.run_firmware_cli_command("wifi.clear")
            except RuntimeError as err:
                if str(err) == "firmware_cli_rejected":
                    raise RuntimeError("firmware_wifi_rejected") from None
                raise
            normalized = reply["text"].lstrip().removeprefix(">").strip().lower()
            if not normalized.startswith("wifi config cleared"):
                if "error" in normalized or "err" in normalized:
                    raise RuntimeError("firmware_wifi_rejected")
                raise RuntimeError("firmware_wifi_unconfirmed")
            return {
                "ssid": None,
                "password_updated": False,
                "enabled": False,
                "cleared": True,
                "reboot_required": True,
                "acknowledged": True,
                "hardware_verified": False,
            }

        if ssid is None and password is None and enabled is None:
            raise ValueError("invalid_firmware_wifi")
        clean_ssid = (
            self._validate_wifi_text_field(ssid, max_bytes=MAX_WIFI_SSID_BYTES, trim_edges=True)
            if ssid is not None
            else None
        )
        clean_pwd = (
            self._validate_wifi_text_field(
                password, max_bytes=MAX_WIFI_PASSWORD_BYTES, trim_edges=False
            )
            if password is not None
            else None
        )
        if enabled is not None and type(enabled) is not bool:
            raise ValueError("invalid_firmware_wifi")

        try:
            if clean_ssid is not None:
                ssid_reply = await self.run_firmware_cli_command(f"set wifi.ssid {clean_ssid}")
                ssid_norm = ssid_reply["text"].lstrip().removeprefix(">").strip().lower()
                if not ssid_norm.startswith("wifi.ssid is now "):
                    if "error" in ssid_norm or "err" in ssid_norm:
                        raise RuntimeError("firmware_wifi_rejected")
                    raise RuntimeError("firmware_wifi_unconfirmed")
            if clean_pwd is not None:
                pwd_reply = await self.run_firmware_cli_command(f"set wifi.pwd {clean_pwd}")
                pwd_norm = pwd_reply["text"].lstrip().removeprefix(">").strip().lower()
                if not pwd_norm.startswith("wifi.pwd updated"):
                    if "error" in pwd_norm or "err" in pwd_norm:
                        raise RuntimeError("firmware_wifi_rejected")
                    raise RuntimeError("firmware_wifi_unconfirmed")
            if enabled is not None:
                flag_str = "on" if enabled else "off"
                en_reply = await self.run_firmware_cli_command(f"set wifi.enabled {flag_str}")
                en_norm = en_reply["text"].lstrip().removeprefix(">").strip().lower()
                if not (
                    en_norm.startswith(f"wifi.enabled is now {flag_str}")
                    or en_norm.startswith(f"wifi.enabled is now {'1' if enabled else '0'}")
                ):
                    if "error" in en_norm or "err" in en_norm:
                        raise RuntimeError("firmware_wifi_rejected")
                    raise RuntimeError("firmware_wifi_unconfirmed")
        except RuntimeError as err:
            if str(err) == "firmware_cli_rejected":
                raise RuntimeError("firmware_wifi_rejected") from None
            raise

        return {
            "ssid": clean_ssid,
            "password_updated": clean_pwd is not None,
            "enabled": enabled,
            "cleared": False,
            "reboot_required": True,
            "acknowledged": True,
            "hardware_verified": False,
        }

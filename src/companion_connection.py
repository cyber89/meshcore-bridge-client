"""Pure validation and private UI projection for the outgoing Companion link."""

from __future__ import annotations

import ipaddress
import re
import unicodedata


def normalize_companion_port(value: object) -> str:
    """Validate an override without resolving hosts, opening ports or logging input.

    An empty string inherits the environment. IPv6 is excluded because the
    current SDK adapter splits its TCP authority at the first colon.
    """
    if not isinstance(value, str) or any(
        unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in value
    ):
        raise ValueError("Invalid Companion endpoint")
    port = value.strip()
    if not port:
        return ""
    if port.startswith("tcp://"):
        authority = port[6:]
        if authority.count(":") != 1:
            raise ValueError("Companion TCP requires an IPv4 or DNS host and explicit port")
        host, number = authority.split(":")
        if not re.fullmatch(r"[0-9]{1,5}", number) or not 1 <= int(number) <= 65535:
            raise ValueError("Companion TCP requires an explicit port from 1 to 65535")
        hostname = host.removesuffix(".")
        if (
            not hostname
            or len(hostname) > 253
            or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in hostname.split(".")
            )
        ):
            raise ValueError("Invalid Companion TCP host")
        if re.fullmatch(r"[0-9.]+", hostname):
            try:
                ipaddress.IPv4Address(hostname)
            except ipaddress.AddressValueError:
                raise ValueError("Invalid Companion IPv4 host") from None
        return port
    if port.upper() in {"AUTO", "DETECT", "DEFAULT"}:
        return port.upper()
    if re.fullmatch(r"COM[1-9][0-9]*", port, flags=re.IGNORECASE):
        return port.upper()
    if any(char in port for char in ("@", "?", "#")) or "://" in port:
        raise ValueError("Invalid Companion serial path")
    if (port.startswith("/") and len(port) > 1 and ":" not in port) or (
        re.match(r"^[A-Za-z]:[\\/]", port) and ":" not in port[2:]
    ):
        return port
    raise ValueError("Companion serial endpoint must be AUTO, a COM port or an absolute path")


def safe_companion_port(value: str) -> str:
    """Hide legacy unsupported endpoints instead of reflecting possible credentials."""
    try:
        return normalize_companion_port(value)
    except ValueError:
        # Legacy environment values may contain unsupported schemes or secrets.
        return ""


def companion_connection_snapshot(
    configured_port: str,
    environment_port: str,
    active_port: str,
    startup_port: str | None = None,
) -> dict[str, str | bool]:
    """Separate next-start configuration from the adapter's resolved active port."""
    effective = configured_port or environment_port
    return {
        "configured_port": safe_companion_port(configured_port),
        "effective_port": safe_companion_port(effective),
        "active_port": safe_companion_port(active_port),
        "restart_required": effective
        != (startup_port if startup_port is not None else active_port),
    }

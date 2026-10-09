"""Transport-neutral access policy copied from the current native web server.

This module imports neither the application nor a web framework. It deliberately
retains legacy credential precedence, broad Origin matching and response headers;
extracting those rules does not harden them or prove ASGI transport equivalence.
Environment settings are read for each access decision, never cached at import.
"""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs

HTTP_MAX_HEADER_BYTES = 65536
HTTP_MAX_BODY_BYTES = 1024 * 1024
HTTP_READ_TIMEOUT_S = 10.0
WS_MAX_CONNECTIONS = 32
WS_MAX_PAYLOAD_BYTES = 1024 * 1024

DEFAULT_ALLOWED_ORIGINS = "http://localhost:8080,http://127.0.0.1:8080"
MAP_TILE_PREFIX = "/api/map/tiles/"
PROTECTED_PREFIXES = (
    "/api/node/reboot",
    "/api/config/reboot",
    "/api/admin",
    "/api/tx",
    "/api/repeater",
    "/api/config/radio",
    "/api/node/config/radio",
)
SENSITIVE_READ_PATHS = (
    "/api/logs/download",
    "/api/logs/raw",
    "/api/system/logs",
    "/api/diagnostics/export",
    "/api/diagnostics/report",
    "/api/diagnostics/report.md",
    "/api/channels/export",
    "/api/packets",
    "/api/packets/export",
)
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob: https: https://*.tile.openstreetmap.org "
    "https://*.basemaps.cartocdn.com https://unpkg.com; "
    "connect-src 'self' ws: wss: https:; "
    "frame-ancestors 'none'"
)

RawHeader = tuple[bytes, bytes]
RouteKind = Literal["api", "tile", "preflight", "static", "websocket"]
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AccessDecision:
    """Access outcome without retaining credentials or query strings for logging.

    A successful decision does not certify method support, payload validation or
    WebSocket acceptance. The caller owns request parsing, tile dispatch and any
    atomic reservation of WebSocket capacity.
    """

    route_kind: RouteKind
    cors_origin: str
    auth_required: bool
    auth_valid: bool
    rejection_status: int | None
    log_path: str


def headers_to_legacy_dict(raw_headers: Iterable[RawHeader]) -> dict[str, str]:
    """Match the native parser's UTF-8/ignore, trimming and last-value-wins rules.

    ASGI transports have already parsed their HTTP headers. This conversion does
    not provide the native parser's byte budget or incomplete-header timeout.
    """
    headers: dict[str, str] = {}
    for name, value in raw_headers:
        headers[name.decode("utf-8", errors="ignore").strip().lower()] = value.decode(
            "utf-8", errors="ignore"
        ).strip()
    return headers


def safe_log_path(raw_path: str) -> str:
    """Exclude query credentials from access-log paths without exposing header keys."""
    return raw_path.partition("?")[0]


def extract_api_key(raw_path: str, headers: Mapping[str, str]) -> str:
    """Use a nonempty X-Api-Key before exactly one strictly decoded query value.

    Headers must already be lowercase. Bearer credentials are not implemented;
    a wrong nonempty header never falls back to a correct query credential.
    """
    header_key = headers.get("x-api-key", "")
    if header_key:
        return header_key
    try:
        params = parse_qs(raw_path.partition("?")[2], keep_blank_values=True, errors="strict")
    except ValueError:
        return ""
    query_keys = params.get("api_key", [])
    return query_keys[0] if len(query_keys) == 1 else ""


def has_valid_api_key(raw_path: str, headers: Mapping[str, str], expected_key: str) -> bool:
    """Compare UTF-8 credential bytes in constant time as in the native server."""
    try:
        return hmac.compare_digest(
            extract_api_key(raw_path, headers).encode("utf-8"), expected_key.encode("utf-8")
        )
    except UnicodeEncodeError:
        return False


def requires_api_auth(method: str, raw_path: str) -> bool:
    """Reproduce the guard alone, before aliases and outside dispatch exceptions.

    The caller must handle OPTIONS and tile requests first. Prefix comparisons
    intentionally lack segment boundaries, matching the current implementation.
    """
    clean_path = safe_log_path(raw_path).rstrip("/") or "/"
    if any(clean_path.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return not (clean_path.startswith("/api/nodes") and method == "GET")
    if clean_path in SENSITIVE_READ_PATHS:
        return True
    return method in ("POST", "PUT", "DELETE", "PATCH") and clean_path.startswith("/api/")


def is_origin_allowed(req_origin: str, host_header: str, allowed_origins: Sequence[str]) -> bool:
    """Preserve broad legacy matching, including its private-IP and IPv6 parser limits."""
    if not req_origin or "*" in allowed_origins or req_origin in allowed_origins:
        return True
    if host_header:
        origin_clean = req_origin.replace("http://", "").replace("https://", "").rstrip("/")
        if origin_clean.lower() == host_header.lower():
            return True
    origin_host = req_origin.split("://")[-1].split(":")[0].split("/")[0].rstrip(".").lower()
    # This tuple is retained exactly. The parser above cannot recognize IPv6
    # ::1; an exact allowlist or Host match can still admit that Origin.
    if origin_host in ("localhost", "127.0.0.1", "::1"):
        return True
    if origin_host.startswith(("192.168.", "10.", "127.")):
        parts = origin_host.split(".")
        if all(part.isdigit() for part in parts) and len(parts) == 4:
            return True
    if origin_host.startswith("172."):
        parts = origin_host.split(".")
        if len(parts) == 4 and all(part.isdigit() for part in parts):
            if 16 <= int(parts[1]) <= 31:
                return True
    return False


def calculate_cors_origin(headers: Mapping[str, str]) -> str:
    """Return accepted Origin verbatim, otherwise omit REST ACAO without denying REST."""
    allowed_origins = [
        origin.strip()
        for origin in os.getenv("BRIDGE_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
        if origin.strip()
    ]
    req_origin = headers.get("origin", "")
    if is_origin_allowed(req_origin, headers.get("host", ""), allowed_origins):
        return req_origin
    return ""


def evaluate_http_access(method: str, raw_path: str, headers: Mapping[str, str]) -> AccessDecision:
    """Apply normal HTTP dispatch ordering after the caller's parsing/perimeter checks.

    A WebSocket upgrade must use evaluate_websocket_access before this function;
    in the native dispatcher upgrade precedes even OPTIONS. Methods must already
    be uppercase, as supplied by the native request parser.
    """
    cors_origin = calculate_cors_origin(headers)
    log_path = safe_log_path(raw_path)
    if method == "OPTIONS":
        return AccessDecision("preflight", cors_origin, False, True, None, log_path)
    if raw_path.startswith(MAP_TILE_PREFIX):
        return AccessDecision(
            "tile", cors_origin, False, True, None if method == "GET" else 405, log_path
        )
    if not raw_path.startswith("/api/"):
        return AccessDecision("static", cors_origin, False, True, None, log_path)
    auth_required = requires_api_auth(method, raw_path)
    expected_key = os.getenv("BRIDGE_API_KEY", "")
    if auth_required and not expected_key:
        logger.warning("BRIDGE_API_KEY no configurada, omitiendo autenticación (modo desarrollo)")
    auth_valid = (
        not auth_required or not expected_key or has_valid_api_key(raw_path, headers, expected_key)
    )
    return AccessDecision(
        "api", cors_origin, auth_required, auth_valid, None if auth_valid else 401, log_path
    )


def evaluate_websocket_access(
    raw_path: str, headers: Mapping[str, str], active_connections: int
) -> AccessDecision:
    """Preserve Origin -> capacity -> key denial order without accepting a socket.

    This check does not reserve capacity. The transport must prevent concurrent
    handshakes from bypassing its reservation if atomic admission is introduced.
    """
    cors_origin = calculate_cors_origin(headers)
    log_path = safe_log_path(raw_path)
    if headers.get("origin", "") and not cors_origin:
        return AccessDecision("websocket", cors_origin, False, True, 403, log_path)
    if active_connections >= WS_MAX_CONNECTIONS:
        return AccessDecision("websocket", cors_origin, False, True, 429, log_path)
    expected_key = os.getenv("BRIDGE_API_KEY", "")
    auth_required = bool(expected_key)
    auth_valid = not auth_required or has_valid_api_key(raw_path, headers, expected_key)
    return AccessDecision(
        "websocket", cors_origin, auth_required, auth_valid, None if auth_valid else 401, log_path
    )


def response_headers(
    *,
    content_type: str | None = None,
    cors_origin: str = "",
    content_length: int | None = None,
    extra_headers: Sequence[RawHeader] = (),
) -> list[RawHeader]:
    """Build native normal-response headers in ASGI's lowercase byte-list format.

    Omit content_length only when the caller already retains its representation
    length. Neither this helper nor HEAD changes the computed length. Header
    values use UTF-8 as the native server's response serializer does.
    """
    headers: list[RawHeader] = list(extra_headers)
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode("utf-8")))
    headers.extend(
        (
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"connection", b"close"),
        )
    )
    if content_type:
        headers.insert(0, (b"content-type", content_type.encode("utf-8")))
        if "text/html" in content_type:
            headers.append((b"content-security-policy", CONTENT_SECURITY_POLICY.encode("utf-8")))
    if cors_origin:
        headers.extend(
            (
                (b"access-control-allow-origin", cors_origin.encode("utf-8")),
                (b"access-control-allow-methods", b"GET, POST, OPTIONS, DELETE"),
                (b"access-control-allow-headers", b"Content-Type, X-Api-Key"),
            )
        )
    return headers


def preflight_headers(cors_origin: str) -> list[RawHeader]:
    """Preserve preflight's explicit exception to normal security-header assembly."""
    headers: list[RawHeader] = []
    if cors_origin:
        headers.append((b"access-control-allow-origin", cors_origin.encode("utf-8")))
    headers.extend(
        (
            (b"access-control-allow-methods", b"GET, POST, OPTIONS, DELETE"),
            (b"access-control-allow-headers", b"Content-Type, Authorization, X-Api-Key"),
            (b"access-control-max-age", b"86400"),
            (b"connection", b"close"),
        )
    )
    return headers

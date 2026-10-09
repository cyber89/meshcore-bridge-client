"""Inactive ASGI ingress guard preserving the native web server's access policy.

This guard belongs outside the application's ServerErrorMiddleware so generated
500 responses also receive the normal security/CORS headers. It supplies no REST
or WebSocket routes. Byte/header parsing, HTTP head deadlines and WS framing stay
in the selected transport; a middleware alone cannot enforce those controls.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, cast

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.web.access_policy import (
    HTTP_MAX_BODY_BYTES,
    HTTP_READ_TIMEOUT_S,
    WS_MAX_CONNECTIONS,
    calculate_cors_origin,
    evaluate_http_access,
    evaluate_websocket_access,
    headers_to_legacy_dict,
    preflight_headers,
    response_headers,
    safe_log_path,
)
from src.web.security_inspector import (
    HttpAccessEvent,
    SecurityTrafficInspector,
    SuspiciousTrafficEvent,
)

# Protocol-owned extension: mark the request disconnected before aborting its
# transport, avoiding Uvicorn's fallback 500 when no response has been started.
# Do not import asgi_http merely to share this name and pull h11 into the guard.
HTTP_ABORT_EXTENSION = "meshcore.http.abort"
WS_ABORT_EXTENSION = "meshcore.websocket.abort"
BODY_BYTES_STATE = "meshcore_body_bytes"
BODY_JSON_STATE = "meshcore_body_json"

_NORMAL_HEADER_NAMES = frozenset(
    {
        b"x-content-type-options",
        b"x-frame-options",
        b"referrer-policy",
        b"connection",
        b"content-security-policy",
        b"access-control-allow-origin",
        b"access-control-allow-methods",
        b"access-control-allow-headers",
    }
)


class HttpAbortUnavailable(RuntimeError):
    """The caller omitted the transport hook required for a silent body-read close."""


@dataclass(frozen=True, slots=True)
class _BufferedRequest:
    raw: bytes
    parsed: dict[str, Any]


def _raw_request_target(scope: Scope) -> str:
    """Retain percent encoding and query for auth, never for audit logging."""
    raw_path = scope.get("raw_path")
    if isinstance(raw_path, bytes):
        path = raw_path.decode("utf-8", errors="ignore")
    else:
        path = str(scope.get("path", "/"))
    query = scope.get("query_string", b"")
    if isinstance(query, bytes) and query:
        return path + "?" + query.decode("utf-8", errors="ignore")
    return path


def _peer_ip(scope: Scope) -> str:
    peer = scope.get("client")
    if isinstance(peer, (tuple, list)) and peer:
        address = str(peer[0])
        return address[7:] if address.startswith("::ffff:") else address
    return "unknown"


def _parse_json_object(raw: bytes) -> dict[str, Any]:
    parsed: Any = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON request must be an object")
    return cast(dict[str, Any], parsed)


class BridgeSecurityMiddleware:
    """Bound request accumulation and reserve this one-loop instance's WS capacity.

    HTTP read timeout/incomplete body aborts without inventing a 408 response.
    In-memory ASGI callers must provide HTTP_ABORT_EXTENSION to exercise that
    contract; without it a controlled, credential-free exception is raised.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._reserved_websockets = 0

    @property
    def active_websocket_reservations(self) -> int:
        return self._reserved_websockets

    @staticmethod
    def _log_rejection(
        *,
        peer: str,
        path: str,
        source: str,
        anomaly: str,
        detail: str,
    ) -> None:
        # No request query, header values, body, or exception text enter this log.
        try:
            SecurityTrafficInspector.log_suspicious_traffic(
                SuspiciousTrafficEvent(
                    client_ip=peer,
                    source_type=source,
                    endpoint=safe_log_path(path),
                    anomaly_type=anomaly,
                    detail=detail,
                    user_agent="",
                )
            )
        except Exception:
            # Failure of an audit sink must never bypass a rejection.
            pass

    def _inspect(self, scope: Scope, target: str, headers: dict[str, str]) -> bool:
        peer = _peer_ip(scope)
        try:
            suspicious, anomaly, _ = SecurityTrafficInspector.inspect_http_request(
                method=str(scope.get("method", "GET")).upper(),
                path=safe_log_path(target),
                headers=headers,
                body_dict=None,
                client_ip=peer,
            )
        except Exception:
            suspicious, anomaly = True, "INSPECTION_FAILED"
        if suspicious:
            self._log_rejection(
                peer=peer,
                path=target,
                source="WEBSOCKET" if scope["type"] == "websocket" else "HTTP",
                anomaly=anomaly,
                detail="Request rejected by the ingress inspector",
            )
        return not suspicious

    @staticmethod
    def _abort_http(scope: Scope) -> None:
        abort = scope.get("extensions", {}).get(HTTP_ABORT_EXTENSION)
        if not callable(abort):
            raise HttpAbortUnavailable("HTTP read close requires the protocol abort hook")
        abort()

    @staticmethod
    async def _reply_http(
        scope: Scope,
        send: Send,
        status: int,
        body: bytes,
        *,
        content_type: str | None = None,
        cors_origin: str = "",
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        header_list = (
            headers
            if headers is not None
            else response_headers(
                content_type=content_type,
                content_length=len(body),
                cors_origin=cors_origin,
            )
        )
        await send({"type": "http.response.start", "status": status, "headers": header_list})
        await send(
            {
                "type": "http.response.body",
                "body": b"" if scope.get("method") == "HEAD" else body,
                "more_body": False,
            }
        )

    async def _read_body(
        self,
        scope: Scope,
        headers: dict[str, str],
        receive: Receive,
        send: Send,
    ) -> _BufferedRequest | None:
        if headers.get("transfer-encoding"):
            await self._reply_http(scope, send, 400, b"Unsupported Transfer-Encoding")
            return None
        expected: int | None = None
        if "content-length" in headers:
            try:
                expected = int(headers["content-length"])
                if expected < 0:
                    raise ValueError("Negative Content-Length")
            except (ValueError, TypeError):
                await self._reply_http(scope, send, 400, b"Invalid Content-Length")
                return None
        if expected is not None and expected > HTTP_MAX_BODY_BYTES:
            await self._reject_large_body(scope, send)
            return None

        loop = asyncio.get_running_loop()
        deadline = loop.time() + HTTP_READ_TIMEOUT_S
        body = bytearray()
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                self._abort_http(scope)
                return None
            try:
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except asyncio.TimeoutError:
                self._abort_http(scope)
                return None
            if message["type"] == "http.disconnect":
                self._abort_http(scope)
                return None
            if message["type"] != "http.request":
                self._abort_http(scope)
                return None
            chunk: bytes = message.get("body", b"")
            # Check before extending; neither declared length nor segmented input
            # can make our accumulator exceed the existing one-MiB byte budget.
            if len(chunk) > HTTP_MAX_BODY_BYTES - len(body):
                await self._reject_large_body(scope, send)
                return None
            body.extend(chunk)
            if expected is not None and len(body) > expected:
                await self._reply_http(scope, send, 400, b"Invalid Content-Length")
                return None
            if not message.get("more_body", False):
                break
        if expected is not None and len(body) != expected:
            self._abort_http(scope)
            return None
        if expected is None or expected == 0:
            # The native parser treats missing/zero Content-Length as {}. Any
            # extra ASGI input is bounded above but is not promoted into JSON.
            return _BufferedRequest(b"", {})
        raw = bytes(body)
        try:
            # Decode and parse bounded JSON off the event loop. No disk or radio
            # access occurs; cancellation still propagates to the request task.
            parsed = await asyncio.to_thread(_parse_json_object, raw)
        except Exception:
            await self._reply_http(
                scope,
                send,
                400,
                b'{"error": "Bad Request", "detail": "Malformed JSON payload"}',
                content_type="application/json",
                cors_origin=calculate_cors_origin(headers),
            )
            return None
        return _BufferedRequest(raw, parsed)

    async def _reject_large_body(self, scope: Scope, send: Send) -> None:
        self._log_rejection(
            peer=_peer_ip(scope),
            path=_raw_request_target(scope),
            source="HTTP",
            anomaly="PAYLOAD_SOBREDIMENSIONADO",
            detail="HTTP request body exceeds the existing one-MiB limit",
        )
        # The native 413 is a bare response, an explicit exception to normal
        # header assembly. Backend framing of this empty response needs wire QA.
        await self._reply_http(
            scope, send, 413, b"", headers=[(b"connection", b"close")]
        )

    @staticmethod
    def _normal_response_headers(
        original: list[tuple[bytes, bytes]], cors_origin: str
    ) -> list[tuple[bytes, bytes]]:
        content_type: str | None = None
        extras: list[tuple[bytes, bytes]] = []
        for name, value in original:
            lowered = name.lower()
            if lowered == b"content-type":
                content_type = value.decode("utf-8", errors="ignore")
            elif lowered not in _NORMAL_HEADER_NAMES:
                extras.append((lowered, value))
        return response_headers(
            content_type=content_type, cors_origin=cors_origin, extra_headers=extras
        )

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        target = _raw_request_target(scope)
        headers = headers_to_legacy_dict(scope.get("headers", ()))
        started_at = time.perf_counter()
        if not self._inspect(scope, target, headers):
            await self._reply_http(scope, send, 403, b"403 Forbidden - Security Violation")
            return
        buffered = await self._read_body(scope, headers, receive, send)
        if buffered is None:
            return
        state = scope.setdefault("state", {})
        state[BODY_BYTES_STATE] = buffered.raw
        state[BODY_JSON_STATE] = buffered.parsed
        decision = evaluate_http_access(str(scope["method"]).upper(), target, headers)
        if decision.route_kind == "preflight":
            await self._reply_http(
                scope, send, 204, b"", headers=preflight_headers(decision.cors_origin)
            )
            return
        if decision.rejection_status == 405:
            await self._reply_http(
                scope,
                send,
                405,
                b'{"error": "Method Not Allowed", "detail": "Only GET is supported for map tiles"}',
                content_type="application/json",
                cors_origin=decision.cors_origin,
            )
            return
        if decision.rejection_status == 401:
            self._log_rejection(
                peer=_peer_ip(scope),
                path=target,
                source="API-AUTH",
                anomaly="AUTENTICACION_API_FALLIDA",
                detail="Protected endpoint rejected an absent or invalid API key",
            )
            await self._reply_http(
                scope,
                send,
                401,
                b'{"error": "Unauthorized"}',
                content_type="application/json",
                cors_origin=decision.cors_origin,
            )
            return

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": buffered.raw, "more_body": False}
            return await receive()

        async def guarded_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = self._normal_response_headers(
                    message.get("headers", []), decision.cors_origin
                )
                try:
                    SecurityTrafficInspector.log_http_access(
                        HttpAccessEvent(
                            client_ip=_peer_ip(scope),
                            method=str(scope["method"]),
                            path=decision.log_path,
                            status_code=int(message["status"]),
                            duration_ms=(time.perf_counter() - started_at) * 1000,
                            user_agent="",
                        )
                    )
                except Exception:
                    pass
            elif message["type"] == "http.response.body" and scope["method"] == "HEAD":
                message = dict(message)
                message["body"] = b""
            await send(message)

        await self.app(scope, replay_receive, guarded_send)

    @staticmethod
    async def _deny_websocket(scope: Scope, send: Send, status: int, body: bytes) -> None:
        if "websocket.http.response" not in scope.get("extensions", {}):
            # ASGI without denial extension can only close before accept; that
            # maps to 403 rather than reproducing legacy 401/429. Never accept a
            # denied socket to manufacture a later close code.
            await send({"type": "websocket.close", "code": 1008})
            return
        await send(
            {
                "type": "websocket.http.response.start",
                "status": status,
                "headers": response_headers(content_length=len(body)),
            }
        )
        await send({"type": "websocket.http.response.body", "body": body, "more_body": False})

    async def _handle_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        target = _raw_request_target(scope)
        headers = headers_to_legacy_dict(scope.get("headers", ()))
        if not self._inspect(scope, target, headers):
            await self._deny_websocket(scope, send, 403, b"403 Forbidden - Security Violation")
            return
        cors_origin = calculate_cors_origin(headers)
        if headers.get("origin", "") and not cors_origin:
            self._log_rejection(
                peer=_peer_ip(scope),
                path=target,
                source="WEBSOCKET",
                anomaly="WS_ORIGIN_RECHAZADO",
                detail="WebSocket Origin is not allowed by the current policy",
            )
            await self._deny_websocket(scope, send, 403, b"")
            return
        if self._reserved_websockets >= WS_MAX_CONNECTIONS:
            self._log_rejection(
                peer=_peer_ip(scope),
                path=target,
                source="WEBSOCKET",
                anomaly="CONEXIONES_WS_AGOTADAS",
                detail="The existing 32-connection WebSocket limit is reached",
            )
            await self._deny_websocket(
                scope, send, 429, b"429 Too Many Requests - WS Limit Reached"
            )
            return
        # One embedded event loop, no await between comparison and increment.
        # Reserve before auth/handshake and release even if either send or app
        # raises or the request task is cancelled.
        previous_count = self._reserved_websockets
        self._reserved_websockets += 1
        try:
            decision = evaluate_websocket_access(target, headers, previous_count)
            if decision.rejection_status is not None:
                status = decision.rejection_status
                body = {
                    403: b"",
                    429: b"429 Too Many Requests - WS Limit Reached",
                    401: b"401 Unauthorized",
                }[status]
                anomaly = {
                    403: "WS_ORIGIN_RECHAZADO",
                    429: "CONEXIONES_WS_AGOTADAS",
                    401: "AUTENTICACION_WS_FALLIDA",
                }[status]
                self._log_rejection(
                    peer=_peer_ip(scope),
                    path=target,
                    source="WEBSOCKET",
                    anomaly=anomaly,
                    detail="WebSocket rejected by the current access policy",
                )
                await self._deny_websocket(scope, send, status, body)
                return
            await self.app(scope, receive, send)
        finally:
            self._reserved_websockets -= 1

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # The native parser uppercases methods. The HTTP transport must do
            # that before feeding h11 as well, so HEAD framing remains coherent.
            # This copy also preserves the contract for in-memory ASGI callers.
            scope = dict(scope)
            scope["method"] = str(scope["method"]).upper()
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
        else:
            await self.app(scope, receive, send)

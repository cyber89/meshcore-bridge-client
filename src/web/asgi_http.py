"""HTTP admission guards for the evaluated Uvicorn 0.54.0 H11 backend.

The raw head guard runs before H11 parsing. Body admission belongs to the ASGI
middleware. HTTP connections serve one request, as the current bridge does;
WebSocket upgrades transfer the transport to Uvicorn's WebSocket protocol.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import h11
from uvicorn import Config
from uvicorn._types import ASGIReceiveCallable, ASGISendCallable, Scope
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.server import ServerState

from src.web.access_policy import HTTP_MAX_HEADER_BYTES, HTTP_READ_TIMEOUT_S, response_headers
from src.web.asgi_logging import SafeProtocolLogger

HTTP_ABORT_EXTENSION = "meshcore.http.abort"
_INVALID_HEAD_BODY = b"Invalid or incomplete HTTP headers"
_INVALID_HEAD_RESPONSE = (
    b"HTTP/1.1 400 Bad Request\r\n"
    + b"".join(
        name + b": " + value + b"\r\n"
        for name, value in response_headers(content_length=len(_INVALID_HEAD_BODY))
    )
    + b"\r\n"
    + _INVALID_HEAD_BODY
)


class BridgeH11Protocol(H11Protocol):
    """Bound raw request headers without treating incoming body bytes as headers."""

    def __init__(
        self,
        config: Config,
        server_state: ServerState,
        app_state: dict[str, Any],
        _loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__(config, server_state, app_state, _loop)
        # H11 passes this logger into RequestResponseCycle before scheduling
        # run_asgi(), whose exception logging can otherwise reveal body values.
        self.logger = cast(logging.Logger, SafeProtocolLogger(self.logger, {}))
        # H11Protocol checks logger handlers rather than Config.access_log.
        # Global bridge logging must not turn URLs/credentials into access logs.
        self.access_log = False
        self._head_buffer = bytearray()
        self._head_scan_offset = 0
        self._head_line_start = 0
        self._head_complete = False
        self._head_rejected = False
        self._head_timer: asyncio.TimerHandle | None = None
        wrapped_app = self.app

        async def app_with_abort(
            scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
        ) -> None:
            if scope["type"] == "http":
                raw_ext = scope.get("extensions")
                extensions: dict[str, Any] = dict(raw_ext) if isinstance(raw_ext, dict) else {}
                extensions[HTTP_ABORT_EXTENSION] = self._abort_request
                scope["extensions"] = extensions
            await wrapped_app(scope, receive, send)

        self.app = app_with_abort

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        super().connection_made(cast(asyncio.Transport, transport))
        # One deadline for the entire head, never extended by individual chunks.
        self._head_timer = self.loop.call_later(HTTP_READ_TIMEOUT_S, self._head_timeout)

    def data_received(self, data: bytes) -> None:
        if self._head_rejected or self.transport.is_closing():
            return
        if self._head_complete:
            super().data_received(data)
            return

        # Reserve only the terminating empty CRLF line beyond the legacy limit.
        # A coalesced large body remains outside this bounded admission buffer.
        capacity = HTTP_MAX_HEADER_BYTES + 2 - len(self._head_buffer)
        taken = min(capacity, len(data))
        self._head_buffer.extend(data[:taken])
        while True:
            newline = self._head_buffer.find(b"\n", self._head_scan_offset)
            if newline < 0:
                self._head_scan_offset = len(self._head_buffer)
                break
            line_end = newline + 1
            line_size = line_end - self._head_line_start
            empty_line = line_size == 1 or (
                line_size == 2 and self._head_buffer[self._head_line_start] == 13
            )
            if empty_line:
                # The current server counts the request line and header lines,
                # including their newlines, but excludes this final empty line.
                if self._head_line_start > HTTP_MAX_HEADER_BYTES:
                    self.send_400_response("")
                    return
                self._head_complete = True
                self._cancel_head_timer()
                admitted = bytes(self._head_buffer[:line_end])
                buffered_tail = bytes(self._head_buffer[line_end:])
                self._head_buffer.clear()
                # The native parser uppercases methods. Normalize only the ASCII
                # method token, after counting original bytes and before H11
                # records their_method (also required for HEAD body framing).
                request_line_end = admitted.find(b"\n")
                method_end = admitted.find(b" ", 0, request_line_end)
                if method_end > 0:
                    admitted = admitted[:method_end].upper() + admitted[method_end:]
                super().data_received(admitted)
                self._forward_admitted_tail(buffered_tail)
                self._forward_admitted_tail(data[taken:])
                return
            self._head_line_start = line_end
            self._head_scan_offset = line_end
            if line_end > HTTP_MAX_HEADER_BYTES:
                self.send_400_response("")
                return

        # A single trailing CR at a line boundary may begin the final empty line.
        possible_final_cr = (
            len(self._head_buffer) == self._head_line_start + 1
            and self._head_buffer[-1:] == b"\r"
        )
        if len(self._head_buffer) > HTTP_MAX_HEADER_BYTES and not possible_final_cr:
            self.send_400_response("")

    def handle_events(self) -> None:
        super().handle_events()
        if self.cycle is not None:
            if not isinstance(self.cycle.logger, SafeProtocolLogger):
                self.cycle.logger = cast(
                    logging.Logger, SafeProtocolLogger(self.cycle.logger, {})
                )
            # Set before the scheduled ASGI app runs. H11 holds later pipelined
            # requests at PAUSED, and the first completed response closes the
            # transport instead of start_next_cycle() dispatching another one.
            self.cycle.keep_alive = False

    def handle_websocket_upgrade(self, event: h11.Request) -> None:
        self._cancel_head_timer()
        super().handle_websocket_upgrade(event)

    def send_400_response(self, msg: str) -> None:
        """Reject without reflecting request data or depending on H11 send state."""
        if self._head_rejected:
            return
        self._head_rejected = True
        self._cancel_head_timer()
        self._head_buffer.clear()
        self._unset_keepalive_if_required()
        if self.cycle is not None:
            self.cycle.disconnected = True
            self.cycle.message_event.set()
            if self.cycle.response_started:
                self.transport.abort()
                return
        if not self.transport.is_closing():
            self.transport.write(_INVALID_HEAD_RESPONSE)
            self.transport.close()

    def eof_received(self) -> None:
        if not self._head_complete:
            if self._head_buffer:
                self.send_400_response("")
            else:
                self._cancel_head_timer()
                self.transport.close()
            return
        super().eof_received()

    def connection_lost(self, exc: Exception | None) -> None:
        self._cancel_head_timer()
        self._head_buffer.clear()
        super().connection_lost(exc)

    def shutdown(self) -> None:
        self._cancel_head_timer()
        super().shutdown()

    def _head_timeout(self) -> None:
        self._head_timer = None
        if not self._head_complete:
            self.send_400_response("")

    def _forward_admitted_tail(self, data: bytes) -> None:
        if not data or self.transport.is_closing():
            return
        protocol = self.transport.get_protocol()
        if protocol is self:
            super().data_received(data)
        else:
            # Upgrade hands off the transport while parsing the head. Coalesced
            # WebSocket frame bytes must reach that new protocol, never H11.
            cast(asyncio.Protocol, protocol).data_received(data)

    def _cancel_head_timer(self) -> None:
        if self._head_timer is not None:
            self._head_timer.cancel()
            self._head_timer = None

    def _abort_request(self) -> None:
        """Close incomplete bodies without inventing an HTTP 408 or ASGI 500."""
        self._cancel_head_timer()
        if self.cycle is not None:
            self.cycle.disconnected = True
            self.cycle.message_event.set()
        self.transport.abort()

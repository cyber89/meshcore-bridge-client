"""Lightweight response compression with a measured half-core duty budget.

Static assets use build-time gzip sidecars instead. Dynamic compression has one
admitted worker, uses zlib level 1, and paces CPU time outside the event loop.
The budget describes the worker's average duty cycle, not an instantaneous OS
CPU quota or a limit on the bridge process.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
import zlib

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_COMPRESSIBLE_PATHS = frozenset(
    (
        "/api/analytics",
        "/api/metrics/analytics",
        "/api/lqi",
        "/api/rf/heatmap",
        "/api/rf/noise",
        "/api/airtime/stats",
    )
)
_MIN_BODY_BYTES = 1024
_MAX_BODY_BYTES = 1024 * 1024
_CHUNK_BYTES = 32 * 1024


def accepts_gzip(accept_encoding: str) -> bool:
    """Honor explicit gzip refusal before considering a wildcard encoding."""
    wildcard = 0.0
    gzip_quality: float | None = None
    for part in accept_encoding.split(","):
        values = [value.strip().lower() for value in part.split(";")]
        if values[0] not in ("gzip", "*"):
            continue
        quality = 1.0
        for value in values[1:]:
            if value.startswith("q="):
                try:
                    quality = float(value[2:])
                except ValueError:
                    quality = 0.0
        if not math.isfinite(quality) or not 0.0 <= quality <= 1.0:
            quality = 0.0
        if values[0] == "gzip":
            gzip_quality = quality
        else:
            wildcard = quality
    return (gzip_quality if gzip_quality is not None else wildcard) > 0.0


def _vary_encoding(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    values: list[bytes] = []
    result = []
    for name, value in headers:
        if name.lower() == b"vary":
            values.extend(item.strip() for item in value.split(b","))
        else:
            result.append((name, value))
    if b"*" not in values and not any(value.lower() == b"accept-encoding" for value in values):
        values.append(b"Accept-Encoding")
    result.append((b"vary", b", ".join(values)))
    return result


class _PacedGzip:
    """Admit one off-loop job; concurrent requests retain their original body."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: set[asyncio.Task[bytes | None]] = set()

    def _finished(self, task: asyncio.Task[bytes | None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _compress(self, body: bytes) -> bytes | None:
        try:
            wall_start = time.monotonic()
            cpu_start = time.thread_time()
            compressor = zlib.compressobj(level=1, wbits=31)
            output = bytearray()
            for offset in range(0, len(body), _CHUNK_BYTES):
                output.extend(compressor.compress(body[offset : offset + _CHUNK_BYTES]))
                if offset + _CHUNK_BYTES >= len(body):
                    output.extend(compressor.flush())
                # Each zlib chunk can burst briefly. Before continuing/returning,
                # charge the measured CPU time and rest until duty is <= 50%.
                cpu_elapsed = time.thread_time() - cpu_start
                rest = cpu_elapsed / 0.5 - (time.monotonic() - wall_start)
                if rest > 0:
                    time.sleep(rest)
            compressed = bytes(output)
            # Include final materialization in the same measured CPU budget.
            rest = (time.thread_time() - cpu_start) / 0.5 - (time.monotonic() - wall_start)
            if rest > 0:
                time.sleep(rest)
            return compressed if len(compressed) < len(body) else None
        finally:
            # Cancellation of to_thread's waiter cannot release admission while
            # its underlying worker still consumes CPU.
            self._lock.release()

    async def compress(self, body: bytes) -> bytes | None:
        if not self._lock.acquire(blocking=False):
            return None
        task = asyncio.create_task(
            asyncio.to_thread(self._compress, body), name="MeshCoreWebCompression"
        )
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        try:
            # Shield preserves the admitted worker even if its request is
            # cancelled before the default executor starts running it.
            return await asyncio.shield(task)
        except Exception:
            # Compressor failures must not turn successful metrics into 500s.
            return None


class BridgeCompressionMiddleware:
    """Compress bounded, single-message metrics responses without buffering streams.

    The allowlist excludes credentials, channel exports, chat, logs and arbitrary
    configuration responses. WebSockets, tiles, HEAD, errors, partial responses
    and already encoded data pass through unchanged.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._gzip = _PacedGzip()

    def owned_tasks(self) -> set[asyncio.Task[bytes | None]]:
        """Expose bounded workers for shutdown waiting, without cancelling their threads."""
        return set(self._gzip._tasks)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "GET"
            or scope.get("path") not in _COMPRESSIBLE_PATHS
        ):
            await self.app(scope, receive, send)
            return
        request_headers = {name.lower(): value for name, value in scope.get("headers", [])}
        encoding = request_headers.get(b"accept-encoding", b"").decode("latin-1")
        start: Message | None = None
        can_compress = accepts_gzip(encoding) and b"range" not in request_headers

        async def compressed_send(message: Message) -> None:
            nonlocal start, can_compress
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {name.lower() for name, _ in headers}
                content_type = next(
                    (value for name, value in headers if name.lower() == b"content-type"),
                    b"",
                )
                can_compress = (
                    can_compress
                    and message["status"] == 200
                    and content_type.split(b";")[0].strip().lower() == b"application/json"
                    and not names.intersection(
                        (b"content-encoding", b"content-range", b"set-cookie", b"etag")
                    )
                    and not any(
                        name.lower() == b"cache-control" and b"no-transform" in value.lower()
                        for name, value in headers
                    )
                )
                message = dict(message)
                message["headers"] = _vary_encoding(headers)
                if can_compress:
                    start = message
                else:
                    await send(message)
                return
            if message["type"] == "http.response.body" and start is not None:
                body = message.get("body", b"")
                compressed = None
                if (
                    not message.get("more_body", False)
                    and _MIN_BODY_BYTES <= len(body) <= _MAX_BODY_BYTES
                ):
                    compressed = await self._gzip.compress(body)
                if compressed is not None:
                    start["headers"] = [
                        (name, value)
                        for name, value in start["headers"]
                        if name.lower() not in (b"content-length", b"content-md5", b"digest")
                    ] + [
                        (b"content-encoding", b"gzip"),
                        (b"content-length", str(len(compressed)).encode("ascii")),
                    ]
                    message = {**message, "body": compressed}
                await send(start)
                start = None
            await send(message)

        await self.app(scope, receive, compressed_send)

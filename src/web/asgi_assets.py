"""Native static/SPA and public tile semantics for the inactive ASGI candidate.

The router owns the borrowed tile service. This adapter neither opens nor closes
its storage. Filesystem work and compression run outside the event loop; this
does not establish timing, memory use, or runtime parity with the native server.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import mimetypes
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from fastapi import FastAPI
from starlette.datastructures import URLPath
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Match, NoMatchFound
from starlette.types import Receive, Scope, Send

from src.web.asgi_security import _raw_request_target

if TYPE_CHECKING:
    from src.web.api_router import WebAPIRouter


_SPA_PATHS = frozenset(
    ("", "chat", "map", "nodes", "contacts", "settings", "telemetry", "logs", "analytics")
)
_RESERVED_DOCS_PATHS = frozenset(("/docs", "/redoc", "/openapi.json"))
_TEXT_SUFFIXES = frozenset((".html", ".css", ".js", ".json", ".svg", ".txt", ".map", ".md"))
_INITIALIZING = b"<h1>MeshCore Web Client</h1><p>Archivos estaticos inicializandose...</p>"


@dataclass(frozen=True, slots=True)
class _CachedAsset:
    mtime: float
    raw: bytes
    compressed: bytes | None
    etag: str
    content_type: str


@dataclass(frozen=True, slots=True)
class _AssetResult:
    status: int
    body: bytes
    headers: dict[str, str]


def _accepts_gzip(accept_encoding: str) -> bool:
    """Retain native substring, wildcard and q-value selection exactly."""
    if not accept_encoding or "gzip" not in accept_encoding:
        return False
    for part in accept_encoding.split(","):
        subparts = [value.strip() for value in part.split(";")]
        if subparts[0].lower() in ("gzip", "*"):
            quality = 1.0
            for value in subparts[1:]:
                if value.lower().startswith("q="):
                    try:
                        quality = float(value[2:].strip())
                    except ValueError:
                        quality = 0.0
            if quality > 0.0:
                return True
    return False


def _traversal_attempt(path: str) -> bool:
    """Apply the native double-decoding guard without selecting decoded files."""
    normalized = path.replace("\\", "/")
    lower = normalized.lower()
    decoded = unquote(unquote(lower))
    return (
        ".." in normalized.split("/")
        or ".." in decoded.split("/")
        or "%2e" in lower
        or "%2f" in lower
        or "%00" in lower
        or "%c0%ae" in lower
        or "..../" in normalized
        or "\x00" in path
    )


def _response(result: _AssetResult) -> Response:
    # Explicit MIME preserves native charset on binary static assets and its
    # absence on errors. Native also emits Content-Length: 0 for 304 responses.
    headers = {**result.headers, "Content-Length": str(len(result.body))}
    return Response(content=result.body, status_code=result.status, headers=headers)


class AssetsAdapter:
    """Borrow maps and keep only an adapter-local, mtime-based static cache."""

    def __init__(self, router: WebAPIRouter, static_dir: Path | None = None) -> None:
        self.tile_service = router.map_tile_service
        # Do not stat/resolve here: application construction performs no file I/O.
        self.static_dir = (
            static_dir if static_dir is not None else Path(__file__).parent / "static"
        )
        self._cache: dict[str, _CachedAsset] = {}
        self._cache_lock = threading.RLock()

    async def dispatch(self, request: Request) -> Response:
        target = _raw_request_target(request.scope)
        path = target.partition("?")[0]
        if path.startswith("/api/map/tiles/"):
            return await self._tile(request.method, target)
        if path.rstrip("/") in _RESERVED_DOCS_PATHS:
            # Phase 5 must install authenticated documentation explicitly. Do not
            # serve a SPA success that could be mistaken for an enabled docs UI.
            return _response(_AssetResult(404, b"404 Not Found", {}))
        # Native assets accept arbitrary methods. OPTIONS is handled by the
        # perimeter before this point; HEAD body suppression is also perimeter.
        headers = {
            key.decode("utf-8", errors="ignore").strip().lower(): value.decode(
                "utf-8", errors="ignore"
            ).strip()
            for key, value in request.scope.get("headers", [])
        }
        result = await asyncio.to_thread(
            self._static, path, headers.get("if-none-match", ""), headers.get("accept-encoding", "")
        )
        return _response(result)

    async def _tile(self, method: str, target: str) -> Response:
        if method != "GET":
            # Normally rejected by the perimeter; retain the same direct-route
            # guard without inventing automatic GET-as-HEAD behavior.
            return _response(
                _AssetResult(
                    405,
                    b'{"error": "Method Not Allowed", '
                    b'"detail": "Only GET is supported for map tiles"}',
                    {"Content-Type": "application/json"},
                )
            )
        subpath = target[len("/api/map/tiles/"):].split("?")[0].strip("/")
        parts = subpath.split("/")
        if len(parts) >= 3:
            try:
                z = int(parts[0])
                x = int(parts[1])
                y = int(parts[2].split(".")[0])
                if 0 <= z <= 22 and 0 <= x < (1 << z) and 0 <= y < (1 << z):
                    status, body, mime = await asyncio.to_thread(
                        self.tile_service.get_tile, z, x, y
                    )
                    if status == 200 and body:
                        return _response(
                            _AssetResult(
                                200,
                                body,
                                {"Content-Type": mime, "Cache-Control": "public, max-age=86400"},
                            )
                        )
            except (ValueError, TypeError, OverflowError):
                pass
        return _response(_AssetResult(404, b"", {"Content-Type": "image/png"}))

    @staticmethod
    def _contained(target: Path, root: Path) -> bool:
        """Check canonical ancestry on Windows and POSIX without string prefixes."""
        try:
            target.resolve().relative_to(root)
            return True
        except (ValueError, OSError, RuntimeError):
            return False

    def _static(self, path: str, if_none_match: str, accept_encoding: str) -> _AssetResult:
        # The worker owns all resolution/stat/read/compression operations. The
        # lock protects this local cache across to_thread calls, never the loop.
        with self._cache_lock:
            clean_path = path.strip("/")
            if _traversal_attempt(clean_path):
                return _AssetResult(403, b"", {})
            try:
                root = self.static_dir.resolve()
                navigation = clean_path in _SPA_PATHS
                target = root / ("index.html" if navigation else clean_path)
                if not self._contained(target, root):
                    return _AssetResult(403, b"", {})
                # Native navigation/fallback keeps the index.html name for
                # MIME/cache selection, including a symlink within the root.
                if not navigation:
                    target = target.resolve()
                if not target.is_file():
                    if target.suffix:
                        return _AssetResult(404, b"404 Not Found", {})
                    target = root / "index.html"
                    # Recheck fallback too: index.html can itself be a symlink.
                    if not self._contained(target, root):
                        return _AssetResult(403, b"", {})
                if not target.is_file():
                    return _AssetResult(
                        200, _INITIALIZING, {"Content-Type": "text/html; charset=utf-8"}
                    )
                mtime = target.stat().st_mtime
            except (OSError, ValueError, RuntimeError):
                return _AssetResult(404, b"404 Not Found", {})
            file_key = str(target)
            cached = self._cache.get(file_key)
            if cached is None or cached.mtime != mtime:
                try:
                    raw = target.read_bytes()
                except OSError:
                    return _AssetResult(500, b"Error reading static file", {})
                content_type, _ = mimetypes.guess_type(str(target))
                content_type = content_type or (
                    "text/html" if target.suffix == ".html" else "application/octet-stream"
                )
                textual = target.suffix in _TEXT_SUFFIXES or content_type.startswith(
                    ("text/", "application/javascript", "application/json", "image/svg+xml")
                )
                compressed = (
                    gzip.compress(raw, compresslevel=6) if textual and len(raw) > 256 else None
                )
                cached = _CachedAsset(
                    mtime,
                    raw,
                    compressed,
                    f'"{hashlib.sha256(raw).hexdigest()[:16]}"',
                    content_type,
                )
                self._cache[file_key] = cached
            headers = {
                "Content-Type": (
                    cached.content_type
                    if "charset" in cached.content_type
                    else cached.content_type + "; charset=utf-8"
                ),
                "Cache-Control": (
                    "no-cache, no-store, must-revalidate"
                    if target.suffix == ".html"
                    else "public, max-age=300"
                ),
                "ETag": cached.etag,
                "Vary": "Accept-Encoding",
            }
            client_etag = if_none_match.strip()
            if client_etag and (
                client_etag == cached.etag
                or client_etag == "W/" + cached.etag
                or cached.etag in client_etag
            ):
                return _AssetResult(304, b"", headers)
            compressed = cached.compressed
            if (
                _accepts_gzip(accept_encoding)
                and compressed is not None
                and len(compressed) < len(cached.raw)
            ):
                headers["Content-Encoding"] = "gzip"
                return _AssetResult(200, compressed, headers)
            return _AssetResult(200, cached.raw, headers)


class _AssetsRoute(BaseRoute):
    def __init__(self, adapter: AssetsAdapter, *, tiles: bool) -> None:
        self.adapter = adapter
        self.tiles = tiles

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] != "http":
            return Match.NONE, {}
        path = _raw_request_target(scope).partition("?")[0]
        is_tile = path.startswith("/api/map/tiles/")
        if (self.tiles and is_tile) or (not self.tiles and not path.startswith("/api/")):
            return Match.FULL, {"route": self}
        return Match.NONE, {}

    def url_path_for(self, name: str, /, **path_params: Any) -> URLPath:
        raise NoMatchFound(name, path_params)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = await self.adapter.dispatch(Request(scope, receive=receive))
        await response(scope, receive, send)


def install_asset_routes(
    app: FastAPI, router: WebAPIRouter, static_dir: Path | None = None
) -> AssetsAdapter:
    """Append tiles and a non-API catchall after REST registration exactly once."""
    if getattr(app.state, "assets_adapter", None) is not None:
        raise RuntimeError("Assets are already registered on this application")
    adapter = AssetsAdapter(router, static_dir)
    app.router.routes.append(_AssetsRoute(adapter, tiles=True))
    app.router.routes.append(_AssetsRoute(adapter, tiles=False))
    app.state.assets_adapter = adapter
    return adapter

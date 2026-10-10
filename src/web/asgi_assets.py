"""Compatibility static/SPA and public tile semantics for the ASGI application.

The router owns the borrowed tile service. This adapter neither opens nor closes
its storage. Filesystem work runs outside the event loop. Minification and gzip
are build-time artifacts selected only when their manifest digests match.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
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

from src.web.asgi_compression import accepts_gzip
from src.web.asgi_security import _raw_request_target

if TYPE_CHECKING:
    from src.web.api_router import WebAPIRouter


_SPA_PATHS = frozenset(
    ("", "chat", "map", "nodes", "contacts", "settings", "telemetry", "logs", "analytics")
)
_RESERVED_DOCS_PATHS = frozenset(("/docs", "/redoc", "/openapi.json"))
_INITIALIZING = b"<h1>MeshCore Web Client</h1><p>Archivos estaticos inicializandose...</p>"

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")


@dataclass(frozen=True, slots=True)
class _CachedAsset:
    signature: tuple[int, int]
    gzip_signature: tuple[int, int] | None
    raw: bytes
    compressed: bytes | None
    digest: str
    compressed_digest: str | None
    content_type: str


@dataclass(frozen=True, slots=True)
class _AssetResult:
    status: int
    body: bytes
    headers: dict[str, str]


_accepts_gzip = accepts_gzip


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
        self.static_dir = static_dir if static_dir is not None else Path(__file__).parent / "static"
        self._cache: dict[str, _CachedAsset] = {}
        self._cache_lock = threading.RLock()
        self._manifest_signature: tuple[str, int, int] | None = None
        self._manifest: dict[str, dict[str, str]] = {}

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
        subpath = target[len("/api/map/tiles/") :].split("?")[0].strip("/")
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

    def _load_manifest(self, root: Path) -> dict[str, dict[str, str]]:
        """Read trusted build metadata off-loop, invalidating it when replaced."""
        manifest_path = root / "asset-manifest.json"
        if not self._contained(manifest_path, root):
            return {}
        try:
            stat = manifest_path.stat()
            signature = (str(root), stat.st_mtime_ns, stat.st_size)
            if signature != self._manifest_signature:
                self._manifest = {}
                self._manifest_signature = signature
                if stat.st_size > 1024 * 1024:
                    return {}
                data = json.loads(manifest_path.read_bytes())
                if not isinstance(data, dict) or data.get("version") != 1:
                    return {}
                assets = data.get("assets")
                if not isinstance(assets, dict):
                    return {}
                for source, entry in assets.items():
                    if isinstance(source, str) and isinstance(entry, dict):
                        fields = ("file", "source_sha256", "sha256", "gzip_sha256")
                        if all(isinstance(entry.get(field), str) for field in fields):
                            self._manifest[source] = {field: entry[field] for field in fields}
            return self._manifest
        except (OSError, ValueError, RuntimeError):
            self._manifest_signature = None
            self._manifest = {}
            return {}

    def _asset(self, target: Path, root: Path) -> _CachedAsset:
        """Cache raw bytes and gzip sidecars; manifest digests establish freshness."""
        stat = target.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        gzip_path = target.with_name(target.name + ".gz")
        gzip_signature = None
        if self._contained(gzip_path, root):
            try:
                gzip_stat = gzip_path.stat()
                if gzip_path.is_file():
                    gzip_signature = (gzip_stat.st_mtime_ns, gzip_stat.st_size)
            except OSError:
                pass
        cached = self._cache.get(str(target))
        if (
            cached is None
            or cached.signature != signature
            or cached.gzip_signature != gzip_signature
        ):
            raw = target.read_bytes()
            compressed = None
            if gzip_signature is not None:
                try:
                    sidecar = gzip_path.read_bytes()
                    if sidecar.startswith(b"\x1f\x8b") and len(sidecar) < len(raw):
                        compressed = sidecar
                except OSError:
                    pass
            content_type, _ = mimetypes.guess_type(str(target))
            cached = _CachedAsset(
                signature,
                gzip_signature,
                raw,
                compressed,
                hashlib.sha256(raw).hexdigest(),
                hashlib.sha256(compressed).hexdigest() if compressed is not None else None,
                content_type or "application/octet-stream",
            )
            self._cache[str(target)] = cached
        return cached

    def _select_asset(self, target: Path, root: Path) -> tuple[Path, _CachedAsset, bool]:
        original = self._asset(target, root)
        entry = self._load_manifest(root).get(target.relative_to(root).as_posix())
        if entry is None:
            # Sidecars without a validated build receipt are not selected: their
            # modification time alone cannot establish that they match the file.
            return target, original, False
        mapped_name = entry["file"]
        mapped = root / mapped_name
        if (
            original.digest != entry["source_sha256"]
            or Path(mapped_name).is_absolute()
            or _traversal_attempt(mapped_name)
            or not self._contained(mapped, root)
            or mapped.suffix != target.suffix
        ):
            return target, original, False
        try:
            selected = original if mapped == target else self._asset(mapped, root)
        except OSError:
            return target, original, False
        if selected.digest != entry["sha256"]:
            return target, original, False
        return mapped, selected, selected.compressed_digest == entry["gzip_sha256"]

    def _static(self, path: str, if_none_match: str, accept_encoding: str) -> _AssetResult:
        # The worker owns all resolution/stat/read/hash operations. The
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
            except (OSError, ValueError, RuntimeError):
                return _AssetResult(404, b"404 Not Found", {})
            try:
                target, cached, gzip_verified = self._select_asset(target, root)
            except (OSError, ValueError, RuntimeError):
                return _AssetResult(500, b"Error reading static file", {})
            compressed = cached.compressed
            use_gzip = _accepts_gzip(accept_encoding) and gzip_verified and compressed is not None
            digest = (cached.compressed_digest or cached.digest) if use_gzip else cached.digest
            etag = '"' + digest[:16] + '"'
            headers = {
                "Content-Type": (
                    cached.content_type
                    if "charset" in cached.content_type
                    else (
                        cached.content_type + "; charset=utf-8"
                        if cached.content_type.startswith(
                            ("text/", "application/javascript", "application/json")
                        )
                        else cached.content_type
                    )
                ),
                "Cache-Control": (
                    "no-cache, no-store, must-revalidate"
                    if target.suffix == ".html"
                    else "public, max-age=300"
                ),
                "ETag": etag,
                "Vary": "Accept-Encoding",
            }
            if use_gzip:
                headers["Content-Encoding"] = "gzip"
            client_etags = [value.strip().removeprefix("W/") for value in if_none_match.split(",")]
            if "*" in client_etags or etag in client_etags:
                return _AssetResult(304, b"", headers)
            if use_gzip and compressed is not None:
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

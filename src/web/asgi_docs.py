"""Local, read-only documentation routes for the ASGI application.

The public login shell and two fixed assets contain no API catalog or schema.
When configured, documentation requires X-Api-Key, never a URL credential or
new session. Schema construction is lazy and detached from operational state.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.datastructures import URLPath
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Match, NoMatchFound
from starlette.types import Receive, Scope, Send

from src.web.access_policy import has_valid_api_key, headers_to_legacy_dict
from src.web.asgi_errors import legacy_json_response
from src.web.asgi_security import DOC_RESPONSE_STATE, _raw_request_target

_DOC_ROOTS = ("/docs", "/redoc", "/openapi.json")
_PUBLIC_ASSETS = {
    "/docs/assets/docs.js": ("docs.js", "text/javascript"),
    "/docs/assets/docs.css": ("docs.css", "text/css"),
}
_NO_STORE = {"Cache-Control": "no-store", "Vary": "X-Api-Key"}


def _reserved(path: str) -> bool:
    return any(path == root or path.startswith(root + "/") for root in _DOC_ROOTS)


class DocumentationAdapter:
    """Own only a static schema cache; borrow no radio, router or configuration."""

    def __init__(self, schema_factory: Callable[[], dict[str, Any]]) -> None:
        self._schema_factory = schema_factory
        self._directory = Path(__file__).parent / "docs_ui"
        self._schema_lock = threading.RLock()
        self._schema: dict[str, Any] | None = None
        self._schema_bytes: bytes | None = None

    def openapi_schema(self) -> dict[str, Any]:
        """FastAPI-compatible lazy accessor; HTTP calls invoke it in a worker."""
        with self._schema_lock:
            if self._schema is None:
                self._schema = self._schema_factory()
            return self._schema

    def _json_schema(self) -> bytes:
        with self._schema_lock:
            if self._schema_bytes is None:
                self._schema_bytes = json.dumps(
                    self.openapi_schema(), ensure_ascii=True, indent=2
                ).encode("utf-8")
            return self._schema_bytes

    @staticmethod
    def _authorized(request: Request) -> bool:
        expected = os.getenv("BRIDGE_API_KEY", "")
        if not expected:
            return True
        headers = headers_to_legacy_dict(request.scope.get("headers", ()))
        # Removing query before the shared comparator makes this boundary
        # header-only while retaining constant-time UTF-8 comparison semantics.
        return has_valid_api_key("/docs", headers, expected)

    def _asset(self, filename: str) -> bytes:
        # Callers select from fixed names below. No target-derived filesystem
        # path, resolve/stat at construction, CDN or framework bundle is used.
        return (self._directory / filename).read_bytes()

    async def dispatch(self, request: Request) -> Response:
        path = _raw_request_target(request.scope).partition("?")[0].rstrip("/")
        request.scope.setdefault("state", {})[DOC_RESPONSE_STATE] = True
        if request.method.upper() not in ("GET", "HEAD"):
            response = legacy_json_response(405, {"error": "Method Not Allowed"})
            response.headers.update(_NO_STORE)
            return response
        public_asset = _PUBLIC_ASSETS.get(path)
        if public_asset is not None:
            filename, media_type = public_asset
            content = await asyncio.to_thread(self._asset, filename)
            return Response(content, media_type=media_type, headers=_NO_STORE)
        if path in ("/docs", "/redoc"):
            # A normal navigation cannot attach X-Api-Key. A 401 login shell
            # renders the local credential form without disclosing the schema;
            # its JS makes the authenticated schema request explicitly.
            status = 200 if self._authorized(request) else 401
            content = await asyncio.to_thread(self._asset, "index.html")
            return Response(
                content, status_code=status, media_type="text/html", headers=_NO_STORE
            )
        if not self._authorized(request):
            response = legacy_json_response(401, {"error": "Unauthorized"})
            response.headers.update(_NO_STORE)
            return response
        if path == "/openapi.json":
            content = await asyncio.to_thread(self._json_schema)
            return Response(content, media_type="application/json", headers=_NO_STORE)
        return Response(b"404 Not Found", status_code=404, headers=_NO_STORE)


class _DocumentationRoute(BaseRoute):
    def __init__(self, adapter: DocumentationAdapter) -> None:
        self.adapter = adapter

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] == "http":
            path = _raw_request_target(scope).partition("?")[0].rstrip("/")
            if _reserved(path):
                return Match.FULL, {"route": self}
        return Match.NONE, {}

    def url_path_for(self, name: str, /, **path_params: Any) -> URLPath:
        raise NoMatchFound(name, path_params)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = await self.adapter.dispatch(Request(scope, receive=receive))
        await response(scope, receive, send)


def install_documentation_routes(
    app: FastAPI, schema_factory: Callable[[], dict[str, Any]]
) -> DocumentationAdapter:
    """Install before the static catchall, with no services or schema built here."""
    if getattr(app.state, "documentation_adapter", None) is not None:
        raise RuntimeError("Documentation is already registered on this application")
    adapter = DocumentationAdapter(schema_factory)
    app.router.routes.append(_DocumentationRoute(adapter))
    app.state.documentation_adapter = adapter
    # Built-in public schema/Swagger/ReDoc routes remain disabled. The callable
    # supplies the curated contract even to internal FastAPI consumers.
    app.openapi = adapter.openapi_schema  # type: ignore[method-assign]
    return adapter

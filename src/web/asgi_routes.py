"""REST transport registration for the FastAPI application.

Routes describe six migration batches while borrowing one existing dispatcher.
That dispatcher still owns query merging, aliases, controller validation and
business effects. Tiles, WebSocket, static assets and documentation use separate adapters. Registration and listener readiness do not establish runtime parity.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from starlette.datastructures import URLPath
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Match, NoMatchFound
from starlette.types import Receive, Scope, Send

from src.web.api_error_policy import redact_returned_error
from src.web.api_router import ROUTE_ALIASES
from src.web.asgi_errors import legacy_json_response
from src.web.asgi_openapi import operation_metadata
from src.web.asgi_route_catalog import ROUTE_BATCHES, ROUTE_CONTRACTS, RouteContract
from src.web.asgi_security import BODY_JSON_STATE, _raw_request_target

if TYPE_CHECKING:
    from src.web.api_router import WebAPIRouter


class _RawTargetAPIRoute(APIRoute):
    """Match the native encoded path without modifying the request's scope.

    FastAPI 0.143 included routers call this override with an effective route
    context in scope. A shallow copy preserves that context while replacing only
    the path used for matching. Re-audit this seam on a framework upgrade.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] != "http":
            return super().matches(scope)
        legacy_scope: Scope = {**scope, "path": _raw_request_target(scope).partition("?")[0]}
        return super().matches(legacy_scope)


class _RestAdapter:
    """Borrow services and invoke the original dispatcher exactly once per call."""

    def __init__(self, router: WebAPIRouter) -> None:
        self.router = router

    async def dispatch(self, request: Request) -> Response:
        body = request.scope.get("state", {}).get(BODY_JSON_STATE)
        if not isinstance(body, dict):
            # The outer ingress guard supplies this mapping after bounded JSON
            # parsing. Do not reparse JSON or bypass it for an isolated endpoint.
            raise RuntimeError("REST endpoint requires the ingress body guard")
        # DTOs document operation fields. Keep the original decoded mapping:
        # Pydantic model_dump may impose a separate recursion/serialization guard
        # even on Any/extras, changing deeply nested input before the controller.
        target = _raw_request_target(request.scope)
        status, payload = await self.router.handle_request(
            request.method, target, cast(dict[str, Any], body)
        )
        return legacy_json_response(status, redact_returned_error(status, payload))


def _endpoint(adapter: _RestAdapter) -> Callable[[Request], Awaitable[Response]]:
    async def dispatch(request: Request) -> Response:
        # Request-only signature prevents inferred Body/Query coercion or 422s.
        return await adapter.dispatch(request)

    return dispatch


def _path_metadata(contract: RouteContract) -> dict[str, Any]:
    # Descriptive metadata only. Endpoint inputs remain Request-only and the
    # original mapping still reaches the native controller without DTO filtering.
    return operation_metadata(contract)


class _CompatibilityFallback(BaseRoute):
    """Retain native family 404/405s, slash variants and arbitrary HTTP verbs."""

    def __init__(self, adapter: _RestAdapter) -> None:
        self.adapter = adapter

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] != "http":
            return Match.NONE, {}
        path = _raw_request_target(scope).partition("?")[0]
        if path.startswith("/api/") and not path.startswith("/api/map/tiles/"):
            # FULL must beat earlier PARTIAL method matches, preventing a new
            # framework 405/Allow or automatic GET-as-HEAD behavior.
            return Match.FULL, {"route": self}
        return Match.NONE, {}

    def url_path_for(self, name: str, /, **path_params: Any) -> URLPath:
        raise NoMatchFound(name, path_params)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = await self.adapter.dispatch(Request(scope, receive=receive))
        await response(scope, receive, send)


def install_rest_routes(app: FastAPI, router: WebAPIRouter) -> None:
    """Prepare all JSON batches and aliases, without constructing domain state."""
    if getattr(app.state, "rest_route_counts", None) is not None:
        raise RuntimeError("REST routes are already registered on this application")
    adapter = _RestAdapter(router)
    batches = {
        batch: APIRouter(route_class=_RawTargetAPIRoute, redirect_slashes=False)
        for batch in ROUTE_BATCHES
    }
    counts = dict.fromkeys(ROUTE_BATCHES, 0)
    alias_count = 0
    for contract in ROUTE_CONTRACTS:
        batch_router = batches[contract.batch]
        operation_id = contract.method.lower() + re.sub(r"\W+", "_", contract.path)
        batch_router.add_api_route(
            contract.path,
            _endpoint(adapter),
            methods=[contract.method],
            name=operation_id,
            operation_id=operation_id,
            tags=[contract.batch],
            response_model=None,
            response_class=Response,
            openapi_extra=_path_metadata(contract),
        )
        counts[contract.batch] += 1
        for alias, canonical in ROUTE_ALIASES.items():
            if canonical != contract.path:
                continue
            batch_router.add_api_route(
                alias,
                _endpoint(adapter),
                methods=[contract.method],
                name="alias_" + contract.method.lower() + re.sub(r"\W+", "_", alias),
                response_model=None,
                response_class=Response,
                include_in_schema=False,
            )
            alias_count += 1
    for batch_router in batches.values():
        app.include_router(batch_router)
    app.router.redirect_slashes = False
    # FastAPI 0.143's include_router ignores unsupported BaseRoute contexts.
    # Append to the root after includes, not inside an included APIRouter.
    app.router.routes.append(_CompatibilityFallback(adapter))
    app.state.rest_route_counts = {
        "canonical_operations": len(ROUTE_CONTRACTS),
        "alias_operations": alias_count,
        "batches": counts,
    }

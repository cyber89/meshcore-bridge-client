"""Preparatory application errors and unfiltered JSON for the optional ASGI app.

Perimeter errors keep their own phase-1 envelopes. Business controllers still
own validation and status selection; these handlers do not rewrite their return
values. In particular, a controller's returned 500 is not a raised exception.
"""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from src.web.controllers.base import problem_details


class CompatibilityRequestError(Exception):
    """Carry an explicitly selected contract error from a future route adapter.

    Callers must provide reviewed, public messages and codes, never exception
    text, submitted values, or credentials. This is not a generic replacement
    for the controller's ordered validations or their 400/422 distinctions.
    """

    def __init__(
        self, *, status_code: int, title: str, detail: str, error_code: str
    ) -> None:
        super().__init__(error_code)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.error_code = error_code


def legacy_json_response(status_code: int, payload: Any) -> Response:
    """Match the native JSON serializer without selecting or filtering fields.

    HEAD suppression and security/CORS headers belong to BridgeSecurityMiddleware.
    Keep ensure_ascii/default handling inherited from json.dumps. Returning this
    Response also avoids FastAPI's jsonable_encoder changing arbitrary result
    values before serialization. Tiles and other binary responses use a different
    adapter in the later route migration.
    """
    if status_code == 204:
        return Response(status_code=status_code, headers={"Content-Length": "0"})
    content = json.dumps(payload, indent=2, default=str).encode("utf-8")
    return Response(content=content, status_code=status_code, media_type="application/json")


def _problem_response(status: int, title: str, detail: str, code: str) -> Response:
    status_code, payload = problem_details(status, title, detail, code)
    return legacy_json_response(status_code, payload)


async def _compatibility_error(request: Request, error: Exception) -> Response:
    # Starlette dispatches this handler by the registered exception class.
    contract = cast(CompatibilityRequestError, error)
    return _problem_response(
        contract.status_code, contract.title, contract.detail, contract.error_code
    )


async def _validation_error(request: Request, error: Exception) -> Response:
    # errors(), body, input, ctx, location and str(error) may contain secrets.
    # This fallback is for a future typed endpoint, not a global 422 policy:
    # transport JSON errors and legacy business validations keep their own codes.
    return _problem_response(
        422,
        "Unprocessable Entity",
        "La solicitud no cumple el esquema de esta operación",
        "request_validation_failed",
    )


async def _http_error(request: Request, error: Exception) -> Response:
    status_code = cast(HTTPException, error).status_code
    if status_code == 404:
        return _problem_response(404, "Not Found", "Ruta no encontrada", "route_not_found")
    if status_code == 405:
        return _problem_response(
            405, "Method Not Allowed", "Método no permitido para este recurso", "method_not_allowed"
        )
    # Framework fallback only. Operation-specific messages must be selected in
    # the adapter/controller rather than reflecting arbitrary HTTPException.detail
    # or headers (which may include credentials). Do not add Allow/Retry-After.
    if status_code == 500:
        return await _internal_error(request, error)
    if status_code > 500:
        return _problem_response(
            status_code, "HTTP Error", "Error interno del servidor", "http_error"
        )
    return _problem_response(
        status_code, "HTTP Error", "La solicitud fue rechazada", "http_error"
    )


async def _internal_error(request: Request, error: Exception) -> Response:
    # The per-instance protocol logger retains sanitized traceback frames if the
    # framework re-raises. Neither this payload nor this handler logs the value.
    return _problem_response(
        500,
        "Internal Server Error",
        "Error interno del servidor",
        "internal_server_error",
    )


def install_error_handlers(app: FastAPI) -> None:
    """Install handlers on the candidate instance, with no global mutations."""
    app.add_exception_handler(CompatibilityRequestError, _compatibility_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _internal_error)

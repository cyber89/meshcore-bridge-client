"""Lazy OpenAPI documentation for the compatibility ASGI application.

The schema describes source evidence, not runtime acceptance. It does not call
controllers, read configuration or apply input/response DTOs to requests. Model
schema generation happens only inside build_openapi_schema, never while routes
are registered. JSON examples are fixed documentation values.
"""

from __future__ import annotations

import re
from typing import Any

from src.web.access_policy import HTTP_MAX_BODY_BYTES, requires_api_auth
from src.web.api_router import ROUTE_ALIASES
from src.web.asgi_openapi_catalog import OBSERVED_OPERATIONS, ObservedOperation
from src.web.asgi_route_catalog import ROUTE_BATCHES, ROUTE_CONTRACTS, RouteContract


def _schema_ref(name: str) -> dict[str, str]:
    return {"$ref": "#/components/schemas/" + name}


def _auth_metadata(method: str, path: str) -> dict[str, Any]:
    guarded = requires_api_auth(method, path)
    return {
        "security": [{"XApiKey": []}, {"LegacyQueryApiKey": []}] if guarded else [],
        "x-meshcore-authentication": {
            "required_when_BRIDGE_API_KEY_configured": guarded,
            "empty_environment_key_bypasses_authentication": True,
            "guard_uses_raw_path_before_alias_resolution": True,
            "nonempty_header_precedes_query_even_if_invalid": True,
            "query_requires_exactly_one_api_key_value": True,
        },
    }


def _parameters(contract: RouteContract, observed: ObservedOperation) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = [
        {
            "name": parameter.split(":", 1)[0],
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
            "description": (
                "El dispatcher conserva las validaciones actuales. Un sufijo id puede "
                "incluir barras; public_key debe superar la ruta y validación del controlador."
            ),
        }
        for parameter in re.findall(r"\{([^}]+)\}", contract.path)
    ]
    for field in observed.fields:
        parameters.append(
            {
                "name": field,
                "in": "query",
                "required": False,
                "schema": {},
                "description": (
                    "Campo observado, sin coerción de FastAPI. Query entrega texto o lista "
                    "de textos repetidos al router; body presente tiene precedencia salvo "
                    "LogsController, que relee query con parse_qs y elige el primer "
                    "valor restante tras descartar valores vacíos."
                ),
                "x-meshcore-compatibility-field": True,
            }
        )
    return parameters


def _responses(contract: RouteContract, observed: ObservedOperation) -> dict[str, Any]:
    # Every operation traverses the ingress body/security perimeter, even when
    # its controller ignores that body. These are not inferred FastAPI 422s.
    statuses = set(observed.statuses) | {400, 403, 413, 500}
    if requires_api_auth(contract.method, contract.path):
        statuses.add(401)
    responses: dict[str, Any] = {}
    for status in sorted(statuses):
        if status == 204:
            responses["204"] = {"description": "Sin cuerpo y sin Content-Type."}
            continue
        if status == 413:
            responses["413"] = {
                "description": "Perímetro: cuerpo superior a 1 MiB; respuesta vacía, cierre.",
            }
            continue
        if status < 400:
            media: dict[str, Any] = {"schema": _schema_ref("LegacyJSONResponse")}
            if contract.method == "GET" and contract.path in (
                "/api/contacts", "/api/channels", "/api/messages/recent"
            ):
                media["examples"] = {
                    "illustrative_empty_snapshot": {
                        "summary": "Ejemplo ilustrativo vacío; no captura datos de una estación",
                        "value": {"status": "ok", "data": [], "count": 0},
                    }
                }
            if contract.path in ("/api/diagnostics/report", "/api/diagnostics/report.md"):
                media["examples"] = {
                    "illustrative_report": {
                        "summary": "Texto documental dentro de JSON; no es descarga Markdown raw",
                        "value": {
                            "status": "ok",
                            "markdown": "# Ejemplo documental sin datos operativos",
                            "text": "# Ejemplo documental sin datos operativos",
                        },
                    }
                }
            responses[str(status)] = {
                "description": observed.response_notes + " Esquema de salida abierto.",
                "content": {"application/json": media},
            }
            continue
        content: dict[str, Any] = {
            "application/json": {"schema": _schema_ref("CompatibilityErrorResponse")}
        }
        untyped_body: dict[str, Any] | None = None
        if status in (400, 403):
            # The perimeter sends text bytes without Content-Type, not a
            # text/plain promise. OpenAPI cannot express an absent media header.
            untyped_body = {
                "content_type_header_present": False,
                "representation": "text bytes",
                "example": (
                    "Invalid Content-Length" if status == 400
                    else "403 Forbidden - Security Violation"
                ),
            }
            if status == 403 and not observed.command_failure_codes:
                content = {}
        if status == 400:
            content["application/json"]["examples"] = {
                "malformed_json_perimeter": {
                    "summary": "Envelope exacto del perímetro para JSON malformado",
                    "value": {"error": "Bad Request", "detail": "Malformed JSON payload"},
                }
            }
        elif status == 401:
            content["application/json"]["examples"] = {
                "unauthorized_perimeter": {
                    "summary": "Rechazo de clave del perímetro; no cubre todos los errores 401",
                    "value": {"error": "Unauthorized"},
                }
            }
        responses[str(status)] = {
            "description": (
                "Error del controlador, router o perímetro. Los envelopes existentes "
                "no son uniformes; Problem Details se transporta como application/json."
            ),
        }
        if content:
            responses[str(status)]["content"] = content
        if untyped_body is not None:
            responses[str(status)]["x-meshcore-perimeter-untyped-body"] = untyped_body
    if observed.command_failure_codes:
        for status_range in ("4XX", "5XX"):
            responses[status_range] = {
                "description": (
                    "BaseController conserva un código remoto entero válido 400..599; "
                    "el catálogo no enumera todas las respuestas del firmware/ejecutor."
                ),
                "content": {
                    "application/json": {"schema": _schema_ref("CompatibilityErrorResponse")}
                },
            }
    return responses


def operation_metadata(contract: RouteContract) -> dict[str, Any]:
    """Return descriptive metadata without generating or validating a DTO schema."""
    observed = OBSERVED_OPERATIONS[(contract.method, contract.path)]
    metadata: dict[str, Any] = {
        "summary": contract.method + " " + contract.path,
        "description": (
            observed.input_notes
            + ". Adaptador de compatibilidad: el controlador conserva coerciones, "
            "defaults, orden de validación y efectos; estos esquemas no los ejecutan."
        ),
        "parameters": _parameters(contract, observed),
        "responses": _responses(contract, observed),
        "x-meshcore-body-model": contract.model.__name__,
        "x-meshcore-consumed-fields": list(observed.fields),
        "x-meshcore-input-policy": observed.input_policy,
        "x-meshcore-effect": observed.effect,
        "x-meshcore-source-evidence": list(observed.evidence),
        "x-meshcore-response-schema-complete": False,
        "x-meshcore-aliases": [
            {
                "path": alias,
                "method": contract.method,
                "authentication_when_key_configured": requires_api_auth(contract.method, alias),
                "canonical_authentication_when_key_configured": requires_api_auth(
                    contract.method, contract.path
                ),
                "included_as_openapi_path": False,
            }
            for alias, canonical in ROUTE_ALIASES.items()
            if canonical == contract.path
        ],
        **_auth_metadata(contract.method, contract.path),
    }
    if not observed.input_policy.startswith("logs_raw_query"):
        metadata["requestBody"] = {
            "required": False,
            "description": (
                "Objeto JSON opcional, campos conocidos Any y extras permitidos. "
                "Sin Content-Length o con longitud cero el perímetro entrega {}. "
                "El DTO es descriptivo y puede incluir campos de otras operaciones "
                "de la familia; no impone campos requeridos, validación o filtrado."
            ),
            "content": {
                "application/json": {"schema": _schema_ref(contract.model.__name__)}
            },
        }
    else:
        metadata["x-meshcore-body-ignored-by-controller"] = True
    return metadata


def _tile_operation() -> dict[str, Any]:
    binary = {"schema": {"type": "string", "format": "binary"}}
    return {
        "operationId": "get_api_map_tiles_z_x_y",
        "tags": ["tiles"],
        "summary": "Tesela offline del servicio de mapas compartido",
        "description": (
            "Patrón representativo: el adaptador admite sufijo .ext y segmentos "
            "posteriores, ignorados tras z/x/y; int() y bounds permanecen en el adaptador. "
            "Sólo GET; HEAD y otros métodos reciben 405 antes de autenticación."
        ),
        "parameters": [
            {
                "name": coordinate,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
                "description": (
                    "z entero 0..22; x/y enteros 0..2**z-1 tras int(). "
                    "No se añade conversión de FastAPI."
                ),
            }
            for coordinate in ("z", "x", "y")
        ],
        "security": [],
        "responses": {
            "200": {
                "description": "Bytes de tesela; Cache-Control public, max-age=86400.",
                "headers": {"Cache-Control": {"schema": {"type": "string"}}},
                "content": {
                    mime: dict(binary)
                    for mime in (
                        "image/png", "image/jpeg", "image/webp", "application/x-protobuf"
                    )
                },
            },
            "400": {
                "description": "Perímetro rechaza framing o JSON del cuerpo si se envía.",
                "content": {
                    "application/json": {"schema": _schema_ref("CompatibilityErrorResponse")},
                },
                "x-meshcore-perimeter-untyped-body": {
                    "content_type_header_present": False,
                    "representation": "text bytes",
                },
            },
            "403": {
                "description": "Rechazo del inspector de ingreso.",
                "x-meshcore-perimeter-untyped-body": {
                    "content_type_header_present": False,
                    "representation": "text bytes",
                    "example": "403 Forbidden - Security Violation",
                },
            },
            "404": {
                "description": "Coordenadas inválidas o tesela ausente: vacío, image/png.",
                "content": {"image/png": binary},
            },
            "405": {
                "description": "Método distinto de GET; sin Allow ni Retry-After añadidos.",
                "content": {
                    "application/json": {"schema": _schema_ref("CompatibilityErrorResponse")}
                },
            },
            "413": {"description": "Perímetro: cuerpo superior a 1 MiB, respuesta vacía."},
            "500": {
                "description": "Fallo no controlado del adaptador.",
                "content": {
                    "application/json": {"schema": _schema_ref("CompatibilityErrorResponse")}
                },
            },
        },
        "x-meshcore-source-evidence": [
            "src/web/asgi_assets.py:AssetsAdapter._tile",
            "src/web/map_tile_service.py:MapTileService.get_tile",
        ],
        "x-meshcore-response-schema-complete": False,
    }


def build_openapi_schema() -> dict[str, Any]:
    """Build a fresh schema lazily, entirely from declarations and source annotations."""
    schemas: dict[str, Any] = {
        "LegacyJSONResponse": {
            "type": "object",
            "additionalProperties": True,
            "description": (
                "Envelope JSON abierto. data/result y campos por operación permanecen "
                "opacos; snapshots y respuestas administrativas no tienen shape cerrado. "
                "Informes Markdown, texto y PCAP se envuelven en JSON HTTP."
            ),
        },
        "CompatibilityErrorResponse": {
            "type": "object",
            "additionalProperties": True,
            "description": (
                "No es Problem Details universal. Incluye errores legacy simples, "
                "Problem Details con extensiones y fallos parciales preservados."
            ),
        },
    }
    # DTOs intentionally have Any fields and extra='allow'. No model instances,
    # model_validate, model_dump, configuration or controller calls occur here.
    for model in sorted(
        {contract.model for contract in ROUTE_CONTRACTS}, key=lambda item: item.__name__
    ):
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        definitions = schema.pop("$defs", {})
        schemas.update(definitions)
        schemas[model.__name__] = schema
    paths: dict[str, Any] = {}
    for contract in ROUTE_CONTRACTS:
        # OpenAPI placeholders have no Starlette :path converter syntax.
        path = re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", contract.path)
        paths.setdefault(path, {})[contract.method.lower()] = {
            "operationId": contract.method.lower() + re.sub(r"\W+", "_", contract.path),
            "tags": [contract.batch],
            **operation_metadata(contract),
        }
    paths["/api/map/tiles/{z}/{x}/{y}"] = {"get": _tile_operation()}
    return {
        "openapi": "3.1.0",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": "MeshCore Bridge API",
            "version": "3.0.0",
            "description": (
                "Contratos del transporte FastAPI seleccionado en el código. "
                "La revisión estática no acredita suites, interoperabilidad, seguridad completa "
                "o rendimiento. No ejecutar operaciones desde la documentación. "
                "GET refresh/preflight y otros endpoints pueden tener efectos."
            ),
        },
        "tags": [{"name": batch} for batch in (*ROUTE_BATCHES, "tiles")],
        "paths": paths,
        "components": {
            "schemas": schemas,
            "securitySchemes": {
                "XApiKey": {
                    "type": "apiKey", "in": "header", "name": "X-Api-Key",
                    "description": "Clave configurada; encabezado no vacío tiene precedencia.",
                },
                "LegacyQueryApiKey": {
                    "type": "apiKey", "in": "query", "name": "api_key",
                    "description": (
                        "Compatibilidad legacy; exige un valor único y se usa sólo "
                        "si X-Api-Key está vacío o ausente. Evitar claves en URLs."
                    ),
                },
            },
        },
        "x-meshcore-observation": {
            "canonical_json_operations": len(ROUTE_CONTRACTS),
            "tile_operations": 1,
            "alias_operations": sum(
                canonical == contract.path
                for contract in ROUTE_CONTRACTS
                for canonical in ROUTE_ALIASES.values()
            ),
            "verification": "static source review; runtime and browser acceptance pending",
            "max_request_body_bytes": HTTP_MAX_BODY_BYTES,
            "request_content_type_is_not_enforced": True,
            "empty_body_becomes_object": True,
            "response_model_validation_enabled": False,
            "request_model_validation_enabled": False,
            "idempotency_or_automatic_retry_guaranteed": False,
            "compatibility_gaps": [
                "GET /api/logs is recognized by the dispatcher but always returns log_not_found 404.",
                "Aliases are guarded by their raw paths; some protected-prefix reads differ from canonical paths.",
                "LogsController reparses raw query and ignores the merged body.",
                "Wrong verbs and slash variants use the existing fallback, not inferred FastAPI 405/307.",
                "OPTIONS is global perimeter 204 and is not counted as a canonical API operation.",
                "WebSocket messages and static SPA assets are separate from OpenAPI HTTP paths.",
            ],
        },
    }

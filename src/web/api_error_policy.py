"""Reviewed error redaction for the ASGI REST adapter.

This module has no optional web dependency. Success/configuration/export payloads
are deliberately outside this policy; controllers own their public projection.
It does not sanitize logs produced inside services, controllers or SDK calls.
"""

from __future__ import annotations

from typing import Any

from src.protocol_types import redact_sensitive_mapping
from src.shared_utils import sanitize_public_payload

_PUBLIC_ERROR_DETAILS: dict[str, str] = {
    "command_failed": "El transceptor rechazó la operación",
    "command_partial": "El transceptor confirmó la operación parcialmente",
    "sync_failed": "No se pudo sincronizar con el transceptor",
    "read_unconfirmed": "El transceptor no confirmó la lectura",
    "unsupported_parameter": "El transceptor rechazó el parámetro",
    "auth_failed": "Autenticación no confirmada por el repetidor",
    "invalid_log_level": "Nivel de registro no válido",
    "tx_submission_failed": "No se pudo admitir la transmisión en la cola",
    "tx_transmission_failed": "No se confirmó la transmisión por radio",
    "reload_failed": "No se pudieron recargar los servicios",
    "route_not_found": "Ruta no encontrada",
    "services_route_not_found": "Ruta de servicios no encontrada",
    "preset_not_found": "Preset no encontrado",
}
_DIAGNOSTIC_FIELDS = frozenset({"detail", "message", "error", "response"})
_NESTED_FAILURE_DETAIL = "La operación no se confirmó"


def _redact_failure_tree(value: Any) -> Any:
    """Copy already canonicalized extensions, retaining metadata and containers.

    The caller applies canonical credential/command masking once. The
    public-sink helper is queried with a dummy value so its
    bytes/float conversions never change metadata in this response adapter.
    Unknown fields and arbitrary free text remain outside this bounded policy.
    """
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key not in sanitize_public_payload({key: None}):
                # Preserve field presence, including the existing PIN envelope.
                cleaned[key] = item if item in (0, "********") else "********"
            elif str(key).lower() in _DIAGNOSTIC_FIELDS and isinstance(item, str):
                cleaned[key] = _NESTED_FAILURE_DETAIL if item else item
            else:
                cleaned[key] = _redact_failure_tree(item)
        return cleaned
    if isinstance(value, list):
        return [_redact_failure_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_failure_tree(item) for item in value)
    return value


def redact_returned_error(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Redact reviewed returned errors without changing HTTP status or codes.

    The MQTT connectivity operation returns HTTP 200 with ``status: error``;
    that failure envelope is treated here while retaining 200, data.ok and
    latency_ms. Other successful payloads are returned untouched. This is not a
    generic response schema or a proof that arbitrary service output is safe.
    """
    wrapper_status = payload.get("status")
    failed_wrapper = isinstance(wrapper_status, str) and wrapper_status.lower() in {
        "error", "failed", "partial"
    }
    if status_code < 400 and not failed_wrapper:
        return payload

    # Only extensions are traversed: preserve the Problem Details error code,
    # title/type/timestamp and either numeric or string status without coercion.
    envelope_fields = {"type", "title", "status", "detail", "error", "message", "timestamp"}
    cleaned = dict(payload)
    extensions = {key: value for key, value in payload.items() if key not in envelope_fields}
    # Canonical masking is recursive; applying it once avoids repeatedly
    # traversing subtrees. Merge its whole result to retain generated has_pin.
    cleaned.update(_redact_failure_tree(redact_sensitive_mapping(extensions)))

    code = payload.get("error")
    public_detail = _PUBLIC_ERROR_DETAILS.get(code) if isinstance(code, str) else None
    if status_code == 500:
        public_detail = "Error interno del servidor"
    elif failed_wrapper:
        public_detail = public_detail or _NESTED_FAILURE_DETAIL
    if public_detail is not None:
        for field in ("detail", "message"):
            if field in payload:
                cleaned[field] = public_detail
    return cleaned

"""
Esquema canónico y validación general de tipos y aliases para configuración local.
"""

from __future__ import annotations

import math
from typing import Any

from src.shared_utils import to_bool

# Campos históricos de UI no soportados por el firmware MeshCore actual
UNSUPPORTED_LOCAL_FIELDS = frozenset({
    "telemetry_interval", "beacon_interval", "advert_interval", "hop_limit", "hops",
    "owner_info", "owner", "altitude", "alt", "altitude_m",
    "fixed_position", "pos_fixed",
})

# Campos empaquetados en un único struct en firmware que requieren baseline de dispositivo
OTHER_PARAM_FIELDS = (
    "telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env",
    "multi_acks", "adv_loc_policy", "manual_add_contacts",
)

# Claves permitidas en solicitudes de configuración local
ALLOWED_LOCAL_KEYS = frozenset({
    # Identidad y ubicación
    "name", "latitude", "lat", "longitude", "lon",
    # Radio
    "frequency", "radio_freq", "bandwidth", "bw", "spreading_factor", "sf", "coding_rate", "cr",
    "tx_power", "power", "repeat", "repeat_enabled",
    # Parámetros de telemetría y políticas
    "telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env",
    "multi_acks", "adv_loc_policy", "manual_add_contacts",
    # Ajustes avanzados y tuning
    "pin", "devicepin", "rx_delay", "rx_dly", "airtime_factor", "af",
    "path_hash_mode", "custom_vars",
    # Políticas de host / airtime
    "duty_cycle_limit_pct", "warn_threshold_pct",
    "airtime_cutoff_enabled", "airtime_cutoff_threshold_pct", "airtime_cutoff_resume_pct",
    "repeater_pre_send_delay_enabled", "repeater_pre_send_delay_s",
})


class LocalConfigValidationError(ValueError):
    """Encapsula los nombres de campos de esquema rechazados antes de mutar el hardware."""

    def __init__(self, reason: str, fields: tuple[str, ...]) -> None:
        super().__init__("Configuración local rechazada antes de aplicar cambios")
        self.reason = reason
        self.fields = fields


def normalize_coding_rate(cr_val: Any) -> int | None:
    """Normaliza y valida un coding rate LoRa (5..8 o 4/5..4/8), devolviendo 5..8 o None si es inválido."""
    if cr_val is None:
        return None
    s = str(cr_val).strip()
    if s in ("5", "6", "7", "8"):
        return int(s)
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 2 and parts[0].strip() == "4" and parts[1].strip() in ("5", "6", "7", "8"):
            return int(parts[1].strip())
    return None


def validate_general_schema(params: dict[str, Any]) -> None:
    """Valida tipos escalares básicos, consistencia de aliases y campos permitidos."""
    if not isinstance(params, dict):
        raise ValueError("params debe ser un objeto")

    integer_keys = {
        "tx_power", "power", "spreading_factor", "sf", "path_hash_mode",
        "pin", "devicepin", "telemetry_mode_base", "telemetry_mode_loc",
        "telemetry_mode_env",
    }
    for key in integer_keys.intersection(params):
        value = params[key]
        if isinstance(value, bool) or (isinstance(value, float) and (not math.isfinite(value) or not value.is_integer())):
            raise ValueError(f"El parámetro '{key}' debe ser un entero")

    if "name" in params and not isinstance(params["name"], str):
        raise ValueError("name debe ser texto")

    boolean_keys = {"repeat", "repeat_enabled", "manual_add_contacts", "adv_loc_policy", "multi_acks"}
    for key in boolean_keys.intersection(params):
        value = params[key]
        if not (
            isinstance(value, bool)
            or (isinstance(value, int) and value in (0, 1))
            or (isinstance(value, str) and value.lower().strip() in {"true", "false", "1", "0", "yes", "no", "on", "off"})
        ):
            raise ValueError(f"El parámetro '{key}' debe ser booleano")

    aliases_to_check = (
        ("frequency", "radio_freq", float),
        ("bandwidth", "bw", float),
        ("spreading_factor", "sf", int),
        ("coding_rate", "cr", normalize_coding_rate),
        ("tx_power", "power", int),
        ("latitude", "lat", float),
        ("longitude", "lon", float),
        ("repeat", "repeat_enabled", to_bool),
        ("rx_delay", "rx_dly", float),
        ("airtime_factor", "af", float),
    )
    for canonical, alias, convert in aliases_to_check:
        if canonical in params and alias in params and convert(params[canonical]) != convert(params[alias]):
            raise ValueError(f"Alias contradictorios: '{canonical}' y '{alias}'")

    for key in {"latitude", "lat", "longitude", "lon"}.intersection(params):
        if isinstance(params[key], bool):
            raise ValueError(f"El parámetro '{key}' no puede ser booleano")

    unsupported = sorted(UNSUPPORTED_LOCAL_FIELDS.intersection(params))
    if unsupported:
        raise LocalConfigValidationError("unsupported_local_fields", tuple(unsupported))

    for k in params:
        if k not in ALLOWED_LOCAL_KEYS:
            raise ValueError(f"Parámetro de configuración local desconocido: '{k}'")

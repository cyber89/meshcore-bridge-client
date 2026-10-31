"""
Validador de modos de telemetría y políticas de airtime / ciclo de trabajo del host.
"""

from __future__ import annotations

import math
from typing import Any


def validate_telemetry_modes(params: dict[str, Any]) -> None:
    """Prevalida modos de telemetría numérica (0=off, 1=on, 2=request)."""
    for ok in ("telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env"):
        if ok in params:
            o_val = params[ok]
            if isinstance(o_val, bool):
                raise ValueError(f"El parámetro '{ok}' no puede ser booleano")
            try:
                oi = int(o_val)
                if oi not in (0, 1, 2):
                    raise ValueError(f"El parámetro '{ok}' debe ser 0, 1 o 2 (recibido: {oi})")
            except (ValueError, TypeError) as err:
                raise ValueError(f"Parámetro '{ok}' inválido: {o_val}") from err


def validate_airtime_policy_params(params: dict[str, Any]) -> None:
    """Prevalida parámetros de política de airtime del host y delay de repetidor."""
    pct_keys = (
        "duty_cycle_limit_pct",
        "warn_threshold_pct",
        "airtime_cutoff_threshold_pct",
        "airtime_cutoff_resume_pct",
    )
    for pk in pct_keys:
        if pk in params:
            val = params[pk]
            if isinstance(val, bool):
                raise ValueError(f"El parámetro '{pk}' no puede ser booleano")
            try:
                flt = float(val)
                if not math.isfinite(flt) or not (0.0 <= flt <= 100.0):
                    raise ValueError(f"El parámetro '{pk}' debe ser un porcentaje finito entre 0 y 100")
            except (ValueError, TypeError) as err:
                raise ValueError(f"Parámetro '{pk}' inválido: {val}") from err

    if "airtime_cutoff_enabled" in params:
        val = params["airtime_cutoff_enabled"]
        if not (isinstance(val, bool) or (isinstance(val, int) and val in (0, 1))):
            raise ValueError("El parámetro 'airtime_cutoff_enabled' debe ser booleano")

    if "repeater_pre_send_delay_s" in params:
        val = params["repeater_pre_send_delay_s"]
        if isinstance(val, bool):
            raise ValueError("El parámetro 'repeater_pre_send_delay_s' no puede ser booleano")
        try:
            flt = float(val)
            if not math.isfinite(flt) or flt < 0.0:
                raise ValueError("El parámetro 'repeater_pre_send_delay_s' debe ser un número finito no negativo")
        except (ValueError, TypeError) as err:
            raise ValueError(f"Parámetro 'repeater_pre_send_delay_s' inválido: {val}") from err

    if "repeater_pre_send_delay_enabled" in params:
        val = params["repeater_pre_send_delay_enabled"]
        if not (isinstance(val, bool) or (isinstance(val, int) and val in (0, 1))):
            raise ValueError("El parámetro 'repeater_pre_send_delay_enabled' debe ser booleano")

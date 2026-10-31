"""
Validador de parámetros de radio LoRa, potencia TX y afinamiento de sincronización.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from src.admin.validators.schema import LocalConfigValidationError, normalize_coding_rate
from src.protocol_types import LORA_MAX_FREQ_MHZ, LORA_MIN_FREQ_MHZ


def validate_radio_params(
    params: dict[str, Any],
    get_baseline_fn: Callable[[str, tuple[str, ...]], Any],
) -> None:
    """Prevalida potencia TX y parámetros de radiofrecuencia (frecuencia, BW, SF, CR)."""
    # Prevalidación de potencia TX (BV06)
    if "tx_power" in params or "power" in params:
        raw_pwr = params.get("tx_power", params.get("power"))
        if isinstance(raw_pwr, bool):
            raise ValueError("Potencia TX no puede ser un booleano")
        try:
            if raw_pwr is None:
                raise ValueError("Potencia TX no puede ser nula")
            p_int = int(raw_pwr)
            if not (-9 <= p_int <= 30):
                raise ValueError(f"Potencia TX fuera de rango (-9..30 dBm): {raw_pwr}")
        except (ValueError, TypeError) as err:
            raise ValueError(f"Potencia TX inválida: {raw_pwr}") from err

    # Prevalidación de parámetros de radio (BV02, BV03, BV10)
    radio_keys = (
        "frequency", "radio_freq", "bandwidth", "bw",
        "spreading_factor", "sf", "coding_rate", "cr",
        "repeat", "repeat_enabled",
    )
    if any(k in params for k in radio_keys):
        b_freq = params.get("frequency", params.get("radio_freq", get_baseline_fn("frequency", ("freq", "radio_freq"))))
        b_bw = params.get("bandwidth", params.get("bw", get_baseline_fn("bandwidth", ("bw", "radio_bw"))))
        b_sf = params.get("spreading_factor", params.get("sf", get_baseline_fn("spreading_factor", ("sf", "radio_sf"))))
        b_cr = params.get("coding_rate", params.get("cr", get_baseline_fn("coding_rate", ("cr", "radio_cr"))))

        if b_freq is None or b_bw is None or b_sf is None or b_cr is None:
            raise ValueError(
                "Baseline de parámetros de radio no disponible; se requiere especificar "
                "frequency, bandwidth, spreading_factor y coding_rate completos."
            )

        try:
            f_flt = float(b_freq)
            if not (LORA_MIN_FREQ_MHZ <= f_flt <= LORA_MAX_FREQ_MHZ):
                raise ValueError(
                    f"Frecuencia {f_flt} MHz fuera del rango permitido ({LORA_MIN_FREQ_MHZ}-{LORA_MAX_FREQ_MHZ} MHz)"
                )
            bw_flt = float(b_bw)
            if not (7.0 <= bw_flt <= 500.0):
                raise ValueError(f"Ancho de banda {bw_flt} kHz inválido")
            sf_int = int(b_sf)
            if sf_int not in range(5, 13):
                raise ValueError(f"Spreading factor SF{sf_int} inválido (5..12)")
            cr_parsed = normalize_coding_rate(b_cr)
            if cr_parsed is None:
                raise ValueError(f"Coding rate CR '{b_cr}' inválido (debe ser 5..8 o 4/5..4/8)")
        except (ValueError, TypeError) as err:
            raise ValueError(f"Parámetros de radio inválidos: {err}") from err


def validate_tuning_params(
    params: dict[str, Any],
    get_baseline_fn: Callable[[str, tuple[str, ...]], Any],
) -> None:
    """Prevalida parámetros de tuning (rx_delay, airtime_factor) y su baseline."""
    for tk in ("rx_delay", "airtime_factor", "af", "rx_dly"):
        if tk in params:
            t_val = params[tk]
            if isinstance(t_val, bool):
                raise ValueError(f"El parámetro '{tk}' no puede ser booleano")
            try:
                f_val = float(t_val)
                if not math.isfinite(f_val) or f_val < 0.0:
                    raise ValueError(f"El parámetro '{tk}' debe ser un número finito no negativo")
                maximum = 20.0 if tk in ("rx_delay", "rx_dly") else 9.0
                if f_val > maximum:
                    raise ValueError(f"El parámetro '{tk}' debe estar entre 0 y {maximum}")
            except (ValueError, TypeError) as err:
                raise ValueError(f"Parámetro '{tk}' inválido: {t_val}") from err

    if any(key in params for key in ("rx_delay", "rx_dly", "airtime_factor", "af")):
        for field, alias in (("rx_delay", "rx_dly"), ("airtime_factor", "af")):
            if field not in params and alias not in params and get_baseline_fn(field, (alias,)) is None:
                raise LocalConfigValidationError("missing_tuning_baseline", (field,))

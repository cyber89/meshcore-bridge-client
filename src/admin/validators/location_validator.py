"""
Validador de coordenadas geográficas (latitud y longitud) del nodo local.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any


def validate_location_params(
    params: dict[str, Any],
    get_baseline_fn: Callable[[str, tuple[str, ...]], Any],
) -> None:
    """Prevalida coordenadas geográficas comprobando completitud, finitud y límites."""
    lat_val = params.get("latitude", params.get("lat"))
    lon_val = params.get("longitude", params.get("lon"))

    if lat_val is None and lon_val is None:
        return

    if lat_val is None:
        lat_val = get_baseline_fn("latitude", ("lat", "adv_lat"))
    if lon_val is None:
        lon_val = get_baseline_fn("longitude", ("lon", "adv_lon"))

    if lat_val is None or lon_val is None:
        raise ValueError("Coordenadas incompletas: se requieren tanto latitud como longitud")

    try:
        lat_f, lon_f = float(lat_val), float(lon_val)
        if math.isnan(lat_f) or math.isnan(lon_f) or math.isinf(lat_f) or math.isinf(lon_f):
            raise ValueError("Coordenadas no pueden ser NaN o infinitas")
        if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
            raise ValueError("Coordenadas fuera de rango (-90..90, -180..180)")
    except (ValueError, TypeError) as err:
        raise ValueError("Coordenadas inválidas") from err

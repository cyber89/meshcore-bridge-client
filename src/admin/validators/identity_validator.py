"""
Validadores de identidad de nodo, PIN, modo de path hash y variables personalizadas.
"""

from __future__ import annotations

from typing import Any


def validate_custom_var(key: str, val: str) -> None:
    """Valida formato y separadores seguros para variables personalizadas."""
    if not key or any(char in key + val for char in (":", ",", "\0", "\r", "\n")):
        raise ValueError("Variable custom inválida: clave vacía o separadores reservados")


def validate_identity_params(params: dict[str, Any]) -> None:
    """Valida campos de nombre, PIN, path hash mode y variables custom."""
    if "name" in params:
        name_val = str(params["name"]).strip()
        if len(name_val.encode("utf-8")) > 31 or any(ord(c) < 0x20 for c in name_val):
            raise ValueError("Nombre de nodo inválido: máximo 31 bytes UTF-8 sin caracteres de control")

    if "path_hash_mode" in params:
        try:
            phm = int(params["path_hash_mode"])
            if phm not in (0, 1, 2):
                raise ValueError(f"path_hash_mode debe ser 0, 1 o 2 (recibido: {phm})")
        except (ValueError, TypeError) as err:
            raise ValueError(f"Path hash mode inválido: {err}") from err

    if "pin" in params or "devicepin" in params:
        raw_pin = params.get("pin", params.get("devicepin"))
        try:
            if raw_pin is None:
                raise ValueError("El PIN del dispositivo no puede ser nulo")
            p_int = int(raw_pin)
            if p_int != 0 and not (100000 <= p_int <= 999999):
                raise ValueError("El PIN del dispositivo debe ser 0 (desactivado) o de 6 dígitos (100000-999999)")
        except (ValueError, TypeError) as err:
            raise ValueError(f"PIN inválido: {raw_pin}") from err

    if "custom_vars" in params:
        if not isinstance(params["custom_vars"], dict):
            raise ValueError("custom_vars debe ser un objeto")
        for key, value in params["custom_vars"].items():
            validate_custom_var(str(key), str(value))

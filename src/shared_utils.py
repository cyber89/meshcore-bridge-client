import asyncio
import logging
import math
import re
from typing import Any

from src.protocol_types import FirmwareAdvertType


def classify_device_role(advert_type: int, is_local: bool = False) -> str:
    """Clasificación canónica de rol de dispositivo según FirmwareAdvertType.

    Single Source of Truth para mapear tipos de advertisement del firmware
    MeshCore a roles de dispositivo legibles.

    Args:
        advert_type: Valor numérico de FirmwareAdvertType del firmware.
        is_local: True si el nodo es la estación base local.

    Returns:
        Rol como string: LOCAL, CLIENT, REPEATER, ROOM, SENSOR.
    """
    if is_local:
        return "LOCAL"
    try:
        fat = FirmwareAdvertType(advert_type)
        if fat in (FirmwareAdvertType.NONE, FirmwareAdvertType.CHAT):
            return "CLIENT"
        return fat.name
    except (ValueError, TypeError):
        return "CLIENT"


def clean_numeric_value(val: Any) -> float | None:
    """Extrae un valor numérico flotante limpio desde enteros, flotantes o strings con unidades o símbolos.

    Soporta:
    - Enteros y flotantes directos (22.5, 60, -118)
    - Strings con unidades o símbolos ("24.5°C", "60%", "1013.2 hPa", "-118 dBm", "350 lux", "250ms")
    - Retorna el valor como float limpio o None si no se puede parsear.
    """
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        try:
            number = float(val)
            return number if math.isfinite(number) else None
        except OverflowError:
            return None
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        m = re.search(r"[-+]?\d*\.?\d+", cleaned)
        if m:
            try:
                number = float(m.group(0))
                return number if math.isfinite(number) else None
            except (ValueError, TypeError, OverflowError):
                return None
    return None


def clean_coordinate_value(value: Any, *, latitude: bool = False) -> float | None:
    """Accept finite geographic degrees, including equator/prime-meridian zero."""
    number = clean_numeric_value(value)
    limit = 90.0 if latitude else 180.0
    return number if number is not None and -limit <= number <= limit else None


def clean_battery_input(val: Any) -> float | None:
    """Extrae y normaliza un valor numérico de batería o voltaje desde diversos tipos y formatos."""
    return clean_numeric_value(val)


def normalize_battery(raw_value: int | float | str | Any) -> tuple[float, float]:
    """Conversión canónica de valor crudo de batería a porcentaje y voltaje.

    El firmware MeshCore reporta batería en diferentes formatos según hardware:
    - 2.5 - 5.5: Voltaje en Voltios (2.50V - 5.50V)
    - 0 - 100: Porcentaje directo
    - 101 - 255: Valor ADC que requiere conversión
    - 300 - 420: Voltaje en centésimas (3.00V - 4.20V)
    - 2500 - 5500: Voltaje en milivoltios (2500mV - 5500mV) o explícito mV

    Args:
        raw_value: Valor crudo reportado por el firmware (int, float o str).

    Returns:
        Tupla (porcentaje, voltaje_estimado).
    """
    num_val = clean_battery_input(raw_value)
    if num_val is None or num_val <= 0:
        return 0.0, 0.0

    raw_str = str(raw_value).strip().lower() if isinstance(raw_value, str) else ""
    is_explicit_pct = "%" in raw_str
    is_explicit_mv = "mv" in raw_str
    is_explicit_volt = ("v" in raw_str and not is_explicit_mv) or (raw_str.endswith("v") and not is_explicit_mv)

    # Caso 1: Voltaje explícito o flotante decimal en rango típico de celda (2.5V - 5.5V)
    if not is_explicit_pct and not is_explicit_mv and (
        is_explicit_volt or (2.5 <= num_val <= 5.5 and (isinstance(raw_value, float) or "." in str(raw_value)))
    ):
        voltage = round(num_val, 2)
        if voltage >= 4.8:
            percent = 100.0
        elif voltage <= 3.0:
            percent = 0.0
        else:
            percent = max(0.0, min(100.0, ((voltage - 3.0) / 1.2) * 100.0))
        return round(percent, 1), voltage

    # Caso 2: Porcentaje directo (0 - 100)
    if 1 <= num_val <= 100 and not is_explicit_mv:
        percent = float(num_val)
        voltage = 3.0 + (percent / 100.0) * 1.2
        return round(percent, 1), round(voltage, 2)

    # Caso 3: Valor ADC (101 - 255)
    if 101 <= num_val <= 255 and not is_explicit_mv:
        percent = round((num_val / 255.0) * 100.0, 1)
        voltage = 3.0 + (num_val / 255.0) * 1.2
        return round(percent, 1), round(voltage, 2)

    # Caso 4: Centivoltios (300 - 420)
    if 300 <= num_val <= 420 and not is_explicit_mv:
        voltage = num_val / 100.0
        percent = max(0.0, min(100.0, ((voltage - 3.0) / 1.2) * 100.0))
        return round(percent, 1), round(voltage, 2)

    # Caso 5: Milivoltios (2500 - 5500) o explícito mV
    if 2500 <= num_val <= 5500 or is_explicit_mv:
        voltage = round(num_val / 1000.0, 2)
        if voltage >= 4.8:
            percent = 100.0
        elif voltage <= 3.0:
            percent = 0.0
        else:
            percent = max(0.0, min(100.0, ((voltage - 3.0) / 1.2) * 100.0))
        return round(percent, 1), voltage

    logging.warning("Valor de batería fuera de rango: %s", raw_value)
    return 0.0, 0.0


# Mapeo canónico de modelos de hardware / transceptores a límites de potencia TX (min_dbm, max_dbm, default_dbm)
HARDWARE_TX_POWER_LIMITS: dict[str, tuple[int, int, int]] = {
    # Semtech SX1262 / SX1268 (Máximo 22 dBm / 160 mW)
    "HELTEC_V3": (2, 22, 20),
    "HELTEC_V4": (2, 22, 20),
    "LILYGO_TBEAM": (2, 22, 20),
    "LILYGO_TECHO": (2, 22, 20),
    "LILYGO_TDECK": (2, 22, 20),
    "RAK4631": (2, 22, 20),
    "SEEED_XIAO": (2, 22, 20),
    "RP2040_LORA": (2, 22, 20),
    "STATION_G1": (2, 22, 20),
    "STATION_G2": (2, 22, 20),
    "NANO_G1": (2, 22, 20),
    "NANO_G2": (2, 22, 20),
    "SX1262": (2, 22, 20),
    "SX1268": (2, 22, 20),
    "LR1121": (2, 22, 20),

    # Semtech SX1276 / SX1278 (Máximo 20 dBm / 100 mW)
    "HELTEC_V2": (2, 20, 17),
    "HELTEC_V1": (2, 20, 17),
    "TLORA_V1": (2, 20, 17),
    "TLORA_V2": (2, 20, 17),
    "M5STACK_CORE": (2, 20, 17),
    "SX1276": (2, 20, 17),
    "SX1278": (2, 20, 17),

    # Módulos de Alta Potencia con Amplificador PA (Ebyte E22-900M30S / E22-400M30S / DIY PA) (Máximo 30 dBm / 1000 mW / 1W)
    "E22_30DBM": (10, 30, 27),
    "EBYTE_E22": (10, 30, 27),
    "E22_900M30S": (10, 30, 27),
    "E22_400M30S": (10, 30, 27),
    "STATION_G2_PLUS": (10, 30, 27),
    "REPEATER_HIGH_POWER": (10, 30, 27),

    # Dispositivos de ultra-bajo consumo / Dongles / CC1352 (Máximo 14 dBm)
    "CC1352": (0, 14, 14),
    "LOW_POWER": (0, 14, 10),

    # Estándar por defecto
    "DEFAULT": (2, 22, 20),
}

NUMERIC_BOARD_ID_MAP: dict[int, str] = {
    1: "HELTEC_V1",
    2: "HELTEC_V2",
    3: "TLORA_V2",
    4: "LILYGO_TBEAM",
    5: "HELTEC_V3",
    6: "RAK4631",
    7: "LILYGO_TECHO",
    8: "LILYGO_TDECK",
}


def get_hardware_power_limits(
    hardware_info: str | int | None = None,
    max_tx_power_hint: int | None = None,
) -> tuple[int, int, int]:
    """Retorna los límites de potencia (min_dbm, max_dbm, default_dbm) para un hardware dado.

    Args:
        hardware_info: Nombre del modelo, placa (ej: 'Heltec v3', 'RAK4631', 'SX1276') o código.
        max_tx_power_hint: Límite máximo explícito reportado por el firmware si está disponible.

    Returns:
        Tupla (min_dbm, max_dbm, default_dbm).
    """
    if max_tx_power_hint is not None and isinstance(max_tx_power_hint, int) and max_tx_power_hint > 0:
        min_p = 10 if max_tx_power_hint >= 30 else (0 if max_tx_power_hint <= 14 else 2)
        def_p = min(20, max_tx_power_hint)
        return (min_p, max_tx_power_hint, def_p)

    if not hardware_info:
        return HARDWARE_TX_POWER_LIMITS["DEFAULT"]

    if isinstance(hardware_info, int) or (isinstance(hardware_info, str) and hardware_info.strip().isdigit()):
        mapped = NUMERIC_BOARD_ID_MAP.get(int(hardware_info))
        if mapped and mapped in HARDWARE_TX_POWER_LIMITS:
            return HARDWARE_TX_POWER_LIMITS[mapped]

    hw_clean = str(hardware_info).upper().replace("-", "_").replace(" ", "_")
    for key, limits in HARDWARE_TX_POWER_LIMITS.items():
        if key != "DEFAULT" and key in hw_clean:
            return limits

    return HARDWARE_TX_POWER_LIMITS["DEFAULT"]


def clamp_tx_power(
    power: int,
    hardware_info: str | int | None = None,
    max_tx_power_hint: int | None = None,
) -> int:
    """Acota la potencia de transmisión dentro del rango seguro soportado por el hardware.

    Args:
        power: Potencia deseada en dBm.
        hardware_info: Modelo de hardware / placa.
        max_tx_power_hint: Límite de potencia máximo explícito.

    Returns:
        Potencia dBm acotada estrictamente a [min_dbm, max_dbm].
    """
    min_p, max_p, _ = get_hardware_power_limits(hardware_info, max_tx_power_hint)
    return max(min_p, min(max_p, int(power)))


REPEATER_NAME_PREFIXES: tuple[str, ...] = (
    "R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-", "REP_", "ROUTER_"
)
REPEATER_SUBSTRINGS: tuple[str, ...] = (
    "REPEATER", "ROUTER", "REPETIDOR"
)


def is_repeater_name(name: str | None) -> bool:
    """Heurística de presentación por nombre; nunca acredita un rol de firmware."""
    if not name or not isinstance(name, str):
        return False
    name_clean = name.strip().upper()
    if name_clean.startswith(REPEATER_NAME_PREFIXES):
        return True
    return any(sub in name_clean for sub in REPEATER_SUBSTRINGS)


def to_bool(val: Any, default: bool = False) -> bool:
    """Convierte de forma robusta cualquier valor a booleano canónico.

    Maneja cadenas ('true', 'false', '1', '0', 'yes', 'no'), enteros y valores nulos
    sin falsos positivos causados por bool("false") == True.
    """
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        clean = val.strip().lower()
        if clean in ("true", "1", "yes", "on", "t"):
            return True
        if clean in ("false", "0", "no", "off", "f", ""):
            return False
        return default
    return bool(val)


def extract_payload_dict(data: Any) -> dict[str, Any]:
    """Extrae un diccionario de datos tanto de objetos Event (SDK oficial) como de dicts nativos."""
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if hasattr(data, "payload") and isinstance(data.payload, dict):
        return data.payload
    return {}


_SECRET_FIELDS = frozenset({
    "private_key", "privatekey", "channel_secret", "secret", "secrets", "psk",
    "password", "passwd", "admin_password", "mqtt_password", "pin", "token", "api_key",
})


def sanitize_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy structured SDK data for public sinks, omitting credential fields."""
    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: sanitize(item) for key, item in value.items()
                    if str(key).lower().replace("-", "_") not in _SECRET_FIELDS}
        if isinstance(value, (list, tuple)):
            return [sanitize(item) for item in value]
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).hex()
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    return dict(sanitize(payload))


async def safe_device_query(
    mc: Any,
    command_name: str,
    *args: Any,
    timeout: float = 3.0,
    fallback: Any = None,
    **kwargs: Any,
) -> Any:
    """Ejecuta una consulta o comando sobre mc.commands de manera segura y no bloqueante.

    Verifica la existencia del método en el SDK, maneja tanto respuestas síncronas como
    corutinas asíncronas con timeout determinista, y captura excepciones de comunicación
    evitando que fallos en un parámetro interrumpan la secuencia de inicialización.

    Args:
        mc: Instancia del cliente MeshCore (con atributo .commands).
        command_name: Nombre del método a invocar en mc.commands.
        *args: Argumentos posicionales para el comando.
        timeout: Tiempo máximo de espera en segundos antes de TimeoutError.
        fallback: Valor retornado en caso de fallo, ausencia del comando o timeout.
        **kwargs: Argumentos por nombre para el comando.

    Returns:
        El resultado retornado por el comando o el valor de fallback.
    """
    if not mc or not hasattr(mc, "commands") or not hasattr(mc.commands, command_name):
        return fallback

    cmd = getattr(mc.commands, command_name)
    try:
        res = cmd(*args, **kwargs)
        if asyncio.iscoroutine(res):
            res = await asyncio.wait_for(res, timeout=timeout)
        return res
    except Exception as e:
        logging.warning("Aviso ejecutando comando de radio '%s': %s", command_name, e)
        return fallback


def is_empty_channel_slot(name: Any, secret: Any = None) -> bool:
    """Determina si una ranura de canal está vacía o sin configurar en el firmware.

    Una ranura se considera vacía cuando el nombre es nulo/vacío y la clave es nula,
    cadena vacía, bytes nulos (b'\\x00' * 16) o secuencia hexadecimal de ceros.
    """
    clean_name = str(name or "").strip()
    if clean_name:
        return False

    if secret is None:
        return True

    if isinstance(secret, (bytes, bytearray)):
        return not any(secret)

    sec_str = str(secret).strip()
    if not sec_str:
        return True

    if sec_str.startswith("b'") and sec_str.endswith("'"):
        inner = sec_str[2:-1]
        if not inner or inner.replace("\\x00", "") == "":
            return True

    clean_hex = sec_str.replace("0x", "").replace(" ", "").replace("-", "")
    return not clean_hex or all(c == "0" for c in clean_hex)




import logging

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
    except ValueError:
        return "CLIENT"


def normalize_battery(raw_value: int) -> tuple[float, float]:
    """Conversión canónica de valor crudo de batería a porcentaje y voltaje.

    El firmware MeshCore reporta batería en diferentes formatos según hardware:
    - 0-100: Porcentaje directo
    - 101-255: Valor ADC que requiere conversión
    - 300-420: Voltaje en centésimas (3.00V - 4.20V)

    Args:
        raw_value: Valor crudo reportado por el firmware.

    Returns:
        Tupla (porcentaje, voltaje_estimado).
    """
    if raw_value <= 0:
        return 0.0, 0.0

    if 1 <= raw_value <= 100:
        percent = float(raw_value)
        voltage = 3.0 + (percent / 100.0) * 1.2
        return percent, round(voltage, 2)

    if 101 <= raw_value <= 255:
        percent = round((raw_value / 255.0) * 100.0, 1)
        voltage = 3.0 + (raw_value / 255.0) * 1.2
        return percent, round(voltage, 2)

    if 300 <= raw_value <= 420:
        voltage = raw_value / 100.0
        percent = max(0.0, min(100.0, ((voltage - 3.0) / 1.2) * 100.0))
        return round(percent, 1), round(voltage, 2)

    logging.warning("Valor de batería fuera de rango: %d", raw_value)
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

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

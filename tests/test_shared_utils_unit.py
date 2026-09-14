"""
Unit tests for shared_utils (Canonical Device Role, Power Limits, Battery Normalization, Repeater Detection).
"""

from src.protocol_types import FirmwareAdvertType
from src.shared_utils import (
    clamp_tx_power,
    classify_device_role,
    get_hardware_power_limits,
    is_repeater_name,
    normalize_battery,
)


def test_classify_device_role() -> None:
    # Caso local
    assert classify_device_role(0, is_local=True) == "LOCAL"
    assert classify_device_role(2, is_local=True) == "LOCAL"

    # Casos estándar según FirmwareAdvertType
    assert classify_device_role(FirmwareAdvertType.NONE) == "CLIENT"
    assert classify_device_role(FirmwareAdvertType.CHAT) == "CLIENT"
    assert classify_device_role(FirmwareAdvertType.REPEATER) == "REPEATER"
    assert classify_device_role(FirmwareAdvertType.ROOM) == "ROOM"
    assert classify_device_role(FirmwareAdvertType.SENSOR) == "SENSOR"

    # Valor desconocido
    assert classify_device_role(99) == "CLIENT"


def test_normalize_battery() -> None:
    # 0 o negativo
    assert normalize_battery(0) == (0.0, 0.0)
    assert normalize_battery(-10) == (0.0, 0.0)

    # 1..100: Porcentaje directo
    pct, volt = normalize_battery(85)
    assert pct == 85.0
    assert volt > 3.0

    # 101..255: Valor ADC
    pct_adc, volt_adc = normalize_battery(200)
    assert 0.0 < pct_adc <= 100.0
    assert 3.0 < volt_adc <= 4.2

    # 300..420: Centésimas de voltio (3.00V - 4.20V)
    pct_mv, volt_mv = normalize_battery(370)
    assert volt_mv == 3.70
    assert 50.0 <= pct_mv <= 65.0

    # Fuera de rango
    assert normalize_battery(500) == (0.0, 0.0)


def test_get_hardware_power_limits_and_clamp() -> None:
    # SX1262 (Heltec V3)
    min_p, max_p, def_p = get_hardware_power_limits("Heltec V3")
    assert min_p == 2
    assert max_p == 22
    assert def_p == 20

    # SX1276 (Heltec V2)
    min_p2, max_p2, def_p2 = get_hardware_power_limits("Heltec V2")
    assert min_p2 == 2
    assert max_p2 == 20
    assert def_p2 == 17

    # High power PA (E22_30DBM)
    min_pa, max_pa, def_pa = get_hardware_power_limits("E22_900M30S")
    assert min_pa == 10
    assert max_pa == 30
    assert def_pa == 27

    # Con max_tx_power_hint explícito
    min_h, max_h, def_h = get_hardware_power_limits(max_tx_power_hint=14)
    assert max_h == 14
    assert min_h == 0

    # Clamping
    assert clamp_tx_power(25, "Heltec V3") == 22
    assert clamp_tx_power(1, "Heltec V3") == 2
    assert clamp_tx_power(15, "Heltec V3") == 15
    assert clamp_tx_power(35, "E22_30DBM") == 30


def test_is_repeater_name() -> None:
    # Prefijos canónicos
    assert is_repeater_name("R-Centro") is True
    assert is_repeater_name("REP-Torre-1") is True
    assert is_repeater_name("ROUTER-Cerro") is True
    assert is_repeater_name("R1-Norte") is True

    # Substrings
    assert is_repeater_name("Heltec Repeater Montaña") is True
    assert is_repeater_name("Repetidor Solar") is True
    assert is_repeater_name("Mesh Router") is True

    # No repetidores
    assert is_repeater_name("Scout Mobile") is False
    assert is_repeater_name("Usuario Alice") is False
    assert is_repeater_name("") is False
    assert is_repeater_name(None) is False  # type: ignore

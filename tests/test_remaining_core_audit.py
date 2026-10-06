"""Regressions for individual telemetry, FIFO and capture pagination findings."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.contact_manager import NodeContactInfo, NodeContactUpdate, NodeRegistry
from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.packet_buffer import PacketBuffer
from src.rate_limiter import CustomTxQueue, TxItem
from src.sensor_decoder import CayenneLPPDecoder, extract_telemetry_fields


def test_equal_priority_fifo_ignores_wall_clock_changes() -> None:
    queue = CustomTxQueue(maxsize=10)
    queue.put_nowait(TxItem(priority=1, counter=1, created_at=100, payload="first"))
    queue.put_nowait(TxItem(priority=1, counter=2, created_at=90, payload="second"))
    assert [queue.get_nowait().payload, queue.get_nowait().payload] == ["first", "second"]
    queue.task_done()
    queue.task_done()


@pytest.mark.parametrize("source,expected", [
    ({"solar_mv": 100}, 0.1), ({"solar_mv": 0}, 0.0),
    ({"solar_v": 120}, 120.0), ({"solar_voltage": 0.1}, 0.1),
])
def test_solar_explicit_unit_wins_over_magnitude(source: dict[str, object], expected: float) -> None:
    assert extract_telemetry_fields(source)["solar_v"] == expected


@pytest.mark.parametrize("value,expected", [("false", False), ("true", True), (0, False), (1, True)])
def test_position_boolean_is_interpreted(value: object, expected: bool) -> None:
    assert extract_telemetry_fields({"fixed_position": value})["fixed_position"] is expected


@pytest.mark.parametrize("value", ["garbage", 2, 0.5, [], float("nan")])
def test_unknown_position_flag_does_not_invent_state(value: object) -> None:
    assert "fixed_position" not in extract_telemetry_fields({"fixed_position": value})


def test_lpp_current_keeps_following_temperature() -> None:
    readings, summary = CayenneLPPDecoder.decode(bytes.fromhex("01750064026700fa"))
    assert len(readings) == 2 and readings[0].value == 0.1 and readings[0].unit == "A"
    assert summary["temperature_c"] == 25.0


@pytest.mark.parametrize("type_code,raw,expected", [
    (100, "0000002a", 42), (117, "ff9c", -0.1), (118, "000003e8", 1000),
    (121, "fffe", -2), (122, "ffff9c", -0.1), (125, "001e", 30),
    (128, "0064", 100), (130, "000003e8", 1.0), (131, "000003e8", 1.0),
    (132, "005a", 90), (133, "6553f100", 1700000000), (142, "01", 1),
])
def test_extended_lpp_scalar_layout(type_code: int, raw: str, expected: float) -> None:
    readings, summary = CayenneLPPDecoder.decode(bytes([1, type_code]) + bytes.fromhex(raw) + bytes.fromhex("026700fa"))
    assert readings[0].value == expected
    assert summary["temperature_c"] == 25.0


def test_lpp_colour_preserves_record_boundary() -> None:
    readings, summary = CayenneLPPDecoder.decode(bytes.fromhex("0187ff8000026700fa"))
    assert readings[0].value == {"red": 255, "green": 128, "blue": 0}
    assert summary["temperature_c"] == 25.0


def test_capture_desc_returns_tail_with_existing_asc_unchanged() -> None:
    buffer = PacketBuffer()
    for index in range(250):
        buffer.record(text=str(index))
    oldest, total = buffer.get_packets(limit=200)
    latest, _ = buffer.get_packets(limit=200, order="desc")
    page, _ = buffer.get_packets(limit=2, offset=1, order="desc")
    assert total == 250 and oldest[0]["text"] == "0"
    assert latest[0]["text"] == "249" and latest[-1]["text"] == "50"
    assert [item["text"] for item in page] == ["248", "247"]


def test_capture_session_and_clear_do_not_reuse_packet_identity() -> None:
    first, second = PacketBuffer(), PacketBuffer()
    one, two = first.record(text="1"), second.record(text="2")
    assert one and two and one.packet_id == two.packet_id
    assert one.to_dict()["session_id"] != two.to_dict()["session_id"]
    first.clear()
    three = first.record(text="3")
    assert three and three.packet_id > one.packet_id and three.session_id == one.session_id


def test_remote_power_unknown_and_observed_are_distinct() -> None:
    node = NodeContactInfo(public_key="ab" * 32, hardware_board="Heltec V3")
    assert node.to_dict()["max_tx_power"] is None
    assert node.to_dict()["tx_power_limits_source"] == "unknown"
    node = NodeContactInfo(public_key="ab" * 32, hardware_board="Heltec V3", max_tx_power=30)
    assert node.to_dict()["max_tx_power"] == 30
    assert node.to_dict()["min_tx_power"] is None
    assert node.to_dict()["tx_power_limits_source"] == "observed"


def test_registry_name_lookup_has_no_unused_index(tmp_path) -> None:
    registry = NodeRegistry()
    key = "ab" * 32
    registry.add_or_update(key, NodeContactUpdate(name="original", alias="alias"))
    assert registry.find_by_name("alias").public_key == key
    registry.add_or_update(key, NodeContactUpdate(name="new", alias="changed"))
    assert registry.find_by_name("original") is None
    assert registry.find_by_name("changed").public_key == key
    registry.add_or_update("cd" * 32, NodeContactUpdate(name="new"))
    assert registry.find_by_name("new") is None
    path = tmp_path / "registry.json"
    assert registry.save_to_file(path, force=True)
    loaded = NodeRegistry()
    loaded.load_from_file(path)
    assert loaded.find_by_name("changed").public_key == key
    assert loaded.remove_node(key)
    assert loaded.find_by_name("changed") is None
    assert not hasattr(loaded, "_nodes_by_name")


def test_mqtt_expiry_request_is_not_silently_ignored() -> None:
    client = AsyncBridgeMQTTClient(MQTTConfig())
    client.client = MagicMock()
    client.is_connected = True
    assert not client.publish_safe("virtual/topic", "{}", ttl_seconds=30)
    client.client.publish.assert_not_called()
    client.client.publish.return_value.rc = 0
    assert client.publish_safe("virtual/topic", "{}")


@pytest.mark.parametrize("type_name,key,value", [
    ("current", "current_a", -0.1), ("117", "current_a", -0.1),
    ("direction", "direction_deg", [90]), ("generic sensor", "generic_sensor", 42),
])
def test_sdk_extended_types_match_binary_summary(type_name: str, key: str, value: object) -> None:
    summary = extract_telemetry_fields({"lpp": [{"channel": 1, "type": type_name, "value": value}]})
    assert summary[key] == (value[0] if isinstance(value, list) else value)


def test_current_battery_millivolts_keep_precision() -> None:
    assert extract_telemetry_fields({"battery_mv": 3875})["voltage_v"] == 3.875

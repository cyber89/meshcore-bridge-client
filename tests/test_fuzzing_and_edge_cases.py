import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from meshcore_bridge import MeshCoreBridge
from src.protocol_types import (
    EOF_BYTE,
    ESC_BYTE,
    SOF_BYTE,
    FrameHeader,
    MeshcoreFrame,
    OpCode,
    TextMessagePayload,
)
from src.serial_driver import RawSerialFramingAdapter


class DummyEventType:
    def __init__(self, name):
        self.name = name


class DummyEvent:
    def __init__(self, ev_type, payload):
        self.type = ev_type
        self.payload = payload


@pytest.fixture
def bridge_setup():
    loop = asyncio.new_event_loop()
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db_path = temp_db.name
    temp_db.close()

    bridge = MeshCoreBridge(loop, db_path=temp_db_path)
    published = []
    bridge.mqtt.publish_safe = MagicMock(side_effect=lambda t, p, qos=0, retain=False: published.append((t, p)))
    bridge.mqtt_client = MagicMock()
    bridge.mqtt_client.publish.side_effect = lambda t, p, qos=0, retain=False: published.append((t, p))
    bridge.mqtt_connected = True
    bridge.mqtt.is_connected = MagicMock(return_value=True)

    mock_mc = MagicMock()
    mock_mc.commands = MagicMock()
    mock_mc.commands.send_chan_msg = AsyncMock(return_value=DummyEvent("OK", {}))
    mock_mc.commands.send_msg = AsyncMock(return_value=DummyEvent("OK", {}))
    mock_mc.commands.set_name = AsyncMock(return_value=DummyEvent("OK", {}))
    mock_mc.commands.set_tx_power = AsyncMock(return_value=DummyEvent("OK", {}))
    mock_mc.commands.req_telemetry = AsyncMock(return_value=DummyEvent("OK", {}))
    mock_mc.commands.reboot = AsyncMock(return_value=DummyEvent("OK", {}))
    mock_mc.contacts = []
    mock_mc.self_info = {"name": "TestNode", "radio_freq": 915.0}
    bridge.mc = mock_mc
    bridge.serial_adapter.is_connected = True
    bridge.serial_adapter.send_message = AsyncMock(return_value={"status": "SENT"})

    yield bridge, loop, published, mock_mc

    loop.close()
    try:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
        for ext in ["-wal", "-shm"]:
            wal_f = temp_db_path + ext
            if os.path.exists(wal_f):
                os.remove(wal_f)
    except Exception:
        pass


@pytest.mark.parametrize("raw_bytes", [
    b"",
    b"   ",
    b"null",
    b"true",
    b"12345",
    b"[1, 2, 3]",
    b"{not a valid json:",
    b"\x00\x01\x02\xff",
    ('{"text": "' + ('A' * 10000) + '"}').encode("utf-8"),
    b'{"to": null, "channel_index": null, "text": "Test"}',
    b'{"to": 12345, "channel_index": "invalido", "text": 67890}',
])
def test_mqtt_fuzzing_malformed_and_weird_payloads(bridge_setup, raw_bytes):
    """Prueba mensajes MQTT con tipos de datos extraños sin que el servicio se bloquee."""
    bridge, loop, published, mock_mc = bridge_setup
    msg_mock = MagicMock()
    msg_mock.topic = "meshcore/tx"
    msg_mock.payload = raw_bytes

    try:
        bridge.on_mqtt_message(bridge.mqtt_client, None, msg_mock)
        loop.run_until_complete(asyncio.sleep(0.005))
    except Exception as e:
        pytest.fail(f"on_mqtt_message falló con payload {raw_bytes}: {e}")


@pytest.mark.parametrize("text", [
    "'; DROP TABLE offline_queue; --",
    "\" OR \"1\"=\"1",
    "SELECT * FROM offline_queue WHERE id = 1; DELETE FROM offline_queue;",
    "Emojis: 🚀🔥📻📡🛰️ ñandú áéíóú Ç",
    "Líneas múltiples\n\r\tcon saltos\ny comillas ' \" `",
    "Caracteres de control: \x00\x07\x08\x1b",
])
def test_sql_injection_and_special_characters_in_sqlite(bridge_setup, text):
    """Verifica que strings con inyección SQL y caracteres especiales se procesen sin fallos."""
    bridge, loop, published, mock_mc = bridge_setup
    bridge.mqtt_connected = True

    bridge.publish_mqtt_safe("meshcore/rx/all", text, qos=0)
    assert len(published) == 1
    assert published[0][1] == text


def test_extreme_numerical_values_in_tx_and_admin(bridge_setup):
    """Prueba valores fuera de rango en potencia y canales de transmisión."""
    bridge, loop, published, mock_mc = bridge_setup

    tx_data = {
        "to": "broadcast",
        "channel_index": 9999999,
        "text": "Prueba canal extremo",
    }
    res = loop.run_until_complete(bridge._execute_tx(tx_data))
    assert res is not None

    admin_data = {
        "action": "set_tx_power",
        "power": 5000,
        "request_id": "test_pow_99",
    }
    loop.run_until_complete(bridge.handle_admin(admin_data))


@pytest.mark.parametrize("ev", [
    DummyEvent(None, None),
    DummyEvent("UNKNOWN_EVENT_123", {"data": "algo"}),
    DummyEvent(12345, "string payload"),
    DummyEvent("CHANNEL_MSG_RECV", None),
    DummyEvent("CHANNEL_MSG_RECV", "no es un dict"),
    DummyEvent("CHANNEL_MSG_RECV", {"text": "", "sender": None}),
    DummyEvent("CONTACT_MSG_RECV", {"message": None, "sender": 12345}),
    DummyEvent("TELEMETRY", {"voltage": "invalido", "battery": None}),
    DummyEvent("ADVERT", {"pubkey": None, "name": 9999}),
])
def test_radio_event_fuzzing_corrupt_structures(bridge_setup, ev):
    """Prueba eventos de radio entrantes con estructuras corruptas o tipos no dict."""
    bridge, loop, published, mock_mc = bridge_setup
    try:
        bridge.on_mesh_event(ev)
    except Exception as e:
        pytest.fail(f"on_mesh_event falló con evento corrupto {ev}: {e}")


def test_radio_commands_returning_error_events(bridge_setup):
    """Verifica que si la radio SX1262 retorna un evento de error, el bridge lo capture y publique ACK de error."""
    bridge, loop, published, mock_mc = bridge_setup
    error_event = DummyEvent("ERROR", {"code": "ERR_BUSY", "message": "Canal LoRa ocupado"})
    mock_mc.commands.send_chan_msg = AsyncMock(return_value=error_event)
    bridge.serial_adapter.send_message = AsyncMock(return_value={"status": "ERROR", "event": error_event})

    tx_data = {
        "request_id": "req_err_test",
        "to": "broadcast",
        "channel_index": 0,
        "text": "Mensaje que fallará"
    }
    loop.run_until_complete(bridge._execute_tx(tx_data))

    status_publishes = [p for t, p in published if "tx/status" in t]
    assert len(status_publishes) > 0
    status_json = json.loads(status_publishes[-1])
    assert status_json["status"] == "error"
    assert status_json["request_id"] == "req_err_test"


@pytest.mark.parametrize("data", [
    {"action": "accion_inexistente"},
    {"action": "set_name"},
    {"action": "set_tx_power"},
    {"action": "req_telemetry"},
    {"action": None},
    {},
])
def test_admin_commands_unhandled_and_missing_parameters(bridge_setup, data):
    """Prueba comandos de administración con acciones inexistentes y campos faltantes."""
    bridge, loop, published, mock_mc = bridge_setup
    published.clear()
    loop.run_until_complete(bridge.handle_admin(data))
    assert len(published) > 0
    res = json.loads(published[0][1])
    assert "status" in res


def _generate_valid_frame() -> bytes:
    payload = TextMessagePayload(channel_idx=0, sender_alias="test", text="hello")
    raw = payload.pack()
    header = FrameHeader(
        opcode=OpCode.TEXT_MSG,
        seq_num=1,
        src_node_id=10,
        dst_node_id=20,
        hop_limit=3,
        payload_len=len(raw)
    )
    frame = MeshcoreFrame(header=header, payload=payload, raw_payload=raw, crc16=0, is_valid=True)
    return frame.serialize()


def test_corrupt_crc_rejected():
    adapter = RawSerialFramingAdapter("AUTO")
    frame_bytes = bytearray(_generate_valid_frame())
    frame_bytes[-2] ^= 0xFF
    frames = adapter.process_incoming_bytes(frame_bytes)
    assert len(frames) == 0


def test_truncated_frame_before_eof():
    adapter = RawSerialFramingAdapter("AUTO")
    frame_bytes = _generate_valid_frame()
    truncated = frame_bytes[:-1]
    frames = adapter.process_incoming_bytes(truncated)
    assert len(frames) == 0


def test_missing_sof_delimiter():
    adapter = RawSerialFramingAdapter("AUTO")
    frame_bytes = _generate_valid_frame()
    missing_sof = frame_bytes[1:]
    frames = adapter.process_incoming_bytes(missing_sof)
    assert len(frames) == 0


def test_malformed_escape_sequence():
    adapter = RawSerialFramingAdapter("AUTO")
    frame_bytes = bytearray([SOF_BYTE, 0x01, 0x02, ESC_BYTE, SOF_BYTE, EOF_BYTE])
    frames = adapter.process_incoming_bytes(frame_bytes)
    assert len(frames) == 0

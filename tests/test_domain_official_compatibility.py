"""Observable regressions for official roles, identities and safe receive routing."""

from __future__ import annotations

import asyncio
import json
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cayennelpp import LppFrame
from meshcore.events import Event, EventType

from src.contact_manager import NodeContactUpdate, NodeDiscoveryEvent, NodeRegistry
from src.protocol_types import (
    AckPayload,
    FrameHeader,
    MeshcoreFrame,
    NodeAdvertisement,
    PacketType,
    TelemetryPayload,
    TextMessagePayload,
    compute_crc16_ccitt,
)
from src.routers.advert_handler import AdvertHandler
from src.routers.base import MeshMessageEvent, RxMeta
from src.routers.repeater_handler import RepeaterAdminHandler
from src.routers.system_handler import SystemHandler
from src.rx_router import RxEventRouter
from src.sensor_decoder import CayenneLPPDecoder
from src.target_resolver import TargetResolver

KEY_A = "aabbccdd" + "11" * 28
KEY_B = "aabbccdd" + "22" * 28


def _meta(event_type: str, *, is_local: bool = False) -> RxMeta:
    return RxMeta(event_type, event_type.upper(), KEY_A, "R-Client", "", 0, 0, -80, 8.0, 0, is_local)


def _ctx(registry: NodeRegistry | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        node_registry=registry or NodeRegistry(), mqtt=MagicMock(), web_server=None,
        serial_adapter=MagicMock(), repeater_manager=MagicMock(),
        deduplicator=SimpleNamespace(is_duplicate=AsyncMock(return_value=False)),
        loop=asyncio.get_running_loop(), background_tasks=set(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0),
        admin_handler=MagicMock(), packet_buffer=None, bridge=None,
        last_rx_rssi=None, last_rx_snr=None,
    )


@pytest.mark.parametrize("name", ["R-Client", "REPEATER Tourist", "ROOMmate", "SENSOR enthusiast"])
def test_official_client_role_is_not_inferred_from_name(name: str) -> None:
    registry = NodeRegistry()
    _, node = registry.discover_node(NodeDiscoveryEvent(KEY_A, name=name, role="CLIENT"))
    assert node.role == "CLIENT"
    assert not registry.is_repeater_key(KEY_A)
    assert [item["public_key"] for item in registry.list_client_contacts()] == [KEY_A]


def test_latest_official_advert_can_correct_previous_role() -> None:
    registry = NodeRegistry()
    registry.discover_node(NodeDiscoveryEvent(KEY_A, name="Alice", role="REPEATER"))
    _, node = registry.discover_node(NodeDiscoveryEvent(KEY_A, name="Alice", role="CLIENT"))
    assert node.role == "CLIENT"


def test_distinct_full_keys_with_identical_names_are_not_merged() -> None:
    registry = NodeRegistry()
    registry.add_or_update(KEY_A, NodeContactUpdate(name="Alice", role="CLIENT"))
    registry.add_or_update(KEY_B, NodeContactUpdate(name="Alice", role="CLIENT"))
    assert {item["public_key"] for item in registry.list_nodes()} == {KEY_A, KEY_B}


def test_ambiguous_prefix_never_selects_first_registry_node() -> None:
    registry = NodeRegistry()
    registry.add_or_update(KEY_A, NodeContactUpdate(name="Alice"))
    registry.add_or_update(KEY_B, NodeContactUpdate(name="Bob"))
    assert registry.get_by_key_or_prefix("aabbccdd") is None
    assert len(registry.list_nodes()) == 2


def test_unknown_short_target_cannot_be_fabricated_by_zero_padding() -> None:
    with pytest.raises(ValueError):
        TargetResolver().resolve("a1b2c3", min_hex_len=64)


def test_unique_registry_prefix_resolves_real_full_identity() -> None:
    registry = NodeRegistry()
    registry.add_or_update(KEY_A, NodeContactUpdate(name="Alice"))
    assert TargetResolver(node_registry=registry).resolve("aabbcc", min_hex_len=64) == KEY_A


@pytest.mark.parametrize("query", ["aabbccdd", "Alice"])
def test_ambiguous_sdk_target_is_rejected(query: str) -> None:
    first = {"public_key": KEY_A, "name": "Alice"}
    second = {"public_key": KEY_B, "name": "Alice"}
    sdk = SimpleNamespace(
        contacts={KEY_A: first, KEY_B: second},
        get_contact_by_name=lambda _q: first,
        get_contact_by_key_prefix=lambda _q: first,
    )
    with pytest.raises(ValueError):
        TargetResolver(mc_provider=sdk).resolve(query)


def test_full_key_is_exact_even_when_another_key_shares_first_eight_hex() -> None:
    first = {"public_key": KEY_A, "name": "Alice"}
    second = {"public_key": KEY_B, "name": "Bob"}
    sdk = SimpleNamespace(contacts={KEY_A: first, KEY_B: second})
    assert TargetResolver(mc_provider=sdk).resolve(KEY_B) == second


@pytest.mark.parametrize("declared,actual", [(5, b"ab"), (1, b"abc"), (256, b"x" * 257)])
@pytest.mark.parametrize("strict", [False, True])
def test_crc_valid_custom_frame_with_incoherent_length_is_rejected(declared: int, actual: bytes, strict: bool) -> None:
    header = FrameHeader(PacketType.RAW_DATA, 1, 2, 3, 0, declared)
    data = header.pack() + actual
    body = data + struct.pack(">H", compute_crc16_ccitt(data))
    with pytest.raises(ValueError):
        MeshcoreFrame.parse_raw_packet(body, strict=strict)


def test_custom_serializer_refuses_incoherent_header() -> None:
    frame = MeshcoreFrame(FrameHeader(PacketType.RAW_DATA, 1, 2, 3, 0, 10), b"ab", b"ab", 0, True)
    with pytest.raises(ValueError):
        frame.serialize()


def test_unknown_lpp_type_does_not_reinterpret_its_bytes_as_temperature() -> None:
    readings, summary = CayenneLPPDecoder.decode(bytes([1, 250, 2, 103, 0, 200]))
    assert "temperature_c" not in summary
    assert all(reading.type_name != "temperature" for reading in readings)


def test_lpp_gyrometer_matches_sdk_dependency_decoder() -> None:
    raw = bytes([1, 134]) + struct.pack(">hhh", 123, -456, 789)
    official = LppFrame.from_bytes(raw).data[0].value
    readings, _ = CayenneLPPDecoder.decode(raw)
    assert len(readings) == 1
    assert readings[0].value == {"x": official[0], "y": official[1], "z": official[2]}


@pytest.mark.asyncio
@pytest.mark.parametrize("name,advert_type,role", [("R-Client", 1, "CLIENT"), ("ROOMmate", 1, "CLIENT"), ("SENSOR enthusiast", 2, "REPEATER"), ("R-Room", 3, "ROOM")])
async def test_advert_handler_uses_firmware_type_before_name(name: str, advert_type: int, role: str) -> None:
    ctx = _ctx()
    router = RxEventRouter(ctx)
    raw = {"public_key": KEY_A, "adv_name": name, "type": advert_type}
    await AdvertHandler().handle(router, dict(raw), _meta("CONTACT"), raw)
    assert ctx.node_registry.get(KEY_A).role == role


@pytest.mark.asyncio
async def test_named_official_client_chat_is_delivered_as_chat() -> None:
    registry = NodeRegistry()
    registry.add_or_update(KEY_A, NodeContactUpdate(name="R-Client", role="CLIENT"))
    ctx = _ctx(registry)
    ctx.repeater_manager.parse_repeater_telemetry_or_response.return_value = {}
    router = RxEventRouter(ctx)
    result = await router._handle_mesh_msg_common(MeshMessageEvent(KEY_A, "R-Client", "Hola amigos", 0), "channel")
    assert result is not None
    ctx.admin_handler.notify_command_response.assert_not_called()


@pytest.mark.asyncio
async def test_client_temperature_does_not_reclassify_firmware_role() -> None:
    registry = NodeRegistry()
    registry.add_or_update(KEY_A, NodeContactUpdate(name="Alice", role="CLIENT"))
    ctx = _ctx(registry)
    RxEventRouter(ctx)._handle_mesh_telemetry_msg({"sender": KEY_A, "temperature_c": 20})
    assert registry.get(KEY_A).role == "CLIENT"


@pytest.mark.asyncio
async def test_invalid_custom_frame_never_publishes_mqtt() -> None:
    ctx = _ctx()
    frame = MeshcoreFrame(FrameHeader(PacketType.RAW_DATA, 1, 2, 3, 0, 1), b"x", b"x", 0, False)
    await RxEventRouter(ctx)._dispatch_parsed_frame(frame)
    ctx.mqtt.publish_safe.assert_not_called()


@pytest.mark.asyncio
async def test_private_key_sdk_response_never_reaches_public_sinks(caplog: pytest.LogCaptureFixture) -> None:
    ctx = _ctx()
    router = RxEventRouter(ctx)
    secret = b"secret-material-" * 4
    router.handle_event(Event(EventType.PRIVATE_KEY, {"private_key": secret}))
    if ctx.background_tasks:
        await asyncio.gather(*list(ctx.background_tasks))
    assert ctx.counters.err_count == 0
    ctx.mqtt.publish_safe.assert_not_called()
    assert secret.hex() not in caplog.text


@pytest.mark.asyncio
async def test_nested_secrets_in_system_events_are_removed_before_publish(caplog: pytest.LogCaptureFixture) -> None:
    ctx = _ctx()
    raw = {"event_type": "custom_vars", "safe": 42, "nested": {"password": "unique-private-secret", "ok": 1}}
    await SystemHandler().handle(ctx, raw, _meta("CUSTOM_VARS"), raw)
    encoded = ctx.mqtt.publish_safe.call_args.args[1]
    assert "unique-private-secret" not in encoded
    assert json.loads(encoded)["safe"] == 42
    assert "unique-private-secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [0, "00000000", "garbage", "1234", True, "1234567890"])
async def test_invalid_ack_cannot_confirm_message(code: object) -> None:
    ctx = _ctx()
    await RepeaterAdminHandler().handle(ctx, {"code": code, "msg_id": "untrusted-id"}, _meta("ACK"), None)
    ctx.mqtt.publish_safe.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_local_ack_does_not_confirm_remote_delivery() -> None:
    ctx = _ctx()
    await RepeaterAdminHandler().handle(ctx, {"code": "12345678", "msg_id": "x"}, _meta("ACK", is_local=True), None)
    ctx.mqtt.publish_safe.assert_not_called()


@pytest.mark.parametrize("declared,actual", [(5, b"hi"), (1, b"hello")])
def test_custom_text_inner_length_cannot_hide_missing_or_extra_data(declared: int, actual: bytes) -> None:
    raw = struct.pack("<B16sB", 0, b"Alice", declared) + actual
    with pytest.raises(ValueError):
        TextMessagePayload.unpack(raw)


@pytest.mark.parametrize("decoder,size", [(AckPayload, 2), (TelemetryPayload, 16), (NodeAdvertisement, 39)])
def test_custom_fixed_payloads_refuse_trailing_bytes(decoder: object, size: int) -> None:
    with pytest.raises(ValueError):
        decoder.unpack(bytes(size + 1))

"""
Unit test suite for modular RxRouter Strategy Pattern handlers and RxEventRouter.
Covers:
- BaseRxHandler and RxMeta
- AdvertHandler
- ChannelMessageHandler
- DirectMessageHandler
- RepeaterAdminHandler
- TelemetryHandler
- SystemHandler
- RxEventRouter dispatch & concurrency
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.contact_manager import NodeContactInfo, NodeRegistry
from src.protocol_types import FirmwareAdvertType, MeshcoreFrame
from src.routers.advert_handler import AdvertHandler
from src.routers.base import MeshMessageEvent, RxMeta
from src.routers.channel_handler import ChannelMessageHandler
from src.routers.direct_handler import DirectMessageHandler
from src.routers.repeater_handler import RepeaterAdminHandler
from src.routers.system_handler import SystemHandler
from src.routers.telemetry_handler import TelemetryHandler
from src.rx_router import RxEventRouter, RxRouterContext


def _dummy_meta(
    ev_type: str = "TEXT",
    sender: str = "a1b2c3d4e5f60102030405060708090a1b2c3d4e5f60102030405060708090a1",
    sender_name: str = "TestNode",
    text: str = "",
    channel_idx: int = 0,
    hops: int = 1,
    is_local: bool = False,
) -> RxMeta:
    return RxMeta(
        ev_type_str=ev_type,
        ev_upper=ev_type.upper(),
        sender=sender,
        sender_name=sender_name,
        text=text,
        channel_idx=channel_idx,
        hops=hops,
        effective_rssi=-75,
        effective_snr=9.5,
        effective_hops=hops,
        is_local_sender=is_local,
    )


class TestRxMetaAndEvent:
    def test_mesh_message_event_dataclass(self) -> None:
        ev = MeshMessageEvent(
            sender="node1",
            sender_name="Alice",
            text="Testing 123",
            channel_idx=1,
            rssi=-80,
            snr=10.0,
            txt_type=0,
        )
        assert ev.sender == "node1"
        assert ev.sender_name == "Alice"
        assert ev.channel_idx == 1
        assert ev.rssi == -80
        assert ev.snr == 10.0

    def test_rx_meta_slots(self) -> None:
        meta = _dummy_meta(ev_type="ADVERT", sender="pubkey123")
        assert meta.ev_type_str == "ADVERT"
        assert meta.ev_upper == "ADVERT"
        assert meta.sender == "pubkey123"
        assert not meta.is_local_sender


class TestAdvertHandler:
    @pytest.fixture
    def handler(self) -> AdvertHandler:
        return AdvertHandler()

    def test_can_handle_matching_advert_types(self, handler: AdvertHandler) -> None:
        for t in ["advert", "new_advert", "advertisement", "ADVERT_PATH"]:
            meta = _dummy_meta(ev_type=t, text="")
            assert handler.can_handle(meta, {}) is True

    def test_cannot_handle_unrelated_or_text_types(self, handler: AdvertHandler) -> None:
        for t in ["chat", "channel_msg", "telemetry", "system_log", "ping"]:
            meta = _dummy_meta(ev_type=t, text="Some text")
            assert handler.can_handle(meta, {}) is False

    @pytest.mark.asyncio
    async def test_handle_advert_creates_node_contact(self, handler: AdvertHandler) -> None:
        mock_ctx = MagicMock()
        mock_ctx._ctx.node_registry = MagicMock(spec=NodeRegistry)
        mock_ctx._ctx.node_registry.discover_node.return_value = (True, MagicMock())
        mock_ctx._ctx.loop = asyncio.get_event_loop()
        mock_ctx._ctx.background_tasks = set()
        mock_ctx._resolve_sender_name.return_value = "Repeater Alpha"
        mock_ctx._deduplicator.is_duplicate.return_value = False

        valid_pk = "aabbccdd" * 8
        meta = _dummy_meta(ev_type="advert", sender=valid_pk, text="")
        payload = {
            "public_key": valid_pk,
            "name": "Repeater Alpha",
            "adv_type": int(FirmwareAdvertType.REPEATER),
            "lat": 23.1234,
            "lon": -82.4321,
            "hops": 2,
        }

        res = await handler.handle(mock_ctx, payload, meta, raw_event=None)
        assert res is True
        mock_ctx._ctx.node_registry.add_or_update.assert_called()


class TestChannelMessageHandler:
    @pytest.fixture
    def handler(self) -> ChannelMessageHandler:
        return ChannelMessageHandler()

    def test_can_handle_channel_events(self, handler: ChannelMessageHandler) -> None:
        for t in ["channel_msg_recv", "channel_msg"]:
            meta = _dummy_meta(ev_type=t, channel_idx=1, text="Hello channel!")
            assert handler.can_handle(meta, {}) is True

    def test_cannot_handle_empty_text_or_direct(self, handler: ChannelMessageHandler) -> None:
        meta_empty = _dummy_meta(ev_type="channel_msg_recv", text="")
        assert handler.can_handle(meta_empty, {}) is False

        meta_dm = _dummy_meta(ev_type="contact_msg_recv", text="Private")
        assert handler.can_handle(meta_dm, {}) is False

    @pytest.mark.asyncio
    async def test_handle_channel_message(self, handler: ChannelMessageHandler) -> None:
        mock_ctx = MagicMock()
        mock_ctx._ctx.loop = asyncio.get_event_loop()
        mock_ctx._ctx.background_tasks = set()
        mock_ctx._handle_mesh_channel_msg = AsyncMock()

        meta = _dummy_meta(ev_type="channel_msg_recv", text="Hello channel!", channel_idx=2)
        payload = {"text": "Hello channel!", "channel_idx": 2}

        res = await handler.handle(mock_ctx, payload, meta, raw_event=None)
        assert res is True
        # Da un tick al loop para que la corrutina planificada corra
        await asyncio.sleep(0.01)
        mock_ctx._handle_mesh_channel_msg.assert_called_once()


class TestDirectMessageHandler:
    @pytest.fixture
    def handler(self) -> DirectMessageHandler:
        return DirectMessageHandler()

    def test_can_handle_direct_events(self, handler: DirectMessageHandler) -> None:
        for t in ["contact_msg_recv", "contact_msg_recv_v3", "direct"]:
            meta = _dummy_meta(ev_type=t, text="Hello DM")
            assert handler.can_handle(meta, {}) is True

    def test_cannot_handle_channel_events(self, handler: DirectMessageHandler) -> None:
        meta = _dummy_meta(ev_type="channel_msg_recv", text="Hello channel")
        assert handler.can_handle(meta, {}) is False

    @pytest.mark.asyncio
    async def test_handle_direct_message_ignores_local_loopback(
        self, handler: DirectMessageHandler
    ) -> None:
        mock_ctx = MagicMock()
        meta = _dummy_meta(ev_type="contact_msg_recv", text="Self message", is_local=True)
        res = await handler.handle(mock_ctx, {}, meta, raw_event=None)
        assert res is True
        mock_ctx._handle_mesh_direct_msg.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_direct_message_dispatches(
        self, handler: DirectMessageHandler
    ) -> None:
        mock_ctx = MagicMock()
        mock_ctx._ctx.loop = asyncio.get_event_loop()
        mock_ctx._ctx.background_tasks = set()
        mock_ctx._handle_mesh_direct_msg = AsyncMock()

        meta = _dummy_meta(ev_type="contact_msg_recv", text="Secret message", is_local=False)
        payload = {"text": "Secret message"}

        res = await handler.handle(mock_ctx, payload, meta, raw_event=None)
        assert res is True
        await asyncio.sleep(0.01)
        mock_ctx._handle_mesh_direct_msg.assert_called_once()


class TestRepeaterAdminHandler:
    @pytest.fixture
    def handler(self) -> RepeaterAdminHandler:
        return RepeaterAdminHandler()

    def test_can_handle_repeater_events(self, handler: RepeaterAdminHandler) -> None:
        for t in ["ack", "trace", "message_delivered"]:
            meta = _dummy_meta(ev_type=t)
            assert handler.can_handle(meta, {"event_type": t}) is True

    @pytest.mark.asyncio
    async def test_handle_repeater_ack(self, handler: RepeaterAdminHandler) -> None:
        mock_ctx = MagicMock()
        mock_ctx._ctx.mqtt = MagicMock()
        mock_ctx._ctx.web_server = None

        meta = _dummy_meta(ev_type="ack")
        payload = {"event_type": "ack", "msg_id": "msg-123", "ack_code": 0, "trip_time_ms": 45}

        res = await handler.handle(mock_ctx, payload, meta, raw_event=None)
        assert res is True
        mock_ctx._ctx.mqtt.publish_safe.assert_called()


class TestTelemetryHandler:
    @pytest.fixture
    def handler(self) -> TelemetryHandler:
        return TelemetryHandler()

    def test_can_handle_telemetry_events(self, handler: TelemetryHandler) -> None:
        for t in ["telemetry", "repeater_telemetry", "stats_radio", "log_data"]:
            meta = _dummy_meta(ev_type=t)
            assert handler.can_handle(meta, {"event_type": t}) is True

    @pytest.mark.asyncio
    async def test_handle_telemetry_log(self, handler: TelemetryHandler) -> None:
        mock_ctx = MagicMock()
        mock_ctx._ctx.admin_handler = None
        mock_ctx._ctx.node_registry = MagicMock()

        meta = _dummy_meta(ev_type="log_data", sender="aabbccdd" * 8)
        payload = {"event_type": "log_data", "rssi": -85, "snr": 8.0}

        res = await handler.handle(mock_ctx, payload, meta, raw_event=None)
        assert res is True
        assert mock_ctx._ctx.last_rx_rssi == -85
        assert mock_ctx._ctx.last_rx_snr == 8.0


class TestSystemHandler:
    @pytest.fixture
    def handler(self) -> SystemHandler:
        return SystemHandler()

    def test_can_handle_system_events(self, handler: SystemHandler) -> None:
        for t in ["MESSAGES_WAITING", "STATUS_RESPONSE", "LOGIN_SUCCESS", "CONTACT_DELETED"]:
            meta = _dummy_meta(ev_type=t)
            assert handler.can_handle(meta, {}) is True

    @pytest.mark.asyncio
    async def test_handle_system_event(self, handler: SystemHandler) -> None:
        mock_ctx = MagicMock()
        mock_ctx._ctx.mqtt = MagicMock()

        meta = _dummy_meta(ev_type="MESSAGES_WAITING", text="")
        payload = {"event_type": "messages_waiting", "count": 3}

        res = await handler.handle(mock_ctx, payload, meta, raw_event=None)
        assert res is True
        mock_ctx._ctx.mqtt.publish_safe.assert_called_once()


class TestRxEventRouterIntegration:
    def test_router_initialization_handlers_list(self) -> None:
        mock_ctx = MagicMock()
        mock_ctx.loop = None
        mock_ctx.background_tasks = set()
        mock_ctx.serial_adapter = MagicMock()
        mock_ctx.counters = MagicMock(rx_count=0)

        router = RxEventRouter(mock_ctx)
        assert len(router._handlers) == 6
        assert isinstance(router._handlers[0], RepeaterAdminHandler)
        assert isinstance(router._handlers[1], DirectMessageHandler)
        assert isinstance(router._handlers[2], ChannelMessageHandler)
        assert isinstance(router._handlers[3], AdvertHandler)
        assert isinstance(router._handlers[4], TelemetryHandler)
        assert isinstance(router._handlers[5], SystemHandler)

    @pytest.mark.asyncio
    async def test_handle_event_meshcore_frame(self) -> None:
        loop = asyncio.get_running_loop()
        mock_ctx = MagicMock()
        mock_ctx.loop = loop
        mock_ctx.background_tasks = set()
        mock_ctx.serial_adapter = MagicMock()
        mock_ctx.packet_buffer = MagicMock()
        mock_ctx.deduplicator = MagicMock()
        mock_ctx.deduplicator.is_duplicate.return_value = False
        mock_ctx.node_registry = MagicMock()
        mock_ctx.counters = MagicMock(rx_count=0)

        from src.protocol_types import FrameHeader, PacketType

        header = FrameHeader(
            packet_type=PacketType.CONTACT_MSG_RECV,
            seq_num=1,
            src_node_id=0x1234,
            dst_node_id=0x5678,
            hop_limit=3,
            payload_len=4,
        )
        frame = MeshcoreFrame(
            header=header,
            payload=b"PING",
            raw_payload=b"PING",
            crc16=0x1234,
            is_valid=True,
        )

        router = RxEventRouter(mock_ctx)
        router.handle_event(frame)
        assert mock_ctx.counters.rx_count == 1
        mock_ctx.serial_adapter.heartbeat.assert_called_once()

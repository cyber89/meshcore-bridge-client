"""
Unit tests for REST API Controllers in src/web/controllers/
Directly tests isolated controllers without full HTTP server overhead.
"""

from __future__ import annotations

import collections
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.contact_manager import NodeContactInfo, NodeContactUpdate, NodeRegistry
from src.packet_buffer import PacketBuffer
from src.web.controllers.base import ApiContext
from src.web.controllers.channels_controller import ChannelsController
from src.web.controllers.config_controller import ConfigController
from src.web.controllers.contacts_controller import ContactsController
from src.web.controllers.nodes_controller import NodesController
from src.web.controllers.packets_controller import PacketsController
from src.web.controllers.repeater_controller import RepeaterController
from src.web.controllers.system_controller import SystemController
from src.web.controllers.tx_controller import TxController


@pytest.fixture
def api_context(tmp_path: Any) -> ApiContext:
    registry = NodeRegistry()
    registry.set_local_pubkey("aabbccddeeff1122")

    # Add sample client node and sample repeater node (must be valid hex keys)
    registry.add_or_update("1122334455667788", NodeContactUpdate(name="BobClient", role="CLIENT"))
    registry.add_or_update("bbccddeeff001122", NodeContactUpdate(name="RepeaterNorth", role="REPEATER"))

    mock_bridge = MagicMock()
    mock_bridge.node_registry = registry
    mock_bridge.start_time = time.time() - 3600
    mock_bridge.rx_count = 50
    mock_bridge.tx_count = 20
    mock_bridge.err_count = 1
    mock_bridge.tx_error_count = 0
    mock_bridge.dup_count = 2
    mock_bridge.last_rx_rssi = -80
    mock_bridge.last_rx_snr = 9.5

    mock_bridge.rate_limiter = MagicMock()
    mock_bridge.rate_limiter.get_queue_depth.return_value = 0
    mock_bridge.rate_limiter.airtime_tracker = MagicMock()
    mock_bridge.rate_limiter.airtime_tracker.get_stats.return_value = {
        "hourly_used_ms": 1200,
        "hourly_duty_cycle_pct": 0.033,
    }

    mock_serial = MagicMock()
    mock_serial.port = "/dev/ttyUSB0"
    mock_serial.is_connected = True
    mock_serial.is_hardware_alive.return_value = True
    mock_serial.get_channels = AsyncMock(return_value=[{"index": 0, "name": "Public", "psk": "", "is_public": True}])
    mock_serial.set_channel = AsyncMock(return_value=True)
    mock_serial.sync_all_contacts = AsyncMock(return_value=[{"public_key": "syncnode11223344", "name": "Synced"}])
    mock_serial.share_contact = AsyncMock(return_value=True)
    mock_serial.export_contact = AsyncMock(return_value="aabbcc")
    mock_serial.import_contact = AsyncMock(return_value=True)
    mock_serial.add_contact = AsyncMock(return_value=True)
    mock_serial.remove_contact = AsyncMock(return_value=True)
    mock_bridge.serial_adapter = mock_serial

    mock_admin = MagicMock()
    mock_admin.get_local_config.return_value = {"public_key": "local112233445566", "name": "BaseStation"}
    mock_admin.fetch_device_config = AsyncMock(return_value={"public_key": "local112233445566", "name": "BaseStation"})
    mock_admin.broadcast_advert = AsyncMock(return_value={"status": "ok", "action": "advert"})
    mock_bridge.admin_handler = mock_admin
    mock_bridge.handle_admin = AsyncMock(return_value={"status": "ok"})
    mock_bridge._execute_tx = AsyncMock(return_value={"status": "dispatched", "request_id": "req_1"})

    recent_msgs: collections.deque[dict[str, Any]] = collections.deque(maxlen=100)
    system_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=100)

    def log_sys(level: str, msg: str, source: str = "sys") -> None:
        system_logs.append({"timestamp": time.time(), "level": level, "message": msg, "source": source})

    packet_buf = PacketBuffer(max_packets=50)

    return ApiContext(
        bridge=mock_bridge,
        recent_messages=recent_msgs,
        system_logs=system_logs,
        log_system_event=log_sys,
        broadcast_ws=MagicMock(),
        start_time=mock_bridge.start_time,
        packet_buffer=packet_buf,
    )


# ------------------ TxController Tests ------------------

@pytest.mark.asyncio
async def test_tx_controller_validation(api_context: ApiContext) -> None:
    ctrl = TxController(api_context)

    # Empty text
    status, res = await ctrl.send_tx({"text": "", "to": "1122334455667788"})
    assert status == 400
    assert res["error"] == "missing_text_field"

    # Send to local node (prohibited)
    status, res = await ctrl.send_tx({"text": "Hello me", "to": "aabbccddeeff1122"})
    assert status == 400
    assert res["error"] == "tx_to_local_forbidden"

    # Send to repeater node (prohibited)
    status, res = await ctrl.send_tx({"text": "Hello repeater", "to": "bbccddeeff001122"})
    assert status == 400
    assert res["error"] == "tx_to_repeater_forbidden"

    # Invalid channel index
    status, res = await ctrl.send_tx({"text": "Hello", "to": "broadcast", "channel_index": "not_an_int"})
    assert status == 400
    assert res["error"] == "invalid_channel_index"

    # Valid broadcast
    status, res = await ctrl.send_tx({"text": "Hello Mesh", "to": "broadcast", "channel_index": 0})
    assert status == 200
    assert res["status"] == "ok"
    assert api_context.bridge._execute_tx.called


@pytest.mark.asyncio
async def test_tx_controller_recent_messages(api_context: ApiContext) -> None:
    ctrl = TxController(api_context)
    api_context.recent_messages.append({"sender": "Bob", "text": "Hi"})

    status, res = await ctrl.get_recent_messages()
    assert status == 200
    assert res["count"] == 1
    assert res["data"][0]["sender"] == "Bob"


# ------------------ ChannelsController Tests ------------------

@pytest.mark.asyncio
async def test_channels_controller_crud(api_context: ApiContext, tmp_path: Any) -> None:
    ch_file = str(tmp_path / "channels.json")
    ctrl = ChannelsController(api_context, channels_file=ch_file)

    # GET channels
    status, res = await ctrl.handle_channels_route("/api/channels", "GET", {})
    assert status == 200
    assert len(res["data"]) >= 1
    assert res["data"][0]["index"] == 0

    # POST create channel 1
    status, res = await ctrl.handle_channels_route("/api/channels", "POST", {"index": 1, "name": "Team", "psk": "secret"})
    assert status == 200
    assert res["data"]["name"] == "Team"

    # POST invalid channel index 9
    status, res = await ctrl.handle_channels_route("/api/channels", "POST", {"index": 9, "name": "Invalid"})
    assert status == 400
    assert res["error"] == "channel_index_out_of_bounds"

    # DELETE public channel 0 (forbidden)
    status, res = await ctrl.handle_channels_route("/api/channels", "DELETE", {"index": 0})
    assert status == 400
    assert res["error"] == "cannot_delete_public_channel"

    # DELETE channel 1 (success)
    status, res = await ctrl.handle_channels_route("/api/channels", "DELETE", {"index": 1})
    assert status == 200

    # DELETE non-existent channel
    status, res = await ctrl.handle_channels_route("/api/channels", "DELETE", {"index": 5})
    assert status == 404
    assert res["error"] == "channel_not_found"


# ------------------ ContactsController Tests ------------------

@pytest.mark.asyncio
async def test_contacts_controller(api_context: ApiContext) -> None:
    ctrl = ContactsController(api_context)

    # GET contacts
    status, res = await ctrl.handle_contacts_route("/api/contacts", "GET", {})
    assert status == 200
    assert res["count"] >= 1

    # POST create/update contact
    status, res = await ctrl.handle_contacts_route(
        "/api/contacts",
        "POST",
        {"public_key": "3344556677889900", "name": "Charlie", "role": "CLIENT"},
    )
    assert status == 200
    assert res["data"]["name"] == "Charlie"

    # POST without public key
    status, res = await ctrl.handle_contacts_route("/api/contacts", "POST", {"name": "NoKey"})
    assert status == 400
    assert res["error"] == "missing_public_key"

    # POST share contact
    status, res = await ctrl.handle_contacts_route("/api/contacts/share", "POST", {"public_key": "3344556677889900"})
    assert status == 200
    assert api_context.bridge.serial_adapter.share_contact.called

    # POST import contact with invalid hex
    status, res = await ctrl.handle_contacts_route("/api/contacts/import", "POST", {"data": "not_hex_zz"})
    assert status == 400
    assert res["error"] == "invalid_hex_data"

    # POST sync contacts
    status, res = await ctrl.handle_contacts_route("/api/contacts/sync", "POST", {})
    assert status == 200
    assert res["imported"] >= 1

    # DELETE contact
    status, res = await ctrl.handle_contacts_route("/api/contacts", "DELETE", {"public_key": "3344556677889900"})
    assert status == 200


# ------------------ NodesController Tests ------------------

@pytest.mark.asyncio
async def test_nodes_controller(api_context: ApiContext) -> None:
    ctrl = NodesController(api_context)

    status, res = await ctrl.list_nodes(limit=10, offset=0)
    assert status == 200
    assert "data" in res
    assert res["total_count"] >= 1

    status, res = await ctrl.get_lqi()
    assert status == 200
    assert "data" in res

    status, res = await ctrl.get_analytics()
    assert status == 200
    assert "summary" in res["data"]
    assert res["data"]["serial_connected"] is True


# ------------------ PacketsController Tests ------------------

@pytest.mark.asyncio
async def test_packets_controller(api_context: ApiContext) -> None:
    ctrl = PacketsController(api_context)

    # Insert a dummy packet into buffer using record
    api_context.packet_buffer.record(
        direction="RX",
        channel_idx=0,
        packet_type="CHAT",
        sender="1122334455667788",
        sender_name="Alice",
        text="Hello world",
        rssi=-70,
        snr=8.0,
    )

    status, res = await ctrl.get_packets(limit=10, offset=0)
    assert status == 200
    assert res["count"] == 1

    # Export formats
    status, pcap_res = await ctrl.export_packets("pcap")
    assert status == 200
    assert pcap_res["format"] == "pcap"
    assert "base64_data" in pcap_res

    status, csv_res = await ctrl.export_packets("csv")
    assert status == 200
    assert csv_res["format"] == "csv"

    status, json_res = await ctrl.export_packets("json")
    assert status == 200
    assert json_res["format"] == "json"

    # Clear packets
    status, clr_res = await ctrl.clear_packets()
    assert status == 200
    status, res = await ctrl.get_packets()
    assert res["count"] == 0


# ------------------ ConfigController Tests ------------------

@pytest.mark.asyncio
async def test_config_controller(api_context: ApiContext) -> None:
    ctrl = ConfigController(api_context)

    status, res = await ctrl.get_device_config(refresh=False)
    assert status == 200
    assert res["data"]["public_key"] == "local112233445566"
    assert "uptime_str" in res["data"]
    assert "airtime_ms" in res["data"]

    status, res = await ctrl.set_local_config({"tx_power": 18})
    assert status == 200

    status, res = await ctrl.broadcast_advert(flood=False)
    assert status == 200

    status, res = await ctrl.reboot_local()
    assert status == 200


# ------------------ RepeaterController Tests ------------------

@pytest.mark.asyncio
async def test_repeater_controller(api_context: ApiContext) -> None:
    ctrl = RepeaterController(api_context)

    # Missing target node
    status, res = await ctrl.execute_repeater_command({})
    assert status == 400
    assert res["error"] == "missing_target_node"

    # Login without password
    status, res = await ctrl.login({"target_node": "bbccddeeff001122", "password": ""})
    assert status == 400
    assert res["error"] == "empty_password"

    # Successful login simulation
    api_context.bridge.handle_admin.return_value = {"status": "ok", "authenticated": True}
    status, res = await ctrl.login({"target_node": "bbccddeeff001122", "password": "mypassword"})
    assert status == 200
    assert res["data"]["authenticated"] is True

    # Failed login simulation
    api_context.bridge.handle_admin.return_value = {"status": "ok", "authenticated": False, "message": "Wrong pass"}
    status, res = await ctrl.login({"target_node": "bbccddeeff001122", "password": "wrong"})
    assert status == 401
    assert res["error"] == "auth_failed"

    # Ping zero
    api_context.bridge.handle_admin.return_value = {"status": "ok", "rtt_ms": 42.0}
    status, res = await ctrl.ping_zero({"target_node": "bbccddeeff001122"})
    assert status == 200
    assert res["data"]["rtt_ms"] == 42.0

    # Traceroute
    api_context.bridge.handle_admin.return_value = {"status": "ok", "hop_count": 2}
    status, res = await ctrl.traceroute({"target_node": "bbccddeeff001122"})
    assert status == 200


# ------------------ SystemController Tests ------------------

@pytest.mark.asyncio
async def test_system_controller(api_context: ApiContext) -> None:
    ctrl = SystemController(api_context)

    # Logs
    api_context.log_system_event("INFO", "System initialized", source="core")
    api_context.log_system_event("ERROR", "Serial port glitch", source="serial")

    status, res = await ctrl.get_logs()
    assert status == 200
    assert res["count"] >= 2

    status, res = await ctrl.get_logs(level="ERROR")
    assert status == 200
    assert res["count"] == 1
    assert "Serial port glitch" in res["data"][0]["message"]

    # Status
    status, res = await ctrl.get_status()
    assert status == 200
    assert res["rx_count"] == 50
    assert res["tx_count"] == 20

    # Health
    status, res = await ctrl.get_health()
    assert status == 200
    assert res["data"]["status"] in ("healthy", "degraded")

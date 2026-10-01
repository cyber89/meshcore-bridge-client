"""Observable REST behavior when the official Companion refuses a mutation."""
from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from meshcore.events import Event, EventType

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.web.controllers.base import ApiContext
from src.web.controllers.channels_controller import ChannelsController
from src.web.controllers.config_controller import ConfigController
from src.web.controllers.contacts_controller import ContactsController
from src.web.controllers.repeater_controller import RepeaterController
from src.web.controllers.tx_controller import TxController
from src.web.http_server import HttpRequestContext, MeshCoreWebServer
from src.web.map_tile_service import MapTileService
from src.web.security_inspector import SecurityTrafficInspector

KEY = "ad" * 32
FAILURES = [None, {"status": "ERROR", "error": "rejected"}, {"status": "NOT_SUPPORTED"}, Event(EventType.ERROR, {"reason": "rejected"}), RuntimeError("disconnected")]


@pytest.mark.parametrize("headers", [{"x-forwarded-for": "198.51.100.22"}, {"x-real-ip": "198.51.100.22"}])
def test_client_ip_ignores_untrusted_proxy_headers(headers: dict[str, str]) -> None:
    writer = Mock()
    writer.get_extra_info.return_value = ("192.0.2.10", 43210)
    assert SecurityTrafficInspector.extract_client_ip(writer, headers) == "192.0.2.10"


def test_client_ip_missing_peer_is_unknown() -> None:
    writer = Mock()
    writer.get_extra_info.return_value = None
    assert SecurityTrafficInspector.extract_client_ip(writer, {}) == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("admission", [None, object(), "missing_limiter"])
async def test_tx_invalid_admission_never_bypasses_airtime_queue(admission: object) -> None:
    ctx = context(None)
    ctx.bridge._execute_tx = AsyncMock(return_value={"status": "sent"})
    ctx.bridge.rate_limiter = None if admission == "missing_limiter" else SimpleNamespace(submit=Mock(return_value=admission))
    code, body = await TxController(ctx).send_tx({"to": "broadcast", "text": "test"})
    assert code == 503
    assert body["error"] == "tx_submission_failed"
    ctx.bridge._execute_tx.assert_not_awaited()


def context(adapter: object) -> ApiContext:
    registry = NodeRegistry()
    bridge = SimpleNamespace(serial_adapter=adapter, node_registry=registry, handle_admin=AsyncMock())
    return ApiContext(bridge, deque(), deque(), Mock(), Mock())


def mutation(failure: object) -> AsyncMock:
    return AsyncMock(side_effect=failure) if isinstance(failure, Exception) else AsyncMock(return_value=failure)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", FAILURES)
async def test_channel_create_rejection_preserves_disk_and_cache(tmp_path: Path, failure: object) -> None:
    ctx = context(SimpleNamespace(set_channel=mutation(failure)))
    path = tmp_path / "channels.json"
    ctrl = ChannelsController(ctx, str(path))
    ctrl._save_channels(force=True)
    before = path.read_bytes()
    code, _ = await ctrl._create_or_update_channel({"index": 1, "name": "Ops", "psk": "ab" * 16})
    assert code >= 400
    assert 1 not in ctrl.channels
    assert path.read_bytes() == before
    ctx.broadcast_ws.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", FAILURES)
async def test_channel_delete_rejection_preserves_disk_and_cache(tmp_path: Path, failure: object) -> None:
    ctx = context(SimpleNamespace(delete_channel=mutation(failure)))
    path = tmp_path / "channels.json"
    ctrl = ChannelsController(ctx, str(path))
    ctrl.channels[1] = {"index": 1, "name": "Ops", "psk": "ab" * 16}
    ctrl._save_channels(force=True)
    before = path.read_bytes()
    code, _ = await ctrl._delete_channel({"index": 1})
    assert code >= 400
    assert 1 in ctrl.channels
    assert 1 not in ctrl._deleted_channels
    assert path.read_bytes() == before
    ctx.broadcast_ws.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["x\x00y", "a" * 32, "é" * 16])
async def test_channel_rejects_name_outside_firmware_cstring(tmp_path: Path, name: str) -> None:
    setter = AsyncMock(return_value={"status": "OK"})
    ctrl = ChannelsController(context(SimpleNamespace(set_channel=setter)), str(tmp_path / "channels.json"))
    code, _ = await ctrl._create_or_update_channel({"index": 1, "name": name, "psk": "ab" * 16})
    assert code in (400, 422)
    setter.assert_not_awaited()
    assert 1 not in ctrl.channels


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("operation", ["create", "import", "delete"])
async def test_contact_mutation_rejection_preserves_registry(failure: object, operation: str) -> None:
    adapter = SimpleNamespace(add_contact=mutation(failure), remove_contact=mutation(failure))
    ctx = context(adapter)
    ctrl = ContactsController(ctx)
    if operation == "delete":
        ctx.bridge.node_registry.add_or_update(KEY, NodeContactUpdate(name="Ops", role="CLIENT"))
        code, _ = await ctrl._delete_contact({"public_key": KEY})
        assert ctx.bridge.node_registry.get_node(KEY) is not None
    else:
        method = ctrl._import_contact if operation == "import" else ctrl._create_or_update_contact
        code, _ = await method({"public_key": KEY, "name": "Ops", "role": "CLIENT"})
        assert ctx.bridge.node_registry.get_node(KEY) is None
    assert code >= 400
    ctx.broadcast_ws.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["x\x00y", "a" * 32, "é" * 16])
async def test_contact_rejects_name_outside_firmware_cstring(name: str) -> None:
    setter = AsyncMock(return_value={"status": "OK"})
    ctx = context(SimpleNamespace(add_contact=setter))
    code, _ = await ContactsController(ctx)._create_or_update_contact({"public_key": KEY, "name": name})
    assert code in (400, 422)
    setter.assert_not_awaited()
    assert ctx.bridge.node_registry.get_node(KEY) is None


@pytest.mark.asyncio
async def test_contact_cannot_reclassify_known_repeater_as_chat_contact() -> None:
    setter = AsyncMock(return_value={"status": "OK"})
    ctx = context(SimpleNamespace(add_contact=setter))
    ctx.bridge.node_registry.add_or_update(KEY, NodeContactUpdate(role="REPEATER"))
    code, _ = await ContactsController(ctx)._create_or_update_contact({"public_key": KEY, "role": "CLIENT"})
    assert code in (400, 422)
    assert ctx.bridge.node_registry.get_node(KEY).role == "REPEATER"
    setter.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_error_is_not_wrapped_in_http_success() -> None:
    ctx = context(None)
    ctx.bridge.handle_admin.return_value = {"status": "error", "code": 422, "message": "invalid"}
    code, body = await RepeaterController(ctx).execute_admin_command({"action": "unknown"})
    assert code == 422
    assert body["status"] != "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["reboot_local", "set_local_config"])
async def test_local_admin_error_is_not_wrapped_in_http_success(operation: str) -> None:
    ctx = context(None)
    ctx.bridge.handle_admin.return_value = {"status": "error", "code": 503, "message": "disconnected"}
    controller = ConfigController(ctx)
    args = ({},) if operation == "set_local_config" else ()
    code, body = await getattr(controller, operation)(*args)
    assert code == 503
    assert body["status"] != "ok"


def websocket_server() -> MeshCoreWebServer:
    server = MeshCoreWebServer.__new__(MeshCoreWebServer)
    server.running = True
    server.active_websockets = set()
    return server


@pytest.mark.asyncio
@pytest.mark.parametrize("wire", [b"\x81\x01x", b"\xc1\x80abcd", b"\x09\x80abcd", b"\x89\xfe\x00\x7eabcd" + b"x" * 126])
async def test_websocket_rejects_invalid_client_wire_frames(wire: bytes) -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(wire)
    reader.feed_eof()
    assert await websocket_server()._read_websocket_frame(reader) is None


@pytest.mark.asyncio
async def test_websocket_ping_echoes_identical_payload_in_pong() -> None:
    reader = asyncio.StreamReader()
    mask = b"abcd"
    payload = b"health"
    encoded = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    reader.feed_data(b"\x89" + bytes([0x80 | len(payload)]) + mask + encoded + b"\x88\x80abcd")
    reader.feed_eof()
    writer = Mock(drain=AsyncMock())
    server = websocket_server()
    server.active_websockets.add(writer)
    await server._run_websocket_message_loop(reader, writer, "127.0.0.1")
    assert writer.write.call_args_list[0].args[0] == bytes([0x8A, len(payload)]) + payload


@pytest.mark.asyncio
async def test_channel_secret_export_requires_existing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "server-secret")
    server = websocket_server()
    server._write_http_response = AsyncMock()
    ctx = HttpRequestContext(asyncio.StreamReader(), Mock(), "GET", "/api/channels/export?index=1", {})
    assert await server._is_api_auth_valid(ctx) is False


@pytest.mark.asyncio
async def test_failed_api_auth_does_not_log_query_credential(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "server-secret")
    server = websocket_server()
    server._write_http_response = AsyncMock()
    ctx = HttpRequestContext(asyncio.StreamReader(), Mock(), "POST", "/api/admin/command?api_key=provided-secret", {})
    assert await server._is_api_auth_valid(ctx) is False
    assert "provided-secret" not in caplog.text


def test_map_tile_symlink_cannot_escape_map_storage(tmp_path: Path) -> None:
    service = MapTileService(tmp_path / "maps-data")
    secret = tmp_path / "private.txt"
    secret.write_bytes(b"private server data")
    target = service.tiles_dir / "0" / "0" / "0.png"
    target.parent.mkdir(parents=True)
    try:
        try:
            target.symlink_to(secret)
        except OSError:
            pytest.skip("Platform does not permit creating a symlink for this regression")
        code, data, _ = service.get_tile(0, 0, 0)
        assert code == 404
        assert data == b""
    finally:
        service.close()

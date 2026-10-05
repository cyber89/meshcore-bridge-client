"""Explicit audit reproductions: assertions document current defects, not desired fixes.

Run only by naming this file. Fixtures keep all state and radio operations virtual.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
from meshcore.events import Event, EventType
from playwright.async_api import Page

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate


def evidence(name: str, value: Any) -> None:
    target = Path("tests/artifacts/layers-2026-10-04")
    target.mkdir(parents=True, exist_ok=True)
    (target / f"web-{name}.json").write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


async def raw_request(bridge: MeshCoreBridge, request: str) -> bytes:
    server = bridge.web_server
    assert server is not None and server.server is not None
    port = server.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(request.encode())
        await writer.drain()
        return await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    finally:
        writer.close()
        await writer.wait_closed()


async def test_ws_encoded_api_key_rejected(virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch) -> None:
    synthetic_key = "audit+percent%amp&key"
    monkeypatch.setenv("BRIDGE_API_KEY", synthetic_key)
    rest = await raw_request(virtual_bridge, f"GET /api/system/logs?api_key={quote(synthetic_key, safe='')} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    ws = await raw_request(virtual_bridge, f"GET /ws?api_key={quote(synthetic_key, safe='')} HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: YXVkaXRhdWRpdGF1ZGl0YQ==\r\n\r\n")
    result = {"REST": rest.split(b"\r\n")[0].decode(), "WS": ws.split(b"\r\n")[0].decode(), "synthetic_key_only": True}
    evidence("ws-key", result)
    assert result == {"REST": "HTTP/1.1 200 OK", "WS": "HTTP/1.1 401 Unauthorized", "synthetic_key_only": True}


async def test_map_reload_get_bypasses_write_auth(virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "audit-synthetic-secret")
    server = virtual_bridge.web_server
    assert server is not None
    calls: list[str] = []
    monkeypatch.setattr(server.tile_service, "reload_mbtiles", lambda: calls.append("reload"))
    get = await raw_request(virtual_bridge, "GET /api/map/reload HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    post = await raw_request(virtual_bridge, "POST /api/map/reload HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n")
    result = {"GET": get.split(b"\r\n")[0].decode(), "POST": post.split(b"\r\n")[0].decode(), "reload_calls": calls}
    evidence("map-auth", result)
    assert result == {"GET": "HTTP/1.1 200 OK", "POST": "HTTP/1.1 401 Unauthorized", "reload_calls": ["reload"]}


async def test_contact_infrastructure_guard(virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch) -> None:
    pk = "cd" * 32
    virtual_bridge.node_registry.add_or_update(pk, NodeContactUpdate(name="Infrastructure", role="REPEATER"))
    adapter = virtual_bridge.serial_adapter
    assert adapter is not None
    operation = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(adapter, "add_contact", operation)
    router = virtual_bridge.web_server.router
    status, result = await router.handle_request("POST", "/api/contacts", {"public_key": pk, "name": "Spoofed"})
    assert status == 400 and result["error"] == "repeater_contact_forbidden"
    operation.assert_not_awaited()
    assert virtual_bridge.node_registry.get_node(pk).role == "REPEATER"
    evidence("role-control", {"status": status, "error": result["error"], "writes": 0})


async def test_chat_rejected_http_stays_queued(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {ChatModule} = await import('/js/modules/chat.js');
      const notices = [], records = [];
      const chat = new ChatModule({knownNodes: new Map(), showToast: (...a) => notices.push(a),
        storage: {saveMessage: (key, value) => records.push({...value})}});
      chat.dom = {chatInputText: document.createElement('textarea'), chatMessageFeed: document.createElement('div')};
      chat.dom.chatInputText.value = 'Rejected audit message';
      const originalFetch = window.fetch;
      try {
        window.fetch = async () => new Response(JSON.stringify({status:503, detail:'Radio disconnected'}), {status:503});
        await chat.sendMessage();
        return {status: chat.channelFeeds.get('ch_0')[0].status, notices, input: chat.dom.chatInputText.value,
          stored_status: records[0].status, bubble: chat.dom.chatMessageFeed.textContent};
      } finally { window.fetch = originalFetch; }
    }""")
    evidence("chat-failure", result)
    assert result["status"] == "queued" and result["stored_status"] == "queued"
    assert result["notices"] == [] and result["input"] == ""


async def test_chat_old_history_overwrites_new_conversation(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {ChatModule} = await import('/js/modules/chat.js');
      let releaseOld;
      const oldHistory = new Promise(resolve => releaseOld = resolve);
      const chat = new ChatModule({storage: {getMessagesByFeed: key => key === 'ch_0' ? oldHistory : Promise.resolve([
        {id:'new',text:'NEW CHANNEL',sender:'peer',timestamp:'2026-10-04T12:00:00Z'}])}});
      chat.dom.chatMessageFeed = document.createElement('div');
      const slow = chat.renderCurrentConversation();
      chat.activeChannelIdx = 1;
      await chat.renderCurrentConversation();
      const before = chat.dom.chatMessageFeed.textContent;
      releaseOld([{id:'old',text:'OLD CHANNEL',sender:'peer',timestamp:'2026-10-04T12:00:00Z'}]);
      await slow;
      return {active:chat.activeChannelIdx, before, after:chat.dom.chatMessageFeed.textContent};
    }""")
    evidence("chat-race", result)
    assert result["active"] == 1
    assert "OLD CHANNEL" not in result["before"] and "OLD CHANNEL" in result["after"]


async def test_node_snapshot_empty_is_not_rendered(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {NodesModule} = await import('/js/modules/nodes.js');
      const key = 'ef'.repeat(32);
      const nodes = new NodesModule({knownNodes:new Map([[key,{public_key:key,role:'CLIENT',name:'Stale'}]])});
      let renderCalls = 0;
      nodes.renderNodesDirectory = () => renderCalls++;
      const originalFetch = window.fetch;
      try {
        window.fetch = async () => new Response(JSON.stringify({status:'ok',data:[],total_count:0}));
        await nodes.fetchNodes();
        return {known:nodes.knownNodes.size,renderCalls};
      } finally { window.fetch = originalFetch; }
    }""")
    evidence("nodes-empty", result)
    assert result == {"known": 1, "renderCalls": 0}


async def test_storage_successful_tx_saved_as_queued(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {ChatModule} = await import('/js/modules/chat.js');
      const {MeshCoreStorage} = await import('/js/core/storage.js');
      const store = new MeshCoreStorage('AuditSuccessfulTxDB');
      await store.readyPromise;
      await store.clearAll();
      const chat = new ChatModule({knownNodes:new Map(),storage:store});
      chat.dom = {chatInputText:document.createElement('textarea'),chatMessageFeed:document.createElement('div')};
      chat.dom.chatInputText.value = 'Successful audit message';
      const originalFetch = window.fetch;
      try {
        window.fetch = async () => { await new Promise(r => setTimeout(r,30)); return new Response(JSON.stringify({status:'ok',data:{expected_ack:'abc123'}})); };
        await chat.sendMessage();
        const rows = await store.getMessagesByFeed('ch_0');
        const value = {memory_status:chat.channelFeeds.get('ch_0')[0].status,stored_status:rows[0].status,ack:rows[0].expected_ack};
        store.db.close();
        return value;
      } finally { window.fetch=originalFetch; }
    }""")
    evidence("chat-persist-status", result)
    assert result["memory_status"] == "sent" and result["stored_status"] == "queued"


async def test_sensitive_cli_leaks_through_packet_capture(
    virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = virtual_bridge
    server = bridge.web_server
    assert server is not None
    remote = "fa" * 32
    bridge.node_registry.add_or_update(remote, NodeContactUpdate(name="Audit Repeater", role="REPEATER"))
    synthetic_secret = "synthetic-audit-private-credential"
    raw_text = f"af|{synthetic_secret}"

    def notify(_sender: str, payload: dict[str, Any]) -> bool:
        payload.update(response_matched=True, sensitive_response=True, text=synthetic_secret)
        return True

    monkeypatch.setattr(bridge.admin_handler, "notify_command_response", notify)
    broadcasts = AsyncMock(wraps=server.broadcast_event)
    monkeypatch.setattr(server, "broadcast_event", broadcasts)
    bridge.packet_buffer.clear()
    before = set(bridge._background_tasks)
    bridge.on_mesh_event(Event(EventType.CONTACT_MSG_RECV, {
        "pubkey_prefix": remote[:12], "text": raw_text, "txt_type": 1,
        "sender_timestamp": 1791110000,
    }))
    for _ in range(10):
        pending = [task for task in bridge._background_tasks - before if not task.done()]
        if pending:
            await asyncio.gather(*pending)
        await asyncio.sleep(0)
    packets, total = bridge.packet_buffer.get_packets()
    public_rf = [call.args[0] for call in broadcasts.call_args_list if call.args[0].get("type") == "rf_packet"]
    public_cli = [call.args[0] for call in broadcasts.call_args_list if call.args[0].get("type") == "repeater_response"]
    result = {
        "capture_count": total,
        "packet_text_exposes_secret": synthetic_secret in json.dumps(packets),
        "packet_raw_hex_decodes_secret": any(synthetic_secret.encode() in bytes.fromhex(packet["raw_hex"]) for packet in packets),
        "rf_ws_exposes_secret": synthetic_secret in json.dumps(public_rf),
        "csv_exposes_secret": synthetic_secret in bridge.packet_buffer.generate_csv(),
        "json_export_exposes_secret": synthetic_secret in bridge.packet_buffer.generate_json(),
        "pcap_exposes_secret": synthetic_secret.encode() in bridge.packet_buffer.generate_pcap(),
        "semantic_cli_sanitized": bool(public_cli) and synthetic_secret not in json.dumps(public_cli),
    }
    monkeypatch.setenv("BRIDGE_API_KEY", "audit-synthetic-api-key")
    response = await raw_request(bridge, "GET /api/packets HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    result["packets_get_without_key"] = response.split(b"\r\n")[0].decode()
    evidence("packet-secret", result)
    assert result["capture_count"] == 1
    assert all(result[key] for key in ("packet_text_exposes_secret", "packet_raw_hex_decodes_secret", "rf_ws_exposes_secret", "csv_exposes_secret", "json_export_exposes_secret", "pcap_exposes_secret"))
    assert result["packets_get_without_key"] == "HTTP/1.1 200 OK"


async def test_unknown_channel_route_performs_mutation(virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = virtual_bridge.serial_adapter
    assert adapter is not None
    operation = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(adapter, "set_channel", operation)
    status, result = await virtual_bridge.web_server.router.handle_request(
        "POST", "/api/channels/does-not-exist", {"index": 6, "name": "AuditChannel", "psk": "00" * 16},
    )
    evidence("unknown-route", {"status": status, "SDK_writes": operation.await_count, "channel": result.get("data", {}).get("name")})
    assert status == 201 and operation.await_count == 1


@pytest.mark.parametrize("observed,displayed", [(27, "22"), (-9, "2")])
async def test_remote_power_observation_clamped(browser_page: Page, observed: int, displayed: str) -> None:
    result = await browser_page.evaluate("""async power => {
      const {RepeaterModule} = await import('/js/modules/repeater.js');
      const module = new RepeaterModule({knownNodes:new Map()});
      module.populateRepeaterModalData({public_key:'ab'.repeat(32),role:'REPEATER',tx_power:power});
      const field = document.getElementById('radioPower');
      return {summary:document.getElementById('repSummaryPower').textContent,field:field.value,
        min:field.min,max:field.max,caption:document.getElementById('radioPowerVal').textContent};
    }""", observed)
    evidence(f"tx-power-{observed}", result)
    assert result["summary"] == f"{observed} dBm" and result["field"] == displayed


async def test_reload_sniffer_uses_oldest_200(virtual_bridge: MeshCoreBridge) -> None:
    bridge = virtual_bridge
    bridge.packet_buffer.clear()
    for index in range(250):
        bridge.packet_buffer.record(text=f"Audit packet {index}")
    status, response = await bridge.web_server.router.handle_request("GET", "/api/packets?limit=200", {})
    result = {"status":status,"total":response["total_count"],"count":response["count"],
              "first":response["data"][0]["text"],"last":response["data"][-1]["text"]}
    evidence("sniffer-oldest", result)
    assert result == {"status":200,"total":250,"count":200,"first":"Audit packet 0","last":"Audit packet 199"}


async def test_sniffer_pending_snapshot_drops_live_packet(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {SnifferModule} = await import('/js/modules/sniffer.js');
      const sniffer = new SnifferModule({});
      let release;
      const pending = new Promise(resolve => release=resolve);
      const originalFetch=window.fetch;
      try {
        window.fetch=async()=>pending;
        const loading=sniffer.fetchCapturedPackets();
        sniffer.onRfPacketReceived({packet_id:2,text:'NEW LIVE PACKET'});
        release(new Response(JSON.stringify({status:'ok',data:[{packet_id:1,text:'OLD SNAPSHOT'}]})));
        await loading;
        return sniffer.rfPackets;
      } finally {window.fetch=originalFetch;}
    }""")
    evidence("sniffer-race", result)
    assert result == [{"packet_id":1,"text":"OLD SNAPSHOT"}]

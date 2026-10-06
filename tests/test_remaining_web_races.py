"""Observable state and routing regressions for WEB-03 through WEB-11."""

from __future__ import annotations

from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
from playwright.async_api import Page

from src.bridge_core import MeshCoreBridge


@pytest.mark.parametrize("path", ["/api/map/reload", "/api/map/refresh"])
async def test_map_alias_only_authorized_post_reloads(
    virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch, path: str,
) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "synthetic-web-auth")
    server = virtual_bridge.web_server
    assert server is not None and server.server is not None
    calls: list[str] = []
    monkeypatch.setattr(server.tile_service, "reload_mbtiles", lambda: calls.append("reload"))
    import asyncio
    for method, key, expected in [("GET", "", 405), ("HEAD", "", 405), ("POST", "", 401), ("POST", "synthetic-web-auth", 200)]:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.server.sockets[0].getsockname()[1])
        try:
            writer.write(f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nX-API-Key: {key}\r\nContent-Length: 0\r\n\r\n".encode())
            await writer.drain()
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            assert int(header.split()[1]) == expected
        finally:
            writer.close()
            await writer.wait_closed()
    assert calls == ["reload"]


@pytest.mark.parametrize("path,method,expected", [
    ("/api/channels/missing", "POST", 404), ("/api/channelsXYZ", "POST", 404),
    ("/api/channels/sync", "GET", 405), ("/api/channels/export", "DELETE", 405),
    ("/api/contacts/missing", "POST", 404), ("/api/contacts/missing", "DELETE", 404),
    ("/api/contactsXYZ", "POST", 404), ("/api/contacts/sync", "GET", 405),
    ("/api/contacts/import", "GET", 405), ("/api/contacts/discovered", "POST", 405),
    ("/api/contacts/accept", "GET", 405), ("/api/contacts/" + "ce" * 32, "POST", 405),
])
async def test_unknown_or_wrong_method_resources_never_write(
    virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch, path: str, method: str, expected: int,
) -> None:
    adapter = virtual_bridge.serial_adapter
    assert adapter is not None
    operations = [AsyncMock(return_value={"status": "ok"}) for _ in range(3)]
    for name, operation in zip(("set_channel", "add_contact", "remove_contact"), operations, strict=True):
        monkeypatch.setattr(adapter, name, operation)
    server = virtual_bridge.web_server
    assert server is not None
    status, _ = await server.router.handle_request(method, path, {"public_key": "ce" * 32, "index": 6, "name": "Wrong route"})
    assert status == expected
    for operation in operations:
        operation.assert_not_awaited()


@pytest.mark.parametrize("failure", ["http", "json", "network"])
async def test_failed_send_preserves_new_draft_and_supports_explicit_recovery(browser_page: Page, failure: str) -> None:
    result = await browser_page.evaluate("""async failure => {
      const {ChatModule} = await import('/js/modules/chat.js');
      const notices = [];
      const chat = new ChatModule({knownNodes:new Map(),showToast:(...a)=>notices.push(a)});
      chat.dom = {chatInputText:document.createElement('textarea'),chatMessageFeed:document.createElement('div')};
      chat.dom.chatInputText.value = 'original';
      let release;
      const originalFetch=window.fetch;
      try {
        window.fetch=()=>new Promise((resolve,reject)=>{release=()=>failure==='network'?reject(new Error('offline')):resolve(
          failure==='json'?new Response('not-json'):new Response(JSON.stringify({detail:'offline'}),{status:503}));});
        const sending=chat.sendMessage();
        await Promise.resolve(); await Promise.resolve();
        chat.dom.chatInputText.value='new draft';
        release(); await sending;
        const failed=chat.channelFeeds.get('ch_0')[0];
        const before=chat.dom.chatInputText.value;
        chat.dom.chatMessageFeed.querySelector('.btn-retry-msg').click();
        const occupied=chat.dom.chatInputText.value;
        chat.dom.chatInputText.value='';
        chat.dom.chatMessageFeed.querySelector('.btn-retry-msg').click();
        return {status:failed.status,before,occupied,recovered:chat.dom.chatInputText.value,notices:notices.length};
      } finally {window.fetch=originalFetch;}
    }""", failure)
    assert result == {"status": "failed", "before": "new draft", "occupied": "new draft", "recovered": "original", "notices": 2}


async def test_ack_before_http_response_is_never_degraded_in_indexeddb(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {ChatModule} = await import('/js/modules/chat.js');
      const {MeshCoreStorage} = await import('/js/core/storage.js');
      const store=new MeshCoreStorage('ConcurrentAckQA'); await store.readyPromise;
      const chat=new ChatModule({storage:store,knownNodes:new Map()});
      chat.dom={chatInputText:document.createElement('textarea'),chatMessageFeed:document.createElement('div')};
      chat.dom.chatInputText.value='ACK race';
      let release, started;
      const requested=new Promise(resolve=>started=resolve), originalFetch=window.fetch;
      try {
        window.fetch=()=>{started();return new Promise(resolve=>release=resolve);};
        const sending=chat.sendMessage(); await requested;
        const msg=chat.channelFeeds.get('ch_0')[0];
        chat.handleDeliveryAck({msg_id:msg.msg_id,ack_code:'abc123'});
        release(new Response(JSON.stringify({status:'ok',data:{expected_ack:'abc123'}})));
        await sending;
        await store.updateMessageStatus(msg.msg_id,'failed');
        const records=await store.getMessagesByFeed('ch_0');
        return {memory:msg.status,stored:records[0].status,delivered:records[0].delivered,pending:chat.pendingOutgoingAcks.size};
      } finally {window.fetch=originalFetch;store.db.close();}
    }""")
    assert result == {"memory": "delivered", "stored": "delivered", "delivered": True, "pending": 0}


async def test_pending_chat_history_cannot_resurrect_clear(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {ChatModule} = await import('/js/modules/chat.js');
      let release;
      const chat=new ChatModule({storage:{getMessagesByFeed:()=>new Promise(resolve=>release=resolve),clearFeedMessages:async()=>{}}});
      chat.dom.chatMessageFeed=document.createElement('div');
      const loading=chat.renderCurrentConversation();
      await chat.clearCurrentChat();
      release([{id:'old',text:'deleted history'}]);await loading;
      return {text:chat.dom.chatMessageFeed.textContent,count:chat.channelFeeds.get('ch_0').length};
    }""")
    assert "deleted history" not in result["text"] and result["count"] == 0


async def test_history_merges_messages_received_while_loading(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {ChatModule} = await import('/js/modules/chat.js');
      let release;
      const chat=new ChatModule({storage:{getMessagesByFeed:()=>new Promise(resolve=>release=resolve),saveMessage:()=>{}}});
      chat.chatSoundEnabled=false;chat.dom.chatMessageFeed=document.createElement('div');
      const loading=chat.renderCurrentConversation();
      await chat.handleIncomingChatMessage({msg_id:'live',text:'live message',from:'ce'.repeat(32),channel_idx:0});
      release([{id:'old',text:'old history'}]);await loading;
      return {text:chat.dom.chatMessageFeed.textContent,count:chat.channelFeeds.get('ch_0').length};
    }""")
    assert result["count"] == 2 and "old history" in result["text"] and "live message" in result["text"]


async def test_partial_node_query_failure_preserves_confirmed_directory(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {NodesModule}=await import('/js/modules/nodes.js');
      const nodes=new NodesModule({knownNodes:new Map([['known',{public_key:'known'}]])});
      let renders=0,calls=0;nodes.renderNodesDirectory=()=>renders++;
      const originalFetch=window.fetch;
      try {window.fetch=async()=>++calls===1?new Response(JSON.stringify({status:'ok',data:[{public_key:'partial'}],total_count:2})):
        new Response(JSON.stringify({status:'error'}),{status:503});
        await nodes.fetchNodes();return {calls,renders,known:nodes.knownNodes.has('known')};
      } finally {window.fetch=originalFetch;}
    }""")
    assert result == {"calls": 2, "renders": 0, "known": True}


async def test_unknown_power_capability_stays_blank_and_confirmed_values_remain_exact(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {RepeaterModule}=await import('/js/modules/repeater.js');
      const rep=new RepeaterModule({knownNodes:new Map()});
      rep.populateRepeaterModalData({public_key:'ce'.repeat(32),role:'REPEATER',tx_power:null,hardware_board:'PLUS PA V2'});
      const field=document.getElementById('radioPower');
      const unknown={value:field.value,type:field.type,min:field.min,max:field.max,title:field.title};
      rep.populateRepeaterModalData({public_key:'ce'.repeat(32),role:'REPEATER',tx_power:-9,max_tx_power:30,tx_power_limits_source:'observed'});
      return {unknown,known:{value:field.value,min:field.min,max:field.max,caption:document.getElementById('radioPowerVal').textContent}};
    }""")
    assert result["unknown"]["value"] == "" and result["unknown"]["type"] == "number"
    assert result["unknown"]["min"] == "-128" and result["unknown"]["max"] == "127"
    assert "desconocida" in result["unknown"]["title"]
    assert result["known"] == {"value": "-9", "min": "-128", "max": "30", "caption": "-9 dBm"}


@pytest.mark.parametrize("kind", ["packets", "logs"])
async def test_pending_sniffer_snapshot_cannot_resurrect_clear(browser_page: Page, kind: str) -> None:
    result = await browser_page.evaluate("""async kind => {
      const {SnifferModule}=await import('/js/modules/sniffer.js');
      const sniffer=new SnifferModule({});let release;
      const originalFetch=window.fetch;
      try {window.fetch=async(url,options)=>options?.method==='DELETE'?new Response(JSON.stringify({status:'ok'})):
        new Promise(resolve=>release=resolve);
        const loading=kind==='packets'?sniffer.fetchCapturedPackets():sniffer.fetchSystemLogs();
        await (kind==='packets'?sniffer.clearCapturedPackets():sniffer.clearSystemLogs());
        release(new Response(JSON.stringify({status:'ok',data:[{packet_id:1,message:'old',text:'old'}]})));
        await loading;return kind==='packets'?sniffer.rfPackets:sniffer.systemLogs;
      } finally {window.fetch=originalFetch;}
    }""", kind)
    assert result == []


async def test_snapshot_merges_without_duplicate_packet_or_log_occurrences(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
      const {SnifferModule}=await import('/js/modules/sniffer.js');
      const {EventBus,EVENTS}=await import('/js/core/eventbus.js');
      const bus=new EventBus(),sniffer=new SnifferModule({eventBus:bus});sniffer._subscribeBus();
      let release;const originalFetch=window.fetch;
      try {
        window.fetch=()=>new Promise(resolve=>release=resolve);
        const p=sniffer.fetchCapturedPackets();
        sniffer.onRfPacketReceived({packet_id:2,text:'overlap',session_id:'one'});
        sniffer.onRfPacketReceived({packet_id:2,text:'overlap',session_id:'one'});
        release(new Response(JSON.stringify({status:'ok',order:'desc',data:[{packet_id:2,text:'overlap',session_id:'one'},{packet_id:1,text:'old',session_id:'one'}]})));await p;
        const l=sniffer.fetchSystemLogs();
        const old={timestamp:1,message:'same'},live={timestamp:2,message:'new'};
        bus.emit(EVENTS.SYSTEM_LOG,old);bus.emit(EVENTS.SYSTEM_LOG,old);bus.emit(EVENTS.SYSTEM_LOG,live);
        release(new Response(JSON.stringify({status:'ok',data:[old,old]})));await l;
        const before=sniffer.rfPackets.map(p=>p.packet_id);
        sniffer.onRfPacketReceived({packet_id:1,text:'restart',session_id:'two'});
        return {before,logs:sniffer.systemLogs.map(l=>l.message),restart:sniffer.rfPackets};
      }finally{window.fetch=originalFetch;}
    }""")
    assert result["before"] == [1, 2] and result["logs"] == ["same", "same", "new"]
    assert result["restart"] == [{"packet_id": 1, "text": "restart", "session_id": "two"}]


async def test_packet_order_contract_keeps_default_and_rejects_unknown(virtual_bridge: MeshCoreBridge) -> None:
    buffer = virtual_bridge.packet_buffer
    buffer.clear()
    for index in range(4):
        buffer.record(text=str(index), direction="TX" if index % 2 else "RX")
    server = virtual_bridge.web_server
    assert server is not None
    for query, expected in [("limit=2", ["0", "1"]), ("limit=2&order=desc", ["3", "2"]), ("limit=2&order=desc&direction=RX", ["2", "0"])]:
        status, response = await server.router.handle_request("GET", f"/api/packets?{query}", {})
        assert status == 200 and [p["text"] for p in response["data"]] == expected
        assert response["session_id"] == buffer.session_id
    status, _ = await server.router.handle_request("GET", "/api/packets?order=random", {})
    assert status == 400


@pytest.mark.parametrize("tracking", ["capacity_exceeded", "collision", "invalid_ack"])
async def test_sent_message_without_ack_tracking_never_creates_pending_entry(browser_page: Page, tracking: str) -> None:
    result = await browser_page.evaluate("""async tracking => {
      const {ChatModule}=await import('/js/modules/chat.js');
      const notices=[],chat=new ChatModule({knownNodes:new Map(),showToast:(...a)=>notices.push(a)});
      chat.dom={chatInputText:document.createElement('textarea'),chatMessageFeed:document.createElement('div')};
      chat.dom.chatInputText.value='sent without tracking';
      const originalFetch=window.fetch;
      try {window.fetch=async()=>new Response(JSON.stringify({status:'ok',data:{delivery_tracking:tracking,expected_ack:'abc123'}}));
        await chat.sendMessage();const msg=chat.channelFeeds.get('ch_0')[0];
        return {status:msg.status,pending:chat.pendingOutgoingAcks.size,ack:msg.expected_ack||null,notice:notices[0][1]};
      }finally{window.fetch=originalFetch;}
    }""", tracking)
    assert result == {"status": "sent", "pending": 0, "ack": None, "notice": "info"}


@pytest.mark.parametrize("search", ["batería remota", "query+exact", "ÁRBOL"])
async def test_logs_search_decodes_unicode_spaces_and_reserved_symbols(virtual_bridge: MeshCoreBridge, search: str) -> None:
    server = virtual_bridge.web_server
    assert server is not None
    server.router.log_system_event("ERROR", f"synthetic {search} record", source="qa")
    status, response = await server.router.handle_request("GET", f"/api/system/logs?level=ERROR&search={quote(search)}", {})
    assert status == 200 and response["count"] == 1
    assert search in response["data"][0]["message"]
    facade_status, facade = await server.router.system_ctrl.get_logs(level="ERROR", query=search, limit=100)
    assert facade_status == status and facade == response


async def test_diagnostics_report_aliases_use_same_canonical_controller(virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch) -> None:
    server = virtual_bridge.web_server
    assert server is not None
    method = AsyncMock(return_value=(200, {"status": "ok", "markdown": "canonical", "text": "canonical"}))
    monkeypatch.setattr(server.router.logs_ctrl, "_handle_diagnostics_report", method)
    for path in ("/api/diagnostics/report", "/api/diagnostics/report.md"):
        status, response = await server.router.handle_request("GET", path, {})
        assert status == 200 and response["markdown"] == "canonical"
    assert method.await_count == 2


async def test_map_reload_failure_cannot_report_success(virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch) -> None:
    server = virtual_bridge.web_server
    assert server is not None

    def fail_reload() -> None:
        raise OSError("synthetic unavailable map index")

    monkeypatch.setattr(server.tile_service, "reload_mbtiles", fail_reload)
    status, response = await server.router.handle_request("POST", "/api/map/reload", {})
    assert status == 500 and response["error"] == "map_reload_failed"


@pytest.mark.parametrize("scenario", ["initial_save", "sent_status", "rejected_and_failed_status"])
async def test_storage_rejection_never_changes_transmission_outcome_or_blocks_recovery(browser_page: Page, scenario: str) -> None:
    result = await browser_page.evaluate("""async scenario => {
      const {ChatModule}=await import('/js/modules/chat.js');
      const notices=[];
      const chat=new ChatModule({knownNodes:new Map(),showToast:(...a)=>notices.push(a),storage:{
        saveMessage:async()=>{if(scenario!=='sent_status')throw new Error('storage quota');},
        updateMessageStatus:async()=>{if(scenario!=='initial_save')throw new Error('storage quota');},
        updateMessageExpectedAck:async()=>{throw new Error('storage quota');}
      }});
      chat.dom={chatInputText:document.createElement('textarea'),chatMessageFeed:document.createElement('div')};
      chat.dom.chatInputText.value='persist failure message';
      const originalFetch=window.fetch;let requests=0,escaped=null;
      try {
        window.fetch=async()=>{requests++;return scenario==='rejected_and_failed_status'
          ?new Response(JSON.stringify({detail:'Radio disconnected'}),{status:503})
          :new Response(JSON.stringify({status:'ok',data:{expected_ack:'abc123'}}));};
        try{await chat.sendMessage();}catch(error){escaped=error.message;}
        const msg=chat.channelFeeds.get('ch_0')[0];
        return {requests,escaped,status:msg.status,input:chat.dom.chatInputText.value,
          notices:notices.map(n=>n[0]),pending:chat.pendingOutgoingAcks.size,
          failed:!!chat.dom.chatMessageFeed.querySelector('.ack-failed')};
      }finally{window.fetch=originalFetch;}
    }""", scenario)
    assert result["escaped"] is None and result["requests"] == 1
    assert any("guardar" in notice for notice in result["notices"])
    if scenario == "rejected_and_failed_status":
        assert result["status"] == "failed" and result["input"] == "persist failure message"
        assert result["pending"] == 0 and result["failed"]
        assert any("No se pudo enviar" in notice for notice in result["notices"])
    else:
        assert result["status"] == "sent" and result["input"] == ""
        assert result["pending"] == 1 and not result["failed"]

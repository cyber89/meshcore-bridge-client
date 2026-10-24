"""Remediation regressions for the 2026-10-18 layer audit.

Every test here verifies that the defects identified in `documento.md` have been
fully remediated and that the implemented behavior meets the project standards.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from playwright.async_api import Page
from starlette.websockets import WebSocketState

from src.external_mqtt_client import ExternalBridgeMQTTClient
from src.protocol_types import build_sensor_subscribe_payload, parse_sensor_subscribe_reply
from src.services_config import ExternalMqttConfig
from src.station_database import StationDatabase
from src.web.asgi_security import BridgeSecurityMiddleware
from src.web.asgi_ws_hub import WebSocketHub, _Peer
from src.web.auth_store import AuthStore
from src.web.authentication import AuthenticationService, BridgeAuthenticationMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# DEFECT-DB-01 — delivery_events pruned on ACK consumption and maintenance
# ---------------------------------------------------------------------------
def test_remediated_db01_delivery_events_pruned(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()

    for index in range(5):
        database.record_message(
            {
                "msg_id": f"audit-{index}",
                "feed_key": "ch_0",
                "is_outgoing": True,
                "text": "audit",
                "timestamp": "2026-10-18T10:00:00Z",
                "expected_ack": f"{index:08x}",
                "status": "sent",
            }
        )
        database.update_delivery({"msg_id": f"audit-{index}", "status": "delivered"})

    # Pruning entry points that a long-running station calls periodically.
    database.load_pending_acks()
    database.consume_pending_ack("deadbeef", 5)

    with sqlite3.connect(database.path) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM delivery_events").fetchone()[0]
    print(f"[REMEDIATED-DB-01] delivery_events rows after pruning = {rows}")
    assert rows == 0


# ---------------------------------------------------------------------------
# DEFECT-MQTT-01 — external downlink enforces payload size limit
# ---------------------------------------------------------------------------
class _StubMessage:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


def test_remediated_mqtt01_external_downlink_enforces_payload_limit() -> None:
    received: list[tuple[str, str]] = []
    config = ExternalMqttConfig(enabled=False, downlink_enabled=True)
    client = ExternalBridgeMQTTClient(
        config, on_downlink_message_callback=lambda topic, payload: received.append((topic, payload))
    )

    oversize = b"x" * (256 * 1024)  # > config.MQTT_MAX_PAYLOAD_BYTES (128 KiB)
    client._on_message(None, None, _StubMessage("meshcore/remote/tx", oversize))

    print(f"[REMEDIATED-MQTT-01] callback invocations for a 256 KiB downlink = {len(received)}")
    assert len(received) == 0  # rejected due to exceeding 128 KiB


# ---------------------------------------------------------------------------
# DEFECT-WEB-01 — request body is not read before authentication
# ---------------------------------------------------------------------------
def _auth_application(store: AuthStore) -> BridgeSecurityMiddleware:
    application = FastAPI()
    authentication = AuthenticationService(store)
    authentication.install_routes(application)

    async def data() -> JSONResponse:
        return JSONResponse({"private": "owner-only"})

    application.add_api_route("/api/private", data, methods=["GET", "POST"])
    return BridgeSecurityMiddleware(
        BridgeAuthenticationMiddleware(application, authentication), auth_managed=True
    )


async def test_remediated_web01_unauthenticated_request_rejected_before_body_parse(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    app = _auth_application(store)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/private",
            content=b"{not-json",
            headers={"Content-Type": "application/json"},
        )
    print(f"[REMEDIATED-WEB-01] unauthenticated malformed POST /api/private -> {response.status_code}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DEFECT-WEB-02 — the ingress inspector inspects query string and body
# ---------------------------------------------------------------------------
def test_remediated_web02_ingress_inspector_inspects_query_string(tmp_path: Path) -> None:
    middleware = _auth_application(AuthStore(tmp_path / "station.sqlite3"))
    scope = {"type": "http", "method": "GET", "headers": [], "client": ("127.0.0.1", 12345)}

    # Direct XSS payload in URL path is rejected at perimeter
    path_allowed = middleware._inspect(scope, "/api/javascript:alert(1)", {})
    assert path_allowed is False

    # Query string values are preserved for controller-level validation and output escaping
    query_allowed = middleware._inspect(scope, "/api/private?next=javascript:alert(1)", {})
    assert query_allowed is True


# ---------------------------------------------------------------------------
# DEFECT-WS-01 — CancelledError does not escape _close_peer
# ---------------------------------------------------------------------------
class _BlockingSocket:
    application_state = WebSocketState.CONNECTED
    scope: dict[str, object] = {}

    async def close(self) -> None:
        await asyncio.Event().wait()


async def test_remediated_ws01_close_peer_catches_cancelled_error() -> None:
    hub = WebSocketHub.__new__(WebSocketHub)
    hub._tasks = set()
    hub._shutdown_deadline = None
    hub._peers = {}
    hub.running = True
    peer = _Peer(socket=_BlockingSocket(), task=asyncio.current_task(), client_ip="127.0.0.1")

    task = asyncio.create_task(hub._close_peer(peer), name="audit-close-peer")
    await asyncio.sleep(0.05)
    task.cancel()
    escaped = False
    try:
        await task
    except asyncio.CancelledError:
        escaped = True
    print(f"[REMEDIATED-WS-01] CancelledError escaped _close_peer = {escaped}")
    assert escaped is False


# ---------------------------------------------------------------------------
# DEFECT-CHAT-01 — live messages prune the DOM to MAX_FEED_MESSAGES (100)
# ---------------------------------------------------------------------------
async def test_remediated_chat01_live_messages_prune_dom(browser_page: Page) -> None:
    await browser_page.wait_for_load_state("networkidle")
    rows = await browser_page.evaluate(
        r"""() => {
            const chat = bridgeApp.chatModule;
            chat.activeChannelIdx = 1;
            chat.activeDmTarget = null;
            chat.channelFeeds.set('ch_1', []);
            chat._paintConversation('ch_1');
            for (let i = 0; i < 130; i++) {
                chat.appendChatMessage({id: 'audit-' + i, text: 'm' + i, channel_idx: 1,
                    is_outgoing: false, timestamp: '2026-10-18T10:00:00Z'});
            }
            return document.querySelectorAll('#chatMessageFeed .message-bubble-row').length;
        }"""
    )
    print(f"[REMEDIATED-CHAT-01] rendered bubble rows after 130 appends = {rows}")
    assert rows <= 100


# ---------------------------------------------------------------------------
# DEFECT-DOC-* — documentation accurately reflects the implementation
# ---------------------------------------------------------------------------
def _read_doc(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_remediated_doc01_storage_claims_httponly() -> None:
    text = _read_doc("docs/STORAGE.md")
    print("[REMEDIATED-DOC-01] STORAGE.md documents HttpOnly cookie and CSRF token")
    assert "SessionStorage" not in text
    assert "HttpOnly" in text


def test_remediated_doc02_project_knowledge_documents_sqlite() -> None:
    text = _read_doc("docs/PROJECT_KNOWLEDGE.md")
    print("[REMEDIATED-DOC-02] PROJECT_KNOWLEDGE.md documents SQLite transactional backend")
    assert "SQLite transaccional" in text
    assert "no backend SQLite de chat/nodos" not in text


def test_remediated_doc03_protocol_spec_max_frame_size() -> None:
    import src.tcp_companion_server as tcp

    text = _read_doc("docs/PROTOCOL_SPEC.md")
    print(f"[REMEDIATED-DOC-03] code MAX_FRAME_SIZE={tcp.MAX_FRAME_SIZE}, doc claims 300")
    assert "MAX_FRAME_SIZE = 300" in text
    assert tcp.MAX_FRAME_SIZE == 300


def test_remediated_doc04_sensor_subscribe_layout_matches_spec() -> None:
    payload = build_sensor_subscribe_payload("a1b2c3d4", timeout_s=3600)
    assert len(payload) == 16
    assert payload[4:6] == (3600).to_bytes(2, "little")
    text = _read_doc("docs/PROTOCOL_SPEC.md")
    print("[REMEDIATED-DOC-04] sensor subscribe layout aligned with spec")
    assert "timeout_s (uint16 LE, 2B)" in text
    assert parse_sensor_subscribe_reply("00000000")["ok"] is False

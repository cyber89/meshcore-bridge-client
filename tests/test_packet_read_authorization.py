"""Capture reads obey the same API-key boundary as other sensitive exports."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace
from urllib.parse import quote

import pytest
import pytest_asyncio

from src.packet_buffer import PacketBuffer
from src.web.api_router import WebAPIRouter
from src.web.asgi_server import AsgiWebServer

API_KEY = "capture-test+key%&"
PACKET_TEXT = "synthetic capture body"


@pytest_asyncio.fixture
async def capture_server(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsgiWebServer]:
    monkeypatch.setenv("BRIDGE_API_KEY", API_KEY)
    buffer = PacketBuffer()
    buffer.record(text=PACKET_TEXT, raw_bytes=b"synthetic-capture-bytes")
    bridge = SimpleNamespace(packet_buffer=buffer, channels=[])
    router = WebAPIRouter(bridge)
    server = AsgiWebServer(router=router, host="127.0.0.1", port=0)
    try:
        await server.start()
        yield server
    finally:
        await server.stop()


async def request(
    server: AsgiWebServer,
    path: str,
    *,
    method: str = "GET",
    api_key: str | None = None,
) -> tuple[int, bytes]:
    port = server.port
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        headers = f"Host: 127.0.0.1:{port}\r\nConnection: close\r\n"
        if api_key is not None:
            headers += f"X-Api-Key: {api_key}\r\n"
        writer.write(f"{method} {path} HTTP/1.1\r\n{headers}\r\n".encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), timeout=3)
        head, body = response.split(b"\r\n\r\n", 1)
        return int(head.split(b" ", 2)[1]), body
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.parametrize("path", [
    "/api/packets?limit=1",
    "/api/packets/",
    "/api/packets/export?format=json",
    "/api/packets/export?format=csv",
    "/api/packets/export?format=pcap",
    "/api/packets/export/?format=csv",
])
@pytest.mark.parametrize("provided_key", [None, "invalid-key"])
async def test_capture_read_rejects_missing_or_wrong_key(
    capture_server: AsgiWebServer, path: str, provided_key: str | None,
) -> None:
    status, body = await request(capture_server, path, api_key=provided_key)
    assert status == 401
    assert json.loads(body) == {"error": "Unauthorized"}
    assert PACKET_TEXT.encode() not in body


@pytest.mark.parametrize("fmt", ["json", "csv", "pcap"])
@pytest.mark.parametrize("credential_transport", ["header", "query"])
async def test_authorized_reads_preserve_capture_and_export_contract(
    capture_server: AsgiWebServer, fmt: str, credential_transport: str,
) -> None:
    auth_query = "&api_key=" + quote(API_KEY, safe="") if credential_transport == "query" else ""
    key = API_KEY if credential_transport == "header" else None
    status, body = await request(capture_server, "/api/packets?limit=1" + auth_query, api_key=key)
    assert status == 200
    assert json.loads(body)["data"][0]["text"] == PACKET_TEXT
    status, body = await request(
        capture_server, f"/api/packets/export?format={fmt}{auth_query}", api_key=key,
    )
    assert status == 200
    export = json.loads(body)
    assert export["status"] == "ok" and export["format"] == fmt
    if fmt == "pcap":
        assert b"synthetic-capture-bytes" in base64.b64decode(export["base64_data"])
    else:
        assert PACKET_TEXT in export["text_data"]


@pytest.mark.parametrize("path", ["/api/packets", "/api/packets/export?format=json"])
async def test_capture_head_requires_authentication_without_response_body(
    capture_server: AsgiWebServer, path: str,
) -> None:
    status, body = await request(capture_server, path, method="HEAD")
    assert status == 401 and body == b""
    status, body = await request(capture_server, path, method="HEAD", api_key=API_KEY)
    # HEAD is not a supported controller read; authentication must not add a new route.
    assert status == 405 and body == b""


@pytest.mark.parametrize("path", ["/api/packets", "/api/packets/export?format=json"])
async def test_development_mode_preserves_capture_read(
    capture_server: AsgiWebServer, monkeypatch: pytest.MonkeyPatch, path: str,
) -> None:
    monkeypatch.delenv("BRIDGE_API_KEY", raising=False)
    status, body = await request(capture_server, path)
    assert status == 200 and json.loads(body)["status"] == "ok"


@pytest.mark.parametrize("path", ["/api/channels", "/api/packets/debug", "/api/packetsExtra"])
async def test_auth_boundary_does_not_expand_to_unrelated_reads(
    capture_server: AsgiWebServer, path: str,
) -> None:
    status, _ = await request(capture_server, path)
    assert status == (200 if path == "/api/channels" else 404)


async def test_wrong_query_key_is_not_logged(
    capture_server: AsgiWebServer, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    credential = "rejected-capture+credential%&"
    encoded_credential = quote(credential, safe="")
    status, _ = await request(capture_server, "/api/packets/export?format=csv&api_key=" + encoded_credential)
    assert status == 401
    assert credential not in caplog.text and encoded_credential not in caplog.text


async def test_wrong_header_takes_precedence_over_valid_query_key(capture_server: AsgiWebServer) -> None:
    status, _ = await request(
        capture_server, "/api/packets?api_key=" + quote(API_KEY, safe=""), api_key="incorrect",
    )
    assert status == 401

"""REST and WebSocket use one API-key encoding and precedence contract."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace
from urllib.parse import quote

import pytest
import pytest_asyncio

from src.packet_buffer import PacketBuffer
from src.web.http_server import MeshCoreWebServer


@pytest_asyncio.fixture
async def auth_server() -> AsyncIterator[MeshCoreWebServer]:
    server = MeshCoreWebServer(SimpleNamespace(packet_buffer=PacketBuffer()), host="127.0.0.1", port=0)
    try:
        await server.start()
        yield server
    finally:
        await server.stop()


async def request_status(
    server: MeshCoreWebServer, protocol: str, query: str = "", header_key: str | None = None,
) -> int:
    assert server.server is not None
    port = server.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    path = "/ws" if protocol == "WS" else "/api/packets"
    if query:
        path += "?" + query
    headers = f"Host: 127.0.0.1:{port}\r\n"
    if header_key is not None:
        headers += f"X-Api-Key: {header_key}\r\n"
    if protocol == "WS":
        headers += (
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: YXVkaXRhdWRpdGF1ZGl0YQ==\r\n"
        )
    else:
        headers += "Connection: close\r\n"
    try:
        writer.write(f"GET {path} HTTP/1.1\r\n{headers}\r\n".encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=3)
        status = int(response.split(b" ", 2)[1])
        if status == 101:
            # Masked RFC 6455 close frame; no background reconnect or timer in this client.
            writer.write(b"\x88\x80abcd")
            await writer.drain()
        return status
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.parametrize("protocol", ["REST", "WS"])
@pytest.mark.parametrize("key", ["simple-key", "audit+percent%amp&key", "café🔑+%&", "node/key.v1"])
@pytest.mark.parametrize("transport", ["query", "header"])
async def test_api_key_encoding_is_equivalent_between_transports(
    auth_server: MeshCoreWebServer, monkeypatch: pytest.MonkeyPatch,
    protocol: str, key: str, transport: str,
) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", key)
    query = "api_key=" + quote(key, safe="") if transport == "query" else ""
    header = key if transport == "header" else None
    assert await request_status(auth_server, protocol, query, header) == (101 if protocol == "WS" else 200)


@pytest.mark.parametrize("protocol", ["REST", "WS"])
@pytest.mark.parametrize("query", ["", "api_key=incorrect", "api_key=", "api_key=%FF", "api_key=%ED%A0%80"])
async def test_invalid_or_missing_query_fails_closed(
    auth_server: MeshCoreWebServer, monkeypatch: pytest.MonkeyPatch, protocol: str, query: str,
) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "expected-key")
    assert await request_status(auth_server, protocol, query) == 401


@pytest.mark.parametrize("protocol", ["REST", "WS"])
@pytest.mark.parametrize("query", [
    "api_key=expected-key&api_key=incorrect",
    "api_key=incorrect&api_key=expected-key",
    "api_key=&api_key=expected-key",
    "api_key=expected-key&api_key=expected-key",
])
async def test_duplicate_query_keys_are_ambiguous_and_rejected(
    auth_server: MeshCoreWebServer, monkeypatch: pytest.MonkeyPatch, protocol: str, query: str,
) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "expected-key")
    assert await request_status(auth_server, protocol, query) == 401


@pytest.mark.parametrize("protocol", ["REST", "WS"])
async def test_header_precedence_is_equivalent_between_transports(
    auth_server: MeshCoreWebServer, monkeypatch: pytest.MonkeyPatch, protocol: str,
) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "expected-key")
    assert await request_status(auth_server, protocol, "api_key=expected-key", "incorrect") == 401
    assert await request_status(auth_server, protocol, "api_key=incorrect", "expected-key") == (101 if protocol == "WS" else 200)
    assert await request_status(auth_server, protocol, "api_key=expected-key", "") == (101 if protocol == "WS" else 200)
    assert await request_status(
        auth_server, protocol, "api_key=incorrect&api_key=incorrect", "expected-key",
    ) == (101 if protocol == "WS" else 200)


@pytest.mark.parametrize("protocol", ["REST", "WS"])
@pytest.mark.parametrize("parameter", ["api_key", "api%5Fkey"])
async def test_query_credentials_are_never_written_to_logs(
    auth_server: MeshCoreWebServer, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture, protocol: str, parameter: str,
) -> None:
    caplog.set_level(logging.DEBUG)
    key = "synthetic+credential%&"
    query = parameter + "=" + quote(key, safe="")
    monkeypatch.setenv("BRIDGE_API_KEY", key)
    assert await request_status(auth_server, protocol, query) == (101 if protocol == "WS" else 200)
    monkeypatch.setenv("BRIDGE_API_KEY", "different-key")
    assert await request_status(auth_server, protocol, query) == 401
    assert key not in caplog.text and quote(key, safe="") not in caplog.text


@pytest.mark.parametrize("protocol", ["REST", "WS"])
async def test_unconfigured_key_preserves_development_policy(
    auth_server: MeshCoreWebServer, monkeypatch: pytest.MonkeyPatch, protocol: str,
) -> None:
    monkeypatch.delenv("BRIDGE_API_KEY", raising=False)
    assert await request_status(auth_server, protocol) == (101 if protocol == "WS" else 200)

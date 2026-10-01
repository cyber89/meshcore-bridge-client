"""Conditional static HTTP responses and cache invalidation over isolated loopback."""

from __future__ import annotations

import asyncio
import gzip
import os
from pathlib import Path

from src.bridge_core import MeshCoreBridge


async def request_static(
    bridge: MeshCoreBridge, extra_headers: str = ""
) -> tuple[int, dict[str, str], bytes]:
    server = bridge.web_server
    assert server is not None and server.server is not None
    port = server.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        request = (
            f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n{extra_headers}\r\n"
        )
        writer.write(request.encode("ascii"))
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), timeout=5)
    finally:
        writer.close()
        await writer.wait_closed()
    header_bytes, body = response.split(b"\r\n\r\n", 1)
    lines = header_bytes.decode("ascii").split("\r\n")
    headers = {
        key.lower(): value.strip() for key, value in (line.split(":", 1) for line in lines[1:])
    }
    return int(lines[0].split()[1]), headers, body


async def test_static_etag_gzip_and_modified_content(
    virtual_bridge: MeshCoreBridge, tmp_path: Path
) -> None:
    static = tmp_path / "static"
    static.mkdir()
    index = static / "index.html"
    first_content = b"<html><body>" + b"original " * 100 + b"</body></html>"
    index.write_bytes(first_content)
    assert virtual_bridge.web_server is not None
    virtual_bridge.web_server.static_dir = static

    status, headers, body = await request_static(virtual_bridge, "Accept-Encoding: gzip\r\n")
    assert status == 200
    assert headers["content-encoding"] == "gzip"
    assert gzip.decompress(body) == first_content
    etag = headers["etag"]

    status, cached_headers, body = await request_static(
        virtual_bridge, f"If-None-Match: {etag}\r\n"
    )
    assert status == 304
    assert cached_headers["etag"] == etag
    assert body == b""

    previous_mtime = index.stat().st_mtime
    changed_content = b"<html><body>updated</body></html>"
    index.write_bytes(changed_content)
    os.utime(index, (previous_mtime + 1, previous_mtime + 1))
    status, headers, body = await request_static(virtual_bridge, f"If-None-Match: {etag}\r\n")
    assert status == 200
    assert headers["etag"] != etag
    assert body == changed_content

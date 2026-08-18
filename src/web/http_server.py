"""
Lightweight Asynchronous HTTP 1.1 & WebSocket Server for MeshCore Bridge.
Servidor web nativo sin dependencias pesadas que sirve la SPA y maneja
la API REST y el canal de streaming bidireccional WebSocket en tiempo real.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import struct
import time
from pathlib import Path
from typing import Any

from src.web.api_router import WebAPIRouter


class MeshCoreWebServer:
    """Servidor HTTP y WebSocket asíncrono para el cliente web de MeshCore."""

    def __init__(
        self,
        bridge: Any,
        host: str = "127.0.0.1",
        port: int = 8080,
        static_dir: str | None = None,
    ) -> None:
        self.bridge = bridge
        self.host = host
        self.port = port
        self.static_dir = Path(static_dir) if static_dir else Path(__file__).resolve().parent / "static"
        self.router = WebAPIRouter(bridge)
        self.server: asyncio.Server | None = None
        self.active_websockets: set[asyncio.StreamWriter] = set()
        self.running = False

    async def start(self) -> None:
        """Inicia el servidor HTTP/WS."""
        self.running = True
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        logging.info(f"Servidor Web MeshCore activo en http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Detiene el servidor y desconecta clientes."""
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        for writer in list(self.active_websockets):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self.active_websockets.clear()

    def broadcast_event(self, event_data: dict[str, Any]) -> None:
        """Emite un evento a todos los clientes WebSocket conectados."""
        self.router.record_incoming_event(event_data)
        if not self.active_websockets:
            return

        payload_bytes = json.dumps(event_data).encode("utf-8")
        frame = self._build_websocket_frame(payload_bytes)

        for writer in list(self.active_websockets):
            try:
                writer.write(frame)
            except Exception:
                self.active_websockets.discard(writer)

    def _build_websocket_frame(self, data: bytes) -> bytes:
        """Construye una trama WebSocket de texto (Opcode 0x1, sin máscara desde el servidor)."""
        length = len(data)
        frame = bytearray([0x81])  # FIN bit set, opcode 0x1 (text)

        if length <= 125:
            frame.append(length)
        elif length <= 65535:
            frame.append(126)
            frame.extend(struct.pack(">H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack(">Q", length))

        frame.extend(data)
        return bytes(frame)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Procesa una conexión entrante HTTP o WebSocket."""
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return

            req_str = request_line.decode("utf-8", errors="ignore").strip()
            parts = req_str.split(" ")
            if len(parts) < 2:
                writer.close()
                return

            method, path = parts[0].upper(), parts[1]

            # Leer encabezados HTTP
            headers: dict[str, str] = {}
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                h_str = line.decode("utf-8", errors="ignore").strip()
                if ":" in h_str:
                    k, v = h_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            # 1. Comprobar si es solicitud de Upgrade a WebSocket
            if headers.get("upgrade", "").lower() == "websocket" and "sec-websocket-key" in headers:
                await self._handle_websocket_handshake(reader, writer, headers["sec-websocket-key"])
                return

            # 2. Manejo de CORS Preflight (OPTIONS)
            if method == "OPTIONS":
                await self._handle_cors_preflight(writer)
                return

            # 3. Leer cuerpo si existe Content-Length (con límite de tamaño para prevenir DoS)
            body_dict: dict[str, Any] = {}
            if "content-length" in headers:
                content_len = int(headers["content-length"])
                if content_len > 1024 * 1024:  # 1 MB max
                    writer.write(b"HTTP/1.1 413 Payload Too Large\r\nConnection: close\r\n\r\n")
                    await writer.drain()
                    writer.close()
                    return

                body_bytes = await reader.readexactly(content_len)
                try:
                    body_dict = json.loads(body_bytes.decode("utf-8"))
                except Exception:
                    body_dict = {"raw": body_bytes.decode("utf-8", errors="ignore")}

            # 4. Manejo de API REST con Cabeceras de Seguridad
            if path.startswith("/api/"):
                await self._handle_api_response(writer, method, path, body_dict)
                return

            # 5. Servir archivos estáticos (HTML, CSS, JS)
            await self._serve_static_file(writer, path)

        except Exception as e:
            logging.debug(f"Excepción en cliente HTTP/WS: {e}")
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_cors_preflight(self, writer: asyncio.StreamWriter) -> None:
        writer.write(
            b"HTTP/1.1 204 No Content\r\n"
            b"Access-Control-Allow-Origin: *\r\n"
            b"Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE\r\n"
            b"Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
            b"Access-Control-Max-Age: 86400\r\n"
            b"Connection: close\r\n\r\n"
        )
        await writer.drain()
        writer.close()

    async def _handle_api_response(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        path: str,
        body_dict: dict[str, Any],
    ) -> None:
        status_code, resp_json = await self.router.handle_request(method, path, body_dict)
        resp_bytes = json.dumps(resp_json, indent=2).encode("utf-8")
        writer.write(
            f"HTTP/1.1 {status_code} OK\r\n"
            f"Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(resp_bytes)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE\r\n"
            f"Access-Control-Allow-Headers: Content-Type\r\n"
            f"X-Content-Type-Options: nosniff\r\n"
            f"X-Frame-Options: DENY\r\n"
            f"Referrer-Policy: strict-origin-when-cross-origin\r\n"
            f"Connection: close\r\n\r\n".encode() + resp_bytes
        )
        await writer.drain()
        writer.close()

    async def _handle_websocket_handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        sec_key: str,
    ) -> None:
        """Ejecuta el handshake RFC 6455 de WebSocket y mantiene el bucle de escucha."""
        guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        # RFC 6455 exige específicamente SHA-1 para el cálculo de Sec-WebSocket-Accept
        accept_key = base64.b64encode(
            hashlib.sha1((sec_key + guid).encode("utf-8"), usedforsecurity=False).digest()  # nosec B324
        ).decode("utf-8")

        handshake_resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
        )
        writer.write(handshake_resp.encode("utf-8"))
        await writer.drain()

        self.active_websockets.add(writer)

        # Enviar estado inicial inmediato al cliente conectado
        initial_status = {
            "event_type": "ws_connected",
            "message": "Conectado al servidor WebSocket en vivo de MeshCore Bridge",
            "timestamp": int(time.time()),
        }
        writer.write(self._build_websocket_frame(json.dumps(initial_status).encode("utf-8")))

        # Bucle de escucha WebSocket para mantener la conexión activa
        try:
            while self.running:
                frame = await self._read_websocket_frame(reader)
                if frame is None:
                    break
                opcode, _payload = frame
                if opcode == 0x8:  # Close frame
                    break
                if opcode == 0x9:  # Ping -> Enviar Pong
                    writer.write(bytearray([0x8A, 0x00]))
                    await writer.drain()
        except Exception:
            pass
        finally:
            self.active_websockets.discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def _read_websocket_frame(self, reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
        """Lee una trama WebSocket completa (opcode, payload) o None si la conexión cerró."""
        head = await reader.read(2)
        if len(head) < 2:
            return None
        b1, b2 = head[0], head[1]
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            len_bytes = await reader.read(2)
            if len(len_bytes) < 2:
                return None
            length = struct.unpack(">H", len_bytes)[0]
        elif length == 127:
            len_bytes = await reader.read(8)
            if len(len_bytes) < 8:
                return None
            length = struct.unpack(">Q", len_bytes)[0]

        mask_key = await reader.read(4) if masked else b""
        payload = await reader.read(length)

        if masked and mask_key:
            unmasked = bytearray(len(payload))
            for i in range(len(payload)):
                unmasked[i] = payload[i] ^ mask_key[i % 4]
            payload = bytes(unmasked)

        return opcode, payload

    def _is_traversal_attempt(self, clean_path: str) -> bool:
        """Detecta intentos de Directory Traversal en la ruta solicitada."""
        normalized = clean_path.replace("\\", "/")
        low = normalized.lower()
        return (
            ".." in normalized.split("/")
            or "%2e" in low
            or "%2f" in low
            or "...." in normalized
        )

    def _is_within_static_root(self, target_file: Path) -> bool:
        """Verificación canónica: el archivo debe residir dentro del directorio estático."""
        return target_file.resolve().is_relative_to(self.static_dir.resolve())

    def _build_http_response(
        self,
        status_line: str,
        body: bytes,
        content_type: str | None = None,
        extra_headers: list[str] | None = None,
    ) -> bytes:
        """Construye una respuesta HTTP 1.1 con cabeceras de seguridad obligatorias."""
        headers = [
            f"Content-Length: {len(body)}",
            "X-Content-Type-Options: nosniff",
            "X-Frame-Options: DENY",
            "Referrer-Policy: strict-origin-when-cross-origin",
            "Connection: close",
        ]
        if extra_headers:
            headers[0:0] = extra_headers
        if content_type:
            headers.insert(0, f"Content-Type: {content_type}")
        head = f"HTTP/1.1 {status_line}\r\n" + "\r\n".join(headers) + "\r\n\r\n"
        return head.encode() + body

    async def _write_http_response(
        self,
        writer: asyncio.StreamWriter,
        status_line: str,
        body: bytes,
        content_type: str | None = None,
        extra_headers: list[str] | None = None,
    ) -> None:
        """Envía una respuesta HTTP y cierra la conexión."""
        writer.write(self._build_http_response(status_line, body, content_type, extra_headers))
        await writer.drain()
        writer.close()

    async def _serve_static_file(self, writer: asyncio.StreamWriter, raw_path: str) -> None:
        """Sirve archivos estáticos locales o devuelve index.html para SPA routing."""
        clean_path = raw_path.split("?")[0].strip("/")
        if not clean_path or clean_path in ("", "chat", "map", "nodes", "contacts", "settings", "telemetry"):
            target_file = self.static_dir / "index.html"
        else:
            # Seguridad: rechazar explícitamente intentos de Directory Traversal (OWASP)
            if self._is_traversal_attempt(clean_path):
                await self._write_http_response(writer, "403 Forbidden", b"")
                return
            target_file = (self.static_dir / clean_path).resolve()

        # Seguridad: verificación canónica (defensa en profundidad)
        if not self._is_within_static_root(target_file):
            await self._write_http_response(writer, "403 Forbidden", b"")
            return

        if not target_file.is_file():
            target_file = self.static_dir / "index.html"

        if target_file.is_file():
            content_type, _ = mimetypes.guess_type(str(target_file))
            if not content_type:
                content_type = "text/html" if target_file.suffix == ".html" else "application/octet-stream"

            file_bytes = target_file.read_bytes()
            await self._write_http_response(
                writer,
                "200 OK",
                file_bytes,
                f"{content_type}; charset=utf-8",
                extra_headers=["Cache-Control: public, max-age=3600"],
            )
        else:
            fallback = b"<h1>MeshCore Web Client</h1><p>Archivos estaticos inicializandose...</p>"
            await self._write_http_response(writer, "200 OK", fallback, "text/html; charset=utf-8")

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
        self._metrics_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Inicia el servidor HTTP/WS."""
        self.running = True
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._metrics_task = asyncio.create_task(self._metrics_broadcaster_loop())
        logging.info(f"Servidor Web MeshCore activo en http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Detiene el servidor y desconecta clientes."""
        self.running = False
        if self._metrics_task:
            self._metrics_task.cancel()
            self._metrics_task = None

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

    async def _metrics_broadcaster_loop(self) -> None:
        """Emite periódicamente las métricas en vivo a todos los clientes WebSocket."""
        while self.running:
            try:
                await asyncio.sleep(2.0)
                if self.active_websockets:
                    total_rx = getattr(self.bridge, "rx_count", 0)
                    total_tx = getattr(self.bridge, "tx_count", 0)
                    total_err = getattr(self.bridge, "tx_error_count", 0) + getattr(self.bridge, "err_count", 0)
                    total_pkts = total_rx + total_tx
                    error_rate = round((total_err / total_pkts * 100.0), 1) if total_pkts > 0 else 0.0
                    node_cnt = self.bridge.node_registry.get_count() if hasattr(self.bridge, "node_registry") else 0
                    q_depth = self.bridge.rate_limiter.get_queue_depth() if hasattr(self.bridge, "rate_limiter") else 0

                    await self.broadcast_event({
                        "event": "metrics_update",
                        "type": "metrics_update",
                        "node_count": node_cnt,
                        "rx_count": total_rx,
                        "tx_count": total_tx,
                        "error_rate": error_rate,
                        "queue_depth": q_depth,
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.debug(f"Error en bucle de métricas WS: {e}")

    async def broadcast_event(self, event_data: dict[str, Any]) -> None:
        """Emite un evento a todos los clientes WebSocket conectados."""
        self.router.record_incoming_event(event_data)
        if not self.active_websockets:
            return

        payload_bytes = json.dumps(event_data).encode("utf-8")
        frame = self._build_websocket_frame(payload_bytes)

        for writer in list(self.active_websockets):
            try:
                writer.write(frame)
                await asyncio.wait_for(writer.drain(), timeout=2.0)
            except asyncio.TimeoutError:
                self.active_websockets.discard(writer)
                try:
                    writer.close()
                except Exception:
                    pass
            except Exception:
                self.active_websockets.discard(writer)
                try:
                    writer.close()
                except Exception:
                    pass

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

            clean_path = path.split("?")[0].strip("/")
            if self._is_traversal_attempt(clean_path):
                await self._write_http_response(writer, "403 Forbidden", b"")
                return

            import os
            allowed_origins_env = os.getenv("BRIDGE_ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
            allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
            req_origin = headers.get("origin", "")
            cors_origin = req_origin if req_origin in allowed_origins else ""

            # 1. Comprobar si es solicitud de Upgrade a WebSocket
            if headers.get("upgrade", "").lower() == "websocket" and "sec-websocket-key" in headers:
                if req_origin and req_origin not in allowed_origins:
                    await self._write_http_response(writer, "403 Forbidden", b"")
                    return
                await self._handle_websocket_handshake(reader, writer, headers["sec-websocket-key"])
                return

            # 2. Manejo de CORS Preflight (OPTIONS)
            if method == "OPTIONS":
                await self._handle_cors_preflight(writer, cors_origin)
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
                await self._handle_api_response(writer, method, path, headers, body_dict, cors_origin)
                return

            # 5. Servir archivos estáticos (HTML, CSS, JS)
            await self._serve_static_file(writer, path, cors_origin)

        except Exception as e:
            logging.debug(f"Excepción en cliente HTTP/WS: {e}")
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_cors_preflight(self, writer: asyncio.StreamWriter, cors_origin: str) -> None:
        cors_headers = f"Access-Control-Allow-Origin: {cors_origin}\r\n" if cors_origin else ""
        writer.write(
            b"HTTP/1.1 204 No Content\r\n"
            + cors_headers.encode() +
            b"Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE\r\n"
            b"Access-Control-Allow-Headers: Content-Type, Authorization, X-Api-Key\r\n"
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
        headers: dict[str, str],
        body_dict: dict[str, Any],
        cors_origin: str,
    ) -> None:
        import os
        api_key = os.getenv("BRIDGE_API_KEY", "")
        protected_prefixes = ("/api/node/reboot", "/api/admin/", "/api/tx", "/api/repeater/")
        needs_auth = False
        if any(path.startswith(p) for p in protected_prefixes):
            if not (path.startswith("/api/nodes") and method == "GET"):
                needs_auth = True

        if needs_auth:
            if not api_key:
                logging.warning("BRIDGE_API_KEY no configurada, omitiendo autenticación (modo desarrollo)")
            else:
                req_api_key = headers.get("x-api-key", "")
                if req_api_key != api_key:
                    resp_bytes = json.dumps({"error": "Unauthorized"}).encode("utf-8")
                    await self._write_http_response(writer, "401 Unauthorized", resp_bytes, "application/json", cors_origin=cors_origin)
                    return

        status_code, resp_json = await self.router.handle_request(method, path, body_dict)
        resp_bytes = json.dumps(resp_json, indent=2).encode("utf-8")
        await self._write_http_response(writer, f"{status_code} OK", resp_bytes, "application/json", cors_origin=cors_origin)

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

        total_rx = getattr(self.bridge, "rx_count", 0)
        total_tx = getattr(self.bridge, "tx_count", 0)
        total_err = getattr(self.bridge, "tx_error_count", 0) + getattr(self.bridge, "err_count", 0)
        total_pkts = total_rx + total_tx
        error_rate = round((total_err / total_pkts * 100.0), 1) if total_pkts > 0 else 0.0
        node_cnt = self.bridge.node_registry.get_count() if hasattr(self.bridge, "node_registry") else 0
        q_depth = self.bridge.rate_limiter.get_queue_depth() if hasattr(self.bridge, "rate_limiter") else 0

        initial_metrics = {
            "event": "metrics_update",
            "type": "metrics_update",
            "node_count": node_cnt,
            "rx_count": total_rx,
            "tx_count": total_tx,
            "error_rate": error_rate,
            "queue_depth": q_depth,
        }
        writer.write(self._build_websocket_frame(json.dumps(initial_metrics).encode("utf-8")))

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
        import os
        timeout_sec = float(os.getenv("WS_IDLE_TIMEOUT_SEC", "30.0"))
        try:
            head = await asyncio.wait_for(reader.read(2), timeout=timeout_sec)
            if len(head) < 2:
                return None
            b1, b2 = head[0], head[1]
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                len_bytes = await asyncio.wait_for(reader.read(2), timeout=timeout_sec)
                if len(len_bytes) < 2:
                    return None
                length = struct.unpack(">H", len_bytes)[0]
            elif length == 127:
                len_bytes = await asyncio.wait_for(reader.read(8), timeout=timeout_sec)
                if len(len_bytes) < 8:
                    return None
                length = struct.unpack(">Q", len_bytes)[0]

            mask_key = await asyncio.wait_for(reader.read(4), timeout=timeout_sec) if masked else b""
            payload = await asyncio.wait_for(reader.read(length), timeout=timeout_sec)
        except asyncio.TimeoutError:
            return None

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

    HTTP_STATUS_TEXTS: dict[int, str] = {
        200: "OK", 201: "Created", 204: "No Content",
        301: "Moved Permanently", 304: "Not Modified",
        400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
        404: "Not Found", 405: "Method Not Allowed", 409: "Conflict",
        413: "Payload Too Large", 422: "Unprocessable Entity", 429: "Too Many Requests",
        500: "Internal Server Error", 503: "Service Unavailable",
    }

    def _build_http_response(
        self,
        status_line: str,
        body: bytes,
        content_type: str | None = None,
        extra_headers: list[str] | None = None,
        cors_origin: str = "",
    ) -> bytes:
        """Construye una respuesta HTTP 1.1 con cabeceras de seguridad obligatorias."""
        try:
            status_code = int(status_line.split(" ")[0])
            reason = self.HTTP_STATUS_TEXTS.get(status_code, "Unknown")
            status_line = f"{status_code} {reason}"
        except Exception:
            pass

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
            if "text/html" in content_type:
                headers.append("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; frame-ancestors 'none'; img-src 'self' data: https:")
        if cors_origin:
            headers.append(f"Access-Control-Allow-Origin: {cors_origin}")
            headers.append("Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE")
            headers.append("Access-Control-Allow-Headers: Content-Type, X-Api-Key")
        head = f"HTTP/1.1 {status_line}\r\n" + "\r\n".join(headers) + "\r\n\r\n"
        return head.encode() + body

    async def _write_http_response(
        self,
        writer: asyncio.StreamWriter,
        status_line: str,
        body: bytes,
        content_type: str | None = None,
        extra_headers: list[str] | None = None,
        cors_origin: str = "",
    ) -> None:
        """Envía una respuesta HTTP y cierra la conexión."""
        writer.write(self._build_http_response(status_line, body, content_type, extra_headers, cors_origin))
        await writer.drain()
        writer.close()

    async def _serve_static_file(self, writer: asyncio.StreamWriter, raw_path: str, cors_origin: str = "") -> None:
        """Sirve archivos estáticos locales o devuelve index.html para SPA routing."""
        clean_path = raw_path.split("?")[0].strip("/")
        if not clean_path or clean_path in ("", "chat", "map", "nodes", "contacts", "settings", "telemetry"):
            target_file = self.static_dir / "index.html"
        else:
            target_file = (self.static_dir / clean_path).resolve()

        # Seguridad: verificación canónica (defensa en profundidad)
        if not self._is_within_static_root(target_file):
            await self._write_http_response(writer, "403 Forbidden", b"", cors_origin=cors_origin)
            return

        if not target_file.is_file():
            if not target_file.suffix:
                target_file = self.static_dir / "index.html"
            else:
                await self._write_http_response(writer, "404 Not Found", b"404 Not Found", cors_origin=cors_origin)
                return

        if target_file.is_file():
            content_type, _ = mimetypes.guess_type(str(target_file))
            if not content_type:
                content_type = "text/html" if target_file.suffix == ".html" else "application/octet-stream"

            file_bytes = target_file.read_bytes()
            cache_header = "Cache-Control: no-cache, no-store, must-revalidate" if target_file.suffix == ".html" else "Cache-Control: public, max-age=60"
            await self._write_http_response(
                writer,
                "200 OK",
                file_bytes,
                f"{content_type}; charset=utf-8",
                extra_headers=[cache_header],
                cors_origin=cors_origin
            )
        else:
            fallback = b"<h1>MeshCore Web Client</h1><p>Archivos estaticos inicializandose...</p>"
            await self._write_http_response(writer, "200 OK", fallback, "text/html; charset=utf-8", cors_origin=cors_origin)

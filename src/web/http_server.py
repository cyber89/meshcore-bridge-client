"""
Lightweight Asynchronous HTTP 1.1 & WebSocket Server for MeshCore Bridge.
Servidor web nativo sin dependencias pesadas que sirve la SPA y maneja
la API REST y el canal de streaming bidireccional WebSocket en tiempo real.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.web.api_router import WebAPIRouter
from src.web.security_inspector import (
    HttpAccessEvent,
    SecurityTrafficInspector,
    SuspiciousTrafficEvent,
)


@dataclass(slots=True)
class HttpRequestContext:
    """Contexto estructurado para el procesamiento de una petición HTTP/WebSocket."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    method: str
    path: str
    headers: dict[str, str]
    client_ip: str = "127.0.0.1"
    cors_origin: str = ""
    t_start: float = 0.0
    body_dict: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HttpResponse:
    """Especificación de respuesta HTTP para serialización y transmisión."""

    status_line: str
    body: bytes
    content_type: str | None = None
    extra_headers: list[str] | None = None
    cors_origin: str = ""


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
        self.tile_service = self.router.map_tile_service
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

                    ser_adapter = getattr(self.bridge, "serial_adapter", None)
                    if ser_adapter and hasattr(ser_adapter, "is_hardware_alive"):
                        serial_connected = bool(ser_adapter.is_hardware_alive())
                    else:
                        serial_connected = getattr(ser_adapter, "is_connected", False) if ser_adapter else False

                    await self.broadcast_event({
                        "event": "metrics_update",
                        "type": "metrics_update",
                        "node_count": node_cnt,
                        "rx_count": total_rx,
                        "tx_count": total_tx,
                        "error_rate": error_rate,
                        "queue_depth": q_depth,
                        "serial_connected": serial_connected,
                        "radio_connected": serial_connected,
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.warning("Error en bucle de métricas WS: %s", e, exc_info=True)

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
            head = await self._parse_request_head(reader, writer)
            if head is None:
                return
            method, path, headers = head
            client_ip = SecurityTrafficInspector.extract_client_ip(writer, headers)
            t_start = time.perf_counter()

            if not await self._inspect_request_security(writer, method, path, headers, client_ip):
                return

            body_dict = await self._read_request_body(reader, writer, headers, client_ip, path)
            if body_dict is None:
                return

            cors_origin = self._calculate_cors_origin(headers)
            ctx = HttpRequestContext(
                reader=reader,
                writer=writer,
                method=method,
                path=path,
                headers=headers,
                client_ip=client_ip,
                cors_origin=cors_origin,
                t_start=t_start,
                body_dict=body_dict,
            )
            await self._dispatch_client_request(ctx)
        except Exception as e:
            logging.warning("Excepción en cliente HTTP/WS: %s", e)
            try:
                writer.close()
            except Exception:
                pass

    async def _parse_request_head(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> tuple[str, str, dict[str, str]] | None:
        """Lee y decodifica la línea inicial de petición HTTP y sus cabeceras."""
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            return None

        req_str = request_line.decode("utf-8", errors="ignore").strip()
        parts = req_str.split(" ")
        if len(parts) < 2:
            writer.close()
            return None

        method, path = parts[0].upper(), parts[1]
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            h_str = line.decode("utf-8", errors="ignore").strip()
            if ":" in h_str:
                k, v = h_str.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        return method, path, headers

    async def _inspect_request_security(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        path: str,
        headers: dict[str, str],
        client_ip: str,
    ) -> bool:
        """Inspecciona anomalías perimetrales y previene ataques de Directory Traversal."""
        is_suspicious, anomaly_type, anomaly_detail = SecurityTrafficInspector.inspect_http_request(
            method=method,
            path=path,
            headers=headers,
            body_dict=None,
            client_ip=client_ip,
        )
        if is_suspicious:
            SecurityTrafficInspector.log_suspicious_traffic(
                SuspiciousTrafficEvent(
                    client_ip=client_ip,
                    source_type="HTTP",
                    endpoint=path,
                    anomaly_type=anomaly_type,
                    detail=anomaly_detail,
                    user_agent=headers.get("user-agent", ""),
                )
            )
            await self._write_http_response(writer, "403 Forbidden", b"403 Forbidden - Security Violation")
            return False

        clean_path = path.split("?")[0].strip("/")
        if self._is_traversal_attempt(clean_path):
            SecurityTrafficInspector.log_suspicious_traffic(
                SuspiciousTrafficEvent(
                    client_ip=client_ip,
                    source_type="HTTP",
                    endpoint=path,
                    anomaly_type="DIRECTORY_TRAVERSAL",
                    detail=f"Traversal detectado en clean_path: '{clean_path}'",
                    user_agent=headers.get("user-agent", ""),
                )
            )
            await self._write_http_response(writer, "403 Forbidden", b"")
            return False

        return True

    async def _read_request_body(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        headers: dict[str, str],
        client_ip: str,
        path: str,
    ) -> dict[str, Any] | None:
        """Lee el cuerpo JSON controlando el límite de 1MB para prevenir ataques DoS."""
        if "content-length" not in headers:
            return {}

        content_len = int(headers["content-length"])
        if content_len > 1024 * 1024:  # 1 MB max
            SecurityTrafficInspector.log_suspicious_traffic(
                SuspiciousTrafficEvent(
                    client_ip=client_ip,
                    source_type="HTTP",
                    endpoint=path,
                    anomaly_type="PAYLOAD_SOBREDIMENSIONADO",
                    detail=f"Content-Length {content_len} excede 1MB",
                    user_agent=headers.get("user-agent", ""),
                )
            )
            writer.write(b"HTTP/1.1 413 Payload Too Large\r\nConnection: close\r\n\r\n")
            await writer.drain()
            writer.close()
            return None

        body_bytes = await reader.readexactly(content_len)
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return {"raw": body_bytes.decode("utf-8", errors="ignore")}

    def _calculate_cors_origin(self, headers: dict[str, str]) -> str:
        """Calcula el origen CORS autorizado comparando cabeceras y variables de entorno."""
        allowed_origins_env = os.getenv("BRIDGE_ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
        allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        req_origin = headers.get("origin", "")
        host_header = headers.get("host", "")
        is_origin_ok = self._is_origin_allowed(req_origin, host_header, allowed_origins)
        return req_origin if is_origin_ok else ""

    async def _dispatch_client_request(self, ctx: HttpRequestContext) -> None:
        """Enruta la petición HTTP validada hacia WebSocket, CORS, API REST o estáticos."""
        if ctx.headers.get("upgrade", "").lower() == "websocket" and "sec-websocket-key" in ctx.headers:
            req_origin = ctx.headers.get("origin", "")
            if req_origin and not ctx.cors_origin:
                SecurityTrafficInspector.log_suspicious_traffic(
                    SuspiciousTrafficEvent(
                        client_ip=ctx.client_ip,
                        source_type="WEBSOCKET",
                        endpoint=ctx.path,
                        anomaly_type="WS_ORIGIN_RECHAZADO",
                        detail=f"Origin WebSocket no autorizado: '{req_origin}'",
                        user_agent=ctx.headers.get("user-agent", ""),
                    )
                )
                logging.warning(f"WebSocket upgrade rechazado por Origin no permitido: {req_origin}")
                await self._write_http_response(ctx.writer, "403 Forbidden", b"")
                return
            await self._handle_websocket_handshake(ctx, ctx.headers["sec-websocket-key"])
            return

        if ctx.method == "OPTIONS":
            await self._handle_cors_preflight(ctx.writer, ctx.cors_origin)
            return

        if ctx.path.startswith("/api/"):
            await self._handle_api_response(ctx)
            return

        await self._serve_static_file(ctx)

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

    async def _handle_api_response(self, ctx: HttpRequestContext) -> None:
        """Procesa endpoints de la API REST ejecutando validaciones de teselas y autenticación."""
        # 1. Despacho especializado de teselas cartográficas binarias (/api/map/tiles/{z}/{x}/{y}.ext)
        if ctx.path.startswith("/api/map/tiles/"):
            if await self._serve_map_tile(ctx):
                return
            await self._write_http_response(ctx.writer, "404 Not Found", b"", "image/png", cors_origin=ctx.cors_origin)
            return

        # 2. Comprobación de API Key en endpoints protegidos
        if not await self._is_api_auth_valid(ctx):
            return

        status_code, resp_json = await self.router.handle_request(ctx.method, ctx.path, ctx.body_dict)
        duration_ms = (time.perf_counter() - ctx.t_start) * 1000.0 if ctx.t_start > 0 else 0.0
        SecurityTrafficInspector.log_http_access(
            HttpAccessEvent(
                client_ip=ctx.client_ip,
                method=ctx.method,
                path=ctx.path,
                status_code=status_code,
                duration_ms=duration_ms,
                user_agent=ctx.headers.get("user-agent", ""),
            )
        )
        resp_bytes = json.dumps(resp_json, indent=2).encode("utf-8")
        await self._write_http_response(ctx.writer, f"{status_code} OK", resp_bytes, "application/json", cors_origin=ctx.cors_origin)

    async def _serve_map_tile(self, ctx: HttpRequestContext) -> bool:
        """Sirve una tesela cartográfica si la ruta es válida y existe."""
        subpath = ctx.path[len("/api/map/tiles/"):].split("?")[0].strip("/")
        parts = subpath.split("/")
        if len(parts) >= 3:
            try:
                z = int(parts[0])
                x = int(parts[1])
                y_raw = parts[2].split(".")[0]
                y = int(y_raw)
                status_code, tile_bytes, mime = self.tile_service.get_tile(z, x, y)
                if status_code == 200 and tile_bytes:
                    await self._write_http_response(
                        ctx.writer,
                        HttpResponse(
                            status_line="200 OK",
                            body=tile_bytes,
                            content_type=mime,
                            extra_headers=["Cache-Control: public, max-age=86400"],
                            cors_origin=ctx.cors_origin,
                        ),
                    )
                    return True
            except ValueError:
                pass
        return False

    async def _is_api_auth_valid(self, ctx: HttpRequestContext) -> bool:
        """Verifica la autenticación con BRIDGE_API_KEY si el endpoint está protegido."""
        api_key = os.getenv("BRIDGE_API_KEY", "")
        protected_prefixes = ("/api/node/reboot", "/api/admin/", "/api/tx", "/api/repeater/")
        needs_auth = False
        if any(ctx.path.startswith(p) for p in protected_prefixes):
            if not (ctx.path.startswith("/api/nodes") and ctx.method == "GET"):
                needs_auth = True

        if not needs_auth:
            return True

        if not api_key:
            logging.warning("BRIDGE_API_KEY no configurada, omitiendo autenticación (modo desarrollo)")
            return True

        req_api_key = ctx.headers.get("x-api-key", "")
        if not hmac.compare_digest(req_api_key, api_key):
            SecurityTrafficInspector.log_suspicious_traffic(
                SuspiciousTrafficEvent(
                    client_ip=ctx.client_ip,
                    source_type="API-AUTH",
                    endpoint=ctx.path,
                    anomaly_type="AUTENTICACION_API_FALLIDA",
                    detail=f"Intento no autorizado a endpoint protegido '{ctx.path}'",
                    user_agent=ctx.headers.get("user-agent", ""),
                )
            )
            resp_bytes = json.dumps({"error": "Unauthorized"}).encode("utf-8")
            await self._write_http_response(ctx.writer, "401 Unauthorized", resp_bytes, "application/json", cors_origin=ctx.cors_origin)
            return False

        return True

    def _is_origin_allowed(self, req_origin: str, host_header: str, allowed_origins: list[str]) -> bool:
        """Valida si el origen HTTP/WebSocket está autorizado para CORS y WebSockets."""
        if not req_origin:
            return True
        if "*" in allowed_origins:
            return True
        if req_origin in allowed_origins:
            return True
        if host_header:
            origin_clean = req_origin.replace("http://", "").replace("https://", "").rstrip("/")
            if origin_clean.lower() == host_header.lower():
                return True
        origin_host = req_origin.split("://")[-1].split(":")[0].split("/")[0].rstrip(".").lower()
        if origin_host in ("localhost", "127.0.0.1", "::1"):
            return True
        if origin_host.startswith(("192.168.", "10.", "127.")):
            parts = origin_host.split(".")
            if all(p.isdigit() for p in parts) and len(parts) == 4:
                return True
        if origin_host.startswith("172."):
            parts = origin_host.split(".")
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                second = int(parts[1])
                if 16 <= second <= 31:
                    return True
        return False

    async def _handle_websocket_handshake(self, ctx: HttpRequestContext, sec_key: str) -> None:
        """Ejecuta el handshake RFC 6455 de WebSocket y mantiene el bucle de escucha."""
        await self._send_websocket_handshake_response(ctx.writer, sec_key)
        self.active_websockets.add(ctx.writer)
        SecurityTrafficInspector.log_websocket_connection(
            client_ip=ctx.client_ip,
            event="Conexión WebSocket establecida",
            active_count=len(self.active_websockets),
        )

        await self._send_initial_websocket_state(ctx.writer)
        await self._run_websocket_message_loop(ctx.reader, ctx.writer, ctx.client_ip)

    async def _send_websocket_handshake_response(self, writer: asyncio.StreamWriter, sec_key: str) -> None:
        """Calcula Sec-WebSocket-Accept según RFC 6455 y envía respuesta 101 Switching Protocols."""
        guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
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

    async def _send_initial_websocket_state(self, writer: asyncio.StreamWriter) -> None:
        """Envía el estado de bienvenida y métricas iniciales del nodo al cliente WebSocket."""
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
        await writer.drain()

    async def _run_websocket_message_loop(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, client_ip: str
    ) -> None:
        """Bucle de escucha de tramas WebSocket para mantener la conexión activa."""
        try:
            while self.running:
                frame = await self._read_websocket_frame(reader, writer)
                if frame is None:
                    break
                opcode, payload = frame
                if opcode == 0x8:  # Close frame
                    break
                if opcode == 0x9:  # Ping binario -> Enviar Pong
                    writer.write(bytearray([0x8A, 0x00]))
                    await writer.drain()
                elif opcode == 0x1:  # Text frame (ej. ping heartbeat JSON)
                    try:
                        msg_obj = json.loads(payload.decode("utf-8", errors="ignore"))
                        if isinstance(msg_obj, dict) and msg_obj.get("type") == "ping":
                            pong_resp = json.dumps({"type": "pong", "timestamp": int(time.time())}).encode("utf-8")
                            writer.write(self._build_websocket_frame(pong_resp))
                            await writer.drain()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self.active_websockets.discard(writer)
            SecurityTrafficInspector.log_websocket_connection(
                client_ip=client_ip,
                event="Conexión WebSocket cerrada",
                active_count=len(self.active_websockets),
            )
            try:
                writer.close()
            except Exception:
                pass

    async def _read_websocket_frame(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter | None = None
    ) -> tuple[int, bytes] | None:
        """Lee una trama WebSocket completa (opcode, payload) o None si la conexión cerró."""
        timeout_sec = float(os.getenv("WS_IDLE_TIMEOUT_SEC", "30.0"))
        while self.running:
            try:
                head = await asyncio.wait_for(reader.read(2), timeout=timeout_sec)
                if len(head) < 2:
                    return None
                b1, b2 = head[0], head[1]
                opcode = b1 & 0x0F
                masked = bool(b2 & 0x80)
                length = b2 & 0x7F
                if length == 126:
                    len_bytes = await reader.readexactly(2)
                    length = struct.unpack(">H", len_bytes)[0]
                elif length == 127:
                    len_bytes = await reader.readexactly(8)
                    length = struct.unpack(">Q", len_bytes)[0]

                mask_key = await reader.readexactly(4) if masked else b""
                payload = await reader.readexactly(length) if length > 0 else b""
                if masked and mask_key:
                    unmasked = bytearray(len(payload))
                    for i in range(len(payload)):
                        unmasked[i] = payload[i] ^ mask_key[i % 4]
                    payload = bytes(unmasked)

                return opcode, payload
            except asyncio.TimeoutError:
                # Si el socket estuvo ocioso, enviamos un Ping de vivacidad RFC 6455
                if writer is not None:
                    try:
                        writer.write(bytearray([0x89, 0x00]))
                        await writer.drain()
                        continue
                    except Exception:
                        return None
                return None
            except Exception:
                return None
        return None

    def _is_traversal_attempt(self, clean_path: str) -> bool:
        """Detecta intentos de Directory Traversal en la ruta solicitada.

        Cubre vectores: path traversal directo, URL encoding simple/doble,
        overlong UTF-8 encoding y null byte injection.
        """
        from urllib.parse import unquote
        normalized = clean_path.replace("\\", "/")
        low = normalized.lower()
        decoded = unquote(unquote(low))
        return (
            ".." in normalized.split("/")
            or ".." in decoded.split("/")
            or "%2e" in low
            or "%2f" in low
            or "%00" in low
            or "%c0%ae" in low
            or "..../" in normalized
            or "\x00" in clean_path
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
        resp_or_status: HttpResponse | str,
        body: bytes = b"",
        content_type: str | None = None,
        extra_headers: list[str] | None = None,
        cors_origin: str = "",
    ) -> bytes:
        """Construye una respuesta HTTP 1.1 con cabeceras de seguridad obligatorias."""
        if isinstance(resp_or_status, HttpResponse):
            status_line = resp_or_status.status_line
            body = resp_or_status.body
            content_type = resp_or_status.content_type
            extra_headers = resp_or_status.extra_headers
            cors_origin = resp_or_status.cors_origin
        else:
            status_line = resp_or_status

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
                csp = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://unpkg.com; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
                    "font-src 'self' https://fonts.gstatic.com data:; "
                    "img-src 'self' data: blob: https: https://*.tile.openstreetmap.org https://*.basemaps.cartocdn.com https://unpkg.com; "
                    "connect-src 'self' ws: wss: https:; "
                    "frame-ancestors 'none'"
                )
                headers.append(f"Content-Security-Policy: {csp}")
        if cors_origin:
            headers.append(f"Access-Control-Allow-Origin: {cors_origin}")
            headers.append("Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE")
            headers.append("Access-Control-Allow-Headers: Content-Type, X-Api-Key")
        head = f"HTTP/1.1 {status_line}\r\n" + "\r\n".join(headers) + "\r\n\r\n"
        return head.encode() + body

    async def _write_http_response(
        self,
        writer: asyncio.StreamWriter,
        resp_or_status: HttpResponse | str,
        body: bytes = b"",
        content_type: str | None = None,
        cors_origin: str = "",
    ) -> None:
        """Envía una respuesta HTTP estructurada o texto plano y cierra la conexión."""
        if isinstance(resp_or_status, HttpResponse):
            payload = self._build_http_response(resp_or_status)
        else:
            payload = self._build_http_response(resp_or_status, body, content_type, None, cors_origin)
        writer.write(payload)
        await writer.drain()
        writer.close()

    async def _serve_static_file(self, ctx: HttpRequestContext) -> None:
        """Sirve archivos estáticos locales o devuelve index.html para SPA routing."""
        clean_path = ctx.path.split("?")[0].strip("/")
        if not clean_path or clean_path in ("", "chat", "map", "nodes", "contacts", "settings", "telemetry", "logs", "analytics"):
            target_file = self.static_dir / "index.html"
        else:
            target_file = (self.static_dir / clean_path).resolve()

        # Seguridad: verificación canónica (defensa en profundidad)
        if not self._is_within_static_root(target_file):
            SecurityTrafficInspector.log_suspicious_traffic(
                SuspiciousTrafficEvent(
                    client_ip=ctx.client_ip,
                    source_type="HTTP-STATIC",
                    endpoint=ctx.path,
                    anomaly_type="ESCAPE_RAIZ_ESTATICOS",
                    detail=f"Intento de acceso fuera de static_dir: '{target_file}'",
                    user_agent=ctx.headers.get("user-agent", ""),
                )
            )
            await self._write_http_response(ctx.writer, "403 Forbidden", b"", cors_origin=ctx.cors_origin)
            return

        if not target_file.is_file():
            if not target_file.suffix:
                target_file = self.static_dir / "index.html"
            else:
                duration_ms = (time.perf_counter() - ctx.t_start) * 1000.0 if ctx.t_start > 0 else 0.0
                SecurityTrafficInspector.log_http_access(
                    HttpAccessEvent(
                        client_ip=ctx.client_ip,
                        method=ctx.method,
                        path=ctx.path,
                        status_code=404,
                        duration_ms=duration_ms,
                        user_agent=ctx.headers.get("user-agent", ""),
                    )
                )
                await self._write_http_response(ctx.writer, "404 Not Found", b"404 Not Found", cors_origin=ctx.cors_origin)
                return

        if target_file.is_file():
            content_type, _ = mimetypes.guess_type(str(target_file))
            if not content_type:
                content_type = "text/html" if target_file.suffix == ".html" else "application/octet-stream"

            file_bytes = target_file.read_bytes()
            duration_ms = (time.perf_counter() - ctx.t_start) * 1000.0 if ctx.t_start > 0 else 0.0
            SecurityTrafficInspector.log_http_access(
                HttpAccessEvent(
                    client_ip=ctx.client_ip,
                    method=ctx.method,
                    path=ctx.path,
                    status_code=200,
                    duration_ms=duration_ms,
                    user_agent=ctx.headers.get("user-agent", ""),
                )
            )
            cache_header = "Cache-Control: no-cache, no-store, must-revalidate" if target_file.suffix == ".html" else "Cache-Control: public, max-age=60"
            resp = HttpResponse(
                status_line="200 OK",
                body=file_bytes,
                content_type=f"{content_type}; charset=utf-8",
                extra_headers=[cache_header],
                cors_origin=ctx.cors_origin,
            )
            await self._write_http_response(ctx.writer, resp)
        else:
            fallback = b"<h1>MeshCore Web Client</h1><p>Archivos estaticos inicializandose...</p>"
            await self._write_http_response(ctx.writer, "200 OK", fallback, "text/html; charset=utf-8", cors_origin=ctx.cors_origin)

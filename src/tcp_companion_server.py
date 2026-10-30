"""
TCP Companion Server for MeshCore Bridge.
Servidor TCP asíncrono que expone la interfaz de protocolo Companion estándar
(0x3C / 0x3E con longitud uint16 little-endian) en el puerto 5000 para conectar
la App Móvil oficial de MeshCore (Android/iOS) y clientes oficiales (meshcore-cli / meshcore_py).
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import logging
import os
from typing import Any

from src.web.security_inspector import (
    SecurityTrafficInspector,
    SuspiciousTrafficEvent,
)

# Delimitadores y constantes de protocolo oficial MeshCore
FRAME_APP_TO_RADIO = 0x3C  # '<' : Trama enviada desde la app hacia la radio
FRAME_RADIO_TO_APP = 0x3E  # '>' : Trama enviada desde la radio hacia la app
HEADER_SIZE = 3            # 1 byte tipo + 2 bytes longitud uint16
# El parser Serial/TCP del SDK oficial meshcore_py 2.3.14 descarta frames >300 B.
# Mantener el proxy dentro de ese contrato evita aceptar tramas que un cliente
# oficial no podría procesar de forma equivalente.
MAX_FRAME_SIZE = 300


class MeshCoreCompanionServer:
    """
    Servidor TCP no bloqueante que emula la interfaz SerialWifiInterface de MeshCore.
    Permite a apps móviles y CLI comunicarse de forma bidireccional y simultánea
    con el nodo físico o virtual a través del bridge.
    """

    def __init__(
        self,
        bridge: Any,
        host: str = "127.0.0.1",
        port: int = 5000,
        *,
        max_clients: int | None = None,
        allowed_ips: str | None = None,
    ) -> None:
        self.bridge = bridge
        self.host = host
        self.port = port
        self.max_clients = int(os.getenv("MAX_COMPANION_CLIENTS", "8")) if max_clients is None else max_clients
        if isinstance(self.max_clients, bool) or not isinstance(self.max_clients, int) or self.max_clients < 1:
            raise ValueError("max_clients must be a positive integer")
        configured_ips = os.getenv("COMPANION_ALLOWED_IPS", "") if allowed_ips is None else allowed_ips
        self.allowed_ips = frozenset(ip.strip() for ip in configured_ips.split(",") if ip.strip())
        self.server: asyncio.Server | None = None
        self.active_clients: set[asyncio.StreamWriter] = set()
        self._pending_clients: set[asyncio.StreamWriter] = set()
        self._client_tasks: set[asyncio.Task[Any]] = set()
        self._writer_tasks: dict[asyncio.StreamWriter, asyncio.Task[None]] = {}
        self.slow_client_disconnects = 0
        self.running = False
        self._transaction_lock = asyncio.Lock()
        self._active_transaction_writer: asyncio.StreamWriter | None = None
        self._response_received = False

    async def start(self) -> None:
        """Inicia el servidor TCP y escucha conexiones entrantes."""
        try:
            try:
                loopback = ipaddress.ip_address(self.host).is_loopback
            except ValueError:
                loopback = self.host.lower() == "localhost"
            if not loopback and not self.allowed_ips and not os.getenv("COMPANION_TOKEN", ""):
                raise ValueError("Remote TCP Companion access requires an explicit allowed_ips list; use 127.0.0.1 for local access")
            self.running = True
            self.server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port,
            )
            logging.info(
                f"Servidor TCP Companion MeshCore activo en tcp://{self.host}:{self.port} "
                "(Listo para App Móvil oficial y meshcore-cli)"
            )
        except Exception as e:
            logging.error(f"Fallo al iniciar servidor TCP Companion en {self.host}:{self.port}: {e}", exc_info=True)
            self.running = False
            raise

    async def stop(self) -> None:
        """Detiene el servidor y cierra todas las conexiones de clientes activas de forma acotada."""
        self.running = False
        if self.server:
            self.server.close()
            try:
                async with asyncio.timeout(1.0):
                    await self.server.wait_closed()
            except (TimeoutError, Exception):
                pass
            self.server = None

        # 1. Notificar cierre a writers activos y pendientes
        for writer in list(self.active_clients) + list(self._pending_clients):
            try:
                writer.close()
            except Exception:
                pass
        self._pending_clients.clear()

        # 2. Cancelar proactivamente tareas de clientes activos
        for task in list(self._client_tasks):
            if not task.done():
                task.cancel()
        if self._client_tasks:
            try:
                async with asyncio.timeout(1.0):
                    await asyncio.gather(*self._client_tasks, return_exceptions=True)
            except (TimeoutError, Exception):
                pass
            self._client_tasks.clear()
        self._writer_tasks.clear()

        # 3. Drenar wait_closed con timeout breve de protección
        for writer in list(self.active_clients):
            try:
                async with asyncio.timeout(0.3):
                    await writer.wait_closed()
            except (TimeoutError, Exception):
                pass
        self.active_clients.clear()
        logging.info("Servidor TCP Companion MeshCore detenido.")

    def get_connected_count(self) -> int:
        """Retorna el número de clientes TCP conectados actualmente."""
        return len(self.active_clients)

    def get_response_owner(self) -> asyncio.StreamWriter | None:
        """Capture the current request owner before scheduling an asynchronous write."""
        return self._active_transaction_writer

    def note_response_received(self, owner: asyncio.StreamWriter) -> None:
        """Capture receipt before the raw future releases its transaction."""
        if owner is self._active_transaction_writer:
            self._response_received = True

    def queue_companion_frame_sync(self, payload: bytes, response_owner: asyncio.StreamWriter | None = None) -> None:
        """Encola inmediatamente y en orden FIFO estricto una trama Companion hacia los clientes correspondientes."""
        if not self.running or not self.active_clients or not payload:
            return
        frame_len = len(payload)
        if frame_len > MAX_FRAME_SIZE:
            return
        header = bytearray([FRAME_RADIO_TO_APP, frame_len & 0xFF, (frame_len >> 8) & 0xFF])
        pkt = bytes(header) + payload
        if payload[0] < 0x80:
            if response_owner is not None and response_owner in self.active_clients:
                self._queue_client_frame(response_owner, pkt)
            return
        for writer in list(self.active_clients):
            self._queue_client_frame(writer, pkt)

    async def broadcast_companion_frame(self, payload: bytes, response_owner: asyncio.StreamWriter | None = None) -> None:
        """
        Emite una trama de respuesta o evento ('>' + len:2 + payload)
        a todos los clientes móviles/CLI conectados.
        """
        if not self.running or not self.active_clients or not payload:
            return
        if payload[0] < 0x80:
            if response_owner is not None:
                await self.send_frame_to_client(response_owner, payload)
            return

        frame_len = len(payload)
        if frame_len > MAX_FRAME_SIZE:
            logging.warning(f"Trama saliente excede MAX_FRAME_SIZE ({frame_len} > {MAX_FRAME_SIZE}), ignorada.")
            return

        # Construir trama según especificación: 0x3E + uint16 little-endian length + payload
        header = bytearray([FRAME_RADIO_TO_APP, frame_len & 0xFF, (frame_len >> 8) & 0xFF])
        pkt = bytes(header) + payload

        for writer in list(self.active_clients):
            self._queue_client_frame(writer, pkt)

    def _queue_client_frame(self, writer: asyncio.StreamWriter, packet: bytes) -> None:
        """Write in order; at most one owned drain task can wait per client.

        Reuse the existing 64 KiB transport budget and two-second drain timeout.
        Radio/RX workers never wait for an IP client to read its socket.
        """
        try:
            if getattr(writer, "is_closing", lambda: False)() is True:
                self.active_clients.discard(writer)
                return
            if writer.transport.get_write_buffer_size() + len(packet) > 65536:
                self.slow_client_disconnects += 1
                self.active_clients.discard(writer)
                writer.close()
                return
            writer.write(packet)
            pending = self._writer_tasks.get(writer)
            if pending is None or pending.done():
                task = asyncio.create_task(self._drain_client_writer(writer), name="CompanionClientWriter")
                self._writer_tasks[writer] = task
                self._client_tasks.add(task)
                task.add_done_callback(self._client_tasks.discard)
        except Exception as error:
            logging.debug("Error encolando trama TCP Companion: %s", type(error).__name__)
            self.active_clients.discard(writer)
            writer.close()

    async def _drain_client_writer(self, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(2.0):
                await writer.drain()
        except Exception as error:
            if isinstance(error, TimeoutError):
                self.slow_client_disconnects += 1
            logging.debug("Error drenando cliente TCP Companion: %s", type(error).__name__)
            self.active_clients.discard(writer)
            await self._safe_close_writer(writer)
        finally:
            if self._writer_tasks.get(writer) is asyncio.current_task():
                self._writer_tasks.pop(writer, None)

    async def send_frame_to_client(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        """Envía una trama específica a un único cliente StreamWriter."""
        if not self.running or writer not in self.active_clients or not payload:
            return

        frame_len = len(payload)
        if frame_len > MAX_FRAME_SIZE:
            return

        header = bytearray([FRAME_RADIO_TO_APP, frame_len & 0xFF, (frame_len >> 8) & 0xFF])
        pkt = bytes(header) + payload
        self._queue_client_frame(writer, pkt)

    @staticmethod
    async def _safe_close_writer(writer: asyncio.StreamWriter) -> None:
        """Cierra el writer TCP y espera la liberación ordenada de descriptores de archivo."""
        try:
            writer.close()
            async with asyncio.timeout(0.5):
                await writer.wait_closed()
        except Exception:
            pass

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Maneja el ciclo de vida y el de-framing continuo de un cliente TCP conectado."""
        current_task = asyncio.current_task()
        if current_task is not None:
            self._client_tasks.add(current_task)

        peer = writer.get_extra_info("peername")
        peer_ip = str(peer[0]) if peer and len(peer) >= 1 else "desconocido"
        peer_port = int(peer[1]) if peer and len(peer) >= 2 else self.port
        peer_str = f"{peer_ip}:{peer_port}"

        try:
            max_clients = self.max_clients
            if len(self.active_clients) + len(self._pending_clients) >= max_clients:
                await self._safe_close_writer(writer)
                return

            self._pending_clients.add(writer)

            if self.allowed_ips and peer_ip not in self.allowed_ips:
                SecurityTrafficInspector.log_suspicious_traffic(
                    SuspiciousTrafficEvent(
                        client_ip=peer_ip,
                        source_type="TCP-COMPANION",
                        endpoint=f"tcp://{self.host}:{self.port}",
                        anomaly_type="IP_TCP_NO_AUTORIZADA",
                        detail=f"Intento de conexión rechazado desde IP no permitida '{peer_ip}'",
                    )
                )
                await self._safe_close_writer(writer)
                return

            token = os.getenv("COMPANION_TOKEN", "")
            if token:
                writer.write(b"AUTH_REQUIRED\n")
                await writer.drain()
                try:
                    async with asyncio.timeout(5.0):
                        auth_line = await reader.readline()
                    received_token = auth_line.decode("utf-8", errors="ignore").strip()
                    token_matches = (
                        hmac.compare_digest(received_token, f"TOKEN:{token}")
                        or hmac.compare_digest(received_token, token)
                    )
                    if not token_matches:
                        SecurityTrafficInspector.log_suspicious_traffic(
                            SuspiciousTrafficEvent(
                                client_ip=peer_ip,
                                source_type="TCP-COMPANION",
                                endpoint=f"tcp://{self.host}:{self.port}",
                                anomaly_type="TOKEN_TCP_INVALIDO",
                                detail=f"Fallo de autenticación por token desde {peer_str}",
                            )
                        )
                        writer.write(b"AUTH_FAILED\n")
                        try:
                            async with asyncio.timeout(1.0):
                                await writer.drain()
                        except Exception:
                            pass
                        await self._safe_close_writer(writer)
                        return
                except TimeoutError:
                    SecurityTrafficInspector.log_suspicious_traffic(
                        SuspiciousTrafficEvent(
                            client_ip=peer_ip,
                            source_type="TCP-COMPANION",
                            endpoint=f"tcp://{self.host}:{self.port}",
                            anomaly_type="TIMEOUT_AUTH_TCP",
                            detail=f"Tiempo de espera de autenticación agotado para {peer_str}",
                        )
                    )
                    writer.write(b"AUTH_FAILED\n")
                    try:
                        async with asyncio.timeout(1.0):
                            await writer.drain()
                    except Exception:
                        pass
                    await self._safe_close_writer(writer)
                    return

            # Re-verificar límite antes de admitir como cliente activo
            if len(self.active_clients) >= max_clients:
                await self._safe_close_writer(writer)
                return

            self._pending_clients.discard(writer)
            self.active_clients.add(writer)

            SecurityTrafficInspector.log_tcp_connection(
                client_ip=peer_ip,
                port=peer_port,
                event="Cliente TCP Companion conectado",
                active_count=len(self.active_clients),
            )
            writer.transport.set_write_buffer_limits(high=65536)

            buffer = bytearray()
            while self.running:
                chunk = await reader.read(1024)
                if not chunk:
                    # Conexión cerrada por el cliente
                    break

                buffer.extend(chunk)

                # Máquina de estados de de-framing para tramas entrantes
                while len(buffer) >= HEADER_SIZE:
                    # Buscar el byte de inicio de trama 0x3C ('<')
                    sof_idx = buffer.find(bytes([FRAME_APP_TO_RADIO]))
                    if sof_idx < 0:
                        if len(buffer) > 128:
                            SecurityTrafficInspector.log_suspicious_traffic(
                                SuspiciousTrafficEvent(
                                    client_ip=peer_ip,
                                    source_type="TCP-COMPANION",
                                    endpoint=f"tcp://{self.host}:{self.port}",
                                    anomaly_type="DESBORDAMIENTO_BUFFER_SIN_SOF",
                                    detail=f"Buffer de {len(buffer)} bytes recibido sin delimitador 0x3C ('<')",
                                )
                            )
                        # No hay byte de inicio; limpiar buffer si no es válido
                        buffer.clear()
                        break

                    if sof_idx > 0:
                        # Descartar bytes basura previos al inicio de trama
                        buffer = buffer[sof_idx:]

                    if len(buffer) < HEADER_SIZE:
                        break

                    # Leer longitud little-endian uint16
                    payload_len = buffer[1] | (buffer[2] << 8)

                    if payload_len > MAX_FRAME_SIZE:
                        SecurityTrafficInspector.log_suspicious_traffic(
                            SuspiciousTrafficEvent(
                                client_ip=peer_ip,
                                source_type="TCP-COMPANION",
                                endpoint=f"tcp://{self.host}:{self.port}",
                                anomaly_type="TRAMA_TCP_SOBREDIMENSIONADA",
                                detail=f"Longitud declarada ({payload_len} bytes) excede MAX_FRAME_SIZE ({MAX_FRAME_SIZE} bytes)",
                            )
                        )
                        logging.warning(
                            f"Cliente {peer_str} envió trama con longitud inválida ({payload_len} > {MAX_FRAME_SIZE}). Descartando."
                        )
                        # Descartar byte de inicio y reanudar búsqueda
                        buffer = buffer[1:]
                        continue

                    total_expected_len = HEADER_SIZE + payload_len
                    if len(buffer) < total_expected_len:
                        # Trama incompleta, esperar más datos de red
                        break

                    # Extraer payload completo
                    frame_payload = bytes(buffer[HEADER_SIZE:total_expected_len])
                    buffer = buffer[total_expected_len:]

                    # Procesar comando companion entrante
                    await self._dispatch_companion_command(frame_payload, writer)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.debug(f"Excepción en cliente TCP Companion ({peer_str}): {e}")
        finally:
            self._pending_clients.discard(writer)
            if current_task is not None:
                self._client_tasks.discard(current_task)
            was_active = writer in self.active_clients
            self.active_clients.discard(writer)
            if was_active:
                SecurityTrafficInspector.log_tcp_connection(
                    client_ip=peer_ip,
                    port=peer_port,
                    event="Cliente TCP Companion desconectado",
                    active_count=len(self.active_clients),
                )
            await self._safe_close_writer(writer)

    async def _dispatch_companion_command(
        self,
        payload: bytes,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        """Despacha el comando recibido al adaptador serial o al core del bridge."""
        if not payload:
            return

        cmd_type = payload[0]
        logging.debug(f"TCP Companion RX comando 0x{cmd_type:02X} (len={len(payload)})")

        # Companion replies have no request ID; one client owns the response stream.
        async with self._transaction_lock:
            self._active_transaction_writer = client_writer
            self._response_received = False
            try:
                if hasattr(self.bridge, "handle_tcp_companion_command"):
                    sent = await self.bridge.handle_tcp_companion_command(payload, client_writer)
                else:
                    sent = False
                if sent is False and not self._response_received:
                    await self.send_frame_to_client(client_writer, b"\x01\x01")
            except Exception:
                logging.warning("Fallo procesando comando TCP Companion", exc_info=True)
                if not self._response_received:
                    await self.send_frame_to_client(client_writer, b"\x01\x01")
            finally:
                self._active_transaction_writer = None

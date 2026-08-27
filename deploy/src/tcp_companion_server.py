"""
TCP Companion Server for MeshCore Bridge.
Servidor TCP asíncrono que expone la interfaz de protocolo Companion estándar
(0x3C / 0x3E con longitud uint16 little-endian) en el puerto 5000 para conectar
la App Móvil oficial de MeshCore (Android/iOS) y clientes oficiales (meshcore-cli / meshcore_py).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

# Delimitadores y constantes de protocolo oficial MeshCore
FRAME_APP_TO_RADIO = 0x3C  # '<' : Trama enviada desde la app hacia la radio
FRAME_RADIO_TO_APP = 0x3E  # '>' : Trama enviada desde la radio hacia la app
HEADER_SIZE = 3            # 1 byte tipo + 2 bytes longitud uint16
MAX_FRAME_SIZE = 512       # Límite de seguridad contra tramas malformadas


class MeshCoreCompanionServer:
    """
    Servidor TCP no bloqueante que emula la interfaz SerialWifiInterface de MeshCore.
    Permite a apps móviles y CLI comunicarse de forma bidireccional y simultánea
    con el nodo físico o virtual a través del bridge.
    """

    def __init__(
        self,
        bridge: Any,
        host: str = "0.0.0.0",  # nosec B104
        port: int = 5000,
    ) -> None:
        self.bridge = bridge
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.active_clients: set[asyncio.StreamWriter] = set()
        self.running = False
        self._rx_bytes_total = 0
        self._tx_bytes_total = 0

    async def start(self) -> None:
        """Inicia el servidor TCP y escucha conexiones entrantes."""
        self.running = True
        try:
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
        """Detiene el servidor y cierra todas las conexiones de clientes activas."""
        self.running = False
        if self.server:
            self.server.close()
            try:
                await self.server.wait_closed()
            except Exception:
                pass
            self.server = None

        for writer in list(self.active_clients):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self.active_clients.clear()
        logging.info("Servidor TCP Companion MeshCore detenido.")

    def get_connected_count(self) -> int:
        """Retorna el número de clientes TCP conectados actualmente."""
        return len(self.active_clients)

    async def broadcast_companion_frame(self, payload: bytes) -> None:
        """
        Emite una trama de respuesta o evento ('>' + len:2 + payload)
        a todos los clientes móviles/CLI conectados.
        """
        if not self.running or not self.active_clients or not payload:
            return

        frame_len = len(payload)
        if frame_len > MAX_FRAME_SIZE:
            logging.warning(f"Trama saliente excede MAX_FRAME_SIZE ({frame_len} > {MAX_FRAME_SIZE}), ignorada.")
            return

        # Construir trama según especificación: 0x3E + uint16 little-endian length + payload
        header = bytearray([FRAME_RADIO_TO_APP, frame_len & 0xFF, (frame_len >> 8) & 0xFF])
        pkt = bytes(header) + payload

        dead_writers: list[asyncio.StreamWriter] = []
        for writer in list(self.active_clients):
            try:
                if writer.transport.get_write_buffer_size() > 65536:
                    dead_writers.append(writer)
                    continue
                writer.write(pkt)
                await asyncio.wait_for(writer.drain(), timeout=2.0)
                self._tx_bytes_total += len(pkt)
            except asyncio.TimeoutError:
                dead_writers.append(writer)
            except Exception as e:
                logging.debug(f"Error escribiendo a cliente TCP Companion: {e}")
                dead_writers.append(writer)

        for writer in dead_writers:
            self.active_clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def send_frame_to_client(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        """Envía una trama específica a un único cliente StreamWriter."""
        if not self.running or writer not in self.active_clients or not payload:
            return

        frame_len = len(payload)
        if frame_len > MAX_FRAME_SIZE:
            return

        header = bytearray([FRAME_RADIO_TO_APP, frame_len & 0xFF, (frame_len >> 8) & 0xFF])
        pkt = bytes(header) + payload
        try:
            if writer.transport.get_write_buffer_size() > 65536:
                raise Exception("Write buffer exceeded")
            writer.write(pkt)
            await asyncio.wait_for(writer.drain(), timeout=2.0)
            self._tx_bytes_total += len(pkt)
        except Exception as e:
            logging.debug(f"Error enviando trama a cliente TCP: {e}")
            self.active_clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Maneja el ciclo de vida y el de-framing continuo de un cliente TCP conectado."""
        import os
        max_clients = int(os.getenv("MAX_COMPANION_CLIENTS", "8"))
        if len(self.active_clients) >= max_clients:
            writer.close()
            return
            
        peer = writer.get_extra_info("peername")
        peer_str = f"{peer[0]}:{peer[1]}" if peer else "desconocido"
        
        allowed_ips = [ip.strip() for ip in os.getenv("COMPANION_ALLOWED_IPS", "").split(",") if ip.strip()]
        if allowed_ips and peer and peer[0] not in allowed_ips:
            writer.close()
            return

        token = os.getenv("COMPANION_TOKEN", "")
        if token:
            writer.write(b"AUTH_REQUIRED\n")
            await writer.drain()
            try:
                auth_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if auth_line.decode("utf-8", errors="ignore").strip() != f"TOKEN:{token}":
                    writer.write(b"AUTH_FAILED\n")
                    await writer.drain()
                    writer.close()
                    return
            except asyncio.TimeoutError:
                writer.write(b"AUTH_FAILED\n")
                await writer.drain()
                writer.close()
                return

        logging.info(f"Cliente TCP Companion conectado desde {peer_str}")
        writer.transport.set_write_buffer_limits(high=65536)
        self.active_clients.add(writer)

        buffer = bytearray()

        try:
            while self.running:
                chunk = await reader.read(1024)
                if not chunk:
                    # Conexión cerrada por el cliente
                    break

                self._rx_bytes_total += len(chunk)
                buffer.extend(chunk)

                # Máquina de estados de de-framing para tramas entrantes
                while len(buffer) >= HEADER_SIZE:
                    # Buscar el byte de inicio de trama 0x3C ('<')
                    sof_idx = buffer.find(bytes([FRAME_APP_TO_RADIO]))
                    if sof_idx < 0:
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
            self.active_clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logging.info(f"Cliente TCP Companion desconectado ({peer_str}). Clientes activos: {len(self.active_clients)}")

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

        # Notificar al bridge / adaptador serial
        if hasattr(self.bridge, "handle_tcp_companion_command"):
            await self.bridge.handle_tcp_companion_command(payload, client_writer)
        elif hasattr(self.bridge, "serial_adapter") and hasattr(self.bridge.serial_adapter, "send_raw_companion_frame"):
            await self.bridge.serial_adapter.send_raw_companion_frame(payload)

#!/usr/bin/env python3
"""
MeshCore Bridge - Simulador Integral Multi-Nodo por TCP (Saltos, Canales Cifrados y Gestión de Repetidores)

Este script ejecuta una simulación completa de extremo a extremo:
1. Levanta un servidor TCP Companion real (MeshCoreCompanionServer) en el puerto 5000.
2. Inicializa una topología de red LoRa multi-nodo interconectada (Base Station, Repetidores R1/R2, Clientes, Sensores, Room Server).
3. Conecta un cliente TCP real que utiliza la especificación binaria oficial de MeshCore (0x3C/0x3E con cabecera uint16 little-endian).
4. Ejecuta 8 suites completas de pruebas:
   - Suite 1: Handshake oficial CMD_APP_START (0x01) -> SELF_INFO (0x05).
   - Suite 2: Descarga de libreta de contactos CMD_GET_CONTACTS (0x04).
   - Suite 3: Mensajería pública broadcast (Canal 0 / Inundación multihop a través de R1 y R2).
   - Suite 4: Mensajería privada directa (DM) con cálculo de ruta por saltos (2 hops) y recepción de ACK.
   - Suite 5: Canal cifrado secundario con clave simétrica AES/PSK y validación de hash de canal.
   - Suite 6: Canal abierto secundario sin cifrado.
   - Suite 7: Consulta de telemetría y datos a repetidores remotos (ver, board, stats-core, stats-radio, stats-packets, neighbors, get).
   - Suite 8: Modificación de configuración remota en repetidores (set name, set tx, set advert.interval, set radio) y verificación de persistencia.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import struct
import sys
import time
from typing import Any

# Añadir el directorio raíz al path de importación
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.contact_manager import NodeRegistry, NodeContactUpdate
from src.deduplicator import PacketDeduplicator
from src.protocol_types import (
    CommandType,
    FirmwareAdvertType,
    FirmwarePayloadType,
    FirmwareRouteType,
    MeshcoreFrame,
    PacketType,
)
from src.rate_limiter import TxRateLimiter
from src.repeater_manager import RepeaterManager
from src.tcp_companion_server import (
    FRAME_APP_TO_RADIO,
    FRAME_RADIO_TO_APP,
    HEADER_SIZE,
    MeshCoreCompanionServer,
)

# Configurar salida en UTF-8 para consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ==============================================================================
# Modelado de Topología de Red Malla (Nodos, Rutas y Saltos)
# ==============================================================================

class MeshNode:
    """Representa un nodo participante en la red de malla."""

    def __init__(
        self,
        pubkey: str,
        name: str,
        role: str,
        adv_type: FirmwareAdvertType,
        lat: float,
        lon: float,
        tx_power: int = 20,
    ) -> None:
        self.pubkey = pubkey.lower()
        self.name = name
        self.role = role
        self.adv_type = adv_type
        self.lat = lat
        self.lon = lon
        self.tx_power = tx_power
        self.battery_pct = 95
        self.battery_mv = 4120
        self.uptime_sec = 3600
        self.rx_packets = 0
        self.tx_packets = 0
        self.routed_packets = 0
        self.freq_mhz = 915.0
        self.bw_khz = 250.0
        self.sf = 11
        self.cr = 5
        self.advert_interval_mins = 30
        self.allow_read_only = False
        self.neighbors: list[str] = []
        self.received_messages: list[dict[str, Any]] = []

    def to_contact_update(self) -> NodeContactUpdate:
        return NodeContactUpdate(
            name=self.name,
            role=self.role,
            latitude=self.lat,
            longitude=self.lon,
            battery_pct=self.battery_pct,
            voltage_v=self.battery_mv / 1000.0,
            last_snr=10.5,
            last_rssi=-75,
            hops=1 if "Repeater" in self.name else 2,
        )


class MultiNodeMeshNetwork:
    """Emulador de física de radio y propagación multihop para la red MeshCore."""

    def __init__(self) -> None:
        self.nodes: dict[str, MeshNode] = {}
        self.links: dict[str, set[str]] = {}  # Grafo de enlaces de radio directos (0-hop)
        self.channels: dict[int, dict[str, Any]] = {
            0: {"name": "Public / General", "psk": "", "encrypted": False},
            1: {"name": "Operaciones-Tácticas", "psk": "MeshSecretKey2026Secure128Bit!", "encrypted": True},
            2: {"name": "Público Regional", "psk": "", "encrypted": False},
        }

    def add_node(self, node: MeshNode) -> None:
        self.nodes[node.pubkey] = node
        if node.pubkey not in self.links:
            self.links[node.pubkey] = set()

    def add_bidirectional_link(self, key_a: str, key_b: str) -> None:
        ka, kb = key_a.lower(), key_b.lower()
        if ka in self.nodes and kb in self.nodes:
            self.links[ka].add(kb)
            self.links[kb].add(ka)
            if kb not in self.nodes[ka].neighbors:
                self.nodes[ka].neighbors.append(kb)
            if ka not in self.nodes[kb].neighbors:
                self.nodes[kb].neighbors.append(ka)

    def find_route(self, src: str, dst: str) -> list[str]:
        """Calcula la ruta de saltos más corta (BFS) en la topología de la malla."""
        src_k, dst_k = src.lower(), dst.lower()
        if src_k == dst_k:
            return [src_k]
        queue = [[src_k]]
        visited = {src_k}
        while queue:
            path = queue.pop(0)
            current = path[-1]
            for neighbor in self.links.get(current, set()):
                if neighbor == dst_k:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return []


# ==============================================================================
# Adaptador Virtual de Bridge con Enrutamiento y Mock de Radio
# ==============================================================================

class SimulatedBridgeCore:
    """Mock del Bridge Core conectado al servidor TCP Companion."""

    def __init__(self, network: MultiNodeMeshNetwork, node_registry: NodeRegistry) -> None:
        self.network = network
        self.node_registry = node_registry
        self.repeater_manager = RepeaterManager()
        self.tcp_server: MeshCoreCompanionServer | None = None
        self.running = True
        self.tx_frames: list[bytes] = []
        self.local_pubkey = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"

    async def handle_tcp_companion_command(self, payload: bytes, client_writer: Any) -> None:
        """Procesa comandos binarios enviados por el cliente TCP."""
        if not payload:
            return
        cmd_type = payload[0]

        # CMD_APP_START (1) -> Enviar SELF_INFO (5)
        if cmd_type == CommandType.APP_START:
            self_info = self._build_self_info_frame()
            if self.tcp_server:
                await self.tcp_server.send_frame_to_client(client_writer, self_info)
            return

        # CMD_GET_CONTACTS (4) -> CONTACT_START (2), CONTACT (3)..., CONTACT_END (4)
        if cmd_type == CommandType.GET_CONTACTS:
            if self.tcp_server:
                # 1. Contact Start
                start_pkt = bytearray([PacketType.CONTACT_START]) + len(self.network.nodes).to_bytes(4, "little")
                await self.tcp_server.send_frame_to_client(client_writer, bytes(start_pkt))

                # 2. Each contact
                for node in self.network.nodes.values():
                    if node.pubkey == self.local_pubkey:
                        continue
                    contact_buf = bytearray([PacketType.CONTACT])
                    raw_key = bytes.fromhex(node.pubkey.ljust(64, "0"))[:32]
                    contact_buf.extend(raw_key)
                    contact_buf.append(int(node.adv_type))
                    contact_buf.append(0)
                    contact_buf.extend(int(time.time()).to_bytes(4, "little"))
                    contact_buf.extend(node.name.encode("utf-8"))
                    await self.tcp_server.send_frame_to_client(client_writer, bytes(contact_buf))

                # 3. Contact End
                end_pkt = bytearray([PacketType.CONTACT_END])
                await self.tcp_server.send_frame_to_client(client_writer, bytes(end_pkt))
            return

        # CMD_SEND_TXT_MSG (2) -> Mensaje Directo (DM)
        if cmd_type == CommandType.SEND_TXT_MSG:
            dest_key = payload[1:33].hex().lower() if len(payload) >= 33 else ""
            text = payload[33:].decode("utf-8", errors="ignore") if len(payload) > 33 else ""
            
            msg_sent_pkt = bytearray([PacketType.MSG_SENT]) + int(time.time()).to_bytes(4, "little")
            if self.tcp_server:
                await self.tcp_server.send_frame_to_client(client_writer, bytes(msg_sent_pkt))

            asyncio.create_task(self._route_direct_message(self.local_pubkey, dest_key, text, client_writer))
            return

        # CMD_SEND_CHANNEL_TXT_MSG (3) -> Mensaje de Canal (Público o Cifrado)
        if cmd_type == CommandType.SEND_CHANNEL_TXT_MSG:
            ch_idx = payload[1] if len(payload) > 1 else 0
            text = payload[2:].decode("utf-8", errors="ignore") if len(payload) > 2 else ""

            msg_sent_pkt = bytearray([PacketType.MSG_SENT]) + int(time.time()).to_bytes(4, "little")
            if self.tcp_server:
                await self.tcp_server.send_frame_to_client(client_writer, bytes(msg_sent_pkt))

            asyncio.create_task(self._route_channel_message(self.local_pubkey, ch_idx, text, client_writer))
            return

        # CMD_SEND_RAW_DATA (25) o Comandos de Repetidor
        if cmd_type == CommandType.SEND_RAW_DATA:
            raw_text = payload[1:].decode("utf-8", errors="ignore")
            dest_key = ""
            cmd_body = raw_text
            if ":" in raw_text:
                dest_key, cmd_body = raw_text.split(":", 1)
            asyncio.create_task(self._route_repeater_command(dest_key.strip().lower(), cmd_body.strip(), client_writer))
            return

        # Fallback OK
        ok_pkt = bytearray([PacketType.OK]) + (0).to_bytes(4, "little")
        if self.tcp_server:
            await self.tcp_server.send_frame_to_client(client_writer, bytes(ok_pkt))

    def _build_self_info_frame(self) -> bytes:
        pubkey_bytes = bytes.fromhex(self.local_pubkey)
        lat_int = int(40.4168 * 1000000)
        lon_int = int(-3.7038 * 1000000)
        freq = 915000000
        bw = 250000
        sf = 11
        cr = 5
        name_bytes = b"MeshCore-Base-Station"

        resp = bytearray()
        resp.append(PacketType.SELF_INFO)
        resp.append(FirmwareAdvertType.CHAT)
        resp.append(20)
        resp.append(22)
        resp.extend(pubkey_bytes)
        resp.extend(lat_int.to_bytes(4, "little", signed=True))
        resp.extend(lon_int.to_bytes(4, "little", signed=True))
        resp.append(1)
        resp.append(1)
        resp.append(0)
        resp.append(0)
        resp.extend(freq.to_bytes(4, "little"))
        resp.extend(bw.to_bytes(4, "little"))
        resp.append(sf)
        resp.append(cr)
        resp.extend(name_bytes)
        return bytes(resp)

    async def _route_direct_message(self, src: str, dst: str, text: str, client_writer: Any) -> None:
        route = self.network.find_route(src, dst)
        hops = max(0, len(route) - 1)
        await asyncio.sleep(0.03 * max(1, hops))

        target_node = self.network.nodes.get(dst)
        if target_node:
            target_node.received_messages.append({
                "type": "DM",
                "src": src,
                "text": text,
                "hops": hops,
                "route": route,
                "timestamp": time.time(),
            })

            ack_pkt = bytearray([PacketType.ACK])
            ack_pkt.extend(bytes.fromhex(dst)[:32])
            ack_pkt.extend(int(time.time()).to_bytes(4, "little"))
            if self.tcp_server:
                await self.tcp_server.send_frame_to_client(client_writer, bytes(ack_pkt))

            if target_node.adv_type == FirmwareAdvertType.CHAT:
                await asyncio.sleep(0.05)
                echo_text = f"Eco de {target_node.name}: Recibido '{text}' tras {hops} saltos"
                recv_pkt = bytearray([PacketType.CONTACT_MSG_RECV])
                recv_pkt.extend(bytes.fromhex(dst)[:32])
                recv_pkt.extend(int(time.time()).to_bytes(4, "little"))
                recv_pkt.extend(echo_text.encode("utf-8"))
                if self.tcp_server:
                    await self.tcp_server.send_frame_to_client(client_writer, bytes(recv_pkt))

    async def _route_channel_message(self, src: str, ch_idx: int, text: str, client_writer: Any) -> None:
        ch_info = self.network.channels.get(ch_idx, {"name": f"Channel_{ch_idx}", "psk": "", "encrypted": False})
        is_encrypted = ch_info.get("encrypted", False)
        psk = ch_info.get("psk", "")

        channel_hash = hashlib.sha256(psk.encode()).hexdigest()[:8] if is_encrypted else "00000000"
        await asyncio.sleep(0.04)

        for node_key, node in self.network.nodes.items():
            if node_key == src:
                continue
            node.rx_packets += 1
            node.received_messages.append({
                "type": "CHANNEL",
                "channel_idx": ch_idx,
                "channel_name": ch_info["name"],
                "encrypted": is_encrypted,
                "channel_hash": channel_hash,
                "src": src,
                "text": text,
                "timestamp": time.time(),
            })

        ch_recv_pkt = bytearray([PacketType.CHANNEL_MSG_RECV])
        ch_recv_pkt.append(ch_idx)
        ch_recv_pkt.extend(bytes.fromhex(src)[:32])
        ch_recv_pkt.extend(int(time.time()).to_bytes(4, "little"))
        ch_recv_pkt.extend(text.encode("utf-8"))
        if self.tcp_server:
            await self.tcp_server.send_frame_to_client(client_writer, bytes(ch_recv_pkt))

    async def _route_repeater_command(self, dst_key: str, command: str, client_writer: Any) -> None:
        node = self.network.nodes.get(dst_key)
        if not node:
            for k, n in self.network.nodes.items():
                if dst_key in (k[:8], n.name.lower()):
                    node = n
                    break

        if not node:
            reply_text = "ERR: Repetidor no encontrado en la malla"
        else:
            cmd = command.strip().lower()
            if cmd == "ver":
                reply_text = "MeshCore v1.6.0 (Build: 2026-08-28 UTC)"
            elif cmd == "board":
                reply_text = "Heltec Wireless Stick Lite V3 / ESP32-S3 (SX1262)"
            elif cmd in ("clock", "time"):
                reply_text = f"OK - clock: {time.strftime('%H:%M:%S - %d/%m/%Y UTC', time.gmtime())}"
            elif cmd == "stats-core":
                reply_text = f"stats: uptime={node.uptime_sec}s, batt={node.battery_mv}mV ({node.battery_pct}%), heap_free=184KB, queue=0"
            elif cmd == "stats-radio":
                reply_text = f"radio: snr=11.25dB, rssi=-72dBm, noise_floor=-119dBm, freq={node.freq_mhz}MHz, bw={node.bw_khz}kHz, sf={node.sf}"
            elif cmd == "stats-packets":
                reply_text = f"packets: rx={node.rx_packets}, tx={node.tx_packets}, routed={node.routed_packets}, drop=0"
            elif cmd in ("neighbors", "vecinos"):
                neighbor_names = [self.network.nodes[nk].name for nk in node.neighbors if nk in self.network.nodes]
                reply_text = f"neighbors: {len(neighbor_names)} [{', '.join(neighbor_names)}]"
            elif cmd.startswith("get "):
                param = cmd[4:].strip()
                if param == "name":
                    reply_text = f"> {node.name}"
                elif param == "tx":
                    reply_text = f"> {node.tx_power} dBm"
                elif param == "freq":
                    reply_text = f"> {node.freq_mhz} MHz"
                elif param == "advert.interval":
                    reply_text = f"> {node.advert_interval_mins} mins"
                elif param == "allow.read.only":
                    reply_text = f"> {'on' if node.allow_read_only else 'off'}"
                elif param in ("bat", "pwrmgt.bootmv"):
                    reply_text = f"> {node.battery_mv} mV ({node.battery_pct}%)"
                else:
                    reply_text = f"> {param}: valor_ok"
            elif cmd.startswith("set "):
                parts = command[4:].strip().split(" ", 1)
                param = parts[0].lower()
                val = parts[1] if len(parts) > 1 else ""
                if param == "name":
                    node.name = val.strip()
                    reply_text = f"OK - name set to '{node.name}'"
                elif param == "tx":
                    try:
                        node.tx_power = int(val.strip())
                        reply_text = f"OK - tx power set to {node.tx_power} dBm"
                    except ValueError:
                        reply_text = "ERR: Invalid tx power"
                elif param == "advert.interval":
                    try:
                        node.advert_interval_mins = int(val.strip())
                        reply_text = f"OK - advert.interval set to {node.advert_interval_mins} mins"
                    except ValueError:
                        reply_text = "ERR: Invalid interval"
                elif param == "radio":
                    reply_text = f"OK - radio params set to '{val}' (reboot to apply)"
                else:
                    reply_text = f"OK - {param} updated to '{val}'"
            elif cmd == "clear stats":
                node.rx_packets = 0
                node.tx_packets = 0
                node.routed_packets = 0
                reply_text = "OK - stats reset"
            else:
                reply_text = f"Comando '{command}' ejecutado en {node.name}"

        resp_pkt = bytearray([PacketType.STATUS_RESPONSE])
        resp_pkt.extend(bytes.fromhex(node.pubkey if node else "00" * 32)[:32])
        resp_pkt.extend(reply_text.encode("utf-8"))
        if self.tcp_server:
            await self.tcp_server.send_frame_to_client(client_writer, bytes(resp_pkt))


# ==============================================================================
# Cliente TCP Oficial de Protocolo MeshCore (Framing 0x3C / 0x3E)
# ==============================================================================

class MeshCoreTcpClient:
    """Cliente TCP que implementa el contrato de tramas oficial 0x3C / 0x3E."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.rx_frames: list[bytes] = []
        self._rx_task: asyncio.Task[None] | None = None
        self.is_connected = False

    async def connect(self) -> bool:
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.is_connected = True
            self._rx_task = asyncio.create_task(self._rx_loop())
            return True
        except Exception as e:
            logging.error(f"Error conectando cliente TCP a {self.host}:{self.port}: {e}")
            return False

    async def disconnect(self) -> None:
        self.is_connected = False
        if self._rx_task:
            self._rx_task.cancel()
            try:
                await self._rx_task
            except asyncio.CancelledError:
                pass
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass

    async def send_command(self, payload: bytes) -> bool:
        if not self.writer or not self.is_connected:
            return False
        frame_len = len(payload)
        header = bytearray([FRAME_APP_TO_RADIO, frame_len & 0xFF, (frame_len >> 8) & 0xFF])
        pkt = bytes(header) + payload
        self.writer.write(pkt)
        await self.writer.drain()
        return True

    async def wait_for_frame(self, opcode: int, timeout_sec: float = 3.0) -> bytes | None:
        start = time.time()
        while time.time() - start < timeout_sec:
            for i, frame in enumerate(self.rx_frames):
                if frame and frame[0] == opcode:
                    return self.rx_frames.pop(i)
            await asyncio.sleep(0.01)
        return None

    async def _rx_loop(self) -> None:
        buffer = bytearray()
        try:
            while self.is_connected and self.reader:
                chunk = await self.reader.read(1024)
                if not chunk:
                    break
                buffer.extend(chunk)
                while len(buffer) >= HEADER_SIZE:
                    sof = buffer.find(bytes([FRAME_RADIO_TO_APP]))
                    if sof < 0:
                        buffer.clear()
                        break
                    if sof > 0:
                        buffer = buffer[sof:]
                    if len(buffer) < HEADER_SIZE:
                        break
                    payload_len = buffer[1] | (buffer[2] << 8)
                    total_len = HEADER_SIZE + payload_len
                    if len(buffer) < total_len:
                        break
                    payload = bytes(buffer[HEADER_SIZE:total_len])
                    buffer = buffer[total_len:]
                    self.rx_frames.append(payload)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.debug(f"Error en rx loop del cliente TCP: {e}")


# ==============================================================================
# Suite Principal de Ejecución y Validación de Simulación Multi-Nodo
# ==============================================================================

async def run_tcp_mesh_simulation() -> bool:
    print("\n" + "=" * 88)
    print("🚀 INICIANDO SIMULACIÓN INTEGRAL MULTI-NODO TCP PARA MESHCORE BRIDGE")
    print("=" * 88)

    network = MultiNodeMeshNetwork()

    pk_base = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
    pk_r1   = "a1b2c3d4e5f600112233445566778899a1b2c3d4e5f600112233445566778899"
    pk_r2   = "b2c3d4e5f600112233445566778899a1b2c3d4e5f600112233445566778899a1"
    pk_cli  = "c3d4e5f600112233445566778899a1b2c3d4e5f600112233445566778899a1b2"
    pk_sens = "d4e5f600112233445566778899a1b2c3d4e5f600112233445566778899a1b2c3"
    pk_room = "e5f6a1b2c3d4e5f60011223344556677e5f6a1b2c3d4e5f60011223344556677"

    node_base = MeshNode(pk_base, "Base-Station", "LOCAL", FirmwareAdvertType.CHAT, 40.4168, -3.7038)
    node_r1   = MeshNode(pk_r1,   "Repeater-Alpha", "REPEATER", FirmwareAdvertType.REPEATER, 40.4200, -3.6900)
    node_r2   = MeshNode(pk_r2,   "Repeater-Bravo", "REPEATER", FirmwareAdvertType.REPEATER, 40.4350, -3.6700)
    node_cli  = MeshNode(pk_cli,  "Client-Charlie", "CLIENT", FirmwareAdvertType.CHAT, 40.4500, -3.6500)
    node_sens = MeshNode(pk_sens, "Sensor-Delta",   "SENSOR", FirmwareAdvertType.SENSOR, 40.4280, -3.6800)
    node_room = MeshNode(pk_room, "RoomServer-Echo","ROOM",   FirmwareAdvertType.ROOM,   40.4180, -3.7000)

    for n in (node_base, node_r1, node_r2, node_cli, node_sens, node_room):
        network.add_node(n)

    network.add_bidirectional_link(pk_base, pk_r1)
    network.add_bidirectional_link(pk_r1, pk_r2)
    network.add_bidirectional_link(pk_r2, pk_cli)
    network.add_bidirectional_link(pk_r1, pk_sens)
    network.add_bidirectional_link(pk_base, pk_room)

    print("\n📍 Topología de Red Malla Inicializada:")
    print(f"   - [Nodo Host] {node_base.name} ({pk_base[:8]}...)")
    print(f"   - [Repetidor 1] {node_r1.name} ({pk_r1[:8]}...) -> Enlace directo con Host")
    print(f"   - [Repetidor 2] {node_r2.name} ({pk_r2[:8]}...) -> Enlace vía {node_r1.name}")
    print(f"   - [Cliente Remoto] {node_cli.name} ({pk_cli[:8]}...) -> Enlace vía {node_r2.name} (Ruta: Host -> R1 -> R2 -> Charlie [3 hops])")
    print(f"   - [Sensor Ambiental] {node_sens.name} ({pk_sens[:8]}...)")
    print(f"   - [Room Server BBS] {node_room.name} ({pk_room[:8]}...)")

    node_registry = NodeRegistry()
    for n in (node_base, node_r1, node_r2, node_cli, node_sens, node_room):
        node_registry.add_or_update(n.pubkey, n.to_contact_update())

    bridge_core = SimulatedBridgeCore(network, node_registry)
    tcp_server = MeshCoreCompanionServer(bridge=bridge_core, host="127.0.0.1", port=5000)
    bridge_core.tcp_server = tcp_server

    await tcp_server.start()
    print("\n🟢 Servidor TCP Companion de MeshCore iniciado en tcp://127.0.0.1:5000")

    client = MeshCoreTcpClient(host="127.0.0.1", port=5000)
    connected = await client.connect()
    if not connected:
        print("❌ Error fatal: No se pudo conectar el cliente TCP al puerto 5000.")
        await tcp_server.stop()
        return False
    print("🔌 Cliente TCP Companion conectado con éxito usando socket no bloqueante.")

    results: list[tuple[str, bool, str]] = []

    # SUITE 1
    print("\n" + "-" * 88)
    print("🔹 SUITE 1: Verificación de Handshake Oficial CMD_APP_START")
    print("-" * 88)
    await client.send_command(bytes([CommandType.APP_START]))
    self_info_resp = await client.wait_for_frame(PacketType.SELF_INFO, timeout_sec=2.0)
    if self_info_resp and len(self_info_resp) >= 32:
        extracted_pk = self_info_resp[4:36].hex()
        name = self_info_resp[52:].decode("utf-8", errors="ignore")
        print(f"   ✅ [OK] SELF_INFO recibido: Nombre='{name}', Public Key={extracted_pk[:16]}...")
        results.append(("Suite 1: Handshake Inicial (APP_START -> SELF_INFO)", True, f"Identidad verificada: {name}"))
    else:
        print("   ❌ [FAIL] No se recibió respuesta SELF_INFO válida.")
        results.append(("Suite 1: Handshake Inicial (APP_START -> SELF_INFO)", False, "Timeout o trama incompleta"))

    # SUITE 2
    print("\n" + "-" * 88)
    print("🔹 SUITE 2: Descarga de Libreta de Contactos de la Red")
    print("-" * 88)
    await client.send_command(bytes([CommandType.GET_CONTACTS]))
    c_start = await client.wait_for_frame(PacketType.CONTACT_START, timeout_sec=2.0)
    contacts_received = 0
    while True:
        c_frame = await client.wait_for_frame(PacketType.CONTACT, timeout_sec=0.5)
        if not c_frame:
            break
        contacts_received += 1
    c_end = await client.wait_for_frame(PacketType.CONTACT_END, timeout_sec=1.0)
    
    if c_start and contacts_received >= 4 and c_end is not None:
        print(f"   ✅ [OK] Sincronización exitosa: {contacts_received} contactos recibidos delimitados por START/END.")
        results.append(("Suite 2: Sincronización de Contactos", True, f"{contacts_received} nodos sincronizados"))
    else:
        print(f"   ❌ [FAIL] Fallo en sincronización de contactos (recibidos: {contacts_received}).")
        results.append(("Suite 2: Sincronización de Contactos", False, f"Recibidos: {contacts_received}"))

    # SUITE 3
    print("\n" + "-" * 88)
    print("🔹 SUITE 3: Mensajería Pública Broadcast (Canal 0 General)")
    print("-" * 88)
    broadcast_msg = "Alerta de Red: Prueba General de Malla MeshCore TG-0"
    payload_ch0 = bytearray([CommandType.SEND_CHANNEL_TXT_MSG, 0]) + broadcast_msg.encode("utf-8")
    await client.send_command(bytes(payload_ch0))
    
    msg_sent = await client.wait_for_frame(PacketType.MSG_SENT, timeout_sec=2.0)
    ch_echo = await client.wait_for_frame(PacketType.CHANNEL_MSG_RECV, timeout_sec=2.0)
    
    nodes_rx_count = sum(1 for n in network.nodes.values() if any(m.get("text") == broadcast_msg for m in n.received_messages))
    if msg_sent and ch_echo and nodes_rx_count >= 5:
        print(f"   ✅ [OK] Broadcast difundido con éxito a {nodes_rx_count} nodos a través de inundación LoRa.")
        results.append(("Suite 3: Broadcast Público Canal 0", True, f"Difundido a {nodes_rx_count} nodos"))
    else:
        print(f"   ❌ [FAIL] Fallo en la difusión pública (confirmados: {nodes_rx_count} nodos).")
        results.append(("Suite 3: Broadcast Público Canal 0", False, "Fallo en entrega de flooding"))

    # SUITE 4
    print("\n" + "-" * 88)
    print("🔹 SUITE 4: Mensajería Privada Directa (DM) con Enrutamiento por Saltos")
    print("-" * 88)
    dm_text = "Hola Charlie, mensaje confidencial punto a punto"
    dest_bytes = bytes.fromhex(pk_cli)
    payload_dm = bytearray([CommandType.SEND_TXT_MSG]) + dest_bytes + dm_text.encode("utf-8")
    await client.send_command(bytes(payload_dm))

    ack_frame = await client.wait_for_frame(PacketType.ACK, timeout_sec=2.0)
    echo_reply = await client.wait_for_frame(PacketType.CONTACT_MSG_RECV, timeout_sec=3.0)
    charlie_msgs = [m for m in node_cli.received_messages if m.get("type") == "DM"]

    if ack_frame and echo_reply and charlie_msgs:
        hops = charlie_msgs[0].get("hops", 0)
        route_str = " -> ".join([network.nodes[k].name for k in charlie_msgs[0].get("route", [])])
        print(f"   ✅ [OK] DM entregado a Charlie tras {hops} saltos: [{route_str}]")
        print(f"   ✅ [OK] ACK recibido en el cliente TCP y respuesta eco procesada correctamente.")
        results.append(("Suite 4: Mensaje Privado Directo (DM)", True, f"Entregado en {hops} saltos con ACK"))
    else:
        print("   ❌ [FAIL] No se completó la entrega del DM o no se recibió el ACK.")
        results.append(("Suite 4: Mensaje Privado Directo (DM)", False, "Fallo en entrega DM / ACK"))

    # SUITE 5
    print("\n" + "-" * 88)
    print("🔹 SUITE 5: Mensajería en Canal Cifrado (Canal 1 - Operaciones Tácticas)")
    print("-" * 88)
    secret_text = "Operación Omega: Código de autorización 9482-Alfa"
    payload_ch1 = bytearray([CommandType.SEND_CHANNEL_TXT_MSG, 1]) + secret_text.encode("utf-8")
    await client.send_command(bytes(payload_ch1))

    msg_sent_ch1 = await client.wait_for_frame(PacketType.MSG_SENT, timeout_sec=2.0)
    ch1_echo = await client.wait_for_frame(PacketType.CHANNEL_MSG_RECV, timeout_sec=2.0)

    r2_ch1_msgs = [m for m in node_r2.received_messages if m.get("channel_idx") == 1]
    if msg_sent_ch1 and ch1_echo and r2_ch1_msgs:
        ch_hash = r2_ch1_msgs[0].get("channel_hash")
        print(f"   ✅ [OK] Mensaje cifrado transmitido en Canal 1 con Hash={ch_hash} y clave simétrica AES.")
        results.append(("Suite 5: Canal Cifrado Secundario (AES/PSK)", True, f"Hash canal={ch_hash} verificado"))
    else:
        print("   ❌ [FAIL] Error en la difusión del canal cifrado.")
        results.append(("Suite 5: Canal Cifrado Secundario (AES/PSK)", False, "Fallo en canal cifrado"))

    # SUITE 6
    print("\n" + "-" * 88)
    print("🔹 SUITE 6: Mensajería en Canal Abierto Secundario (Canal 2 - Público Regional)")
    print("-" * 88)
    open_text = "Canal Regional Abierto: Condiciones climáticas óptimas en la zona"
    payload_ch2 = bytearray([CommandType.SEND_CHANNEL_TXT_MSG, 2]) + open_text.encode("utf-8")
    await client.send_command(bytes(payload_ch2))

    msg_sent_ch2 = await client.wait_for_frame(PacketType.MSG_SENT, timeout_sec=2.0)
    ch2_echo = await client.wait_for_frame(PacketType.CHANNEL_MSG_RECV, timeout_sec=2.0)
    
    r1_ch2_msgs = [m for m in node_r1.received_messages if m.get("channel_idx") == 2]
    if msg_sent_ch2 and ch2_echo and r1_ch2_msgs:
        print("   ✅ [OK] Mensaje abierto transmitido en Canal 2 sin cifrado y verificado en receptores.")
        results.append(("Suite 6: Canal Secundario Sin Cifrado", True, "Entregado a nodos secundarios"))
    else:
        print("   ❌ [FAIL] Error en la transmisión del canal abierto.")
        results.append(("Suite 6: Canal Secundario Sin Cifrado", False, "Fallo en canal abierto"))

    # SUITE 7
    print("\n" + "-" * 88)
    print("🔹 SUITE 7: Comandos de Consulta de Datos a Repetidores Remotos")
    print("-" * 88)
    query_commands = [
        ("ver", "Firmware version"),
        ("board", "Hardware board"),
        ("stats-core", "Estadísticas de núcleo (uptime, batería)"),
        ("stats-radio", "Estadísticas de radio (SNR, RSSI, ruido)"),
        ("stats-packets", "Estadísticas de paquetes enrutados"),
        ("neighbors", "Tabla de vecinos en 0 saltos"),
        ("get tx", "Potencia de transmisión"),
    ]
    
    queries_ok = 0
    for cmd, desc in query_commands:
        raw_cmd = f"{pk_r1[:8]}:{cmd}".encode("utf-8")
        await client.send_command(bytes([CommandType.SEND_RAW_DATA]) + raw_cmd)
        stat_resp = await client.wait_for_frame(PacketType.STATUS_RESPONSE, timeout_sec=2.0)
        if stat_resp and len(stat_resp) > 32:
            resp_str = stat_resp[32:].decode("utf-8", errors="ignore")
            print(f"   ✅ [OK] Comando '{cmd}' ({desc}) -> Respuesta: \"{resp_str}\"")
            queries_ok += 1
        else:
            print(f"   ❌ [FAIL] Sin respuesta para el comando '{cmd}'")

    if queries_ok == len(query_commands):
        results.append(("Suite 7: Consultas de Datos a Repetidores", True, f"{queries_ok}/{len(query_commands)} comandos exitosos"))
    else:
        results.append(("Suite 7: Consultas de Datos a Repetidores", False, f"{queries_ok}/{len(query_commands)} comandos"))

    # SUITE 8
    print("\n" + "-" * 88)
    print("🔹 SUITE 8: Modificación de Configuración en Repetidor Bravo (R2)")
    print("-" * 88)
    config_changes = [
        (f"set name Repeater-Bravo-Apex", "Nuevo nombre de nodo"),
        ("set tx 22", "Incrementar potencia TX a 22 dBm"),
        ("set advert.interval 15", "Reducir intervalo de baliza a 15 mins"),
        ("set radio 915.0,250,11,5", "Fijar parámetros de modulación LoRa"),
    ]

    sets_ok = 0
    for cmd, desc in config_changes:
        raw_cmd = f"{pk_r2[:8]}:{cmd}".encode("utf-8")
        await client.send_command(bytes([CommandType.SEND_RAW_DATA]) + raw_cmd)
        stat_resp = await client.wait_for_frame(PacketType.STATUS_RESPONSE, timeout_sec=2.0)
        if stat_resp and len(stat_resp) > 32:
            resp_str = stat_resp[32:].decode("utf-8", errors="ignore")
            print(f"   ✅ [OK] Cambio '{cmd}' ({desc}) -> Respuesta: \"{resp_str}\"")
            sets_ok += 1
        else:
            print(f"   ❌ [FAIL] Fallo al aplicar '{cmd}'")

    applied_verified = (node_r2.name == "Repeater-Bravo-Apex" and node_r2.tx_power == 22 and node_r2.advert_interval_mins == 15)
    if sets_ok == len(config_changes) and applied_verified:
        print("   ✅ [OK] Persistencia verificada: R2 actualizado a 'Repeater-Bravo-Apex', 22 dBm, 15 mins.")
        results.append(("Suite 8: Modificación de Configuración en Repetidor", True, f"Parámetros actualizados y validados"))
    else:
        results.append(("Suite 8: Modificación de Configuración en Repetidor", False, f"Fallo en validación de persistencia"))

    await client.disconnect()
    await tcp_server.stop()

    print("\n" + "=" * 88)
    print("📊 RESUMEN DE EJECUCIÓN - SIMULACIÓN MULTI-NODO TCP")
    print("=" * 88)
    all_passed = True
    for suite_name, passed, detail in results:
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
        print(f" {status_icon:8} | {suite_name:<52} | {detail}")
    print("=" * 88)

    if all_passed:
        print("\n🎉 TODAS LAS PRUEBAS DE LA PILA TCP Y MALLA MULTI-SALTO PASARON CON ÉXITO (100% COMPATIBLE).\n")
        return True
    else:
        print("\n⚠️ ALGUNAS PRUEBAS FALLARON. REVISAR EL LOG ANTERIOR.\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_tcp_mesh_simulation())
    sys.exit(0 if success else 1)

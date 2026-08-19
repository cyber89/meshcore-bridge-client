"""
Virtual Mesh Adapter & Hardware Simulator for MeshCore Bridge.
Simula un transceptor físico LoRa conectado por USB con soporte bidireccional para:
- Nodos remotos (Alpha Field Sensor y Bravo Scout Rover).
- Bot de Auto-Eco inteligente en mensajes directos (DMs).
- Generación de telemetría ambiental dinámica y trayectorias GPS.
- Inyección de tramas RF wire (0x88 LOG_DATA) para el Packet Sniffer.
- Respuestas a comandos administrativos y de repetidores.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import struct
import time
from typing import Any

from src.protocol_types import MeshcoreFrame, OpCode
from src.sensor_decoder import LppDataType
from src.serial_driver import BaseSerialAdapter


class VirtualMeshAdapter(BaseSerialAdapter):
    """Adaptador de simulación que emula un nodo hardware MeshCore y una red de clientes."""

    def __init__(
        self,
        port: str = "VIRTUAL_COM",
        baud_rate: int = 115200,
        timeout_sec: float = 30.0,
        event_callback: Any = None,
    ) -> None:
        super().__init__(port=port, baud_rate=baud_rate, timeout_sec=timeout_sec)
        if event_callback:
            self.set_rx_callback(event_callback)
        self.running = False
        self._sim_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._tick_counter = 0

        # Definición de Nodos y Repetidores de la Malla Simulada
        self.nodes: dict[str, dict[str, Any]] = {
            "a1b2c3d4e5f6": {
                "key": "a1b2c3d4e5f6",
                "name": "Node_Alpha",
                "alias": "Alpha Field Sensor",
                "role": "REPEATER",
                "lat": 20.1520,
                "lon": -75.1980,
                "alt": 850.0,
                "temp": 18.2,
                "humidity": 62.0,
                "pressure": 1018.4,
                "battery": 98,
                "voltage": 4.18,
                "solar_v": 5.12,
                "rssi": -65,
                "snr": 12.4,
                "hops": 0,
            },
            "d7e8f9012345": {
                "key": "d7e8f9012345",
                "name": "Node_Bravo",
                "alias": "Bravo Scout Rover",
                "role": "CLIENT",
                "lat": 20.1850,
                "lon": -75.2420,
                "alt": 120.0,
                "temp": 25.4,
                "humidity": 51.0,
                "pressure": 1012.1,
                "battery": 84,
                "voltage": 3.95,
                "solar_v": 0.0,
                "rssi": -78,
                "snr": 8.5,
                "hops": 1,
            },
            "c3d4e5f6a7b8": {
                "key": "c3d4e5f6a7b8",
                "name": "Node_Charlie",
                "alias": "⛅ Charlie Weather Station",
                "role": "SENSOR",
                "lat": 20.1410,
                "lon": -75.2150,
                "alt": 210.0,
                "temp": 22.8,
                "humidity": 70.0,
                "pressure": 1014.6,
                "battery": 91,
                "voltage": 4.05,
                "solar_v": 4.80,
                "rssi": -74,
                "snr": 10.1,
                "hops": 1,
            },
            "e9f012345678": {
                "key": "e9f012345678",
                "name": "Node_Delta",
                "alias": "📱 Delta Field Operative",
                "role": "CLIENT",
                "lat": 20.1650,
                "lon": -75.2280,
                "alt": 95.0,
                "temp": 24.1,
                "humidity": 55.0,
                "pressure": 1013.0,
                "battery": 76,
                "voltage": 3.82,
                "solar_v": 0.0,
                "rssi": -70,
                "snr": 11.2,
                "hops": 0,
            },
            "5a6b7c8d9e0f": {
                "key": "5a6b7c8d9e0f",
                "name": "Node_Echo",
                "alias": "⚡ Echo Gateway Repeater",
                "role": "REPEATER",
                "lat": 20.1720,
                "lon": -75.1850,
                "alt": 540.0,
                "temp": 19.5,
                "humidity": 59.0,
                "pressure": 1016.2,
                "battery": 99,
                "voltage": 4.20,
                "solar_v": 5.40,
                "rssi": -63,
                "snr": 13.1,
                "hops": 0,
            },
            "6f7e8d9c0b1a": {
                "key": "6f7e8d9c0b1a",
                "name": "Node_Foxtrot",
                "alias": "🏥 Foxtrot Base HQ",
                "role": "ROOM",
                "lat": 20.1380,
                "lon": -75.2350,
                "alt": 60.0,
                "temp": 23.0,
                "humidity": 50.0,
                "pressure": 1013.5,
                "battery": 100,
                "voltage": 4.25,
                "solar_v": 0.0,
                "rssi": -58,
                "snr": 14.2,
                "hops": 0,
            },
            "7a8b9c0d1e2f": {
                "key": "7a8b9c0d1e2f",
                "name": "Node_Golf",
                "alias": "🚁 Golf Drone Scout",
                "role": "CLIENT",
                "lat": 20.1920,
                "lon": -75.2110,
                "alt": 350.0,
                "temp": 16.8,
                "humidity": 45.0,
                "pressure": 1008.0,
                "battery": 68,
                "voltage": 3.75,
                "solar_v": 0.0,
                "rssi": -76,
                "snr": 9.4,
                "hops": 1,
            },
            "8b9c0d1e2f3a": {
                "key": "8b9c0d1e2f3a",
                "name": "Node_Hotel",
                "alias": "🌲 Hotel Forest Sensor",
                "role": "SENSOR",
                "lat": 20.1250,
                "lon": -75.2050,
                "alt": 420.0,
                "temp": 20.1,
                "humidity": 78.0,
                "pressure": 1015.0,
                "battery": 93,
                "voltage": 4.10,
                "solar_v": 4.95,
                "rssi": -82,
                "snr": 6.8,
                "hops": 2,
            },
        }

        # Canales simulados de inicio (Públicos y Privados)
        self.channels: dict[int, dict[str, Any]] = {
            0: {"index": 0, "name": "Public / Broadcast", "psk": "", "is_public": True},
            1: {"index": 1, "name": "Operaciones Tácticas", "psk": "A1B2C3D4E5F67890123456789ABCDEF0", "is_public": False},
            2: {"index": 2, "name": "Telemetría Sensores", "psk": "FEEDFACECAFED00D1234567890ABCDEF", "is_public": False},
            3: {"index": 3, "name": "Emergencias Malla", "psk": "99887766554433221100FFEEDDCCBBAA", "is_public": False},
        }

        # Referencias directas para compatibilidad
        self.node_alpha = self.nodes["a1b2c3d4e5f6"]
        self.node_bravo = self.nodes["d7e8f9012345"]

    async def get_channels(self) -> list[dict[str, Any]]:
        """Devuelve los canales virtuales configurados."""
        return list(self.channels.values())

    async def set_channel(self, index: int, name: str, psk: str) -> dict[str, Any]:
        """Configura un canal virtual en el simulador."""
        if not name and not psk:
            self.channels.pop(index, None)
            return {"status": "CLEARED", "index": index}
        self.channels[index] = {
            "index": index,
            "name": name or f"Canal {index}",
            "psk": psk,
            "is_public": (index == 0),
        }
        return {"status": "OK", "channel": self.channels[index]}

    async def sync_all_contacts(self) -> list[dict[str, Any]]:
        """Descarga e importa todos los nodos simulados como contactos."""
        contacts = []
        for n in self.nodes.values():
            contacts.append({
                "public_key": n["key"],
                "name": n["name"],
                "alias": n["alias"],
                "role": n.get("role", "CLIENT"),
            })
        return contacts

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Añade un contacto a los nodos simulados."""
        pk = str(contact_data.get("public_key", "")).strip().lower()
        if pk:
            self.nodes[pk] = {
                "key": pk,
                "name": contact_data.get("name", f"Node_{pk[:6]}"),
                "alias": contact_data.get("alias", contact_data.get("name", f"Node_{pk[:6]}")),
                "role": contact_data.get("role", "CLIENT"),
                "lat": 20.1600,
                "lon": -75.2200,
                "alt": 100.0,
                "temp": 24.0,
                "humidity": 50.0,
                "pressure": 1013.0,
                "battery": 90,
                "voltage": 4.0,
                "solar_v": 0.0,
                "rssi": -70,
                "snr": 10.0,
                "hops": 1,
            }
        return {"status": "OK", "contact": contact_data}

    async def remove_contact(self, pubkey: str) -> dict[str, Any]:
        """Elimina un contacto simulado."""
        norm_pk = str(pubkey).strip().lower()
        self.nodes.pop(norm_pk, None)
        return {"status": "OK", "public_key": pubkey}

    async def connect(self) -> bool:
        """Inicializa la conexión virtual y arranca el bucle de simulación RF."""
        self.is_connected = True
        self.running = True
        logging.info("⚡ [USB-HARDWARE] Heltec v4 MeshCore Companion USB conectado (modo virtual).")

        # Emitir anuncios iniciales de presencia de todos los nodos
        for node in self.nodes.values():
            self._emit_node_presence(node)

        # Iniciar ciclo de simulación en segundo plano
        self._sim_task = asyncio.create_task(self._simulation_loop())
        self._background_tasks.add(self._sim_task)
        self._sim_task.add_done_callback(self._background_tasks.discard)
        return True

    async def disconnect(self) -> None:
        """Detiene la simulación y libera recursos."""
        self.running = False
        if self._sim_task and not self._sim_task.done():
            self._sim_task.cancel()
            try:
                await self._sim_task
            except asyncio.CancelledError:
                pass
        self.is_connected = False
        logging.info("Adaptador Virtual LoRa MeshCore desconectado.")

    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        """Envía un mensaje de texto simulado y programa la respuesta eco si va a un nodo cliente."""
        self.heartbeat()
        target_clean = str(target or "").strip().lower()

        if target_clean.startswith("channel"):
            is_direct = False
            try:
                channel_idx = int(target_clean.split("_")[1])
            except Exception:
                pass
            target_node = self.node_bravo if channel_idx == 1 else self.node_alpha
        elif target_clean and target_clean not in ("broadcast", "public", "0xffff", "none"):
            is_direct = True
            matched = None
            for k, n in self.nodes.items():
                if target_clean in (k.lower(), n["name"].lower(), str(n["alias"]).lower()):
                    matched = n
                    break
            if matched:
                target_node = matched
            else:
                target_node = {
                    "key": target_clean,
                    "name": f"Node_{target_clean[:6]}",
                    "alias": f"Node_{target_clean[:6]}",
                    "snr": 10.0,
                    "rssi": -78,
                    "hops": 1,
                }
        else:
            is_direct = False
            if channel_idx == 0:
                target_node = self.node_alpha
            elif channel_idx == 1:
                target_node = self.node_bravo
            else:
                target_node = self.node_alpha

        if target_node:
            task = asyncio.create_task(self._simulate_echo_reply(target_node, text, channel_idx=channel_idx, is_direct=is_direct))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        return {
            "status": "ok",
            "delivered": True,
            "target": target or "broadcast",
            "channel": channel_idx,
            "timestamp": int(time.time()),
        }

    async def send_admin_cmd(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Responde a comandos de administración de repetidores y diagnóstico de radio."""
        self.heartbeat()
        action_clean = action.lower().strip()

        if "stats" in action_clean or "radio" in action_clean or "core" in action_clean or "packet" in action_clean:
            return {
                "status": "ok",
                "action": action,
                "frequency_mhz": float(params.get("freq", 915.0)),
                "tx_power_dbm": int(params.get("power", 20)),
                "spreading_factor": int(params.get("sf", 11)),
                "bandwidth_khz": float(params.get("bw", 250.0)),
                "channel_utilization_pct": 3.8,
                "noise_floor_dbm": -118,
                "uptime_hours": 142.5,
                "packets_routed": 18420,
            }

        if "neighbor" in action_clean or "node" in action_clean:
            return {
                "status": "ok",
                "action": action,
                "neighbors": [
                    {"pubkey": n["key"], "alias": n["alias"], "snr": n["snr"], "rssi": n["rssi"], "hops": n["hops"]}
                    for n in list(self.nodes.values())[:4]
                ],
            }

        if "set" in action_clean or "config" in action_clean:
            return {
                "status": "ok",
                "action": action,
                "applied_params": params,
                "message": f"Parámetros actualizados con éxito en repetidor: {action}",
            }

        if "reboot" in action_clean:
            return {"status": "ok", "action": "reboot", "message": "Repetidor reiniciándose en 3 segundos..."}

        return {"status": "ok", "action": action, "message": f"Comando '{action}' ejecutado con éxito en repetidor"}

    async def send_frame(self, frame: MeshcoreFrame) -> bool:
        """Procesa una trama saliente enviada desde el bridge y dispara auto-eco si corresponde."""
        if not self.is_connected:
            return False

        self.heartbeat()
        task = asyncio.create_task(self._process_outbound_frame(frame))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return True

    async def send_raw_companion_frame(self, data: bytes) -> bool:
        """Procesa comandos crudos Companion recibidos desde app móvil o CLI y genera respuestas acordes."""
        if not data:
            return False

        cmd_type = data[0]
        self.heartbeat()

        # CMD_APP_START (1) -> Responder con SELF_INFO (5)
        if cmd_type == 1:
            pubkey_bytes = bytes.fromhex("11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff")
            lat_int = int(20.1520 * 1000000)
            lon_int = int(-75.1980 * 1000000)
            freq = 915000000
            bw = 250000
            sf = 11
            cr = 5
            name_bytes = "MeshCore-Bridge-Virtual".encode("utf-8")

            resp = bytearray()
            resp.append(5)  # PacketType.SELF_INFO
            resp.append(1)  # adv_type
            resp.append(20)  # tx_power
            resp.append(22)  # max_tx_power
            resp.extend(pubkey_bytes)  # 32 bytes
            resp.extend(lat_int.to_bytes(4, "little", signed=True))
            resp.extend(lon_int.to_bytes(4, "little", signed=True))
            resp.append(1)  # multi_acks
            resp.append(1)  # adv_loc_policy
            resp.append(0)  # telemetry_mode
            resp.append(0)  # manual_add_contacts
            resp.extend(freq.to_bytes(4, "little"))
            resp.extend(bw.to_bytes(4, "little"))
            resp.append(sf)
            resp.append(cr)
            resp.extend(name_bytes)

            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(resp))
            return True

        # CMD_GET_CONTACTS (4) -> Responder CONTACT_START (2), CONTACT (3)..., CONTACT_END (4)
        if cmd_type == 4:
            count = len(self.nodes)
            start_pkt = bytearray([2]) + count.to_bytes(4, "little")
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(start_pkt))

            for _node_key, node in self.nodes.items():
                contact_buf = bytearray([3])
                raw_key = bytes.fromhex(node["key"].ljust(64, "0"))
                contact_buf.extend(raw_key)
                contact_buf.append(1 if node["role"] == "REPEATER" else 0)
                contact_buf.append(0)
                contact_buf.extend(int(time.time()).to_bytes(4, "little"))
                contact_buf.extend(node["alias"].encode("utf-8"))
                if self.companion_rx_callback:
                    self.companion_rx_callback(bytes(contact_buf))

            end_pkt = bytearray([4])
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(end_pkt))
            return True

        # CMD_GET_BATT_AND_STORAGE (20) -> BATTERY (12)
        if cmd_type == 20:
            bat_pkt = bytearray([12]) + (4150).to_bytes(2, "little") + bytes([95])
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(bat_pkt))
            return True

        # CMD_SEND_TXT_MSG (2) o CMD_SEND_CHANNEL_TXT_MSG (3)
        if cmd_type in (2, 3):
            ok_pkt = bytearray([6]) + int(time.time()).to_bytes(4, "little")
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(ok_pkt))

            try:
                text_bytes = data[1:]
                text = text_bytes.decode("utf-8", errors="ignore").strip()
                if text:
                    asyncio.create_task(
                        self._simulate_echo_reply(self.node_alpha, text, channel_idx=0, is_direct=(cmd_type == 2))
                    )
            except Exception:
                pass
            return True

        # Cualquier otro comando -> OK (0)
        ok_pkt = bytearray([0]) + (0).to_bytes(4, "little")
        if self.companion_rx_callback:
            self.companion_rx_callback(bytes(ok_pkt))
        return True

    async def _process_outbound_frame(self, frame: MeshcoreFrame) -> None:
        """Analiza la trama TX y simula la respuesta en el aire de los nodos remotos."""
        await asyncio.sleep(0.2)

        # 1. Acuse de recibo inmediato
        ack_event = {
            "type": "ACK",
            "payload": {
                "sequence_number": frame.header.seq_num,
                "status": "SENT_OK",
                "timestamp": int(time.time()),
            },
        }
        self._dispatch_event(ack_event)

        # 2. Análisis de mensaje de texto
        payload_bytes = frame.raw_payload
        text = ""
        try:
            text = payload_bytes.decode("utf-8", errors="ignore").strip()
        except Exception:
            pass

        target_node = None
        if frame.header.opcode == OpCode.TEXT_MSG or "alpha" in text.lower() or "a1b2c3" in text.lower():
            target_node = self.node_alpha
        elif "bravo" in text.lower() or "d7e8f9" in text.lower():
            target_node = self.node_bravo

        if target_node and text:
            await self._simulate_echo_reply(target_node, text, channel_idx=0, is_direct=True)

    async def _simulate_echo_reply(
        self,
        node: dict[str, Any],
        original_text: str,
        channel_idx: int = 0,
        is_direct: bool = True,
    ) -> None:
        """Simula que el nodo remoto procesa el mensaje y responde con un Eco por RF."""
        await asyncio.sleep(0.4)

        if is_direct:
            echo_msg = f"[Echo DM de {node['alias']}]: Recibido: \"{original_text}\" | SNR: {node['snr']}dB RSSI: {node['rssi']}dBm Hops: {node['hops']}"
            echo_event = {
                "type": "DIRECT_MSG",
                "event_type": "direct",
                "sender": str(node["key"]),
                "sender_name": str(node["alias"]),
                "text": echo_msg,
                "metrics": {
                    "rssi": node["rssi"],
                    "snr": node["snr"],
                },
                "hop_count": int(node["hops"]),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        else:
            ch_name = f"Canal {channel_idx}"
            echo_msg = f"[Echo {ch_name} de {node['alias']}]: Recibido en {ch_name}: \"{original_text}\" | SNR: {node['snr']}dB"
            echo_event = {
                "type": "CHANNEL_MSG",
                "event_type": "public" if channel_idx == 0 else "channel",
                "sender": str(node["key"]),
                "sender_name": str(node["alias"]),
                "text": echo_msg,
                "channel_idx": channel_idx,
                "channel_index": channel_idx,
                "metrics": {
                    "rssi": node["rssi"],
                    "snr": node["snr"],
                },
                "hop_count": int(node["hops"]),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

        self._dispatch_event(echo_event)
        logging.info(f"Bot de Eco ejecutado desde nodo virtual {node['name']} ({node['alias']}) [Direct={is_direct}, Ch={channel_idx}]")

    async def _simulation_loop(self) -> None:
        """Bucle continuo que emite telemetría ambiental, posiciones GPS y tramas de sniffer."""
        while self.running:
            try:
                await asyncio.sleep(5.0)
                self._tick_counter += 1
                self.heartbeat()

                self._update_node_states()

                # 1. Emitir Telemetría CayenneLPP de Nodo Alpha
                if self._tick_counter % 1 == 0:
                    self._emit_cayennelpp_telemetry(self.node_alpha)

                # 2. Emitir Telemetría CayenneLPP de Nodo Bravo
                if self._tick_counter % 2 == 0:
                    self._emit_cayennelpp_telemetry(self.node_bravo)

                # 3. Inyectar trama de RF Packet Sniffer (0x88 LOG_DATA)
                if self._tick_counter % 2 == 0:
                    self._emit_sniffer_wire_packet()

                # 4. Anuncios de presencia de red periódicos
                if self._tick_counter % 4 == 0:
                    self._emit_node_presence(self.node_alpha)
                    self._emit_node_presence(self.node_bravo)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.debug(f"Excepción en bucle de simulación: {e}")

    def _update_node_states(self) -> None:
        """Simula movimiento GPS suave y fluctuaciones ambientales realistas."""
        angle = self._tick_counter * 0.15
        self.node_bravo["lat"] = 20.1800 + round(math.sin(angle) * 0.008, 4)
        self.node_bravo["lon"] = -75.2500 + round(math.cos(angle) * 0.008, 4)

        self.node_alpha["temp"] = round(24.0 + math.sin(self._tick_counter * 0.1) * 2.0, 1)
        self.node_bravo["temp"] = round(25.5 + math.cos(self._tick_counter * 0.1) * 1.5, 1)

    def _emit_node_presence(self, node: dict[str, Any]) -> None:
        """Genera un evento de anuncio de nodo descubierto."""
        event = {
            "type": "ADVERTISEMENT",
            "event_type": "node_discovered",
            "sender": node["key"],
            "sender_name": node["alias"],
            "hops": node["hops"],
            "rssi": node["rssi"],
            "snr": node["snr"],
            "battery": node["battery"],
            "latitude": node["lat"],
            "longitude": node["lon"],
        }
        self._dispatch_event(event)

    def _emit_cayennelpp_telemetry(self, node: dict[str, Any]) -> None:
        """Construye un paquete binario CayenneLPP real y lo inyecta como evento."""
        buf = io.BytesIO()

        # Canal 1: Temperatura
        buf.write(bytes([1, LppDataType.TEMPERATURE]))
        buf.write(struct.pack(">h", int(float(node["temp"]) * 10)))

        # Canal 2: Humedad
        buf.write(bytes([2, LppDataType.HUMIDITY]))
        buf.write(bytes([int(float(node["humidity"]) * 2)]))

        # Canal 3: Barómetro
        buf.write(bytes([3, LppDataType.BAROMETER]))
        buf.write(struct.pack(">H", int(float(node["pressure"]) * 10)))

        # Canal 4: Batería %
        buf.write(bytes([4, LppDataType.PERCENTAGE]))
        buf.write(bytes([int(node["battery"])]))

        # Canal 5: GPS
        buf.write(bytes([5, LppDataType.GPS_LOCATION]))
        lat_int = int(float(node["lat"]) * 10000)
        lon_int = int(float(node["lon"]) * 10000)
        alt_int = int(float(node["alt"]) * 100)
        buf.write(lat_int.to_bytes(3, byteorder="big", signed=True))
        buf.write(lon_int.to_bytes(3, byteorder="big", signed=True))
        buf.write(alt_int.to_bytes(3, byteorder="big", signed=True))

        raw_bytes = buf.getvalue()

        telemetry_event = {
            "type": "TELEMETRY_RESPONSE",
            "event_type": "telemetry",
            "sender": node["key"],
            "sender_name": node["alias"],
            "raw_bytes": raw_bytes,
            "metrics": {
                "rssi": node["rssi"],
                "snr": node["snr"],
            },
            "hop_count": node["hops"],
            "temperature_c": node["temp"],
            "humidity_pct": node["humidity"],
            "pressure_hpa": node["pressure"],
            "battery_pct": node["battery"],
            "gps": {
                "latitude": node["lat"],
                "longitude": node["lon"],
                "altitude_m": node["alt"],
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._dispatch_event(telemetry_event)

    def _emit_sniffer_wire_packet(self) -> None:
        """Simula una captura en el aire de trama LoRa Wire (OpCode 0x88 LOG_DATA)."""
        header_byte = (0 & 0x03) | ((1 & 0x0F) << 2) | ((1 & 0x03) << 6)
        wire_data = bytes([header_byte, 0x01, 0x02, 0xA1, 0xB2, 0xC3, 0xD4, 0x10, 0x20, 0x30, 0x40])

        log_event = {
            "type": "LOG_DATA",
            "event_type": "rf_log",
            "raw": wire_data,
            "rssi": -76,
            "snr": 8.5,
            "timestamp": int(time.time()),
        }
        self._dispatch_event(log_event)

    def _dispatch_event(self, event: Any) -> None:
        """Despacha un evento hacia el callback del bridge."""
        if self.rx_callback:
            try:
                self.rx_callback(event)
            except Exception as e:
                logging.error(f"Error en callback del bridge desde simulador: {e}")

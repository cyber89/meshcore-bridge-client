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
import hashlib
import io
import logging
import math
import struct
import time
from typing import Any

from src.sensor_decoder import LppDataType
from src.serial_driver import BaseSerialAdapter
from src.shared_utils import classify_device_role


class VirtualMeshCoreCommands:
    """Implementa comandos mock compatibles con MeshCore SDK para simulación."""

    def __init__(self, adapter: VirtualMeshAdapter) -> None:
        self._adapter = adapter

    async def send_appstart(self) -> dict[str, Any]:
        return {"status": "ok", "self_info": self._adapter.mc.self_info}

    async def send_device_query(self) -> Any:
        class MockEvent:
            type = "DEVICE_INFO"
            payload = {
                "model": "MeshCore Virtual Transceiver",
                "ver": "v1.6.0-sim",
                "fw ver": 3,
                "fw_build": "2026-08-25",
                "repeat": True,
            }
        return MockEvent()

    async def get_bat(self) -> dict[str, Any]:
        return {
            "battery_pct": self._adapter.mc.self_info.get("battery_pct", 100),
            "battery_mv": self._adapter.mc.self_info.get("battery_mv", 5000),
            "voltage": self._adapter.mc.self_info.get("voltage", 5.0),
        }

    async def get_time(self) -> dict[str, Any]:
        ts = self._adapter.device_time()
        return {
            "time": ts,
            "timestamp": ts,
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)),
        }

    async def set_time(self, val: int) -> dict[str, Any]:
        if isinstance(val, bool) or not isinstance(val, int) or not 0 <= val <= 0xffffffff:
            return {"status": "ERROR", "reason": "RTC requiere entero uint32"}
        self._adapter._rtc_epoch = val
        self._adapter._rtc_monotonic = time.monotonic()
        return {"status": "ok", "time": val}

    async def set_name(self, name: str) -> dict[str, Any]:
        self._adapter.mc.self_info["name"] = name
        self._adapter.mc.self_info["adv_name"] = name
        return {"status": "ok", "name": name}

    async def set_coords(self, lat: float, lon: float) -> dict[str, Any]:
        self._adapter.mc.self_info["latitude"] = lat
        self._adapter.mc.self_info["longitude"] = lon
        self._adapter.mc.self_info["adv_lat"] = lat
        self._adapter.mc.self_info["adv_lon"] = lon
        return {"status": "ok", "lat": lat, "lon": lon}

    async def set_tx_power(self, val: int) -> dict[str, Any]:
        self._adapter.mc.self_info["tx_power"] = val
        return {"status": "ok", "tx_power": val}

    async def set_radio(self, freq: float, bw: float, sf: int, cr: int, repeat: Any = None) -> dict[str, Any]:
        self._adapter.mc.self_info.update({
            "frequency": freq,
            "radio_freq": freq,
            "bandwidth": bw,
            "bw": bw,
            "spreading_factor": sf,
            "sf": sf,
            "coding_rate": f"4/{cr}" if cr in (5, 6, 7, 8) else str(cr),
            "cr": cr,
            "repeat": bool(repeat) if repeat is not None else True,
        })
        return {"status": "ok"}

    async def send_advert(self, flood: bool = False) -> dict[str, Any]:
        return {"status": "ok", "flood": flood}

    async def reboot(self) -> dict[str, Any]:
        return {"status": "ok"}

    async def get_stats_core(self) -> dict[str, Any]:
        uptime_val = max(0, int(time.time() - self._adapter._start_time))
        return {
            "uptime": uptime_val,
            "uptime_secs": uptime_val,
            "airtime_ms": 120,
            "battery_mv": self._adapter.mc.self_info["battery_mv"],
            "errors": 0,
            "queue_len": 0,
        }

    async def get_stats_radio(self) -> dict[str, Any]:
        return {
            "last_snr": 12.0,
            "last_rssi": -72,
            "noise_floor": -118,
            "noise_floor_dbm": -118,
            "tx_air_secs": 2,
            "rx_air_secs": 5,
        }

    async def get_stats_packets(self) -> dict[str, Any]:
        return {
            "sent": 15,
            "recv": 24,
            "flood_tx": 10,
            "direct_tx": 5,
            "flood_rx": 18,
            "direct_rx": 6,
            "recv_errors": 0,
        }

    async def req_status_sync(self, contact: Any, timeout: float = 0, min_timeout: float = 0) -> dict[str, Any]:
        uptime_val = max(1, int(time.time() - getattr(self._adapter, "_start_time", time.time())))
        return {
            "bat": 3630,
            "tx_queue_len": 0,
            "noise_floor": -118,
            "last_rssi": -35,
            "nb_recv": 24,
            "nb_sent": 15,
            "airtime": 12,
            "uptime": uptime_val,
            "sent_flood": 10,
            "sent_direct": 5,
            "recv_flood": 18,
            "recv_direct": 6,
            "full_evts": 0,
            "last_snr": 12.0,
            "direct_dups": 0,
            "flood_dups": 0,
            "rx_airtime": 25,
            "recv_errors": 0,
        }

    async def req_telemetry_sync(self, contact: Any, timeout: float = 0, min_timeout: float = 0) -> list[dict[str, Any]]:
        return [
            {"channel": 0, "type": "voltage", "val": 3.63},
            {"channel": 0, "type": "temperature", "val": 25.2},
        ]

    async def set_custom_var(self, key: str, val: str) -> dict[str, Any]:
        self._adapter.mc.self_info[key] = val
        return {"status": "ok"}

    async def get_channels(self) -> list[dict[str, Any]]:
        return [
            {"index": 0, "name": "Public / Broadcast", "psk": "", "is_public": True},
        ]


class VirtualMeshCoreMock:
    """Mock de MeshCore SDK para VirtualMeshAdapter."""

    def __init__(self, adapter: VirtualMeshAdapter) -> None:
        self.self_info: dict[str, Any] = {
            "name": "MeshCore_Base_Station",
            "public_key": "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff",
            "role": "Base Station",
            "owner_info": "Operador Estación Base / TG-0",
            "latitude": 20.1500,
            "longitude": -75.2000,
            "adv_lat": 20.1500,
            "adv_lon": -75.2000,
            "altitude": 50,
            "tx_power": 20,
            "frequency": 915.0,
            "radio_freq": 915.0,
            "spreading_factor": 11,
            "sf": 11,
            "bandwidth": 250,
            "bw": 250,
            "coding_rate": "4/5",
            "cr": 5,
            "repeat": True,
            "battery_pct": 100,
            "battery_mv": 5000,
            "voltage": 5.0,
            "power_source": "USB 5V Directo",
            "model": "MeshCore Virtual Transceiver",
            "ver": "v1.6.0-sim",
            "fw_build": "2026-08-25",
        }
        self.commands = VirtualMeshCoreCommands(adapter)


# Definición canónica de Nodos y Repetidores de la Malla Simulada
DEFAULT_VIRTUAL_NODES: dict[str, dict[str, Any]] = {
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
    "aabbccddeeff": {
        "key": "aabbccddeeff",
        "name": "Node_Ridge",
        "alias": "⛰️ R3-Ridge Solar Repeater",
        "role": "REPEATER",
        "lat": 20.1880,
        "lon": -75.1740,
        "alt": 980.0,
        "temp": 17.5,
        "humidity": 58.0,
        "pressure": 1015.5,
        "battery": 97,
        "voltage": 4.16,
        "solar_v": 5.30,
        "rssi": -68,
        "snr": 12.0,
        "hops": 1,
    },
    "334455667788": {
        "key": "334455667788",
        "name": "Node_Emergency",
        "alias": "🚨 Emergency Bulletin Mailbox",
        "role": "ROOM",
        "lat": 20.1450,
        "lon": -75.2050,
        "alt": 110.0,
        "temp": 22.5,
        "humidity": 54.0,
        "pressure": 1013.8,
        "battery": 100,
        "voltage": 5.00,
        "solar_v": 0.0,
        "rssi": -60,
        "snr": 13.5,
        "hops": 0,
    },
}

# Canales simulados de inicio (Públicos y Privados)
DEFAULT_VIRTUAL_CHANNELS: dict[int, dict[str, Any]] = {
    0: {"index": 0, "name": "Public / Broadcast", "psk": "", "is_public": True},
    1: {"index": 1, "name": "Operaciones Tácticas", "psk": "A1B2C3D4E5F67890123456789ABCDEF0", "is_public": False},
    2: {"index": 2, "name": "Telemetría Sensores", "psk": "FEEDFACECAFED00D1234567890ABCDEF", "is_public": False},
    3: {"index": 3, "name": "Emergencias Malla", "psk": "99887766554433221100FFEEDDCCBBAA", "is_public": False},
}


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
        self._start_time = time.time()
        self._rtc_epoch = int(time.time())
        self._rtc_monotonic = time.monotonic()
        self.mc = VirtualMeshCoreMock(self)
        self._sim_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._tick_counter = 0

        # Inicialización de Nodos y Repetidores simulados a partir de plantillas canónicas
        self.nodes: dict[str, dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_VIRTUAL_NODES.items()}
        self.channels: dict[int, dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_VIRTUAL_CHANNELS.items()}

        # Referencias directas para compatibilidad
        self.node_alpha = self.nodes["a1b2c3d4e5f6"]
        self.node_bravo = self.nodes["d7e8f9012345"]

    def device_time(self) -> int:
        """RTC propio de la estación virtual; no modifica el reloj del host."""
        return (self._rtc_epoch + int(time.monotonic() - self._rtc_monotonic)) & 0xffffffff

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

    async def delete_channel(self, index: int) -> dict[str, Any]:
        """Elimina un canal virtual en el simulador."""
        self.channels.pop(index, None)
        return {"status": "DELETED", "index": index}

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
            name = str(contact_data.get("name") or contact_data.get("adv_name") or f"Node_{pk[:6]}")
            role = contact_data.get("role")
            if not role:
                adv_type = contact_data.get("type", contact_data.get("adv_type"))
                if adv_type is not None:
                    try:
                        role = classify_device_role(int(adv_type), False)
                    except (ValueError, TypeError):
                        role = "CLIENT"
                else:
                    role = "CLIENT"
            self.nodes[pk] = {
                "key": pk,
                "name": name,
                "alias": contact_data.get("alias", name),
                "role": role,
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
        if self.is_connected and self._sim_task and not self._sim_task.done():
            return True
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
        self.is_connected = False
        tasks = set(self._background_tasks)
        if self._sim_task:
            tasks.add(self._sim_task)
        tasks.discard(asyncio.current_task())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        self._sim_task = None
        logging.info("Adaptador Virtual LoRa MeshCore desconectado.")

    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        """Envía un mensaje de texto simulado y programa la respuesta eco si va a un nodo cliente."""
        if not self.is_connected:
            return {"status": "ERROR", "reason": "Simulador desconectado"}
        self.heartbeat()

        # Validación MTU LoRa oficial y capacidad de canal (VRT-M01)
        raw_bytes = text.encode("utf-8")
        if len(raw_bytes) > 160:
            return {
                "status": "ERROR",
                "reason": f"Payload de mensaje excede límite oficial ({len(raw_bytes)} > 160 bytes)",
            }
        target_clean = str(target or "").strip().lower()
        resolved_channel: Any = channel_idx
        if target_clean.startswith("channel"):
            suffix = target_clean[8:]
            if not target_clean.startswith("channel_") or not suffix.isascii() or not suffix.isdigit():
                return {"status": "ERROR", "reason": "Alias de canal inválido"}
            try:
                resolved_channel = int(suffix)
            except ValueError:
                return {"status": "ERROR", "reason": "Alias de canal inválido"}
        if isinstance(resolved_channel, bool) or not isinstance(resolved_channel, int):
            return {"status": "ERROR", "reason": "Índice de canal requiere entero"}
        safe_ch = resolved_channel
        if not (0 <= safe_ch < 8):
            return {
                "status": "ERROR",
                "reason": f"Índice de canal inválido ({safe_ch}). Debe estar en el rango 0..7",
            }

        channel_idx = safe_ch
        local_key = str(self.mc.self_info.get("public_key", "")).lower()
        is_local_target = bool(
            target_clean
            and (
                target_clean in ("local", "000000000000")
                or target_clean == local_key
                or (len(local_key) >= 6 and len(target_clean) >= 6 and (local_key.startswith(target_clean) or target_clean.startswith(local_key)))
            )
        )
        if is_local_target:
            return {"status": "ERROR", "reason": "No se permite chat al nodo local"}

        if target_clean.startswith("channel"):
            is_direct = False
            target_node = self.node_bravo
        elif target_clean and target_clean not in ("broadcast", "public", "0xffff", "none"):
            is_direct = True
            matched = None
            for k, n in self.nodes.items():
                k_low = k.lower()
                if (
                    target_clean in (k_low, n["name"].lower(), str(n["alias"]).lower())
                    or (len(target_clean) >= 8 and k_low.startswith(target_clean))
                    or (len(k_low) >= 8 and target_clean.startswith(k_low))
                ):
                    matched = n
                    break
            if matched:
                target_node = matched
                if str(matched.get("role", "")).upper() in ("REPEATER", "ROUTER", "LOCAL", "BASE STATION"):
                    return {"status": "ERROR", "reason": "El destino no admite chat"}
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
                target_node = self.node_bravo
            elif channel_idx == 1:
                target_node = self.node_bravo
            else:
                target_node = self.node_bravo

        exp_ack = f"{(int(time.time() * 1000) ^ (hash(text) & 0xffffffff)) & 0xffffffff:08x}" if is_direct else None
        if target_node:
            task = asyncio.create_task(
                self._simulate_echo_reply(
                    target_node,
                    text,
                    channel_idx=channel_idx,
                    is_direct=is_direct,
                    expected_ack=exp_ack,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        return {
            "status": "ok",
            "delivered": False,
            "target": target or "broadcast",
            "channel": channel_idx,
            "expected_ack": exp_ack,
            "timestamp": int(time.time()),
        }

    async def send_raw_companion_frame(self, data: bytes) -> bool:
        """Emulate the documented read/message subset; unsupported commands return ERROR.

        Synthetic identities are generated only for this simulator. They are not
        padding rules for public keys received from a physical MeshCore network.
        """
        if not data or not self.is_connected:
            return False

        cmd_type = data[0]
        self.heartbeat()

        # CMD_APP_START (1) -> Responder con SELF_INFO (5)
        if cmd_type == 1:
            pubkey_bytes = bytes.fromhex(str(self.mc.self_info["public_key"]))
            info = self.mc.self_info
            lat_int = int(float(info["adv_lat"]) * 1000000)
            lon_int = int(float(info["adv_lon"]) * 1000000)
            freq = int(float(info["radio_freq"]) * 1000)
            bw = int(float(info["bw"]) * 1000)
            sf = int(info["sf"])
            cr = int(info["cr"])
            name_bytes = str(info["name"]).encode("utf-8")

            resp = bytearray()
            resp.append(5)  # PacketType.SELF_INFO
            resp.append(1)  # adv_type
            resp.append(int(info["tx_power"]) & 0xff)  # signed int8 wire representation
            resp.append(int(info.get("max_tx_power", 22)))
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
                contact_buf.append({"CLIENT": 1, "REPEATER": 2, "ROOM": 3, "SENSOR": 4}.get(node["role"], 1))
                contact_buf.extend(b"\x00\xff")  # flags, flood out_path_len
                contact_buf.extend(bytes(64))
                alias = node["alias"].encode("utf-8")[:31].decode("utf-8", "ignore").encode("utf-8")
                contact_buf.extend(alias.ljust(32, b"\x00"))
                contact_buf.extend(int(time.time()).to_bytes(4, "little"))
                contact_buf.extend(int(float(node["lat"]) * 1e6).to_bytes(4, "little", signed=True))
                contact_buf.extend(int(float(node["lon"]) * 1e6).to_bytes(4, "little", signed=True))
                contact_buf.extend(int(time.time()).to_bytes(4, "little"))
                if self.companion_rx_callback:
                    self.companion_rx_callback(bytes(contact_buf))

            end_pkt = bytearray([4]) + int(time.time()).to_bytes(4, "little")
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(end_pkt))
            return True

        # CMD_GET_BATT_AND_STORAGE (20) -> BATTERY (12)
        if cmd_type == 20:
            bat_pkt = struct.pack("<BHII", 12, int(self.mc.self_info["battery_mv"]), 0, 1024)
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(bat_pkt))
            return True

        # CMD_GET_DEVICE_TIME (5) -> CURRENT_TIME (9)
        if cmd_type == 5:
            time_pkt = bytearray([9]) + self.device_time().to_bytes(4, "little")
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(time_pkt))
            return True

        # CMD_SET_DEVICE_TIME (6) updates the same RTC as the SDK setter.
        if cmd_type == 6:
            result = await self.mc.commands.set_time(int.from_bytes(data[1:], "little")) if len(data) == 5 else {"status": "ERROR"}
            if self.companion_rx_callback:
                self.companion_rx_callback(b"\x00" if result["status"] == "ok" else b"\x01\x06")
            return True

        # CMD_DEVICE_QUERY (22) -> DEVICE_INFO (13)
        if cmd_type == 22:
            dev_pkt = (
                bytes([13, 10, 64, max(self.channels, default=-1) + 1])
                + bytes(4)  # virtual BLE PIN
                + b"2026-09-30".ljust(12, b"\x00")
                + b"MeshCore Virtual Transceiver".ljust(40, b"\x00")
                + b"virtual-subset".ljust(20, b"\x00")
                + b"\x00\x00"  # repeater mode, path hash mode
            )
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(dev_pkt))
            return True

        # CMD_GET_STATS (56) -> STATS (24)
        if cmd_type == 56:
            subtype = data[1] if len(data) == 2 else -1
            if subtype == 0:
                core = await self.mc.commands.get_stats_core()
                stats_pkt = struct.pack("<BBHIHB", 24, 0, core["battery_mv"], core["uptime_secs"], core["errors"], core["queue_len"])
            elif subtype == 1:
                radio = await self.mc.commands.get_stats_radio()
                stats_pkt = struct.pack("<BBhbbII", 24, 1, radio["noise_floor"], radio["last_rssi"], int(radio["last_snr"] * 4), radio["tx_air_secs"], radio["rx_air_secs"])
            elif subtype == 2:
                packets = await self.mc.commands.get_stats_packets()
                stats_pkt = struct.pack("<BBIIIIIII", 24, 2, *(packets[key] for key in ("recv", "sent", "flood_tx", "direct_tx", "flood_rx", "direct_rx", "recv_errors")))
            else:
                stats_pkt = b"\x01\x06"  # ERR_CODE_ILLEGAL_ARG
            if self.companion_rx_callback:
                self.companion_rx_callback(bytes(stats_pkt))
            return True

        # CMD_SEND_TXT_MSG (2) o CMD_SEND_CHANNEL_TXT_MSG (3)
        if cmd_type in (2, 3):
            try:
                if data[1] != 0:
                    raise ValueError("Virtual administrative CLI is not emulated")
                if cmd_type == 2:
                    if len(data) < 14:
                        raise ValueError("Truncated DM")
                    target = data[7:13].hex()
                    text = data[13:].decode("utf-8")
                    result = await self.send_message(text, target)
                else:
                    if len(data) < 8:
                        raise ValueError("Truncated channel message")
                    text = data[7:].decode("utf-8")
                    result = await self.send_message(text, channel_idx=data[2])
                if str(result.get("status", "")).upper() == "ERROR":
                    raise ValueError("Rejected virtual message")
                if cmd_type == 2:
                    ack = bytes.fromhex(str(result["expected_ack"]))
                    response = b"\x06\x01" + ack + (1000).to_bytes(4, "little")
                else:
                    response = b"\x00"
            except (ValueError, IndexError, UnicodeDecodeError):
                response = b"\x01\x06"
            if self.companion_rx_callback:
                self.companion_rx_callback(response)
            return True

        if cmd_type == 10:
            response = b"\x0a"  # NO_MORE_MSGS: simulator delivers RX through its event callback
        elif cmd_type == 31 and len(data) == 2 and data[1] in self.channels:
            try:
                channel = self.channels[data[1]]
                name = str(channel["name"]).encode("utf-8")[:31].decode("utf-8", "ignore").encode("utf-8")
                secret = str(channel.get("psk", "")).strip()
                if not secret:
                    key = hashlib.sha256(b"#public").digest()[:16]
                else:
                    try:
                        key_bytes = bytes.fromhex(secret)
                        if len(key_bytes) >= 16:
                            key = key_bytes[:16]
                        else:
                            key = key_bytes.ljust(16, b"\x00")
                    except ValueError:
                        raw_bytes = secret.encode("utf-8")
                        if len(raw_bytes) == 16:
                            key = raw_bytes
                        else:
                            key = hashlib.sha256(raw_bytes).digest()[:16]
                response = bytes([18, data[1]]) + name.ljust(32, b"\x00") + key
            except Exception:
                response = b"\x01\x06"  # ERR_CODE_ILLEGAL_ARG
        else:
            response = b"\x01\x02"  # ERR_CODE_UNSUPPORTED_CMD
        if self.companion_rx_callback:
            self.companion_rx_callback(response)
        return True

    async def _simulate_echo_reply(
        self,
        node: dict[str, Any],
        original_text: str,
        channel_idx: int = 0,
        is_direct: bool = True,
        expected_ack: str | None = None,
    ) -> None:
        """Simula que el nodo remoto procesa el mensaje y responde con un Eco por RF."""
        await asyncio.sleep(0.3)

        if is_direct and expected_ack:
            ack_event = {
                "type": "ACK",
                "event_type": "ack",
                "code": expected_ack,
                "sender": str(node["key"]),
                "trip_time_ms": round(float(node.get("hops", 1)) * 45.0 + 35.0, 1),
                "rssi": node["rssi"],
                "snr": node["snr"],
            }
            self._dispatch_event(ack_event)
            await asyncio.sleep(0.2)

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
        """Bucle continuo que emite telemetría ambiental y posiciones GPS."""
        while self.running:
            try:
                await asyncio.sleep(15.0)
                self._tick_counter += 1
                self.heartbeat()

                self._update_node_states()

                # 1. Emitir Telemetría CayenneLPP de Nodo Alpha (cada 30s)
                if self._tick_counter % 2 == 0:
                    self._emit_cayennelpp_telemetry(self.node_alpha)

                # 2. Emitir Telemetría CayenneLPP de Nodo Bravo (cada 45s)
                if self._tick_counter % 3 == 0:
                    self._emit_cayennelpp_telemetry(self.node_bravo)

                # 3. Anuncios de presencia de red periódicos (cada 60s)
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
            "role": node.get("role", "CLIENT"),
            "adv_type": {"CLIENT": 1, "REPEATER": 2, "ROOM": 3, "SENSOR": 4}.get(str(node.get("role")), 1),
            "event_type": "node_discovered",
            "sender": node["key"],
            "public_key": node["key"],
            "sender_name": node["alias"],
            "alias": node["alias"],
            "name": node["name"],
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
            "public_key": node["key"],
            "sender_name": node["alias"],
            "alias": node["alias"],
            "name": node["name"],
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

    def _dispatch_event(self, event: Any) -> None:
        """Despacha un evento hacia el callback del bridge."""
        if self.rx_callback:
            try:
                self.rx_callback(event)
            except Exception as e:
                logging.error(f"Error en callback del bridge desde simulador: {e}")

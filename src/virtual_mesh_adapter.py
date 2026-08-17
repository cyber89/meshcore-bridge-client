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
        self._tick_counter = 0

        # Definición de los 2 nodos clientes remotos
        self.node_alpha: dict[str, Any] = {
            "key": "a1b2c3d4e5f6",
            "name": "Node_Alpha",
            "alias": "Alpha Field Sensor",
            "lat": 20.1500,
            "lon": -75.2000,
            "alt": 45.0,
            "temp": 24.5,
            "humidity": 58.0,
            "pressure": 1013.2,
            "battery": 94,
            "rssi": -72,
            "snr": 9.8,
            "hops": 1,
        }

        self.node_bravo: dict[str, Any] = {
            "key": "d7e8f9012345",
            "name": "Node_Bravo",
            "alias": "Bravo Scout Rover",
            "lat": 20.1800,
            "lon": -75.2500,
            "alt": 78.0,
            "temp": 26.1,
            "humidity": 52.0,
            "pressure": 1011.8,
            "battery": 88,
            "rssi": -81,
            "snr": 7.2,
            "hops": 2,
        }

    async def connect(self) -> bool:
        """Inicializa la conexión virtual y arranca el bucle de simulación RF."""
        self.is_connected = True
        self.running = True
        logging.info("Adaptador Virtual LoRa MeshCore conectado en modo simulación.")

        # Emitir anuncios iniciales de presencia de ambos nodos
        self._emit_node_presence(self.node_alpha)
        self._emit_node_presence(self.node_bravo)

        # Iniciar ciclo de simulación en segundo plano
        self._sim_task = asyncio.create_task(self._simulation_loop())
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

        target_node = None
        if target_clean in (str(self.node_alpha["key"]), "alpha", str(self.node_alpha["alias"]).lower()):
            target_node = self.node_alpha
        elif target_clean in (str(self.node_bravo["key"]), "bravo", str(self.node_bravo["alias"]).lower()):
            target_node = self.node_bravo
        elif channel_idx == 0 and not target_clean:
            target_node = self.node_alpha

        if target_node:
            asyncio.create_task(self._simulate_echo_reply(target_node, text))

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

        if "stats" in action_clean or "radio" in action_clean:
            return {
                "status": "ok",
                "action": action,
                "frequency_mhz": 915.0,
                "tx_power_dbm": 22,
                "spreading_factor": 11,
                "bandwidth_khz": 250.0,
                "channel_utilization_pct": 3.4,
                "noise_floor_dbm": -118,
            }

        if "neighbor" in action_clean or "node" in action_clean:
            return {
                "status": "ok",
                "action": action,
                "neighbors": [
                    {"pubkey": self.node_alpha["key"], "snr": self.node_alpha["snr"], "rssi": self.node_alpha["rssi"]},
                    {"pubkey": self.node_bravo["key"], "snr": self.node_bravo["snr"], "rssi": self.node_bravo["rssi"]},
                ],
            }

        return {"status": "ok", "action": action, "message": f"Comando '{action}' ejecutado con éxito en repetidor"}

    async def send_frame(self, frame: MeshcoreFrame) -> bool:
        """Procesa una trama saliente enviada desde el bridge y dispara auto-eco si corresponde."""
        if not self.is_connected:
            return False

        self.heartbeat()
        asyncio.create_task(self._process_outbound_frame(frame))
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
            await self._simulate_echo_reply(target_node, text)

    async def _simulate_echo_reply(self, node: dict[str, Any], original_text: str) -> None:
        """Simula que el nodo remoto procesa el mensaje y responde con un Eco por RF."""
        await asyncio.sleep(0.4)

        echo_msg = f"[Echo de {node['alias']}]: Recibido: \"{original_text}\" | SNR: {node['snr']}dB RSSI: {node['rssi']}dBm Hops: {node['hops']}"

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
        self._dispatch_event(echo_event)
        logging.info(f"Bot de Eco ejecutado desde nodo virtual {node['name']} ({node['alias']})")

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

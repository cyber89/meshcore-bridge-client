"""
Simulador Avanzado de Red MeshCore LoRa y Puente MQTT (Heltec v4 Companion USB).
Simula una red completa con múltiples nodos y repetidores transmitiendo en Canales 0, 1, 2 y DMs,
publicando en Mosquitto MQTT, alimentando el servidor Web SPA y Home Assistant Discovery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config
from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter


class SimulatedHeltecV4MeshCoreAdapter(VirtualMeshAdapter):
    """Emulador de hardware Heltec v4 MeshCore Companion USB conectado por USB UART."""

    def __init__(self) -> None:
        super().__init__(port="COM7_HELTEC_V4_USB", baud_rate=115200)

    async def connect(self) -> bool:
        self.is_connected = True
        self.running = True
        logging.info("⚡ [USB-HARDWARE] Heltec v4 MeshCore Companion USB inicializado en COM7 (115200 baud).")

        # Anunciar todos los 8 nodos de la malla
        for node in self.nodes.values():
            self._emit_node_presence(node)

        # Iniciar bucle de simulación activo
        self._sim_task = asyncio.create_task(self._simulation_loop())
        self._background_tasks.add(self._sim_task)
        self._sim_task.add_done_callback(self._background_tasks.discard)
        return True

    async def _simulation_loop(self) -> None:
        """Bucle generador de tráfico LoRa multi-nodo y multi-canal en tiempo real."""
        step = 0
        while self.running:
            try:
                await asyncio.sleep(2.0)
                step += 1
                self.heartbeat()

                # Actualizar movimiento GPS del Rover y Drone
                angle = step * 0.2
                if "d7e8f9012345" in self.nodes:
                    self.nodes["d7e8f9012345"]["lat"] = 20.1850 + round(math.sin(angle) * 0.006, 4)
                    self.nodes["d7e8f9012345"]["lon"] = -75.2420 + round(math.cos(angle) * 0.006, 4)
                if "7a8b9c0d1e2f" in self.nodes:
                    self.nodes["7a8b9c0d1e2f"]["lat"] = 20.1920 + round(math.cos(angle * 1.5) * 0.010, 4)
                    self.nodes["7a8b9c0d1e2f"]["lon"] = -75.2110 + round(math.sin(angle * 1.5) * 0.010, 4)

                # 1. Tráfico Canal 0 (Público / Broadcast comunitario)
                if step % 2 == 1:
                    messages_ch0 = [
                        ("e9f012345678", "¡Saludos equipo! Enlace de radio Heltec v4 LoRa 915MHz excelente."),
                        ("a1b2c3d4e5f6", "[Anuncio Router]: Malla operativa en SF11 BW250. 5 nodos conectados."),
                        ("d7e8f9012345", "Rover en patrulla de exploración sector norte. Coordenadas GPS transmitidas."),
                        ("6f7e8d9c0b1a", "[Base HQ]: Estación central en escucha activa. Todos los enlaces verdes."),
                    ]
                    sender_key, txt = messages_ch0[(step // 2) % len(messages_ch0)]
                    node = self.nodes[sender_key]
                    self._dispatch_event({
                        "type": "CHANNEL_MSG",
                        "event_type": "public",
                        "sender": node["key"],
                        "sender_name": node["alias"],
                        "role": node["role"],
                        "lat": node.get("lat"),
                        "lon": node.get("lon"),
                        "text": txt,
                        "channel_idx": 0,
                        "channel_index": 0,
                        "metrics": {"rssi": node["rssi"], "snr": node["snr"]},
                        "hop_count": node["hops"],
                        "battery": node["battery"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # 2. Tráfico Canal 1 (Operaciones Tácticas - Cifrado AES)
                if step % 3 == 0:
                    messages_ch1 = [
                        ("d7e8f9012345", f"Reporte Táctico: Punto de control alcanzado ({self.nodes['d7e8f9012345']['lat']}, {self.nodes['d7e8f9012345']['lon']}) - Batería {self.nodes['d7e8f9012345']['battery']}%"),
                        ("7a8b9c0d1e2f", "🚁 Reconocimiento aéreo completado. Perímetro este despejado."),
                    ]
                    sender_key, txt = messages_ch1[(step // 3) % len(messages_ch1)]
                    node = self.nodes[sender_key]
                    self._dispatch_event({
                        "type": "CHANNEL_MSG",
                        "event_type": "channel",
                        "sender": node["key"],
                        "sender_name": node["alias"],
                        "role": node["role"],
                        "lat": node.get("lat"),
                        "lon": node.get("lon"),
                        "text": txt,
                        "channel_idx": 1,
                        "channel_index": 1,
                        "metrics": {"rssi": node["rssi"], "snr": node["snr"]},
                        "hop_count": node["hops"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # 3. Tráfico Canal 3 (Emergencias Malla - Cifrado)
                if step % 5 == 0:
                    node = self.nodes["5a6b7c8d9e0f"]
                    self._dispatch_event({
                        "type": "CHANNEL_MSG",
                        "event_type": "channel",
                        "sender": node["key"],
                        "sender_name": node["alias"],
                        "role": node["role"],
                        "lat": node.get("lat"),
                        "lon": node.get("lon"),
                        "text": "⚡ [Canal Emergencia]: Prueba de redundancia de energía solar OK. Canal de respaldo listo.",
                        "channel_idx": 3,
                        "channel_index": 3,
                        "metrics": {"rssi": node["rssi"], "snr": node["snr"]},
                        "hop_count": node["hops"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # 4. Mensajes Directos Punto a Punto (DMs)
                if step % 4 == 0:
                    dm_samples = [
                        ("a1b2c3d4e5f6", "Alpha Sensor: Telemetría ambiental sincronizada. Nivel de señal óptimo."),
                        ("e9f012345678", "Delta Operative: Recibido enlace base. Listo para transmisión."),
                        ("7a8b9c0d1e2f", "Golf Drone: Transmitiendo datos de vuelo y altitud de patrulla."),
                    ]
                    sender_key, dm_txt = dm_samples[(step // 4) % len(dm_samples)]
                    node = self.nodes[sender_key]
                    self._dispatch_event({
                        "type": "DIRECT_MSG",
                        "event_type": "direct",
                        "sender": node["key"],
                        "sender_name": node["alias"],
                        "role": node["role"],
                        "lat": node.get("lat"),
                        "lon": node.get("lon"),
                        "text": dm_txt,
                        "metrics": {"rssi": node["rssi"], "snr": node["snr"]},
                        "hop_count": node["hops"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # 5. Telemetría Ambiental CayenneLPP (Canal 2 / Sensores)
                if step % 2 == 0:
                    sensor_node = self.nodes["c3d4e5f6a7b8"]
                    self._emit_cayennelpp_telemetry(sensor_node)

                # 6. Sniffer de Tramas RF Wire (0x88 / Raw Frame Interception)
                if step % 2 == 0:
                    self._emit_sniffer_wire_packet()

                # 7. Simulación de Error RF / CRC Mismatch periódica para verificar métricas de error
                if step % 5 == 0:
                    if hasattr(self, "_bridge_ref") and self._bridge_ref:
                        self._bridge_ref.tx_error_count += 1
                        self._bridge_ref.err_count += 1
                        if hasattr(self._bridge_ref, "web_server") and self._bridge_ref.web_server:
                            self._bridge_ref.web_server.router.log_system_event(
                                "WARNING",
                                f"Trama LoRa descartada por CRC corrupto (RSSI -118 dBm, SNR -7.5 dB). Reintentos: {step % 3}",
                                source="rf_radio",
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en bucle de simulación: {e}")

    def _emit_sniffer_wire_packet(self) -> None:
        """Inyecta una trama RF raw real en el sniffer con OpCode dinámico."""
        opcodes = ["TEXT_MSG", "TELEMETRY_RESP", "NODE_ADVERT", "ACK", "ROUTING_TABLE"]
        op = opcodes[int(time.time()) % len(opcodes)]
        src = list(self.nodes.keys())[int(time.time()) % len(self.nodes)]
        raw_hex = f"02{int(time.time() * 1000) & 0xFF:02x}{src[:6]}ffff{int(time.time()) & 0xFFFF:04x}4d657368436f7265"

        sniff_event = {
            "type": "LOG_DATA",
            "event_type": "rf_log",
            "opcode": op,
            "sender": src,
            "to": "0xFFFF",
            "byte_length": len(raw_hex) // 2,
            "raw_hex": raw_hex,
            "snr": round(8.0 + (int(time.time()) % 5), 1),
            "rssi": -70 - (int(time.time()) % 15),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._dispatch_event(sniff_event)


async def run_simulation(duration_sec: int = 15) -> None:
    """Ejecuta la simulación completa con Heltec v4, Mosquitto MQTT y Servidor Web."""
    print("=" * 80)
    print(" 📻 MESHCORE BRIDGE - SIMULACIÓN EN VIVO (HELTEC V4 USB + MOSQUITTO MQTT)")
    
    # 1. Configurar logging y directorios de logs
    config.WEB_PORT = 8080
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "simulation_meshcore_full.log"
    events_jsonl = log_dir / "simulation_events.jsonl"

    if events_jsonl.exists():
        events_jsonl.unlink()

    # Logging file handler
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
    root_logger.addHandler(fh)

    # 2. Instanciar Bridge con Adaptador Heltec v4
    bridge = MeshCoreBridge()
    sim_adapter = SimulatedHeltecV4MeshCoreAdapter()
    sim_adapter._bridge_ref = bridge
    bridge.serial_adapter = sim_adapter
    sim_adapter.set_rx_callback(bridge.on_mesh_event)

    # Interceptar eventos para registro JSONL
    orig_broadcast = bridge.web_server.broadcast_event

    def logging_broadcast(event_data: dict[str, Any]) -> None:
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_data.get("type") or event_data.get("event_type") or "unknown",
                "sender": event_data.get("sender") or event_data.get("recipient") or "system",
                "details": event_data,
            }
            with open(events_jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
        orig_broadcast(event_data)

    bridge.web_server.broadcast_event = logging_broadcast

    # 3. Interceptar publicaciones MQTT para monitoreo visual en consola
    mqtt_messages_logged: list[dict[str, Any]] = []
    original_publish = bridge.mqtt.publish_safe

    def logging_publish_safe(topic: str, payload: str, qos: int = 0, retain: bool = False, *args: Any, **kwargs: Any) -> bool:
        mqtt_messages_logged.append({
            "topic": topic,
            "payload": payload[:100] + ("..." if len(payload) > 100 else ""),
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        })
        print(f"📡 [MQTT OUT] Tópico: {topic:<40} | Retain: {str(retain):<5} | Payload: {payload[:80]}")
        return original_publish(topic, payload, qos=qos, retain=retain)

    bridge.mqtt.publish_safe = logging_publish_safe  # type: ignore[method-assign]

    # 4. Iniciar subsistemas del Bridge
    await bridge.start()
    print(f"\n🚀 [SISTEMA] Servidor Web SPA disponible en: http://localhost:{config.WEB_PORT}\n")

    # 5. Ejecutar tráfico simulado por la duración solicitada
    try:
        # Enviar mensaje de prueba directo vía API / Chat
        await asyncio.sleep(1.5)
        print("\n💬 [TX CHAT] Transmitiendo mensaje desde Estación Base en Canal 0 (Público)...")
        await bridge._execute_tx({"to": "broadcast", "channel_index": 0, "text": "Hola a todos desde MeshCore Web Station Base", "request_id": "sim_tx_1"})

        await asyncio.sleep(1.5)
        print("\n💬 [TX DM] Enviando Mensaje Directo (DM) a 🏔️ Alpha Mountain Repeater...")
        dm_res = await bridge._execute_tx({"to": "a1b2c3d4e5f6", "channel_index": 0, "text": "Reporte de estado de repetidor y calidad de enlace", "request_id": "sim_tx_2"})
        print(f"  ✓ Expected ACK code: {dm_res.get('expected_ack')}")

        await asyncio.sleep(1.5)
        print("\n🎯 [PING ZERO] Ejecutando Ping Zero a 🏔️ Alpha Mountain Repeater...")
        ping_res = await bridge.admin_handler.handle({
            "target_node": "a1b2c3d4e5f6",
            "action": "ping_zero",
        })
        print(f"  ✓ Ping Zero Result: Duration={ping_res.get('rtt_ms')} ms, SNR there={ping_res.get('snr_there')}, SNR back={ping_res.get('snr_back')}, RSSI={ping_res.get('rssi')} dBm")

        await asyncio.sleep(1.5)
        print("\n🎛️ [REPEATER CMD] Enviando comando 'stats-radio' a repetidor Alpha...")
        stats_reply = await bridge.admin_handler.handle({
            "target_node": "a1b2c3d4e5f6",
            "action": "stats-radio",
        })
        print(f"✓ [REPEATER DISPATCH]: {json.dumps(stats_reply)}")

        if duration_sec <= 0:
            print("\n🟢 [MODO EN VIVO] Simulación ejecutándose indefinidamente. Presiona Ctrl+C para detener.")
            while True:
                await asyncio.sleep(1)
        else:
            print(f"\n⏳ Ejecutando simulación de tráfico continuo durante {duration_sec} segundos...")
            await asyncio.sleep(duration_sec)

    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\n🛑 Detención solicitada por el usuario.")
    finally:
        await bridge.stop()
        print("\n" + "=" * 80)
        print(" 📊 RESUMEN DE LA SIMULACIÓN DE HARDWARE Y RED LoRa")
        print("=" * 80)
        print(f"• Total Paquetes RX Recibidos por Radio:  {bridge.rx_count}")
        print(f"• Total Paquetes TX Transmitidos:        {bridge.tx_count}")
        print(f"• Nodos Registrados en Directorio:       {len(bridge.node_registry.list_nodes())}")
        print(f"• Mensajes Publicados en MQTT Mosquitto: {len(mqtt_messages_logged)}")
        print(f"• Fichero de Logs Generado:              {log_file}")
        print(f"• Fichero de Eventos JSONL:              {events_jsonl}")
        print("=" * 80)


if __name__ == "__main__":
    dur = 12
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--live", "--forever", "-f", "live", "forever"):
            dur = 0
        else:
            try:
                dur = int(sys.argv[1])
            except ValueError:
                pass
    try:
        asyncio.run(run_simulation(dur))
    except KeyboardInterrupt:
        print("\nProceso finalizado.")

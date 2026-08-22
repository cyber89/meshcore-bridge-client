"""
Pruebas de Validación para la Lógica de Parsing, Desempaquetado y Deduplicación de n8n.
Simula el comportamiento exacto de los nodos JavaScript de n8n ante todas las variantes de payloads.
"""

import json
import time
import unittest


class N8nSimulator:
    """Simulador de la lógica JavaScript del flujo n8n para pruebas automatizadas."""
    def __init__(self):
        self.message_cache = {}
        self.admin_whitelist = ['admin_master', 'heltec_admin', '8f3a12bc']
        self.cache_ttl_sec = 30.0

    def parse_and_deduplicate(self, input_item: dict, now_ts: float = None) -> dict:
        if now_ts is None:
            now_ts = time.time()

        payload = input_item.get("json", input_item)

        # 1. Desempaquetar si viene en message o data
        if "message" in payload and payload["message"] is not None:
            if isinstance(payload["message"], str):
                try:
                    payload = json.loads(payload["message"])
                except Exception:
                    payload = {"text": payload["message"], "event_type": "public"}
            elif isinstance(payload["message"], dict):
                payload = payload["message"]
        elif "data" in payload and payload["data"] is not None:
            if isinstance(payload["data"], str):
                try:
                    payload = json.loads(payload["data"])
                except Exception:
                    payload = {"text": payload["data"], "event_type": "public"}

        if not isinstance(payload, dict):
            return None

        event_type = payload.get("event_type", "public")
        sender_id = str(payload.get("sender_id", "unknown"))
        channel_idx = int(payload.get("channel_index", 0))
        text = str(payload.get("text", payload.get("raw_text", ""))).strip()

        msg_key = f"{event_type}_{sender_id}_{channel_idx}_{text}"

        is_duplicate = False
        if len(text) > 0:
            if msg_key in self.message_cache and (now_ts - self.message_cache[msg_key] < self.cache_ttl_sec):
                is_duplicate = True
            else:
                self.message_cache[msg_key] = now_ts

        result = dict(payload)
        result["event_type"] = event_type
        result["sender_id"] = sender_id
        result["channel_index"] = channel_idx
        result["text"] = text
        result["is_duplicate"] = is_duplicate
        return result

    def process_dm_and_admin(self, msg: dict) -> list:
        raw_text = str(msg.get("text", "")).strip()
        lower = raw_text.toLowerCase() if hasattr(raw_text, "toLowerCase") else raw_text.lower()
        sender_id = str(msg.get("sender_id", "unknown"))
        sender_name = msg.get("sender_name", sender_id)
        is_admin = (sender_id in self.admin_whitelist) or (sender_name in self.admin_whitelist)

        results = []

        if lower == "/status":
            reply_text = "[Status Heltec v4]\nBridge: Online\nNodo: Activo"
            results.append({
                "topic": "meshcore/tx",
                "to": sender_id,
                "channel_index": 0,
                "text": reply_text
            })
            return results

        if lower.startswith("/admin"):
            if not is_admin:
                results.append({
                    "topic": "meshcore/tx",
                    "to": sender_id,
                    "channel_index": 0,
                    "text": "⛔ Acceso denegado: Nodo no autorizado para comandos administrativos."
                })
                return results

            parts = [p for p in raw_text.split(" ") if len(p) > 0]
            sub_cmd = parts[1].lower() if len(parts) > 1 else ""

            if sub_cmd in ["get_config", "config"]:
                results.append({"topic": "meshcore/tx", "to": sender_id, "text": "⚙️ Consultando configuración..."})
                results.append({"topic": "meshcore/admin/cmd", "action": "get_config"})
            return results

        # Eco DM
        results.append({
            "topic": "meshcore/tx",
            "to": sender_id,
            "channel_index": 0,
            "text": f'[Eco DM] Recibido: "{raw_text}"'
        })
        return results

    def format_periodic_weather_status(self, weather_data: dict, fixed_dt_str: str = "2026-08-22 18:00") -> dict:
        """Simula la lógica del nodo JavaScript 'Formatear Reporte Estado y Clima'."""
        wmo_codes = {
            0: "☀️ Despejado",
            1: "🌤️ Mayormente despejado",
            2: "⛅ Parcialmente nublado",
            3: "☁️ Nublado",
            45: "🌫️ Niebla",
            51: "🌦️ Llovizna ligera",
            61: "🌧️ Lluvia ligera",
            71: "❄️ Nieve ligera",
            80: "🌧️ Chubascos ligeros",
            95: "⛈️ Tormenta eléctrica",
        }

        current = weather_data.get("current", {})
        temp_c = float(current.get("temperature_2m", 25.0))
        temp_f = round((temp_c * 9.0 / 5.0) + 32.0, 1)
        feels_like_c = float(current.get("apparent_temperature", temp_c))
        feels_like_f = round((feels_like_c * 9.0 / 5.0) + 32.0, 1)
        humidity = int(current.get("relative_humidity_2m", 60))
        wind_kmh = float(current.get("wind_speed_10m", 10.0))
        wind_mph = round(wind_kmh * 0.621371, 1)
        code = int(current.get("weather_code", 0))
        desc = wmo_codes.get(code, "🌤️ Variable")
        precip = float(current.get("precipitation", 0.0))

        status_text = (
            f"📡 [Estado Periódico - Lehigh Acres, FL]\n"
            f"📅 {fixed_dt_str} (Local)\n"
            f"🌡️ Temp: {temp_c}°C ({temp_f}°F) | ST: {feels_like_c}°C ({feels_like_f}°F)\n"
            f"💧 Hum: {humidity}% | 💨 Viento: {wind_kmh} km/h ({wind_mph} mph)\n"
            f"🌤️ Clima: {desc}"
        )
        if precip > 0:
            status_text += f" | 🌧️ Prec: {precip} mm"

        return {
            "topic": "meshcore/tx",
            "request_id": f"n8n_periodic_{int(time.time())}",
            "to": "broadcast",
            "channel_index": 0,
            "text": status_text,
            "metadata": {
                "location": "Lehigh Acres, FL",
                "temperature_c": temp_c,
                "temperature_f": temp_f,
                "humidity_pct": humidity,
                "wind_kmh": wind_kmh,
                "weather_code": code,
                "weather_desc": desc,
            }
        }



class TestN8nParserMatrix(unittest.TestCase):
    def setUp(self):
        self.sim = N8nSimulator()

    def test_n8n_deserialization_wrapped_in_message_string(self):
        """Simula MQTT Trigger entregando un JSON stringificado en message."""
        raw_item = {
            "json": {
                "topic": "meshcore/rx/all",
                "message": json.dumps({"event_type": "public", "sender_id": "Nodo_Alpha", "text": "Hola n8n"})
            }
        }
        res = self.sim.parse_and_deduplicate(raw_item)
        self.assertIsNotNone(res)
        self.assertEqual(res["event_type"], "public")
        self.assertEqual(res["sender_id"], "Nodo_Alpha")
        self.assertEqual(res["text"], "Hola n8n")
        self.assertFalse(res["is_duplicate"])

    def test_n8n_deserialization_plain_text_fallback(self):
        """Simula MQTT Trigger recibiendo texto plano."""
        raw_item = {
            "json": {
                "topic": "meshcore/rx/public",
                "message": "Hola directo desde terminal"
            }
        }
        res = self.sim.parse_and_deduplicate(raw_item)
        self.assertIsNotNone(res)
        self.assertEqual(res["event_type"], "public")
        self.assertEqual(res["text"], "Hola directo desde terminal")

    def test_n8n_deduplication_exact_timing(self):
        """Prueba que mensajes repetidos dentro de 30s se marquen duplicados y después de 30s como nuevos."""
        item = {"json": {"event_type": "public", "sender_id": "8f3a12bc", "text": "Alerta repetida"}}

        t0 = 1000.0
        r1 = self.sim.parse_and_deduplicate(item, now_ts=t0)
        self.assertFalse(r1["is_duplicate"], "El primer mensaje debe ser nuevo")

        # Repetición 10 segundos después
        r2 = self.sim.parse_and_deduplicate(item, now_ts=t0 + 10.0)
        self.assertTrue(r2["is_duplicate"], "El segundo mensaje dentro de 30s debe ser marcado duplicado")

        # Mensaje 35 segundos después (expiró ventana)
        r3 = self.sim.parse_and_deduplicate(item, now_ts=t0 + 35.0)
        self.assertFalse(r3["is_duplicate"], "Tras 35s el mensaje debe ser procesado como nuevo")

    def test_n8n_admin_whitelist_authorization(self):
        """Verifica que solo los administradores puedan invocar /admin."""
        # 1. Nodo no autorizado
        unauth_msg = {"sender_id": "nodo_anonimo", "text": "/admin get_config"}
        out1 = self.sim.process_dm_and_admin(unauth_msg)
        self.assertEqual(len(out1), 1)
        self.assertTrue("Acceso denegado" in out1[0]["text"])

        # 2. Nodo autorizado (en whitelist)
        auth_msg = {"sender_id": "admin_master", "text": "/admin get_config"}
        out2 = self.sim.process_dm_and_admin(auth_msg)
        self.assertEqual(len(out2), 2)
        self.assertEqual(out2[1]["topic"], "meshcore/admin/cmd")
        self.assertEqual(out2[1]["action"], "get_config")

    def test_n8n_periodic_weather_formatting(self):
        """Verifica la generación del reporte meteorológico para Lehigh Acres."""
        sample_weather = {
            "current": {
                "temperature_2m": 28.5,
                "apparent_temperature": 32.0,
                "relative_humidity_2m": 72,
                "weather_code": 1,
                "wind_speed_10m": 12.5,
                "precipitation": 0.0,
            }
        }
        res = self.sim.format_periodic_weather_status(sample_weather, fixed_dt_str="2026-08-22 18:00")
        self.assertEqual(res["topic"], "meshcore/tx")
        self.assertEqual(res["to"], "broadcast")
        self.assertEqual(res["channel_index"], 0)
        self.assertIn("Lehigh Acres, FL", res["text"])
        self.assertIn("28.5°C (83.3°F)", res["text"])
        self.assertIn("ST: 32.0°C (89.6°F)", res["text"])
        self.assertIn("💧 Hum: 72%", res["text"])
        self.assertIn("🌤️ Mayormente despejado", res["text"])
        self.assertEqual(res["metadata"]["location"], "Lehigh Acres, FL")
        self.assertEqual(res["metadata"]["temperature_c"], 28.5)
        self.assertEqual(res["metadata"]["temperature_f"], 83.3)


if __name__ == "__main__":
    unittest.main()


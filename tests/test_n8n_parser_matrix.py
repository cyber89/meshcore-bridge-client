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


if __name__ == "__main__":
    unittest.main()

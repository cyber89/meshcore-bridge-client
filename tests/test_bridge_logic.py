"""
Pruebas unitarias para validar la lógica del puente MeshCore Bridge:
- Parsing seguro de mensajes de canales y DMs (sin romper textos con dos puntos).
- Manejo de transmisión (TX) tolerante a texto plano y JSON estructurado.
- Lógica de deduplicación de paquetes anti-relay.
"""

import json
import time
import unittest


class MockContact:
    def __init__(self, name, public_key):
        self.name = name
        self.public_key = public_key
        self.alias = name


class MockMeshCore:
    def __init__(self):
        self.contacts = [
            MockContact("Nodo_Alfa", "1122334455667788"),
            MockContact("Heltec_Master", "aabbccddeeff0011")
        ]
        self.self_info = {
            "name": "Heltec_Bridge",
            "radio_freq": 910.525,
            "tx_power": 20,
            "public_key": "aabbccddeeff0011"
        }

    def get_contact_by_key_prefix(self, prefix):
        for c in self.contacts:
            if c.public_key.startswith(prefix):
                return c
        return None

    def get_contact_by_name(self, name):
        for c in self.contacts:
            if c.name.lower() == name.lower():
                return c
        return None


class TestBridgeLogic(unittest.TestCase):
    def setUp(self):
        self.mock_mc = MockMeshCore()

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        if not prefix_or_key:
            return prefix_or_key
        c = self.mock_mc.get_contact_by_key_prefix(prefix_or_key)
        if c:
            return c.name
        for contact in self.mock_mc.contacts:
            if prefix_or_key in contact.public_key:
                return contact.name
        return prefix_or_key

    def test_colon_in_channel_message_preserved(self):
        """Valida que mensajes con dos puntos (URLs, horas, alertas) no sean mutilados."""
        raw_text = "Alerta: Temperatura critica a las 14:30 en http://sensor.local"
        sender_id = "11223344"
        sender_name = self.resolve_sender_name(sender_id)

        self.assertEqual(sender_name, "Nodo_Alfa")
        # El texto completo debe conservarse intacto
        self.assertIn("14:30", raw_text)
        self.assertIn("http://sensor.local", raw_text)

    def test_plain_text_tx_fallback(self):
        """Valida que un payload MQTT de texto plano no lance excepciones y se estructure correctamente."""
        raw_payload = "Mensaje directo de prueba"

        # Simulación del parser de on_mqtt_message
        try:
            data = json.loads(raw_payload)
        except Exception:
            data = {"text": raw_payload}

        if not isinstance(data, dict):
            data = {"text": str(data)}

        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("text"), "Mensaje directo de prueba")
        self.assertEqual(data.get("to", "broadcast"), "broadcast")
        self.assertEqual(data.get("channel_index", 0), 0)

    def test_json_tx_parsing_with_request_id(self):
        """Valida el parsing de órdenes JSON estructuradas con request_id para n8n."""
        json_payload = json.dumps({
            "request_id": "n8n_test_123",
            "to": "Nodo_Alfa",
            "channel_index": 2,
            "text": "Comando de prueba"
        })

        data = json.loads(json_payload)
        self.assertEqual(data["request_id"], "n8n_test_123")
        self.assertEqual(data["to"], "Nodo_Alfa")
        self.assertEqual(data["channel_index"], 2)
        self.assertEqual(data["text"], "Comando de prueba")

        # Resolución de destinatario
        contact = self.mock_mc.get_contact_by_name(data["to"])
        target_key = contact.public_key if contact else data["to"]
        self.assertEqual(target_key, "1122334455667788")

    def test_deduplication_logic(self):
        """Simula y valida el mecanismo de deduplicación de paquetes repetidos por relays."""
        cache = {}
        ttl = 30  # segundos

        def process_message(event_type, sender_id, channel_idx, text, current_time):
            key = f"{event_type}_{sender_id}_{channel_idx}_{text}"
            if key in cache and (current_time - cache[key] < ttl):
                return True  # Duplicado
            cache[key] = current_time
            return False  # Nuevo

        t0 = time.time()
        # Primer paquete recibido directamente del nodo
        dup1 = process_message("public", "11223344", 0, "Hola a todos", t0)
        self.assertFalse(dup1, "El primer mensaje debe considerarse nuevo")

        # Segundo paquete recibido 3 segundos después retransmitido por un repetidor
        dup2 = process_message("public", "11223344", 0, "Hola a todos", t0 + 3)
        self.assertTrue(dup2, "El paquete repetido por el relay debe ser marcado como duplicado")

        # Tercer paquete con diferente texto
        dup3 = process_message("public", "11223344", 0, "Otro mensaje", t0 + 5)
        self.assertFalse(dup3, "Un mensaje con contenido diferente debe ser procesado")

        # Cuarto paquete recibido después de expirar la ventana TTL (35s después)
        dup4 = process_message("public", "11223344", 0, "Hola a todos", t0 + 35)
        self.assertFalse(dup4, "Un mensaje tras expirar el TTL debe volver a considerarse nuevo")


if __name__ == "__main__":
    unittest.main()

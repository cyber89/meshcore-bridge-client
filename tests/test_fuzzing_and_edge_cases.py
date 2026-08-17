"""
Pruebas de Fuzzing, Inyección y Casos Límite Extremos para MeshCore Bridge.
Cubre payloads corruptos, inyecciones SQL, caracteres nulos, valores numéricos extremos,
eventos de radio malformados y desbordamiento de cadenas.
"""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from meshcore_bridge import MeshCoreBridge


class DummyEventType:
    def __init__(self, name):
        self.name = name


class DummyEvent:
    def __init__(self, ev_type, payload):
        self.type = ev_type
        self.payload = payload


class TestFuzzingAndEdgeCases(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        self.bridge = MeshCoreBridge(self.loop, db_path=self.temp_db_path)
        self.bridge.mqtt_client = MagicMock()
        self.published = []
        self.bridge.mqtt_client.publish.side_effect = lambda t, p, qos=0, retain=False: self.published.append((t, p))
        self.bridge.mqtt_connected = True

        # Mock del transceptor MeshCore
        self.mock_mc = MagicMock()
        self.mock_mc.commands = MagicMock()
        self.mock_mc.commands.send_chan_msg = AsyncMock(return_value=DummyEvent("OK", {}))
        self.mock_mc.commands.send_msg = AsyncMock(return_value=DummyEvent("OK", {}))
        self.mock_mc.commands.set_name = AsyncMock(return_value=DummyEvent("OK", {}))
        self.mock_mc.commands.set_tx_power = AsyncMock(return_value=DummyEvent("OK", {}))
        self.mock_mc.commands.req_telemetry = AsyncMock(return_value=DummyEvent("OK", {}))
        self.mock_mc.commands.reboot = AsyncMock(return_value=DummyEvent("OK", {}))
        self.mock_mc.contacts = []
        self.mock_mc.self_info = {"name": "TestNode", "radio_freq": 915.0}
        self.bridge.mc = self.mock_mc

    def tearDown(self):
        self.loop.close()
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
            for ext in ["-wal", "-shm"]:
                wal_f = self.temp_db_path + ext
                if os.path.exists(wal_f):
                    os.remove(wal_f)
        except Exception:
            pass

    def test_mqtt_fuzzing_malformed_and_weird_payloads(self):
        """Prueba mensajes MQTT con tipos de datos extraños sin que el servicio se bloquee."""
        weird_inputs = [
            b"",                                        # Cadena vacía
            b"   ",                                     # Espacios en blanco
            b"null",                                    # JSON null
            b"true",                                    # JSON booleano
            b"12345",                                   # JSON número
            b"[1, 2, 3]",                               # JSON array
            b"{not a valid json:",                      # JSON sintaxis inválida
            b"\x00\x01\x02\xff",                        # Bytes binarios no UTF-8
            ('{"text": "' + ('A' * 10000) + '"}').encode("utf-8"), # Payload gigante de 10KB
            b'{"to": null, "channel_index": null, "text": "Test"}',
            b'{"to": 12345, "channel_index": "invalido", "text": 67890}',
        ]

        for raw_bytes in weird_inputs:
            msg_mock = MagicMock()
            msg_mock.topic = "meshcore/tx"
            msg_mock.payload = raw_bytes

            # Debe procesarlo sin excepciones no controladas
            try:
                self.bridge.on_mqtt_message(self.bridge.mqtt_client, None, msg_mock)
            except Exception as e:
                self.fail(f"on_mqtt_message falló con payload {raw_bytes}: {e}")

    def test_sql_injection_and_special_characters_in_sqlite(self):
        """Verifica que strings con inyección SQL y caracteres especiales se almacenen intactos."""
        naughty_strings = [
            "'; DROP TABLE offline_queue; --",
            "\" OR \"1\"=\"1",
            "SELECT * FROM offline_queue WHERE id = 1; DELETE FROM offline_queue;",
            "Emojis: 🚀🔥📻📡🛰️ ñandú áéíóú Ç",
            "Líneas múltiples\n\r\tcon saltos\ny comillas ' \" `",
            "Caracteres de control: \x00\x07\x08\x1b",
        ]

        self.bridge.mqtt_connected = False
        for text in naughty_strings:
            self.bridge.publish_mqtt_safe("meshcore/rx/all", text, qos=1)

        self.assertEqual(self.bridge.sqlite_buffer.get_size(), len(naughty_strings))

        # Reconectar y vaciar
        self.bridge.mqtt_connected = True
        self.bridge._flush_offline_buffer()

        self.assertEqual(len(self.published), len(naughty_strings))
        for i, (_t, p) in enumerate(self.published):
            self.assertEqual(p, naughty_strings[i], f"El string {i} debe coincidir byte a byte")

    def test_extreme_numerical_values_in_tx_and_admin(self):
        """Prueba valores fuera de rango en potencia y canales de transmisión."""
        # 1. Canal extremo en TX
        tx_data = {
            "to": "broadcast",
            "channel_index": 9999999,
            "text": "Prueba canal extremo"
        }
        self.loop.run_until_complete(self.bridge._execute_tx(tx_data))
        self.mock_mc.commands.send_chan_msg.assert_called_with(9999999, "Prueba canal extremo")

        # 2. Potencia extrema en Admin
        admin_data = {
            "action": "set_tx_power",
            "power": 5000,
            "request_id": "test_pow_99"
        }
        self.loop.run_until_complete(self.bridge.handle_admin(admin_data))
        self.mock_mc.commands.set_tx_power.assert_called_with(5000)

    def test_radio_event_fuzzing_corrupt_structures(self):
        """Prueba eventos de radio entrantes con estructuras corruptas o tipos no dict."""
        corrupt_events = [
            DummyEvent(None, None),
            DummyEvent("UNKNOWN_EVENT_123", {"data": "algo"}),
            DummyEvent(12345, "string payload"),
            DummyEvent("CHANNEL_MSG_RECV", None),
            DummyEvent("CHANNEL_MSG_RECV", "no es un dict"),
            DummyEvent("CHANNEL_MSG_RECV", {"text": "", "sender": None}),
            DummyEvent("CONTACT_MSG_RECV", {"message": None, "sender": 12345}),
            DummyEvent("TELEMETRY", {"voltage": "invalido", "battery": None}),
            DummyEvent("ADVERT", {"pubkey": None, "name": 9999}),
        ]

        for ev in corrupt_events:
            try:
                self.bridge.on_mesh_event(ev)
            except Exception as e:
                self.fail(f"on_mesh_event falló con evento corrupto {ev}: {e}")

    def test_radio_commands_returning_error_events(self):
        """Verifica que si la radio SX1262 retorna un evento de error, el bridge lo capture y publique ACK de error."""
        error_event = DummyEvent("ERROR", {"code": "ERR_BUSY", "message": "Canal LoRa ocupado"})
        self.mock_mc.commands.send_chan_msg = AsyncMock(return_value=error_event)

        tx_data = {
            "request_id": "req_err_test",
            "to": "broadcast",
            "channel_index": 0,
            "text": "Mensaje que fallará"
        }
        self.loop.run_until_complete(self.bridge._execute_tx(tx_data))

        # Debe haber publicado un estado de error en meshcore/tx/status
        status_publishes = [p for t, p in self.published if t == "meshcore/tx/status"]
        self.assertTrue(len(status_publishes) > 0)
        status_json = json.loads(status_publishes[-1])
        self.assertEqual(status_json["status"], "error")
        self.assertEqual(status_json["request_id"], "req_err_test")

    def test_admin_commands_unhandled_and_missing_parameters(self):
        """Prueba comandos de administración con acciones inexistentes y campos faltantes."""
        test_cases = [
            {"action": "accion_inexistente"},
            {"action": "set_name"},                       # Falta name
            {"action": "set_tx_power"},                   # Falta power
            {"action": "req_telemetry"},                  # Falta target
            {"action": None},
            {},
        ]

        for data in test_cases:
            self.published.clear()
            self.loop.run_until_complete(self.bridge.handle_admin(data))
            self.assertTrue(len(self.published) > 0)
            res = json.loads(self.published[0][1])
            self.assertTrue("status" in res)


if __name__ == "__main__":
    unittest.main()

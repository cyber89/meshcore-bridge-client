"""
Prueba de Simulación End-to-End (E2E) Completa.
Simula el ciclo de vida completo de un nodo Heltec v4 (MeshCore v1.17),
el broker MQTT y los flujos bidireccionales de n8n.
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from meshcore_bridge import MeshCoreBridge


class MockEventType:
    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        if hasattr(other, "name"):
            return self.name == other.name
        return False


class MockEvent:
    def __init__(self, ev_type_name, payload):
        self.type = MockEventType(ev_type_name)
        self.payload = payload


class MockContact:
    def __init__(self, name: str, public_key: str):
        self.name = name
        self.public_key = public_key
        self.alias = name


class TestE2ESimulation(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.bridge = MeshCoreBridge(self.loop)
        self.bridge.mqtt_connected = True
        self.published_messages = []

        # Interceptar todas las publicaciones MQTT
        def mock_pub(topic, payload, qos=0, retain=False):
            self.published_messages.append({
                "topic": topic,
                "payload": json.loads(payload) if isinstance(payload, str) and payload.startswith("{") else payload,
                "qos": qos,
                "retain": retain
            })

        self.bridge.mqtt_client.publish = mock_pub

        # Simular hardware MeshCore
        self.bridge.mc = MagicMock()
        self.bridge.mc.self_info = {
            "name": "Heltec_Router_E2E",
            "radio_freq": 915.0,
            "tx_power": 22,
            "public_key": "feedfacecafe0001"
        }
        self.bridge.mc.contacts = [
            MockContact("Nodo_Remoto_1", "aabbccdd11223344")
        ]
        self.bridge.mc.commands = MagicMock()
        self.bridge.mc.commands.send_chan_msg = AsyncMock()
        self.bridge.mc.commands.send_msg = AsyncMock()
        self.bridge.mc.commands.set_name = AsyncMock()
        self.bridge.mc.commands.set_tx_power = AsyncMock()

    def tearDown(self):
        self.loop.close()

    def test_complete_e2e_lifecycle(self):
        """Ejecuta un ciclo E2E completo: RX público, RX DM, Telemetría, TX n8n, Admin y Shutdown."""
        async def run_e2e():
            # ============================================================
            # Paso 1: Recepción de mensaje en Canal Público (/time)
            # ============================================================
            rx_pub_event = MockEvent("CHANNEL_MSG_RECV", {
                "channel_idx": 0,
                "sender": "aabbccdd11223344",
                "sender_name": "Nodo_Remoto_1",
                "text": "/time",
                "rssi": -82,
                "snr": 10.5,
                "hop_count": 1
            })
            self.bridge.on_mesh_event(rx_pub_event)

            # Validar que se publicó en meshcore/rx/public y meshcore/rx/all
            pub_topics = [m["topic"] for m in self.published_messages]
            self.assertIn("meshcore/rx/public", pub_topics)
            self.assertIn("meshcore/rx/all", pub_topics)

            rx_all_msg = next(m for m in self.published_messages if m["topic"] == "meshcore/rx/all")
            self.assertEqual(rx_all_msg["payload"]["event_type"], "public")
            self.assertEqual(rx_all_msg["payload"]["sender_name"], "Nodo_Remoto_1")
            self.assertEqual(rx_all_msg["payload"]["text"], "/time")
            self.assertEqual(rx_all_msg["payload"]["metrics"]["rssi"], -82)

            # ============================================================
            # Paso 2: n8n responde con TX hacia meshcore/tx
            # ============================================================
            tx_req = {
                "request_id": "n8n_flow_time_resp_001",
                "to": "broadcast",
                "channel_index": 0,
                "text": "⏰ Hora actual: 14:55:00 UTC"
            }
            await self.bridge._execute_tx(tx_req)

            # Validar que MeshCore commands fue llamado y se publicó ACK
            self.bridge.mc.commands.send_chan_msg.assert_called_with(0, "⏰ Hora actual: 14:55:00 UTC")
            ack_msg = next(m for m in self.published_messages if m["topic"] == "meshcore/tx/status")
            self.assertEqual(ack_msg["payload"]["request_id"], "n8n_flow_time_resp_001")
            self.assertEqual(ack_msg["payload"]["status"], "sent")

            # ============================================================
            # Paso 3: Recepción de Mensaje Directo (DM /status)
            # ============================================================
            rx_dm_event = MockEvent("DIRECT_MSG_RECV", {
                "pubkey_prefix": "aabbccdd11223344",
                "sender_name": "Nodo_Remoto_1",
                "text": "/status",
                "rssi": -78,
                "snr": 11.2
            })
            self.bridge.on_mesh_event(rx_dm_event)

            dm_topics = [m["topic"] for m in self.published_messages]
            self.assertIn("meshcore/rx/direct/aabbccdd11223344", dm_topics)

            # ============================================================
            # Paso 4: Recepción de Telemetría (Batería de Nodo)
            # ============================================================
            rx_telem_event = MockEvent("TELEMETRY_RECV", {
                "node_id": "aabbccdd11223344",
                "battery": 88,
                "voltage": 4.05,
                "rssi": -80,
                "snr": 9.0
            })
            self.bridge.on_mesh_event(rx_telem_event)
            self.assertIn("meshcore/rx/telemetry", [m["topic"] for m in self.published_messages])

            # ============================================================
            # Paso 5: Comando Administrativo desde n8n (/admin get_config)
            # ============================================================
            admin_req = {
                "request_id": "n8n_adm_req_55",
                "action": "get_config"
            }
            await self.bridge.handle_admin(admin_req)

            admin_status_msg = next(m for m in self.published_messages if m["topic"] == "meshcore/admin/status")
            self.assertEqual(admin_status_msg["payload"]["request_id"], "n8n_adm_req_55")
            self.assertEqual(admin_status_msg["payload"]["config"]["name"], "Heltec_Router_E2E")
            self.assertEqual(admin_status_msg["payload"]["config"]["radio_freq"], 915.0)

            # ============================================================
            # Paso 6: Apagado Limpio (Shutdown)
            # ============================================================
            await self.bridge.shutdown()
            self.assertFalse(self.bridge.running)
            state_msg = next(m for m in self.published_messages if m["topic"] == "meshcore/bridge/state" and m["payload"].get("status") == "offline")
            self.assertIsNotNone(state_msg)

        self.loop.run_until_complete(run_e2e())


if __name__ == "__main__":
    unittest.main()

"""
Automated Integration & Simulation Tests for VirtualMeshAdapter.
Verifica la interacción completa con los nodos virtuales Alpha y Bravo,
el bot de auto-eco, telemetría y sniffer.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter


class TestVirtualMeshSimulation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Instanciar bridge con base temporal
        self.bridge = MeshCoreBridge(db_path=self.db_path)
        # Reemplazar adaptador serial por el VirtualMeshAdapter
        self.v_adapter = VirtualMeshAdapter(event_callback=self.bridge.on_mesh_event)
        self.bridge.serial_adapter = self.v_adapter

        # Mock de cliente MQTT para capturar publicaciones
        self.published_events: list[tuple[str, str]] = []
        self.bridge.mqtt.publish_safe = MagicMock(
            side_effect=lambda topic, payload, qos=0, retain=False: self.published_events.append((topic, payload))
        )

        await self.v_adapter.connect()

    async def asyncTearDown(self) -> None:
        await self.v_adapter.disconnect()
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    async def test_initial_node_discovery(self) -> None:
        """Comprueba que los nodos Alpha y Bravo sean descubiertos automáticamente."""
        nodes = self.bridge.node_registry.list_nodes()
        keys = [n["public_key"] for n in nodes]
        self.assertIn("a1b2c3d4e5f6", keys)
        self.assertIn("d7e8f9012345", keys)

    async def test_alpha_echo_response_on_dm(self) -> None:
        """Comprueba que enviar un mensaje privado a Alpha dispare una respuesta Echo."""
        # Enviar mensaje a Alpha
        tx_item = {
            "to": "a1b2c3d4e5f6",
            "channel_index": 0,
            "text": "Hola Alpha Prueba 123",
            "request_id": "test_req_1",
        }
        res = await self.bridge._execute_tx(tx_item)
        self.assertTrue(res)

        # Esperar a que el bot de eco procese la trama (latencia de 800ms)
        await asyncio.sleep(1.0)

        # Buscar el mensaje de eco en las publicaciones MQTT o mensajes recientes del web router
        recent = list(self.bridge.web_server.router.recent_messages) if self.bridge.web_server else []
        echo_found = any("Echo de Alpha Field Sensor" in m.get("text", "") for m in recent)
        if not echo_found:
            # Buscar en published_events
            echo_found = any("Echo de Alpha Field Sensor" in p[1] for p in self.published_events)

        self.assertTrue(echo_found, "No se recibió la respuesta de eco de Alpha Field Sensor")

    async def test_bravo_echo_response_on_dm(self) -> None:
        """Comprueba que enviar un mensaje privado a Bravo dispare una respuesta Echo."""
        tx_item = {
            "to": "d7e8f9012345",
            "channel_index": 0,
            "text": "Status check rover",
            "request_id": "test_req_2",
        }
        res = await self.bridge._execute_tx(tx_item)
        self.assertTrue(res)

        await asyncio.sleep(1.0)

        recent = list(self.bridge.web_server.router.recent_messages) if self.bridge.web_server else []
        echo_found = any("Echo de Bravo Scout Rover" in m.get("text", "") for m in recent)
        if not echo_found:
            echo_found = any("Echo de Bravo Scout Rover" in p[1] for p in self.published_events)

        self.assertTrue(echo_found, "No se recibió la respuesta de eco de Bravo Scout Rover")


if __name__ == "__main__":
    unittest.main()

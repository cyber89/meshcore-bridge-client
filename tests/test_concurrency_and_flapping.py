"""
Pruebas de Concurrencia Extrema, Flapping de Red y Fallas en Caliente para MeshCore Bridge.
Verifica la estabilidad del motor WAL de SQLite con escrituras multihilo concurrentes,
caídas de conexión intermitentes a mitad de vaciado y excepciones de hardware.
"""

import asyncio
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock

from meshcore_bridge import MeshCoreBridge, SQLiteStoreAndForward


class TestConcurrencyAndFlapping(unittest.TestCase):
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

        self.mock_mc = MagicMock()
        self.mock_mc.commands = MagicMock()
        self.mock_mc.commands.send_chan_msg = AsyncMock(return_value=MagicMock(type=MagicMock(name="SENT")))
        self.mock_mc.contacts = []
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

    def _run(self, coro):
        """Ejecuta una corrutina en el bucle de eventos dedicado del test."""
        return self.loop.run_until_complete(coro)

    def test_concurrent_sqlite_writes_multithreaded(self):
        """Prueba 10 hilos concurrentes insertando 50 mensajes cada uno en SQLite (500 total)."""
        buffer = SQLiteStoreAndForward(db_path=self.temp_db_path, max_size=1000)
        num_threads = 10
        msgs_per_thread = 50

        def worker(thread_idx):
            for i in range(msgs_per_thread):
                asyncio.run(buffer.enqueue("meshcore/rx/all", f'{{"thread": {thread_idx}, "msg": {i}}}', qos=0))

        threads = []
        for t in range(num_threads):
            th = threading.Thread(target=worker, args=(t,))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        self.assertEqual(self._run(buffer.count()), num_threads * msgs_per_thread, "Todos los 500 mensajes deben estar en SQLite sin bloqueos")

    def test_mqtt_connection_flapping_during_traffic(self):
        """Simula 10 micro-cortes y reconexiones de MQTT mientras llegan mensajes continuos."""
        total_messages = 50
        for i in range(total_messages):
            # Alternar estado de conexión cada 5 mensajes
            if i % 5 == 0:
                self.bridge.on_mqtt_disconnect(self.bridge.mqtt_client, None, rc=1)
            elif i % 5 == 2:
                self.bridge.on_mqtt_connect(self.bridge.mqtt_client, None, flags=0, rc=0)

            self.bridge.publish_mqtt_safe("meshcore/rx/all", f'{{"seq": {i}}}', qos=0)

        # Forzar reconexión final y vaciado completo
        self.bridge.on_mqtt_connect(self.bridge.mqtt_client, None, flags=0, rc=0)

        self.assertEqual(self._run(self.bridge.sqlite_buffer.count()), 0, "El buffer SQLite debe quedar completamente vacío")

        # Filtrar solo los mensajes recibidos en el tópico de datos
        rx_messages = [p for t, p in self.published if t == "meshcore/rx/all"]
        self.assertEqual(len(rx_messages), total_messages, f"Deben haberse entregado exactamente los {total_messages} mensajes")

    def test_mid_flush_mqtt_disconnect(self):
        """Simula una desconexión de MQTT a mitad de un vaciado por lotes."""
        # 1. Inyectar 20 mensajes con MQTT desconectado
        self.bridge.mqtt_connected = False
        for i in range(20):
            self._run(self.bridge.sqlite_buffer.enqueue("meshcore/rx/all", f'{{"item": {i}}}', qos=0))

        self.assertEqual(self._run(self.bridge.sqlite_buffer.count()), 20)

        # 2. Configurar el mock para que en el mensaje 5 MQTT falle
        publish_count = 0
        def failing_publish(t, p, qos=0, retain=False):
            nonlocal publish_count
            publish_count += 1
            if publish_count == 5:
                # Simular corte de red a mitad del bucle
                self.bridge.mqtt_connected = False
                raise ConnectionResetError("Broker MQTT cerró conexión")
            self.published.append((t, p))

        self.bridge.mqtt_client.publish.side_effect = failing_publish
        self.bridge.mqtt_connected = True

        # Ejecutar vaciado (se cortará en el mensaje 5)
        self._run(self.bridge._flush_offline_buffer())

        # Comprobar que los mensajes restantes siguen a salvo en SQLite
        remaining = self._run(self.bridge.sqlite_buffer.count())
        self.assertTrue(remaining > 0, "Los mensajes no entregados deben permanecer en SQLite")

        # 3. Restaurar conexión limpia y terminar el vaciado
        self.bridge.mqtt_client.publish.side_effect = lambda t, p, qos=0, retain=False: self.published.append((t, p))
        self.bridge.mqtt_connected = True
        self._run(self.bridge._flush_offline_buffer())

        self.assertEqual(self._run(self.bridge.sqlite_buffer.count()), 0, "Tras reconectar, la base de datos debe quedar vacía")

    def test_serial_exception_during_active_tx(self):
        """Verifica que una falla de hardware en el puerto USB durante TX no congele el worker."""
        self.mock_mc.commands.send_chan_msg = AsyncMock(side_effect=OSError("USB Device Disconnected"))

        tx_data = {
            "request_id": "test_crash_safe",
            "to": "broadcast",
            "channel_index": 0,
            "text": "Mensaje en puerto fallido"
        }

        # Ejecutar TX (debe manejar la excepción limpiamente)
        self.loop.run_until_complete(self.bridge._execute_tx(tx_data))
        self.assertEqual(self.bridge.tx_error_count, 1)

        # El worker debe continuar operativo
        status_publishes = [p for t, p in self.published if t == "meshcore/tx/status"]
        self.assertTrue(len(status_publishes) > 0)
        status_data = json.loads(status_publishes[-1])
        self.assertEqual(status_data["status"], "error")
        self.assertTrue("USB Device Disconnected" in status_data.get("error", ""))


if __name__ == "__main__":
    unittest.main()

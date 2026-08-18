"""
Pruebas Unitarias para el mecanismo Store-and-Forward Persistente en SQLite.
Verifica que los mensajes se guarden en base de datos SQLite durante caídas de MQTT,
sobrevivan a reinicios del proceso y se entreguen en orden FIFO estricto.
"""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from meshcore_bridge import MeshCoreBridge, SQLiteStoreAndForward, StoredMessage


class TestStoreAndForward(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        self.bridge = MeshCoreBridge(self.loop, db_path=self.temp_db_path)
        self.bridge.mqtt_client = MagicMock()

    def _run(self, coro):
        """Ejecuta una corrutina en el bucle de eventos dedicado del test."""
        return self.loop.run_until_complete(coro)

    def tearDown(self):
        self.loop.close()
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
            # Eliminar archivos auxiliares WAL y SHM si existen
            for ext in ["-wal", "-shm"]:
                wal_file = self.temp_db_path + ext
                if os.path.exists(wal_file):
                    os.remove(wal_file)
        except Exception:
            pass

    def test_sqlite_offline_buffering_and_flushing(self):
        """Simula caída de MQTT, encolado en SQLite y reenvío ordenado tras reconexión."""
        self.bridge.mqtt_connected = False
        published_messages = []

        self.bridge.mqtt_client.publish.side_effect = lambda t, p, qos=0, retain=False: published_messages.append((t, p))

        # 1. Inyectar 10 mensajes mientras MQTT está offline
        for i in range(10):
            payload = json.dumps({"msg_num": i, "text": f"Mensaje persistente {i}"})
            self.bridge.publish_mqtt_safe("meshcore/rx/all", payload, qos=0)

        # 2. Comprobar que los mensajes están en la base de datos SQLite
        self.assertEqual(len(published_messages), 0, "No debe publicar mientras MQTT esté offline")
        self.assertEqual(self._run(self.bridge.sqlite_buffer.count()), 10, "Los 10 mensajes deben estar guardados en SQLite")

        # 3. Simular reconexión a MQTT y vaciado
        self.bridge.mqtt_connected = True
        self._run(self.bridge._flush_offline_buffer())

        # 4. Comprobar que la base de datos quedó vacía y todos se publicaron en orden FIFO
        self.assertEqual(self._run(self.bridge.sqlite_buffer.count()), 0, "La DB SQLite debe quedar vacía tras el vaciado")
        self.assertEqual(len(published_messages), 10, "Los 10 mensajes deben haber sido publicados a MQTT")

        for i, (topic, payload_str) in enumerate(published_messages):
            self.assertEqual(topic, "meshcore/rx/all")
            data = json.loads(payload_str)
            self.assertEqual(data["msg_num"], i, f"El mensaje {i} debe mantener el orden FIFO estricto")

    def test_sqlite_persistence_across_process_restart(self):
        """Verifica que los mensajes encolados en SQLite sobrevivan a un reinicio/apagado del servicio."""
        # 1. Guardar 5 mensajes con el bridge 1 (offline)
        self.bridge.mqtt_connected = False
        for i in range(5):
            self.bridge.publish_mqtt_safe("meshcore/rx/all", f'{{"reboot_test": {i}}}', qos=0)

        self.assertEqual(self._run(self.bridge.sqlite_buffer.count()), 5)

        # 2. Destruir la instancia actual y crear una NUEVA instancia con la misma BD (simula reinicio)
        new_bridge = MeshCoreBridge(self.loop, db_path=self.temp_db_path)
        new_published = []
        new_bridge.mqtt_client.publish = MagicMock(side_effect=lambda t, p, qos=0, retain=False: new_published.append((t, p)))

        # 3. Verificar que los 5 mensajes siguen en disco en la nueva instancia
        self.assertEqual(self._run(new_bridge.sqlite_buffer.count()), 5, "Los mensajes deben persistir tras el reinicio")

        # 4. Conectar MQTT en la nueva instancia y vaciar
        new_bridge.mqtt_connected = True
        self._run(new_bridge._flush_offline_buffer())

        self.assertEqual(len(new_published), 5, "Todos los mensajes persistidos deben publicarse al reiniciar")
        self.assertEqual(self._run(new_bridge.sqlite_buffer.count()), 0)

    def test_sqlite_buffer_capacity_limit(self):
        """Verifica que SQLite respete el límite máximo acotado (FIFO) sin crecimiento infinito."""
        db_handler = SQLiteStoreAndForward(db_path=self.temp_db_path, max_size=30)

        for i in range(100):
            self._run(db_handler.enqueue(StoredMessage("meshcore/rx/all", f'{{"count": {i}}}', qos=0)))

        self.assertEqual(self._run(db_handler.count()), 30, "La tabla SQLite debe recortarse al tamaño máximo (30)")

        # El lote debe comenzar desde el elemento 70 (los primeros 70 fueron descartados en rotación FIFO)
        batch = self._run(db_handler.dequeue_batch(limit=1))
        first_payload = json.loads(batch[0][2])
        self.assertEqual(first_payload["count"], 70)


if __name__ == "__main__":
    unittest.main()

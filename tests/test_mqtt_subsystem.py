"""
Unit tests for AsyncBridgeMQTTClient and MqttInboundDispatcher.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.mqtt_dispatcher import MqttInboundContext, MqttInboundDispatcher
from src.rate_limiter import TxPriority, TxRateLimiter


class TestMqttSubsystem(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mock_paho = MagicMock()
        self.config = MQTTConfig(
            broker="192.168.1.50",
            port=1883,
            username="test_user",
            password="test_password",
            topic_prefix="meshcore_test",
        )
        with patch("src.mqtt_client.mqtt.Client", return_value=self.mock_paho):
            self.client = AsyncBridgeMQTTClient(config=self.config)

    def test_mqtt_config_and_topic_generation(self) -> None:
        """Verifica la generación de tópicos MQTT y configuración."""
        self.assertEqual(self.client.topic_state, "meshcore_test/bridge/state")
        self.assertEqual(self.client.topic_health, "meshcore_test/bridge/health")
        self.assertEqual(self.client.topic_tx, "meshcore_test/tx")
        self.assertEqual(self.client.topic_tx_status, "meshcore_test/tx/status")
        self.assertEqual(self.client.topic_admin_cmd, "meshcore_test/admin/cmd")
        self.assertEqual(self.client.topic_admin_stat, "meshcore_test/admin/status")

        cfg = MQTTConfig(broker="localhost", port=1884, topic_prefix="test_mesh")
        self.assertEqual(cfg.broker, "localhost")
        self.assertEqual(cfg.port, 1884)
        self.assertEqual(cfg.topic_prefix, "test_mesh")

    async def test_client_start_and_stop(self) -> None:
        """Verifica la configuración de credenciales, LWT e inicio/parada del bucle de red."""
        self.mock_paho.username_pw_set.assert_called_once_with("test_user", "test_password")
        self.mock_paho.will_set.assert_called_once()
        will_args = self.mock_paho.will_set.call_args[0]
        self.assertEqual(will_args[0], "meshcore_test/bridge/state")
        self.assertIn('"status": "offline"', will_args[1])

        loop = asyncio.get_running_loop()
        self.client.start(loop)

        self.mock_paho.connect_async.assert_called_once_with("192.168.1.50", 1883, 60)
        self.mock_paho.loop_start.assert_called_once()

        # Simular callback _on_connect
        self.client._on_connect(self.mock_paho, None, None, 0)
        self.assertTrue(self.client.is_connected)
        self.mock_paho.subscribe.assert_called_once()

        # Detener cliente
        self.client.stop()
        self.mock_paho.loop_stop.assert_called_once()
        self.mock_paho.disconnect.assert_called_once()
        self.assertFalse(self.client.is_connected)

    def test_publish_safe_validation(self) -> None:
        """Verifica la publicación con control de conexión y límites de tamaño."""
        # Desconectado no debe publicar
        self.client.is_connected = False
        res = self.client.publish_safe("meshcore_test/test", "payload")
        self.assertFalse(res)

        # Conectado debe publicar correctamente
        self.client.is_connected = True
        res_ok = self.client.publish_safe("meshcore_test/test", "payload_ok", qos=1, retain=False)
        self.assertTrue(res_ok)
        self.mock_paho.publish.assert_called_with("meshcore_test/test", "payload_ok", qos=1, retain=False)
        self.assertEqual(self.client.total_published, 1)

    async def test_inbound_dispatcher_tx_message(self) -> None:
        """Verifica el despacho de comandos TX desde MQTT hacia el TxRateLimiter."""
        loop = asyncio.get_running_loop()
        background_tasks: set[asyncio.Task[Any]] = set()

        fut = loop.create_future()
        fut.set_result({"status": "sent"})

        mock_rate_limiter = MagicMock(spec=TxRateLimiter)
        mock_rate_limiter.submit = AsyncMock(return_value=fut)
        mock_rate_limiter.get_queue_depth = MagicMock(return_value=0)

        mock_admin = AsyncMock()

        ctx = MqttInboundContext(
            loop=loop,
            background_tasks=background_tasks,
            mqtt=self.client,
            rate_limiter=mock_rate_limiter,
            handle_admin=mock_admin,
        )
        dispatcher = MqttInboundDispatcher(ctx)

        # Enviar petición TX por el tópico TX con prioridad 0 (HIGH)
        tx_payload = json.dumps({
            "text": "Comando LoRa desde n8n",
            "target": "feedface0001",
            "priority": 0,
            "channel_idx": 1,
        })
        dispatcher.handle_incoming(self.client.topic_tx, tx_payload)

        # Esperar a que la tarea asíncrona termine
        await asyncio.sleep(0.1)

        mock_rate_limiter.submit.assert_awaited_once()
        call_kwargs = mock_rate_limiter.submit.call_args.kwargs
        self.assertEqual(call_kwargs["payload"], "Comando LoRa desde n8n")
        self.assertEqual(call_kwargs["target"], "feedface0001")
        self.assertEqual(call_kwargs["priority"], TxPriority.HIGH)
        self.assertEqual(call_kwargs["channel_idx"], 1)

    async def test_inbound_dispatcher_admin_command(self) -> None:
        """Verifica el despacho de comandos administrativos hacia el handle_admin."""
        loop = asyncio.get_running_loop()
        background_tasks: set[asyncio.Task[Any]] = set()

        mock_rate_limiter = MagicMock()
        mock_admin = AsyncMock(return_value={"status": "ok", "action": "reboot_done"})

        ctx = MqttInboundContext(
            loop=loop,
            background_tasks=background_tasks,
            mqtt=self.client,
            rate_limiter=mock_rate_limiter,
            handle_admin=mock_admin,
        )
        dispatcher = MqttInboundDispatcher(ctx)

        admin_payload = json.dumps({
            "action": "reboot",
            "target_node": "local",
        })
        dispatcher.handle_incoming(self.client.topic_admin_cmd, admin_payload)

        await asyncio.sleep(0.1)

        mock_admin.assert_awaited_once_with({"action": "reboot", "target_node": "local"})

    async def test_inbound_dispatcher_malformed_json(self) -> None:
        """Verifica que payloads malformados no provoquen excepciones no controladas."""
        loop = asyncio.get_running_loop()
        background_tasks: set[asyncio.Task[Any]] = set()

        ctx = MqttInboundContext(
            loop=loop,
            background_tasks=background_tasks,
            mqtt=self.client,
            rate_limiter=MagicMock(),
            handle_admin=AsyncMock(),
        )
        dispatcher = MqttInboundDispatcher(ctx)

        # Enviar JSON corrupto
        dispatcher.handle_incoming(self.client.topic_tx, "ESTO NO ES UN JSON {}}")
        await asyncio.sleep(0.05)
        # Debe manejar el error limpiamente sin lanzar excepciones
        self.assertEqual(len(background_tasks), 0)


if __name__ == "__main__":
    unittest.main()

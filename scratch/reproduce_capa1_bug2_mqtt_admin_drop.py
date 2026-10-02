import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from unittest.mock import MagicMock, AsyncMock
import config
from src.mqtt_dispatcher import MqttInboundDispatcher, MqttInboundContext
from src.admin_handler import AdminCommandHandler, AdminContext

async def test_mqtt_admin_drop_reproduction():
    print("=== REPRODUCING BUG 2: MQTT Admin Commands drop responses for get_custom_vars / path_hash / autoadd / flood ===")
    
    published_messages = []
    
    mock_mqtt = MagicMock()
    mock_mqtt.topic_tx = config.TOPIC_TX
    mock_mqtt.topic_admin_cmd = config.TOPIC_ADMIN_CMD
    mock_mqtt.topic_admin_status = config.TOPIC_ADMIN_STAT
    
    def fake_publish_safe(topic, payload, qos=0, retain=False):
        published_messages.append((topic, payload))
        return True
        
    mock_mqtt.publish_safe.side_effect = fake_publish_safe
    
    # Mock AdminContext
    mock_node_registry = MagicMock()
    mock_node_registry.is_local_key.return_value = False
    mock_node_registry.list_nodes.return_value = []
    
    mock_mc = MagicMock()
    
    admin_ctx = AdminContext(
        mc_provider=lambda: mock_mc,
        node_registry=mock_node_registry,
        repeater_manager=MagicMock(),
        mqtt=mock_mqtt,
        execute_tx=AsyncMock(),
    )
    admin_handler = AdminCommandHandler(admin_ctx)
    
    # Mock get_custom_vars to return some sample dict
    admin_handler.get_custom_vars = AsyncMock(return_value={"test_var": "123"})
    
    # Create MqttInboundDispatcher
    background_tasks = set()
    dispatcher_ctx = MqttInboundContext(
        loop=asyncio.get_running_loop(),
        background_tasks=background_tasks,
        mqtt=mock_mqtt,
        rate_limiter=MagicMock(),
        handle_admin=admin_handler.handle,
        register_task=background_tasks.add,
    )
    dispatcher = MqttInboundDispatcher(dispatcher_ctx)
    
    # Case A: list_nodes (This works because list_nodes explicitly publishes in admin_handler)
    print("\n--- Submitting command: list_nodes ---")
    published_messages.clear()
    dispatcher.handle_incoming(config.TOPIC_ADMIN_CMD, '{"action": "list_nodes"}')
    await asyncio.gather(*list(background_tasks), return_exceptions=True)
    background_tasks.clear()
    
    print(f"Messages published for list_nodes: {len(published_messages)}")
    for t, p in published_messages:
        print(f"  -> Topic: {t}, Payload: {p}")
    assert len(published_messages) == 1, "list_nodes should have published to TOPIC_ADMIN_STAT"
    
    # Case B: get_custom_vars (BUG: This drops the response!)
    print("\n--- Submitting command: get_custom_vars ---")
    published_messages.clear()
    dispatcher.handle_incoming(config.TOPIC_ADMIN_CMD, '{"action": "get_custom_vars"}')
    await asyncio.gather(*list(background_tasks), return_exceptions=True)
    background_tasks.clear()
    
    print(f"Messages published for get_custom_vars: {len(published_messages)}")
    if len(published_messages) == 0:
        print("\n[REPRODUCTION CONFIRMED] BUG IDENTIFIED: 'get_custom_vars' completed, but published 0 messages to MQTT!")
        print("Root cause: admin_handler.py returns 'res' without publishing to TOPIC_ADMIN_STAT, and mqtt_dispatcher._handle_admin_request drops the return value of handle_admin().")
        print("Contract violation: MQTT client sent a command to meshcore/admin/cmd expecting response on meshcore/admin/status, but no response was ever emitted.")
    else:
        for t, p in published_messages:
            print(f"  -> Topic: {t}, Payload: {p}")

if __name__ == "__main__":
    asyncio.run(test_mqtt_admin_drop_reproduction())

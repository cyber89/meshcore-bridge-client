import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from unittest.mock import MagicMock
from src.contact_manager import NodeRegistry
from src.repeater_manager import RepeaterManager
from src.deduplicator import PacketDeduplicator
from src.rx_router import RxEventRouter, RxRouterContext

class DummyCounters:
    rx_count = 0
    tx_count = 0
    tx_error_count = 0
    err_count = 0

async def test_dedup_bypass_reproduction():
    print("=== REPRODUCING BUG C2-01: Deduplication Bypass for Standard Mesh Events in RxEventRouter ===")

    bg_tasks = set()
    reg = NodeRegistry()
    rep = RepeaterManager()
    dedup = PacketDeduplicator(window_seconds=60.0)
    mock_mqtt = MagicMock()
    mock_serial = MagicMock()
    mock_serial.resolve_sender_name.return_value = "SenderNode"

    ctx = RxRouterContext(
        mqtt=mock_mqtt,
        node_registry=reg,
        serial_adapter=mock_serial,
        deduplicator=dedup,
        repeater_manager=rep,
        web_server=None,
        loop=asyncio.get_running_loop(),
        background_tasks=bg_tasks,
        counters=DummyCounters(),
        packet_buffer=None,
        bridge=None,
        register_task=bg_tasks.add,
    )
    router = RxEventRouter(ctx)

    sender_pk = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
    event = {
        "type": "CHANNEL_MSG_RECV",
        "channel_idx": 0,
        "sender": sender_pk,
        "text": "Flood mesh test message",
        "rssi": -80,
        "snr": 9.0,
    }

    # First event received
    print("\n[Step 1] Feeding incoming mesh channel message...")
    router.handle_event(event)
    await asyncio.gather(*list(bg_tasks))
    bg_tasks.clear()

    count_1 = mock_mqtt.publish_safe.call_count
    print(f"MQTT publish calls after 1st event: {count_1} (published to rx/all and rx/public)")
    print(f"Deduplicator cache entries: {len(dedup)}")

    # Second identical event received 100ms later (repeated by a LoRa repeater)
    print("\n[Step 2] Feeding identical mesh channel message 100ms later (simulated multi-hop flood)...")
    event_repeat = dict(event)
    event_repeat["rssi"] = -83  # slightly different RF metric as it bounced off another repeater
    event_repeat["snr"] = 8.5
    router.handle_event(event_repeat)
    await asyncio.gather(*list(bg_tasks))
    bg_tasks.clear()

    count_2 = mock_mqtt.publish_safe.call_count
    print(f"Total MQTT publish calls after 2nd event: {count_2}")
    print(f"Deduplicator cache entries: {len(dedup)}")

    # Verification
    if count_2 > count_1 and len(dedup) == 0:
        print(f"\n[REPRODUCTION CONFIRMED] BUG IDENTIFIED: Both identical packets were fully processed ({count_1} -> {count_2} MQTT publishes)!")
        print("Root cause: RxEventRouter only calls deduplicator.is_duplicate() in _dispatch_parsed_frame(MeshcoreFrame).")
        print("Standard companion SDK events completely bypass deduplication, causing duplicate MQTT publications, redundant database writes and duplicate WebSocket events during mesh flooding.")
    else:
        print(f"[UNEXPECTED] Count after second: {count_2}, Dedup size: {len(dedup)}")

if __name__ == "__main__":
    asyncio.run(test_dedup_bypass_reproduction())

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from unittest.mock import MagicMock
from src.bridge_core import MeshCoreBridge
from src.rate_limiter import TxPriority

async def test_tcp_companion_unbounded_future_reproduction():
    print("=== REPRODUCING BUG C2-02: Unbounded 'await future' in handle_tcp_companion_command ===")

    # Create dummy bridge instance
    mock_bridge = MagicMock(spec=MeshCoreBridge)
    mock_rate_limiter = MagicMock()
    mock_bridge.rate_limiter = mock_rate_limiter

    # A future that simulates an unresolved/delayed transmission (e.g. rate limiter paused or high queue)
    unresolved_future = asyncio.get_running_loop().create_future()
    # submit is an async def in RateLimiter, so it returns a coroutine returning future
    async def fake_submit(*args, **kwargs):
        return unresolved_future
    mock_rate_limiter.submit.side_effect = fake_submit

    # Companion binary payload representing a channel message:
    # payload[0] = 3 (Channel message), payload[1] = 0 (attempt), payload[2] = 0 (channel), payload[3:7] = timestamp, payload[7:] = text
    payload = bytes([3, 0, 0, 0x01, 0x02, 0x03, 0x04]) + b"Hello from Companion TCP"

    real_handle = MeshCoreBridge.handle_tcp_companion_command

    print("\n[Step 1] Invoking handle_tcp_companion_command with unresolved future...")
    task = asyncio.create_task(real_handle(mock_bridge, payload, MagicMock(), timeout=0.2))

    # Wait 0.5s to see if it times out cleanly without hanging indefinitely
    done, pending = await asyncio.wait([task], timeout=0.5)

    if task in done and task.result() is False:
        print("[SUCCESS] handle_tcp_companion_command timed out safely and returned False without freezing!")
    else:
        print(f"[FAIL] Task did not time out as expected: done={task in done}")

if __name__ == "__main__":
    asyncio.run(test_tcp_companion_unbounded_future_reproduction())

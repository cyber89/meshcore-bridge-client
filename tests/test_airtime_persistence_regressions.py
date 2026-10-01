"""Disk writes must leave the event loop and shutdown must flush the last snapshot."""

import asyncio
import json
import threading
from unittest.mock import AsyncMock

from src.rate_limiter import AirtimeTracker, TxRateLimiter


async def test_airtime_persistence_runs_outside_event_loop(tmp_path, monkeypatch):
    import src.rate_limiter as module

    threads = []
    original = module.os.replace

    def replace(source, destination):
        threads.append(threading.get_ident())
        original(source, destination)

    monkeypatch.setattr(module.os, "replace", replace)
    path = tmp_path / "history.json"
    tracker = AirtimeTracker(history_file=str(path))
    tracker.record_tx(12, target="remote")
    assert threads == []
    await tracker.flush_history()
    assert threads and threading.get_ident() not in threads
    assert json.loads(path.read_text())["records"][0]["airtime_ms"] == 12


async def test_stop_flushes_latest_airtime_snapshot(tmp_path):
    path = tmp_path / "history.json"
    limiter = TxRateLimiter(history_file=str(path))
    limiter.airtime_tracker.record_tx(12)
    await asyncio.sleep(0)
    limiter.airtime_tracker.record_tx(15)
    await limiter.stop()
    assert json.loads(path.read_text())["total_packets"] == 2
    assert len(json.loads(path.read_text())["records"]) == 2


async def test_cancelled_queued_request_is_not_transmitted():
    transmit = AsyncMock(return_value={"status": "sent"})
    limiter = TxRateLimiter(tx_interval_sec=0, transmit_callback=transmit)
    future = await limiter.submit("cancelled")
    future.cancel()
    try:
        limiter.start()
        await asyncio.wait_for(limiter.queue.join(), 1)
        transmit.assert_not_awaited()
        assert limiter.airtime_tracker.total_packets == 0
    finally:
        await limiter.stop()

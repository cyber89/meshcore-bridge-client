"""History access/import regressions; no operational station or radio fixtures."""

from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.station_database import StationDatabase
from src.web.access_policy import requires_api_auth
from src.web.controllers.base import ApiContext
from src.web.controllers.history_controller import HistoryController


@pytest.mark.asyncio
async def test_history_import_is_durable_and_does_not_transmit(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    bridge = SimpleNamespace(database=database)  # No radio or transmission queue exists.
    controller = HistoryController(ApiContext(bridge, deque(), deque(), lambda *args, **kwargs: None))
    message = {"text": "old browser message", "feed_key": "ch_0", "timestamp": "2026-10-10T12:00:00Z"}
    code, imported = await controller.handle("POST", "/api/messages/import", {"messages": [message]})
    assert code == 200
    code, result = await controller.handle("GET", "/api/messages/history", {"feed_key": "ch_0"})
    assert code == 200
    assert result["data"]["messages"][0]["text"] == message["text"]
    assert result["data"]["station_id"] == imported["data"]["station_id"]
    reopened = StationDatabase(database.path)
    reopened.initialize()
    assert len(reopened.history("ch_0")["messages"]) == 1


@pytest.mark.asyncio
async def test_invalid_batch_cannot_partially_import(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    controller = HistoryController(ApiContext(SimpleNamespace(database=database), deque(), deque(), lambda *args, **kwargs: None))
    code, _ = await controller.handle("POST", "/api/messages/import", {"messages": [{"text": "ok", "feed_key": "ch_0"}, 3]})
    assert code == 422
    assert not database.history()["messages"]


@pytest.mark.parametrize("path", ["/api/messages/history", "/api/messages/conversations", "/api/messages/recent"])
def test_history_reads_are_guarded(path: str) -> None:
    assert requires_api_auth("GET", path)

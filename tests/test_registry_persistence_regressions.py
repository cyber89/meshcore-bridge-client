"""Concurrent updates must remain dirty until their snapshot reaches disk."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from src.contact_manager import NodeContactUpdate, NodeRegistry

KEY = "ab" * 32


@pytest.mark.asyncio
async def test_update_during_atomic_replace_is_not_marked_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = NodeRegistry()
    registry.add_or_update(KEY, NodeContactUpdate(name="Before", role="CLIENT"))
    destination = tmp_path / "nodes.json"
    entered = threading.Event()
    release = threading.Event()
    original = Path.replace

    def pause_replace(path: Path, target: Path) -> Path:
        if target == destination and not entered.is_set():
            entered.set()
            assert release.wait(5), "Writer was not released"
        return original(path, target)

    monkeypatch.setattr(Path, "replace", pause_replace)
    save = asyncio.create_task(registry.save_to_file_async(destination))
    try:
        assert await asyncio.to_thread(entered.wait, 5), "Writer did not reach atomic replace"
        # Executes on the event loop while filesystem work is paused in a thread.
        registry.add_or_update(KEY, NodeContactUpdate(name="After"))
    finally:
        release.set()
        await save
    assert json.loads(destination.read_text(encoding="utf-8"))["nodes"][0]["name"] == "Before"
    assert registry._dirty is True
    assert await registry.save_to_file_async(destination)
    assert json.loads(destination.read_text(encoding="utf-8"))["nodes"][0]["name"] == "After"
    assert registry._dirty is False


def test_remove_node_persists_without_force(tmp_path: Path) -> None:
    registry = NodeRegistry()
    registry.add_or_update(KEY, NodeContactUpdate(name="Alice"))
    destination = tmp_path / "nodes.json"
    assert registry.save_to_file(destination)
    assert registry.remove_node(KEY)
    assert registry.save_to_file(destination)
    assert json.loads(destination.read_text(encoding="utf-8"))["nodes"] == []

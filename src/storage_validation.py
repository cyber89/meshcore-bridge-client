"""Shared state validators independent from optional web dependencies."""

from typing import Any


def validate_channels_document(data: Any) -> None:
    if isinstance(data, list):
        entries = [(entry.get("index", index), entry) for index, entry in enumerate(data) if isinstance(entry, dict)]
        if len(entries) != len(data):
            raise ValueError("Channel entry invalid")
    elif isinstance(data, dict):
        entries = list(data.items())
    else:
        raise ValueError("Channels document invalid")
    seen: set[int] = set()
    for index, entry in entries:
        if not str(index).isdigit() or not isinstance(entry, dict) or int(index) in seen:
            raise ValueError("Channel entry invalid")
        seen.add(int(index))
        if "index" in entry and (isinstance(entry["index"], bool) or not isinstance(entry["index"], int) or entry["index"] != int(index)):
            raise ValueError("Channel index inconsistent")

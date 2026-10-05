"""Persistence and analytics preserve observed state rather than view defaults."""

import json
from pathlib import Path

import pytest

from src.contact_manager import NodeContactUpdate, NodeRegistry

REMOTE = "ab" * 32


@pytest.mark.parametrize("observed", [False, True])
def test_raw_registry_roundtrip_preserves_unknown_and_observed_fields(tmp_path: Path, observed: bool) -> None:
    registry = NodeRegistry()
    fields = {"hop_limit": 0, "max_tx_power": 30, "tx_power": -9, "repeat_enabled": False} if observed else {}
    registry.add_or_update(REMOTE, NodeContactUpdate(name="Stored repeater", role="REPEATER", **fields))
    path = tmp_path / "registry.json"
    assert registry.save_to_file(path)
    stored = json.loads(path.read_text(encoding="utf-8"))["nodes"][0]
    assert "presence_status" not in stored and "default_tx_power" not in stored
    restored = NodeRegistry()
    assert restored.load_from_file(path) == 1
    node = restored.get(REMOTE)
    assert node is not None
    for key in ("hop_limit", "max_tx_power", "tx_power", "repeat_enabled"):
        expected = fields.get(key)
        assert stored[key] == expected
        assert getattr(node, key) == expected
    assert node.fixed_position is None


def test_analytics_never_attributes_other_mesh_nodes_to_a_repeater() -> None:
    registry = NodeRegistry()
    registry.add_or_update(REMOTE, NodeContactUpdate(role="REPEATER"))
    for index in range(3):
        registry.add_or_update(f"{index + 1:064x}", NodeContactUpdate(role="CLIENT", hops=0))
    repeater = registry.get_analytics_summary()["top_repeaters_by_clients"][0]
    assert repeater["connected_clients_count"] == 0
    assert repeater["connected_clients_count_source"] == "unknown"
    assert repeater["tx_power"] is None
    assert repeater["hop_limit"] is None
    assert repeater["max_tx_power"] is None


def test_analytics_preserves_reported_values_and_observed_neighbours() -> None:
    registry = NodeRegistry()
    registry.add_or_update(REMOTE, NodeContactUpdate(
        role="REPEATER", tx_power=-9, max_tx_power=30, hop_limit=0,
        neighbors=["cd" * 32, "ef" * 32], connected_clients_count=9,
    ))
    repeater = registry.get_analytics_summary()["top_repeaters_by_clients"][0]
    assert repeater["connected_clients_count"] == 2
    assert repeater["connected_clients_count_source"] == "neighbors"
    assert repeater["tx_power"] == -9
    assert repeater["max_tx_power"] == 30
    assert repeater["hop_limit"] == 0


def test_storage_deduplicates_local_and_preserves_routes(tmp_path: Path) -> None:
    registry = NodeRegistry()
    registry.set_local_pubkey("cd" * 32)
    registry.add_or_update("cd" * 32, NodeContactUpdate(name="Local", role="LOCAL", is_local=True))
    registry.add_or_update(REMOTE, NodeContactUpdate(
        name="Remote", role="REPEATER", out_path="000102", out_path_len=3,
        out_path_hash_mode=0, lqi_score=77.0, lqi_status="GOOD",
        last_rx_route={"hashes": ["00", "01"], "count": 2},
    ))
    path = tmp_path / "registry.json"
    assert registry.save_to_file(path)
    restored = NodeRegistry()
    assert restored.load_from_file(path) == 2
    node = restored.get(REMOTE)
    assert node is not None
    assert node.out_path == "000102" and node.out_path_len == 3
    assert node.last_rx_route == {"hashes": ["00", "01"], "count": 2}
    assert node.lqi_score == 77.0 and node.lqi_status == "GOOD"
    assert len([item for item in restored.list_nodes() if item["is_local"]]) == 1


def test_loading_legacy_values_does_not_erase_ambiguous_measurements(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"nodes": [{
        "public_key": REMOTE, "role": "REPEATER", "max_tx_power": 22,
        "hop_limit": 3, "repeat_enabled": True,
    }]}), encoding="utf-8")
    registry = NodeRegistry()
    assert registry.load_from_file(path) == 1
    node = registry.get(REMOTE)
    assert node is not None
    assert (node.max_tx_power, node.hop_limit, node.repeat_enabled) == (22, 3, True)

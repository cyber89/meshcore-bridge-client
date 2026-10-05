"""Explicit audit observations of current defects, not solution acceptance tests."""

from __future__ import annotations

import ast
import gc
import importlib.util
import json
import tracemalloc
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.metrics_aggregator import MetricsAggregator

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/audits/layers-2026-10-04"


def record(name: str, expected: Any, observed: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / (name + ".json")).write_text(
        json.dumps({"expected": expected, "observed": observed}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_metrics_helper() -> Any:
    path = ROOT / ".agents/skills/refactoring-clean-architecture/scripts/evaluate_refactoring_metrics.py"
    spec = importlib.util.spec_from_file_location("layer_audit_metrics_helper", path)
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def test_metrics_helper_misses_nested_production_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    helper = load_metrics_helper()
    source = tmp_path / "src"
    (source / "admin").mkdir(parents=True)
    (source / "safe.py").write_text("def safe(): return 1\n", encoding="utf-8")
    (source / "admin/unsafe.py").write_text("def dense(x):\n" + "    if x: pass\n" * 20, encoding="utf-8")
    monkeypatch.setattr(helper, "get_project_root", lambda: tmp_path)
    assert helper.main() == 0
    output = capsys.readouterr().out
    assert "100%" in output
    assert "unsafe.py" not in output
    assert helper.analyze_file_metrics(source / "admin/unsafe.py")
    record("quality-metrics-scope", "nested dense module reported", {"console": output, "missed": "src/admin/unsafe.py"})


def test_metrics_helper_counts_context_managers_and_nested_decisions() -> None:
    helper = load_metrics_helper()
    context = ast.parse("def f():\n    with manager():\n        return 1\n").body[0]
    nested = ast.parse("def outer():\n    def inner(x):\n        if x: return 1\n        return 2\n    return inner\n").body[0]
    observed = {"with": helper.calculate_cyclomatic_complexity(context), "outer": helper.calculate_cyclomatic_complexity(nested)}
    assert observed == {"with": 2, "outer": 2}
    record("quality-metrics-definition", {"with_decisions": 1, "outer_decisions_excluding_nested_scope": 1}, observed)


def test_metrics_retained_allocations_exceed_declared_memory_budget() -> None:
    gc.collect()
    tracemalloc.start()
    try:
        baseline, _ = tracemalloc.get_traced_memory()
        metrics = MetricsAggregator(max_minutes=1440)
        for minute in range(1440):
            metrics.record_packet("rx", "CHAT", size_bytes=32, timestamp=1700000040 + minute * 60)
        current, peak = tracemalloc.get_traced_memory()
        retained = current - baseline
        assert len(metrics._buckets) == 1440
        assert retained > 100 * 1024
        record("quality-metrics-memory", "docstring declares <100 KB", {"retained_bytes": retained, "peak_bytes": peak - baseline, "buckets": 1440, "load": "one 32-byte RX per minute, 1440 synthetic minutes", "scope": "traced Python allocations in isolated pytest process; not RSS or live service/SBC"})
    finally:
        tracemalloc.stop()


def test_metrics_current_minute_is_absent_from_all_time_series(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1700000040
    monkeypatch.setattr("src.metrics_aggregator.time.time", lambda: now)
    metrics = MetricsAggregator()
    metrics.record_packet("rx", "CHAT", timestamp=now)
    observed = {window: sum(point["rx"] for point in metrics.get_time_series(window)) for window in ("1h", "6h", "24h")}
    assert metrics.total_rx_packets == 1
    assert observed == {"1h": 0, "6h": 0, "24h": 0}
    record("quality-metrics-current-minute", "live packet represented in live chart or explicit closed-minute label", {"session_rx": 1, "chart_rx": observed})


def test_metrics_expired_packet_is_attributed_to_oldest_retained_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1700000040
    monkeypatch.setattr("src.metrics_aggregator.time.time", lambda: now + 300)
    metrics = MetricsAggregator(max_minutes=5)
    for minute in range(5):
        metrics.record_packet("rx", "CHAT", timestamp=now + minute * 60)
    oldest = metrics._buckets[0]
    metrics.record_packet("rx", "CHAT", timestamp=now - 6000)
    assert oldest.rx_packets == 2
    record("quality-metrics-expired-packet", "do not move expired packet into another timestamp", {"packet_timestamp": now - 6000, "assigned_timestamp": oldest.timestamp, "assigned_rx_count": oldest.rx_packets})


async def test_demo_database_argument_does_not_isolate_json_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    import config
    import run_interactive_demo as demo
    from src.bridge_core import MeshCoreBridge

    created: list[MeshCoreBridge] = []

    class StopBeforeStart(Exception):
        pass

    async def never_start() -> None:
        raise StopBeforeStart

    def capture_bridge(**kwargs: Any) -> MeshCoreBridge:
        bridge = MeshCoreBridge(**kwargs)
        created.append(bridge)
        bridge.start = AsyncMock(side_effect=never_start)  # type: ignore[method-assign]
        return bridge

    monkeypatch.setattr(demo, "MeshCoreBridge", capture_bridge)
    monkeypatch.setattr(demo, "VirtualMeshAdapter", lambda **kwargs: SimpleNamespace())
    with pytest.raises(StopBeforeStart):
        await demo.main()
    bridge = created[0]
    from src.contact_manager import NodeContactUpdate

    # Resolve default persistence exactly as core stop does, only in fixture data.
    bridge.node_registry.add_or_update("ef" * 32, NodeContactUpdate(name="Synthetic Demo", role="CLIENT"))
    assert bridge.node_registry.save_to_file(force=True)
    persisted = Path(config.NODE_REGISTRY_STORAGE_PATH)
    assert persisted.exists()
    assert "Synthetic Demo" in persisted.read_text(encoding="utf-8")
    assert "meshcore_sim_buffer.db" not in str(persisted)
    record("quality-demo-storage", "demo data paths distinct from operational configuration", {"requested_legacy_db_path": "meshcore_sim_buffer.db", "actual": "config.NODE_REGISTRY_STORAGE_PATH", "start_called": False, "broker_or_radio_started": False})

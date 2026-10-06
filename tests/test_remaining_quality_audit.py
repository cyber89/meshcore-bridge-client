"""Behavioral regressions for metrics and the isolated demo launcher."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.metrics_aggregator import MetricsAggregator

ROOT = Path(__file__).resolve().parents[1]


def load_helper() -> Any:
    path = ROOT / '.agents/skills/refactoring-clean-architecture/scripts/evaluate_refactoring_metrics.py'
    spec = importlib.util.spec_from_file_location('remaining_quality_helper', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_helper_recurses_and_reports_parse_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    helper = load_helper()
    source = tmp_path / 'src'
    (source / 'admin').mkdir(parents=True)
    (source / 'safe.py').write_text('def safe(): return 1\n', encoding='utf-8')
    (source / 'admin/dense.py').write_text('def dense(x):\n' + '    if x: pass\n' * 20, encoding='utf-8')
    (source / 'broken.py').write_text('def broken(\n', encoding='utf-8')
    monkeypatch.setattr(helper, 'get_project_root', lambda: tmp_path)
    assert helper.main() == 1
    output = capsys.readouterr().out
    assert 'dense.py' in output
    assert 'broken.py' in output
    assert '100%' not in output
    assert 'analizados=2' in output
    assert 'errores=1' in output


@pytest.mark.parametrize(('source', 'expected'), [
    ('def f():\n    with manager():\n        return 1\n', 1),
    ('def outer():\n    def inner(x):\n        if x: return 1\n    return inner\n', 1),
    ('def f(x):\n    return 1 if x else 2\n', 2),
    ('def f(xs):\n    return [x for x in xs if x]\n', 3),
    ('def f(a,b,c):\n    return a and b or c\n', 3),
])
def test_helper_decisions_exclude_other_scopes(source: str, expected: int) -> None:
    assert load_helper().calculate_cyclomatic_complexity(ast.parse(source).body[0]) == expected


def test_memory_claim_is_scoped() -> None:
    assert '< 100 KB' not in (MetricsAggregator.__doc__ or '')
    assert 'Python' in (MetricsAggregator.__doc__ or '')


@pytest.mark.parametrize('window', ['1h', '6h', '24h'])
def test_live_series_includes_current_minute(window: str, monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1700000040
    monkeypatch.setattr('src.metrics_aggregator.time.time', lambda: now)
    metrics = MetricsAggregator()
    metrics.record_packet('rx', 'CHAT', timestamp=now)
    summary = metrics.get_summary(window)
    assert sum(point['rx'] for point in summary['time_series']['points']) == 1
    assert summary['time_series']['points'][-1]['partial'] is True
    assert summary['summary']['scope'] == 'session'
    assert summary['time_series']['includes_current_minute'] is True


def test_expired_packets_keep_session_totals_without_rewriting_history() -> None:
    metrics = MetricsAggregator(max_minutes=5)
    start = 1700000040
    for minute in range(5):
        metrics.record_packet('rx', 'CHAT', timestamp=start + minute * 60)
    before = [(b.timestamp, b.rx_packets, b.errors) for b in metrics._buckets]
    metrics.record_packet('rx', 'CHAT', timestamp=start - 6000, error='crc')
    metrics.record_error('timeout', timestamp=start - 6000)
    assert [(b.timestamp, b.rx_packets, b.errors) for b in metrics._buckets] == before
    assert metrics.total_rx_packets == 6
    assert metrics.error_totals['crc_errors'] == 1
    assert metrics.error_totals['timeouts'] == 1


def test_out_of_order_and_large_gap_preserve_exact_retained_timestamps() -> None:
    metrics = MetricsAggregator(max_minutes=5)
    start = 1700000040
    metrics.record_packet('rx', 'CHAT', timestamp=start)
    metrics.record_packet('rx', 'CHAT', timestamp=start + 6000)
    assert [b.timestamp for b in metrics._buckets] == [start + 5760 + n * 60 for n in range(5)]
    metrics.record_packet('tx', 'CHAT', timestamp=start + 5940)
    assert metrics._buckets[-2].tx_packets == 1
    assert metrics._buckets[-1].tx_packets == 0


def test_demo_environment_does_not_inherit_operator_paths_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import run_interactive_demo as demo
    monkeypatch.setenv('MQTT_PASSWORD', 'operator-secret')
    monkeypatch.setenv('NODE_REGISTRY_STORAGE_PATH', 'operator/nodes.json')
    monkeypatch.setenv('UNRELATED_OPERATOR_SECRET', 'secret')
    env = demo.isolated_environment(tmp_path)
    assert env['MQTT_PASSWORD'] == ''
    assert 'UNRELATED_OPERATOR_SECRET' not in env
    assert env['NODE_REGISTRY_STORAGE_PATH'] == str(tmp_path / 'nodes.json')
    assert env['WEB_PORT'] == '0' and env['TCP_SERVER_ENABLED'] == 'false'


async def test_demo_paths_and_constructor_are_isolated_before_start(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import config
    import run_interactive_demo as demo
    from src.contact_manager import NodeContactUpdate
    monkeypatch.setattr('src.bridge_core.MeshcoreSDKAdapter', lambda **kwargs: pytest.fail('physical adapter'))
    bridge = demo.create_demo_bridge(isolated_state)
    try:
        assert bridge.tcp_server is None
        assert isinstance(bridge.mqtt, demo.InMemoryMQTT)
        assert bridge.watchdog.adapter is bridge.serial_adapter
        assert bridge.web_server.tile_service.base_dir == isolated_state
        bridge.node_registry.add_or_update('ef' * 32, NodeContactUpdate(name='Synthetic Demo', role='CLIENT'))
        assert bridge.node_registry.save_to_file(force=True)
        saved = Path(config.NODE_REGISTRY_STORAGE_PATH)
        assert saved.resolve().is_relative_to(isolated_state.resolve())
        assert 'Synthetic Demo' in json.dumps(json.loads(saved.read_text(encoding='utf-8')))
    finally:
        await bridge.stop()


async def test_demo_rejects_effective_path_outside_its_directory(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import config
    import run_interactive_demo as demo
    monkeypatch.setattr(config, 'AIRTIME_HISTORY_FILE', str(isolated_state.parent / 'operator.json'))
    with pytest.raises(ValueError, match='AIRTIME_HISTORY_FILE'):
        demo.create_demo_bridge(isolated_state)


async def test_demo_start_failure_always_closes_partial_resources(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import run_interactive_demo as demo
    bridge = demo.create_demo_bridge(isolated_state)
    bridge.web_server.start = AsyncMock(side_effect=RuntimeError('simulated listen failure'))
    monkeypatch.setattr(demo, 'create_demo_bridge', lambda directory: bridge)
    with pytest.raises(RuntimeError, match='simulated listen failure'):
        await demo.main(isolated_state)
    assert not bridge.serial_adapter.is_connected
    assert not bridge.serial_adapter._background_tasks
    assert not bridge.mqtt.is_connected
    assert bridge._is_stopped


async def test_demo_real_loopback_shutdown_leaves_no_tasks(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import run_interactive_demo as demo
    bridge = demo.create_demo_bridge(isolated_state)
    bridge.preflight.run_all = lambda **kwargs: pytest.fail('production preflight')
    bridge.watchdog.start = lambda: pytest.fail('physical watchdog')
    monkeypatch.setattr(demo, 'create_demo_bridge', lambda directory: bridge)
    stopping = asyncio.Event()
    stopping.set()
    await demo.main(isolated_state, stopping)
    assert bridge._is_stopped and not bridge._background_tasks
    assert bridge.web_server.server is None
    assert not bridge.serial_adapter._background_tasks

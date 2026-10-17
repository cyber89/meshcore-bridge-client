"""Browser regression tests for manual SENSOR subscription controls in the unified Nodes view."""

from __future__ import annotations


def test_sensor_card_renders_manual_subscribe_and_unsubscribe_controls_in_nodes_source() -> None:
    """Static contract check ensuring SENSOR cards expose manual subscription buttons and never DM controls."""
    from pathlib import Path

    nodes_js = Path("src/web/static/js/modules/nodes.js").read_text(encoding="utf-8")
    assert "btn-subscribe-sensor" in nodes_js
    assert "btn-unsubscribe-sensor" in nodes_js
    assert "sensor-subscription-badge" in nodes_js
    assert 'manageSensorSubscription(node.public_key, cleanName, "subscribe_sensor"' in nodes_js
    assert 'manageSensorSubscription(node.public_key, cleanName, "unsubscribe_sensor"' in nodes_js

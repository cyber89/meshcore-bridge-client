"""Administrative responses reach their waiter before public copies are redacted."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.routers.base import MeshMessageEvent
from src.rx_router import RxEventRouter


@pytest.mark.parametrize("matched,sensitive,text", [
    (True, True, "af|unique-private-secret"),
    (False, False, "af|unique-private-secret"),
    (True, False, "af|OK"),
    (False, False, "password now: unique-private-secret"),
])
async def test_cli_publication_preserves_context_without_disclosing_secrets(
    matched: bool, sensitive: bool, text: str,
) -> None:
    registry = NodeRegistry()
    registry.set_local_pubkey("cd" * 32)
    remote = "ab" * 32
    registry.add_or_update(remote, NodeContactUpdate(name="Repeater", role="REPEATER"))
    private_seen: list[str] = []

    def notify(_sender: str, data: dict[str, object]) -> bool:
        private_seen.append(str(data["text"]))
        if matched:
            data.update(response_matched=True, sensitive_response=sensitive, text=text[3:])
        return matched

    manager = MagicMock()
    manager.parse_repeater_telemetry_or_response.return_value = {}
    ctx = SimpleNamespace(
        node_registry=registry, repeater_manager=manager, deduplicator=None,
        admin_handler=SimpleNamespace(notify_command_response=notify),
        mqtt=MagicMock(), loop=None, register_task=None, background_tasks=set(),
    )
    router = RxEventRouter(ctx)
    router._spawn_broadcast_task = MagicMock()
    await router._handle_mesh_msg_common(MeshMessageEvent(remote, "Repeater", text, 0, txt_type=1), "direct")
    assert private_seen == [text]
    broadcast = router._spawn_broadcast_task.call_args.args[0]
    assert "unique-private-secret" not in json.dumps(broadcast)
    for call in ctx.mqtt.publish_safe.call_args_list:
        assert "unique-private-secret" not in call.args[1]
    if text.startswith("af|"):
        manager.parse_repeater_telemetry_or_response.assert_not_called()
    if matched and not sensitive:
        assert broadcast["text"] == "OK"

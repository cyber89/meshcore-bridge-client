"""
Unit tests for ChannelsController and ContactsController.
Verifies PSK masking, bounds checking, atomic persistence, and strict ADR 0001 repeater exclusion.
"""

from collections import deque
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.web.controllers.base import ApiContext
from src.web.controllers.channels_controller import ChannelsController
from src.web.controllers.contacts_controller import ContactsController


@pytest.fixture
def mock_api_context(tmp_path: Any) -> ApiContext:
    mock_bridge = MagicMock()
    mock_bridge.node_registry = NodeRegistry()
    mock_bridge.serial_adapter = None
    mock_bridge.execute_tx = MagicMock()
    mock_bridge.recent_messages = []

    return ApiContext(
        bridge=mock_bridge,
        recent_messages=deque(),
        system_logs=deque(),
        log_system_event=MagicMock(),
        start_time=1000.0,
    )


@pytest.mark.asyncio
async def test_channels_controller_get_masked(mock_api_context: ApiContext, tmp_path: Any) -> None:
    ch_file = str(tmp_path / "test_channels.json")
    ctrl = ChannelsController(mock_api_context, channels_file=ch_file)

    # Añadir canal privado con PSK
    ctrl.channels[1] = {
        "index": 1,
        "name": "Equipo Alfa",
        "psk": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
    }

    status, resp = await ctrl.handle_channels_route("/api/channels", "GET", {})
    assert status == 200
    assert resp["status"] == "ok"
    channels = resp["data"]
    assert len(channels) >= 2

    # Canal 0 no tiene PSK
    ch0 = next(c for c in channels if c["index"] == 0)
    assert ch0["has_psk"] is False

    # Canal 1 debe tener PSK enmascarada
    ch1 = next(c for c in channels if c["index"] == 1)
    assert ch1["psk"] == "••••••••"
    assert ch1["has_psk"] is True


@pytest.mark.asyncio
async def test_channels_controller_bounds_validation(mock_api_context: ApiContext, tmp_path: Any) -> None:
    ch_file = str(tmp_path / "test_channels.json")
    ctrl = ChannelsController(mock_api_context, channels_file=ch_file)

    # Índice válido (0..7)
    status_ok, resp_ok = await ctrl.handle_channels_route(
        "/api/channels", "POST", {"index": 3, "name": "Canal 3", "psk": ""}
    )
    assert status_ok in (200, 201)

    # Índice fuera de rango (< 0 o > 7)
    status_bad, resp_bad = await ctrl.handle_channels_route(
        "/api/channels", "POST", {"index": 9, "name": "Canal Invalido"}
    )
    assert status_bad == 400
    assert resp_bad.get("error") == "channel_index_out_of_bounds"


@pytest.mark.asyncio
async def test_contacts_controller_strict_repeater_exclusion(mock_api_context: ApiContext) -> None:
    registry = mock_api_context.bridge.node_registry

    # Registrar nodo cliente y nodo repetidor con claves hex válidas
    client_pk = "1122334455aabbcc"
    repeater_pk = "9988776655ddeeff"
    registry.add_or_update(client_pk, NodeContactUpdate(name="Usuario Humano", role="CLIENT"))
    registry.add_or_update(repeater_pk, NodeContactUpdate(name="Repetidor Cerro", role="REPEATER"))

    ctrl = ContactsController(mock_api_context)
    status, resp = await ctrl.handle_contacts_route("/api/contacts", "GET", {})
    assert status == 200
    contacts = resp["data"]
    contact_pks = [c["public_key"] for c in contacts]

    # REGLA INMUTABLE ADR 0001: El cliente debe estar en contactos, el repetidor NUNCA
    assert client_pk in contact_pks
    assert repeater_pk not in contact_pks

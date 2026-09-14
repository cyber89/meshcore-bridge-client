"""
Unit tests for TargetResolver (SSoT Destination Target Resolution).
Covers SDK lookups, NodeRegistry lookups, hex padding, and error handling.
"""

from unittest.mock import MagicMock

import pytest

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.target_resolver import TargetResolver


def test_target_resolver_empty_or_passthrough() -> None:
    resolver = TargetResolver()
    assert resolver.resolve("") == ""
    assert resolver.resolve(None) is None  # type: ignore

    dict_target = {"public_key": "aabbcc112233", "name": "Node A"}
    assert resolver.resolve(dict_target) == dict_target


def test_target_resolver_sdk_lookup_by_name() -> None:
    mock_mc = MagicMock()
    mock_mc.get_contact_by_name.return_value = {"public_key": "1234567890ab", "name": "Alpha"}
    mock_mc.commands = MagicMock()

    resolver = TargetResolver(mc_provider=mock_mc)
    res = resolver.resolve("Alpha")
    assert res == {"public_key": "1234567890ab", "name": "Alpha"}
    mock_mc.get_contact_by_name.assert_called_with("Alpha")


def test_target_resolver_sdk_lookup_by_prefix() -> None:
    mock_mc = MagicMock()
    mock_mc.get_contact_by_name.return_value = None
    mock_mc.get_contact_by_key_prefix.return_value = {"public_key": "abcdef123456", "name": "Bravo"}
    mock_mc.commands = MagicMock()

    resolver = TargetResolver(mc_provider=mock_mc)
    res = resolver.resolve("abcdef")
    assert res == {"public_key": "abcdef123456", "name": "Bravo"}


def test_target_resolver_registry_lookup() -> None:
    registry = NodeRegistry()
    registry.add_or_update("112233445566", NodeContactUpdate(name="Scout Unit"))

    resolver = TargetResolver(node_registry=registry)
    # Buscar por nombre
    res_name = resolver.resolve("Scout Unit")
    assert res_name == "112233445566"

    # Buscar por prefijo
    res_prefix = resolver.resolve("112233")
    assert res_prefix == "112233445566"


def test_target_resolver_hex_padding() -> None:
    resolver = TargetResolver()
    # Cadena hex corta de 6 caracteres con min_hex_len=12
    padded = resolver.resolve("a1b2c3", min_hex_len=12)
    assert padded == "a1b2c3000000"
    assert len(padded) == 12


def test_target_resolver_raise_on_not_found() -> None:
    resolver = TargetResolver()
    # Nombre no-hex desconocido con raise_on_not_found=True debe lanzar ValueError
    with pytest.raises(ValueError, match="Destinatario no encontrado"):
        resolver.resolve("NonExistentNode", raise_on_not_found=True)

    # Con raise_on_not_found=False retorna el string original
    assert resolver.resolve("NonExistentNode", raise_on_not_found=False) == "NonExistentNode"

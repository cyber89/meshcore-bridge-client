"""Unit tests for companion identity healing and lookup (identity_resolve)."""

import os

import pytest

from repeater.companion.identity_resolve import (
    derive_companion_public_key_hex,
    find_companion_index,
    heal_companion_empty_names,
    identity_key_bytes_from_config,
    identity_key_hex_normalized,
    suggest_companion_name_from_pubkey,
    unique_suggested_name,
)


def _seed32() -> bytes:
    return os.urandom(32)


@pytest.fixture
def key_a_hex() -> str:
    return _seed32().hex()


@pytest.fixture
def key_b_hex() -> str:
    return _seed32().hex()


def test_identity_key_bytes_from_config_hex_string():
    raw = _seed32()
    h = raw.hex()
    assert identity_key_bytes_from_config(h) == raw
    assert identity_key_bytes_from_config("0x" + h) == raw


def test_identity_key_bytes_from_config_raw_bytes():
    raw = _seed32()
    assert identity_key_bytes_from_config(raw) == raw
    assert identity_key_bytes_from_config(bytearray(raw)) == raw


def test_identity_key_bytes_from_config_invalid():
    assert identity_key_bytes_from_config(None) is None
    assert identity_key_bytes_from_config("nothex") is None
    assert identity_key_bytes_from_config("ab") is None  # wrong length


def test_identity_key_hex_normalized_matches_bytes():
    raw = _seed32()
    assert identity_key_hex_normalized(raw.hex()) == raw.hex().lower()
    assert identity_key_hex_normalized(raw) == raw.hex().lower()


def test_derive_companion_public_key_hex_32_byte_seed(key_a_hex: str):
    pub = derive_companion_public_key_hex(key_a_hex)
    assert pub is not None
    assert len(pub) == 64
    assert int(pub, 16) >= 0


def test_derive_companion_public_key_hex_invalid():
    assert derive_companion_public_key_hex(None) is None
    assert derive_companion_public_key_hex("") is None


def test_suggest_companion_name_from_pubkey():
    pub = "a" * 64
    assert suggest_companion_name_from_pubkey(pub) == "companion_aaaaaaaa"
    assert suggest_companion_name_from_pubkey("0x" + "b" * 64) == "companion_bbbbbbbb"


def test_unique_suggested_name_collision_suffix(key_a_hex: str):
    pub = derive_companion_public_key_hex(key_a_hex)
    assert pub is not None
    base = suggest_companion_name_from_pubkey(pub)
    assert unique_suggested_name(pub, {base}) == f"{base}-2"
    assert unique_suggested_name(pub, {base, f"{base}-2"}) == f"{base}-3"


def test_heal_companion_empty_names_sets_stable_name(key_a_hex: str):
    companions = [{"name": "", "identity_key": key_a_hex, "settings": {}}]
    assert heal_companion_empty_names(companions) is True
    assert companions[0]["name"].startswith("companion_")
    assert len(companions[0]["name"]) > len("companion_")


def test_heal_companion_empty_names_whitespace_name_treated_as_empty(key_a_hex: str):
    companions = [{"name": "   ", "identity_key": key_a_hex, "settings": {}}]
    assert heal_companion_empty_names(companions) is True
    assert companions[0]["name"].startswith("companion_")


def test_heal_companion_no_op_when_name_present(key_a_hex: str):
    companions = [{"name": "MyCompanion", "identity_key": key_a_hex, "settings": {}}]
    assert heal_companion_empty_names(companions) is False
    assert companions[0]["name"] == "MyCompanion"


def test_heal_skips_row_without_derivable_key():
    companions = [{"name": "", "identity_key": "dead", "settings": {}}]
    assert heal_companion_empty_names(companions) is False
    assert companions[0].get("name") in ("", None) or str(companions[0].get("name")).strip() == ""


def test_heal_two_unnamed_get_distinct_names(key_a_hex: str, key_b_hex: str):
    companions = [
        {"name": "", "identity_key": key_a_hex, "settings": {}},
        {"name": None, "identity_key": key_b_hex, "settings": {}},
    ]
    assert heal_companion_empty_names(companions) is True
    assert companions[0]["name"] != companions[1]["name"]


def test_find_companion_index_by_name(key_a_hex: str):
    companions = [{"name": "c1", "identity_key": key_a_hex, "settings": {}}]
    idx, err = find_companion_index(companions, name="c1")
    assert err is None and idx == 0


def test_find_companion_index_name_not_found(key_a_hex: str):
    companions = [{"name": "c1", "identity_key": key_a_hex, "settings": {}}]
    idx, err = find_companion_index(companions, name="nope")
    assert idx is None and "not found" in (err or "")


def test_find_companion_index_duplicate_names_error(key_a_hex: str, key_b_hex: str):
    companions = [
        {"name": "dup", "identity_key": key_a_hex, "settings": {}},
        {"name": "dup", "identity_key": key_b_hex, "settings": {}},
    ]
    idx, err = find_companion_index(companions, name="dup")
    assert idx is None and err and "Multiple" in err


def test_find_companion_index_by_full_identity_key(key_a_hex: str):
    companions = [{"name": "x", "identity_key": key_a_hex, "settings": {}}]
    idx, err = find_companion_index(companions, identity_key=key_a_hex.lower())
    assert err is None and idx == 0


def test_find_companion_index_by_identity_key_prefix(key_a_hex: str):
    companions = [{"name": "x", "identity_key": key_a_hex, "settings": {}}]
    prefix = key_a_hex[:16]
    idx, err = find_companion_index(companions, identity_key=prefix)
    assert err is None and idx == 0


def test_find_companion_index_identity_key_too_short():
    companions = [{"name": "x", "identity_key": "a" * 64, "settings": {}}]
    idx, err = find_companion_index(companions, identity_key="abcd")
    assert idx is None and err and "at least" in err


def test_find_companion_index_identity_key_ambiguous_prefix():
    """Two keys sharing the same 8-hex prefix should make prefix lookup ambiguous."""
    shared = "aabbccdd"
    key_a_hex = shared + os.urandom(28).hex()
    key_b_hex = shared + os.urandom(28).hex()
    assert len(key_a_hex) == 64 and len(key_b_hex) == 64
    assert key_a_hex != key_b_hex

    companions = [
        {"name": "a1", "identity_key": key_a_hex, "settings": {}},
        {"name": "a2", "identity_key": key_b_hex, "settings": {}},
    ]
    idx, err = find_companion_index(companions, identity_key=shared)
    assert idx is None and err and "ambiguous" in err


def test_find_companion_index_by_public_key_prefix(key_a_hex: str):
    pub = derive_companion_public_key_hex(key_a_hex)
    assert pub is not None
    companions = [{"name": "x", "identity_key": key_a_hex, "settings": {}}]
    idx, err = find_companion_index(companions, public_key_prefix=pub[:16])
    assert err is None and idx == 0


def test_find_companion_index_public_key_prefix_with_0x(key_a_hex: str):
    pub = derive_companion_public_key_hex(key_a_hex)
    assert pub is not None
    companions = [{"name": "x", "identity_key": key_a_hex, "settings": {}}]
    idx, err = find_companion_index(companions, public_key_prefix="0x" + pub[:16])
    assert err is None and idx == 0


def test_find_companion_index_missing_lookup_fields():
    companions = [{"name": "x", "identity_key": "a" * 64, "settings": {}}]
    idx, err = find_companion_index(companions)
    assert idx is None and err and "Missing companion lookup" in err


def test_name_lookup_takes_priority_over_identity_key(key_a_hex: str, key_b_hex: str):
    """When `name` is set, identity_key lookup is not used."""
    companions = [
        {"name": "first", "identity_key": key_a_hex, "settings": {}},
        {"name": "second", "identity_key": key_b_hex, "settings": {}},
    ]
    idx, err = find_companion_index(companions, name="first", identity_key=key_b_hex)
    assert err is None and idx == 0

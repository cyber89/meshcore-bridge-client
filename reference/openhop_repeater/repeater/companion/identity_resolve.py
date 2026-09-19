"""Resolve companion config rows by registration name, identity key, or public key prefix."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Set, Tuple

from repeater.companion.utils import normalize_companion_identity_key

logger = logging.getLogger(__name__)

# Minimum hex chars for identity_key / public_key prefix disambiguation (4 bytes)
_MIN_PREFIX_HEX_LEN = 8


def _companion_registration_name(entry: dict) -> str:
    n = entry.get("name")
    if n is None:
        return ""
    return str(n).strip()


def identity_key_bytes_from_config(identity_key: Any) -> Optional[bytes]:
    """Parse companion identity_key from YAML (str hex or raw bytes)."""
    if identity_key is None:
        return None
    if isinstance(identity_key, (bytes, bytearray, memoryview)):
        raw = bytes(identity_key)
        return raw if len(raw) in (32, 64) else None
    if isinstance(identity_key, str):
        try:
            raw = bytes.fromhex(normalize_companion_identity_key(identity_key))
        except ValueError:
            return None
        return raw if len(raw) in (32, 64) else None
    return None


def identity_key_hex_normalized(identity_key: Any) -> Optional[str]:
    """Lowercase hex string of the raw key bytes (64 or 128 chars), or None."""
    raw = identity_key_bytes_from_config(identity_key)
    if raw is None:
        return None
    return raw.hex().lower()


def derive_companion_public_key_hex(identity_key: Any) -> Optional[str]:
    """Return ed25519 public key hex for a companion seed, or None if invalid."""
    raw = identity_key_bytes_from_config(identity_key)
    if raw is None:
        return None
    try:
        from openhop_core import LocalIdentity

        identity = LocalIdentity(seed=raw)
        return identity.get_public_key().hex()
    except Exception as e:
        logger.debug("derive_companion_public_key_hex failed: %s", e)
        return None


def suggest_companion_name_from_pubkey(pubkey_hex: str, prefix_len: int = 8) -> str:
    """Stable default registration name: companion_<first prefix_len hex chars of pubkey>."""
    p = pubkey_hex.strip().lower()
    if p.startswith("0x"):
        p = p[2:]
    if len(p) < prefix_len:
        prefix = p
    else:
        prefix = p[:prefix_len]
    return f"companion_{prefix}"


def unique_suggested_name(
    pubkey_hex: str,
    existing_names: set,
    prefix_len: int = 8,
) -> str:
    """Like suggest_companion_name_from_pubkey but appends -2, -3, ... if name collides."""
    base = suggest_companion_name_from_pubkey(pubkey_hex, prefix_len=prefix_len)
    if base not in existing_names:
        return base
    n = 2
    while f"{base}-{n}" in existing_names:
        n += 1
    return f"{base}-{n}"


def find_companion_index(
    companions: List[dict],
    *,
    name: Optional[str] = None,
    identity_key: Optional[str] = None,
    public_key_prefix: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Find a single companion list index.

    Lookup priority when multiple fields are set:
    1) name (non-empty after strip)
    2) identity_key (full hex or unique prefix)
    3) public_key_prefix (unique prefix of derived public key hex)

    Returns (index, None) on success, or (None, error_message) on failure.
    """
    name_s = str(name).strip() if name is not None else ""
    idk = str(identity_key).strip() if identity_key is not None else ""
    pkp = str(public_key_prefix).strip() if public_key_prefix is not None else ""
    if pkp.lower().startswith("0x"):
        pkp = pkp[2:].strip()
    pkp = pkp.lower()

    if idk:
        idk = normalize_companion_identity_key(idk).lower()

    if name_s:
        matches = [i for i, c in enumerate(companions) if _companion_registration_name(c) == name_s]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) == 0:
            return None, f"Companion '{name_s}' not found"
        return None, f"Multiple companions named '{name_s}'"

    if idk:
        if len(idk) < _MIN_PREFIX_HEX_LEN:
            return None, (
                f"identity_key lookup must be at least {_MIN_PREFIX_HEX_LEN} hex characters"
            )
        exact: List[int] = []
        prefix_matches: List[int] = []
        for i, c in enumerate(companions):
            h = identity_key_hex_normalized(c.get("identity_key"))
            if not h:
                continue
            if h == idk:
                exact.append(i)
            elif h.startswith(idk):
                prefix_matches.append(i)
        if len(exact) == 1:
            return exact[0], None
        if len(exact) > 1:
            return None, "Multiple companions match identity_key (ambiguous)"
        if len(prefix_matches) == 1:
            return prefix_matches[0], None
        if len(prefix_matches) == 0:
            return None, "No companion matches identity_key"
        return None, "Multiple companions match identity_key prefix (ambiguous)"

    if pkp:
        if len(pkp) < _MIN_PREFIX_HEX_LEN:
            return None, (
                f"public_key_prefix must be at least {_MIN_PREFIX_HEX_LEN} hex characters"
            )
        matches: List[int] = []
        for i, c in enumerate(companions):
            pub = derive_companion_public_key_hex(c.get("identity_key"))
            if pub and pub.lower().startswith(pkp):
                matches.append(i)
        if len(matches) == 1:
            return matches[0], None
        if len(matches) == 0:
            return None, "No companion matches public_key_prefix"
        return None, "Multiple companions match public_key_prefix (ambiguous)"

    return None, "Missing companion lookup: provide name, identity_key, or public_key_prefix"


def heal_companion_empty_names(companions: List[dict]) -> bool:
    """
    Assign companion_<pubkeyPrefix> names to entries with missing/blank registration names.
    Mutates companions in place. Returns True if any entry was updated.
    """
    names_in_use: Set[str] = set()
    for c in companions:
        n = _companion_registration_name(c)
        if n:
            names_in_use.add(n)
    changed = False
    for entry in companions:
        if _companion_registration_name(entry):
            continue
        pk = derive_companion_public_key_hex(entry.get("identity_key"))
        if not pk:
            logger.warning("Skipping companion name heal: invalid or missing identity_key")
            continue
        new_name = unique_suggested_name(pk, names_in_use)
        entry["name"] = new_name
        names_in_use.add(new_name)
        changed = True
    return changed

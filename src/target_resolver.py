"""Resolve MeshCore targets without inventing keys or choosing ambiguous prefixes."""

from __future__ import annotations

from typing import Any


class TargetResolver:
    """Resolve exact keys, unique known prefixes, and unique contact names."""

    def __init__(self, mc_provider: Any = None, node_registry: Any = None) -> None:
        self._mc_provider = mc_provider
        self._node_registry = node_registry

    def _get_mc(self) -> Any:
        provider = self._mc_provider
        if callable(provider) and not any(hasattr(provider, attr) for attr in ("commands", "contacts", "get_contact_by_name")):
            return provider()
        return provider

    @staticmethod
    def _field(contact: Any, field: str) -> Any:
        return contact.get(field) if isinstance(contact, dict) else getattr(contact, field, None)

    @classmethod
    def _select_unique(cls, contacts: dict[str, Any], query: str) -> Any | None:
        """An enumerable contact book takes precedence over SDK first-match helpers."""
        q = query.lower()
        exact = [(key, contact) for key, contact in contacts.items() if str(key).lower() == q]
        matches = exact or [
            (key, contact) for key, contact in contacts.items()
            if str(key).lower().startswith(q)
            or any(str(cls._field(contact, attr) or "").lower() == q for attr in ("name", "alias", "adv_name"))
        ]
        unique = {str(cls._field(contact, "public_key") or key).lower(): contact for key, contact in matches}
        if len(unique) > 1:
            raise ValueError(f"Destinatario ambiguo: '{query}'")
        return next(iter(unique.values()), None)

    def resolve(self, name_or_key: Any, min_hex_len: int = 12, raise_on_not_found: bool = False) -> Any:
        """Resolve known contacts, or accept a complete 32-byte public key.

        ``min_hex_len`` remains for call compatibility. It never pads a key.
        Partial keys must match a unique existing contact. Unknown names remain
        unchanged only for callers explicitly permitting unresolved names.
        """
        if not name_or_key:
            return name_or_key
        if isinstance(name_or_key, dict) or hasattr(name_or_key, "public_key"):
            return name_or_key
        query = str(name_or_key).strip()
        is_hex = bool(query) and all(char in "0123456789abcdefABCDEF" for char in query)
        mc = self._get_mc()
        if mc is not None:
            raw_contacts = getattr(mc, "contacts", None)
            if callable(raw_contacts):
                try:
                    contacts = raw_contacts()
                except Exception:
                    contacts = getattr(mc, "_contacts", None)
            elif raw_contacts is None:
                contacts = getattr(mc, "_contacts", None)
            else:
                contacts = raw_contacts

            if isinstance(contacts, dict):
                result = self._select_unique(contacts, query)
            else:
                result = self._search_sdk_helpers(mc, query, is_hex)
            if result is not None:
                return result

        registry = self._node_registry
        if registry is not None:
            nodes = getattr(registry, "_nodes_by_key", None)
            if isinstance(nodes, dict):
                result = self._select_unique(nodes, query)
            else:
                result = registry.get_by_key_or_prefix(query)
            if result is not None:
                pubkey = self._field(result, "public_key")
                if pubkey:
                    return str(pubkey)

        if is_hex:
            if len(query) == 64:
                return query.lower()
            raise ValueError(f"Destinatario no encontrado o clave pública incompleta: '{query}'")
        if raise_on_not_found:
            raise ValueError(f"Destinatario no encontrado o clave pública inválida: '{query}'")
        return query

    @classmethod
    def _search_sdk_helpers(cls, mc: Any, query: str, is_hex: bool) -> Any | None:
        """Compatibility for providers without an enumerable contact book."""
        methods = ("get_contact_by_key_prefix", "get_contact_by_name") if is_hex else ("get_contact_by_name",)
        for method in methods:
            lookup = getattr(mc, method, None)
            if not callable(lookup):
                continue
            try:
                result = lookup(query)
            except (KeyError, ValueError):
                continue
            if not result:
                continue
            key = str(cls._field(result, "public_key") or "").lower()
            if method == "get_contact_by_key_prefix" and not key.startswith(query.lower()):
                continue
            return result
        return None

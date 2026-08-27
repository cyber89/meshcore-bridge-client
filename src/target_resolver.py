"""
TargetResolver: Resolución canónica de identificadores de destino a claves públicas.

Consolida la lógica duplicada de resolución de destino que existía en
serial_driver.py y admin_handler.py en una única fuente de verdad.
"""

from __future__ import annotations

import logging
from typing import Any


class TargetResolver:
    """Resolución canónica de identificadores de destino a claves públicas.

    Busca por nombre, clave hex parcial, prefijo de clave, o ID numérico
    en el SDK MeshCore y en el NodeRegistry local, unificando la lógica
    que antes estaba duplicada en serial_driver.py y admin_handler.py.
    """

    def __init__(
        self,
        mc_provider: Any = None,
        node_registry: Any = None,
    ) -> None:
        """Inicializa el resolver con las fuentes de datos disponibles.

        Args:
            mc_provider: Callable que retorna la instancia del SDK MeshCore,
                         o la instancia directa del SDK.
            node_registry: Instancia del NodeRegistry para búsqueda local.
        """
        self._mc_provider = mc_provider
        self._node_registry = node_registry

    def _get_mc(self) -> Any:
        """Obtiene la instancia del SDK MeshCore."""
        if callable(self._mc_provider):
            return self._mc_provider()
        return self._mc_provider

    def resolve(
        self,
        name_or_key: str,
        min_hex_len: int = 12,
        raise_on_not_found: bool = False,
    ) -> Any:
        """Resuelve un identificador de destino a clave pública o contacto SDK.

        La búsqueda sigue este orden de prioridad:
        1. SDK MeshCore: get_contact_by_key_prefix → get_contact_by_name → contacts dict
        2. NodeRegistry local: get_contact → _nodes_by_key prefix scan
        3. Padding de clave hex corta a min_hex_len caracteres
        4. Retorno directo si es hex válido, ValueError si no lo es

        Args:
            name_or_key: Nombre, clave hex parcial/completa, o ID numérico del nodo.
            min_hex_len: Longitud mínima de clave hex para validación (default 12 = 6 bytes).
            raise_on_not_found: Si True, lanza ValueError para nombres no-hex no encontrados
                                en vez de retornar el string sin cambios.

        Returns:
            Objeto contacto del SDK, clave pública como string, o dict según la fuente.

        Raises:
            ValueError: Si raise_on_not_found=True y el identificador no es hex
                        ni se encontró en contactos.
        """
        if not name_or_key:
            return name_or_key
        if isinstance(name_or_key, dict) or hasattr(name_or_key, "public_key"):
            return name_or_key

        name_str = str(name_or_key).strip()
        mc = self._get_mc()

        # 1. Buscar en MeshCore SDK
        if mc:
            result = self._search_sdk(mc, name_str)
            if result is not None:
                return result

        # 2. Buscar en NodeRegistry local
        if self._node_registry:
            result = self._search_registry(mc, name_str, min_hex_len)
            if result is not None:
                return result

        # 3. Padding de clave hex corta
        is_hex = all(c in "0123456789abcdefABCDEF" for c in name_str)
        if is_hex and len(name_str) < min_hex_len:
            return (name_str + "0" * min_hex_len)[:min_hex_len]

        # 4. Validación final
        if not is_hex and raise_on_not_found:
            logging.warning(
                "Target '%s' no es una clave hex válida ni se encontró en contactos.",
                name_str,
            )
            raise ValueError(
                f"Destinatario no encontrado o clave pública inválida: '{name_str}'"
            )

        return name_str

    def _search_sdk(self, mc: Any, name_str: str) -> Any | None:
        """Busca el destino en el SDK MeshCore.

        Args:
            mc: Instancia del SDK MeshCore.
            name_str: Identificador a buscar.

        Returns:
            Contacto SDK si se encontró, None si no.
        """
        # Búsqueda por prefijo de clave
        if hasattr(mc, "get_contact_by_key_prefix"):
            try:
                c = mc.get_contact_by_key_prefix(name_str)
                if c:
                    return c
            except Exception:
                pass

        # Búsqueda por nombre
        if hasattr(mc, "get_contact_by_name"):
            try:
                c = mc.get_contact_by_name(name_str)
                if c:
                    return c
            except Exception:
                pass

        # Escaneo directo del dict de contactos
        if hasattr(mc, "contacts") and isinstance(mc.contacts, dict):
            name_lower = name_str.lower()
            for pk, contact in mc.contacts.items():
                pk_lower = pk.lower()
                c_name = ""
                if isinstance(contact, dict):
                    c_name = str(contact.get("name", ""))
                elif hasattr(contact, "name"):
                    c_name = str(getattr(contact, "name", ""))

                if (
                    pk_lower.startswith(name_lower)
                    or name_lower.startswith(pk_lower[:8])
                    or (c_name and c_name.lower() == name_lower)
                ):
                    return contact

        return None

    def _search_registry(
        self, mc: Any, name_str: str, min_hex_len: int
    ) -> Any | None:
        """Busca el destino en el NodeRegistry local.

        Args:
            mc: Instancia del SDK MeshCore (para re-lookup cruzado).
            name_str: Identificador a buscar.
            min_hex_len: Longitud mínima de clave hex.

        Returns:
            Clave pública, contacto SDK o None si no se encontró.
        """
        registry = self._node_registry

        # Búsqueda directa por clave o prefijo
        c_info = None
        if hasattr(registry, "get_contact"):
            c_info = registry.get_contact(name_str)

        if not c_info and hasattr(registry, "get_by_key_or_prefix"):
            c_info = registry.get_by_key_or_prefix(name_str)

        if not c_info and hasattr(registry, "find_by_name"):
            c_info = registry.find_by_name(name_str)

        # Escaneo por prefijo en _nodes_by_key
        if not c_info:
            name_lower = name_str.lower()
            for pk, node in getattr(registry, "_nodes_by_key", {}).items():
                pk_lower = pk.lower()
                if pk_lower.startswith(name_lower) or name_lower.startswith(
                    pk_lower[:8]
                ):
                    c_info = node
                    break

        if c_info:
            # Intentar obtener contacto SDK completo si está disponible
            pub_key = getattr(c_info, "public_key", None)
            if (
                mc
                and pub_key
                and hasattr(mc, "get_contact_by_key_prefix")
            ):
                try:
                    c = mc.get_contact_by_key_prefix(pub_key[:12])
                    if c:
                        return c
                except Exception:
                    pass

            if pub_key and len(pub_key) >= min_hex_len:
                return pub_key

        return None

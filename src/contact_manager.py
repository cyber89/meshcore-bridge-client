"""
Node Registry & Contact Directory for MeshCore Bridge.
Mantiene un registro de nodos activos, libretas de contactos, alias y métricas RF
en memoria con soporte de búsqueda O(1) y sincronización delta.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class NodeContactInfo:
    """Información consolidada de un nodo o contacto en la malla."""
    public_key: str
    name: str
    alias: str
    hops: int = 0
    last_rssi: int = -80
    last_snr: float = 10.0
    battery_pct: int | None = None
    last_seen: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key_prefix"] = self.public_key[:8] if len(self.public_key) >= 8 else self.public_key
        return d


class NodeRegistry:
    """Directorio en memoria para contactos y resolución de nombres de la red MeshCore."""

    def __init__(self) -> None:
        self._nodes_by_key: dict[str, NodeContactInfo] = {}
        self._nodes_by_name: dict[str, str] = {}  # lower(name) -> public_key
        self.last_sync_timestamp: float = 0.0

    def add_or_update(
        self,
        public_key: str,
        name: str,
        alias: str = "",
        hops: int = 0,
        last_rssi: int = -80,
        last_snr: float = 10.0,
        battery_pct: int | None = None,
    ) -> NodeContactInfo:
        """Añade o actualiza la información de un nodo."""
        norm_key = public_key.strip().lower()
        clean_name = name.strip() or f"Node_{norm_key[:6]}"
        clean_alias = alias.strip() or clean_name
        now = time.time()

        contact = NodeContactInfo(
            public_key=norm_key,
            name=clean_name,
            alias=clean_alias,
            hops=hops,
            last_rssi=last_rssi,
            last_snr=last_snr,
            battery_pct=battery_pct,
            last_seen=now,
        )

        self._nodes_by_key[norm_key] = contact
        self._nodes_by_name[clean_name.lower()] = norm_key
        if clean_alias:
            self._nodes_by_name[clean_alias.lower()] = norm_key

        return contact

    def get_by_key_or_prefix(self, query: str) -> NodeContactInfo | None:
        """Busca un nodo por clave completa, prefijo hex o nombre exacto."""
        if not query:
            return None
        q = query.strip().lower()

        # 1. Búsqueda exacta por clave pública
        if q in self._nodes_by_key:
            return self._nodes_by_key[q]

        # 2. Búsqueda por nombre o alias
        if q in self._nodes_by_name:
            target_key = self._nodes_by_name[q]
            return self._nodes_by_key.get(target_key)

        # 3. Búsqueda por prefijo de clave pública
        for key, contact in self._nodes_by_key.items():
            if key.startswith(q) or q.startswith(key):
                return contact

        return None

    def resolve_name(self, query: str) -> str:
        """Resuelve el nombre amigable de un nodo o devuelve el identificador original."""
        contact = self.get_by_key_or_prefix(query)
        if contact:
            return contact.alias or contact.name
        return query

    def list_nodes(self) -> list[dict[str, Any]]:
        """Retorna la lista de todos los nodos registrados en formato serializable."""
        return [c.to_dict() for c in self._nodes_by_key.values()]

    def get_count(self) -> int:
        return len(self._nodes_by_key)

    def cleanup_inactive(self, max_idle_seconds: float = 86400.0 * 7) -> int:
        """Elimina nodos inactivos que no hayan transmitido durante el período especificado."""
        now = time.time()
        to_remove = [
            k for k, c in self._nodes_by_key.items()
            if (now - c.last_seen) > max_idle_seconds
        ]
        for k in to_remove:
            contact = self._nodes_by_key.pop(k, None)
            if contact:
                self._nodes_by_name.pop(contact.name.lower(), None)
                self._nodes_by_name.pop(contact.alias.lower(), None)

        if to_remove:
            logging.info(f"Limpieza de NodeRegistry: eliminados {len(to_remove)} nodos obsoletos.")
        return len(to_remove)

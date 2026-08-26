"""
In-Memory Packet Deduplication Layer for MeshCore Bridge.
Filtro de deduplicación de alta velocidad en memoria RAM con ventana deslizante.
"""

from __future__ import annotations

import collections
import hashlib
import time


class PacketDeduplicator:
    """Filtro de deduplicación de alta velocidad en memoria RAM con ventana deslizante."""

    def __init__(self, window_seconds: float = 60.0, max_entries: int = 5000) -> None:
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        self._cache: collections.OrderedDict[str, float] = collections.OrderedDict()

    async def is_duplicate(self, key: str) -> bool:
        """Verifica si la clave ha sido vista recientemente dentro de la ventana de tiempo."""
        now = time.time()
        self._prune(now)

        if key in self._cache:
            last_seen = self._cache[key]
            if (now - last_seen) < self.window_seconds:
                return True

        self._cache[key] = now
        self._cache.move_to_end(key)

        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

        return False

    def is_duplicate_sync(self, key: str) -> bool:
        """Versión síncrona para comprobaciones directas."""
        now = time.time()
        self._prune(now)

        if key in self._cache:
            last_seen = self._cache[key]
            if (now - last_seen) < self.window_seconds:
                return True

        self._cache[key] = now
        self._cache.move_to_end(key)

        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

        return False

    def _prune(self, now: float) -> None:
        """Elimina entradas expiradas desde el inicio del OrderedDict."""
        threshold = now - self.window_seconds
        while self._cache:
            first_key, first_time = next(iter(self._cache.items()))
            if first_time < threshold:
                del self._cache[first_key]
            else:
                break

    @staticmethod
    def compute_hash(topic: str, payload: str) -> str:
        """Genera un hash SHA-256 corto del tópico y payload."""
        hasher = hashlib.sha256()
        hasher.update(topic.encode("utf-8"))
        hasher.update(b"::")
        hasher.update(payload.encode("utf-8"))
        return hasher.hexdigest()[:16]

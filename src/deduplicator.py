"""
In-Memory Packet Deduplication Layer for MeshCore Bridge.
Filtro de deduplicación de alta velocidad en memoria RAM con ventana deslizante.
"""

from __future__ import annotations

import collections
import threading
import time


class PacketDeduplicator:
    """Filtro de deduplicación de alta velocidad en memoria RAM con ventana deslizante.

    Unifica la sincronización bajo un único lock reentrante/atómico para eliminar
    el riesgo de bloqueo híbrido y asegurar coherencia entre corrutinas y llamadas síncronas.
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        max_entries: int = 5000,
        ttl_seconds: float | None = None,
        max_history: int | None = None,
    ) -> None:
        self.window_seconds = ttl_seconds if ttl_seconds is not None else window_seconds
        self.max_entries = max_history if max_history is not None else max_entries
        self._cache: collections.OrderedDict[str, tuple[float, float]] = collections.OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __bool__(self) -> bool:
        return True

    def _check_and_insert(self, key: str, window_override: float | None = None) -> bool:
        """Evalúa e inserta una clave en la ventana deslizante bajo protección de lock."""
        now = time.monotonic()
        self._prune(now)

        eff_window = window_override if window_override is not None else self.window_seconds
        if key in self._cache:
            last_seen, expires_at = self._cache[key]
            if now < expires_at and (now - last_seen) < eff_window:
                return True

        self._cache[key] = (now, now + eff_window)
        self._cache.move_to_end(key)

        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

        return False

    async def is_duplicate(self, key: str, window_override: float | None = None) -> bool:
        """Verifica de forma asíncrona si la clave ha sido vista recientemente dentro de la ventana."""
        with self._lock:
            return self._check_and_insert(key, window_override)

    def _prune(self, now: float) -> None:
        """Elimina entradas expiradas respetando window_override individual."""
        expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for k in expired:
            del self._cache[k]

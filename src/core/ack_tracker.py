"""ack_tracker.py: Registro, correlación y ciclo de vida de ACKs de entrega esperados."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class AckTracker:
    """Gestiona el seguimiento de confirmaciones de entrega de mensajes en memoria y base de datos."""

    def __init__(
        self,
        database_provider: Callable[[], Any] | None = None,
        persist_fn: Callable[..., Awaitable[Any]] | None = None,
        capacity: int = 200,
        ttl_sec: float = 3600.0,
    ) -> None:
        self.database_provider = database_provider
        self.persist_fn = persist_fn
        self.capacity = capacity
        self.ttl_sec = ttl_sec
        self.pending_acks: dict[str, dict[str, Any]] = {}

    def load_from_database(self, database: Any) -> None:
        """Carga los ACKs pendientes registrados previamente en la base de datos."""
        if database is not None and hasattr(database, "load_pending_acks"):
            self.pending_acks = database.load_pending_acks()
            now_mono = time.monotonic()
            now_epoch = time.time()
            for pending in self.pending_acks.values():
                ts = pending.get("timestamp", now_epoch)
                pending["registered_at"] = now_mono - max(0.0, now_epoch - ts)

    def prune(self) -> None:
        """Expira correlaciones de entrega que excedan el tiempo máximo acordado."""
        now = time.monotonic()
        expired = [
            key
            for key, info in self.pending_acks.items()
            if now - info.get("registered_at", float("-inf")) >= self.ttl_sec
        ]
        for key in expired:
            self.pending_acks.pop(key, None)

    def register(self, expected_ack: str, req_id: str, target: str = "") -> str:
        """Registra un ACK esperado acotado a la capacidad configurada sin pisar colisiones."""
        clean_ack = str(expected_ack).lower().strip()
        if clean_ack.startswith("0x"):
            clean_ack = clean_ack[2:]
        self.prune()
        if (
            len(clean_ack) != 8
            or any(char not in "0123456789abcdef" for char in clean_ack)
            or set(clean_ack) <= {"0"}
        ):
            return "invalid_ack"
        previous = self.pending_acks.get(clean_ack)
        if previous:
            if previous.get("req_id") == req_id and previous.get("target") == target:
                return "registered"
            logging.warning("ACK delivery tracking unavailable: collision; request_id=%s", req_id)
            return "collision"
        if len(self.pending_acks) >= self.capacity:
            logging.warning(
                "ACK delivery tracking unavailable: capacity_exceeded; request_id=%s", req_id
            )
            return "capacity_exceeded"
        self.pending_acks[clean_ack] = {
            "req_id": req_id,
            "timestamp": time.time(),
            "registered_at": time.monotonic(),
            "target": target,
        }
        return "registered"

    def resolve(self, ack_code: str) -> dict[str, Any] | None:
        """Resuelve y remueve de memoria el registro asociado a un código ACK recibido."""
        clean_ack = str(ack_code).lower().strip()
        if clean_ack.startswith("0x"):
            clean_ack = clean_ack[2:]
        self.prune()
        if not clean_ack or set(clean_ack) <= {"0"}:
            return None
        return self.pending_acks.pop(clean_ack, None)

    async def consume(
        self, ack_code: str, trip_time_ms: float | None = None
    ) -> dict[str, Any] | None:
        """Consume el ACK tanto en memoria como en almacenamiento durable."""
        memory = self.resolve(ack_code)
        database = self.database_provider() if self.database_provider else None
        if database is None:
            return memory
        if self.persist_fn is not None:
            durable = await self.persist_fn(database.consume_pending_ack, ack_code, trip_time_ms)
        else:
            durable = database.consume_pending_ack(ack_code, trip_time_ms)
        return durable or memory

    def remove(self, ack_code: str) -> None:
        """Remueve de memoria una clave de ACK específica."""
        clean = str(ack_code).lower().removeprefix("0x")
        self.pending_acks.pop(clean, None)

    def clear(self) -> None:
        """Limpia todos los ACKs pendientes en memoria."""
        self.pending_acks.clear()

"""
Base interfaces and context for the RxRouter Strategy Pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class MeshMessageEvent:
    """Representa un mensaje de texto normalizado recibido por RF."""

    sender: str
    sender_name: str
    text: str
    channel_idx: int
    rssi: float | int | None = None
    snr: float | None = None
    txt_type: int = 0


@dataclass(slots=True)
class RxMeta:
    """Metadatos extraídos y normalizados de una trama o evento recibido."""

    ev_type_str: str
    ev_upper: str
    sender: str
    sender_name: str
    text: str
    channel_idx: int
    hops: int
    effective_rssi: int | None
    effective_snr: float | None
    effective_hops: int
    is_local_sender: bool


class BaseRxHandler(Protocol):
    """Protocolo estructural para manejadores de eventos RF (Strategy Pattern)."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        """Determina si este manejador puede procesar el evento recibido."""
        ...

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        """
        Ejecuta el procesamiento y enrutamiento del evento.
        Retorna True si el evento fue procesado con éxito.
        """
        ...

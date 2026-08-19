"""
LoRa Transmission Rate Limiter & Airtime Manager for MeshCore Bridge.
Implementa una cola de prioridades asíncrona (PriorityQueue) y cálculo determinista
del tiempo en el aire (Airtime) según parámetros RF de LoRa (SF, BW, CR).
"""

from __future__ import annotations

import asyncio
import collections
import logging
import math
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class TxPriority(IntEnum):
    """Niveles de prioridad de transmisión."""
    HIGH = 0    # ACKs, Pings de Watchdog, Comandos Administrativos
    NORMAL = 1  # Mensajes de texto directo y canales secundarios
    LOW = 2     # Telemetría periódica, Anuncios y Broadcasts


@dataclass(frozen=True, slots=True)
class LoRaRadioConfig:
    """Parámetros de radio LoRa agrupados para evitar firmas con 8 argumentos."""
    sf: int = 11
    bw_khz: float = 250.0
    cr: int = 5
    preamble_len: int = 8
    has_crc: bool = True
    explicit_header: bool = True
    low_data_rate_opt: bool = False


def estimate_lora_airtime_ms(payload_len_bytes: int, radio: LoRaRadioConfig) -> float:
    """
    Calcula el tiempo de transmisión en el aire (Airtime) en milisegundos
    según la fórmula estándar de modulación LoRa de Semtech.
    """
    bw_hz = radio.bw_khz * 1000.0
    t_sym_ms = (2 ** radio.sf) / bw_hz * 1000.0
    t_preamble_ms = (radio.preamble_len + 4.25) * t_sym_ms

    ih = 0 if radio.explicit_header else 1
    de = 1 if radio.low_data_rate_opt or (radio.sf >= 11 and radio.bw_khz <= 125.0) else 0
    crc_val = 1 if radio.has_crc else 0

    term1 = 8 * payload_len_bytes - 4 * radio.sf + 28 + 16 * crc_val - 20 * ih
    term2 = 4 * (radio.sf - 2 * de)
    if term2 <= 0:
        term2 = 1

    payload_symbols_num = math.ceil(term1 / term2) * radio.cr
    symbol_count = 8 + max(payload_symbols_num, 0)
    t_payload_ms = symbol_count * t_sym_ms

    return float(round(t_preamble_ms + t_payload_ms, 2))


@dataclass(order=True)
class TxItem:
    """Elemento ordenable para asyncio.PriorityQueue con desempate por contador."""
    priority: int
    created_at: float
    counter: int
    payload: Any = field(compare=False)
    target: str | None = field(compare=False, default=None)
    channel_idx: int = field(compare=False, default=0)
    request_id: str | None = field(compare=False, default=None)
    estimated_airtime_ms: float = field(compare=False, default=100.0)
    future: asyncio.Future[Any] | None = field(compare=False, default=None)


class CustomTxQueue(asyncio.PriorityQueue[Any]):
    """Cola de prioridad que envuelve dicts o payloads heterogéneos evitando errores de comparación '<'."""

    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize=maxsize)
        self._seq = 0

    def _put(self, item: Any) -> None:
        self._seq += 1
        if isinstance(item, TxItem):
            wrapped = item
        elif isinstance(item, dict):
            prio = item.get("priority", 1)
            prio_int = int(prio) if prio is not None else 1
            target_val = item.get("to", item.get("target"))
            req_id_val = item.get("request_id", item.get("id"))
            raw_ch = item.get("channel_index", item.get("channel_idx", item.get("channel", 0)))
            ch_idx = int(raw_ch) if raw_ch is not None else 0

            wrapped = TxItem(
                priority=prio_int,
                created_at=time.time(),
                counter=self._seq,
                payload=item,
                target=str(target_val) if target_val is not None else None,
                channel_idx=ch_idx,
                request_id=str(req_id_val) if req_id_val is not None else None,
            )
        else:
            wrapped = TxItem(
                priority=1,
                created_at=time.time(),
                counter=self._seq,
                payload=item,
            )
        super()._put(wrapped)

    def _get(self) -> Any:
        return super()._get()


@dataclass
class AirtimeRecord:
    """Registro temporal de transmisión con tiempo de aire y canal."""
    timestamp: float
    airtime_ms: float
    channel_idx: int = 0
    target: str | None = None


class AirtimeTracker:
    """
    Rastreador de tiempo en el aire (Airtime) y cumplimiento de ciclo de trabajo (Duty Cycle)
    con soporte de ventanas deslizantes de 1 hora y 24 horas.
    """

    def __init__(self, duty_cycle_limit_pct: float = 1.0) -> None:
        self.duty_cycle_limit_pct = duty_cycle_limit_pct
        self._history: collections.deque[AirtimeRecord] = collections.deque()
        self.total_airtime_ms: float = 0.0
        self.total_packets: int = 0
        self._channel_airtime: dict[int, float] = {}
        self._channel_packets: dict[int, int] = {}

    def record_tx(self, airtime_ms: float, channel_idx: int = 0, target: str | None = None) -> None:
        """Registra una transmisión realizada."""
        now = time.time()
        rec = AirtimeRecord(timestamp=now, airtime_ms=airtime_ms, channel_idx=channel_idx, target=target)
        self._history.append(rec)
        self.total_airtime_ms += airtime_ms
        self.total_packets += 1
        self._channel_airtime[channel_idx] = self._channel_airtime.get(channel_idx, 0.0) + airtime_ms
        self._channel_packets[channel_idx] = self._channel_packets.get(channel_idx, 0) + 1
        self._prune(now)

    def _prune(self, now: float) -> None:
        """Elimina registros anteriores a 24 horas."""
        cutoff_24h = now - 86400.0
        while self._history and self._history[0].timestamp < cutoff_24h:
            self._history.popleft()

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadísticas completas de consumo de Airtime y Duty Cycle."""
        now = time.time()
        self._prune(now)

        cutoff_1h = now - 3600.0
        hourly_ms = 0.0
        daily_ms = 0.0
        hourly_pkts = 0

        for r in self._history:
            daily_ms += r.airtime_ms
            if r.timestamp >= cutoff_1h:
                hourly_ms += r.airtime_ms
                hourly_pkts += 1

        # Presupuesto de 1 hora: por ejemplo al 1% = 36,000 ms (36s)
        hourly_budget_ms = 3600.0 * 1000.0 * (self.duty_cycle_limit_pct / 100.0)
        duty_cycle_pct = (hourly_ms / 3600000.0) * 100.0

        is_throttled = duty_cycle_pct >= self.duty_cycle_limit_pct if self.duty_cycle_limit_pct > 0 else False

        return {
            "hourly_used_ms": round(hourly_ms, 1),
            "hourly_budget_ms": round(hourly_budget_ms, 1),
            "hourly_duty_cycle_pct": round(duty_cycle_pct, 3),
            "hourly_limit_pct": self.duty_cycle_limit_pct,
            "hourly_packets": hourly_pkts,
            "daily_used_ms": round(daily_ms, 1),
            "total_airtime_ms": round(self.total_airtime_ms, 1),
            "total_packets": self.total_packets,
            "is_throttled": is_throttled,
            "channel_stats": {
                ch: {
                    "airtime_ms": round(self._channel_airtime.get(ch, 0.0), 1),
                    "packets": self._channel_packets.get(ch, 0),
                }
                for ch in self._channel_airtime
            },
        }


class TxRateLimiter:
    """
    Gestor de tasa de transmisión LoRa con cola de prioridades y espaciado de seguridad.
    Evita saturar el transceptor LoRa SX1262/SX1276 y minimiza colisiones en el aire.
    """

    def __init__(
        self,
        tx_interval_sec: float = 1.0,
        radio_config: LoRaRadioConfig | None = None,
        transmit_callback: Callable[[Any], Awaitable[Any]] | None = None,
        duty_cycle_limit_pct: float = 1.0,
    ) -> None:
        self.tx_interval_sec = tx_interval_sec
        self.radio_config = radio_config or LoRaRadioConfig()
        self.transmit_callback = transmit_callback

        self.queue: CustomTxQueue = CustomTxQueue()
        self.airtime_tracker: AirtimeTracker = AirtimeTracker(duty_cycle_limit_pct=duty_cycle_limit_pct)
        self._seq_counter = 0
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self.total_transmitted = 0
        self.total_dropped = 0

    def start(self) -> None:
        """Inicia la tarea worker de procesamiento en segundo plano."""
        if self._worker_task is None or self._worker_task.done():
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop(), name="TxRateLimiterWorker")
            logging.debug("TxRateLimiter worker iniciado.")

    async def stop(self) -> None:
        """Detiene limpiamente el despachador de transmisión."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            logging.debug("TxRateLimiter worker detenido.")

    async def submit(
        self,
        payload: Any,
        priority: TxPriority = TxPriority.NORMAL,
        target: str | None = None,
        channel_idx: int = 0,
        request_id: str | None = None,
    ) -> asyncio.Future[Any]:
        """Encola una solicitud de transmisión con prioridad asignada."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        if isinstance(payload, bytes):
            plen = len(payload)
        elif isinstance(payload, str):
            plen = len(payload.encode("utf-8"))
        elif hasattr(payload, "pack"):
            plen = len(payload.pack())
        else:
            plen = 32

        airtime_ms = estimate_lora_airtime_ms(plen, self.radio_config)

        self._seq_counter += 1
        item = TxItem(
            priority=int(priority),
            created_at=time.time(),
            counter=self._seq_counter,
            payload=payload,
            target=target,
            channel_idx=channel_idx,
            request_id=request_id,
            estimated_airtime_ms=airtime_ms,
            future=future,
        )

        await self.queue.put(item)
        return future

    def get_queue_depth(self) -> int:
        """Retorna la cantidad de elementos encolados esperando emisión."""
        return self.queue.qsize()

    async def _worker_loop(self) -> None:
        """Bucle continuo que extrae y transmite elementos según su prioridad."""
        while self._running:
            try:
                item = await self.queue.get()
                if item is None:
                    continue

                if self.transmit_callback:
                    try:
                        res = await self.transmit_callback(item)
                        self.total_transmitted += 1
                        if isinstance(item, TxItem):
                            self.airtime_tracker.record_tx(
                                airtime_ms=item.estimated_airtime_ms,
                                channel_idx=item.channel_idx,
                                target=item.target,
                            )
                            if item.future and not item.future.done():
                                item.future.set_result(res)
                    except Exception as e:
                        logging.error(f"Error en callback de transmisión: {e}")
                        if isinstance(item, TxItem) and item.future and not item.future.done():
                            item.future.set_exception(e)
                else:
                    if isinstance(item, TxItem):
                        self.airtime_tracker.record_tx(
                            airtime_ms=item.estimated_airtime_ms,
                            channel_idx=item.channel_idx,
                            target=item.target,
                        )
                        if item.future and not item.future.done():
                            item.future.set_result({"status": "SENT_DRY_RUN", "airtime_ms": item.estimated_airtime_ms})

                self.queue.task_done()

                # Espaciado regulatorio
                airtime_sec = item.estimated_airtime_ms / 1000.0 if isinstance(item, TxItem) else 0.05
                jitter_sec = random.uniform(0.01, 0.05)
                delay = self.tx_interval_sec + (airtime_sec * 0.1) + jitter_sec
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error inesperado en TxRateLimiter: {e}", exc_info=True)
                await asyncio.sleep(0.1)

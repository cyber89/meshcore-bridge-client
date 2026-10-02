"""
LoRa Transmission Rate Limiter & Airtime Manager for MeshCore Bridge.
Implementa una cola de prioridades asíncrona (PriorityQueue) y cálculo determinista
del tiempo en el aire (Airtime) según parámetros RF de LoRa (SF, BW, CR).
"""

from __future__ import annotations

import asyncio
import collections
import heapq
import json
import logging
import math
import os
import random
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, cast


class TxPriority(IntEnum):
    """Niveles de prioridad de transmisión."""
    HIGH = 0    # ACKs, Pings de Watchdog, Comandos Administrativos
    NORMAL = 1  # Mensajes de texto directo y canales secundarios
    LOW = 2     # Telemetría periódica, Anuncios y Broadcasts

MAX_QUEUE_SIZE = 500


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
    según la fórmula estándar de modulación LoRa de Semtech (AN1200.13 / SX1276 / SX1262).
    """
    bw_hz = radio.bw_khz * 1000.0
    t_sym_ms = (2 ** radio.sf) / bw_hz * 1000.0
    t_preamble_ms = (radio.preamble_len + 4.25) * t_sym_ms

    ih = 0 if radio.explicit_header else 1
    # Semtech AN1200.13: LDRO (Low Data Rate Optimization) debe habilitarse si T_sym > 16.0 ms
    de = 1 if (radio.low_data_rate_opt or t_sym_ms > 16.0) else 0
    crc_val = 1 if radio.has_crc else 0

    term1 = 8 * payload_len_bytes - 4 * radio.sf + 28 + 16 * crc_val - 20 * ih
    term2 = 4 * (radio.sf - 2 * de)
    if term2 <= 0:
        term2 = 1

    # Normalizar multiplicador de coding rate (admite 5..8 para 4/5..4/8, o 1..4)
    cr_mult = radio.cr if radio.cr in (5, 6, 7, 8) else (radio.cr + 4 if radio.cr in (1, 2, 3, 4) else 5)
    payload_symbols_num = math.ceil(term1 / term2) * cr_mult
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

    def _evict_low_priority_if_needed(self) -> bool:
        """Si la cola está llena o supera MAX_QUEUE_SIZE, desaloja el elemento más antiguo de baja prioridad."""
        is_full_limit = self.full() or (self.qsize() >= MAX_QUEUE_SIZE)
        if is_full_limit:
            queue_list = cast(list[Any], getattr(self, "_queue", []))
            low_items = [x for x in queue_list if getattr(x, "priority", 1) >= 2]
            if low_items:
                oldest = min(low_items, key=lambda x: getattr(x, "counter", 0))
                queue_list.remove(oldest)
                heapq.heapify(queue_list)
                future = getattr(oldest, "future", None)
                if future is not None and not future.done():
                    future.set_exception(RuntimeError("Elemento TX desalojado por prioridad"))
                self.task_done()
                logging.warning("CustomTxQueue: Evicted oldest LOW priority item to make room.")
                return True
        return False

    def put_nowait(self, item: Any) -> None:
        self._evict_low_priority_if_needed()
        super().put_nowait(item)

    async def put(self, item: Any) -> None:
        self._evict_low_priority_if_needed()
        await super().put(item)

    def _put(self, item: Any) -> None:
        self._evict_low_priority_if_needed()
        self._seq += 1
        if isinstance(item, TxItem):
            wrapped = item
        elif isinstance(item, dict):
            prio = item.get("priority", 1)
            try:
                prio_int = int(prio) if prio is not None else 1
            except (ValueError, TypeError):
                prio_int = 1
            target_val = item.get("to", item.get("target"))
            req_id_val = item.get("request_id", item.get("id"))
            raw_ch = item.get("channel_index", item.get("channel_idx", item.get("channel", 0)))
            try:
                ch_idx = int(raw_ch) if raw_ch is not None else 0
            except (ValueError, TypeError):
                ch_idx = 0

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "airtime_ms": self.airtime_ms,
            "channel_idx": self.channel_idx,
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirtimeRecord:
        return cls(
            timestamp=float(data.get("timestamp", 0.0)),
            airtime_ms=float(data.get("airtime_ms", 0.0)),
            channel_idx=int(data.get("channel_idx", 0)),
            target=data.get("target"),
        )


class AirtimeTracker:
    """
    Rastreador de tiempo en el aire (Airtime) y cumplimiento de ciclo de trabajo (Duty Cycle)
    con soporte de ventanas deslizantes de 1 hora y 24 horas, alertas progresivas de dos niveles
    (preventiva 80% y crítica 100%) y persistencia atómica en disco.
    """

    def __init__(
        self,
        duty_cycle_limit_pct: float = 1.0,
        warn_threshold_pct: float = 80.0,
        history_file: str | None = None,
        on_alert_callback: Callable[[str, dict[str, Any]], None] | None = None,
        cutoff_threshold_pct: float = 35.0,
        cutoff_resume_pct: float = 30.0,
        cutoff_enabled: bool = True,
        on_cutoff_change_callback: Callable[[bool, float], None] | None = None,
    ) -> None:
        self.duty_cycle_limit_pct = duty_cycle_limit_pct
        self.warn_threshold_pct = warn_threshold_pct
        self.history_file = history_file
        self.on_alert_callback = on_alert_callback
        self.cutoff_threshold_pct = cutoff_threshold_pct
        self.cutoff_resume_pct = cutoff_resume_pct
        self.cutoff_enabled = cutoff_enabled
        self.on_cutoff_change_callback = on_cutoff_change_callback

        self._history: collections.deque[AirtimeRecord] = collections.deque()
        self.total_airtime_ms: float = 0.0
        self.total_packets: int = 0
        self._channel_airtime: dict[int, float] = {}
        self._channel_packets: dict[int, int] = {}
        self._current_status: str = "normal"  # "normal", "warning", "critical"
        self._last_save_time: float = 0.0
        self._save_task: asyncio.Task[None] | None = None
        self._pending_save: dict[str, Any] | None = None
        self._save_lock = threading.Lock()
        self._lock = threading.Lock()
        self._last_tx_time: float | None = None
        self._channel_utilization_pct: float = 0.0
        self._cutoff_active: bool = False

        if self.history_file:
            self.load_history()

    def load_history(self) -> None:
        """Carga y rehidrata el historial de transmisiones desde el archivo persistente en disco."""
        if not self.history_file or not os.path.isfile(self.history_file):
            return
        try:
            with open(self.history_file, encoding="utf-8") as f:
                data = json.load(f)

            now = time.time()
            cutoff_24h = now - 86400.0
            recs = data.get("records", [])
            loaded_count = 0

            with self._lock:
                has_saved_totals = "total_airtime_ms" in data and "total_packets" in data
                if has_saved_totals:
                    self.total_airtime_ms = float(data.get("total_airtime_ms", 0.0))
                    self.total_packets = int(data.get("total_packets", 0))
                else:
                    self.total_airtime_ms = 0.0
                    self.total_packets = 0

                sum_loaded_airtime = 0.0
                sum_loaded_packets = 0

                for r_data in recs:
                    try:
                        rec = AirtimeRecord.from_dict(r_data)
                        if rec.timestamp >= cutoff_24h:
                            self._history.append(rec)
                            sum_loaded_airtime += rec.airtime_ms
                            sum_loaded_packets += 1
                            self._channel_airtime[rec.channel_idx] = (
                                self._channel_airtime.get(rec.channel_idx, 0.0) + rec.airtime_ms
                            )
                            self._channel_packets[rec.channel_idx] = (
                                self._channel_packets.get(rec.channel_idx, 0) + 1
                            )
                            if self._last_tx_time is None or rec.timestamp > self._last_tx_time:
                                self._last_tx_time = rec.timestamp
                            loaded_count += 1
                    except Exception:
                        continue

                if has_saved_totals:
                    self.total_airtime_ms = max(self.total_airtime_ms, sum_loaded_airtime)
                    self.total_packets = max(self.total_packets, sum_loaded_packets)
                else:
                    self.total_airtime_ms = sum_loaded_airtime
                    self.total_packets = sum_loaded_packets

                if "duty_cycle_limit_pct" in data:
                    try:
                        self.duty_cycle_limit_pct = float(data["duty_cycle_limit_pct"])
                    except (ValueError, TypeError):
                        pass
                if "warn_threshold_pct" in data:
                    try:
                        self.warn_threshold_pct = float(data["warn_threshold_pct"])
                    except (ValueError, TypeError):
                        pass
                if "cutoff_threshold_pct" in data:
                    try:
                        self.cutoff_threshold_pct = float(data["cutoff_threshold_pct"])
                    except (ValueError, TypeError):
                        pass
                if "cutoff_resume_pct" in data:
                    try:
                        self.cutoff_resume_pct = float(data["cutoff_resume_pct"])
                    except (ValueError, TypeError):
                        pass
                if "cutoff_enabled" in data:
                    self.cutoff_enabled = bool(data["cutoff_enabled"])

                self._channel_utilization_pct = float(data.get("channel_utilization_pct", 0.0))
                if self.cutoff_enabled:
                    self._cutoff_active = bool(data.get("cutoff_active", False))

            stats = self.get_stats()
            self._current_status = stats["status_level"]
            logging.info(
                f"AirtimeTracker: Rehidratados {loaded_count} registros de airtime desde {self.history_file}. "
                f"Consumo 1h: {stats['hourly_used_ms']}ms ({stats['hourly_duty_cycle_pct']}%), Estado: {self._current_status}, "
                f"Cutoff: {'ACTIVO' if self._cutoff_active else 'INACTIVO'} ({self._channel_utilization_pct}% ocupación)."
            )
        except Exception as e:
            logging.warning(f"AirtimeTracker: No se pudo cargar historial previo de {self.history_file}: {e}")

    def save_history(self, sync: bool = False) -> None:
        """Guarda atómicamente el historial activo (ventana 24h) en disco."""
        if not self.history_file:
            return

        now = time.time()
        if not sync and (now - self._last_save_time) < 10.0:
            return

        with self._lock:
            self._prune(now)
            payload: dict[str, Any] = {
                "version": 1, "saved_at": now,
                "duty_cycle_limit_pct": self.duty_cycle_limit_pct,
                "warn_threshold_pct": self.warn_threshold_pct,
                "total_airtime_ms": round(self.total_airtime_ms, 1),
                "total_packets": self.total_packets,
                "channel_utilization_pct": round(self._channel_utilization_pct, 2),
                "cutoff_active": self._cutoff_active,
                "cutoff_threshold_pct": self.cutoff_threshold_pct,
                "cutoff_resume_pct": self.cutoff_resume_pct,
                "cutoff_enabled": self.cutoff_enabled,
                "records": [r.to_dict() for r in self._history],
            }
        self._last_save_time = now
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._write_history(payload)
            return
        self._pending_save = payload
        if self._save_task is None or self._save_task.done():
            self._save_task = loop.create_task(self._drain_history(), name="AirtimePersistence")

    def _write_history(self, payload: dict[str, Any]) -> None:
        """Write an immutable snapshot; serialize writers sharing the atomic temp path."""
        if not self.history_file:
            return
        with self._save_lock:
            try:
                target_dir = os.path.dirname(os.path.abspath(self.history_file))
                os.makedirs(target_dir, exist_ok=True)
                temp_path = f"{self.history_file}.tmp"
                with open(temp_path, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, indent=2)
                os.replace(temp_path, self.history_file)
            except Exception:
                logging.warning("AirtimeTracker: Error al persistir historial")

    async def _drain_history(self) -> None:
        try:
            while self._pending_save is not None:
                payload, self._pending_save = self._pending_save, None
                await asyncio.to_thread(self._write_history, payload)
        finally:
            self._save_task = None

    async def flush_history(self) -> None:
        """Snapshot the final state on the loop and wait for the owned disk writer."""
        self.save_history(sync=True)
        if self._save_task is not None:
            await asyncio.shield(self._save_task)


    def record_tx(self, airtime_ms: float, channel_idx: int = 0, target: str | None = None) -> None:
        """Registra una transmisión realizada y evalúa alertas de umbral progresivo."""
        now = time.time()
        rec = AirtimeRecord(timestamp=now, airtime_ms=airtime_ms, channel_idx=channel_idx, target=target)
        with self._lock:
            self._history.append(rec)
            self.total_airtime_ms += airtime_ms
            self.total_packets += 1
            self._last_tx_time = now
            self._channel_airtime[channel_idx] = self._channel_airtime.get(channel_idx, 0.0) + airtime_ms
            self._channel_packets[channel_idx] = self._channel_packets.get(channel_idx, 0) + 1
            self._prune(now)

        stats = self.get_stats()
        new_status = stats["status_level"]
        status_changed = new_status != self._current_status
        if status_changed:
            old_status = self._current_status
            self._current_status = new_status
            if new_status == "critical":
                logging.warning(
                    f"⚠️ ALERTA CRÍTICA: Duty Cycle LoRa al {stats['hourly_duty_cycle_pct']}% "
                    f"(límite {self.duty_cycle_limit_pct}% superado). Consumo: {stats['hourly_used_ms']}ms / {stats['hourly_budget_ms']}ms."
                )
            elif new_status == "warning":
                logging.warning(
                    f"⚠️ ADVERTENCIA: Duty Cycle LoRa al {stats['hourly_duty_cycle_pct']}% "
                    f"(alcanzado {self.warn_threshold_pct}% del cupo horario de {self.duty_cycle_limit_pct}%)."
                )
            elif new_status == "normal" and old_status != "normal":
                logging.info(
                    f"✅ Duty Cycle LoRa restablecido a nivel normal: {stats['hourly_duty_cycle_pct']}%."
                )

            if self.on_alert_callback:
                try:
                    self.on_alert_callback(new_status, stats)
                except Exception as e:
                    logging.error(f"Error en on_alert_callback de AirtimeTracker: {e}")

        self.save_history(sync=status_changed)

    def _prune(self, now: float) -> None:
        """Elimina registros anteriores a 24 horas. El invocador DEBE sostener self._lock."""
        cutoff_24h = now - 86400.0
        while self._history and self._history[0].timestamp < cutoff_24h:
            self._history.popleft()

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadísticas completas de consumo de Airtime, Duty Cycle y estado de alertas."""
        now = time.time()
        with self._lock:
            self._prune(now)
            records_snapshot = list(self._history)
            total_airtime = self.total_airtime_ms
            total_pkts = self.total_packets
            ch_util = self._channel_utilization_pct
            cutoff_act = self._cutoff_active
            last_tx = self._last_tx_time
            ch_airtime_copy = {ch: round(ms, 1) for ch, ms in self._channel_airtime.items()}
            ch_packets_copy = dict(self._channel_packets)

        cutoff_1h = now - 3600.0
        hourly_ms = 0.0
        daily_ms = 0.0
        hourly_pkts = 0

        for r in records_snapshot:
            daily_ms += r.airtime_ms
            if r.timestamp >= cutoff_1h:
                hourly_ms += r.airtime_ms
                hourly_pkts += 1

        hourly_budget_ms = 3600.0 * 1000.0 * (self.duty_cycle_limit_pct / 100.0)
        duty_cycle_pct = (hourly_ms / 3600000.0) * 100.0 if hourly_ms > 0 else 0.0
        warn_duty_pct = self.duty_cycle_limit_pct * (self.warn_threshold_pct / 100.0)

        is_critical = duty_cycle_pct >= self.duty_cycle_limit_pct if self.duty_cycle_limit_pct > 0 else False
        is_warning = (not is_critical) and (duty_cycle_pct >= warn_duty_pct) if self.duty_cycle_limit_pct > 0 else False

        if is_critical:
            status_level = "critical"
        elif is_warning:
            status_level = "warning"
        else:
            status_level = "normal"

        return {
            "hourly_used_ms": round(hourly_ms, 1),
            "hourly_budget_ms": round(hourly_budget_ms, 1),
            "hourly_duty_cycle_pct": round(duty_cycle_pct, 3),
            "hourly_limit_pct": self.duty_cycle_limit_pct,
            "warn_threshold_pct": self.warn_threshold_pct,
            "hourly_packets": hourly_pkts,
            "daily_used_ms": round(daily_ms, 1),
            "total_airtime_ms": round(total_airtime, 1),
            "total_packets": total_pkts,
            "is_throttled": is_critical,
            "is_warning": is_warning,
            "is_critical": is_critical,
            "status_level": status_level,
            "channel_utilization_pct": round(ch_util, 2),
            "cutoff_active": cutoff_act if self.cutoff_enabled else False,
            "cutoff_enabled": self.cutoff_enabled,
            "cutoff_threshold_pct": self.cutoff_threshold_pct,
            "cutoff_resume_pct": self.cutoff_resume_pct,
            "last_tx_time": last_tx,
            "channel_stats": {
                ch: {
                    "airtime_ms": ch_airtime_copy.get(ch, 0.0),
                    "packets": ch_packets_copy.get(ch, 0),
                }
                for ch in ch_airtime_copy
            },
        }

    def update_channel_utilization(self, ch_util_pct: float) -> bool:
        """
        Actualiza el porcentaje de ocupación del canal LoRa (ChUtil) recibido de telemetría
        o calculado localmente. Evalúa y conmuta el estado de Airtime Cutoff con histéresis.
        Retorna True si hubo cambio de estado (activo/inactivo).
        """
        val = max(0.0, min(100.0, round(float(ch_util_pct), 2)))
        state_changed = False
        log_msg: str | None = None
        log_is_warning = False

        with self._lock:
            self._channel_utilization_pct = val

            if self.cutoff_enabled:
                if not self._cutoff_active and val >= self.cutoff_threshold_pct:
                    self._cutoff_active = True
                    state_changed = True
                    log_is_warning = True
                    log_msg = (
                        f"⚠️ AIRTIME CUTOFF ACTIVADO: Ocupación de canal al {val}% >= {self.cutoff_threshold_pct}%. "
                        "Sondeos periódicos de telemetría y pings automáticos suspendidos temporalmente."
                    )
                elif self._cutoff_active and val <= self.cutoff_resume_pct:
                    self._cutoff_active = False
                    state_changed = True
                    log_is_warning = False
                    log_msg = (
                        f"✅ AIRTIME CUTOFF DESACTIVADO: Ocupación de canal normalizada a {val}% <= {self.cutoff_resume_pct}%. "
                        "Reanudando sondeos periódicos y tareas normales de red."
                    )
            cutoff_active = self._cutoff_active
            ch_util = self._channel_utilization_pct

        if log_msg:
            if log_is_warning:
                logging.warning(log_msg)
            else:
                logging.info(log_msg)

        if state_changed:
            self.save_history(sync=True)
            if self.on_cutoff_change_callback:
                try:
                    self.on_cutoff_change_callback(cutoff_active, ch_util)
                except Exception as e:
                    logging.error(f"Error en on_cutoff_change_callback de AirtimeTracker: {e}")

        return state_changed

    def is_cutoff_active(self) -> bool:
        """Indica si el Airtime Cutoff está activo (deben suspenderse tareas automáticas no críticas)."""
        with self._lock:
            return bool(self.cutoff_enabled and self._cutoff_active)


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
        warn_threshold_pct: float = 80.0,
        history_file: str | None = None,
        on_alert_callback: Callable[[str, dict[str, Any]], None] | None = None,
        cutoff_threshold_pct: float = 35.0,
        cutoff_resume_pct: float = 30.0,
        cutoff_enabled: bool = True,
        on_cutoff_change_callback: Callable[[bool, float], None] | None = None,
    ) -> None:
        self.tx_interval_sec = tx_interval_sec
        self.radio_config = radio_config or LoRaRadioConfig()
        self.transmit_callback = transmit_callback

        import os
        MAX_TX_QUEUE_SIZE = int(os.getenv("MAX_TX_QUEUE_SIZE", "500"))
        self.queue: CustomTxQueue = CustomTxQueue(maxsize=MAX_TX_QUEUE_SIZE)
        self.airtime_tracker: AirtimeTracker = AirtimeTracker(
            duty_cycle_limit_pct=duty_cycle_limit_pct,
            warn_threshold_pct=warn_threshold_pct,
            history_file=history_file,
            on_alert_callback=on_alert_callback,
            cutoff_threshold_pct=cutoff_threshold_pct,
            cutoff_resume_pct=cutoff_resume_pct,
            cutoff_enabled=cutoff_enabled,
            on_cutoff_change_callback=on_cutoff_change_callback,
        )
        self._seq_counter = 0
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False

    def update_channel_utilization(self, ch_util_pct: float) -> bool:
        """Actualiza la ocupación de canal y evalúa si activa/desactiva el Airtime Cutoff."""
        return self.airtime_tracker.update_channel_utilization(ch_util_pct)

    def is_cutoff_active(self) -> bool:
        """Indica si el Airtime Cutoff dinámico está actualmente activo."""
        return self.airtime_tracker.is_cutoff_active()


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

        drained = 0
        while not self.queue.empty():
            try:
                orphan = self.queue.get_nowait()
                if isinstance(orphan, TxItem) and orphan.future and not orphan.future.done():
                    orphan.future.cancel()
                self.queue.task_done()
                drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            logging.debug("TxRateLimiter: drenados %d items huérfanos al detener.", drained)

        # Persistir historial de transmisiones en disco de forma segura
        await self.airtime_tracker.flush_history()
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

        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            logging.warning("TxRateLimiter queue is full, dropping item.")
            future.set_exception(asyncio.QueueFull("Queue Full"))
        return future

    def get_queue_depth(self) -> int:
        """Retorna la cantidad de elementos encolados esperando emisión."""
        return self.queue.qsize()

    async def _worker_loop(self) -> None:
        """Bucle continuo que extrae y transmite elementos según su prioridad."""
        while self._running:
            try:
                item = await self.queue.get()
                try:
                    if item is None:
                        continue
                    if isinstance(item, TxItem) and item.future is not None and item.future.cancelled():
                        continue

                    # Protección de Airtime LoRa: Si estamos en estado crítico (100% de duty cycle),
                    # descartar paquetes de baja prioridad (telemetría/anuncios) para no violar el límite legal.
                    if isinstance(item, TxItem) and item.priority >= int(TxPriority.LOW):
                        stats = self.airtime_tracker.get_stats()
                        if stats.get("is_critical"):
                            logging.warning(
                                f"TxRateLimiter: Descartando paquete de baja prioridad (prio={item.priority}) "
                                f"debido a saturación de Duty Cycle ({stats.get('hourly_duty_cycle_pct')}% >= {self.airtime_tracker.duty_cycle_limit_pct}%)."
                            )
                            if item.future and not item.future.done():
                                item.future.set_exception(
                                    RuntimeError(f"Duty cycle LoRa al 100% ({stats.get('hourly_duty_cycle_pct')}%), paquete de baja prioridad suspendido")
                                )
                            continue

                    if self.transmit_callback:
                        try:
                            res = await self.transmit_callback(item)
                            if isinstance(item, TxItem):
                                if isinstance(res, dict) and str(res.get("status", "")).lower() in ("sent", "ok", "success"):
                                    self.airtime_tracker.record_tx(
                                        airtime_ms=item.estimated_airtime_ms,
                                        channel_idx=item.channel_idx,
                                        target=item.target,
                                    )
                                if item.future and not item.future.done():
                                    item.future.set_result(res)
                        except asyncio.CancelledError:
                            if isinstance(item, TxItem) and item.future and not item.future.done():
                                item.future.cancel()
                            raise
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
                finally:
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

"""
MetricsAggregator: Agregador en memoria de series temporales y telemetría de tráfico LoRa.
Mantiene cubos temporales rodantes (últimas 24 horas a resolución de 1 minuto) para
alimentar visualizaciones gráficas de tráfico (RX vs TX), eficiencia de enrutamiento
(Flood vs Directo), distribución por tipo de trama y diagnóstico de errores.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

CANONICAL_TYPES = ("CHAT", "ADVERT", "TELEMETRY", "TRACEROUTE", "PING", "ADMIN", "OTHER")
CANONICAL_ERRORS = ("crc_errors", "timeouts", "queue_overflow", "airtime_cutoff", "other")


@dataclass(slots=True)
class MinuteBucket:
    """Representa las métricas agregadas en un intervalo de un minuto."""
    timestamp: int  # Timestamp de inicio de minuto (múltiplo de 60)
    rx_packets: int = 0
    tx_packets: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    flood_rx: int = 0
    flood_tx: int = 0
    direct_rx: int = 0
    direct_tx: int = 0
    errors: int = 0
    crc_errors: int = 0
    timeouts: int = 0
    queue_overflow: int = 0
    airtime_cutoff: int = 0
    type_counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CANONICAL_TYPES, 0))


class MetricsAggregator:
    """
    Agregador en memoria de alto rendimiento y bajo consumo RAM (< 100 KB).
    Almacena hasta 1440 cubos de 1 minuto (24 horas continuas de tráfico).
    """

    def __init__(self, max_minutes: int = 1440) -> None:
        self.max_minutes = max_minutes
        self._lock = threading.Lock()
        self._buckets: deque[MinuteBucket] = deque(maxlen=max_minutes)
        self.start_time = time.time()

        # Contadores acumulativos de sesión
        self.total_rx_packets = 0
        self.total_tx_packets = 0
        self.total_rx_bytes = 0
        self.total_tx_bytes = 0
        self.total_flood_rx = 0
        self.total_flood_tx = 0
        self.total_direct_rx = 0
        self.total_direct_tx = 0

        self.type_totals: dict[str, int] = dict.fromkeys(CANONICAL_TYPES, 0)
        self.error_totals: dict[str, int] = dict.fromkeys(CANONICAL_ERRORS, 0)

        # Últimos valores de radio conocidos
        self.last_snr: float | None = None
        self.last_rssi: int | None = None
        self.last_noise_floor_dbm: int | None = None

    def _normalize_type(self, raw_type: str) -> str:
        """Mapea tipos de trama crudos a categorías canónicas."""
        t = str(raw_type or "").upper().strip()
        if any(k in t for k in ("TEXT", "CHAT", "DM", "MSG")):
            return "CHAT"
        if any(k in t for k in ("ADV", "DISCOVERY")):
            return "ADVERT"
        if any(k in t for k in ("TELEM", "SENSOR", "BATTERY", "STATUS", "POS", "GPS")):
            return "TELEMETRY"
        if any(k in t for k in ("TRACE", "ROUTE")):
            return "TRACEROUTE"
        if any(k in t for k in ("PING", "PONG")):
            return "PING"
        if any(k in t for k in ("ADMIN", "CONFIG", "REBOOT", "OTA")):
            return "ADMIN"
        return "OTHER"

    def _get_or_create_bucket(self, ts: float) -> MinuteBucket:
        """Obtiene el cubo correspondiente al minuto dado o crea los intermedios."""
        minute_ts = (int(ts) // 60) * 60

        if not self._buckets:
            bucket = MinuteBucket(timestamp=minute_ts)
            self._buckets.append(bucket)
            return bucket

        last_bucket = self._buckets[-1]
        if last_bucket.timestamp == minute_ts:
            return last_bucket

        if minute_ts > last_bucket.timestamp:
            # Rellenar minutos faltantes si hay un salto temporal (máx 1440)
            gap_seconds = minute_ts - last_bucket.timestamp
            gap_minutes = min(gap_seconds // 60, self.max_minutes)

            cur_ts = last_bucket.timestamp
            for _ in range(1, gap_minutes):
                cur_ts += 60
                self._buckets.append(MinuteBucket(timestamp=cur_ts))

            new_bucket = MinuteBucket(timestamp=minute_ts)
            self._buckets.append(new_bucket)
            return new_bucket

        # Trama rezagada: buscar cubo histórico
        for b in reversed(self._buckets):
            if b.timestamp == minute_ts:
                return b

        # Si es más viejo que el búfer, devolver el primero disponible
        return self._buckets[0]

    def record_packet(
        self,
        direction: str,
        packet_type: str = "PACKET",
        target: str = "broadcast",
        size_bytes: int = 0,
        snr: float | None = None,
        rssi: int | None = None,
        timestamp: float | None = None,
        error: str | None = None,
    ) -> None:
        """Registra un paquete RX o TX en las series temporales y contadores acumulativos."""
        ts = timestamp if timestamp is not None else time.time()
        is_rx = str(direction).lower() == "rx"
        canon_type = self._normalize_type(packet_type)

        target_str = str(target or "").lower().strip()
        is_flood = (
            not target_str
            or target_str in ("broadcast", "*", "ffffffffffff")
            or target_str.startswith("broadcast")
        )

        with self._lock:
            bucket = self._get_or_create_bucket(ts)

            if is_rx:
                self.total_rx_packets += 1
                self.total_rx_bytes += size_bytes
                bucket.rx_packets += 1
                bucket.rx_bytes += size_bytes
                if is_flood:
                    self.total_flood_rx += 1
                    bucket.flood_rx += 1
                else:
                    self.total_direct_rx += 1
                    bucket.direct_rx += 1
            else:
                self.total_tx_packets += 1
                self.total_tx_bytes += size_bytes
                bucket.tx_packets += 1
                bucket.tx_bytes += size_bytes
                if is_flood:
                    self.total_flood_tx += 1
                    bucket.flood_tx += 1
                else:
                    self.total_direct_tx += 1
                    bucket.direct_tx += 1

            self.type_totals[canon_type] = self.type_totals.get(canon_type, 0) + 1
            bucket.type_counts[canon_type] = bucket.type_counts.get(canon_type, 0) + 1

            if snr is not None:
                self.last_snr = round(float(snr), 1)
            if rssi is not None:
                self.last_rssi = int(rssi)

            if error:
                self._record_error_locked(bucket, error)

    def record_error(self, category: str = "other", timestamp: float | None = None) -> None:
        """Registra un evento de error de red o de transmisión."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            bucket = self._get_or_create_bucket(ts)
            self._record_error_locked(bucket, category)

    def _record_error_locked(self, bucket: MinuteBucket, category: str) -> None:
        """Incrementa los contadores de error de forma segura con el lock adquirido."""
        cat = str(category).lower().strip()
        matched = "other"
        if "crc" in cat:
            matched = "crc_errors"
            bucket.crc_errors += 1
        elif "timeout" in cat or "ack" in cat:
            matched = "timeouts"
            bucket.timeouts += 1
        elif "queue" in cat or "overflow" in cat:
            matched = "queue_overflow"
            bucket.queue_overflow += 1
        elif "cutoff" in cat or "duty" in cat or "airtime" in cat:
            matched = "airtime_cutoff"
            bucket.airtime_cutoff += 1

        bucket.errors += 1
        self.error_totals[matched] = self.error_totals.get(matched, 0) + 1

    def get_time_series(self, range_str: str = "24h") -> list[dict[str, Any]]:
        """
        Retorna las series temporales agregadas para el rango solicitado.
        - '1h': 60 puntos (1 min por punto)
        - '6h': 72 puntos (5 min por punto)
        - '24h': 96 puntos (15 min por punto)
        """
        now = time.time()
        current_minute = (int(now) // 60) * 60

        if range_str == "1h":
            num_points = 60
            bucket_step_sec = 60
        elif range_str == "6h":
            num_points = 72
            bucket_step_sec = 300  # 5 minutos
        else:  # '24h' por defecto
            num_points = 96
            bucket_step_sec = 900  # 15 minutos

        start_ts = current_minute - (num_points * bucket_step_sec)

        with self._lock:
            # Crear mapa de búsqueda rápida por timestamp de minuto
            bucket_map = {b.timestamp: b for b in self._buckets}

        result: list[dict[str, Any]] = []

        for i in range(num_points):
            slot_start = start_ts + (i * bucket_step_sec)
            slot_end = slot_start + bucket_step_sec

            slot_rx = 0
            slot_tx = 0
            slot_flood = 0
            slot_direct = 0
            slot_errors = 0

            # Acumular minutos dentro del intervalo de este punto
            cur = slot_start
            while cur < slot_end:
                b = bucket_map.get(cur)
                if b is not None:
                    slot_rx += b.rx_packets
                    slot_tx += b.tx_packets
                    slot_flood += (b.flood_rx + b.flood_tx)
                    slot_direct += (b.direct_rx + b.direct_tx)
                    slot_errors += b.errors
                cur += 60

            result.append({
                "timestamp": slot_start,
                "rx": slot_rx,
                "tx": slot_tx,
                "flood": slot_flood,
                "direct": slot_direct,
                "errors": slot_errors,
            })

        return result

    def get_summary(self, range_str: str = "24h") -> dict[str, Any]:
        """Genera el payload analítico completo consolidado con series temporales."""
        with self._lock:
            total_rx = self.total_rx_packets
            total_tx = self.total_tx_packets
            total_flood_rx = self.total_flood_rx
            total_flood_tx = self.total_flood_tx
            total_direct_rx = self.total_direct_rx
            total_direct_tx = self.total_direct_tx
            type_breakdown = dict(self.type_totals)
            err_breakdown = dict(self.error_totals)
            last_snr = self.last_snr
            last_rssi = self.last_rssi
            last_noise = self.last_noise_floor_dbm

        total_packets = total_rx + total_tx
        total_flood = total_flood_rx + total_flood_tx
        total_direct = total_direct_rx + total_direct_tx
        total_errors = sum(err_breakdown.values())

        flood_ratio_pct = round((total_flood / (total_packets or 1)) * 100, 1)
        error_rate_pct = round((total_errors / (total_packets or 1)) * 100, 2)

        time_series = self.get_time_series(range_str)

        return {
            "summary": {
                "total_rx_packets": total_rx,
                "total_tx_packets": total_tx,
                "total_errors": total_errors,
                "global_error_rate_pct": error_rate_pct,
            },
            "routing_efficiency": {
                "flood_tx": total_flood_tx,
                "direct_tx": total_direct_tx,
                "flood_rx": total_flood_rx,
                "direct_rx": total_direct_rx,
                "total_flood": total_flood,
                "total_direct": total_direct,
                "flood_ratio_pct": flood_ratio_pct,
            },
            "packet_type_breakdown": type_breakdown,
            "error_breakdown": err_breakdown,
            "radio_metrics": {
                "last_snr": last_snr,
                "last_rssi": last_rssi,
                "noise_floor_dbm": last_noise,
            },
            "time_series": {
                "range": range_str,
                "points": time_series,
            },
        }

    def reset(self) -> None:
        """Restablece todos los cubos temporales y contadores acumulativos."""
        with self._lock:
            self._buckets.clear()
            self.total_rx_packets = 0
            self.total_tx_packets = 0
            self.total_rx_bytes = 0
            self.total_tx_bytes = 0
            self.total_flood_rx = 0
            self.total_flood_tx = 0
            self.total_direct_rx = 0
            self.total_direct_tx = 0
            self.type_totals = dict.fromkeys(CANONICAL_TYPES, 0)
            self.error_totals = dict.fromkeys(CANONICAL_ERRORS, 0)
            self.last_snr = None
            self.last_rssi = None
            self.start_time = time.time()

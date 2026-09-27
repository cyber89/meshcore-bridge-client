"""
MeshCore Bridge - Dynamic Link Quality Index (LQI) & Optimal Route Engine.
Motor determinista de cálculo de Calidad de Enlace (LQI) para redes malladas LoRa.
Calcula métricas combinadas de SNR, RSSI, penalización de saltos (Hop Penalty),
suavizado mediante Media Móvil Exponencial (EMA) y decaimiento por inactividad temporal.
"""

from __future__ import annotations

import time
from enum import Enum


class LQIStatus(str, Enum):
    """Clasificación cualitativa de la calidad de enlace."""
    EXCELLENT = "EXCELLENT"      # >= 80% (Verde)
    GOOD = "GOOD"                # 60% - 79% (Azul)
    FAIR = "FAIR"                # 40% - 59% (Amarillo)
    POOR = "POOR"                # 1% - 39% (Naranja)
    UNREACHABLE = "UNREACHABLE"  # 0% (Rojo / Inaccesible)


class LinkQualityEngine:
    """Motor de cálculo y evaluación de calidad de enlace LoRa."""

    # Rango operativo estándar para LoRa Semtech
    MIN_SNR: float = -20.0
    MAX_SNR: float = 10.0
    MIN_RSSI: float = -125.0
    MAX_RSSI: float = -40.0

    # Pesos relativos de señal
    WEIGHT_SNR: float = 0.65
    WEIGHT_RSSI: float = 0.35
    PENALTY_PER_HOP: float = 15.0

    # Coeficiente EMA
    DEFAULT_ALPHA: float = 0.30

    # Decaimiento por inactividad
    INACTIVITY_THRESHOLD_SEC: float = 180.0  # 3 minutos
    DECAY_RATE_PER_MINUTE: float = 0.10      # 10% por minuto de inactividad

    @classmethod
    def compute_instant_lqi(
        cls,
        snr: float | None,
        rssi: int | float | None,
        hops: int = 0,
    ) -> float:
        """
        Calcula la puntuación LQI instantánea (0.0 a 100.0%) a partir de SNR, RSSI y saltos.
        """
        if snr is None and rssi is None:
            return 0.0

        # 1. Normalizar SNR (-20dB a +10dB -> 0% a 100%)
        if snr is not None:
            snr_clamped = max(cls.MIN_SNR, min(cls.MAX_SNR, float(snr)))
            snr_norm = ((snr_clamped - cls.MIN_SNR) / (cls.MAX_SNR - cls.MIN_SNR)) * 100.0
        else:
            snr_norm = 50.0  # Valor neutral si falta SNR

        # 2. Normalizar RSSI (-125dBm a -40dBm -> 0% a 100%)
        if rssi is not None:
            rssi_clamped = max(cls.MIN_RSSI, min(cls.MAX_RSSI, float(rssi)))
            rssi_norm = ((rssi_clamped - cls.MIN_RSSI) / (cls.MAX_RSSI - cls.MIN_RSSI)) * 100.0
        else:
            rssi_norm = 50.0  # Valor neutral si falta RSSI

        # 3. Puntuación combinada ponderada
        signal_score = (cls.WEIGHT_SNR * snr_norm) + (cls.WEIGHT_RSSI * rssi_norm)

        # 4. Penalización por saltos multi-hop
        hop_penalty = max(0, hops) * cls.PENALTY_PER_HOP
        lqi_instant = max(0.0, min(100.0, signal_score - hop_penalty))

        return float(round(lqi_instant, 2))

    @classmethod
    def update_ema_lqi(
        cls,
        prev_lqi: float,
        instant_lqi: float,
        alpha: float = DEFAULT_ALPHA,
    ) -> float:
        """
        Suaviza la puntuación LQI mediante Media Móvil Exponencial (EMA).
        Si el LQI previo es 0 (nodo nuevo), se adopta directamente el LQI instantáneo.
        """
        if prev_lqi <= 0.0:
            return float(round(instant_lqi, 2))

        clamped_alpha = max(0.05, min(0.95, alpha))
        new_lqi = (clamped_alpha * instant_lqi) + ((1.0 - clamped_alpha) * prev_lqi)
        return float(round(max(0.0, min(100.0, new_lqi)), 2))

    @classmethod
    def apply_time_decay(
        cls,
        lqi: float,
        last_seen_ts: float,
        now_ts: float | None = None,
    ) -> float:
        """
        Aplica decaimiento temporal si el nodo no ha transmitido en más de INACTIVITY_THRESHOLD_SEC.
        """
        if lqi <= 0.0:
            return 0.0

        current_time = time.time() if now_ts is None else now_ts
        inactive_seconds = max(0.0, current_time - last_seen_ts)

        if inactive_seconds <= cls.INACTIVITY_THRESHOLD_SEC:
            return float(round(lqi, 2))

        # Minutos adicionales de inactividad tras el umbral
        extra_minutes = (inactive_seconds - cls.INACTIVITY_THRESHOLD_SEC) / 60.0
        decay_factor = max(0.0, 1.0 - (extra_minutes * cls.DECAY_RATE_PER_MINUTE))
        decayed_lqi = lqi * decay_factor

        return float(round(max(0.0, min(100.0, decayed_lqi)), 2))

    @classmethod
    def classify_lqi_status(cls, lqi: float) -> str:
        """Determina la categoría cualitativa del enlace según el valor de LQI."""
        if lqi >= 80.0:
            return LQIStatus.EXCELLENT.value
        if lqi >= 60.0:
            return LQIStatus.GOOD.value
        if lqi >= 40.0:
            return LQIStatus.FAIR.value
        if lqi > 0.0:
            return LQIStatus.POOR.value
        return LQIStatus.UNREACHABLE.value

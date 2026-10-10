"""
Node Registry & Contact Directory for MeshCore Bridge.
Mantiene un registro de nodos activos, libretas de contactos, alias, telemetría y métricas RF
en memoria con soporte de búsqueda O(1), estadísticas de tráfico y análisis topológico.
"""

from __future__ import annotations

import asyncio
import heapq
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.lqi_engine import LinkQualityEngine, LQIStatus
from src.protocol_types import (
    hash_mode_to_bytes,
    normalize_hash_mode,
)
from src.shared_utils import (
    clean_numeric_value,
    haversine_distance_m,
    normalize_battery,
)


def _safe_int(val: Any) -> int | None:
    """Convierte de forma segura valores de batería o contadores a entero."""
    clean = clean_numeric_value(val)
    if clean is not None:
        return int(round(clean))
    return None


def _safe_float(val: Any) -> float | None:
    """Convierte de forma segura valores a flotante."""
    return clean_numeric_value(val)


@dataclass(frozen=True, slots=True)
class NodeIdentity:
    """Atributos de identidad canónica e inmutable del nodo en la red MeshCore."""
    public_key: str
    name: str = ""
    alias: str = ""
    role: str = "CLIENT"
    owner_name: str | None = None
    owner_info: str | None = None
    firmware_version: str | None = None
    hardware_board: str | None = None
    is_local: bool = False
    auto_discovered: bool = False
    discovery_time: float = 0.0
    verified_identity: bool = False
    is_favorite: bool = False


@dataclass(frozen=True, slots=True)
class NodeRfMetrics:
    """Métricas volátiles de señal de radiofrecuencia (RF), saltos y rutas."""
    hops: int | None = None
    last_rssi: int | None = None
    last_snr: float | None = None
    noise_floor_dbm: int | None = None
    lqi_score: float = 0.0
    lqi_status: str = "UNKNOWN"
    best_route: str = "DIRECT"
    tx_power: int | None = None
    max_tx_power: int | None = None
    hop_limit: int | None = None
    frequency: float | None = None
    spreading_factor: int | None = None
    bandwidth: float | None = None
    coding_rate: str | None = None
    repeat_enabled: bool | None = None
    advert_interval: int | None = None
    flood_advert_interval: int | None = None
    allow_read_only: bool | None = None
    flags: int | None = None
    last_advert: float | None = None
    last_advert_heard_at: float | None = None
    last_rx_at: float | None = None
    last_rx_route: dict[str, Any] | None = None
    out_path: str | None = None
    out_path_len: int | None = None
    out_path_hash_mode: int | str | None = None
    out_route_state: str = "unknown"
    out_path_hash_size_bytes: int | None = None
    hops_source: str = "unknown"


@dataclass(frozen=True, slots=True)
class NodeTelemetry:
    """Métricas operacionales, telemetría de sensores, posicionamiento y contadores."""
    battery_pct: int | None = None
    voltage_v: float | None = None
    solar_v: float | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    fixed_position: bool | None = None
    adv_lat: float | None = None
    adv_lon: float | None = None
    position_valid: bool = False
    position_source: str | None = None
    position_updated_at: float | None = None
    uptime: str | None = None
    clock: str | None = None
    airtime_ms: int | None = None
    rx_packets: int = 0
    tx_packets: int = 0
    error_count: int = 0
    connected_clients_count: int = 0
    packets_sent: int | None = None
    packets_recv: int | None = None
    duplicate_packets: int | None = None
    packet_errors: int | None = None
    queue_len: int | None = None
    neighbors: tuple[str, ...] = field(default_factory=tuple)
    duty_cycle_pct: float | None = None
    last_seen: float = 0.0


@dataclass(frozen=True, slots=True)
class NodeContactInfo:
    """Información consolidada de un nodo o contacto en la malla.

    Compone de forma limpia y desacoplada las tres dimensiones del dominio:
    - identity: NodeIdentity (identidad, nombre, rol, hardware)
    - rf: NodeRfMetrics (calidad de enlace LQI, RSSI/SNR, saltos, rutas)
    - telemetry: NodeTelemetry (batería, sensores, GPS, contadores)
    """
    identity: NodeIdentity
    rf: NodeRfMetrics = field(default_factory=NodeRfMetrics)
    telemetry: NodeTelemetry = field(default_factory=NodeTelemetry)

    def __init__(
        self,
        identity: NodeIdentity | None = None,
        rf: NodeRfMetrics | None = None,
        telemetry: NodeTelemetry | None = None,
        # Argumentos planos de compatibilidad total con llamadas heredadas
        public_key: str = "",
        name: str = "",
        alias: str = "",
        role: str = "CLIENT",
        hops: int | None = None,
        last_rssi: int | None = None,
        last_snr: float | None = None,
        battery_pct: int | None = None,
        last_seen: float = 0.0,
        rx_packets: int = 0,
        tx_packets: int = 0,
        error_count: int = 0,
        connected_clients_count: int = 0,
        neighbors: tuple[str, ...] | list[str] = (),
        temperature_c: float | None = None,
        humidity_pct: float | None = None,
        pressure_hpa: float | None = None,
        voltage_v: float | None = None,
        solar_v: float | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude_m: float | None = None,
        uptime: str | None = None,
        clock: str | None = None,
        airtime_ms: int | None = None,
        duty_cycle_pct: float | None = None,
        noise_floor_dbm: int | None = None,
        packets_sent: int | None = None,
        packets_recv: int | None = None,
        duplicate_packets: int | None = None,
        packet_errors: int | None = None,
        queue_len: int | None = None,
        owner_name: str | None = None,
        owner_info: str | None = None,
        firmware_version: str | None = None,
        hardware_board: str | None = None,
        advert_interval: int | None = None,
        flood_advert_interval: int | None = None,
        allow_read_only: bool | None = None,
        repeat_enabled: bool | None = None,
        tx_power: int | None = None,
        max_tx_power: int | None = None,
        hop_limit: int | None = None,
        frequency: float | None = None,
        spreading_factor: int | None = None,
        bandwidth: float | None = None,
        coding_rate: str | None = None,
        fixed_position: bool | None = None,
        is_local: bool = False,
        auto_discovered: bool = False,
        discovery_time: float = 0.0,
        verified_identity: bool = False,
        is_favorite: bool = False,
        lqi_score: float = 0.0,
        lqi_status: str = "UNKNOWN",
        best_route: str = "DIRECT",
        flags: int | None = None,
        last_advert: float | None = None,
        last_advert_heard_at: float | None = None,
        last_rx_at: float | None = None,
        last_rx_route: dict[str, Any] | None = None,
        out_path: str | None = None,
        out_path_len: int | None = None,
        out_path_hash_mode: int | str | None = None,
        out_route_state: str = "unknown",
        out_path_hash_size_bytes: int | None = None,
        hops_source: str = "unknown",
        adv_lat: float | None = None,
        adv_lon: float | None = None,
        position_valid: bool = False,
        position_source: str | None = None,
        position_updated_at: float | None = None,
        lat: float | None = None,
        lon: float | None = None,
        **kwargs: Any,
    ) -> None:
        eff_lat = latitude if latitude is not None else (lat if lat is not None else adv_lat)
        eff_lon = longitude if longitude is not None else (lon if lon is not None else adv_lon)
        eff_adv_lat = adv_lat if adv_lat is not None else eff_lat
        eff_adv_lon = adv_lon if adv_lon is not None else eff_lon

        if identity is None:
            identity = NodeIdentity(
                public_key=public_key,
                name=name,
                alias=alias,
                role=role,
                owner_name=owner_name,
                owner_info=owner_info,
                firmware_version=firmware_version,
                hardware_board=hardware_board,
                is_local=is_local,
                auto_discovered=auto_discovered,
                discovery_time=discovery_time,
                verified_identity=verified_identity,
                is_favorite=is_favorite,
            )
        if rf is None:
            rf = NodeRfMetrics(
                hops=hops,
                last_rssi=last_rssi,
                last_snr=last_snr,
                noise_floor_dbm=noise_floor_dbm,
                lqi_score=lqi_score,
                lqi_status=lqi_status,
                best_route=best_route,
                tx_power=tx_power,
                max_tx_power=max_tx_power,
                hop_limit=hop_limit,
                frequency=frequency,
                spreading_factor=spreading_factor,
                bandwidth=bandwidth,
                coding_rate=coding_rate,
                repeat_enabled=repeat_enabled,
                advert_interval=advert_interval,
                flood_advert_interval=flood_advert_interval,
                allow_read_only=allow_read_only,
                flags=flags,
                last_advert=last_advert,
                last_advert_heard_at=last_advert_heard_at,
                last_rx_at=last_rx_at,
                last_rx_route=last_rx_route,
                out_path=out_path,
                out_path_len=out_path_len,
                out_path_hash_mode=out_path_hash_mode,
                out_route_state=out_route_state,
                out_path_hash_size_bytes=out_path_hash_size_bytes,
                hops_source=hops_source,
            )
        if telemetry is None:
            telemetry = NodeTelemetry(
                battery_pct=battery_pct,
                voltage_v=voltage_v,
                solar_v=solar_v,
                temperature_c=temperature_c,
                humidity_pct=humidity_pct,
                pressure_hpa=pressure_hpa,
                latitude=eff_lat,
                longitude=eff_lon,
                altitude_m=altitude_m,
                fixed_position=fixed_position,
                adv_lat=eff_adv_lat,
                adv_lon=eff_adv_lon,
                position_valid=position_valid,
                position_source=position_source,
                position_updated_at=position_updated_at,
                uptime=uptime,
                clock=clock,
                airtime_ms=airtime_ms,
                duty_cycle_pct=duty_cycle_pct,
                rx_packets=rx_packets,
                tx_packets=tx_packets,
                error_count=error_count,
                connected_clients_count=connected_clients_count,
                packets_sent=packets_sent,
                packets_recv=packets_recv,
                duplicate_packets=duplicate_packets,
                packet_errors=packet_errors,
                queue_len=queue_len,
                neighbors=tuple(neighbors) if isinstance(neighbors, (list, tuple)) else (),
                last_seen=last_seen,
            )
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "rf", rf)
        object.__setattr__(self, "telemetry", telemetry)

    # Identidad Delegada
    @property
    def public_key(self) -> str:
        return self.identity.public_key

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def alias(self) -> str:
        return self.identity.alias

    @property
    def role(self) -> str:
        return self.identity.role

    @property
    def owner_name(self) -> str | None:
        return self.identity.owner_name

    @property
    def owner_info(self) -> str | None:
        return self.identity.owner_info

    @property
    def firmware_version(self) -> str | None:
        return self.identity.firmware_version

    @property
    def hardware_board(self) -> str | None:
        return self.identity.hardware_board

    @property
    def is_local(self) -> bool:
        return self.identity.is_local

    @property
    def auto_discovered(self) -> bool:
        return self.identity.auto_discovered

    @property
    def discovery_time(self) -> float:
        return self.identity.discovery_time

    @property
    def verified_identity(self) -> bool:
        return self.identity.verified_identity

    @property
    def is_favorite(self) -> bool:
        return self.identity.is_favorite

    # Métricas RF Delegadas
    @property
    def hops(self) -> int | None:
        return self.rf.hops

    @property
    def last_rssi(self) -> int | None:
        return self.rf.last_rssi

    @property
    def last_snr(self) -> float | None:
        return self.rf.last_snr

    @property
    def noise_floor_dbm(self) -> int | None:
        return self.rf.noise_floor_dbm

    @property
    def lqi_score(self) -> float:
        return self.rf.lqi_score

    @property
    def lqi_status(self) -> str:
        return self.rf.lqi_status

    @property
    def best_route(self) -> str:
        return self.rf.best_route

    @property
    def tx_power(self) -> int | None:
        return self.rf.tx_power

    @property
    def max_tx_power(self) -> int | None:
        return self.rf.max_tx_power

    @property
    def hop_limit(self) -> int | None:
        return self.rf.hop_limit

    @property
    def frequency(self) -> float | None:
        return self.rf.frequency

    @property
    def spreading_factor(self) -> int | None:
        return self.rf.spreading_factor

    @property
    def bandwidth(self) -> float | None:
        return self.rf.bandwidth

    @property
    def coding_rate(self) -> str | None:
        return self.rf.coding_rate

    @property
    def repeat_enabled(self) -> bool | None:
        return self.rf.repeat_enabled

    @property
    def advert_interval(self) -> int | None:
        return self.rf.advert_interval

    @property
    def flood_advert_interval(self) -> int | None:
        return self.rf.flood_advert_interval

    @property
    def allow_read_only(self) -> bool | None:
        return self.rf.allow_read_only

    @property
    def flags(self) -> int | None:
        return self.rf.flags

    @property
    def last_advert(self) -> float | None:
        return self.rf.last_advert

    @property
    def last_advert_heard_at(self) -> float | None:
        return self.rf.last_advert_heard_at

    @property
    def last_rx_at(self) -> float | None:
        return self.rf.last_rx_at

    @property
    def last_rx_route(self) -> dict[str, Any] | None:
        return self.rf.last_rx_route

    @property
    def out_path(self) -> str | None:
        return self.rf.out_path

    @property
    def out_path_len(self) -> int | None:
        return self.rf.out_path_len

    @property
    def out_path_hash_mode(self) -> int | str | None:
        return self.rf.out_path_hash_mode

    @property
    def out_route_state(self) -> str:
        return self.rf.out_route_state

    @property
    def out_path_hash_size_bytes(self) -> int | None:
        return self.rf.out_path_hash_size_bytes

    @property
    def hops_source(self) -> str:
        return self.rf.hops_source

    # Telemetría y Sensores Delegados
    @property
    def battery_pct(self) -> int | None:
        return self.telemetry.battery_pct

    @property
    def voltage_v(self) -> float | None:
        return self.telemetry.voltage_v

    @property
    def duty_cycle_pct(self) -> float | None:
        return self.telemetry.duty_cycle_pct

    @property
    def solar_v(self) -> float | None:
        return self.telemetry.solar_v

    @property
    def temperature_c(self) -> float | None:
        return self.telemetry.temperature_c

    @property
    def humidity_pct(self) -> float | None:
        return self.telemetry.humidity_pct

    @property
    def pressure_hpa(self) -> float | None:
        return self.telemetry.pressure_hpa

    @property
    def latitude(self) -> float | None:
        return self.telemetry.latitude if self.telemetry.latitude is not None else self.telemetry.adv_lat

    @property
    def longitude(self) -> float | None:
        return self.telemetry.longitude if self.telemetry.longitude is not None else self.telemetry.adv_lon

    @property
    def lat(self) -> float | None:
        return self.latitude

    @property
    def lon(self) -> float | None:
        return self.longitude

    @property
    def altitude_m(self) -> float | None:
        return self.telemetry.altitude_m

    @property
    def fixed_position(self) -> bool | None:
        return self.telemetry.fixed_position

    @property
    def adv_lat(self) -> float | None:
        return self.telemetry.adv_lat if self.telemetry.adv_lat is not None else self.telemetry.latitude

    @property
    def adv_lon(self) -> float | None:
        return self.telemetry.adv_lon if self.telemetry.adv_lon is not None else self.telemetry.longitude

    @property
    def position_valid(self) -> bool:
        return self.telemetry.position_valid

    @property
    def position_source(self) -> str | None:
        return self.telemetry.position_source

    @property
    def position_updated_at(self) -> float | None:
        return self.telemetry.position_updated_at

    @property
    def uptime(self) -> str | None:
        return self.telemetry.uptime

    @property
    def clock(self) -> str | None:
        return self.telemetry.clock

    @property
    def airtime_ms(self) -> int | None:
        return self.telemetry.airtime_ms

    @property
    def rx_packets(self) -> int:
        return self.telemetry.rx_packets

    @property
    def tx_packets(self) -> int:
        return self.telemetry.tx_packets

    @property
    def error_count(self) -> int:
        return self.telemetry.error_count

    @property
    def connected_clients_count(self) -> int:
        return self.telemetry.connected_clients_count

    @property
    def packets_sent(self) -> int | None:
        return self.telemetry.packets_sent

    @property
    def packets_recv(self) -> int | None:
        return self.telemetry.packets_recv

    @property
    def duplicate_packets(self) -> int | None:
        return self.telemetry.duplicate_packets

    @property
    def packet_errors(self) -> int | None:
        return self.telemetry.packet_errors

    @property
    def queue_len(self) -> int | None:
        return self.telemetry.queue_len

    @property
    def neighbors(self) -> tuple[str, ...]:
        return self.telemetry.neighbors

    @property
    def last_seen(self) -> float:
        return self.telemetry.last_seen

    def as_flat_dict(self) -> dict[str, Any]:
        """Retorna un diccionario plano unificando identity, rf y telemetry."""
        d: dict[str, Any] = {}
        d.update(asdict(self.identity))
        d.update(asdict(self.rf))
        d.update(asdict(self.telemetry))
        return d

    def replace_fields(self, **changes: Any) -> NodeContactInfo:
        """Retorna una nueva instancia con los campos indicados modificados."""
        current = self.as_flat_dict()
        current.update(changes)
        return NodeContactInfo(**current)

    def to_dict(self, local_lat: float | None = None, local_lon: float | None = None) -> dict[str, Any]:
        d = self.as_flat_dict()
        d["key_prefix"] = self.public_key[:8] if len(self.public_key) >= 8 else self.public_key
        d["total_packets"] = self.rx_packets + self.tx_packets
        d["error_rate_pct"] = round((self.error_count / (d["total_packets"] or 1)) * 100, 1)
        d["is_local"] = self.is_local
        eff_lat = self.latitude
        eff_lon = self.longitude
        d["latitude"] = eff_lat
        d["longitude"] = eff_lon
        d["lat"] = eff_lat
        d["lon"] = eff_lon

        pos_valid = bool(self.position_valid)
        if not pos_valid and (eff_lat is not None and eff_lon is not None):
            if -90.0 <= eff_lat <= 90.0 and -180.0 <= eff_lon <= 180.0:
                if eff_lat != 0.0 or eff_lon != 0.0 or self.fixed_position:
                    pos_valid = True
        d["position_valid"] = pos_valid
        d["position_source"] = self.position_source or ("ADVERT" if pos_valid else "NONE")
        d["position_updated_at"] = self.position_updated_at
        d["fixed_position"] = self.fixed_position if self.fixed_position is not None else pos_valid
        d["best_route"] = self.best_route
        d["flags"] = self.flags
        d["last_advert"] = self.last_advert
        d["last_advert_heard_at"] = self.last_advert_heard_at
        d["last_rx_at"] = self.last_rx_at
        d["last_rx_route"] = self.last_rx_route
        d["out_path"] = self.out_path
        d["out_path_len"] = self.out_path_len

        norm_mode = normalize_hash_mode(self.out_path_hash_mode)
        d["out_path_hash_mode"] = norm_mode
        d["out_path_hash_mode_raw"] = self.out_path_hash_mode
        d["out_path_hash_size_bytes"] = hash_mode_to_bytes(norm_mode) if norm_mode is not None else self.out_path_hash_size_bytes

        if norm_mode == -1 or self.out_route_state == "flood":
            d["out_route_state"] = "flood"
        elif self.out_path and len(self.out_path) > 0 and self.out_path_len and self.out_path_len > 0:
            d["out_route_state"] = "known"
        else:
            d["out_route_state"] = self.out_route_state or "unknown"

        d["hops_source"] = self.hops_source or ("direct" if self.hops == 0 else ("rx_flood" if self.hops and self.hops > 0 else "unknown"))

        # Distancia en metros respecto a coordenadas de origen (nodo local)
        if not self.is_local and str(self.role).upper() != "LOCAL" and local_lat is not None and local_lon is not None and pos_valid:
            d["distance_m"] = haversine_distance_m(local_lat, local_lon, eff_lat, eff_lon)
        else:
            d["distance_m"] = None

        d["adv_lat"] = self.adv_lat if self.adv_lat is not None else eff_lat
        d["adv_lon"] = self.adv_lon if self.adv_lon is not None else eff_lon
        d["repeat_enabled"] = self.repeat_enabled if self.repeat_enabled is not None else (self.role in ("REPEATER", "ROUTER"))
        d["hop_limit"] = self.hop_limit if self.hop_limit is not None else 3
        # A board name cannot establish the radio's measured power limits.
        d["min_tx_power"] = None
        d["max_tx_power"] = self.max_tx_power
        d["default_tx_power"] = None
        d["tx_power_limits_source"] = "observed" if self.max_tx_power is not None else "unknown"

        # Ciclo de vida y presencia: Activo (<12h), Inactivo (12h-24h), Desconectado (>24h)
        now_ts = time.time()
        if self.is_local or str(self.role).upper() == "LOCAL":
            presence_status = "online"
            status_label = "Local"
            last_seen_iso = datetime.now(UTC).isoformat()
            last_seen_formatted = "En línea (Local)"
            d["lqi_score"] = 100.0
            d["lqi_status"] = "EXCELLENT"
        elif self.last_seen and self.last_seen > 0:
            diff = max(0.0, now_ts - float(self.last_seen))
            ls_dt = datetime.fromtimestamp(float(self.last_seen))
            last_seen_iso = ls_dt.isoformat()
            last_seen_formatted = ls_dt.strftime("%Y-%m-%d %H:%M:%S")

            if diff < 12 * 3600:
                presence_status = "online"
                status_label = "Activo"
                d["lqi_score"] = round(self.lqi_score, 1)
                d["lqi_status"] = self.lqi_status
            elif diff < 24 * 3600:
                presence_status = "idle"
                status_label = "Inactivo"
                d["lqi_score"] = round(self.lqi_score, 1)
                d["lqi_status"] = self.lqi_status
            else:
                presence_status = "offline"
                status_label = "Desconectado"
                d["last_rssi"] = self.last_rssi
                d["last_snr"] = self.last_snr
                d["lqi_score"] = 0.0
                d["lqi_status"] = "DISCONNECTED"
        else:
            presence_status = "offline"
            status_label = "Desconectado"
            last_seen_iso = None
            last_seen_formatted = "Sin señal registrada"
            d["last_rssi"] = self.last_rssi
            d["last_snr"] = self.last_snr
            d["lqi_score"] = 0.0
            d["lqi_status"] = "DISCONNECTED"

        d["presence_status"] = presence_status
        d["status_label"] = status_label
        d["last_seen_iso"] = last_seen_iso
        d["last_seen_formatted"] = last_seen_formatted

        return d


@dataclass(slots=True)
class NodeContactUpdate:
    """Objeto de parámetro para add_or_update."""
    name: str | None = None
    alias: str | None = None
    role: str | None = None
    last_seen: float | None = None
    is_local: bool | None = None
    auto_discovered: bool | None = None
    discovery_time: float | None = None
    verified_identity: bool | None = None
    is_favorite: bool | None = None
    lqi_score: float | None = None
    lqi_status: str | None = None
    best_route: str | None = None
    hops: int | None = None
    last_rssi: int | None = None
    last_snr: float | None = None
    battery_pct: int | None = None
    rx_packets: int | None = None
    tx_packets: int | None = None
    error_count: int | None = None
    connected_clients_count: int | None = None
    neighbors: list[str] | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    voltage_v: float | None = None
    solar_v: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    uptime: str | None = None
    clock: str | None = None
    airtime_ms: int | None = None
    duty_cycle_pct: float | None = None
    noise_floor_dbm: int | None = None
    packets_sent: int | None = None
    packets_recv: int | None = None
    duplicate_packets: int | None = None
    packet_errors: int | None = None
    queue_len: int | None = None
    owner_name: str | None = None
    owner_info: str | None = None
    firmware_version: str | None = None
    hardware_board: str | None = None
    advert_interval: int | None = None
    flood_advert_interval: int | None = None
    allow_read_only: bool | None = None
    repeat_enabled: bool | None = None
    tx_power: int | None = None
    max_tx_power: int | None = None
    hop_limit: int | None = None
    frequency: float | None = None
    spreading_factor: int | None = None
    bandwidth: float | None = None
    coding_rate: str | None = None
    fixed_position: bool | None = None
    flags: int | None = None
    last_advert: float | None = None
    last_advert_heard_at: float | None = None
    last_rx_at: float | None = None
    last_rx_route: dict[str, Any] | None = None
    out_path: str | None = None
    out_path_len: int | None = None
    out_path_hash_mode: int | str | None = None
    out_route_state: str | None = None
    out_path_hash_size_bytes: int | None = None
    hops_source: str | None = None
    adv_lat: float | None = None
    adv_lon: float | None = None
    position_valid: bool | None = None
    position_source: str | None = None
    position_updated_at: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], **overrides: Any) -> NodeContactUpdate:
        """Construye un NodeContactUpdate filtrando campos válidos de data y aplicando overrides."""
        slots = set(getattr(cls, "__slots__", ()))
        kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if k in slots and v is not None:
                kwargs[k] = v
        for k, v in overrides.items():
            if k in slots and (v is not None or k in overrides):
                kwargs[k] = v
        return cls(**kwargs)


@dataclass(slots=True)
class PacketRecord:
    """Objeto de parámetro para record_packet: metadatos de un evento de paquete RX/TX."""
    public_key: str
    is_rx: bool
    is_error: bool = False
    rssi: int | float | None = None
    snr: float | None = None
    hop_count: int | None = None
    telemetry: dict[str, Any] | None = None


INVALID_NODE_KEYS: set[str] = {
    "unknown",
    "broadcast",
    "none",
    "null",
    "system",
    "00000000",
    "000000000000",
    "ffff",
    "0xffff",
    "",
}


@dataclass(slots=True)
class NodeDiscoveryEvent:
    """Parámetros normalizados para el descubrimiento de un nodo en la red Mesh LoRa."""

    public_key: str
    name: str | None = None
    role: str = "CLIENT"
    rssi: int | None = None
    snr: float | None = None
    hops: int | None = None
    last_seen: float | None = None
    last_advert_heard_at: float | None = None
    is_import: bool = False


def is_valid_node_key(key: Any) -> bool:
    """Verifica si una clave pública es válida para registrar o descubrir un nodo."""
    if not key or not isinstance(key, str):
        return False
    norm = key.strip().lower()
    if not norm or norm in INVALID_NODE_KEYS or len(norm) < 4:
        return False
    if norm == "local":
        return True
    if norm.startswith("unknow") or norm.startswith("broadcast") or norm.startswith("0x0000"):
        return False
    if not all(c in "0123456789abcdef" for c in norm):
        return False
    return True


class NodeRegistry:
    """Directorio en memoria para contactos y resolución de nombres de la red MeshCore."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._nodes_by_key: dict[str, NodeContactInfo] = {}
        self._local_pubkey: str = ""
        self.error_categories: dict[str, int] = {
            "SERIAL_TIMEOUT": 0,
            "TX_BUFFER_OVERFLOW": 0,
            "CRC_MISMATCH": 0,
            "RADIO_BUSY": 0,
            "ROUTE_UNREACHABLE": 0,
            "MQTT_DISCONNECT": 0,
        }
        self._dirty: bool = False
        self._generation = 0
        self._save_lock = threading.Lock()
        self._save_debounce_task: asyncio.Task[Any] | None = None

    def _mark_dirty(self) -> None:
        """Called while holding _lock, identifying every persistence mutation."""
        self._generation += 1
        self._dirty = True

    def set_local_pubkey(self, pubkey: str) -> None:
        """Establece la clave pública del nodo local y consolida entradas existentes para evitar duplicados."""
        self._local_pubkey = str(pubkey).strip().lower()
        if not self._local_pubkey:
            return

        with self._lock:
            self._mark_dirty()
            # Consolidar y purgar cualquier entrada local previa bajo la clave canónica oficial
            local_entries = [
                (k, node) for k, node in list(self._nodes_by_key.items())
                if node.is_local or self.is_local_key(k) or str(node.role).upper() == "LOCAL"
            ]

            if local_entries:
                # Encontrar la entrada local con datos más completos
                primary_k, primary_node = local_entries[0]
                for k, node in local_entries:
                    if len(k) > len(primary_k) or (node.name and not node.name.startswith("Node_")):
                        primary_k, primary_node = k, node

                # Eliminar todas las entradas locales detectadas
                for k, _node in local_entries:
                    self._nodes_by_key.pop(k, None)

                # Fusionar todos los atributos de las entradas locales (GPS, telemetría, batería)
                merged_fields = primary_node.as_flat_dict()
                for _, node in local_entries:
                    node_fields = node.as_flat_dict()
                    for f_name, f_val in node_fields.items():
                        if f_val is not None and merged_fields.get(f_name) is None:
                            merged_fields[f_name] = f_val

                merged_fields["public_key"] = self._local_pubkey
                merged_fields["is_local"] = True
                merged_fields["role"] = "LOCAL"
                merged_fields["hops"] = 0
                consolidated = NodeContactInfo(**merged_fields)
                self._nodes_by_key[self._local_pubkey] = consolidated

    def get_local_pubkey(self) -> str:
        """Devuelve la clave pública del nodo local."""
        return self._local_pubkey

    @property
    def local_pubkey(self) -> str:
        """Propiedad de acceso a la clave pública del nodo local."""
        return self._local_pubkey

    def is_local_key(self, raw_key: str) -> bool:
        """Determina si una clave o prefijo corresponde a la estación base local."""
        norm = str(raw_key).strip().lower()
        if not norm or norm in ("local", "000000000000"):
            return True
        if not self._local_pubkey:
            return False
        loc = self._local_pubkey
        return norm == loc or (len(loc) >= 6 and len(norm) >= 6 and (loc.startswith(norm) or norm.startswith(loc)))

    def _find_existing_key(self, raw_key: str, name: str | None = None) -> str | None:
        """Encuentra si ya existe una clave exacta o unificada por prefijo/nombre para evitar duplicados."""
        norm = raw_key.strip().lower() if raw_key and isinstance(raw_key, str) else ""

        # 1. Coincidencia exacta por clave pública
        if norm and norm in self._nodes_by_key:
            return norm

        # Los prefijos sólo identifican un nodo cuando la coincidencia es única.
        if norm and is_valid_node_key(norm):
            matches = [k for k in self._nodes_by_key if
                       (len(k) < len(norm) and norm.startswith(k)) or
                       (len(norm) < len(k) and k.startswith(norm))]
            if len(matches) == 1:
                return matches[0]
            # Una clave pública nueva nunca se fusiona por un nombre mutable.
            return None

        # 3. Coincidencia por nombre exacto o alias si no es un nombre genérico (solo coincidencia única)
        if name:
            n_clean = name.strip().lower()
            if n_clean and not n_clean.startswith("node_") and not n_clean.startswith("unknow") and len(n_clean) >= 2:
                matching_keys = [
                    k for k, node in self._nodes_by_key.items()
                    if (node.name and node.name.strip().lower() == n_clean) or
                       (node.alias and node.alias.strip().lower() == n_clean)
                ]
                if len(matching_keys) == 1:
                    return matching_keys[0]

        return None


    def get_canonical_key(self, raw_key: str, name: str | None = None) -> str:
        """Devuelve la clave pública canónica (más larga o conocida) para una clave o prefijo."""
        if not is_valid_node_key(raw_key):
            return ""
        with self._lock:
            existing = self._find_existing_key(raw_key, name)
            return existing if existing else raw_key.strip().lower()

    def _resolve_canonical_key_and_clean_locals(
        self,
        norm_key: str,
        clean_name_candidate: str,
        is_local_flag: bool,
    ) -> tuple[str, NodeContactInfo | None]:
        """Resuelve la clave canónica del nodo y purga duplicados locales o prefijos residuales."""
        existing_key = self._find_existing_key(norm_key, clean_name_candidate)
        existing: NodeContactInfo | None = None

        if is_local_flag:
            for k, node in list(self._nodes_by_key.items()):
                if node.is_local or self.is_local_key(k) or str(node.role).upper() == "LOCAL":
                    existing_key = k
                    existing = node
                    break
            if self._local_pubkey and len(self._local_pubkey) >= len(norm_key):
                canonical_key = self._local_pubkey
            else:
                canonical_key = norm_key

            # Purgar cualquier otra entrada local residual
            for k, node in list(self._nodes_by_key.items()):
                if k != canonical_key and (node.is_local or self.is_local_key(k) or str(node.role).upper() == "LOCAL"):
                    del self._nodes_by_key[k]
        else:
            canonical_key = norm_key
            if existing_key:
                existing = self._nodes_by_key.get(existing_key)
                if existing and len(existing_key) > len(norm_key):
                    canonical_key = existing_key
                elif existing_key != norm_key and existing_key in self._nodes_by_key:
                    del self._nodes_by_key[existing_key]

        return canonical_key, existing

    def _compute_node_lqi(
        self,
        update: NodeContactUpdate,
        existing: NodeContactInfo | None,
        is_local_flag: bool,
    ) -> tuple[float, str]:
        """Calcula y suaviza el puntaje LQI y su estado correspondiente."""
        lqi_score = getattr(update, "lqi_score", None)
        lqi_status = getattr(update, "lqi_status", None)
        last_snr = getattr(update, "last_snr", None)
        last_rssi = getattr(update, "last_rssi", None)
        hops = getattr(update, "hops", None)

        if lqi_score is not None:
            calc_lqi = float(lqi_score)
            calc_status = lqi_status or LinkQualityEngine.classify_lqi_status(calc_lqi)
            return calc_lqi, calc_status
        if is_local_flag:
            return 100.0, LQIStatus.EXCELLENT.value

        eff_snr = last_snr if last_snr is not None else (existing.last_snr if existing else None)
        eff_rssi = last_rssi if last_rssi is not None else (existing.last_rssi if existing else None)
        eff_hops = hops if hops is not None else (existing.hops if existing else 0)

        if eff_snr is not None or eff_rssi is not None:
            instant_lqi = LinkQualityEngine.compute_instant_lqi(eff_snr, eff_rssi, eff_hops or 0)
            prev_lqi = existing.lqi_score if existing else 0.0
            calc_lqi = LinkQualityEngine.update_ema_lqi(prev_lqi, instant_lqi)
            calc_status = LinkQualityEngine.classify_lqi_status(calc_lqi)
        else:
            calc_lqi = existing.lqi_score if existing else 0.0
            calc_status = existing.lqi_status if existing else "UNKNOWN"

        return calc_lqi, calc_status

    def _resolve_node_role(
        self,
        clean_name: str,
        clean_alias: str,
        update: NodeContactUpdate,
        existing: NodeContactInfo | None,
        is_local_flag: bool,
    ) -> str:
        """Determina el rol canónico del nodo respetando la clasificación oficial y repetidores."""
        if is_local_flag:
            return "LOCAL"
        up_role = getattr(update, "role", None)
        if up_role is not None:
            return str(up_role).upper()
        if existing and existing.role:
            return existing.role
        return "CLIENT"

    @staticmethod
    def _merge_field(new_val: Any, existing: NodeContactInfo | None, attr: str, default: Any = None) -> Any:
        if new_val is not None:
            return new_val
        if existing is not None:
            old_val = getattr(existing, attr, None)
            if old_val is not None:
                return old_val
        return default

    def _build_updated_contact(
        self,
        canonical_key: str,
        update: NodeContactUpdate,
        existing: NodeContactInfo | None,
        identity_meta: tuple[str, str, str, bool],
        rf_meta: tuple[int | None, int | None, float | None, float, str, str],
    ) -> NodeContactInfo:
        """Ensambla el objeto NodeContactInfo fusionando los datos anteriores con la actualización."""
        clean_name, clean_alias, final_role, is_local_flag = identity_meta
        eff_hops, eff_rssi, eff_snr, calc_lqi, calc_status, calc_route = rf_meta
        now = time.time()
        up_ls = getattr(update, "last_seen", None)
        up_rssi = getattr(update, "last_rssi", None)
        up_snr = getattr(update, "last_snr", None)
        if up_ls is not None:
            new_ls = float(up_ls)
            eff_last_seen = max(float(existing.last_seen), new_ls) if (existing and existing.last_seen > 0) else new_ls
        elif is_local_flag:
            eff_last_seen = now
        elif up_rssi is not None or up_snr is not None:
            eff_last_seen = now
        elif existing and existing.last_seen > 0:
            eff_last_seen = float(existing.last_seen)
        else:
            eff_last_seen = 0.0

        def u(attr: str, default: Any = None) -> Any:
            return getattr(update, attr, default)

        m = self._merge_field
        up_neighbors = u("neighbors")
        up_lat = u("latitude")
        up_lon = u("longitude")
        up_adv_lat = u("adv_lat")
        up_adv_lon = u("adv_lon")
        return NodeContactInfo(
            public_key=canonical_key,
            name=clean_name,
            alias=clean_alias,
            role=final_role,
            is_local=is_local_flag,
            hops=eff_hops if not is_local_flag else 0,
            last_rssi=eff_rssi,
            last_snr=eff_snr,
            lqi_score=calc_lqi,
            lqi_status=calc_status,
            best_route=calc_route,
            battery_pct=m(u("battery_pct"), existing, "battery_pct"),
            last_seen=eff_last_seen,
            rx_packets=m(u("rx_packets"), existing, "rx_packets", 0),
            tx_packets=m(u("tx_packets"), existing, "tx_packets", 0),
            error_count=m(u("error_count"), existing, "error_count", 0),
            connected_clients_count=m(u("connected_clients_count"), existing, "connected_clients_count", 0),
            neighbors=tuple(up_neighbors) if up_neighbors is not None else (existing.neighbors if existing else ()),
            temperature_c=m(u("temperature_c"), existing, "temperature_c"),
            humidity_pct=m(u("humidity_pct"), existing, "humidity_pct"),
            pressure_hpa=m(u("pressure_hpa"), existing, "pressure_hpa"),
            voltage_v=m(u("voltage_v"), existing, "voltage_v"),
            solar_v=m(u("solar_v"), existing, "solar_v"),
            latitude=m(up_lat if up_lat is not None else up_adv_lat, existing, "latitude"),
            longitude=m(up_lon if up_lon is not None else up_adv_lon, existing, "longitude"),
            altitude_m=m(u("altitude_m"), existing, "altitude_m"),
            uptime=m(u("uptime"), existing, "uptime"),
            clock=m(u("clock"), existing, "clock"),
            airtime_ms=m(u("airtime_ms"), existing, "airtime_ms"),
            duty_cycle_pct=m(u("duty_cycle_pct"), existing, "duty_cycle_pct"),
            noise_floor_dbm=m(u("noise_floor_dbm"), existing, "noise_floor_dbm"),
            packets_sent=m(u("packets_sent"), existing, "packets_sent"),
            packets_recv=m(u("packets_recv"), existing, "packets_recv"),
            duplicate_packets=m(u("duplicate_packets"), existing, "duplicate_packets"),
            packet_errors=m(u("packet_errors"), existing, "packet_errors"),
            queue_len=m(u("queue_len"), existing, "queue_len"),
            owner_name=m(u("owner_name"), existing, "owner_name"),
            owner_info=m(u("owner_info"), existing, "owner_info"),
            firmware_version=m(u("firmware_version"), existing, "firmware_version"),
            hardware_board=m(u("hardware_board"), existing, "hardware_board"),
            advert_interval=m(u("advert_interval"), existing, "advert_interval"),
            flood_advert_interval=m(u("flood_advert_interval"), existing, "flood_advert_interval"),
            allow_read_only=m(u("allow_read_only"), existing, "allow_read_only"),
            repeat_enabled=m(u("repeat_enabled"), existing, "repeat_enabled"),
            tx_power=m(u("tx_power"), existing, "tx_power"),
            max_tx_power=m(u("max_tx_power"), existing, "max_tx_power"),
            hop_limit=m(u("hop_limit"), existing, "hop_limit"),
            frequency=m(u("frequency"), existing, "frequency"),
            spreading_factor=m(u("spreading_factor"), existing, "spreading_factor"),
            bandwidth=m(u("bandwidth"), existing, "bandwidth"),
            coding_rate=m(u("coding_rate"), existing, "coding_rate"),
            fixed_position=m(u("fixed_position"), existing, "fixed_position"),
            flags=m(u("flags"), existing, "flags"),
            last_advert=m(u("last_advert"), existing, "last_advert"),
            last_advert_heard_at=m(u("last_advert_heard_at"), existing, "last_advert_heard_at"),
            last_rx_at=m(u("last_rx_at"), existing, "last_rx_at"),
            last_rx_route=m(u("last_rx_route"), existing, "last_rx_route"),
            out_path=m(u("out_path"), existing, "out_path"),
            out_path_len=m(u("out_path_len"), existing, "out_path_len"),
            out_path_hash_mode=m(u("out_path_hash_mode"), existing, "out_path_hash_mode"),
            out_route_state=m(u("out_route_state"), existing, "out_route_state", "unknown"),
            out_path_hash_size_bytes=m(u("out_path_hash_size_bytes"), existing, "out_path_hash_size_bytes"),
            hops_source=m(u("hops_source"), existing, "hops_source", "unknown"),
            adv_lat=m(up_adv_lat if up_adv_lat is not None else up_lat, existing, "adv_lat"),
            adv_lon=m(up_adv_lon if up_adv_lon is not None else up_lon, existing, "adv_lon"),
            position_valid=m(u("position_valid"), existing, "position_valid", False),
            position_source=m(u("position_source"), existing, "position_source"),
            position_updated_at=m(u("position_updated_at"), existing, "position_updated_at"),
            auto_discovered=m(u("auto_discovered"), existing, "auto_discovered", False),
            discovery_time=m(u("discovery_time"), existing, "discovery_time", 0.0),
            verified_identity=m(u("verified_identity"), existing, "verified_identity", False),
            is_favorite=m(u("is_favorite"), existing, "is_favorite", False),
        )

    def add_or_update(self, public_key: str, update: NodeContactUpdate) -> NodeContactInfo:
        """Añade o actualiza la información de un nodo preservando métricas acumuladas y deduplicando prefijos."""
        norm_key = public_key.strip().lower()
        if not is_valid_node_key(norm_key):
            return NodeContactInfo(
                public_key="",
                name="Invalid",
                alias="Invalid",
            )
        clean_name_candidate = (getattr(update, "name", None) or "").strip()

        is_local_key_flag = self.is_local_key(norm_key)
        is_local_attr = getattr(update, "is_local", None)
        is_local_flag = bool(is_local_key_flag or (is_local_attr if is_local_attr is not None else False))
        up_role = getattr(update, "role", None)
        if up_role and str(up_role).upper() == "LOCAL":
            is_local_flag = True

        with self._lock:
            canonical_key, existing = self._resolve_canonical_key_and_clean_locals(norm_key, clean_name_candidate, is_local_flag)
            clean_name = clean_name_candidate or (existing.name if existing else f"Node_{canonical_key[:6]}")
            clean_alias = (getattr(update, "alias", None) or "").strip() or (existing.alias if existing else clean_name)
            final_role = self._resolve_node_role(clean_name, clean_alias, update, existing, is_local_flag)

            calc_lqi, calc_status = self._compute_node_lqi(update, existing, is_local_flag)
            up_hops = getattr(update, "hops", None)
            up_rssi = getattr(update, "last_rssi", None)
            up_snr = getattr(update, "last_snr", None)
            up_route = getattr(update, "best_route", None)
            eff_hops = 0 if is_local_flag else (up_hops if up_hops is not None else (existing.hops if existing else None))
            eff_rssi = None if is_local_flag else (up_rssi if up_rssi is not None else (existing.last_rssi if existing else None))
            eff_snr = None if is_local_flag else (up_snr if up_snr is not None else (existing.last_snr if existing else None))
            calc_route = up_route if up_route is not None else (existing.best_route if existing else "DIRECT")

            contact = self._build_updated_contact(
                canonical_key,
                update,
                existing,
                (clean_name, clean_alias, final_role, is_local_flag),
                (eff_hops, eff_rssi, eff_snr, calc_lqi, calc_status, calc_route),
            )

            self._nodes_by_key[canonical_key] = contact

            self._mark_dirty()
            return contact

    def _classify_advert_role(self, clean_name: str, role: str) -> tuple[str, bool]:
        """Clasifica el rol de un nodo descubierto y si es parte de la infraestructura de red."""
        role_upper = (role or "CLIENT").upper()
        return role_upper, role_upper in ("REPEATER", "ROUTER", "ROOM", "SENSOR")

    def _handle_local_discovery(self, norm_key: str, clean_name: str) -> tuple[bool, NodeContactInfo]:
        """Maneja el descubrimiento de la propia estación base local."""
        contact = self.add_or_update(
            norm_key,
            NodeContactUpdate(
                name=clean_name,
                role="LOCAL",
                is_local=True,
                auto_discovered=False,
                last_rssi=None,
                last_snr=None,
                hops=0,
            ),
        )
        return False, contact

    def discover_node(
        self,
        event: NodeDiscoveryEvent | str,
        **kwargs: Any,
    ) -> tuple[bool, NodeContactInfo]:
        """
        Descubre un nuevo nodo en el aire si no existía previamente.
        Acepta un objeto estructurado NodeDiscoveryEvent o parámetros legacy en kwargs.
        Retorna (is_new, contact_info).
        """
        if isinstance(event, NodeDiscoveryEvent):
            evt = event
        else:
            evt = NodeDiscoveryEvent(
                public_key=event,
                name=kwargs.get("name"),
                role=str(kwargs.get("role", "CLIENT")),
                rssi=kwargs.get("rssi"),
                snr=kwargs.get("snr"),
                hops=kwargs.get("hops"),
            )

        norm_key = evt.public_key.strip().lower()
        if not is_valid_node_key(norm_key):
            return False, NodeContactInfo(public_key="", name="Invalid", alias="Invalid")

        clean_name = (evt.name or f"Node_{norm_key[:6]}").strip()
        effective_role, is_infrastructure = self._classify_advert_role(clean_name, evt.role)

        if self.is_local_key(norm_key):
            return self._handle_local_discovery(norm_key, clean_name)

        existing_key = self._find_existing_key(norm_key, evt.name)
        now_ts = time.time()
        eff_ls = evt.last_seen if evt.last_seen is not None else (None if evt.is_import else now_ts)
        eff_heard = evt.last_advert_heard_at if evt.last_advert_heard_at is not None else (None if evt.is_import else now_ts)

        if existing_key:
            existing = self._nodes_by_key[existing_key]
            target_key = norm_key if len(norm_key) >= len(existing_key) else existing_key
            updated = self.add_or_update(
                target_key,
                NodeContactUpdate(
                    last_seen=eff_ls,
                    last_advert_heard_at=eff_heard,
                    last_rssi=evt.rssi,
                    last_snr=evt.snr,
                    hops=evt.hops,
                    name=evt.name if evt.name and evt.name != existing.name else None,
                    role=effective_role,
                ),
            )
            return False, updated

        is_auto_discovered = not is_infrastructure
        contact = self.add_or_update(
            norm_key,
            NodeContactUpdate(
                last_seen=eff_ls if eff_ls is not None else 0.0,
                last_advert_heard_at=eff_heard,
                name=clean_name,
                role=effective_role,
                last_rssi=evt.rssi,
                last_snr=evt.snr,
                hops=evt.hops,
                auto_discovered=is_auto_discovered,
                discovery_time=now_ts,
                verified_identity=len(norm_key) >= 12,
            ),
        )
        return is_auto_discovered, contact

    def list_discovered(self) -> list[dict[str, Any]]:
        """Lista los nodos clientes descubiertos automáticamente que no estén en la libreta."""
        with self._lock:
            results = []
            for c in self._nodes_by_key.values():
                if c.auto_discovered and (c.role or "").upper() == "CLIENT" and not c.is_local:
                    results.append(c.to_dict())
            return results

    def accept_discovered_contact(self, public_key: str) -> bool:
        """Marca un nodo descubierto como contacto permanente aceptado."""
        norm_key = public_key.strip().lower()
        with self._lock:
            existing_key = self._find_existing_key(norm_key)
            if not existing_key or existing_key not in self._nodes_by_key:
                return False
        self.add_or_update(
            existing_key,
            NodeContactUpdate(
                auto_discovered=False,
                is_favorite=True,
            ),
        )
        return True

    @staticmethod
    def _extract_telemetry_fields(telem: dict[str, Any]) -> dict[str, Any]:
        """Extrae de forma segura métricas ambientales y coordenadas GPS de telemetría."""
        from src.sensor_decoder import extract_telemetry_fields
        return extract_telemetry_fields(telem)

    def record_packet(self, event: PacketRecord) -> None:
        """Registra un evento de paquete para actualizar contadores de tráfico y salud."""
        norm_key = event.public_key.strip().lower()
        if not is_valid_node_key(norm_key):
            return

        with self._lock:
            is_local_node = self.is_local_key(norm_key)
            if is_local_node:
                event.rssi = None
                event.snr = None
                # El nodo local (estación base) nunca debe contabilizar paquetes entrantes (RX) de sí mismo
                if event.is_rx:
                    return

            existing_key = self._find_existing_key(norm_key)
            existing = self._nodes_by_key.get(existing_key) if existing_key else None
            target_key = norm_key if (existing_key and len(norm_key) > len(existing_key)) else (existing_key or norm_key)

            curr_rx = (existing.rx_packets if existing else 0) + (1 if event.is_rx else 0)
            curr_tx = (existing.tx_packets if existing else 0) + (0 if event.is_rx else 1)
            curr_err = (existing.error_count if existing else 0) + (1 if event.is_error else 0)

            telem = event.telemetry or {}
            extracted = self._extract_telemetry_fields(telem)

            rx_observed_ts = time.time() if event.is_rx else None
            m = self._merge_field

            eff_volt = extracted.get("voltage_v") if extracted.get("voltage_v") is not None else (existing.voltage_v if existing else None)
            calc_bat = extracted.get("battery_pct")
            if calc_bat is None and eff_volt is not None and 2.5 <= eff_volt <= 4.5:
                norm_pct, _ = normalize_battery(eff_volt)
                calc_bat = int(round(norm_pct))

            self.add_or_update(
                target_key,
                NodeContactUpdate(
                    last_seen=rx_observed_ts,
                    last_rx_at=rx_observed_ts,
                    name=existing.name if existing else f"Node_{target_key[:6]}",
                    alias=existing.alias if existing else "",
                    hops=m(event.hop_count, existing, "hops") if event.is_rx else (existing.hops if existing else None),
                    last_rssi=int(event.rssi) if (event.is_rx and event.rssi is not None) else None,
                    last_snr=float(event.snr) if (event.is_rx and event.snr is not None) else None,
                    battery_pct=m(calc_bat, existing, "battery_pct"),
                    rx_packets=curr_rx,
                    tx_packets=curr_tx,
                    error_count=curr_err,
                    temperature_c=m(extracted.get("temperature_c"), existing, "temperature_c"),
                    humidity_pct=m(extracted.get("humidity_pct"), existing, "humidity_pct"),
                    pressure_hpa=m(extracted.get("pressure_hpa"), existing, "pressure_hpa"),
                    voltage_v=m(extracted.get("voltage_v"), existing, "voltage_v"),
                    solar_v=m(extracted.get("solar_v"), existing, "solar_v"),
                    duty_cycle_pct=m(extracted.get("duty_cycle_pct"), existing, "duty_cycle_pct"),
                    latitude=m(extracted.get("latitude"), existing, "latitude"),
                    longitude=m(extracted.get("longitude"), existing, "longitude"),
                    position_valid=True if (extracted.get("latitude") is not None and extracted.get("longitude") is not None) else (existing.position_valid if existing else False),
                    position_source="TELEMETRY_LPP" if (extracted.get("latitude") is not None and extracted.get("longitude") is not None) else (existing.position_source if existing else None),
                    position_updated_at=rx_observed_ts if (extracted.get("latitude") is not None and extracted.get("longitude") is not None) else (existing.position_updated_at if existing else None),
                    altitude_m=m(extracted.get("altitude_m"), existing, "altitude_m"),
                    uptime=m(extracted.get("uptime"), existing, "uptime"),
                    clock=m(extracted.get("clock"), existing, "clock"),
                ),
            )

    def get_by_key_or_prefix(self, query: str) -> NodeContactInfo | None:
        """Busca un nodo por clave completa, prefijo hex o nombre exacto."""
        if not query:
            return None
        q = query.strip().lower()

        with self._lock:
            # 1. Búsqueda exacta por clave pública
            if q in self._nodes_by_key:
                return self._nodes_by_key[q]

            # 2. Coincidencia por prefijo hex único
            prefix_matches = [
                contact for key, contact in self._nodes_by_key.items()
                if len(q) < len(key) and key.startswith(q)
            ]
            if len(prefix_matches) == 1:
                return prefix_matches[0]

            # 3. Búsqueda por nombre o alias único (rechaza nombres duplicados ambiguos)
            name_matches = [
                contact for contact in self._nodes_by_key.values()
                if (contact.name and contact.name.strip().lower() == q) or
                   (contact.alias and contact.alias.strip().lower() == q)
            ]
            if len(name_matches) == 1:
                return name_matches[0]

            return None


    def find_by_name(self, name: str) -> NodeContactInfo | None:
        """Busca un nodo registrado por su nombre o alias de forma insensible a mayúsculas.
        Si existen múltiples nodos con el mismo nombre (ambiguo), devuelve None."""
        if not name:
            return None
        n_clean = name.strip().lower()
        with self._lock:
            matches = [
                contact for contact in self._nodes_by_key.values()
                if (contact.name and contact.name.strip().lower() == n_clean) or
                   (contact.alias and contact.alias.strip().lower() == n_clean)
            ]
            if len(matches) == 1:
                return matches[0]
            return None

    def get(self, query: str) -> NodeContactInfo | None:
        """Obtiene la información de un nodo por clave, prefijo o alias (alias estándar para get_by_key_or_prefix)."""
        return self.get_by_key_or_prefix(query)

    def get_contact(self, query: str) -> NodeContactInfo | None:
        """Obtiene la información del contacto buscando por clave, prefijo o alias."""
        return self.get_by_key_or_prefix(query)

    def get_node(self, query: str) -> NodeContactInfo | None:
        """Obtiene la información de un nodo buscando por clave, prefijo o alias."""
        return self.get_by_key_or_prefix(query)

    def resolve_name(self, query: str) -> str:
        """Resuelve el nombre amigable de un nodo o devuelve el identificador original."""
        contact = self.get_by_key_or_prefix(query)
        if contact:
            return contact.alias or contact.name
        return query

    def remove_node(self, public_key: str) -> bool:
        """Elimina un nodo del registro canónico."""
        if not public_key:
            return False
        with self._lock:
            canon = self.get_canonical_key(public_key)
            if not canon or canon not in self._nodes_by_key:
                return False
            self._nodes_by_key.pop(canon)
            self._mark_dirty()
            return True

    def list_nodes(self) -> list[dict[str, Any]]:
        """Retorna la lista de todos los nodos registrados en formato serializable sin duplicados."""
        with self._lock:
            return self._list_nodes_snapshot()

    def _snapshot_contacts(self) -> list[NodeContactInfo]:
        """Select canonical contacts once; callers hold _lock for a coherent snapshot."""
        seen_keys: set[str] = set()
        local_included = False
        result: list[NodeContactInfo] = []
        for contact in self._nodes_by_key.values():
            if not is_valid_node_key(contact.public_key) or contact.name.startswith("Node_unknow"):
                continue
            if contact.is_local or self.is_local_key(contact.public_key) or str(contact.role).upper() == "LOCAL":
                if local_included:
                    continue
                local_included = True
            norm_pk = contact.public_key.strip().lower()
            if norm_pk not in seen_keys:
                seen_keys.add(norm_pk)
                result.append(contact)
        return result

    def _list_nodes_snapshot(self) -> list[dict[str, Any]]:
        """Serialize the public view independently from persisted domain fields."""
        result: list[dict[str, Any]] = []
        contacts_snapshot = self._snapshot_contacts()
        local_node = next(
            (c for c in contacts_snapshot if c.is_local or self.is_local_key(c.public_key) or str(c.role).upper() == "LOCAL"),
            None,
        )
        local_lat = local_node.latitude if local_node else None
        local_lon = local_node.longitude if local_node else None
        if local_lat is None and local_node:
            local_lat = local_node.adv_lat
        if local_lon is None and local_node:
            local_lon = local_node.adv_lon

        for c in contacts_snapshot:
            node_dict = c.to_dict(local_lat=local_lat, local_lon=local_lon)
            # Preservar métricas medidas reales de LQI y hardware sin contaminación de presentación
            node_dict["lqi_score"] = c.lqi_score
            node_dict["lqi_status"] = c.lqi_status
            node_dict["measured_lqi_score"] = c.lqi_score
            node_dict["measured_lqi_status"] = c.lqi_status
            if c.max_tx_power is not None:
                node_dict["max_tx_power"] = c.max_tx_power
            result.append(node_dict)

        return result

    def is_repeater_key(self, public_key: str) -> bool:
        """Determina si una clave pública corresponde a un repetidor/router de infraestructura."""
        if not public_key:
            return False
        contact = self.get_by_key_or_prefix(public_key)
        if not contact:
            return False
        if contact.is_local or str(contact.role).upper() == "LOCAL":
            return False
        role_upper = str(contact.role).upper()
        return role_upper in ("REPEATER", "ROUTER")

    def list_client_contacts(self) -> list[dict[str, Any]]:
        """Retorna únicamente los contactos de tipo CLIENT (excluye repetidores, infraestructura y nodo local)."""
        return [
            n for n in self.list_nodes()
            if not n.get("is_local")
            and str(n.get("role", "")).upper() == "CLIENT"
            and not self.is_repeater_key(str(n.get("public_key", "")))
        ]

    def _extract_top_repeaters(self, nodes_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extrae y filtra los nodos de infraestructura (repetidores y routers) con mayor conectividad."""
        def is_repeater_node(n: dict[str, Any]) -> bool:
            if n.get("is_local") or str(n.get("role")).upper() == "LOCAL":
                return False
            role_str = str(n.get("role", "")).upper()
            return bool(
                role_str in ("REPEATER", "ROUTER")
                or n.get("type") == 2
                or n.get("adv_type") == 2
            )

        repeaters_list = []
        for n in nodes_list:
            if is_repeater_node(n):
                r_dict = dict(n)
                neighbors_list = r_dict.get("neighbors") or []
                clients_count = len(neighbors_list) if neighbors_list else int(r_dict.get("connected_clients_count") or 0)
                r_dict["connected_clients_count"] = clients_count
                r_dict["connected_clients_count_source"] = (
                    "neighbors" if neighbors_list else "reported" if clients_count else "unknown"
                )
                repeaters_list.append(r_dict)

        return heapq.nlargest(5, repeaters_list, key=lambda n: int(str(n.get("connected_clients_count", 0))))

    def get_analytics_summary(self) -> dict[str, Any]:
        """Calcula el resumen analítico avanzado (Top Nodos, Top Clientes, Top Errores)."""
        with self._lock:
            nodes_list = self._list_nodes_snapshot()
            contacts = {c.public_key: c for c in self._snapshot_contacts()}
            for node in nodes_list:
                contact = contacts[node["public_key"]]
                # Analytics describes observations, not defaults of an editor.
                for field_name in ("tx_power", "max_tx_power", "hop_limit", "repeat_enabled"):
                    node[field_name] = getattr(contact, field_name)

        # 1. Top Nodos por Tráfico y Señal
        top_traffic = heapq.nlargest(10, nodes_list, key=lambda n: int(str(n.get("total_packets", 0))))
        measured_nodes = [n for n in nodes_list if n.get("last_snr") is not None]
        top_best_signal = heapq.nlargest(5, measured_nodes, key=lambda n: float(n.get("last_snr", 0.0)))
        top_worst_signal = heapq.nsmallest(5, measured_nodes, key=lambda n: float(n.get("last_snr", 0.0)))

        # 2. Top Routers & Repetidores
        top_repeaters = self._extract_top_repeaters(nodes_list)

        # 3. Top Errores y Totales Globales
        error_items: list[dict[str, Any]] = [{"category": k, "count": v} for k, v in self.error_categories.items()]
        sorted_errors = sorted(error_items, key=lambda e: int(str(e["count"])), reverse=True)

        total_rx = sum(int(str(n.get("rx_packets", 0))) for n in nodes_list)
        total_tx = sum(int(str(n.get("tx_packets", 0))) for n in nodes_list)
        total_err = sum(int(str(n.get("error_count", 0))) for n in nodes_list)

        return {
            "summary": {
                "total_nodes": len(nodes_list),
                "total_rx_packets": total_rx,
                "total_tx_packets": total_tx,
                "total_errors": total_err,
                "global_error_rate_pct": round((total_err / ((total_rx + total_tx) or 1)) * 100, 2),
            },
            "top_nodes_by_traffic": top_traffic,
            "top_nodes_best_snr": top_best_signal,
            "top_nodes_worst_snr": top_worst_signal,
            "top_repeaters_by_clients": top_repeaters,
            "top_error_breakdown": sorted_errors,
        }

    def reset_analytics(self) -> dict[str, int]:
        """Restablece los contadores de paquetes y errores de todos los nodos y categorías."""
        with self._lock:
            reset_count = 0
            for k, contact in list(self._nodes_by_key.items()):
                new_contact = contact.replace_fields(
                    rx_packets=0,
                    tx_packets=0,
                    error_count=0,
                    packets_sent=0,
                    packets_recv=0,
                    duplicate_packets=0,
                    packet_errors=0,
                )
                self._nodes_by_key[k] = new_contact
                reset_count += 1
            self.error_categories.clear()
            self._mark_dirty()
            return {"nodes_reset": reset_count}

    def get_all_lqi_metrics(self) -> list[dict[str, Any]]:
        """Retorna métricas LQI de todos los nodos ordenadas por puntaje descendente."""
        metrics: list[dict[str, Any]] = []
        for node in self.list_nodes():
            metrics.append({
                "public_key": node.get("public_key", ""),
                "name": node.get("name") or node.get("alias", ""),
                "role": node.get("role", "CLIENT"),
                "lqi_score": float(node.get("lqi_score", 0.0)),
                "lqi_status": node.get("lqi_status", "UNKNOWN"),
                "best_route": node.get("best_route", "DIRECT"),
                "last_seen": float(node.get("last_seen", 0.0)),
            })
        return sorted(metrics, key=lambda x: x["lqi_score"], reverse=True)

    def get_count(self) -> int:
        """Retorna el conteo exacto de nodos únicos registrados deduplicando el nodo local y colisiones."""
        return len(self.list_nodes())

    def cleanup_inactive(self, max_idle_seconds: float = 86400.0 * 7) -> int:
        """Elimina nodos inactivos que no hayan transmitido durante el período especificado."""
        now = time.time()
        with self._lock:
            to_remove = [
                k for k, c in self._nodes_by_key.items()
                if (now - c.last_seen) > max_idle_seconds
                and not c.is_local
                and not self.is_local_key(k)
                and str(c.role).upper() != "LOCAL"
            ]
            for k in to_remove:
                self._nodes_by_key.pop(k, None)

        if to_remove:
            with self._lock:
                self._mark_dirty()
            logging.info(f"Limpieza de NodeRegistry: eliminados {len(to_remove)} nodos obsoletos.")
        return len(to_remove)

    def save_to_file(self, filepath: str | Path | None = None, force: bool = False) -> bool:
        """Guarda la libreta de contactos y estado de nodos en un archivo JSON sin duplicados si hubo cambios."""
        # Serialize writers so a slow older snapshot cannot replace a newer file.
        # The async facade runs this filesystem/writer wait in a worker thread.
        with self._save_lock:
            return self._save_snapshot_to_file(filepath, force)

    def _save_snapshot_to_file(self, filepath: str | Path | None, force: bool) -> bool:
        with self._lock:
            if not force and not self._dirty:
                logging.debug("NodeRegistry sin cambios pendientes de persistencia (omitiendo escritura en disco)")
                return True
            generation = self._generation
            # Keep raw domain values, including None; view-only suggestions must
            # never become firmware observations after a save/load roundtrip.
            nodes_list = [contact.as_flat_dict() for contact in self._snapshot_contacts()]
            data = {
                "local_pubkey": self._local_pubkey,
                "saved_at": time.time(),
                "nodes": nodes_list,
                "error_categories": dict(self.error_categories),
            }

        target_str = str(filepath or os.getenv("NODE_REGISTRY_STORAGE_PATH") or os.path.join("data", "node_registry.json"))
        target_path = Path(target_str)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target_path.with_name(f"{target_path.stem}_{os.getpid()}_{time.time_ns()}.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(target_path)
            with self._lock:
                if self._generation == generation:
                    self._dirty = False
            logging.debug(f"NodeRegistry guardado exitosamente en {target_path} ({len(nodes_list)} nodos)")
            return True
        except Exception as e:
            logging.warning(f"Error guardando NodeRegistry en {target_path}: {e}")
            return False

    async def save_to_file_async(self, filepath: str | Path | None = None, force: bool = False) -> bool:
        """Guarda la libreta de contactos y estado de nodos de forma asíncrona sin bloquear el event loop."""
        return await asyncio.to_thread(self.save_to_file, filepath, force)

    def _deserialize_node_contact(self, nd: dict[str, Any]) -> NodeContactInfo | None:
        """Reconstruye un objeto NodeContactInfo a partir de un diccionario serializado."""
        pk = nd.get("public_key")
        if not pk or not is_valid_node_key(pk):
            return None

        def _safe_int(val: Any, default: int = 0) -> int:
            if val is None:
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def _safe_float(val: Any, default: float = 0.0) -> float:
            if val is None:
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        raw_neighbors = nd.get("neighbors", ())
        neighbors_tuple = tuple(raw_neighbors) if isinstance(raw_neighbors, (list, tuple)) else ()

        raw_bat = nd.get("battery_pct")
        if raw_bat is not None:
            raw_bat = _safe_int(raw_bat, 0)
        v_v = _safe_float(nd.get("voltage_v"), 0.0) if nd.get("voltage_v") is not None else None
        if raw_bat is None and v_v is not None and 2.5 <= v_v <= 4.5:
            pct_norm, _ = normalize_battery(v_v)
            raw_bat = int(round(pct_norm))

        stored_lqi = nd.get("measured_lqi_score")
        if stored_lqi is None:
            stored_lqi = nd.get("lqi_score", 0.0)
        stored_status = nd.get("measured_lqi_status")
        if not stored_status or stored_status == "DISCONNECTED":
            raw_st = str(nd.get("lqi_status", "UNKNOWN"))
            stored_status = raw_st if raw_st != "DISCONNECTED" else "UNKNOWN"

        return NodeContactInfo(
            public_key=str(pk).strip().lower(),
            name=str(nd.get("name", "")),
            alias=str(nd.get("alias", "")),
            role=str(nd.get("role", "CLIENT")),
            hops=_safe_int(nd.get("hops")) if nd.get("hops") is not None else None,
            last_rssi=_safe_int(nd.get("last_rssi")) if nd.get("last_rssi") is not None else None,
            last_snr=_safe_float(nd.get("last_snr")) if nd.get("last_snr") is not None else None,
            battery_pct=raw_bat,
            last_seen=_safe_float(nd.get("last_seen", 0.0)),
            rx_packets=_safe_int(nd.get("rx_packets", 0)),
            tx_packets=_safe_int(nd.get("tx_packets", 0)),
            error_count=_safe_int(nd.get("error_count", 0)),
            connected_clients_count=_safe_int(nd.get("connected_clients_count", 0)),
            neighbors=neighbors_tuple,
            temperature_c=_safe_float(nd.get("temperature_c")) if nd.get("temperature_c") is not None else None,
            humidity_pct=_safe_float(nd.get("humidity_pct")) if nd.get("humidity_pct") is not None else None,
            pressure_hpa=_safe_float(nd.get("pressure_hpa")) if nd.get("pressure_hpa") is not None else None,
            voltage_v=v_v,
            solar_v=_safe_float(nd.get("solar_v")) if nd.get("solar_v") is not None else None,
            latitude=_safe_float(nd.get("latitude")) if nd.get("latitude") is not None else (_safe_float(nd.get("lat")) if nd.get("lat") is not None else None),
            longitude=_safe_float(nd.get("longitude")) if nd.get("longitude") is not None else (_safe_float(nd.get("lon")) if nd.get("lon") is not None else None),
            adv_lat=_safe_float(nd.get("adv_lat")) if nd.get("adv_lat") is not None else None,
            adv_lon=_safe_float(nd.get("adv_lon")) if nd.get("adv_lon") is not None else None,
            altitude_m=_safe_float(nd.get("altitude_m")) if nd.get("altitude_m") is not None else None,
            uptime=nd.get("uptime"),
            clock=nd.get("clock"),
            airtime_ms=_safe_int(nd.get("airtime_ms")) if nd.get("airtime_ms") is not None else None,
            duty_cycle_pct=_safe_float(nd.get("duty_cycle_pct")) if nd.get("duty_cycle_pct") is not None else None,
            noise_floor_dbm=_safe_int(nd.get("noise_floor_dbm")) if nd.get("noise_floor_dbm") is not None else None,
            packets_sent=_safe_int(nd.get("packets_sent")) if nd.get("packets_sent") is not None else None,
            packets_recv=_safe_int(nd.get("packets_recv")) if nd.get("packets_recv") is not None else None,
            duplicate_packets=_safe_int(nd.get("duplicate_packets")) if nd.get("duplicate_packets") is not None else None,
            packet_errors=_safe_int(nd.get("packet_errors")) if nd.get("packet_errors") is not None else None,
            queue_len=_safe_int(nd.get("queue_len")) if nd.get("queue_len") is not None else None,
            owner_name=nd.get("owner_name"),
            owner_info=nd.get("owner_info"),
            firmware_version=nd.get("firmware_version"),
            hardware_board=nd.get("hardware_board"),
            advert_interval=_safe_int(nd.get("advert_interval")) if nd.get("advert_interval") is not None else None,
            flood_advert_interval=_safe_int(nd.get("flood_advert_interval")) if nd.get("flood_advert_interval") is not None else None,
            allow_read_only=bool(nd.get("allow_read_only")) if nd.get("allow_read_only") is not None else None,
            repeat_enabled=bool(nd.get("repeat_enabled", False)) if nd.get("repeat_enabled") is not None else None,
            tx_power=_safe_int(nd.get("tx_power")) if nd.get("tx_power") is not None else None,
            max_tx_power=_safe_int(nd.get("max_tx_power")) if nd.get("max_tx_power") is not None else None,
            hop_limit=_safe_int(nd.get("hop_limit")) if nd.get("hop_limit") is not None else None,
            frequency=_safe_float(nd.get("frequency")) if nd.get("frequency") is not None else None,
            spreading_factor=_safe_int(nd.get("spreading_factor")) if nd.get("spreading_factor") is not None else None,
            bandwidth=_safe_float(nd.get("bandwidth")) if nd.get("bandwidth") is not None else None,
            coding_rate=str(nd["coding_rate"]) if nd.get("coding_rate") is not None else None,
            fixed_position=bool(nd.get("fixed_position", False)) if nd.get("fixed_position") is not None else None,
            flags=_safe_int(nd.get("flags")) if nd.get("flags") is not None else None,
            last_advert=_safe_float(nd.get("last_advert")) if nd.get("last_advert") is not None else None,
            last_advert_heard_at=_safe_float(nd.get("last_advert_heard_at")) if nd.get("last_advert_heard_at") is not None else None,
            last_rx_at=_safe_float(nd.get("last_rx_at")) if nd.get("last_rx_at") is not None else None,
            last_rx_route=nd.get("last_rx_route") if isinstance(nd.get("last_rx_route"), dict) else None,
            out_path=str(nd["out_path"]) if nd.get("out_path") is not None else None,
            out_path_len=_safe_int(nd.get("out_path_len")) if nd.get("out_path_len") is not None else None,
            out_path_hash_mode=normalize_hash_mode(nd.get("out_path_hash_mode")) if nd.get("out_path_hash_mode") is not None else None,
            out_route_state=str(nd.get("out_route_state", "unknown")),
            out_path_hash_size_bytes=_safe_int(nd.get("out_path_hash_size_bytes")) if nd.get("out_path_hash_size_bytes") is not None else None,
            hops_source=str(nd.get("hops_source", "unknown")),
            position_valid=bool(nd.get("position_valid", False)),
            position_source=nd.get("position_source"),
            position_updated_at=_safe_float(nd.get("position_updated_at")) if nd.get("position_updated_at") is not None else None,
            is_local=bool(nd.get("is_local", False)),
            auto_discovered=bool(nd.get("auto_discovered", False)),
            discovery_time=_safe_float(nd.get("discovery_time", 0.0)),
            verified_identity=bool(nd.get("verified_identity", False)),
            is_favorite=bool(nd.get("is_favorite", False)),
            lqi_score=_safe_float(stored_lqi, 0.0),
            lqi_status=str(stored_status),
            best_route=str(nd.get("best_route", "DIRECT")),
        )

    def load_from_file(self, filepath: str | Path | None = None) -> int:
        """Carga la libreta de contactos y estado de nodos desde un archivo JSON."""
        target_str = str(filepath or os.getenv("NODE_REGISTRY_STORAGE_PATH") or os.path.join("data", "node_registry.json"))
        target_path = Path(target_str)
        if not target_path.is_file():
            return 0
        try:
            with open(target_path, encoding="utf-8") as f:
                data = json.load(f)
            loaded_count = 0
            with self._lock:
                for nd in data.get("nodes", []):
                    try:
                        contact = self._deserialize_node_contact(nd)
                    except Exception as ex_node:
                        logging.warning(f"Omitiendo nodo inválido en {target_path}: {ex_node}")
                        continue
                    if not contact:
                        continue
                    self._nodes_by_key[contact.public_key] = contact
                    loaded_count += 1

                if "local_pubkey" in data and data["local_pubkey"]:
                    self.set_local_pubkey(data["local_pubkey"])
                elif self._local_pubkey:
                    self.set_local_pubkey(self._local_pubkey)
                if "error_categories" in data and isinstance(data["error_categories"], dict):
                    self.error_categories.update(data["error_categories"])

            logging.info(f"NodeRegistry cargado exitosamente desde {target_path} ({loaded_count} nodos)")
            return loaded_count
        except Exception as e:
            logging.warning(f"Error cargando NodeRegistry desde {target_path}: {e}")
            return 0

"""
Node Registry & Contact Directory for MeshCore Bridge.
Mantiene un registro de nodos activos, libretas de contactos, alias, telemetría y métricas RF
en memoria con soporte de búsqueda O(1), estadísticas de tráfico y análisis topológico.
"""

from __future__ import annotations

import heapq
import json
import logging
import os
from pathlib import Path
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from src.lqi_engine import LinkQualityEngine, LQIStatus


def _safe_int(val: Any) -> int | None:
    """Convierte de forma segura valores de batería o contadores a entero."""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return int(val)
        cleaned = str(val).strip().rstrip("%").rstrip("mV").rstrip("V")
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    """Convierte de forma segura valores a flotante."""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        cleaned = str(val).strip().rstrip("dB").rstrip("dBm").rstrip("MHz").rstrip("V").rstrip("°C").rstrip("%")
        return float(cleaned)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True, slots=True)
class NodeContactInfo:
    """Información consolidada de un nodo o contacto en la malla."""
    public_key: str
    name: str
    alias: str
    role: str = "CLIENT"
    hops: int | None = None
    last_rssi: int | None = None
    last_snr: float | None = None
    battery_pct: int | None = None
    last_seen: float = 0.0
    rx_packets: int = 0
    tx_packets: int = 0
    error_count: int = 0
    connected_clients_count: int = 0
    neighbors: tuple[str, ...] = field(default_factory=tuple)
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
    repeat_enabled: bool | None = None
    tx_power: int | None = None
    frequency: float | None = None
    spreading_factor: int | None = None
    bandwidth: float | None = None
    coding_rate: str | None = None
    fixed_position: bool | None = None
    is_local: bool = False
    auto_discovered: bool = False
    discovery_time: float = 0.0
    verified_identity: bool = False
    is_favorite: bool = False
    lqi_score: float = 0.0
    lqi_status: str = "UNKNOWN"
    best_route: str = "DIRECT"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key_prefix"] = self.public_key[:8] if len(self.public_key) >= 8 else self.public_key
        d["total_packets"] = self.rx_packets + self.tx_packets
        d["error_rate_pct"] = round((self.error_count / (d["total_packets"] or 1)) * 100, 1)
        d["is_local"] = self.is_local
        d["lat"] = self.latitude
        d["lon"] = self.longitude
        d["lqi_score"] = round(self.lqi_score, 1)
        d["lqi_status"] = self.lqi_status
        d["best_route"] = self.best_route
        return d


@dataclass(slots=True)
class NodeContactUpdate:
    """Objeto de parámetro para add_or_update."""
    name: str | None = None
    alias: str | None = None
    role: str | None = None
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
    repeat_enabled: bool | None = None
    tx_power: int | None = None
    frequency: float | None = None
    spreading_factor: int | None = None
    bandwidth: float | None = None
    coding_rate: str | None = None
    fixed_position: bool | None = None


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


def is_valid_node_key(key: Any) -> bool:
    """Verifica si una clave pública es válida para registrar o descubrir un nodo."""
    if not key or not isinstance(key, str):
        return False
    norm = key.strip().lower()
    if not norm or norm in INVALID_NODE_KEYS or len(norm) < 4:
        return False
    if norm.startswith("unknow") or norm.startswith("broadcast") or norm.startswith("0x0000"):
        return False
    return True


class NodeRegistry:
    """Directorio en memoria para contactos y resolución de nombres de la red MeshCore."""

    def __init__(self) -> None:
        self._nodes_by_key: dict[str, NodeContactInfo] = {}
        self._nodes_by_name: dict[str, str] = {}  # lower(name) -> public_key
        self._local_pubkey: str = ""
        self.error_categories: dict[str, int] = {
            "SERIAL_TIMEOUT": 0,
            "TX_BUFFER_OVERFLOW": 0,
            "CRC_MISMATCH": 0,
            "RADIO_BUSY": 0,
            "ROUTE_UNREACHABLE": 0,
            "MQTT_DISCONNECT": 0,
        }
        self.last_sync_timestamp: float = 0.0

    def set_local_pubkey(self, pubkey: str) -> None:
        """Establece la clave pública del nodo local para distinguirlo de nodos remotos."""
        self._local_pubkey = str(pubkey).strip().lower()

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
        if not norm or norm == "local":
            return True
        if not self._local_pubkey:
            return False
        loc = self._local_pubkey
        return norm == loc or (len(loc) >= 8 and norm.startswith(loc[:8])) or (len(norm) >= 8 and loc.startswith(norm[:8]))

    def _find_existing_key(self, raw_key: str, name: str | None = None) -> str | None:
        """Encuentra si ya existe una clave exacta o unificada por prefijo/nombre para evitar duplicados."""
        norm = raw_key.strip().lower() if raw_key and isinstance(raw_key, str) else ""

        # 1. Coincidencia exacta por clave pública
        if norm and norm in self._nodes_by_key:
            return norm

        # 2. Coincidencia por prefijo (>= 6 caracteres comunes)
        if norm and is_valid_node_key(norm):
            for k in self._nodes_by_key:
                if (len(k) >= 6 and len(norm) >= 6 and (k.startswith(norm) or norm.startswith(k))) or \
                   (len(norm) >= 8 and len(k) >= 8 and (k.startswith(norm[:8]) or norm.startswith(k[:8]))):
                    return k

        # 3. Coincidencia por nombre exacto o alias si no es un nombre genérico
        if name:
            n_clean = name.strip().lower()
            if n_clean and not n_clean.startswith("node_") and not n_clean.startswith("unknow") and len(n_clean) >= 2:
                for k, node in self._nodes_by_key.items():
                    if (node.name and node.name.strip().lower() == n_clean) or \
                       (node.alias and node.alias.strip().lower() == n_clean):
                        return k

        return None


    def get_canonical_key(self, raw_key: str, name: str | None = None) -> str:
        """Devuelve la clave pública canónica (más larga o conocida) para una clave o prefijo."""
        if not is_valid_node_key(raw_key):
            return ""
        existing = self._find_existing_key(raw_key, name)
        return existing if existing else raw_key.strip().lower()

    def add_or_update(self, public_key: str, update: NodeContactUpdate) -> NodeContactInfo:
        """Añade o actualiza la información de un nodo preservando métricas acumuladas y deduplicando prefijos."""
        norm_key = public_key.strip().lower()
        if not is_valid_node_key(norm_key):
            return NodeContactInfo(
                public_key="",
                name="Invalid",
                alias="Invalid",
            )
        clean_name_candidate = (update.name or "").strip()

        # Buscar si ya existe una entrada para este nodo (evita duplicados de prefijo vs clave completa)
        existing_key = self._find_existing_key(norm_key, clean_name_candidate)
        existing: NodeContactInfo | None = None

        # Determinar clave canónica (preferir la más larga de 64 caracteres)
        canonical_key = norm_key
        if existing_key:
            existing = self._nodes_by_key.get(existing_key)
            if existing and len(existing_key) > len(norm_key):
                canonical_key = existing_key
            elif existing_key != norm_key and existing_key in self._nodes_by_key:
                # Migrar de la clave corta a la clave larga
                del self._nodes_by_key[existing_key]

        clean_name = clean_name_candidate or (existing.name if existing else f"Node_{canonical_key[:6]}")
        clean_alias = (update.alias or "").strip() or (existing.alias if existing else clean_name)
        now = time.time()

        is_local_flag = update.is_local if update.is_local is not None else (
            existing.is_local if existing else self.is_local_key(canonical_key)
        )
        role_default = "LOCAL" if is_local_flag else "CLIENT"

        # Cálculo / Suavizado de LQI
        eff_snr = None if is_local_flag else (update.last_snr if update.last_snr is not None else (existing.last_snr if existing else None))
        eff_rssi = None if is_local_flag else (update.last_rssi if update.last_rssi is not None else (existing.last_rssi if existing else None))
        eff_hops = 0 if is_local_flag else (update.hops if update.hops is not None else (existing.hops if existing else 0))

        if update.lqi_score is not None:
            calc_lqi = float(update.lqi_score)
            calc_status = update.lqi_status or LinkQualityEngine.classify_lqi_status(calc_lqi)
        elif is_local_flag:
            calc_lqi = 100.0
            calc_status = LQIStatus.EXCELLENT.value
        elif eff_snr is not None or eff_rssi is not None:
            instant_lqi = LinkQualityEngine.compute_instant_lqi(eff_snr, eff_rssi, eff_hops or 0)
            prev_lqi = existing.lqi_score if existing else 0.0
            calc_lqi = LinkQualityEngine.update_ema_lqi(prev_lqi, instant_lqi)
            calc_status = LinkQualityEngine.classify_lqi_status(calc_lqi)
        else:
            calc_lqi = existing.lqi_score if existing else 0.0
            calc_status = existing.lqi_status if existing else "UNKNOWN"

        calc_route = update.best_route if update.best_route is not None else (existing.best_route if existing else "DIRECT")

        contact = NodeContactInfo(
            public_key=canonical_key,
            name=clean_name,
            alias=clean_alias,
            role=update.role if update.role is not None else (existing.role if existing else role_default),
            is_local=is_local_flag,
            hops=eff_hops if not is_local_flag else 0,
            last_rssi=eff_rssi,
            last_snr=eff_snr,
            lqi_score=calc_lqi,
            lqi_status=calc_status,
            best_route=calc_route,
            battery_pct=update.battery_pct if update.battery_pct is not None else (existing.battery_pct if existing else None),
            last_seen=now,
            rx_packets=update.rx_packets if update.rx_packets is not None else (existing.rx_packets if existing else 0),
            tx_packets=update.tx_packets if update.tx_packets is not None else (existing.tx_packets if existing else 0),
            error_count=update.error_count if update.error_count is not None else (existing.error_count if existing else 0),
            connected_clients_count=update.connected_clients_count if update.connected_clients_count is not None else (existing.connected_clients_count if existing else 0),
            neighbors=tuple(update.neighbors) if update.neighbors is not None else (existing.neighbors if existing else ()),
            temperature_c=update.temperature_c if update.temperature_c is not None else (existing.temperature_c if existing else None),
            humidity_pct=update.humidity_pct if update.humidity_pct is not None else (existing.humidity_pct if existing else None),
            pressure_hpa=update.pressure_hpa if update.pressure_hpa is not None else (existing.pressure_hpa if existing else None),
            voltage_v=update.voltage_v if update.voltage_v is not None else (existing.voltage_v if existing else None),
            solar_v=update.solar_v if update.solar_v is not None else (existing.solar_v if existing else None),
            latitude=update.latitude if update.latitude is not None else (existing.latitude if existing else None),
            longitude=update.longitude if update.longitude is not None else (existing.longitude if existing else None),
            altitude_m=update.altitude_m if update.altitude_m is not None else (existing.altitude_m if existing else None),
            uptime=update.uptime if update.uptime is not None else (existing.uptime if existing else None),
            clock=update.clock if update.clock is not None else (existing.clock if existing else None),
            airtime_ms=update.airtime_ms if update.airtime_ms is not None else (existing.airtime_ms if existing else None),
            noise_floor_dbm=update.noise_floor_dbm if update.noise_floor_dbm is not None else (existing.noise_floor_dbm if existing else None),
            packets_sent=update.packets_sent if update.packets_sent is not None else (existing.packets_sent if existing else None),
            packets_recv=update.packets_recv if update.packets_recv is not None else (existing.packets_recv if existing else None),
            duplicate_packets=update.duplicate_packets if update.duplicate_packets is not None else (existing.duplicate_packets if existing else None),
            packet_errors=update.packet_errors if update.packet_errors is not None else (existing.packet_errors if existing else None),
            queue_len=update.queue_len if update.queue_len is not None else (existing.queue_len if existing else None),
            owner_name=update.owner_name if update.owner_name is not None else (existing.owner_name if existing else None),
            owner_info=update.owner_info if update.owner_info is not None else (existing.owner_info if existing else None),
            firmware_version=update.firmware_version if update.firmware_version is not None else (existing.firmware_version if existing else None),
            hardware_board=update.hardware_board if update.hardware_board is not None else (existing.hardware_board if existing else None),
            advert_interval=update.advert_interval if update.advert_interval is not None else (existing.advert_interval if existing else None),
            repeat_enabled=update.repeat_enabled if update.repeat_enabled is not None else (existing.repeat_enabled if existing else None),
            tx_power=update.tx_power if update.tx_power is not None else (existing.tx_power if existing else None),
            frequency=update.frequency if update.frequency is not None else (existing.frequency if existing else None),
            spreading_factor=update.spreading_factor if update.spreading_factor is not None else (existing.spreading_factor if existing else None),
            bandwidth=update.bandwidth if update.bandwidth is not None else (existing.bandwidth if existing else None),
            coding_rate=update.coding_rate if update.coding_rate is not None else (existing.coding_rate if existing else None),
            fixed_position=update.fixed_position if update.fixed_position is not None else (existing.fixed_position if existing else None),
            auto_discovered=update.auto_discovered if update.auto_discovered is not None else (existing.auto_discovered if existing else False),
            discovery_time=update.discovery_time if update.discovery_time is not None else (existing.discovery_time if existing else 0.0),
            verified_identity=update.verified_identity if update.verified_identity is not None else (existing.verified_identity if existing else False),
            is_favorite=update.is_favorite if update.is_favorite is not None else (existing.is_favorite if existing else False),
        )

        self._nodes_by_key[canonical_key] = contact
        self._nodes_by_name[clean_name.lower()] = canonical_key
        if clean_alias:
            self._nodes_by_name[clean_alias.lower()] = canonical_key

        return contact

    def get_all_lqi_metrics(self) -> list[dict[str, Any]]:
        """Retorna las métricas LQI y estado de enlace de todos los nodos registrados."""
        now = time.time()
        results = []
        for contact in self._nodes_by_key.values():
            if contact.is_local:
                decayed_lqi = 100.0
                status = LQIStatus.EXCELLENT.value
            else:
                decayed_lqi = LinkQualityEngine.apply_time_decay(contact.lqi_score, contact.last_seen or now, now)
                status = LinkQualityEngine.classify_lqi_status(decayed_lqi)

            results.append({
                "public_key": contact.public_key,
                "key_prefix": contact.public_key[:8] if len(contact.public_key) >= 8 else contact.public_key,
                "name": contact.name,
                "alias": contact.alias,
                "role": contact.role,
                "lqi_score": round(decayed_lqi, 1),
                "lqi_status": status,
                "best_route": contact.best_route,
                "last_snr": contact.last_snr,
                "last_rssi": contact.last_rssi,
                "hops": contact.hops,
                "is_local": contact.is_local,
                "last_seen_seconds_ago": round(max(0.0, now - contact.last_seen), 1) if contact.last_seen else None,
            })
        return results

    def discover_node(
        self,
        public_key: str,
        name: str | None = None,
        role: str = "CLIENT",
        rssi: int | None = None,
        snr: float | None = None,
        hops: int | None = None,
    ) -> tuple[bool, NodeContactInfo]:
        """
        Descubre un nuevo nodo en el aire si no existía previamente.
        Retorna (is_new, contact_info).
        """
        norm_key = public_key.strip().lower()
        if not is_valid_node_key(norm_key):
            return False, NodeContactInfo(public_key="", name="Invalid", alias="Invalid")

        clean_name = (name or f"Node_{norm_key[:6]}").strip()
        name_upper = clean_name.upper()
        role_upper = (role or "CLIENT").upper()
        is_infrastructure = (
            role_upper in ("REPEATER", "ROUTER", "ROOM", "SENSOR")
            or name_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-"))
            or "REPEATER" in name_upper
            or "ROUTER" in name_upper
            or "SENSOR" in name_upper
            or "ROOM" in name_upper
            or "BBS" in name_upper
        )
        effective_role = "REPEATER" if ("REPEATER" in name_upper or name_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-"))) else role

        # Si corresponde a la estación base local, marcar como LOCAL y no auto_discovered
        if self.is_local_key(norm_key):
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

        existing_key = self._find_existing_key(norm_key, name)
        if existing_key:
            existing = self._nodes_by_key[existing_key]
            updated = self.add_or_update(
                existing_key,
                NodeContactUpdate(
                    last_rssi=rssi,
                    last_snr=snr,
                    hops=hops,
                    name=name if name and name != existing.name else None,
                    role=effective_role if existing.role == "CLIENT" and is_infrastructure else None,
                ),
            )
            return False, updated

        # Si es un nodo de infraestructura (repetidor, sensor, sala), no marcar como auto_discovered para la libreta
        is_auto_discovered = not is_infrastructure

        contact = self.add_or_update(
            norm_key,
            NodeContactUpdate(
                name=clean_name,
                role=effective_role,
                last_rssi=rssi,
                last_snr=snr,
                hops=hops,
                auto_discovered=is_auto_discovered,
                discovery_time=time.time(),
                verified_identity=len(norm_key) >= 12,
            ),
        )
        return is_auto_discovered, contact

    def list_discovered(self, pending_only: bool = False) -> list[dict[str, Any]]:
        """Lista los nodos clientes descubiertos automáticamente que no estén en la libreta."""
        results = []
        for c in self._nodes_by_key.values():
            if c.auto_discovered and (c.role or "").upper() == "CLIENT" and not c.is_local:
                results.append(c.to_dict())
        return results

    def accept_discovered_contact(self, public_key: str) -> bool:
        """Marca un nodo descubierto como contacto permanente aceptado."""
        norm_key = public_key.strip().lower()
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

    def record_packet(self, event: PacketRecord) -> None:
        """Registra un evento de paquete para actualizar contadores de tráfico y salud."""
        norm_key = event.public_key.strip().lower()
        if not is_valid_node_key(norm_key):
            return

        is_local_node = self.is_local_key(norm_key)
        if is_local_node:
            event.rssi = None
            event.snr = None

        existing_key = self._find_existing_key(norm_key)
        existing = self._nodes_by_key.get(existing_key) if existing_key else None
        target_key = existing_key or norm_key

        curr_rx = (existing.rx_packets if existing else 0) + (1 if event.is_rx else 0)
        curr_tx = (existing.tx_packets if existing else 0) + (0 if event.is_rx else 1)
        curr_err = (existing.error_count if existing else 0) + (1 if event.is_error else 0)

        telem = event.telemetry or {}
        temp = _safe_float(telem.get("temperature_c", telem.get("temperature")))
        hum = _safe_float(telem.get("humidity_pct", telem.get("humidity")))
        press = _safe_float(telem.get("pressure_hpa", telem.get("pressure")))
        volt = _safe_float(telem.get("voltage_v", telem.get("voltage")))
        solar = _safe_float(telem.get("solar_v", telem.get("solar_voltage", telem.get("solar"))))
        batt = _safe_int(telem.get("battery_pct", telem.get("battery", telem.get("batt"))))

        gps = telem.get("gps", {})
        lat_raw = telem.get("lat", telem.get("latitude", telem.get("gps_lat", telem.get("adv_lat"))))
        if lat_raw is None and isinstance(gps, dict):
            lat_raw = gps.get("latitude", gps.get("lat"))
        lon_raw = telem.get("lon", telem.get("longitude", telem.get("gps_lon", telem.get("adv_lon"))))
        if lon_raw is None and isinstance(gps, dict):
            lon_raw = gps.get("longitude", gps.get("lon"))
        alt_raw = telem.get("alt", telem.get("altitude", telem.get("altitude_m")))
        if alt_raw is None and isinstance(gps, dict):
            alt_raw = gps.get("altitude", gps.get("alt", gps.get("altitude_m")))

        self.add_or_update(
            target_key,
            NodeContactUpdate(
                name=existing.name if existing else f"Node_{target_key[:6]}",
                alias=existing.alias if existing else "",
                hops=event.hop_count if event.hop_count is not None else (existing.hops if existing else None),
                last_rssi=int(event.rssi) if event.rssi is not None else (existing.last_rssi if existing else None),
                last_snr=float(event.snr) if event.snr is not None else (existing.last_snr if existing else None),
                battery_pct=batt if batt is not None else (existing.battery_pct if existing else None),
                rx_packets=curr_rx,
                tx_packets=curr_tx,
                error_count=curr_err,
                temperature_c=temp if temp is not None else (existing.temperature_c if existing else None),
                humidity_pct=hum if hum is not None else (existing.humidity_pct if existing else None),
                pressure_hpa=press if press is not None else (existing.pressure_hpa if existing else None),
                voltage_v=volt if volt is not None else (existing.voltage_v if existing else None),
                solar_v=solar if solar is not None else (existing.solar_v if existing else None),
                latitude=_safe_float(lat_raw) if lat_raw is not None else (existing.latitude if existing else None),
                longitude=_safe_float(lon_raw) if lon_raw is not None else (existing.longitude if existing else None),
                altitude_m=_safe_float(alt_raw) if alt_raw is not None else (existing.altitude_m if existing else None),
                uptime=str(telem["uptime"]) if "uptime" in telem else (existing.uptime if existing else None),
                clock=str(telem["clock"]) if "clock" in telem else (existing.clock if existing else None),
            ),
        )

    def record_error(self, category: str) -> None:
        """Incrementa el contador de errores por categoría."""
        cat = category.upper().strip()
        if cat in self.error_categories:
            self.error_categories[cat] += 1
        else:
            self.error_categories[cat] = 1

    def record_neighbors(self, public_key: str, neighbors: list[str]) -> None:
        """Registra la lista de vecinos/clientes conectados a un repetidor."""
        norm_key = public_key.strip().lower()
        clean_neighbors = [n.strip().lower() for n in neighbors if n.strip()]
        existing = self._nodes_by_key.get(norm_key)
        if existing:
            self.add_or_update(
                norm_key,
                NodeContactUpdate(
                    name=existing.name,
                    alias=existing.alias,
                    neighbors=clean_neighbors,
                    connected_clients_count=len(clean_neighbors),
                ),
            )

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


    def find_by_name(self, name: str) -> NodeContactInfo | None:
        """Busca un nodo registrado por su nombre o alias de forma insensible a mayúsculas."""
        if not name:
            return None
        n_clean = name.strip().lower()
        if n_clean in self._nodes_by_name:
            cand_key = self._nodes_by_name[n_clean]
            res = self._nodes_by_key.get(cand_key)
            if res:
                return res
        for contact in self._nodes_by_key.values():
            c_name = (contact.name or "").strip().lower()
            c_alias = (contact.alias or "").strip().lower()
            if c_name == n_clean or c_alias == n_clean:
                return contact
        return None

    def get_contact(self, query: str) -> NodeContactInfo | None:

        """Obtiene la información del contacto buscando por clave, prefijo o alias."""
        return self.get_by_key_or_prefix(query)

    def resolve_name(self, query: str) -> str:
        """Resuelve el nombre amigable de un nodo o devuelve el identificador original."""
        contact = self.get_by_key_or_prefix(query)
        if contact:
            return contact.alias or contact.name
        return query

    def resolve_display_name(self, key_or_prefix: str) -> str:
        """Resuelve el nombre de display de un nodo dado su key completa o prefijo de 8 chars.
        Single Source of Truth para resolución de nombres en todo el bridge.
        Retorna alias si existe, nombre si no, o el prefijo como fallback.
        """
        prefix = key_or_prefix[:8] if len(key_or_prefix) >= 8 else key_or_prefix
        node = self.get_by_key_or_prefix(key_or_prefix)
        if node:
            return node.alias or node.name or prefix
        return prefix

    def list_nodes(self) -> list[dict[str, Any]]:
        """Retorna la lista de todos los nodos registrados en formato serializable."""
        return [
            c.to_dict()
            for c in self._nodes_by_key.values()
            if is_valid_node_key(c.public_key) and not c.name.startswith("Node_unknow")
        ]

    def get_analytics_summary(self) -> dict[str, Any]:
        """Calcula el resumen analítico avanzado (Top Nodos, Top Clientes, Top Errores)."""
        nodes_list = [c.to_dict() for c in self._nodes_by_key.values()]

        # 1. Top Nodos por Tráfico (RX + TX)
        top_traffic = heapq.nlargest(10, nodes_list, key=lambda n: int(str(n.get("total_packets", 0))))

        # 2. Top Nodos por Calidad de Señal (SNR / RSSI) - Solo nodos con mediciones reales
        measured_nodes = [n for n in nodes_list if n.get("last_snr") is not None]
        top_best_signal = heapq.nlargest(5, measured_nodes, key=lambda n: float(n.get("last_snr", 0.0)))
        top_worst_signal = heapq.nsmallest(5, measured_nodes, key=lambda n: float(n.get("last_snr", 0.0)))

        # 3. Top Clientes Conectados por Repetidor
        top_repeaters = heapq.nlargest(5, nodes_list, key=lambda n: int(str(n.get("connected_clients_count", 0))))

        # 4. Top Errores
        error_items: list[dict[str, Any]] = [
            {"category": k, "count": v} for k, v in self.error_categories.items()
        ]
        sorted_errors = sorted(
            error_items,
            key=lambda e: int(str(e["count"])),
            reverse=True,
        )

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

    def save_to_file(self, filepath: str | Path | None = None) -> bool:
        """Guarda la libreta de contactos y estado de nodos en un archivo JSON."""
        target_path = Path(filepath or os.getenv("NODE_REGISTRY_STORAGE_PATH", os.path.join("data", "node_registry.json")))
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "local_pubkey": self._local_pubkey,
                "saved_at": time.time(),
                "nodes": [c.to_dict() for c in self._nodes_by_key.values()],
                "error_categories": self.error_categories,
            }
            tmp_path = target_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(target_path)
            logging.debug(f"NodeRegistry guardado exitosamente en {target_path} ({len(self._nodes_by_key)} nodos)")
            return True
        except Exception as e:
            logging.warning(f"Error guardando NodeRegistry en {target_path}: {e}")
            return False

    def load_from_file(self, filepath: str | Path | None = None) -> int:
        """Carga la libreta de contactos y estado de nodos desde un archivo JSON."""
        target_path = Path(filepath or os.getenv("NODE_REGISTRY_STORAGE_PATH", os.path.join("data", "node_registry.json")))
        if not target_path.is_file():
            return 0
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded_count = 0
            raw_nodes = data.get("nodes", [])
            for nd in raw_nodes:
                pk = nd.get("public_key")
                if not pk or not is_valid_node_key(pk):
                    continue
                # Asegurar que neighbors sea una tupla
                raw_neighbors = nd.get("neighbors", ())
                neighbors_tuple = tuple(raw_neighbors) if isinstance(raw_neighbors, (list, tuple)) else ()
                
                # Construir campos de NodeContactInfo
                contact = NodeContactInfo(
                    public_key=str(pk).strip().lower(),
                    name=str(nd.get("name", "")),
                    alias=str(nd.get("alias", "")),
                    role=str(nd.get("role", "CLIENT")),
                    hops=nd.get("hops"),
                    last_rssi=nd.get("last_rssi"),
                    last_snr=nd.get("last_snr"),
                    battery_pct=nd.get("battery_pct"),
                    last_seen=float(nd.get("last_seen", 0.0)),
                    rx_packets=int(nd.get("rx_packets", 0)),
                    tx_packets=int(nd.get("tx_packets", 0)),
                    error_count=int(nd.get("error_count", 0)),
                    connected_clients_count=int(nd.get("connected_clients_count", 0)),
                    neighbors=neighbors_tuple,
                    temperature_c=nd.get("temperature_c"),
                    humidity_pct=nd.get("humidity_pct"),
                    pressure_hpa=nd.get("pressure_hpa"),
                    voltage_v=nd.get("voltage_v"),
                    solar_v=nd.get("solar_v"),
                    latitude=nd.get("latitude"),
                    longitude=nd.get("longitude"),
                    altitude_m=nd.get("altitude_m"),
                    uptime=nd.get("uptime"),
                    clock=nd.get("clock"),
                    airtime_ms=nd.get("airtime_ms"),
                    noise_floor_dbm=nd.get("noise_floor_dbm"),
                    packets_sent=nd.get("packets_sent"),
                    packets_recv=nd.get("packets_recv"),
                    duplicate_packets=nd.get("duplicate_packets"),
                    packet_errors=nd.get("packet_errors"),
                    queue_len=nd.get("queue_len"),
                    owner_name=nd.get("owner_name"),
                    owner_info=nd.get("owner_info"),
                    firmware_version=nd.get("firmware_version"),
                    hardware_board=nd.get("hardware_board"),
                    advert_interval=nd.get("advert_interval"),
                    repeat_enabled=nd.get("repeat_enabled"),
                    tx_power=nd.get("tx_power"),
                    frequency=nd.get("frequency"),
                    spreading_factor=nd.get("spreading_factor"),
                    bandwidth=nd.get("bandwidth"),
                    coding_rate=nd.get("coding_rate"),
                    fixed_position=nd.get("fixed_position"),
                    is_local=bool(nd.get("is_local", False)),
                    auto_discovered=bool(nd.get("auto_discovered", False)),
                    discovery_time=float(nd.get("discovery_time", 0.0)),
                    verified_identity=bool(nd.get("verified_identity", False)),
                    is_favorite=bool(nd.get("is_favorite", False)),
                    lqi_score=float(nd.get("lqi_score", 0.0)),
                    lqi_status=str(nd.get("lqi_status", "UNKNOWN")),
                    best_route=str(nd.get("best_route", "DIRECT")),
                )
                self._nodes_by_key[contact.public_key] = contact
                if contact.name:
                    self._nodes_by_name[contact.name.lower()] = contact.public_key
                if contact.alias:
                    self._nodes_by_name[contact.alias.lower()] = contact.public_key
                loaded_count += 1

            if "local_pubkey" in data and data["local_pubkey"]:
                self._local_pubkey = data["local_pubkey"]
            if "error_categories" in data and isinstance(data["error_categories"], dict):
                self.error_categories.update(data["error_categories"])

            logging.info(f"NodeRegistry cargado exitosamente desde {target_path} ({loaded_count} nodos)")
            return loaded_count
        except Exception as e:
            logging.warning(f"Error cargando NodeRegistry desde {target_path}: {e}")
            return 0

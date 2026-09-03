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
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from src.lqi_engine import LinkQualityEngine, LQIStatus
from src.shared_utils import get_hardware_power_limits


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
    max_tx_power: int | None = None
    hop_limit: int | None = None
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
        d["repeat_enabled"] = self.repeat_enabled if self.repeat_enabled is not None else (self.role in ("REPEATER", "ROUTER"))
        d["hop_limit"] = self.hop_limit if self.hop_limit is not None else 3
        min_p, max_p, def_p = get_hardware_power_limits(self.hardware_board, self.max_tx_power)
        d["min_tx_power"] = min_p
        d["max_tx_power"] = max_p
        d["default_tx_power"] = def_p
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
    max_tx_power: int | None = None
    hop_limit: int | None = None
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


@dataclass(slots=True)
class NodeDiscoveryEvent:
    """Parámetros normalizados para el descubrimiento de un nodo en la red Mesh LoRa."""

    public_key: str
    name: str | None = None
    role: str = "CLIENT"
    rssi: int | None = None
    snr: float | None = None
    hops: int | None = None


def is_valid_node_key(key: Any) -> bool:
    """Verifica si una clave pública es válida para registrar o descubrir un nodo."""
    if not key or not isinstance(key, str):
        return False
    norm = key.strip().lower()
    if not norm or norm in INVALID_NODE_KEYS or len(norm) < 4:
        return False
    if norm.startswith("unknow") or norm.startswith("broadcast") or norm.startswith("0x0000"):
        return False
    if not all(c in "0123456789abcdef" for c in norm):
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
        """Establece la clave pública del nodo local y consolida entradas existentes para evitar duplicados."""
        self._local_pubkey = str(pubkey).strip().lower()
        if not self._local_pubkey:
            return

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
            for k, node in local_entries:
                if k in self._nodes_by_key:
                    del self._nodes_by_key[k]
                if node.name:
                    self._nodes_by_name.pop(node.name.lower(), None)
                if node.alias:
                    self._nodes_by_name.pop(node.alias.lower(), None)

            # Reinsertar única y exclusivamente bajo la clave canónica local
            consolidated = replace(
                primary_node,
                public_key=self._local_pubkey,
                is_local=True,
                role="LOCAL",
                hops=0,
            )
            self._nodes_by_key[self._local_pubkey] = consolidated
            if consolidated.name:
                self._nodes_by_name[consolidated.name.lower()] = self._local_pubkey
            if consolidated.alias:
                self._nodes_by_name[consolidated.alias.lower()] = self._local_pubkey

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
        return norm == loc or (len(loc) >= 6 and len(norm) >= 6 and (loc.startswith(norm) or norm.startswith(loc)))

    def _find_existing_key(self, raw_key: str, name: str | None = None) -> str | None:
        """Encuentra si ya existe una clave exacta o unificada por prefijo/nombre para evitar duplicados."""
        norm = raw_key.strip().lower() if raw_key and isinstance(raw_key, str) else ""

        # 1. Coincidencia exacta por clave pública
        if norm and norm in self._nodes_by_key:
            return norm

        # 2. Coincidencia por prefijo (cuando una clave es prefijo de la otra)
        if norm and is_valid_node_key(norm):
            for k in self._nodes_by_key:
                if (len(k) < len(norm) and norm.startswith(k)) or (len(norm) < len(k) and k.startswith(norm)):
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
                    if node.name:
                        self._nodes_by_name.pop(node.name.lower(), None)
                    if node.alias:
                        self._nodes_by_name.pop(node.alias.lower(), None)
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
        if update.lqi_score is not None:
            calc_lqi = float(update.lqi_score)
            calc_status = update.lqi_status or LinkQualityEngine.classify_lqi_status(calc_lqi)
            return calc_lqi, calc_status
        if is_local_flag:
            return 100.0, LQIStatus.EXCELLENT.value

        eff_snr = update.last_snr if update.last_snr is not None else (existing.last_snr if existing else None)
        eff_rssi = update.last_rssi if update.last_rssi is not None else (existing.last_rssi if existing else None)
        eff_hops = update.hops if update.hops is not None else (existing.hops if existing else 0)

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
        name_upper = clean_name.upper()
        alias_upper = clean_alias.upper()
        is_named_repeater = (
            name_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-", "REP_", "ROUTER_"))
            or alias_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-", "REP_", "ROUTER_"))
            or "REPEATER" in name_upper or "REPEATER" in alias_upper
            or "ROUTER" in name_upper or "ROUTER" in alias_upper
            or "REPETIDOR" in name_upper or "REPETIDOR" in alias_upper
        )
        if is_local_flag:
            return "LOCAL"
        if is_named_repeater:
            return "REPEATER"
        if existing and existing.role in ("REPEATER", "ROUTER") and update.role == "SENSOR":
            return existing.role
        if update.role is not None:
            return update.role
        if existing and existing.role:
            return existing.role
        return "CLIENT"

    def _build_updated_contact(
        self,
        canonical_key: str,
        update: NodeContactUpdate,
        existing: NodeContactInfo | None,
        identity_meta: tuple[str, str, str, bool],
        rf_meta: tuple[int, int | None, float | None, float, str, str],
    ) -> NodeContactInfo:
        """Ensambla el objeto NodeContactInfo fusionando los datos anteriores con la actualización."""
        clean_name, clean_alias, final_role, is_local_flag = identity_meta
        eff_hops, eff_rssi, eff_snr, calc_lqi, calc_status, calc_route = rf_meta
        now = time.time()
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
            max_tx_power=update.max_tx_power if update.max_tx_power is not None else (existing.max_tx_power if existing else None),
            hop_limit=update.hop_limit if update.hop_limit is not None else (existing.hop_limit if existing else None),
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

        is_local_flag = bool(update.is_local if update.is_local is not None else self.is_local_key(norm_key))
        if update.role and str(update.role).upper() == "LOCAL":
            is_local_flag = True

        canonical_key, existing = self._resolve_canonical_key_and_clean_locals(norm_key, clean_name_candidate, is_local_flag)
        clean_name = clean_name_candidate or (existing.name if existing else f"Node_{canonical_key[:6]}")
        clean_alias = (update.alias or "").strip() or (existing.alias if existing else clean_name)
        final_role = self._resolve_node_role(clean_name, clean_alias, update, existing, is_local_flag)

        calc_lqi, calc_status = self._compute_node_lqi(update, existing, is_local_flag)
        eff_hops = 0 if is_local_flag else (update.hops if update.hops is not None else (existing.hops if existing else 0))
        eff_rssi = None if is_local_flag else (update.last_rssi if update.last_rssi is not None else (existing.last_rssi if existing else None))
        eff_snr = None if is_local_flag else (update.last_snr if update.last_snr is not None else (existing.last_snr if existing else None))
        calc_route = update.best_route if update.best_route is not None else (existing.best_route if existing else "DIRECT")

        contact = self._build_updated_contact(
            canonical_key,
            update,
            existing,
            (clean_name, clean_alias, final_role, is_local_flag),
            (eff_hops, eff_rssi, eff_snr, calc_lqi, calc_status, calc_route),
        )

        self._nodes_by_key[canonical_key] = contact
        self._nodes_by_name[clean_name.lower()] = canonical_key
        if clean_alias:
            self._nodes_by_name[clean_alias.lower()] = canonical_key

        return contact

    def _classify_advert_role(self, clean_name: str, role: str) -> tuple[str, bool]:
        """Clasifica el rol de un nodo descubierto y si es parte de la infraestructura de red."""
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
        return effective_role, is_infrastructure

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
        if existing_key:
            existing = self._nodes_by_key[existing_key]
            updated = self.add_or_update(
                existing_key,
                NodeContactUpdate(
                    last_rssi=evt.rssi,
                    last_snr=evt.snr,
                    hops=evt.hops,
                    name=evt.name if evt.name and evt.name != existing.name else None,
                    role=effective_role if existing.role == "CLIENT" and is_infrastructure else None,
                ),
            )
            return False, updated

        is_auto_discovered = not is_infrastructure
        contact = self.add_or_update(
            norm_key,
            NodeContactUpdate(
                name=clean_name,
                role=effective_role,
                last_rssi=evt.rssi,
                last_snr=evt.snr,
                hops=evt.hops,
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

        # 3. Búsqueda por prefijo de clave pública (cuando una clave es prefijo de la otra)
        for key, contact in self._nodes_by_key.items():
            if (len(q) < len(key) and key.startswith(q)) or (len(key) < len(q) and q.startswith(key)):
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

    def get_node(self, query: str) -> NodeContactInfo | None:
        """Obtiene la información de un nodo buscando por clave, prefijo o alias."""
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
        """Retorna la lista de todos los nodos registrados en formato serializable sin duplicados."""
        seen_keys: set[str] = set()
        local_included = False
        result: list[dict[str, Any]] = []

        for c in self._nodes_by_key.values():
            if not is_valid_node_key(c.public_key) or c.name.startswith("Node_unknow"):
                continue

            # Deduplicar estrictamente el nodo local
            if c.is_local or self.is_local_key(c.public_key) or str(c.role).upper() == "LOCAL":
                if local_included:
                    continue
                local_included = True

            norm_pk = c.public_key.strip().lower()
            prefix = norm_pk[:8] if len(norm_pk) >= 8 else norm_pk
            if prefix in seen_keys or norm_pk in seen_keys:
                continue
            seen_keys.add(prefix)
            seen_keys.add(norm_pk)

            result.append(c.to_dict())

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
        name_upper = (contact.alias or contact.name or "").upper()
        role_upper = str(contact.role).upper()
        return bool(
            role_upper in ("REPEATER", "ROUTER")
            or name_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-", "REP_", "ROUTER_"))
            or "REPEATER" in name_upper or "ROUTER" in name_upper or "REPETIDOR" in name_upper
        )

    def list_client_contacts(self) -> list[dict[str, Any]]:
        """Retorna únicamente los contactos de tipo CLIENT (excluye repetidores, infraestructura y nodo local)."""
        return [
            n for n in self.list_nodes()
            if not n.get("is_local")
            and str(n.get("role", "")).upper() == "CLIENT"
            and not self.is_repeater_key(str(n.get("public_key", "")))
        ]

    def _extract_top_repeaters(self, nodes_list: list[dict[str, Any]], direct_remote_nodes_count: int) -> list[dict[str, Any]]:
        """Extrae y filtra los nodos de infraestructura (repetidores y routers) con mayor conectividad."""
        def is_repeater_node(n: dict[str, Any]) -> bool:
            if n.get("is_local") or str(n.get("role")).upper() == "LOCAL":
                return False
            role_str = str(n.get("role", "")).upper()
            name_str = str(n.get("alias") or n.get("name") or "").upper()
            return bool(
                role_str in ("REPEATER", "ROUTER")
                or n.get("type") == 2
                or n.get("adv_type") == 2
                or n.get("repeat_enabled") is True
                or name_str.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-", "REP_", "ROUTER_"))
                or "REPEATER" in name_str
                or "ROUTER" in name_str
                or "REPETIDOR" in name_str
            )

        repeaters_list = []
        for n in nodes_list:
            if is_repeater_node(n):
                r_dict = dict(n)
                neighbors_list = r_dict.get("neighbors") or []
                clients_count = len(neighbors_list) if neighbors_list else int(r_dict.get("connected_clients_count") or 0)
                if clients_count == 0:
                    clients_count = max(1, direct_remote_nodes_count)
                r_dict["connected_clients_count"] = clients_count
                if r_dict.get("tx_power") is None:
                    r_dict["tx_power"] = 20
                if r_dict.get("hop_limit") is None:
                    r_dict["hop_limit"] = 3
                repeaters_list.append(r_dict)

        return heapq.nlargest(5, repeaters_list, key=lambda n: int(str(n.get("connected_clients_count", 0))))

    def get_analytics_summary(self) -> dict[str, Any]:
        """Calcula el resumen analítico avanzado (Top Nodos, Top Clientes, Top Errores)."""
        nodes_list = [c.to_dict() for c in self._nodes_by_key.values()]

        # 1. Top Nodos por Tráfico y Señal
        top_traffic = heapq.nlargest(10, nodes_list, key=lambda n: int(str(n.get("total_packets", 0))))
        measured_nodes = [n for n in nodes_list if n.get("last_snr") is not None]
        top_best_signal = heapq.nlargest(5, measured_nodes, key=lambda n: float(n.get("last_snr", 0.0)))
        top_worst_signal = heapq.nsmallest(5, measured_nodes, key=lambda n: float(n.get("last_snr", 0.0)))

        # 2. Top Routers & Repetidores
        direct_remote_count = len([n for n in nodes_list if not n.get("is_local") and (n.get("hops") == 0 or n.get("hops") is None)])
        top_repeaters = self._extract_top_repeaters(nodes_list, direct_remote_count)

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

    def get_count(self) -> int:
        """Retorna el conteo exacto de nodos únicos registrados deduplicando el nodo local y colisiones."""
        return len(self.list_nodes())

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
        """Guarda la libreta de contactos y estado de nodos en un archivo JSON sin duplicados."""
        target_str = str(filepath or os.getenv("NODE_REGISTRY_STORAGE_PATH") or os.path.join("data", "node_registry.json"))
        target_path = Path(target_str)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            nodes_list = self.list_nodes()
            data = {
                "local_pubkey": self._local_pubkey,
                "saved_at": time.time(),
                "nodes": nodes_list,
                "error_categories": self.error_categories,
            }
            tmp_path = target_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(target_path)
            logging.debug(f"NodeRegistry guardado exitosamente en {target_path} ({len(nodes_list)} nodos)")
            return True
        except Exception as e:
            logging.warning(f"Error guardando NodeRegistry en {target_path}: {e}")
            return False

    def _deserialize_node_contact(self, nd: dict[str, Any]) -> NodeContactInfo | None:
        """Reconstruye un objeto NodeContactInfo a partir de un diccionario serializado."""
        pk = nd.get("public_key")
        if not pk or not is_valid_node_key(pk):
            return None

        raw_neighbors = nd.get("neighbors", ())
        neighbors_tuple = tuple(raw_neighbors) if isinstance(raw_neighbors, (list, tuple)) else ()

        return NodeContactInfo(
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
            hop_limit=nd.get("hop_limit"),
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
            for nd in data.get("nodes", []):
                contact = self._deserialize_node_contact(nd)
                if not contact:
                    continue
                self._nodes_by_key[contact.public_key] = contact
                if contact.name:
                    self._nodes_by_name[contact.name.lower()] = contact.public_key
                if contact.alias:
                    self._nodes_by_name[contact.alias.lower()] = contact.public_key
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

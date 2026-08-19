"""
Node Registry & Contact Directory for MeshCore Bridge.
Mantiene un registro de nodos activos, libretas de contactos, alias, telemetría y métricas RF
en memoria con soporte de búsqueda O(1), estadísticas de tráfico y análisis topológico.
"""

from __future__ import annotations

import heapq
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any


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
    hops: int = 0
    last_rssi: int = -80
    last_snr: float = 10.0
    battery_pct: int | None = None
    last_seen: float = 0.0
    rx_packets: int = 0
    tx_packets: int = 0
    error_count: int = 0
    connected_clients_count: int = 0
    neighbors: list[str] = field(default_factory=list)
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
    auto_discovered: bool = False
    discovery_time: float = 0.0
    verified_identity: bool = False
    is_favorite: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key_prefix"] = self.public_key[:8] if len(self.public_key) >= 8 else self.public_key
        d["total_packets"] = self.rx_packets + self.tx_packets
        d["error_rate_pct"] = round((self.error_count / (d["total_packets"] or 1)) * 100, 1)
        return d


@dataclass(slots=True)
class NodeContactUpdate:
    """Objeto de parámetro para add_or_update."""
    name: str | None = None
    alias: str | None = None
    role: str | None = None
    auto_discovered: bool | None = None
    discovery_time: float | None = None
    verified_identity: bool | None = None
    is_favorite: bool | None = None
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


@dataclass(slots=True)
class PacketRecord:
    """Objeto de parámetro para record_packet: metadatos de un evento de paquete RX/TX."""
    public_key: str
    is_rx: bool
    is_error: bool = False
    rssi: int | None = None
    snr: float | None = None
    telemetry: dict[str, Any] | None = None


class NodeRegistry:
    """Directorio en memoria para contactos y resolución de nombres de la red MeshCore."""

    def __init__(self) -> None:
        self._nodes_by_key: dict[str, NodeContactInfo] = {}
        self._nodes_by_name: dict[str, str] = {}  # lower(name) -> public_key
        self.error_categories: dict[str, int] = {
            "SERIAL_TIMEOUT": 0,
            "TX_BUFFER_OVERFLOW": 0,
            "CRC_MISMATCH": 0,
            "RADIO_BUSY": 0,
            "ROUTE_UNREACHABLE": 0,
            "MQTT_DISCONNECT": 0,
        }
        self.last_sync_timestamp: float = 0.0

    def _find_existing_key(self, raw_key: str, name: str | None = None) -> str | None:
        """Encuentra si ya existe una clave exacta o unificada por prefijo/nombre para evitar duplicados."""
        norm = raw_key.strip().lower()
        if not norm:
            return None

        # 1. Coincidencia exacta
        if norm in self._nodes_by_key:
            return norm

        # 2. Coincidencia por prefijo (>= 8 caracteres comunes)
        for k in self._nodes_by_key:
            if (len(k) >= 8 and len(norm) >= 8 and (k.startswith(norm) or norm.startswith(k))) or \
               (len(norm) == 12 and k.startswith(norm[:12])) or \
               (len(k) == 12 and norm.startswith(k[:12])):
                return k

        # 3. Coincidencia por nombre exacto si el prefijo de 6 caracteres coincide
        if name:
            n_clean = name.strip().lower()
            if n_clean in self._nodes_by_name:
                cand_key = self._nodes_by_name[n_clean]
                if cand_key.startswith(norm[:6]) or norm.startswith(cand_key[:6]):
                    return cand_key

        return None

    def add_or_update(self, public_key: str, update: NodeContactUpdate) -> NodeContactInfo:
        """Añade o actualiza la información de un nodo preservando métricas acumuladas y deduplicando prefijos."""
        norm_key = public_key.strip().lower()
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

        contact = NodeContactInfo(
            public_key=canonical_key,
            name=clean_name,
            alias=clean_alias,
            role=update.role if update.role is not None else (existing.role if existing else "CLIENT"),
            hops=update.hops if update.hops is not None and (update.hops != 0 or not existing) else (existing.hops if existing else 0),
            last_rssi=update.last_rssi if update.last_rssi is not None and (update.last_rssi != -80 or not existing) else (existing.last_rssi if existing else -80),
            last_snr=update.last_snr if update.last_snr is not None and (update.last_snr != 10.0 or not existing) else (existing.last_snr if existing else 10.0),
            battery_pct=update.battery_pct if update.battery_pct is not None or not existing else existing.battery_pct,
            last_seen=now,
            rx_packets=update.rx_packets if update.rx_packets is not None else (existing.rx_packets if existing else 0),
            tx_packets=update.tx_packets if update.tx_packets is not None else (existing.tx_packets if existing else 0),
            error_count=update.error_count if update.error_count is not None else (existing.error_count if existing else 0),
            connected_clients_count=update.connected_clients_count if update.connected_clients_count is not None else (existing.connected_clients_count if existing else 0),
            neighbors=update.neighbors if update.neighbors is not None else (existing.neighbors if existing else []),
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

    def discover_node(
        self,
        public_key: str,
        name: str | None = None,
        role: str = "CLIENT",
        rssi: int = -80,
        snr: float = 10.0,
        hops: int = 0,
    ) -> tuple[bool, NodeContactInfo]:
        """
        Descubre un nuevo nodo en el aire si no existía previamente.
        Retorna (is_new, contact_info).
        """
        norm_key = public_key.strip().lower()
        if not norm_key:
            raise ValueError("public_key no puede estar vacía")

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
                ),
            )
            return False, updated

        clean_name = (name or f"Node_{norm_key[:6]}").strip()
        contact = self.add_or_update(
            norm_key,
            NodeContactUpdate(
                name=clean_name,
                role=role,
                last_rssi=rssi,
                last_snr=snr,
                hops=hops,
                auto_discovered=True,
                discovery_time=time.time(),
                verified_identity=len(norm_key) >= 12,
            ),
        )
        return True, contact

    def list_discovered(self, pending_only: bool = False) -> list[dict[str, Any]]:
        """Lista los nodos descubiertos automáticamente en la red."""
        results = []
        for c in self._nodes_by_key.values():
            if c.auto_discovered:
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
        if not norm_key:
            return

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
        lat_raw = telem.get("lat", telem.get("latitude"))
        if lat_raw is None and isinstance(gps, dict):
            lat_raw = gps.get("latitude", gps.get("lat"))
        lon_raw = telem.get("lon", telem.get("longitude"))
        if lon_raw is None and isinstance(gps, dict):
            lon_raw = gps.get("longitude", gps.get("lon"))
        alt_raw = telem.get("alt", telem.get("altitude"))
        if alt_raw is None and isinstance(gps, dict):
            alt_raw = gps.get("altitude", gps.get("alt"))

        self.add_or_update(
            target_key,
            NodeContactUpdate(
                name=existing.name if existing else f"Node_{target_key[:6]}",
                alias=existing.alias if existing else "",
                last_rssi=event.rssi if event.rssi is not None else (existing.last_rssi if existing else -80),
                last_snr=event.snr if event.snr is not None else (existing.last_snr if existing else 10.0),
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

    def resolve_name(self, query: str) -> str:
        """Resuelve el nombre amigable de un nodo o devuelve el identificador original."""
        contact = self.get_by_key_or_prefix(query)
        if contact:
            return contact.alias or contact.name
        return query

    def list_nodes(self) -> list[dict[str, Any]]:
        """Retorna la lista de todos los nodos registrados en formato serializable."""
        return [c.to_dict() for c in self._nodes_by_key.values()]

    def get_analytics_summary(self) -> dict[str, Any]:
        """Calcula el resumen analítico avanzado (Top Nodos, Top Clientes, Top Errores)."""
        nodes_list = [c.to_dict() for c in self._nodes_by_key.values()]

        # 1. Top Nodos por Tráfico (RX + TX)
        top_traffic = heapq.nlargest(10, nodes_list, key=lambda n: int(str(n.get("total_packets", 0))))

        # 2. Top Nodos por Calidad de Señal (SNR / RSSI)
        top_best_signal = heapq.nlargest(5, nodes_list, key=lambda n: float(str(n.get("last_snr", 0.0))))
        top_worst_signal = heapq.nsmallest(5, nodes_list, key=lambda n: float(str(n.get("last_snr", 0.0))))

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

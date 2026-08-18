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


@dataclass(frozen=True, slots=True)
class NodeContactInfo:
    """Información consolidada de un nodo o contacto en la malla."""
    public_key: str
    name: str
    alias: str
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
    latitude: float | None = None
    longitude: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key_prefix"] = self.public_key[:8] if len(self.public_key) >= 8 else self.public_key
        d["total_packets"] = self.rx_packets + self.tx_packets
        d["error_rate_pct"] = round((self.error_count / (d["total_packets"] or 1)) * 100, 1)
        return d


@dataclass(slots=True)
class NodeContactUpdate:
    """Objeto de parámetro para add_or_update: evita firmas con 19 argumentos."""
    name: str | None = None
    alias: str | None = None
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
    latitude: float | None = None
    longitude: float | None = None


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

    def add_or_update(self, public_key: str, update: NodeContactUpdate) -> NodeContactInfo:
        """Añade o actualiza la información de un nodo preservando métricas acumuladas."""
        norm_key = public_key.strip().lower()
        existing = self._nodes_by_key.get(norm_key)

        clean_name = (update.name or "").strip() or (existing.name if existing else f"Node_{norm_key[:6]}")
        clean_alias = (update.alias or "").strip() or (existing.alias if existing else clean_name)
        now = time.time()

        contact = NodeContactInfo(
            public_key=norm_key,
            name=clean_name,
            alias=clean_alias,
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
            latitude=update.latitude if update.latitude is not None else (existing.latitude if existing else None),
            longitude=update.longitude if update.longitude is not None else (existing.longitude if existing else None),
        )

        self._nodes_by_key[norm_key] = contact
        self._nodes_by_name[clean_name.lower()] = norm_key
        if clean_alias:
            self._nodes_by_name[clean_alias.lower()] = norm_key

        return contact

    def record_packet(self, event: PacketRecord) -> None:
        """Registra un evento de paquete para actualizar contadores de tráfico y salud."""
        norm_key = event.public_key.strip().lower()
        if not norm_key:
            return

        existing = self._nodes_by_key.get(norm_key)
        curr_rx = (existing.rx_packets if existing else 0) + (1 if event.is_rx else 0)
        curr_tx = (existing.tx_packets if existing else 0) + (0 if event.is_rx else 1)
        curr_err = (existing.error_count if existing else 0) + (1 if event.is_error else 0)

        telem = event.telemetry or {}
        temp = telem.get("temperature_c", telem.get("temperature"))
        hum = telem.get("humidity_pct", telem.get("humidity"))
        press = telem.get("pressure_hpa", telem.get("pressure"))
        volt = telem.get("voltage_v", telem.get("voltage"))
        batt = telem.get("battery_pct", telem.get("battery"))
        gps = telem.get("gps", {})

        self.add_or_update(
            norm_key,
            NodeContactUpdate(
                name=existing.name if existing else f"Node_{norm_key[:6]}",
                alias=existing.alias if existing else "",
                last_rssi=event.rssi if event.rssi is not None else (existing.last_rssi if existing else -80),
                last_snr=event.snr if event.snr is not None else (existing.last_snr if existing else 10.0),
                battery_pct=int(batt) if batt is not None else (existing.battery_pct if existing else None),
                rx_packets=curr_rx,
                tx_packets=curr_tx,
                error_count=curr_err,
                temperature_c=float(temp) if temp is not None else None,
                humidity_pct=float(hum) if hum is not None else None,
                pressure_hpa=float(press) if press is not None else None,
                voltage_v=float(volt) if volt is not None else None,
                latitude=float(gps["latitude"]) if isinstance(gps, dict) and "latitude" in gps else None,
                longitude=float(gps["longitude"]) if isinstance(gps, dict) and "longitude" in gps else None,
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

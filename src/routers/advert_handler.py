"""
Advert and node discovery strategy handler for RxEventRouter.
Handles node advertisements and contact book synchronization.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.contact_manager import NodeContactUpdate, is_valid_node_key
from src.routers.base import BaseRxHandler, RxMeta


def _get_coord(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for k in keys:
        if k in data and data[k] is not None:
            try:
                val = float(data[k])
                if -180.0 <= val <= 180.0 and val != 0.0:
                    return val
            except (ValueError, TypeError):
                pass
    return None


def _safe_int(val: Any) -> int | None:
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None


class AdvertHandler(BaseRxHandler):
    """Manejador especializado para anuncios de presencia y descubrimiento de nodos."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        p_type_upper = str(payload.get("type", "")).upper()
        return (
            "CONTACT" in meta.ev_upper
            or "ADVERT" in meta.ev_upper
            or "ADVERTISEMENT" in meta.ev_upper
            or p_type_upper in ("ADVERT", "ADVERTISEMENT", "CONTACT")
            or payload.get("event_type") in ("advert", "node_advert", "node_discovered", "advertisement")
            or meta.ev_upper in ("NEW_CONTACT", "CONTACT_UPDATE", "NODE_DISCOVERED")
        )

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        router_ctx = getattr(ctx, "_ctx", ctx)

        # Caso Descubrimiento / Importación de Contacto múltiple o individual
        c_items: list[dict[str, Any]] = []
        payload_obj = getattr(raw_event, "payload", getattr(raw_event, "data", payload))
        if isinstance(payload_obj, list):
            c_items = [x for x in payload_obj if isinstance(x, dict)]
        elif isinstance(payload_obj, dict):
            if "contacts" in payload_obj and isinstance(payload_obj["contacts"], list):
                c_items = [x for x in payload_obj["contacts"] if isinstance(x, dict)]
            else:
                c_items = [payload_obj]

        for c_item in c_items:
            c_pk = str(c_item.get("public_key", c_item.get("key", c_item.get("pubkey", "")))).strip().lower()
            if not c_pk or not is_valid_node_key(c_pk):
                continue

            c_name = str(c_item.get("adv_name", c_item.get("name", c_item.get("alias", f"Node_{c_pk[:6]}")))).strip()
            c_raw_type = c_item.get("type", c_item.get("adv_type", 1))
            c_name_upper = c_name.upper()

            if c_raw_type == 2 or c_name_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-")) or "REPEATER" in c_name_upper or "ROUTER" in c_name_upper:
                c_role = "REPEATER"
            elif c_raw_type == 3 or "ROOM" in c_name_upper or "BBS" in c_name_upper:
                c_role = "ROOM"
            elif c_raw_type == 4 or "SENSOR" in c_name_upper:
                c_role = "SENSOR"
            else:
                c_role = "CLIENT"

            c_lat = _get_coord(c_item, ("adv_lat", "lat", "latitude", "gps_lat"))
            c_lon = _get_coord(c_item, ("adv_lon", "lon", "longitude", "gps_lon"))
            c_bat = _safe_int(c_item.get("battery_pct", c_item.get("battery", c_item.get("batt"))))

            is_c_new, c_contact_info = router_ctx.node_registry.discover_node(
                public_key=c_pk,
                name=c_name,
                role=c_role,
                rssi=meta.effective_rssi,
                snr=meta.effective_snr,
                hops=meta.effective_hops,
            )
            router_ctx.node_registry.add_or_update(
                c_pk,
                NodeContactUpdate(
                    name=c_name,
                    alias=c_name,
                    role=c_role,
                    latitude=c_lat,
                    longitude=c_lon,
                    battery_pct=c_bat,
                    last_rssi=meta.effective_rssi,
                    last_snr=meta.effective_snr,
                    hops=meta.effective_hops,
                ),
            )

        if "event_type" not in payload:
            payload["event_type"] = "advert"

        ctx._handle_mesh_telemetry_msg(payload)
        return True

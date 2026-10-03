"""
Advert and node discovery strategy handler for RxEventRouter.
Handles node advertisements and contact book synchronization.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.contact_manager import NodeContactUpdate, NodeDiscoveryEvent, is_valid_node_key
from src.routers.base import BaseRxHandler, RxMeta
from src.shared_utils import classify_device_role, clean_coordinate_value, clean_numeric_value


def _get_coord(data: dict[str, Any], keys: tuple[str, ...], *, latitude: bool = False) -> float | None:
    for k in keys:
        if k in data and data[k] is not None:
            val = clean_coordinate_value(data[k], latitude=latitude)
            if val is not None:
                return val
    return None


def _safe_int(val: Any) -> int | None:
    number = clean_numeric_value(val)
    return int(number) if number is not None else None


def _safe_float(val: Any) -> float | None:
    number = clean_numeric_value(val)
    return float(number) if number is not None else None



class AdvertHandler(BaseRxHandler):
    """Manejador especializado para anuncios de presencia y descubrimiento de nodos."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        # Nunca interceptar mensajes de texto, chats ni tramas de datos
        if bool(meta.text) or "MSG" in meta.ev_upper or "MESSAGE" in meta.ev_upper or "DATA" in meta.ev_upper:
            return False

        p_type_upper = str(payload.get("type", "")).upper()
        if p_type_upper in ("CHAN", "CHANNEL", "DIRECT", "PRIV"):
            return False

        is_advert = (
            "ADVERT" in meta.ev_upper
            or "ADVERTISEMENT" in meta.ev_upper
            or p_type_upper in ("ADVERT", "ADVERTISEMENT")
            or payload.get("event_type") in ("advert", "node_advert", "node_discovered", "advertisement")
        )
        is_contact_sync = (
            "CONTACTS" in meta.ev_upper
            or "NEXT_CONTACT" in meta.ev_upper
            or "NEW_CONTACT" in meta.ev_upper
            or "CONTACT_UPDATE" in meta.ev_upper
            or "NODE_DISCOVERED" in meta.ev_upper
            or p_type_upper in ("CONTACT", "CONTACTS")
            or "contacts" in payload
            or (isinstance(payload, dict) and any(len(str(k)) >= 12 for k in payload.keys()) and all(isinstance(v, dict) for v in payload.values()))
        )
        return is_advert or is_contact_sync

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
            elif all(isinstance(v, dict) for v in payload_obj.values()) and payload_obj:
                c_items = list(payload_obj.values())
            else:
                c_items = [payload_obj]

        for c_item in c_items:
            c_pk = str(c_item.get("public_key", c_item.get("key", c_item.get("pubkey", "")))).strip().lower()
            if not c_pk or not is_valid_node_key(c_pk):
                continue

            c_name = str(c_item.get("adv_name", c_item.get("name", c_item.get("alias", f"Node_{c_pk[:6]}")))).strip()
            c_raw_type = c_item.get("type", c_item.get("adv_type", 1))
            c_role = classify_device_role(c_raw_type)

            c_lat = _get_coord(c_item, ("adv_lat", "lat", "latitude", "gps_lat"), latitude=True)
            c_lon = _get_coord(c_item, ("adv_lon", "lon", "longitude", "gps_lon"))
            if c_lat == 0 and c_lon in (0, None):
                c_lat = None
            if c_lon == 0 and c_lat is None:
                c_lon = None
            c_bat = _safe_int(c_item.get("battery_pct", c_item.get("battery", c_item.get("batt"))))

            is_snapshot_sync = any(k in meta.ev_upper for k in ("CONTACTS", "NEXT_CONTACT")) or bool(c_item.get("is_import"))
            now_ts = time.time()
            eff_last_seen = None if is_snapshot_sync else now_ts
            eff_heard_at = None if is_snapshot_sync else now_ts
            remote_advert_ts = _safe_float(c_item.get("last_advert"))

            pos_valid = bool(c_lat is not None and c_lon is not None and (c_lat != 0 or c_lon != 0 or c_item.get("fixed_position")))
            pos_src = "ADVERT_GPS" if pos_valid else None
            pos_updated = now_ts if (pos_valid and not is_snapshot_sync) else None

            is_c_new, _ = router_ctx.node_registry.discover_node(
                NodeDiscoveryEvent(
                    public_key=c_pk,
                    name=c_name,
                    role=c_role,
                    rssi=meta.effective_rssi,
                    snr=meta.effective_snr,
                    hops=meta.effective_hops,
                    last_seen=eff_last_seen,
                    last_advert_heard_at=eff_heard_at,
                    is_import=is_snapshot_sync,
                )
            )
            if is_c_new:
                logging.info(
                    f"[NODO-DESCUBIERTO] Nuevo nodo detectado en la malla: {c_name} ({c_pk[:8]}) | "
                    f"Rol: {c_role} | RSSI: {meta.effective_rssi} dBm, SNR: {meta.effective_snr} dB, Saltos: {meta.effective_hops}"
                )

            updated_c = router_ctx.node_registry.add_or_update(
                c_pk,
                NodeContactUpdate(
                    last_seen=eff_last_seen,
                    last_advert_heard_at=eff_heard_at,
                    last_advert=remote_advert_ts,
                    name=c_name,
                    alias=c_name,
                    role=c_role,
                    latitude=c_lat,
                    longitude=c_lon,
                    adv_lat=c_lat,
                    adv_lon=c_lon,
                    position_valid=pos_valid,
                    position_source=pos_src,
                    position_updated_at=pos_updated,
                    battery_pct=c_bat,
                    last_rssi=meta.effective_rssi,
                    last_snr=meta.effective_snr,
                    hops=meta.effective_hops,
                    flags=_safe_int(c_item.get("flags")),
                    out_path=c_item.get("out_path"),
                    out_path_len=_safe_int(c_item.get("out_path_len")),
                    out_path_hash_mode=c_item.get("out_path_hash_mode"),
                ),
            )

            # Emitir siempre el snapshot final actualizado
            if ctx and hasattr(ctx, "_spawn_broadcast_task"):
                ctx._spawn_broadcast_task({
                    "type": "contact_discovered" if is_c_new else "contact_updated",
                    "event_type": "contact_discovered" if is_c_new else "contact_updated",
                    "is_new": is_c_new,
                    "contact": updated_c.to_dict(),
                })

        if "event_type" not in payload:
            payload["event_type"] = "advert"

        ctx._handle_mesh_telemetry_msg(payload)
        return True

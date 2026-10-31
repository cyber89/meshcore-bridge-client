"""
TelemetryProcessor: Normalización, enriquecimiento, LQI y persistencia de telemetría de red.
Extraído de RxEventRouter para separar la lógica de telemetría, sensores y diagnóstico de la estación local.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.contact_manager import (
    NodeContactUpdate,
    is_valid_node_key,
)
from src.event_utils import extract_sender_from_payload
from src.integrations.mqtt.topics import MqttTopics
from src.lqi_engine import LinkQualityEngine
from src.protocol_types import normalize_tx_power
from src.sensor_decoder import (
    extract_telemetry_fields,
    format_telemetry_summary,
)
from src.shared_utils import (
    clean_coordinate_value,
    clean_numeric_value,
    sanitize_public_payload,
)

if TYPE_CHECKING:
    from src.rx_router import RxRouterContext


def get_coord(d: dict[str, Any], keys: tuple[str, ...], *, latitude: bool = False) -> float | None:
    """Extrae una coordenada geográfica finita y acotada; cero puede ser válido."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            value = clean_coordinate_value(d[k], latitude=latitude)
            if value is not None:
                return value
    for sub in ("gps", "position", "pos", "location", "telemetry"):
        if sub in d and isinstance(d[sub], dict):
            res = get_coord(d[sub], keys, latitude=latitude)
            if res is not None:
                return res
    return None


def location_pair(data: dict[str, Any]) -> tuple[float | None, float | None]:
    """Obtiene el par (latitud, longitud) normalizado y valida coordenadas nulas o incompletas."""
    lat = get_coord(data, ("lat", "latitude", "gps_lat", "adv_lat"), latitude=True)
    lon = get_coord(data, ("lon", "longitude", "gps_lon", "adv_lon"))
    # Firmware advert (0,0) denota sin GPS; un cero aislado también es incompleto.
    if lat == 0 and lon in (0, None):
        lat = None
    if lon == 0 and lat is None:
        lon = None
    return lat, lon


class TelemetryProcessor:
    """Procesador especializado para normalización, enriquecimiento, LQI y persistencia de telemetría."""

    def __init__(
        self,
        ctx: RxRouterContext,
        topics: MqttTopics,
        spawn_broadcast_fn: Callable[[dict[str, Any]], None],
        forward_external_mqtt_fn: Callable[..., None],
        resolve_sender_name_fn: Callable[[str], str],
    ) -> None:
        self._ctx = ctx
        self._topics = topics
        self._spawn_broadcast = spawn_broadcast_fn
        self._forward_external_mqtt = forward_external_mqtt_fn
        self._resolve_sender_name = resolve_sender_name_fn

    def handle_local_station_telemetry(
        self,
        ev_name: str,
        payload_dict: dict[str, Any],
        sender: str | None,
    ) -> bool:
        """Procesa y registra configuración y telemetría de la estación base local."""
        is_self_info = ev_name in ("self_info", "SELF_INFO", "self") or "SELF" in ev_name.upper()
        if is_self_info:
            node_name = payload_dict.get("name") or "Estación Base"
            pk_val = str(payload_dict.get("public_key", sender or "")).strip().lower()
            freq = payload_dict.get("radio_freq", "--")
            sf = payload_dict.get("radio_sf", "--")
            bw = payload_dict.get("radio_bw", "--")
            cr = payload_dict.get("radio_cr", "--")
            tx_p = normalize_tx_power(payload_dict.get("tx_power"))

            if pk_val and is_valid_node_key(pk_val) and self._ctx.node_registry is not None:
                self._ctx.node_registry.set_local_pubkey(pk_val)
                self._ctx.node_registry.add_or_update(
                    pk_val,
                    NodeContactUpdate(
                        name=node_name,
                        alias=node_name,
                        role="LOCAL",
                        is_local=True,
                        hops=0,
                        fixed_position=True,
                    ),
                )
            if self._ctx.admin_handler and hasattr(self._ctx.admin_handler, "_local_config"):
                cfg_update: dict[str, Any] = {"name": node_name}
                if pk_val:
                    cfg_update["public_key"] = pk_val
                if freq != "--":
                    try:
                        cfg_update["frequency"] = float(freq)
                        cfg_update["radio_freq"] = float(freq)
                    except (ValueError, TypeError):
                        pass
                if sf != "--":
                    try:
                        cfg_update["spreading_factor"] = int(sf)
                    except (ValueError, TypeError):
                        pass
                if bw != "--":
                    try:
                        cfg_update["bandwidth"] = float(bw)
                    except (ValueError, TypeError):
                        pass
                if cr != "--":
                    try:
                        cfg_update["coding_rate"] = int(cr)
                    except (ValueError, TypeError):
                        pass
                if tx_p is not None or ("tx_power" in payload_dict and payload_dict["tx_power"] is None):
                    cfg_update["tx_power"] = tx_p
                self._ctx.admin_handler._local_config.update(cfg_update)

            logging.info(
                f"[ESTACIÓN LOCAL] Configuración: {node_name} ({pk_val[:8] if pk_val else '??'}) | Freq: {freq} MHz, SF{sf}/BW{bw}/CR{cr}, TX: {tx_p} dBm"
            )
            return True

        if ev_name in ("device_info", "DEVICE_INFO", "device"):
            model = payload_dict.get("model") or "LoRa Device"
            ver = payload_dict.get("ver") or payload_dict.get("firmware_version") or ""
            build = payload_dict.get("fw_build") or ""
            max_c = payload_dict.get("max_contacts", "--")
            if "repeat" in payload_dict and self._ctx.admin_handler:
                self._ctx.admin_handler._local_config["repeat"] = bool(payload_dict["repeat"])
            rep_status = "ON" if payload_dict.get("repeat") else "OFF"
            logging.info(
                f"[ESTACIÓN LOCAL] Hardware: {model} {ver} (Build: {build}, Contactos Máx: {max_c}, Repetidor: {rep_status})"
            )
            return True

        return False

    def handle_mesh_telemetry_msg(self, payload_dict: dict[str, Any]) -> None:
        """Procesa, normaliza, enriquece con LQI y publica eventos de telemetría de la malla."""
        payload_dict = sanitize_public_payload(payload_dict)
        ev_name = str(payload_dict.get("event_type", payload_dict.get("type", "telemetry")))
        is_self_info = ev_name in ("self_info", "SELF_INFO", "self") or "SELF" in ev_name.upper()
        if is_self_info and "tx_power" in payload_dict:
            raw_power = payload_dict["tx_power"]
            power = normalize_tx_power(raw_power)
            if power is not None or raw_power is None:
                payload_dict["tx_power"] = power
            else:
                payload_dict.pop("tx_power")

        # Extraer y normalizar exhaustivamente todas las lecturas de telemetría/sensores
        extracted_fields = extract_telemetry_fields(payload_dict)
        if is_self_info:
            # Telemetría genérica acepta floats; SELF_INFO es un campo int8
            extracted_fields.pop("tx_power", None)
        payload_dict.update(extracted_fields)
        latitude, longitude = location_pair(payload_dict)
        for key in ("lat", "latitude", "gps_lat", "adv_lat"):
            if key in payload_dict:
                payload_dict[key] = latitude
        for key in ("lon", "longitude", "gps_lon", "adv_lon"):
            if key in payload_dict:
                payload_dict[key] = longitude

        # Si el payload contiene texto de telemetría de repetidor
        raw_text_cand = payload_dict.get("text", payload_dict.get("raw_text", payload_dict.get("message", "")))
        if isinstance(raw_text_cand, str) and raw_text_cand.strip() and self._ctx.repeater_manager is not None:
            extracted_rep = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(raw_text_cand)
            if extracted_rep:
                payload_dict.update(extracted_rep)

        # Resolver emisor si aún no está resuelto
        sender, sender_name_cand = extract_sender_from_payload(payload_dict)
        if not sender and payload_dict.get("pubkey_prefix") and self._ctx.node_registry is not None:
            contact = self._ctx.node_registry.get_by_key_or_prefix(str(payload_dict["pubkey_prefix"]))
            if contact and contact.public_key:
                sender = contact.public_key
                if not sender_name_cand:
                    sender_name_cand = contact.alias or contact.name
        if sender:
            payload_dict["sender"] = sender
        if sender_name_cand:
            payload_dict["sender_name"] = sender_name_cand

        if sender and is_valid_node_key(sender) and self._ctx.node_registry is not None:
            is_local_telem = bool(
                payload_dict.get("is_local")
                or self._ctx.node_registry.is_local_key(sender)
            )
            sender_name_cand = str(
                payload_dict.get("sender_name")
                or payload_dict.get("adv_name")
                or payload_dict.get("name")
                or payload_dict.get("alias")
                or self._resolve_sender_name(sender)
            )
            existing_contact = self._ctx.node_registry.get_contact(sender)
            is_known_rep = bool(
                existing_contact and existing_contact.role in ("REPEATER", "ROUTER")
            )

            telem_role = payload_dict.get("role")
            if not telem_role:
                if is_known_rep:
                    telem_role = "REPEATER"
                elif existing_contact and existing_contact.role:
                    telem_role = existing_contact.role
                else:
                    telem_role = "CLIENT"

            clean_rssi = clean_numeric_value(payload_dict.get("last_rssi", payload_dict.get("rssi")))
            clean_snr = clean_numeric_value(payload_dict.get("last_snr", payload_dict.get("snr")))

            telem_update = NodeContactUpdate.from_dict(
                payload_dict,
                last_seen=time.time() if not is_local_telem else None,
                name=sender_name_cand,
                role=telem_role,
                last_rssi=int(round(clean_rssi)) if clean_rssi is not None else None,
                last_snr=round(clean_snr, 1) if clean_snr is not None else None,
            )
            updated_telem_contact = self._ctx.node_registry.add_or_update(sender, telem_update)
            if updated_telem_contact and not is_local_telem:
                contact_dict = updated_telem_contact.to_dict()
                db = getattr(self._ctx.node_registry, "database", None)
                if str(updated_telem_contact.role).upper() == "SENSOR" and db is not None and hasattr(db, "get_sensor_subscription_public_view"):
                    contact_dict["sensor_subscription"] = db.get_sensor_subscription_public_view(updated_telem_contact.public_key)
                self._spawn_broadcast({
                    "type": "contact_updated",
                    "event_type": "contact_updated",
                    "contact": contact_dict,
                })

        # Sanitizar cualquier otro campo bytes restante
        for k, v in list(payload_dict.items()):
            if isinstance(v, (bytes, bytearray)):
                payload_dict[k] = bytes(v).hex()

        payload_dict["timestamp"] = datetime.now(UTC).isoformat()
        evt_json = json.dumps(payload_dict, sort_keys=True)
        if self._ctx.mqtt is not None:
            self._ctx.mqtt.publish_safe(self._topics.rx_all, evt_json, qos=0)
        is_telemetry_payload = (
            payload_dict.get("telemetry_source") == "sensor_subscription"
            or any(
                k in payload_dict
                for k in (
                    "battery", "battery_pct", "battery_mv", "voltage", "voltage_v",
                    "temperature", "temperature_c", "humidity_pct", "pressure_hpa",
                    "solar_v", "lpp_readings",
                )
            )
        )
        if is_telemetry_payload and self._ctx.mqtt is not None:
            self._ctx.mqtt.publish_safe(self._topics.rx_telemetry, evt_json, qos=0)
        self._spawn_broadcast(payload_dict)

        if not is_self_info:
            ev_type = "telemetry" if is_telemetry_payload else "node"
            self._forward_external_mqtt(
                event_type=ev_type,
                payload_data=payload_dict,
                pubkey=str(sender or ""),
            )

        # Actualizar ocupación de canal en RateLimiter para gobernar el Airtime Cutoff
        ch_util_cand = payload_dict.get("channel_utilization", payload_dict.get("ch_util"))
        if ch_util_cand is not None:
            try:
                ch_util_val = float(ch_util_cand)
                bridge = getattr(self._ctx, "bridge", None) or getattr(self._ctx, "_bridge", None)
                if bridge and hasattr(bridge, "rate_limiter") and bridge.rate_limiter:
                    bridge.rate_limiter.update_channel_utilization(ch_util_val)
            except Exception as e:
                logging.debug(f"Error actualizando ocupación de canal en rate limiter: {e}")

        # Si el evento corresponde a configuración o hardware del nodo local, procesar con el handler dedicado
        if self.handle_local_station_telemetry(ev_name, payload_dict, sender):
            return

        self._compute_lqi_and_log(ev_name, payload_dict, sender)

    def _compute_lqi_and_log(
        self,
        ev_name: str,
        payload_dict: dict[str, Any],
        sender: str | None,
    ) -> None:
        """Calcula LQI instantáneo, formatea el resumen de sensores y emite el log estructurado."""
        sender_name_val = payload_dict.get("sender_name")
        if sender and sender_name_val and sender_name_val != sender and len(sender) >= 8:
            sender_label = f"{sender_name_val} ({sender[:8]})"
        elif sender_name_val:
            sender_label = str(sender_name_val)
        elif sender and len(sender) >= 8:
            sender_label = f"Nodo [{sender[:8]}]"
        elif payload_dict.get("pubkey_prefix"):
            sender_label = f"Nodo [{str(payload_dict['pubkey_prefix'])[:8]}]"
        else:
            is_ev_local = any(k in ev_name.lower() for k in (
                "self", "battery", "device", "stats", "tuning", "time", "custom_vars", "status", "channel"
            ))
            sender_label = "Estación Base Local" if is_ev_local else "Desconocido"

        rssi_val = payload_dict.get("rssi", payload_dict.get("RSSI", payload_dict.get("last_rssi")))
        snr_val = payload_dict.get("snr", payload_dict.get("SNR", payload_dict.get("last_snr")))
        rssi_str = f"{rssi_val} dBm" if rssi_val is not None else "N/A"
        snr_str = f"{snr_val} dB" if snr_val is not None else "N/A"

        lqi_part = ""
        if rssi_val is not None and snr_val is not None:
            try:
                snr_f = float(snr_val)
                rssi_f = float(rssi_val)
                hops_val = int(payload_dict.get("hops", 0) or 0)
                instant_lqi = LinkQualityEngine.compute_instant_lqi(snr_f, rssi_f, hops=hops_val)
                lqi_stat = LinkQualityEngine.classify_lqi_status(instant_lqi)
                lqi_part = f" | LQI: {instant_lqi:.1f}% [{lqi_stat}]"
                payload_dict["lqi_score"] = instant_lqi
                payload_dict["lqi_status"] = lqi_stat
            except (ValueError, TypeError):
                pass

        telem_summary = format_telemetry_summary(payload_dict)

        # Distinguir telemetría de hardware local o tramas vacías vs telemetría RF legítima de nodos remotos
        is_local_station = (
            sender_label.startswith("Estación Base Local")
            or (sender and self._ctx.node_registry and sender == self._ctx.node_registry.local_pubkey)
            or (sender and str(sender).upper() == "LOCAL")
            or payload_dict.get("is_local") is True
            or any(k in ev_name.lower() for k in ("self", "battery", "device", "stats", "tuning", "time", "custom_vars", "channel"))
        )
        has_readings = telem_summary != "Sin lecturas adicionales"

        if is_local_station:
            log_fn = logging.debug if str(ev_name).lower() in ("time", "clock") else logging.info
            log_fn(
                f"[ESTACIÓN LOCAL] Telemetría/Diagnóstico ({ev_name}): {telem_summary}"
            )
            return

        if sender_label == "Desconocido" and not has_readings:
            logging.debug(
                f"[RX-TELEMETRÍA] Respuesta interna/vacía sin emisor (Tipo: {ev_name})"
            )
            return

        logging.info(
            f"[RX-TELEMETRÍA] De: {sender_label} -> Para: Gateway/MQTT | "
            f"Tipo: {ev_name} | {telem_summary} | RSSI: {rssi_str}, SNR: {snr_str}{lqi_part}"
        )

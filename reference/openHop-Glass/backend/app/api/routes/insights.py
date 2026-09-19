from __future__ import annotations
import asyncio
import json
import re
from collections import Counter

from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    MqttIngestEvent,
    Packet,
    Repeater,
    TopologyNode,
    TopologyObservation,
    TopologyObservationSample,
    User,
)
from app.db.session import get_db_session
from app.schemas.insights import (
    NeighborObservationListResponse,
    NeighborObservationResponse,
    NodeDetailResponse,
    TopologyPacketGraphEdgeResponse,
    TopologyPacketGraphNodeResponse,
    TopologyPacketQualityResponse,
    TopologyPacketStructureResponse,
    TopologyPacketSubpathResponse,
    TopologyRepeaterTrafficShareResponse,
    TopologySignalDistributionBinResponse,
    TopologySignalTrendPointResponse,
    NodeObserverSnapshotResponse,
    NodeTimeseriesPointResponse,
    NodeTimeseriesResponse,
    TopologyEdgeListResponse,
    TopologyEdgeResponse,
    TopologySummaryResponse,
)
from app.security.deps import require_roles
from app.services.telemetry_stream import get_mqtt_telemetry_broadcaster

router = APIRouter(prefix="/api/insights")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _bool_from_int(value: int | None) -> bool | None:
    if value is None:
        return None
    return value != 0


def _to_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return _ensure_utc(parsed)
    return None


def _normalized_coordinates(latitude: Any, longitude: Any) -> tuple[float | None, float | None]:
    lat = _to_optional_float(latitude)
    lng = _to_optional_float(longitude)
    if lat is None or lng is None:
        return None, None
    if lat < -90 or lat > 90:
        return None, None
    if lng < -180 or lng > 180:
        return None, None
    return lat, lng


def _route_bucket_key(route_type: int | None) -> str:
    return "unknown" if route_type is None else str(route_type)


def _format_sse(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def _build_filter_clauses(
    *,
    cutoff: datetime,
    observer_node_name: str | None,
    contact_type: str | None,
    route_type: int | None,
    zero_hop: bool | None,
    search: str | None,
) -> list[Any]:
    clauses: list[Any] = [TopologyObservation.last_seen_at >= cutoff]
    if observer_node_name:
        clauses.append(Repeater.node_name == observer_node_name.strip())
    if contact_type:
        clauses.append(TopologyObservation.contact_type == contact_type.strip())
    if route_type is not None:
        clauses.append(TopologyObservation.route_type == route_type)
    if zero_hop is not None:
        clauses.append(TopologyObservation.zero_hop == int(zero_hop))
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        clauses.append(
            or_(
                func.lower(TopologyNode.pubkey).like(pattern),
                func.lower(func.coalesce(TopologyNode.node_name, "")).like(pattern),
                func.lower(Repeater.node_name).like(pattern),
                func.lower(func.coalesce(TopologyObservation.contact_type, "")).like(pattern),
            )
        )
    return clauses

def _normalize_count_key(value: Any, *, unknown: str = "unknown") -> str:
    text = _to_optional_string(value)
    return text if text is not None else unknown


def _bucket_start(timestamp: datetime, bucket_seconds: int) -> datetime:
    epoch = int(_ensure_utc(timestamp).timestamp())
    return datetime.fromtimestamp(epoch - (epoch % bucket_seconds), UTC)


def _build_signal_distribution(
    values: list[float],
    *,
    bins: int = 12,
) -> list[TopologySignalDistributionBinResponse]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if low == high:
        return [
            TopologySignalDistributionBinResponse(
                range_start=float(round(low, 3)),
                range_end=float(round(high, 3)),
                count=len(values),
            )
        ]

    safe_bins = max(1, bins)
    width = (high - low) / safe_bins
    counts = [0 for _ in range(safe_bins)]
    for value in values:
        index = int((value - low) / width)
        if index >= safe_bins:
            index = safe_bins - 1
        counts[index] += 1

    output: list[TopologySignalDistributionBinResponse] = []
    for index, count in enumerate(counts):
        if count <= 0:
            continue
        start = low + index * width
        end = high if index == safe_bins - 1 else start + width
        output.append(
            TopologySignalDistributionBinResponse(
                range_start=float(round(start, 3)),
                range_end=float(round(end, 3)),
                count=count,
            )
        )
    return output


def _normalize_hop_token(value: Any) -> str | None:
    token = _to_optional_string(value)
    if token is None:
        return None
    normalized = token[2:] if token.lower().startswith("0x") else token
    normalized = normalized.strip()
    if not normalized:
        return None
    if re.fullmatch(r"[0-9a-fA-F]+", normalized):
        return normalized.upper()
    return normalized


def _parse_hops_from_value(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                decoded_json = json.loads(text)
            except json.JSONDecodeError:
                decoded_json = None
            if decoded_json is not None:
                return _parse_hops_from_value(decoded_json)
        tokens = [piece for piece in re.split(r"[\s,>|/]+", text) if piece]
        output: list[str] = []
        for token in tokens:
            normalized = _normalize_hop_token(token)
            if normalized is not None:
                output.append(normalized)
        return output

    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(_parse_hops_from_value(item))
        return output

    normalized = _normalize_hop_token(value)
    return [normalized] if normalized is not None else []


def _decode_raw_packet_hops(raw_hex: str) -> list[str]:
    normalized_hex = re.sub(r"\s+", "", raw_hex)
    if not normalized_hex:
        return []
    if len(normalized_hex) % 2 != 0:
        return []
    try:
        payload_bytes = bytes.fromhex(normalized_hex)
    except ValueError:
        return []
    if len(payload_bytes) < 2:
        return []

    route_type = payload_bytes[0] & 0x03
    offset = 1
    if route_type in {0, 3}:
        offset += 4
    if offset >= len(payload_bytes):
        return []

    path_descriptor = payload_bytes[offset]
    offset += 1
    hash_size = int(path_descriptor >> 6) + 1
    hash_count = int(path_descriptor & 0x3F)
    if hash_count <= 0:
        return []

    required = hash_size * hash_count
    if offset + required > len(payload_bytes):
        return []

    hops: list[str] = []
    for index in range(hash_count):
        start = offset + index * hash_size
        end = start + hash_size
        hops.append(payload_bytes[start:end].hex().upper())
    return hops


def _extract_packet_hops(payload: dict[str, Any]) -> tuple[list[str], str | None]:
    nested_payload = payload.get("payload")
    nested_map = nested_payload if isinstance(nested_payload, dict) else {}
    for key in ("hops", "path", "route_hops", "resolved_path", "routePath"):
        hops = _parse_hops_from_value(payload.get(key))
        if hops:
            return hops, "structured"
        hops = _parse_hops_from_value(nested_map.get(key))
        if hops:
            return hops, "structured"

    raw_hex = _to_optional_string(payload.get("raw")) or _to_optional_string(nested_map.get("raw"))
    if raw_hex:
        hops = _decode_raw_packet_hops(raw_hex)
        if hops:
            return hops, "raw"

    src_hash = _normalize_hop_token(payload.get("src_hash")) or _normalize_hop_token(nested_map.get("src_hash"))
    dst_hash = _normalize_hop_token(payload.get("dst_hash")) or _normalize_hop_token(nested_map.get("dst_hash"))
    if src_hash and dst_hash:
        return [src_hash, dst_hash], "derived"
    return [], None


def _extract_channel_detail(payload: dict[str, Any]) -> str | None:
    nested_payload = payload.get("payload")
    nested_map = nested_payload if isinstance(nested_payload, dict) else {}
    for key in ("channel", "channel_hash", "channelHash", "channel_hash_hex", "channelHashHex"):
        value = _to_optional_string(payload.get(key))
        if value is not None:
            return f"{key}:{value}"
        value = _to_optional_string(nested_map.get(key))
        if value is not None:
            return f"{key}:{value}"
    return None

@router.get("/neighbors/latest", response_model=NeighborObservationListResponse)
def list_neighbor_observations(
    hours: int = Query(default=168, ge=1, le=24 * 30),
    limit: int = Query(default=300, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    observer_node_name: str | None = Query(default=None),
    contact_type: str | None = Query(default=None),
    route_type: int | None = Query(default=None),
    zero_hop: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> NeighborObservationListResponse:
    cutoff = _utc_now() - timedelta(hours=hours)
    clauses = _build_filter_clauses(
        cutoff=cutoff,
        observer_node_name=observer_node_name,
        contact_type=contact_type,
        route_type=route_type,
        zero_hop=zero_hop,
        search=search,
    )

    base_select = (
        select(TopologyObservation, TopologyNode, Repeater.node_name.label("observer_node_name"))
        .join(TopologyNode, TopologyNode.id == TopologyObservation.observed_node_id)
        .join(Repeater, Repeater.id == TopologyObservation.observer_repeater_id)
        .where(*clauses)
    )

    total = int(
        db.scalar(
            select(func.count(TopologyObservation.id))
            .join(TopologyNode, TopologyNode.id == TopologyObservation.observed_node_id)
            .join(Repeater, Repeater.id == TopologyObservation.observer_repeater_id)
            .where(*clauses)
        )
        or 0
    )
    unique_observed_nodes = int(
        db.scalar(
            select(func.count(func.distinct(TopologyObservation.observed_node_id)))
            .join(TopologyNode, TopologyNode.id == TopologyObservation.observed_node_id)
            .join(Repeater, Repeater.id == TopologyObservation.observer_repeater_id)
            .where(*clauses)
        )
        or 0
    )
    unique_observers = int(
        db.scalar(
            select(func.count(func.distinct(TopologyObservation.observer_repeater_id)))
            .join(TopologyNode, TopologyNode.id == TopologyObservation.observed_node_id)
            .join(Repeater, Repeater.id == TopologyObservation.observer_repeater_id)
            .where(*clauses)
        )
        or 0
    )

    rows = db.execute(
        base_select.order_by(TopologyObservation.last_seen_at.desc()).offset(offset).limit(limit)
    ).all()
    paged_items = [
        NeighborObservationResponse(
            observer_repeater_id=observation.observer_repeater_id,
            observer_node_name=observer_node_name_value,
            pubkey=node.pubkey,
            node_name=node.node_name,
            is_repeater=_bool_from_int(node.is_repeater),
            contact_type=observation.contact_type,
            route_type=observation.route_type,
            zero_hop=_bool_from_int(observation.zero_hop),
            latitude=observation.latitude,
            longitude=observation.longitude,
            rssi=observation.rssi,
            snr=observation.snr,
            first_seen=_ensure_utc(observation.first_seen_at)
            if observation.first_seen_at is not None
            else None,
            last_seen=_ensure_utc(observation.last_seen_at),
            advert_count=observation.advert_count,
        )
        for observation, node, observer_node_name_value in rows
    ]
    return NeighborObservationListResponse(
        hours=hours,
        total=total,
        limit=limit,
        offset=offset,
        unique_observed_nodes=unique_observed_nodes,
        unique_observers=unique_observers,
        items=paged_items,
    )


@router.get("/nodes/{pubkey}", response_model=NodeDetailResponse)
def get_node_detail(
    pubkey: str,
    hours: int = Query(default=168, ge=1, le=24 * 30),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> NodeDetailResponse:
    normalized_pubkey = pubkey.strip().lower()
    if not normalized_pubkey:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pubkey is required",
        )
    node = db.scalar(select(TopologyNode).where(func.lower(TopologyNode.pubkey) == normalized_pubkey))
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node observation not found in selected time window",
        )

    cutoff = _utc_now() - timedelta(hours=hours)
    rows = db.execute(
        select(TopologyObservation, Repeater.node_name.label("observer_node_name"))
        .join(Repeater, Repeater.id == TopologyObservation.observer_repeater_id)
        .where(TopologyObservation.observed_node_id == node.id)
        .where(TopologyObservation.last_seen_at >= cutoff)
        .order_by(TopologyObservation.last_seen_at.desc())
    ).all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node observation not found in selected time window",
        )

    observers: list[NodeObserverSnapshotResponse] = []
    last_seen_values: list[datetime] = []
    first_seen_values: list[datetime] = []
    for observation, observer_node_name_value in rows:
        last_seen_values.append(_ensure_utc(observation.last_seen_at))
        if observation.first_seen_at is not None:
            first_seen_values.append(_ensure_utc(observation.first_seen_at))
        observers.append(
            NodeObserverSnapshotResponse(
                observer_repeater_id=observation.observer_repeater_id,
                observer_node_name=observer_node_name_value,
                contact_type=observation.contact_type,
                route_type=observation.route_type,
                zero_hop=_bool_from_int(observation.zero_hop),
                latitude=observation.latitude,
                longitude=observation.longitude,
                rssi=observation.rssi,
                snr=observation.snr,
                first_seen=_ensure_utc(observation.first_seen_at)
                if observation.first_seen_at is not None
                else None,
                last_seen=_ensure_utc(observation.last_seen_at),
                advert_count=observation.advert_count,
            )
        )

    first_seen = _ensure_utc(node.first_seen_at) if node.first_seen_at else None
    if first_seen is None and first_seen_values:
        first_seen = min(first_seen_values)
    if first_seen is None:
        first_seen = min(last_seen_values)

    last_seen = max(last_seen_values)
    zero_hop_observer_count = sum(1 for item in observers if item.zero_hop is True)
    effective_contact_type = node.contact_type
    if effective_contact_type is None and observers:
        effective_contact_type = observers[0].contact_type

    return NodeDetailResponse(
        pubkey=node.pubkey,
        node_name=node.node_name,
        is_repeater=_bool_from_int(node.is_repeater),
        contact_type=effective_contact_type,
        latitude=node.latitude,
        longitude=node.longitude,
        first_seen=first_seen,
        last_seen=last_seen,
        observer_count=len(observers),
        zero_hop_observer_count=zero_hop_observer_count,
        observers=observers,
    )


@router.get("/topology/summary", response_model=TopologySummaryResponse)
def get_topology_summary(
    hours: int = Query(default=168, ge=1, le=24 * 30),
    stale_after_hours: int = Query(default=6, ge=1, le=24 * 7),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> TopologySummaryResponse:
    now = _utc_now()
    cutoff = now - timedelta(hours=hours)
    stale_cutoff = now - timedelta(hours=stale_after_hours)

    (
        total_observations,
        unique_nodes,
        unique_observers,
        zero_hop_observations,
        avg_rssi,
        avg_snr,
        last_ingested_at,
    ) = db.execute(
        select(
            func.count(TopologyObservation.id),
            func.count(func.distinct(TopologyObservation.observed_node_id)),
            func.count(func.distinct(TopologyObservation.observer_repeater_id)),
            func.coalesce(func.sum(func.coalesce(TopologyObservation.zero_hop, 0)), 0),
            func.avg(TopologyObservation.rssi),
            func.avg(TopologyObservation.snr),
            func.max(TopologyObservation.last_ingested_at),
        ).where(TopologyObservation.last_seen_at >= cutoff)
    ).one()

    stale_nodes = int(
        db.scalar(
            select(func.count())
            .select_from(
                select(TopologyObservation.observed_node_id)
                .where(TopologyObservation.last_seen_at >= cutoff)
                .group_by(TopologyObservation.observed_node_id)
                .having(func.max(TopologyObservation.last_seen_at) < stale_cutoff)
                .subquery()
            )
        )
        or 0
    )

    top_observer_row = db.execute(
        select(
            Repeater.node_name,
            func.count(TopologyObservation.id).label("observation_count"),
        )
        .join(TopologyObservation, TopologyObservation.observer_repeater_id == Repeater.id)
        .where(TopologyObservation.last_seen_at >= cutoff)
        .group_by(Repeater.id, Repeater.node_name)
        .order_by(func.count(TopologyObservation.id).desc(), Repeater.node_name.asc())
        .limit(1)
    ).first()

    latest_mqtt_ingested_at = db.scalar(
        select(func.max(MqttIngestEvent.ingested_at)).where(MqttIngestEvent.ingested_at >= cutoff)
    )
    latest_packet_ingested_at = db.scalar(
        select(func.max(MqttIngestEvent.ingested_at))
        .where(MqttIngestEvent.ingested_at >= cutoff)
        .where(MqttIngestEvent.event_type == "packet")
    )
    latest_event_ingested_at = db.scalar(
        select(func.max(MqttIngestEvent.ingested_at))
        .where(MqttIngestEvent.ingested_at >= cutoff)
        .where(MqttIngestEvent.event_type == "event")
    )

    def _lag_seconds(latest: Any) -> int | None:
        if not isinstance(latest, datetime):
            return None
        return max(int((now - _ensure_utc(latest)).total_seconds()), 0)

    topology_advert_lag_seconds = _lag_seconds(last_ingested_at)
    mqtt_overall_lag_seconds = _lag_seconds(latest_mqtt_ingested_at)
    mqtt_packet_lag_seconds = _lag_seconds(latest_packet_ingested_at)
    mqtt_event_lag_seconds = _lag_seconds(latest_event_ingested_at)

    total_observations_int = int(total_observations or 0)
    zero_hop_int = int(zero_hop_observations or 0)
    return TopologySummaryResponse(
        hours=hours,
        total_observations=total_observations_int,
        unique_nodes=int(unique_nodes or 0),
        unique_observers=int(unique_observers or 0),
        zero_hop_observations=zero_hop_int,
        multi_hop_observations=max(total_observations_int - zero_hop_int, 0),
        stale_nodes=stale_nodes,
        avg_rssi=float(avg_rssi) if avg_rssi is not None else None,
        avg_snr=float(avg_snr) if avg_snr is not None else None,
        topology_advert_lag_seconds=topology_advert_lag_seconds,
        mqtt_overall_lag_seconds=mqtt_overall_lag_seconds,
        mqtt_packet_lag_seconds=mqtt_packet_lag_seconds,
        mqtt_event_lag_seconds=mqtt_event_lag_seconds,
        telemetry_lag_seconds=topology_advert_lag_seconds,
        top_observer_node_name=top_observer_row[0] if top_observer_row is not None else None,
        top_observer_count=int(top_observer_row[1]) if top_observer_row is not None else None,
    )

@router.get("/topology/packet-quality", response_model=TopologyPacketQualityResponse)
def get_topology_packet_quality(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    bucket_minutes: int = Query(default=60, ge=5, le=24 * 60),
    limit: int = Query(default=5000, ge=100, le=50000),
    observer_node_name: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> TopologyPacketQualityResponse:
    cutoff = _utc_now() - timedelta(hours=hours)
    query = (
        select(
            Packet.timestamp,
            Packet.packet_type,
            Packet.route,
            Packet.rssi,
            Packet.snr,
            Repeater.id,
            Repeater.node_name,
        )
        .join(Repeater, Repeater.id == Packet.repeater_id)
        .where(Packet.timestamp >= cutoff)
        .order_by(Packet.timestamp.desc())
        .limit(limit)
    )
    if observer_node_name:
        query = query.where(Repeater.node_name == observer_node_name.strip())
    rows = db.execute(query).all()

    route_mix: Counter[str] = Counter()
    packet_type_mix: Counter[str] = Counter()
    repeater_counts: Counter[tuple[str, str]] = Counter()
    rssi_values: list[float] = []
    snr_values: list[float] = []
    bucket_seconds = bucket_minutes * 60
    trend_buckets: dict[datetime, dict[str, float | int]] = {}

    for timestamp, packet_type, route, rssi, snr, repeater_id, repeater_node_name in rows:
        route_mix[_normalize_count_key(route)] += 1
        packet_type_mix[_normalize_count_key(packet_type)] += 1
        repeater_counts[(str(repeater_id), str(repeater_node_name))] += 1
        if rssi is not None:
            rssi_values.append(float(rssi))
        if snr is not None:
            snr_values.append(float(snr))

        bucket_start = _bucket_start(timestamp, bucket_seconds)
        bucket = trend_buckets.get(bucket_start)
        if bucket is None:
            bucket = {
                "packet_count": 0,
                "rssi_sum": 0.0,
                "rssi_count": 0,
                "snr_sum": 0.0,
                "snr_count": 0,
            }
            trend_buckets[bucket_start] = bucket
        bucket["packet_count"] += 1
        if rssi is not None:
            bucket["rssi_sum"] += float(rssi)
            bucket["rssi_count"] += 1
        if snr is not None:
            bucket["snr_sum"] += float(snr)
            bucket["snr_count"] += 1

    total_packets = len(rows)
    repeater_traffic_share = [
        TopologyRepeaterTrafficShareResponse(
            repeater_id=repeater_id,
            repeater_node_name=repeater_node_name,
            packet_count=count,
            share_percent=(count / total_packets * 100) if total_packets > 0 else 0.0,
        )
        for (repeater_id, repeater_node_name), count in repeater_counts.most_common(25)
    ]
    signal_trend = [
        TopologySignalTrendPointResponse(
            bucket_start=bucket_start,
            packet_count=int(values["packet_count"]),
            avg_rssi=float(values["rssi_sum"] / values["rssi_count"])
            if int(values["rssi_count"]) > 0
            else None,
            avg_snr=float(values["snr_sum"] / values["snr_count"])
            if int(values["snr_count"]) > 0
            else None,
        )
        for bucket_start, values in sorted(trend_buckets.items(), key=lambda item: item[0])
    ]

    return TopologyPacketQualityResponse(
        hours=hours,
        bucket_minutes=bucket_minutes,
        total_packets=total_packets,
        avg_rssi=(sum(rssi_values) / len(rssi_values)) if rssi_values else None,
        avg_snr=(sum(snr_values) / len(snr_values)) if snr_values else None,
        route_mix=dict(route_mix),
        packet_type_mix=dict(packet_type_mix),
        repeater_traffic_share=repeater_traffic_share,
        rssi_distribution=_build_signal_distribution(rssi_values),
        snr_distribution=_build_signal_distribution(snr_values),
        signal_trend=signal_trend,
    )


@router.get("/topology/packet-structure", response_model=TopologyPacketStructureResponse)
def get_topology_packet_structure(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    limit: int = Query(default=3000, ge=100, le=20000),
    top_subpaths: int = Query(default=20, ge=1, le=100),
    top_nodes: int = Query(default=120, ge=10, le=500),
    top_edges: int = Query(default=120, ge=10, le=500),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> TopologyPacketStructureResponse:
    cutoff = _utc_now() - timedelta(hours=hours)
    rows = db.execute(
        select(MqttIngestEvent.payload_json)
        .where(MqttIngestEvent.event_type == "packet")
        .where(MqttIngestEvent.timestamp >= cutoff)
        .order_by(MqttIngestEvent.ingested_at.desc())
        .limit(limit)
    ).all()

    analyzed_events = 0
    packets_with_raw = 0
    packets_with_structured_hops = 0
    packets_with_decoded_hops = 0
    packets_with_channel_details = 0
    channel_detail_mix: Counter[str] = Counter()
    subpath_counter: Counter[tuple[str, ...]] = Counter()
    node_counter: Counter[str] = Counter()
    edge_counter: Counter[tuple[str, str]] = Counter()

    for (payload_json,) in rows:
        try:
            payload = json.loads(payload_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        analyzed_events += 1

        nested_payload = payload.get("payload")
        nested_map = nested_payload if isinstance(nested_payload, dict) else {}
        has_raw = _to_optional_string(payload.get("raw")) is not None or _to_optional_string(
            nested_map.get("raw")
        ) is not None
        if has_raw:
            packets_with_raw += 1

        hops, source = _extract_packet_hops(payload)
        if source == "structured":
            packets_with_structured_hops += 1
        if hops:
            packets_with_decoded_hops += 1
            for hop in hops:
                node_counter[hop] += 1
            for index in range(len(hops) - 1):
                edge_counter[(hops[index], hops[index + 1])] += 1
            max_subpath_len = min(4, len(hops))
            for subpath_len in range(2, max_subpath_len + 1):
                for start in range(0, len(hops) - subpath_len + 1):
                    subpath_counter[tuple(hops[start : start + subpath_len])] += 1

        channel_detail = _extract_channel_detail(payload)
        if channel_detail is not None:
            packets_with_channel_details += 1
            channel_detail_mix[channel_detail] += 1

    top_subpath_rows = [
        TopologyPacketSubpathResponse(hops=list(hops), count=count)
        for hops, count in subpath_counter.most_common(top_subpaths)
    ]
    node_rows = [
        TopologyPacketGraphNodeResponse(node_id=node_id, label=node_id, count=count)
        for node_id, count in node_counter.most_common(top_nodes)
    ]
    edge_rows = [
        TopologyPacketGraphEdgeResponse(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            count=count,
        )
        for (source_node_id, target_node_id), count in edge_counter.most_common(top_edges)
    ]
    decode_coverage_percent = (
        (packets_with_decoded_hops / analyzed_events) * 100 if analyzed_events > 0 else 0.0
    )

    return TopologyPacketStructureResponse(
        hours=hours,
        total_packet_events=len(rows),
        analyzed_events=analyzed_events,
        packets_with_raw=packets_with_raw,
        packets_with_structured_hops=packets_with_structured_hops,
        packets_with_decoded_hops=packets_with_decoded_hops,
        packets_with_channel_details=packets_with_channel_details,
        decode_coverage_percent=decode_coverage_percent,
        channel_detail_mix=dict(channel_detail_mix),
        top_subpaths=top_subpath_rows,
        neighbor_graph_nodes=node_rows,
        neighbor_graph_edges=edge_rows,
    )


@router.get("/topology/edges", response_model=TopologyEdgeListResponse)
def list_topology_edges(
    hours: int = Query(default=168, ge=1, le=24 * 30),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    observer_node_name: str | None = Query(default=None),
    contact_type: str | None = Query(default=None),
    route_type: int | None = Query(default=None),
    zero_hop: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> TopologyEdgeListResponse:
    cutoff = _utc_now() - timedelta(hours=hours)
    observer_topology_node = aliased(TopologyNode)
    clauses = _build_filter_clauses(
        cutoff=cutoff,
        observer_node_name=observer_node_name,
        contact_type=contact_type,
        route_type=route_type,
        zero_hop=zero_hop,
        search=search,
    )

    total = int(
        db.scalar(
            select(func.count(TopologyObservation.id))
            .join(TopologyNode, TopologyNode.id == TopologyObservation.observed_node_id)
            .join(Repeater, Repeater.id == TopologyObservation.observer_repeater_id)
            .where(*clauses)
        )
        or 0
    )

    rows = db.execute(
        select(
            TopologyObservation,
            TopologyNode,
            Repeater.node_name.label("observer_node_name"),
            observer_topology_node.latitude.label("observer_latitude"),
            observer_topology_node.longitude.label("observer_longitude"),
        )
        .join(TopologyNode, TopologyNode.id == TopologyObservation.observed_node_id)
        .join(Repeater, Repeater.id == TopologyObservation.observer_repeater_id)
        .outerjoin(
            observer_topology_node,
            func.lower(observer_topology_node.pubkey) == func.lower(Repeater.pubkey),
        )
        .where(*clauses)
        .order_by(TopologyObservation.last_seen_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    items = [
        TopologyEdgeResponse(
            observer_repeater_id=observation.observer_repeater_id,
            observer_node_name=observer_name,
            observer_latitude=observer_latitude,
            observer_longitude=observer_longitude,
            observed_node_pubkey=observed_node.pubkey,
            observed_node_name=observed_node.node_name,
            observed_latitude=observed_node.latitude
            if observed_node.latitude is not None
            else observation.latitude,
            observed_longitude=observed_node.longitude
            if observed_node.longitude is not None
            else observation.longitude,
            route_type=observation.route_type,
            zero_hop=_bool_from_int(observation.zero_hop),
            contact_type=observation.contact_type,
            rssi=observation.rssi,
            snr=observation.snr,
            last_seen=_ensure_utc(observation.last_seen_at),
        )
        for observation, observed_node, observer_name, observer_latitude, observer_longitude in rows
    ]

    return TopologyEdgeListResponse(
        hours=hours,
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get("/nodes/{pubkey}/timeseries", response_model=NodeTimeseriesResponse)
def get_node_timeseries(
    pubkey: str,
    hours: int = Query(default=168, ge=1, le=24 * 30),
    bucket_hours: int = Query(default=6, ge=1, le=24 * 7),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> NodeTimeseriesResponse:
    normalized_pubkey = pubkey.strip().lower()
    if not normalized_pubkey:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pubkey is required",
        )

    node = db.scalar(select(TopologyNode).where(func.lower(TopologyNode.pubkey) == normalized_pubkey))
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if bucket_hours > hours:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bucket_hours cannot exceed hours",
        )

    cutoff = _utc_now() - timedelta(hours=hours)
    rows = db.execute(
        select(
            TopologyObservationSample.observed_at,
            TopologyObservationSample.rssi,
            TopologyObservationSample.snr,
            TopologyObservationSample.zero_hop,
            TopologyObservationSample.route_type,
        )
        .where(TopologyObservationSample.observed_node_id == node.id)
        .where(TopologyObservationSample.observed_at >= cutoff)
        .order_by(TopologyObservationSample.observed_at.asc())
    ).all()

    bucket_seconds = bucket_hours * 3600
    bucket_aggregates: dict[datetime, dict[str, Any]] = {}
    for observed_at, rssi, snr, zero_hop, route_type in rows:
        observed_ts = _ensure_utc(observed_at)
        epoch = int(observed_ts.timestamp())
        bucket_start_epoch = epoch - (epoch % bucket_seconds)
        bucket_start = datetime.fromtimestamp(bucket_start_epoch, UTC)

        aggregate = bucket_aggregates.get(bucket_start)
        if aggregate is None:
            aggregate = {
                "sample_count": 0,
                "rssi_sum": 0.0,
                "rssi_count": 0,
                "snr_sum": 0.0,
                "snr_count": 0,
                "zero_hop_count": 0,
                "route_counts": {},
            }
            bucket_aggregates[bucket_start] = aggregate

        aggregate["sample_count"] += 1
        if rssi is not None:
            aggregate["rssi_sum"] += float(rssi)
            aggregate["rssi_count"] += 1
        if snr is not None:
            aggregate["snr_sum"] += float(snr)
            aggregate["snr_count"] += 1
        if _bool_from_int(zero_hop):
            aggregate["zero_hop_count"] += 1

        route_key = _route_bucket_key(route_type)
        route_counts = aggregate["route_counts"]
        route_counts[route_key] = int(route_counts.get(route_key, 0)) + 1

    points = [
        NodeTimeseriesPointResponse(
            bucket_start=bucket_start,
            sample_count=aggregate["sample_count"],
            avg_rssi=aggregate["rssi_sum"] / aggregate["rssi_count"]
            if aggregate["rssi_count"] > 0
            else None,
            avg_snr=aggregate["snr_sum"] / aggregate["snr_count"]
            if aggregate["snr_count"] > 0
            else None,
            zero_hop_count=aggregate["zero_hop_count"],
            route_counts={str(k): int(v) for k, v in aggregate["route_counts"].items()},
        )
        for bucket_start, aggregate in sorted(bucket_aggregates.items(), key=lambda item: item[0])
    ]

    return NodeTimeseriesResponse(
        pubkey=node.pubkey,
        hours=hours,
        bucket_hours=bucket_hours,
        points=points,
    )


@router.get("/topology/stream")
async def stream_topology_updates(
    max_events: int | None = Query(default=None, ge=1, le=2000),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> StreamingResponse:
    broadcaster = get_mqtt_telemetry_broadcaster()
    queue = broadcaster.subscribe()

    async def _stream() -> AsyncGenerator[str, None]:
        emitted_events = 0
        yield _format_sse("ready", {"status": "connected"})
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                event_type = _to_optional_string(event.get("event_type"))
                if event_type != "advert":
                    continue

                payload = {
                    "event_id": event.get("event_id"),
                    "node_name": event.get("node_name"),
                    "timestamp": event.get("timestamp"),
                    "ingested_at": event.get("ingested_at"),
                    "payload": event.get("payload", {}),
                }
                yield _format_sse("topology_update", payload)
                emitted_events += 1
                if max_events is not None and emitted_events >= max_events:
                    break
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

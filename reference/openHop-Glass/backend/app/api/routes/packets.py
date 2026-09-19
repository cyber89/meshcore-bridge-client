from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Packet, Repeater, User
from app.db.session import get_db_session
from app.schemas.packets import PacketRecordResponse, PacketSummaryResponse
from app.security.deps import require_roles

router = APIRouter(prefix="/api/packets")


def _utc_now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[PacketRecordResponse])
def list_packets(
    limit: int = Query(default=200, ge=1, le=2000),
    node_name: str | None = Query(default=None),
    packet_type: str | None = Query(default=None),
    route: str | None = Query(default=None),
    hours: int | None = Query(default=24, ge=1, le=24 * 30),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[PacketRecordResponse]:
    query = (
        select(Packet, Repeater.node_name)
        .join(Repeater, Repeater.id == Packet.repeater_id)
        .order_by(Packet.timestamp.desc())
        .limit(limit)
    )
    if node_name:
        query = query.where(Repeater.node_name == node_name)
    if packet_type:
        query = query.where(Packet.packet_type == packet_type)
    if route:
        query = query.where(Packet.route == route)
    if hours is not None:
        cutoff = _utc_now() - timedelta(hours=hours)
        query = query.where(Packet.timestamp >= cutoff)

    rows = db.execute(query).all()
    return [
        PacketRecordResponse(
            id=packet.id,
            repeater_id=packet.repeater_id,
            node_name=row_node_name,
            timestamp=packet.timestamp,
            packet_type=packet.packet_type,
            route=packet.route,
            rssi=packet.rssi,
            snr=packet.snr,
            src_hash=packet.src_hash,
            dst_hash=packet.dst_hash,
            packet_hash=packet.packet_hash,
            payload=packet.payload,
        )
        for packet, row_node_name in rows
    ]


@router.get("/summary", response_model=PacketSummaryResponse)
def packet_summary(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    node_name: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> PacketSummaryResponse:
    cutoff = _utc_now() - timedelta(hours=hours)
    filters = [Packet.timestamp >= cutoff]
    if node_name:
        filters.append(Repeater.node_name == node_name)

    base_query = select(
        func.count(Packet.id),
        func.count(func.distinct(Packet.repeater_id)),
        func.count(func.distinct(Packet.src_hash)),
        func.count(func.distinct(Packet.dst_hash)),
        func.avg(Packet.rssi),
        func.avg(Packet.snr),
    ).select_from(Packet)
    if node_name:
        base_query = base_query.join(Repeater, Repeater.id == Packet.repeater_id)
    base_query = base_query.where(*filters)
    totals = db.execute(base_query).one()

    packet_type_rows = db.execute(
        select(Packet.packet_type, func.count(Packet.id))
        .select_from(Packet)
        .join(Repeater, Repeater.id == Packet.repeater_id)
        .where(*filters)
        .group_by(Packet.packet_type)
    ).all()
    route_rows = db.execute(
        select(Packet.route, func.count(Packet.id))
        .select_from(Packet)
        .join(Repeater, Repeater.id == Packet.repeater_id)
        .where(*filters)
        .group_by(Packet.route)
    ).all()
    repeater_rows = db.execute(
        select(Repeater.node_name, func.count(Packet.id))
        .select_from(Packet)
        .join(Repeater, Repeater.id == Packet.repeater_id)
        .where(*filters)
        .group_by(Repeater.node_name)
        .order_by(func.count(Packet.id).desc())
    ).all()

    return PacketSummaryResponse(
        hours=hours,
        total_packets=int(totals[0] or 0),
        unique_repeaters=int(totals[1] or 0),
        unique_sources=int(totals[2] or 0),
        unique_destinations=int(totals[3] or 0),
        avg_rssi=float(totals[4]) if totals[4] is not None else None,
        avg_snr=float(totals[5]) if totals[5] is not None else None,
        by_packet_type={
            str(packet_type_value or "unknown"): int(count)
            for packet_type_value, count in packet_type_rows
        },
        by_route={str(route_value or "unknown"): int(count) for route_value, count in route_rows},
        packets_per_repeater={
            str(repeater_name): int(count) for repeater_name, count in repeater_rows
        },
    )

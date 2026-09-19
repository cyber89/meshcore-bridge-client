import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CommandQueueItem,
    Repeater,
    TransportKey,
    TransportKeyGroup,
    TransportKeySyncStatus,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TransportKeySyncDispatchResult:
    payload_hash: str
    queued_commands: int
    skipped_commands: int


def build_transport_key_sync_payload(db: Session) -> tuple[dict, str]:
    groups = db.scalars(
        select(TransportKeyGroup).order_by(TransportKeyGroup.sort_order.asc(), TransportKeyGroup.name.asc())
    ).all()
    keys = db.scalars(select(TransportKey).order_by(TransportKey.sort_order.asc(), TransportKey.name.asc())).all()

    nodes: list[dict[str, object | None]] = []
    for group in groups:
        nodes.append(
            {
                "node_id": f"group:{group.id}",
                "kind": "group",
                "name": group.name,
                "flood_policy": group.flood_policy,
                "transport_key": group.transport_key,
                "parent_node_id": f"group:{group.parent_group_id}" if group.parent_group_id else None,
                "sort_order": group.sort_order,
            }
        )
    for key in keys:
        nodes.append(
            {
                "node_id": f"key:{key.id}",
                "kind": "key",
                "name": key.name,
                "flood_policy": key.flood_policy,
                "transport_key": key.transport_key,
                "parent_node_id": f"group:{key.group_id}" if key.group_id else None,
                "sort_order": key.sort_order,
            }
        )

    payload = {"sync_version": 1, "nodes": nodes}
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload, payload_hash


def queue_transport_key_sync_for_fleet(
    db: Session,
    *,
    requested_by: str,
) -> TransportKeySyncDispatchResult:
    payload, payload_hash = build_transport_key_sync_payload(db)
    payload_json = json.dumps(
        {
            "sync_version": 1,
            "payload_hash": payload_hash,
            "transport_keys": payload["nodes"],
        },
        separators=(",", ":"),
        sort_keys=True,
    )

    repeaters = db.scalars(
        select(Repeater).where(~Repeater.status.in_(["pending_adoption", "rejected"]))
    ).all()
    queued_commands = 0
    skipped_commands = 0
    now = _utc_now()
    for repeater in repeaters:
        sync_row = db.scalar(
            select(TransportKeySyncStatus).where(TransportKeySyncStatus.repeater_id == repeater.id)
        )
        if (
            sync_row is not None
            and sync_row.payload_hash == payload_hash
            and sync_row.status in {"queued", "dispatched", "success"}
        ):
            skipped_commands += 1
            continue

        command = CommandQueueItem(
            repeater_id=repeater.id,
            command="transport_keys_sync",
            params_json=payload_json,
            status="queued",
            requested_by=requested_by,
        )
        db.add(command)
        db.flush()
        if sync_row is None:
            sync_row = TransportKeySyncStatus(repeater_id=repeater.id)
            db.add(sync_row)
        sync_row.command_id = command.id
        sync_row.payload_hash = payload_hash
        sync_row.status = "queued"
        sync_row.error_message = None
        sync_row.queued_at = now
        sync_row.dispatched_at = None
        sync_row.completed_at = None
        sync_row.updated_at = now
        queued_commands += 1

    return TransportKeySyncDispatchResult(
        payload_hash=payload_hash,
        queued_commands=queued_commands,
        skipped_commands=skipped_commands,
    )


def mark_transport_key_sync_dispatched(
    db: Session,
    *,
    repeater_id: str,
    command_id: str,
) -> None:
    row = db.scalar(select(TransportKeySyncStatus).where(TransportKeySyncStatus.repeater_id == repeater_id))
    if row is None:
        row = TransportKeySyncStatus(repeater_id=repeater_id)
        db.add(row)
    now = _utc_now()
    row.command_id = command_id
    row.status = "dispatched"
    row.dispatched_at = now
    row.updated_at = now


def mark_transport_key_sync_result(
    db: Session,
    *,
    repeater_id: str,
    command_id: str,
    status: str,
    message: str | None,
    completed_at: datetime | None,
) -> None:
    row = db.scalar(select(TransportKeySyncStatus).where(TransportKeySyncStatus.repeater_id == repeater_id))
    if row is None:
        row = TransportKeySyncStatus(repeater_id=repeater_id)
        db.add(row)
    normalized_status = status.lower().strip()
    if normalized_status not in {"success", "failed", "partial"}:
        normalized_status = "failed"
    now = _utc_now()
    row.command_id = command_id
    row.status = normalized_status
    row.error_message = message if normalized_status in {"failed", "partial"} else None
    row.completed_at = completed_at or now
    row.updated_at = now


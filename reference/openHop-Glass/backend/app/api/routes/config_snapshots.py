import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import CommandQueueItem, ConfigSnapshot, Repeater, User
from app.db.session import get_db_session
from app.schemas.config_snapshot import (
    ConfigSnapshotDetailResponse,
    ConfigSnapshotExportQueuedResponse,
    ConfigSnapshotExportRequest,
    ConfigSnapshotResponse,
)
from app.security.deps import require_roles
from app.services.audit import write_audit_log
from app.services.config_snapshot import ConfigSnapshotService, SnapshotEncryptionError
from app.services.system_settings import get_effective_config_snapshot_encryption_keys

router = APIRouter(prefix="/api/config-snapshots")


def _to_response(snapshot: ConfigSnapshot, *, node_name: str) -> ConfigSnapshotResponse:
    return ConfigSnapshotResponse(
        id=snapshot.id,
        repeater_id=snapshot.repeater_id,
        node_name=node_name,
        command_id=snapshot.command_id,
        captured_at=snapshot.captured_at,
        created_at=snapshot.created_at,
        encryption_key_id=snapshot.encryption_key_id,
        payload_sha256=snapshot.payload_sha256,
        payload_size_bytes=snapshot.payload_size_bytes,
    )


def _resolve_repeater(db: Session, payload: ConfigSnapshotExportRequest) -> Repeater | None:
    if payload.repeater_id and payload.node_name:
        return db.scalar(
            select(Repeater).where(
                Repeater.id == payload.repeater_id,
                Repeater.node_name == payload.node_name,
            )
        )
    if payload.repeater_id:
        return db.scalar(select(Repeater).where(Repeater.id == payload.repeater_id))
    if payload.node_name:
        return db.scalar(select(Repeater).where(Repeater.node_name == payload.node_name))
    return None


@router.post(
    "/export",
    response_model=ConfigSnapshotExportQueuedResponse,
    status_code=status.HTTP_201_CREATED,
)
def queue_config_snapshot_export(
    payload: ConfigSnapshotExportRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> ConfigSnapshotExportQueuedResponse:
    repeater = _resolve_repeater(db, payload)
    if repeater is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repeater not found",
        )

    effective_keys, _, _ = get_effective_config_snapshot_encryption_keys(db)
    snapshot_service = ConfigSnapshotService(get_settings(), encryption_keys=effective_keys)
    if not snapshot_service.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Config snapshot encryption is not configured. "
                "Configure snapshot encryption keys in System Settings or set "
                "CONFIG_SNAPSHOT_ENCRYPTION_KEYS to one or more key_id:fernet_key values."
            ),
        )

    command = CommandQueueItem(
        repeater_id=repeater.id,
        command="export_config",
        params_json=json.dumps(
            {
                "format": "json",
                "include_secrets": True,
                "request_reason": payload.reason,
            }
        ),
        status="queued",
        requested_by=f"user:{current_user.email}",
    )
    db.add(command)
    db.flush()

    write_audit_log(
        db,
        action="config_snapshot_export_queued",
        target_type="command",
        target_id=command.id,
        user_id=current_user.id,
        details={
            "repeater_id": repeater.id,
            "node_name": repeater.node_name,
            "requested_by": current_user.email,
            "reason": payload.reason,
        },
    )
    db.commit()

    return ConfigSnapshotExportQueuedResponse(
        command_id=command.id,
        repeater_id=repeater.id,
        node_name=repeater.node_name,
        status=command.status,
        queued_at=command.created_at,
    )


@router.get("", response_model=list[ConfigSnapshotResponse])
def list_config_snapshots(
    repeater_id: str | None = Query(default=None),
    node_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator")),
) -> list[ConfigSnapshotResponse]:
    query = (
        select(ConfigSnapshot, Repeater.node_name)
        .join(Repeater, Repeater.id == ConfigSnapshot.repeater_id)
        .order_by(ConfigSnapshot.captured_at.desc(), ConfigSnapshot.created_at.desc())
        .limit(limit)
    )
    if repeater_id:
        query = query.where(ConfigSnapshot.repeater_id == repeater_id)
    if node_name:
        query = query.where(Repeater.node_name == node_name)

    rows = db.execute(query).all()
    return [_to_response(snapshot, node_name=row_node_name) for snapshot, row_node_name in rows]


@router.get("/{snapshot_id}", response_model=ConfigSnapshotDetailResponse)
def get_config_snapshot(
    snapshot_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> ConfigSnapshotDetailResponse:
    row = db.execute(
        select(ConfigSnapshot, Repeater.node_name)
        .join(Repeater, Repeater.id == ConfigSnapshot.repeater_id)
        .where(ConfigSnapshot.id == snapshot_id)
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config snapshot not found",
        )

    snapshot, node_name = row
    effective_keys, _, _ = get_effective_config_snapshot_encryption_keys(db)
    snapshot_service = ConfigSnapshotService(get_settings(), encryption_keys=effective_keys)
    try:
        payload = snapshot_service.decrypt_snapshot_payload(snapshot)
    except SnapshotEncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    write_audit_log(
        db,
        action="config_snapshot_viewed",
        target_type="config_snapshot",
        target_id=snapshot.id,
        user_id=current_user.id,
        details={"repeater_id": snapshot.repeater_id, "node_name": node_name},
    )
    db.commit()

    return ConfigSnapshotDetailResponse(
        **_to_response(snapshot, node_name=node_name).model_dump(),
        payload=payload,
    )

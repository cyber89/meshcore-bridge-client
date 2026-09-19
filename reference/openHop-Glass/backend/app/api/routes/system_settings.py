import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CommandQueueItem, Repeater, User
from app.db.session import get_db_session
from app.config import get_settings
from app.schemas.system_settings import (
    ConfigSnapshotEncryptionKeyGenerateRequest,
    ConfigSnapshotEncryptionKeyGenerateResponse,
    ConfigSnapshotEncryptionSettingsResponse,
    ConfigSnapshotEncryptionSettingsUpdateRequest,
    ManagedMqttSettingsResponse,
    ManagedMqttSettingsUpdateRequest,
    ManagedMqttSettingsUpdateResponse,
)
from app.security.deps import require_roles
from app.services.audit import write_audit_log
from app.services.system_settings import (
    get_effective_config_snapshot_encryption_keys,
    get_effective_managed_mqtt_settings,
    managed_mqtt_view_payload,
    save_config_snapshot_encryption_keys,
    save_managed_mqtt_settings,
)
from app.services.pki import PkiService

router = APIRouter(prefix="/api/system-settings")
_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_response(
    effective_settings: dict,
    source: str,
    updated_at: datetime | None,
) -> ManagedMqttSettingsResponse:
    view_payload = managed_mqtt_view_payload(effective_settings)
    return ManagedMqttSettingsResponse(
        mqtt_enabled=bool(view_payload.get("mqtt_enabled", True)),
        mqtt_broker_host=str(view_payload.get("mqtt_broker_host", "")),
        mqtt_broker_port=int(view_payload.get("mqtt_broker_port", 1883)),
        mqtt_base_topic=str(view_payload.get("mqtt_base_topic", "glass")),
        mqtt_tls_enabled=bool(view_payload.get("mqtt_tls_enabled", False)),
        source=source,
        updated_at=_normalize_datetime(updated_at),
    )


def _queue_update_for_repeaters(
    db: Session,
    effective_settings: dict,
    requested_by: str,
    reason: str | None,
) -> int:
    repeaters = db.scalars(
        select(Repeater).where(
            ~Repeater.status.in_(["pending_adoption", "rejected"]),
        )
    ).all()
    if not repeaters:
        return 0

    payload = {
        "config": {
            "glass_managed": managed_mqtt_view_payload(effective_settings),
        },
        "merge_mode": "patch",
    }
    for repeater in repeaters:
        db.add(
            CommandQueueItem(
                repeater_id=repeater.id,
                command="config_update",
                params_json=json.dumps(payload),
                status="queued",
                requested_by=requested_by,
            )
        )

    write_audit_log(
        db,
        action="managed_mqtt_settings_queued_to_fleet",
        target_type="repeater",
        target_id=None,
        details={
            "queued_commands": len(repeaters),
            "reason": reason,
            "requested_by": requested_by,
        },
    )
    return len(repeaters)


def _extract_key_ids(raw_keys: str | None) -> list[str]:
    if not raw_keys:
        return []
    key_ids: list[str] = []
    for token in raw_keys.split(","):
        part = token.strip()
        if not part or ":" not in part:
            continue
        key_id, _ = part.split(":", 1)
        normalized_key_id = key_id.strip()
        if normalized_key_id:
            key_ids.append(normalized_key_id)
    return key_ids


def _snapshot_settings_response(
    raw_keys: str | None,
    source: str,
    updated_at: datetime | None,
) -> ConfigSnapshotEncryptionSettingsResponse:
    return ConfigSnapshotEncryptionSettingsResponse(
        configured=bool(raw_keys),
        source=source,
        key_ids=_extract_key_ids(raw_keys),
        updated_at=_normalize_datetime(updated_at),
    )


@router.get("/mqtt-managed", response_model=ManagedMqttSettingsResponse)
def get_managed_mqtt_settings(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> ManagedMqttSettingsResponse:
    effective_settings, source, updated_at = get_effective_managed_mqtt_settings(db)
    return _to_response(effective_settings, source, updated_at)


@router.put("/mqtt-managed", response_model=ManagedMqttSettingsUpdateResponse)
def update_managed_mqtt_settings(
    payload: ManagedMqttSettingsUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> ManagedMqttSettingsUpdateResponse:
    save_payload = payload.model_dump(
        include={
            "mqtt_enabled",
            "mqtt_broker_host",
            "mqtt_broker_port",
            "mqtt_base_topic",
            "mqtt_tls_enabled",
        }
    )
    save_payload["mqtt_base_topic"] = str(save_payload["mqtt_base_topic"]).strip().strip("/")
    save_payload["mqtt_broker_host"] = str(save_payload["mqtt_broker_host"]).strip()
    if not save_payload["mqtt_broker_host"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="mqtt_broker_host cannot be empty",
        )
    if not save_payload["mqtt_base_topic"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="mqtt_base_topic cannot be empty",
        )
    save_managed_mqtt_settings(db, save_payload)

    effective_settings, _, _ = get_effective_managed_mqtt_settings(db)
    broker_host = str(effective_settings.get("mqtt_broker_host", "")).strip()
    pki_service = PkiService(get_settings())
    pki_service.ensure_ca()
    broker_cert_reissued = pki_service.ensure_mqtt_broker_server_certificate(
        extra_san_hosts=[broker_host] if broker_host else None
    )
    queued_commands = 0
    if payload.queue_to_repeaters:
        queued_commands = _queue_update_for_repeaters(
            db,
            effective_settings=effective_settings,
            requested_by=current_user.email,
            reason=payload.reason,
        )

    write_audit_log(
        db,
        action="managed_mqtt_settings_updated",
        target_type="system_settings",
        target_id="managed_mqtt_settings",
        user_id=current_user.id,
        details={
            "mqtt_enabled": effective_settings.get("mqtt_enabled"),
            "mqtt_broker_host": effective_settings.get("mqtt_broker_host"),
            "mqtt_broker_port": effective_settings.get("mqtt_broker_port"),
            "mqtt_base_topic": effective_settings.get("mqtt_base_topic"),
            "mqtt_tls_enabled": effective_settings.get("mqtt_tls_enabled"),
            "queue_to_repeaters": payload.queue_to_repeaters,
            "queued_commands": queued_commands,
            "broker_cert_reissued": broker_cert_reissued,
            "reason": payload.reason,
        },
    )
    db.commit()

    post_commit_settings, source, updated_at = get_effective_managed_mqtt_settings(db)
    return ManagedMqttSettingsUpdateResponse(
        settings=_to_response(post_commit_settings, source, updated_at),
        queued_commands=queued_commands,
    )


@router.get(
    "/config-snapshot-encryption",
    response_model=ConfigSnapshotEncryptionSettingsResponse,
)
def get_config_snapshot_encryption_settings(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> ConfigSnapshotEncryptionSettingsResponse:
    raw_keys, source, updated_at = get_effective_config_snapshot_encryption_keys(db)
    return _snapshot_settings_response(raw_keys, source, updated_at)


@router.put(
    "/config-snapshot-encryption",
    response_model=ConfigSnapshotEncryptionSettingsResponse,
)
def update_config_snapshot_encryption_settings(
    payload: ConfigSnapshotEncryptionSettingsUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin")),
) -> ConfigSnapshotEncryptionSettingsResponse:
    save_config_snapshot_encryption_keys(db, payload.encryption_keys)
    raw_keys, source, updated_at = get_effective_config_snapshot_encryption_keys(db)
    write_audit_log(
        db,
        action="config_snapshot_encryption_keys_updated",
        target_type="system_settings",
        target_id="config_snapshot_encryption",
        user_id=current_user.id,
        details={
            "source": source,
            "key_ids": _extract_key_ids(raw_keys),
            "reason": payload.reason,
        },
    )
    db.commit()
    return _snapshot_settings_response(raw_keys, source, updated_at)


@router.post(
    "/config-snapshot-encryption/generate",
    response_model=ConfigSnapshotEncryptionKeyGenerateResponse,
)
def generate_config_snapshot_encryption_key(
    payload: ConfigSnapshotEncryptionKeyGenerateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin")),
) -> ConfigSnapshotEncryptionKeyGenerateResponse:
    current_keys, _, _ = get_effective_config_snapshot_encryption_keys(db)
    if current_keys and not payload.replace_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Encryption keys already configured. Use replace_existing=true to replace.",
        )

    key_id = (
        payload.key_id.strip()
        if payload.key_id and payload.key_id.strip()
        else f"generated-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    )
    if not _KEY_ID_PATTERN.fullmatch(key_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="key_id may only contain letters, numbers, dot, underscore, or hyphen.",
        )
    generated_key = Fernet.generate_key().decode("utf-8")
    generated_entry = f"{key_id}:{generated_key}"
    save_config_snapshot_encryption_keys(db, generated_entry)

    raw_keys, source, updated_at = get_effective_config_snapshot_encryption_keys(db)
    write_audit_log(
        db,
        action="config_snapshot_encryption_key_generated",
        target_type="system_settings",
        target_id="config_snapshot_encryption",
        user_id=current_user.id,
        details={
            "source": source,
            "key_id": key_id,
            "replace_existing": payload.replace_existing,
            "reason": payload.reason,
        },
    )
    db.commit()
    return ConfigSnapshotEncryptionKeyGenerateResponse(
        settings=_snapshot_settings_response(raw_keys, source, updated_at),
        generated_entry=generated_entry,
    )

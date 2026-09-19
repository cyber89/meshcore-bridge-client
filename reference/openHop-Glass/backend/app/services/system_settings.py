import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import SystemSetting
from app.services.config_snapshot import normalize_config_snapshot_encryption_keys

MANAGED_MQTT_SETTINGS_KEY = "managed_mqtt_settings"
CONFIG_SNAPSHOT_ENCRYPTION_SETTINGS_KEY = "config_snapshot_encryption"
_MANAGED_MQTT_FIELDS = (
    "mqtt_enabled",
    "mqtt_broker_host",
    "mqtt_broker_port",
    "mqtt_base_topic",
    "mqtt_tls_enabled",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def default_managed_mqtt_settings() -> dict[str, Any]:
    settings = get_settings()
    payload: dict[str, Any] = {
        "mqtt_enabled": True,
        "mqtt_broker_host": settings.mqtt_broker_host,
        "mqtt_broker_port": settings.mqtt_broker_port,
        "mqtt_base_topic": settings.mqtt_base_topic,
        "mqtt_tls_enabled": settings.mqtt_repeater_tls_enabled,
    }
    if settings.mqtt_broker_username:
        payload["mqtt_username"] = settings.mqtt_broker_username
    if settings.mqtt_broker_password:
        payload["mqtt_password"] = settings.mqtt_broker_password
    return payload


def sanitize_managed_mqtt_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    if "mqtt_enabled" in raw:
        sanitized["mqtt_enabled"] = bool(raw["mqtt_enabled"])
    if "mqtt_broker_host" in raw:
        sanitized["mqtt_broker_host"] = str(raw["mqtt_broker_host"] or "").strip()
    if "mqtt_broker_port" in raw:
        try:
            sanitized["mqtt_broker_port"] = int(raw["mqtt_broker_port"])
        except (TypeError, ValueError):
            pass
    if "mqtt_base_topic" in raw:
        sanitized["mqtt_base_topic"] = str(raw["mqtt_base_topic"] or "").strip().strip("/")
    if "mqtt_tls_enabled" in raw:
        sanitized["mqtt_tls_enabled"] = bool(raw["mqtt_tls_enabled"])
    return sanitized


def _load_stored_overrides(db: Session) -> tuple[dict[str, Any], datetime | None]:
    row = db.scalar(
        select(SystemSetting).where(SystemSetting.key == MANAGED_MQTT_SETTINGS_KEY)
    )
    if row is None:
        return {}, None
    try:
        value = json.loads(row.value_json)
    except json.JSONDecodeError:
        return {}, row.updated_at
    if not isinstance(value, dict):
        return {}, row.updated_at
    return sanitize_managed_mqtt_overrides(value), row.updated_at


def _load_stored_snapshot_encryption_keys(
    db: Session,
) -> tuple[str | None, datetime | None]:
    row = db.scalar(
        select(SystemSetting).where(SystemSetting.key == CONFIG_SNAPSHOT_ENCRYPTION_SETTINGS_KEY)
    )
    if row is None:
        return None, None
    try:
        value = json.loads(row.value_json)
    except json.JSONDecodeError:
        return None, row.updated_at
    if not isinstance(value, dict):
        return None, row.updated_at
    raw_keys = value.get("encryption_keys")
    if not isinstance(raw_keys, str):
        return None, row.updated_at
    normalized_keys = normalize_config_snapshot_encryption_keys(raw_keys)
    return normalized_keys or None, row.updated_at


def get_effective_managed_mqtt_settings(
    db: Session,
) -> tuple[dict[str, Any], str, datetime | None]:
    defaults = default_managed_mqtt_settings()
    overrides, updated_at = _load_stored_overrides(db)
    if overrides:
        defaults.update(overrides)
        return defaults, "override", updated_at
    return defaults, "defaults", updated_at


def get_effective_config_snapshot_encryption_keys(
    db: Session,
) -> tuple[str | None, str, datetime | None]:
    override_keys, updated_at = _load_stored_snapshot_encryption_keys(db)
    if override_keys:
        return override_keys, "override", updated_at
    env_keys = normalize_config_snapshot_encryption_keys(
        get_settings().config_snapshot_encryption_keys
    )
    if env_keys:
        return env_keys, "env", updated_at
    return None, "unset", updated_at


def save_managed_mqtt_settings(db: Session, payload: dict[str, Any]) -> SystemSetting:
    sanitized = sanitize_managed_mqtt_overrides(payload)
    existing = db.scalar(
        select(SystemSetting).where(SystemSetting.key == MANAGED_MQTT_SETTINGS_KEY)
    )
    if existing is None:
        existing = SystemSetting(
            key=MANAGED_MQTT_SETTINGS_KEY,
            value_json=json.dumps(sanitized),
            updated_at=_utc_now(),
        )
        db.add(existing)
    else:
        existing.value_json = json.dumps(sanitized)
        existing.updated_at = _utc_now()
    db.flush()
    return existing


def save_config_snapshot_encryption_keys(
    db: Session,
    encryption_keys: str,
) -> SystemSetting:
    normalized_keys = normalize_config_snapshot_encryption_keys(encryption_keys)
    existing = db.scalar(
        select(SystemSetting).where(SystemSetting.key == CONFIG_SNAPSHOT_ENCRYPTION_SETTINGS_KEY)
    )
    payload_json = json.dumps({"encryption_keys": normalized_keys})
    if existing is None:
        existing = SystemSetting(
            key=CONFIG_SNAPSHOT_ENCRYPTION_SETTINGS_KEY,
            value_json=payload_json,
            updated_at=_utc_now(),
        )
        db.add(existing)
    else:
        existing.value_json = payload_json
        existing.updated_at = _utc_now()
    db.flush()
    return existing


def managed_mqtt_view_payload(settings_payload: dict[str, Any]) -> dict[str, Any]:
    return {field: settings_payload.get(field) for field in _MANAGED_MQTT_FIELDS}

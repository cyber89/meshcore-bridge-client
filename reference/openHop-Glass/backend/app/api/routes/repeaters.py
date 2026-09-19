import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Certificate,
    CommandQueueItem,
    InformSnapshot,
    MqttIngestEvent,
    Repeater,
    User,
)
from app.db.session import get_db_session
from app.schemas.repeater import (
    DeleteStaleRepeatersResponse,
    InformSnapshotPointResponse,
    RepeaterCertDiagnosticLogResponse,
    RepeaterCreateRequest,
    RepeaterDetailResponse,
    RepeaterResponse,
    RepeaterUpdateRequest,
)
from app.security.deps import require_roles
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/repeaters")


def _utc_now() -> datetime:
    return datetime.now(UTC)

def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _max_age_seconds_between(now_utc: datetime, event_time: datetime | None) -> int | None:
    normalized = _ensure_utc(event_time)
    if normalized is None:
        return None
    return max(0, int((now_utc - normalized).total_seconds()))


def _parse_json(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None

def _parse_json_object(value: str | None) -> dict[str, Any]:
    parsed = _parse_json(value)
    return parsed or {}

def _settings_expect_mqtt_tls(settings: dict[str, Any] | None) -> bool:
    if not settings:
        return False
    glass_managed = settings.get("glass_managed")
    if isinstance(glass_managed, dict):
        if bool(glass_managed.get("mqtt_enabled", True)) and bool(
            glass_managed.get("mqtt_tls_enabled")
        ):
            return True
    mqtt_settings = settings.get("mqtt")
    if isinstance(mqtt_settings, dict):
        tls = mqtt_settings.get("tls")
        if bool(mqtt_settings.get("enabled")) and isinstance(tls, dict) and bool(
            tls.get("enabled")
        ):
            return True
    return False


def _build_cert_diagnostics(
    db: Session,
    repeater: Repeater,
    settings: dict[str, Any] | None,
    *,
    log_limit: int,
) -> list[RepeaterCertDiagnosticLogResponse]:
    diagnostics: list[RepeaterCertDiagnosticLogResponse] = []
    now = _utc_now()
    last_inform_at_utc = _ensure_utc(repeater.last_inform_at)
    stale_warn_seconds = 10 * 60
    stale_critical_seconds = 30 * 60
    tls_expected = _settings_expect_mqtt_tls(settings)
    if last_inform_at_utc is None:
        if repeater.status in {"connected", "adopted", "offline"}:
            diagnostics.append(
                RepeaterCertDiagnosticLogResponse(
                    timestamp=now,
                    severity="error",
                    source="inform_health_check",
                    message="No inform heartbeat has been received for this managed repeater.",
                    details={"status": repeater.status},
                )
            )
    else:
        age_seconds = _max_age_seconds_between(now, last_inform_at_utc)
        if age_seconds is None:
            age_seconds = 0
        if age_seconds >= stale_warn_seconds:
            severity = "warning"
            if age_seconds >= stale_critical_seconds:
                severity = "error"
            diagnostics.append(
                RepeaterCertDiagnosticLogResponse(
                    timestamp=last_inform_at_utc,
                    severity=severity,
                    source="inform_health_check",
                    message=(
                        f"Last inform heartbeat is stale ({age_seconds}s old). "
                        "Repeater connectivity or control-plane health may be degraded."
                    ),
                    details={
                        "status": repeater.status,
                        "age_seconds": age_seconds,
                        "threshold_seconds": stale_warn_seconds,
                    },
                )
            )

    certificate_rows = db.scalars(
        select(Certificate)
        .where(Certificate.repeater_id == repeater.id)
        .order_by(Certificate.issued_at.desc())
        .limit(max(3, log_limit))
    ).all()
    for cert in certificate_rows:
        issued_at_utc = _ensure_utc(cert.issued_at) or now
        diagnostics.append(
            RepeaterCertDiagnosticLogResponse(
                timestamp=issued_at_utc,
                severity="info",
                source="certificate_issued",
                message=f"Issued client certificate serial {cert.serial[:12]}…",
                details={
                    "serial": cert.serial,
                    "expires_at": cert.expires_at.isoformat().replace("+00:00", "Z"),
                    "revoked_at": cert.revoked_at.isoformat().replace("+00:00", "Z")
                    if cert.revoked_at
                    else None,
                },
            )
        )

    command_rows = db.scalars(
        select(CommandQueueItem)
        .where(CommandQueueItem.repeater_id == repeater.id)
        .order_by(CommandQueueItem.created_at.desc())
        .limit(max(10, log_limit * 2))
    ).all()
    for row in command_rows:
        params = _parse_json_object(row.params_json)
        result = _parse_json_object(row.result_json)
        timestamp = _ensure_utc(row.completed_at) or _ensure_utc(row.created_at) or now
        status = (row.status or "").lower()
        severity = "info"
        if status in {"failed", "error"}:
            severity = "error"
        elif status in {"queued", "dispatched"}:
            severity = "warning"
        message = f"Command '{row.command}' is {row.status}."
        result_message = str(result.get("message", "")).strip()
        if result_message:
            message = f"Command '{row.command}' is {row.status}: {result_message}"
        if row.command == "export_config" and isinstance(result.get("details"), dict):
            change_control = result.get("details", {}).get("change_control")
            if isinstance(change_control, dict):
                if bool(change_control.get("has_changes")):
                    change_count = int(change_control.get("total_change_count") or 0)
                    message = (
                        f"{message} Change control detected {change_count} changed path"
                        f"{'' if change_count == 1 else 's'}."
                    )
                elif bool(change_control.get("is_duplicate_content")):
                    message = f"{message} Change control detected no config differences."
        diagnostics.append(
            RepeaterCertDiagnosticLogResponse(
                timestamp=timestamp,
                severity=severity,
                source="command_queue",
                message=message,
                details={
                    "command_id": row.id,
                    "status": row.status,
                    "requested_by": row.requested_by,
                    "params": _json_safe(params),
                    "result": _json_safe(result),
                },
            )
        )
        if row.command == "export_config":
            request_reason = str(params.get("request_reason") or "").strip()
            requested_by = str(row.requested_by or "unknown")
            request_message = f"Config snapshot backup requested by {requested_by}."
            if request_reason:
                request_message = f"{request_message} Reason: {request_reason}"
            diagnostics.append(
                RepeaterCertDiagnosticLogResponse(
                    timestamp=_ensure_utc(row.created_at) or timestamp,
                    severity="info",
                    source="config_snapshot_request",
                    message=request_message,
                    details={
                        "command_id": row.id,
                        "requested_by": requested_by,
                        "reason": request_reason or None,
                        "status": row.status,
                    },
                )
            )

    latest_mqtt_ingest = db.scalar(
        select(MqttIngestEvent.ingested_at)
        .where(MqttIngestEvent.repeater_id == repeater.id)
        .order_by(MqttIngestEvent.ingested_at.desc())
        .limit(1)
    )
    latest_mqtt_ingest_utc = _ensure_utc(latest_mqtt_ingest)
    latest_mqtt_ingest_age_seconds = _max_age_seconds_between(now, latest_mqtt_ingest_utc)
    if latest_mqtt_ingest_utc is None:
        diagnostics.append(
            RepeaterCertDiagnosticLogResponse(
                timestamp=now,
                severity="warning",
                source="mqtt_ingest_health",
                message="No MQTT telemetry ingest has been recorded for this repeater yet.",
                details={
                    "node_name": repeater.node_name,
                    "status": repeater.status,
                },
            )
        )
    else:
        diagnostics.append(
            RepeaterCertDiagnosticLogResponse(
                timestamp=latest_mqtt_ingest_utc,
                severity="info",
                source="mqtt_ingest_health",
                message=(
                    f"Latest MQTT telemetry ingest is {latest_mqtt_ingest_age_seconds or 0}s old."
                ),
                details={
                    "latest_mqtt_ingest_at": _json_safe(latest_mqtt_ingest_utc),
                    "age_seconds": latest_mqtt_ingest_age_seconds or 0,
                },
            )
        )
    if tls_expected:
        last_inform_age_seconds = _max_age_seconds_between(now, last_inform_at_utc)
        last_inform_stale = (
            last_inform_age_seconds is None or last_inform_age_seconds > stale_warn_seconds
        )
        telemetry_stale = (
            latest_mqtt_ingest_age_seconds is None
            or latest_mqtt_ingest_age_seconds > stale_warn_seconds
        )
        if telemetry_stale:
            diagnostics.append(
                RepeaterCertDiagnosticLogResponse(
                    timestamp=last_inform_at_utc or now,
                    severity="warning" if not last_inform_stale else "error",
                    source="tls_health_check",
                    message=(
                        "MQTT telemetry is stale while TLS is enabled. "
                        "This may indicate certificate trust or mTLS handshake issues."
                    ),
                    details={
                        "last_inform_at": _json_safe(last_inform_at_utc),
                        "latest_mqtt_ingest_at": _json_safe(latest_mqtt_ingest_utc),
                        "tls_expected": True,
                    },
                )
            )

        recent_tls_command = next(
            (
                row
                for row in command_rows
                if row.command == "config_update"
                and isinstance(_parse_json_object(row.params_json).get("config"), dict)
                and isinstance(
                    _parse_json_object(row.params_json).get("config", {}).get("glass_managed"),
                    dict,
                )
                and bool(
                    _parse_json_object(row.params_json)
                    .get("config", {})
                    .get("glass_managed", {})
                    .get("mqtt_tls_enabled")
                )
            ),
            None,
        )
        if recent_tls_command and recent_tls_command.status == "success" and last_inform_stale:
            diagnostics.append(
                RepeaterCertDiagnosticLogResponse(
                    timestamp=_ensure_utc(recent_tls_command.completed_at)
                    or _ensure_utc(recent_tls_command.created_at)
                    or now,
                    severity="error",
                    source="tls_health_check",
                    message=(
                        "Repeater stopped informing after successful TLS configuration update. "
                        "Certificate mismatch/trust issues are likely."
                    ),
                    details={
                        "command_id": recent_tls_command.id,
                        "command_status": recent_tls_command.status,
                        "last_inform_at": _json_safe(last_inform_at_utc),
                    },
                )
            )

    diagnostics.sort(key=lambda item: _ensure_utc(item.timestamp) or now, reverse=True)
    return diagnostics[:log_limit]


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _to_response(repeater: Repeater) -> RepeaterResponse:
    return RepeaterResponse(
        id=repeater.id,
        node_name=repeater.node_name,
        pubkey=repeater.pubkey,
        status=repeater.status,
        firmware_version=repeater.firmware_version,
        location=repeater.location,
        config_hash=repeater.config_hash,
        last_inform_at=repeater.last_inform_at,
        created_at=repeater.created_at,
        updated_at=repeater.updated_at,
    )


def _to_snapshot_point(snapshot: InformSnapshot) -> InformSnapshotPointResponse:
    return InformSnapshotPointResponse(
        timestamp=snapshot.timestamp,
        cpu=snapshot.cpu,
        memory=snapshot.memory,
        disk=snapshot.disk,
        uptime_seconds=snapshot.uptime_seconds,
        noise_floor=snapshot.noise_floor,
        rx_total=snapshot.rx_total,
        tx_total=snapshot.tx_total,
        forwarded=snapshot.forwarded,
        dropped=snapshot.dropped,
        airtime_percent=snapshot.airtime_percent,
    )


def _to_detail_response(
    repeater: Repeater,
    snapshots: list[InformSnapshot],
    *,
    settings: dict[str, Any] | None = None,
    cert_diagnostics: list[RepeaterCertDiagnosticLogResponse] | None = None,
) -> RepeaterDetailResponse:
    parsed_settings = settings if settings is not None else _parse_json(repeater.settings_json)
    return RepeaterDetailResponse(
        id=repeater.id,
        node_name=repeater.node_name,
        pubkey=repeater.pubkey,
        status=repeater.status,
        firmware_version=repeater.firmware_version,
        location=repeater.location,
        config_hash=repeater.config_hash,
        last_inform_at=repeater.last_inform_at,
        created_at=repeater.created_at,
        updated_at=repeater.updated_at,
        state=repeater.state,
        system=_parse_json(repeater.system_json),
        radio=_parse_json(repeater.radio_json),
        counters=_parse_json(repeater.counters_json),
        settings=parsed_settings,
        snapshots=[_to_snapshot_point(item) for item in snapshots],
        cert_diagnostics=cert_diagnostics or [],
    )


@router.get("", response_model=list[RepeaterResponse])
def list_repeaters(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[RepeaterResponse]:
    repeaters = db.scalars(select(Repeater).order_by(Repeater.created_at.desc())).all()
    return [_to_response(item) for item in repeaters]


@router.post("", response_model=RepeaterResponse, status_code=status.HTTP_201_CREATED)
def create_repeater(
    payload: RepeaterCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> RepeaterResponse:
    repeater = Repeater(
        node_name=payload.node_name.strip(),
        pubkey=payload.pubkey.strip(),
        status=payload.status.strip(),
        firmware_version=payload.firmware_version,
        location=payload.location,
    )
    db.add(repeater)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repeater already exists",
        ) from exc

    write_audit_log(
        db,
        action="repeater_created",
        target_type="repeater",
        target_id=repeater.id,
        user_id=current_user.id,
        details={"node_name": repeater.node_name},
    )
    db.commit()
    db.refresh(repeater)
    return _to_response(repeater)


@router.delete("/stale", response_model=DeleteStaleRepeatersResponse)
def delete_stale_repeaters(
    inactive_hours: int = Query(default=168, ge=1, le=24 * 365),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> DeleteStaleRepeatersResponse:
    cutoff = _utc_now() - timedelta(hours=inactive_hours)
    stale_repeaters = db.scalars(
        select(Repeater).where(
            or_(
                Repeater.last_inform_at < cutoff,
                and_(Repeater.last_inform_at.is_(None), Repeater.created_at < cutoff),
            )
        )
    ).all()
    if not stale_repeaters:
        return DeleteStaleRepeatersResponse(removed=0)

    node_names = [item.node_name for item in stale_repeaters]
    for repeater in stale_repeaters:
        db.delete(repeater)
    write_audit_log(
        db,
        action="stale_repeaters_deleted",
        target_type="repeater",
        target_id=None,
        user_id=current_user.id,
        details={"inactive_hours": inactive_hours, "removed_nodes": node_names},
    )
    db.commit()
    return DeleteStaleRepeatersResponse(removed=len(stale_repeaters))


@router.get("/{repeater_id}/detail", response_model=RepeaterDetailResponse)
def get_repeater_detail(
    repeater_id: str,
    snapshot_limit: int = Query(default=240, ge=10, le=1000),
    cert_log_limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> RepeaterDetailResponse:
    repeater = db.scalar(select(Repeater).where(Repeater.id == repeater_id))
    if repeater is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repeater not found",
        )
    snapshots_desc = db.scalars(
        select(InformSnapshot)
        .where(InformSnapshot.repeater_id == repeater.id)
        .order_by(InformSnapshot.timestamp.desc())
        .limit(snapshot_limit)
    ).all()
    snapshots = list(reversed(snapshots_desc))
    settings = _parse_json(repeater.settings_json)
    cert_diagnostics = _build_cert_diagnostics(
        db,
        repeater,
        settings,
        log_limit=cert_log_limit,
    )
    return _to_detail_response(
        repeater,
        snapshots,
        settings=settings,
        cert_diagnostics=cert_diagnostics,
    )


@router.get("/{repeater_id}", response_model=RepeaterResponse)
def get_repeater(
    repeater_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> RepeaterResponse:
    repeater = db.scalar(select(Repeater).where(Repeater.id == repeater_id))
    if repeater is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repeater not found",
        )
    return _to_response(repeater)


@router.patch("/{repeater_id}", response_model=RepeaterResponse)
def update_repeater(
    repeater_id: str,
    payload: RepeaterUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> RepeaterResponse:
    repeater = db.scalar(select(Repeater).where(Repeater.id == repeater_id))
    if repeater is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repeater not found",
        )

    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(repeater, key, value)

    write_audit_log(
        db,
        action="repeater_updated",
        target_type="repeater",
        target_id=repeater.id,
        user_id=current_user.id,
        details={"changes": _json_safe(changes)},
    )
    db.commit()
    db.refresh(repeater)
    return _to_response(repeater)


@router.delete("/{repeater_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repeater(
    repeater_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> Response:
    repeater = db.scalar(select(Repeater).where(Repeater.id == repeater_id))
    if repeater is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repeater not found",
        )
    repeater_node_name = repeater.node_name
    db.delete(repeater)
    write_audit_log(
        db,
        action="repeater_deleted",
        target_type="repeater",
        target_id=repeater_id,
        user_id=current_user.id,
        details={"node_name": repeater_node_name},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

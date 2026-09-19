import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Alert, NotificationEvent


def _utc_now() -> datetime:
    return datetime.now(UTC)


def queue_notification_event(
    db: Session,
    *,
    alert_id: str,
    channel: str,
    event_type: str,
    payload: dict[str, Any],
    integration_id: str | None = None,
    action_template_id: str | None = None,
    binding_id: str | None = None,
    provider_type: str | None = None,
    idempotency_key: str | None = None,
    rendered_payload: dict[str, Any] | None = None,
    response_status_code: int | None = None,
    provider_message_id: str | None = None,
) -> NotificationEvent:
    event = NotificationEvent(
        alert_id=alert_id,
        channel=channel,
        event_type=event_type,
        status="queued",
        attempts=0,
        integration_id=integration_id,
        action_template_id=action_template_id,
        binding_id=binding_id,
        provider_type=provider_type,
        idempotency_key=idempotency_key,
        payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str),
        rendered_payload_json=(
            json.dumps(rendered_payload, separators=(",", ":"), sort_keys=True, default=str)
            if rendered_payload is not None
            else None
        ),
        response_status_code=response_status_code,
        provider_message_id=provider_message_id,
        created_at=_utc_now(),
    )
    db.add(event)
    db.flush()
    return event


def apply_alert_state_transition(
    alert: Alert,
    *,
    new_state: str,
    actor: str | None = None,
    note: str | None = None,
) -> Alert:
    now = _utc_now()
    alert.state = new_state
    alert.last_seen_at = now
    if note is not None:
        alert.note = note

    if new_state == "acknowledged":
        alert.acked_at = now
        alert.acked_by = actor
        alert.resolved_at = None
    elif new_state == "resolved":
        alert.resolved_at = now
    elif new_state == "suppressed":
        if alert.acked_at is None:
            alert.acked_at = now
            alert.acked_by = actor
    elif new_state == "active":
        alert.resolved_at = None
        alert.acked_at = None
        alert.acked_by = None
    return alert

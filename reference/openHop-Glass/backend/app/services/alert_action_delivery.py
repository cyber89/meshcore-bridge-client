from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    AlertActionIntegration,
    AlertActionTemplate,
    AlertPolicyActionBinding,
    AlertPolicyTemplate,
    NotificationEvent,
    Repeater,
)
from app.schemas.alert_actions import (
    VALID_ALERT_ACTION_EVENT_TYPES,
    VALID_ALERT_ACTION_SEVERITIES,
)
from app.services.alert_action_templating import render_template_text, render_template_value
from app.services.alert_actions import (
    parse_action_template_default_events,
    parse_action_template_payload,
    parse_binding_event_types,
    parse_integration_settings,
)
from app.services.alerts import queue_notification_event
from app.services.notification_providers.base import NotificationSendRequest
from app.services.notification_providers.registry import NotificationProviderRegistry

logger = logging.getLogger("alert-action-delivery")

ALERT_SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3}
ALERT_TYPE_RULE_MAP = {
    "repeater_offline": "offline_repeater",
    "mqtt_tls_health": "tls_telemetry_stale",
    "high_noise_floor": "high_noise_floor",
    "high_cpu_usage": "high_cpu_percent",
    "high_memory_usage": "high_memory_percent",
    "high_disk_usage": "high_disk_percent",
    "high_temperature": "high_temperature_c",
    "high_airtime_usage": "high_airtime_percent",
    "high_drop_rate": "high_drop_rate",
    "new_zero_hop_node_detected": "new_zero_hop_node_detected",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_rule_type_from_alert(alert: Alert) -> str | None:
    if alert.fingerprint and ":" in alert.fingerprint:
        candidate = alert.fingerprint.split(":", maxsplit=1)[1].strip()
        if candidate:
            return candidate
    return ALERT_TYPE_RULE_MAP.get(alert.alert_type)


def _severity_meets_minimum(*, alert_severity: str, min_severity: str | None) -> bool:
    if min_severity is None:
        return True
    alert_rank = ALERT_SEVERITY_RANK.get(alert_severity.strip().lower())
    min_rank = ALERT_SEVERITY_RANK.get(min_severity.strip().lower())
    if alert_rank is None or min_rank is None:
        return True
    return alert_rank >= min_rank


def _binding_event_types(
    binding: AlertPolicyActionBinding,
    action_template: AlertActionTemplate,
) -> list[str]:
    binding_events = parse_binding_event_types(binding)
    if binding_events:
        return binding_events
    template_events = parse_action_template_default_events(action_template)
    if template_events:
        return template_events
    return sorted(VALID_ALERT_ACTION_EVENT_TYPES)


def _format_event_label(event_type: str) -> str:
    return event_type.replace("_", " ").strip().title()


def _build_render_context(
    *,
    alert: Alert,
    repeater: Repeater | None,
    policy_template: AlertPolicyTemplate,
    event_type: str,
    actor: str | None,
    note: str | None,
    occurred_at: datetime,
) -> dict[str, Any]:
    return {
        "alert": {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "state": alert.state,
            "fingerprint": alert.fingerprint,
            "first_seen_at": alert.first_seen_at,
            "last_seen_at": alert.last_seen_at,
            "acked_at": alert.acked_at,
            "resolved_at": alert.resolved_at,
            "note": alert.note,
        },
        "repeater": {
            "id": repeater.id if repeater else alert.repeater_id,
            "node_name": repeater.node_name if repeater else None,
            "pubkey": repeater.pubkey if repeater else None,
            "status": repeater.status if repeater else None,
            "location": repeater.location if repeater else None,
        },
        "policy": {
            "id": policy_template.id,
            "name": policy_template.name,
            "rule_type": policy_template.rule_type,
            "severity": policy_template.severity,
        },
        "event": {
            "type": event_type,
            "label": _format_event_label(event_type),
            "actor": actor,
            "note": note,
            "occurred_at": occurred_at,
        },
    }


def build_alert_action_context(
    *,
    alert: Alert,
    repeater: Repeater | None,
    policy_template: AlertPolicyTemplate,
    event_type: str,
    actor: str | None = None,
    note: str | None = None,
    occurred_at: datetime | None = None,
    sample_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = _build_render_context(
        alert=alert,
        repeater=repeater,
        policy_template=policy_template,
        event_type=event_type,
        actor=actor,
        note=note,
        occurred_at=occurred_at or _utc_now(),
    )
    if sample_context:
        context.update(sample_context)
    return context


def _render_action_payload(
    *,
    action_template: AlertActionTemplate,
    context: dict[str, Any],
    event_type: str,
) -> dict[str, Any]:
    title = render_template_text(action_template.title_template, context)
    body = render_template_text(action_template.body_template, context)
    payload_template = parse_action_template_payload(action_template)
    rendered_payload_value = (
        render_template_value(payload_template, context)
        if payload_template is not None
        else {}
    )
    rendered_payload: dict[str, Any]
    if isinstance(rendered_payload_value, dict):
        rendered_payload = dict(rendered_payload_value)
    else:
        rendered_payload = {"value": rendered_payload_value}
    if title and "title" not in rendered_payload:
        rendered_payload["title"] = title
    if body and "body" not in rendered_payload:
        rendered_payload["body"] = body
    if not rendered_payload:
        rendered_payload = {
            "event_type": event_type,
            "event_label": _format_event_label(event_type),
            "alert_id": context["alert"]["id"],
            "message": context["alert"]["message"],
            "severity": context["alert"]["severity"],
        }
    rendered_payload.setdefault("event_type", event_type)
    rendered_payload.setdefault("event_label", _format_event_label(event_type))
    return rendered_payload


def render_action_template_preview(
    *,
    title_template: str | None,
    body_template: str | None,
    payload_template: dict[str, Any] | None,
    event_type: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    title = render_template_text(title_template, context)
    body = render_template_text(body_template, context)
    rendered_payload_value = (
        render_template_value(payload_template, context)
        if payload_template is not None
        else {}
    )
    payload: dict[str, Any]
    if isinstance(rendered_payload_value, dict):
        payload = dict(rendered_payload_value)
    else:
        payload = {"value": rendered_payload_value}
    if title and "title" not in payload:
        payload["title"] = title
    if body and "body" not in payload:
        payload["body"] = body
    if not payload:
        payload = {"event_type": event_type, "event_label": _format_event_label(event_type)}
    payload.setdefault("event_type", event_type)
    payload.setdefault("event_label", _format_event_label(event_type))
    return {"title": title, "body": body, "payload": payload}


def _event_cooldown_active(
    db: Session,
    *,
    binding_id: str,
    event_type: str,
    cooldown_seconds: int,
    now: datetime,
) -> bool:
    if cooldown_seconds <= 0:
        return False
    recent_created_at = db.scalar(
        select(NotificationEvent.created_at)
        .where(
            NotificationEvent.binding_id == binding_id,
            NotificationEvent.channel == "action",
            NotificationEvent.event_type == event_type,
        )
        .order_by(NotificationEvent.created_at.desc())
        .limit(1)
    )
    if recent_created_at is None:
        return False
    return (now - recent_created_at).total_seconds() < cooldown_seconds


def resolve_policy_template_for_alert(
    db: Session,
    *,
    alert: Alert,
) -> AlertPolicyTemplate | None:
    rule_type = _parse_rule_type_from_alert(alert)
    if not rule_type:
        return None
    return db.scalar(
        select(AlertPolicyTemplate)
        .where(
            AlertPolicyTemplate.rule_type == rule_type,
            AlertPolicyTemplate.severity.in_(VALID_ALERT_ACTION_SEVERITIES),
        )
        .order_by(AlertPolicyTemplate.enabled.desc(), AlertPolicyTemplate.updated_at.desc())
        .limit(1)
    )


def enqueue_policy_action_notifications(
    db: Session,
    *,
    alert: Alert,
    repeater: Repeater | None,
    policy_template: AlertPolicyTemplate,
    event_type: str,
    transition_key: str,
    actor: str | None = None,
    note: str | None = None,
) -> int:
    normalized_event_type = event_type.strip().lower()
    if normalized_event_type not in VALID_ALERT_ACTION_EVENT_TYPES:
        return 0
    now = _utc_now()
    bindings = db.scalars(
        select(AlertPolicyActionBinding)
        .where(
            AlertPolicyActionBinding.policy_template_id == policy_template.id,
            AlertPolicyActionBinding.enabled == 1,
        )
        .order_by(
            AlertPolicyActionBinding.sort_order.asc(),
            AlertPolicyActionBinding.created_at.asc(),
        )
    ).all()
    queued_count = 0
    for binding in bindings:
        integration = db.scalar(
            select(AlertActionIntegration).where(
                AlertActionIntegration.id == binding.integration_id
            )
        )
        action_template = db.scalar(
            select(AlertActionTemplate).where(
                AlertActionTemplate.id == binding.action_template_id
            )
        )
        if integration is None or action_template is None:
            continue
        if integration.enabled != 1 or action_template.enabled != 1:
            continue
        if not _severity_meets_minimum(
            alert_severity=alert.severity,
            min_severity=binding.min_severity,
        ):
            continue
        supported_event_types = _binding_event_types(binding, action_template)
        if normalized_event_type not in supported_event_types:
            continue
        if _event_cooldown_active(
            db,
            binding_id=binding.id,
            event_type=normalized_event_type,
            cooldown_seconds=binding.cooldown_seconds,
            now=now,
        ):
            continue
        idempotency_key = (
            f"{alert.id}:{binding.id}:{normalized_event_type}:{transition_key.strip()}"
        )
        existing = db.scalar(
            select(NotificationEvent.id).where(
                NotificationEvent.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            continue
        try:
            context = _build_render_context(
                alert=alert,
                repeater=repeater,
                policy_template=policy_template,
                event_type=normalized_event_type,
                actor=actor,
                note=note,
                occurred_at=now,
            )
            rendered_payload = _render_action_payload(
                action_template=action_template,
                context=context,
                event_type=normalized_event_type,
            )
        except KeyError as exc:
            missing_token = str(exc).strip("'")
            event = queue_notification_event(
                db,
                alert_id=alert.id,
                channel="action",
                event_type=normalized_event_type,
                payload={
                    "alert_id": alert.id,
                    "event_type": normalized_event_type,
                    "binding_id": binding.id,
                },
                integration_id=integration.id,
                action_template_id=action_template.id,
                binding_id=binding.id,
                provider_type=integration.provider_type,
                idempotency_key=idempotency_key,
                rendered_payload={
                    "template_error": f"Missing template variable: {missing_token}"
                },
            )
            event.status = "failed"
            event.last_error = f"Template rendering failed: missing variable '{missing_token}'"
            event.next_attempt_at = None
            logger.warning(
                "Alert action template rendering failed for binding %s: missing %s",
                binding.id,
                missing_token,
            )
            continue
        queue_notification_event(
            db,
            alert_id=alert.id,
            channel="action",
            event_type=normalized_event_type,
            payload={
                "alert_id": alert.id,
                "event_type": normalized_event_type,
                "binding_id": binding.id,
                "policy_template_id": policy_template.id,
                "policy_template_name": policy_template.name,
                "integration_id": integration.id,
                "integration_name": integration.name,
                "action_template_id": action_template.id,
                "action_template_name": action_template.name,
                "actor": actor,
                "note": note,
            },
            integration_id=integration.id,
            action_template_id=action_template.id,
            binding_id=binding.id,
            provider_type=integration.provider_type,
            idempotency_key=idempotency_key,
            rendered_payload=rendered_payload,
        )
        queued_count += 1
    return queued_count


def enqueue_alert_lifecycle_action_notifications(
    db: Session,
    *,
    alert: Alert,
    repeater: Repeater | None,
    event_type: str,
    transition_key: str,
    actor: str | None = None,
    note: str | None = None,
) -> int:
    policy_template = resolve_policy_template_for_alert(db, alert=alert)
    if policy_template is None:
        return 0
    return enqueue_policy_action_notifications(
        db,
        alert=alert,
        repeater=repeater,
        policy_template=policy_template,
        event_type=event_type,
        transition_key=transition_key,
        actor=actor,
        note=note,
    )


def _apply_dispatch_success(
    event: NotificationEvent,
    *,
    attempts: int,
    now: datetime,
    status_code: int | None,
    provider_message_id: str | None,
) -> None:
    event.status = "sent"
    event.attempts = attempts
    event.last_error = None
    event.next_attempt_at = None
    event.sent_at = now
    event.response_status_code = status_code
    event.provider_message_id = provider_message_id


def _apply_dispatch_failure(
    event: NotificationEvent,
    *,
    attempts: int,
    max_attempts: int,
    backoff_seconds: int,
    now: datetime,
    error_message: str,
    status_code: int | None = None,
    provider_message_id: str | None = None,
) -> None:
    event.attempts = attempts
    event.last_error = error_message
    event.response_status_code = status_code
    event.provider_message_id = provider_message_id
    if attempts >= max_attempts:
        event.status = "failed"
        event.next_attempt_at = None
        return
    delay = max(1, backoff_seconds) * (2 ** max(0, attempts - 1))
    delay = min(delay, 3600)
    event.status = "queued"
    event.next_attempt_at = now + timedelta(seconds=delay)


def run_action_dispatch_batch(
    db: Session,
    *,
    registry: NotificationProviderRegistry,
    batch_size: int,
    max_attempts: int,
    backoff_seconds: int,
) -> int:
    now = _utc_now()
    events = db.scalars(
        select(NotificationEvent)
        .where(
            NotificationEvent.channel == "action",
            NotificationEvent.status == "queued",
            or_(
                NotificationEvent.next_attempt_at.is_(None),
                NotificationEvent.next_attempt_at <= now,
            ),
        )
        .order_by(NotificationEvent.created_at.asc())
        .limit(max(1, batch_size))
    ).all()
    processed = 0
    for event in events:
        processed += 1
        attempts = int(event.attempts) + 1
        integration = None
        if event.integration_id:
            integration = db.scalar(
                select(AlertActionIntegration).where(
                    AlertActionIntegration.id == event.integration_id
                )
            )
        if integration is None:
            _apply_dispatch_failure(
                event,
                attempts=attempts,
                max_attempts=max_attempts,
                backoff_seconds=backoff_seconds,
                now=now,
                error_message="Referenced alert action integration no longer exists",
            )
            continue
        if integration.enabled != 1:
            _apply_dispatch_failure(
                event,
                attempts=attempts,
                max_attempts=max_attempts,
                backoff_seconds=backoff_seconds,
                now=now,
                error_message="Integration is disabled",
            )
            continue
        try:
            settings = parse_integration_settings(integration)
            payload = _parse_json_dict(event.payload_json)
            rendered_payload = _parse_json_dict(event.rendered_payload_json) or None
            send_result = registry.send(
                provider_type=integration.provider_type,
                settings=settings,
                request=NotificationSendRequest(
                    event_type=event.event_type,
                    payload=payload,
                    rendered_payload=rendered_payload,
                ),
            )
        except Exception as exc:
            logger.exception(
                "Action dispatch failed for event %s before provider response",
                event.id,
            )
            _apply_dispatch_failure(
                event,
                attempts=attempts,
                max_attempts=max_attempts,
                backoff_seconds=backoff_seconds,
                now=now,
                error_message=f"Dispatch exception: {exc}",
            )
            continue
        if send_result.is_success:
            _apply_dispatch_success(
                event,
                attempts=attempts,
                now=now,
                status_code=send_result.status_code,
                provider_message_id=send_result.provider_message_id,
            )
            continue
        failure_message = send_result.error or "Provider returned failure"
        _apply_dispatch_failure(
            event,
            attempts=attempts,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
            now=now,
            error_message=failure_message,
            status_code=send_result.status_code,
            provider_message_id=send_result.provider_message_id,
        )
    return processed


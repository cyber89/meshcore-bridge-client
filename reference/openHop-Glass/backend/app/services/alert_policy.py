from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    AlertPolicyAssignment,
    AlertPolicyTemplate,
    CommandQueueItem,
    InformSnapshot,
    MqttIngestEvent,
    NodeGroup,
    NodeGroupMembership,
    Repeater,
    TopologyNode,
    TopologyObservation,
)
from app.services.alert_action_delivery import enqueue_policy_action_notifications
from app.services.alerts import apply_alert_state_transition, queue_notification_event

POLICY_SCOPE_RANK = {"global": 1, "group": 2, "node": 3}
SUPPORTED_RULE_TYPES = {
    "offline_repeater",
    "tls_telemetry_stale",
    "high_noise_floor",
    "high_cpu_percent",
    "high_memory_percent",
    "high_disk_percent",
    "high_temperature_c",
    "high_airtime_percent",
    "high_drop_rate",
    "new_zero_hop_node_detected",
}

WINDOWED_SNAPSHOT_RULES: dict[str, dict[str, Any]] = {
    "high_noise_floor": {
        "column": "noise_floor",
        "threshold_default": -95.0,
        "window_minutes_default": 10,
        "unit": "dBm",
    },
    "high_cpu_percent": {
        "column": "cpu",
        "threshold_default": 90.0,
        "window_minutes_default": 10,
        "unit": "%",
    },
    "high_memory_percent": {
        "column": "memory",
        "threshold_default": 90.0,
        "window_minutes_default": 10,
        "unit": "%",
    },
    "high_disk_percent": {
        "column": "disk",
        "threshold_default": 90.0,
        "window_minutes_default": 30,
        "unit": "%",
    },
    "high_airtime_percent": {
        "column": "airtime_percent",
        "threshold_default": 80.0,
        "window_minutes_default": 10,
        "unit": "%",
    },
}


@dataclass
class EffectivePolicyItem:
    template: AlertPolicyTemplate
    assignment: AlertPolicyAssignment
    scope_name: str | None


@dataclass
class PolicyEvaluationSummary:
    evaluated_repeaters: int = 0
    alerts_activated: int = 0
    alerts_resolved: int = 0


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_config(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _settings_expect_mqtt_tls(settings: dict[str, Any]) -> bool:
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


def _is_tls_enable_config_update(params_json: str | None) -> bool:
    params = _parse_config(params_json)
    config = params.get("config")
    if not isinstance(config, dict):
        return False
    glass_managed = config.get("glass_managed")
    if isinstance(glass_managed, dict) and bool(glass_managed.get("mqtt_tls_enabled")):
        return True
    mqtt_settings = config.get("mqtt")
    if isinstance(mqtt_settings, dict):
        tls = mqtt_settings.get("tls")
        if isinstance(tls, dict) and bool(tls.get("enabled")):
            return True
    return False


def _parse_system_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def list_effective_policies_for_repeater(
    db: Session,
    repeater: Repeater,
) -> list[EffectivePolicyItem]:
    membership_rows = db.scalars(
        select(NodeGroupMembership).where(NodeGroupMembership.repeater_id == repeater.id)
    ).all()
    group_ids = [membership.group_id for membership in membership_rows]

    filters = [
        and_(AlertPolicyAssignment.scope_type == "global", AlertPolicyAssignment.scope_id.is_(None)),
        and_(
            AlertPolicyAssignment.scope_type == "node",
            AlertPolicyAssignment.scope_id == repeater.id,
        ),
    ]
    if group_ids:
        filters.append(
            and_(
                AlertPolicyAssignment.scope_type == "group",
                AlertPolicyAssignment.scope_id.in_(group_ids),
            )
        )
    rows = db.execute(
        select(AlertPolicyAssignment, AlertPolicyTemplate)
        .join(AlertPolicyTemplate, AlertPolicyTemplate.id == AlertPolicyAssignment.template_id)
        .where(AlertPolicyAssignment.enabled == 1, AlertPolicyTemplate.enabled == 1, or_(*filters))
    ).all()

    group_names = {
        group.id: group.name
        for group in db.scalars(select(NodeGroup).where(NodeGroup.id.in_(group_ids))).all()
    }

    resolved: dict[str, EffectivePolicyItem] = {}
    for assignment, template in rows:
        if template.rule_type not in SUPPORTED_RULE_TYPES:
            continue
        scope_name = None
        if assignment.scope_type == "global":
            scope_name = "Global"
        elif assignment.scope_type == "group":
            scope_name = group_names.get(assignment.scope_id or "", assignment.scope_id)
        elif assignment.scope_type == "node":
            scope_name = repeater.node_name

        candidate = EffectivePolicyItem(
            template=template,
            assignment=assignment,
            scope_name=scope_name,
        )
        existing = resolved.get(template.rule_type)
        if existing is None:
            resolved[template.rule_type] = candidate
            continue

        existing_rank = (
            POLICY_SCOPE_RANK.get(existing.assignment.scope_type, 0),
            existing.assignment.priority,
            existing.assignment.updated_at,
        )
        candidate_rank = (
            POLICY_SCOPE_RANK.get(candidate.assignment.scope_type, 0),
            candidate.assignment.priority,
            candidate.assignment.updated_at,
        )
        if candidate_rank > existing_rank:
            resolved[template.rule_type] = candidate

    return sorted(resolved.values(), key=lambda item: item.template.rule_type)


def evaluate_policies_for_repeater(
    db: Session,
    repeater: Repeater,
    *,
    now: datetime | None = None,
) -> PolicyEvaluationSummary:
    summary = PolicyEvaluationSummary(evaluated_repeaters=1)
    evaluation_now = _normalize_datetime(now) or _utc_now()
    policy_map = {
        item.template.rule_type: item for item in list_effective_policies_for_repeater(db, repeater)
    }

    offline_policy = policy_map.get("offline_repeater")
    if offline_policy:
        should_alert, message = _evaluate_offline_policy(repeater, offline_policy, evaluation_now)
        if should_alert:
            summary.alerts_activated += int(
                _activate_or_refresh_alert(
                    db,
                    repeater=repeater,
                    policy=offline_policy,
                    now=evaluation_now,
                    message=message,
                )
            )
        elif offline_policy.template.auto_resolve == 1:
            summary.alerts_resolved += int(
                _resolve_alert_if_open(
                    db,
                    repeater=repeater,
                    rule_type="offline_repeater",
                    now=evaluation_now,
                    note="Auto-resolved: repeater resumed inform heartbeat",
                )
            )

    for rule_type, policy in policy_map.items():
        if rule_type == "offline_repeater":
            continue
        if rule_type == "tls_telemetry_stale":
            should_alert, message = _evaluate_tls_telemetry_stale_policy(
                db=db,
                repeater=repeater,
                policy=policy,
                now=evaluation_now,
            )
        elif rule_type in WINDOWED_SNAPSHOT_RULES:
            should_alert, message = _evaluate_windowed_snapshot_rule(
                db=db,
                repeater=repeater,
                policy=policy,
                now=evaluation_now,
            )
        elif rule_type == "high_temperature_c":
            should_alert, message = _evaluate_temperature_policy(repeater, policy)
        elif rule_type == "high_drop_rate":
            should_alert, message = _evaluate_drop_rate_policy(
                db=db,
                repeater=repeater,
                policy=policy,
                now=evaluation_now,
            )
        elif rule_type == "new_zero_hop_node_detected":
            should_alert, message = _evaluate_new_zero_hop_node_policy(
                db=db,
                repeater=repeater,
                policy=policy,
                now=evaluation_now,
            )
        else:
            continue

        if should_alert:
            summary.alerts_activated += int(
                _activate_or_refresh_alert(
                    db,
                    repeater=repeater,
                    policy=policy,
                    now=evaluation_now,
                    message=message,
                )
            )
        elif policy.template.auto_resolve == 1:
            summary.alerts_resolved += int(
                _resolve_alert_if_open(
                    db,
                    repeater=repeater,
                    rule_type=rule_type,
                    now=evaluation_now,
                    note=f"Auto-resolved: {rule_type} condition returned to normal",
                )
            )

    return summary


def evaluate_policies_for_fleet(
    db: Session,
    *,
    repeater_id: str | None = None,
    now: datetime | None = None,
) -> PolicyEvaluationSummary:
    summary = PolicyEvaluationSummary()
    evaluation_now = _normalize_datetime(now) or _utc_now()

    query = select(Repeater)
    if repeater_id:
        query = query.where(Repeater.id == repeater_id)
    else:
        query = query.where(Repeater.status.in_(["adopted", "connected", "offline"]))

    repeaters = db.scalars(query).all()
    for repeater in repeaters:
        repeater_summary = evaluate_policies_for_repeater(db, repeater, now=evaluation_now)
        summary.evaluated_repeaters += repeater_summary.evaluated_repeaters
        summary.alerts_activated += repeater_summary.alerts_activated
        summary.alerts_resolved += repeater_summary.alerts_resolved

    return summary


def _evaluate_offline_policy(
    repeater: Repeater,
    policy: EffectivePolicyItem,
    now: datetime,
) -> tuple[bool, str]:
    grace_seconds = policy.template.offline_grace_seconds or 120
    if repeater.last_inform_at is None:
        return (
            True,
            f"Repeater has not reported inform data for at least {grace_seconds} seconds.",
        )
    last_inform_at = _normalize_datetime(repeater.last_inform_at)
    assert last_inform_at is not None
    age_seconds = (now - last_inform_at).total_seconds()
    if age_seconds > grace_seconds:
        return (
            True,
            (
                f"Repeater inform heartbeat is stale ({int(age_seconds)}s old), "
                f"exceeding {grace_seconds}s threshold."
            ),
        )
    return (False, "Repeater inform heartbeat is within the configured threshold.")


def _evaluate_windowed_snapshot_rule(
    db: Session,
    repeater: Repeater,
    policy: EffectivePolicyItem,
    now: datetime,
) -> tuple[bool, str]:
    rule_type = policy.template.rule_type
    rule_cfg = WINDOWED_SNAPSHOT_RULES[rule_type]
    metric_column_name = str(rule_cfg["column"])
    metric_column = getattr(InformSnapshot, metric_column_name)
    window_minutes = policy.template.window_minutes or int(rule_cfg["window_minutes_default"])
    threshold = (
        policy.template.threshold_value
        if policy.template.threshold_value is not None
        else float(rule_cfg["threshold_default"])
    )
    unit = str(rule_cfg["unit"])
    window_start = now - timedelta(minutes=window_minutes)
    rows = db.execute(
        select(metric_column)
        .where(
            InformSnapshot.repeater_id == repeater.id,
            InformSnapshot.timestamp >= window_start,
            metric_column.is_not(None),
        )
        .order_by(InformSnapshot.timestamp.desc())
    ).all()
    values = [float(row[0]) for row in rows if row[0] is not None]
    if not values:
        return (False, f"No {metric_column_name} samples available in policy window.")
    average_value = sum(values) / len(values)
    should_alert = average_value >= threshold
    message = (
        f"Average {metric_column_name} {average_value:.1f}{unit} over {window_minutes}m "
        f"(threshold {threshold:.1f}{unit}, samples={len(values)})."
    )
    return should_alert, message


def _evaluate_tls_telemetry_stale_policy(
    db: Session,
    repeater: Repeater,
    policy: EffectivePolicyItem,
    now: datetime,
) -> tuple[bool, str]:
    settings = _parse_config(repeater.settings_json)
    if not _settings_expect_mqtt_tls(settings):
        return (False, "TLS telemetry health check skipped: repeater settings do not require MQTT TLS.")

    grace_seconds = policy.template.offline_grace_seconds or 600
    last_inform_at = _normalize_datetime(repeater.last_inform_at)
    if last_inform_at is None:
        return (False, "TLS telemetry health check skipped: no inform heartbeat recorded yet.")

    inform_age_seconds = int((now - last_inform_at).total_seconds())
    if inform_age_seconds <= grace_seconds:
        return (
            False,
            (
                f"Inform heartbeat age ({inform_age_seconds}s) is within "
                f"TLS telemetry grace window ({grace_seconds}s)."
            ),
        )

    latest_ingest = db.scalar(
        select(MqttIngestEvent.ingested_at)
        .where(MqttIngestEvent.repeater_id == repeater.id)
        .order_by(MqttIngestEvent.ingested_at.desc())
        .limit(1)
    )
    latest_ingest_at = _normalize_datetime(latest_ingest)
    telemetry_age_seconds: int | None = None
    if latest_ingest_at is not None:
        telemetry_age_seconds = int((now - latest_ingest_at).total_seconds())
        if telemetry_age_seconds <= grace_seconds:
            return (
                False,
                (
                    f"MQTT telemetry age ({telemetry_age_seconds}s) is within "
                    f"TLS telemetry grace window ({grace_seconds}s)."
                ),
            )

    recent_tls_command = next(
        (
            row
            for row in db.scalars(
                select(CommandQueueItem)
                .where(
                    CommandQueueItem.repeater_id == repeater.id,
                    CommandQueueItem.command == "config_update",
                    CommandQueueItem.status == "success",
                )
                .order_by(CommandQueueItem.completed_at.desc(), CommandQueueItem.created_at.desc())
                .limit(20)
            ).all()
            if _is_tls_enable_config_update(row.params_json)
        ),
        None,
    )
    if recent_tls_command is not None:
        return (
            True,
            (
                f"Inform heartbeat is stale ({inform_age_seconds}s old) and MQTT telemetry is stale "
                f"({telemetry_age_seconds}s old) after successful TLS configuration update; "
                "certificate trust or mTLS handshake mismatch is likely."
            )
            if telemetry_age_seconds is not None
            else (
                f"Inform heartbeat is stale ({inform_age_seconds}s old) and no MQTT telemetry has been "
                "ingested after successful TLS configuration update; certificate trust or mTLS "
                "handshake mismatch is likely."
            ),
        )

    return (
        True,
        (
            f"Inform heartbeat is stale ({inform_age_seconds}s old) and MQTT telemetry is stale "
            f"({telemetry_age_seconds}s old) while TLS is enabled; investigate certificate and broker trust."
        )
        if telemetry_age_seconds is not None
        else (
            f"Inform heartbeat is stale ({inform_age_seconds}s old) and no MQTT telemetry has been "
            "ingested while TLS is enabled; investigate certificate and broker trust."
        ),
    )


def _evaluate_temperature_policy(
    repeater: Repeater,
    policy: EffectivePolicyItem,
) -> tuple[bool, str]:
    threshold = policy.template.threshold_value if policy.template.threshold_value is not None else 80.0
    system_payload = _parse_system_json(repeater.system_json)
    raw_temperature = system_payload.get("temperature_c")
    if raw_temperature is None:
        return (False, "No temperature_c value available in repeater system payload.")
    try:
        temperature = float(raw_temperature)
    except (TypeError, ValueError):
        return (False, "Temperature value in repeater system payload is invalid.")
    should_alert = temperature >= threshold
    message = f"System temperature {temperature:.1f}°C (threshold {threshold:.1f}°C)."
    return should_alert, message


def _evaluate_drop_rate_policy(
    db: Session,
    repeater: Repeater,
    policy: EffectivePolicyItem,
    now: datetime,
) -> tuple[bool, str]:
    window_minutes = policy.template.window_minutes or 15
    threshold = policy.template.threshold_value if policy.template.threshold_value is not None else 0.05
    window_start = now - timedelta(minutes=window_minutes)
    rows = db.execute(
        select(InformSnapshot.timestamp, InformSnapshot.rx_total, InformSnapshot.tx_total, InformSnapshot.dropped)
        .where(
            InformSnapshot.repeater_id == repeater.id,
            InformSnapshot.timestamp >= window_start,
            InformSnapshot.rx_total.is_not(None),
            InformSnapshot.tx_total.is_not(None),
            InformSnapshot.dropped.is_not(None),
        )
        .order_by(InformSnapshot.timestamp.asc())
    ).all()
    if len(rows) < 2:
        return (False, "Need at least two snapshot points to evaluate drop rate.")

    first = rows[0]
    last = rows[-1]
    rx_delta = max(0, int(last[1]) - int(first[1]))
    tx_delta = max(0, int(last[2]) - int(first[2]))
    dropped_delta = max(0, int(last[3]) - int(first[3]))
    traffic_delta = rx_delta + tx_delta
    if traffic_delta <= 0:
        return (False, "No RX/TX counter movement in drop-rate policy window.")
    drop_rate = dropped_delta / traffic_delta
    should_alert = drop_rate >= threshold
    message = (
        f"Drop rate {drop_rate * 100:.2f}% over {window_minutes}m "
        f"(threshold {threshold * 100:.2f}%, dropped_delta={dropped_delta}, traffic_delta={traffic_delta})."
    )
    return should_alert, message


def _evaluate_new_zero_hop_node_policy(
    db: Session,
    repeater: Repeater,
    policy: EffectivePolicyItem,
    now: datetime,
) -> tuple[bool, str]:
    window_minutes = policy.template.window_minutes or 60
    window_start = now - timedelta(minutes=window_minutes)
    rows = db.execute(
        select(
            TopologyNode.node_name,
            TopologyNode.pubkey,
            TopologyNode.first_seen_at,
            TopologyObservation.last_seen_at,
        )
        .join(TopologyNode, TopologyNode.id == TopologyObservation.observed_node_id)
        .where(
            TopologyObservation.observer_repeater_id == repeater.id,
            TopologyObservation.zero_hop == 1,
            TopologyNode.first_seen_at.is_not(None),
            TopologyNode.first_seen_at >= window_start,
            TopologyObservation.last_seen_at >= window_start,
        )
        .order_by(TopologyNode.first_seen_at.desc())
    ).all()
    if not rows:
        return (
            False,
            (
                f"No newly discovered zero-hop nodes observed by {repeater.node_name} "
                f"in the last {window_minutes}m."
            ),
        )

    node_labels = [
        (str(node_name).strip() if node_name else str(pubkey).strip())
        for node_name, pubkey, _, _ in rows
    ]
    unique_node_labels = list(dict.fromkeys(label for label in node_labels if label))
    preview_labels = unique_node_labels[:5]
    suffix = "…" if len(unique_node_labels) > len(preview_labels) else ""
    message = (
        f"Detected {len(unique_node_labels)} newly discovered zero-hop node(s) in the last "
        f"{window_minutes}m: {', '.join(preview_labels)}{suffix}"
    )
    return True, message


def _alert_fingerprint(repeater_id: str, rule_type: str) -> str:
    return f"{repeater_id}:{rule_type}"


def _alert_type_for_rule(rule_type: str) -> str:
    if rule_type == "offline_repeater":
        return "repeater_offline"
    if rule_type == "tls_telemetry_stale":
        return "mqtt_tls_health"
    if rule_type == "high_noise_floor":
        return "high_noise_floor"
    if rule_type == "high_cpu_percent":
        return "high_cpu_usage"
    if rule_type == "high_memory_percent":
        return "high_memory_usage"
    if rule_type == "high_disk_percent":
        return "high_disk_usage"
    if rule_type == "high_temperature_c":
        return "high_temperature"
    if rule_type == "high_airtime_percent":
        return "high_airtime_usage"
    if rule_type == "high_drop_rate":
        return "high_drop_rate"
    if rule_type == "new_zero_hop_node_detected":
        return "new_zero_hop_node_detected"
    return rule_type


def _activate_or_refresh_alert(
    db: Session,
    *,
    repeater: Repeater,
    policy: EffectivePolicyItem,
    now: datetime,
    message: str,
) -> bool:
    fingerprint = _alert_fingerprint(repeater.id, policy.template.rule_type)
    alert = db.scalar(
        select(Alert)
        .where(Alert.fingerprint == fingerprint)
        .order_by(Alert.last_seen_at.desc(), Alert.timestamp.desc())
    )
    if alert is None:
        alert = Alert(
            repeater_id=repeater.id,
            timestamp=now,
            alert_type=_alert_type_for_rule(policy.template.rule_type),
            severity=policy.template.severity,
            message=message,
            state="active",
            first_seen_at=now,
            last_seen_at=now,
            fingerprint=fingerprint,
        )
        db.add(alert)
        db.flush()
        queue_notification_event(
            db,
            alert_id=alert.id,
            channel="internal",
            event_type="alert_activated",
            payload={
                "alert_id": alert.id,
                "fingerprint": fingerprint,
                "rule_type": policy.template.rule_type,
                "severity": policy.template.severity,
                "message": message,
            },
        )
        enqueue_policy_action_notifications(
            db,
            alert=alert,
            repeater=repeater,
            policy_template=policy.template,
            event_type="alert_activated",
            transition_key=(alert.first_seen_at or now).isoformat(),
            actor="system:policy-engine",
            note=None,
        )
        return True

    alert.repeater_id = repeater.id
    alert.alert_type = _alert_type_for_rule(policy.template.rule_type)
    alert.severity = policy.template.severity
    alert.message = message
    alert.last_seen_at = now
    if alert.state == "resolved":
        apply_alert_state_transition(
            alert,
            new_state="active",
            actor="system:policy-engine",
            note="Auto-reactivated: policy condition active",
        )
        queue_notification_event(
            db,
            alert_id=alert.id,
            channel="internal",
            event_type="alert_reactivated",
            payload={
                "alert_id": alert.id,
                "fingerprint": fingerprint,
                "rule_type": policy.template.rule_type,
                "severity": policy.template.severity,
                "message": message,
            },
        )
        enqueue_policy_action_notifications(
            db,
            alert=alert,
            repeater=repeater,
            policy_template=policy.template,
            event_type="alert_reactivated",
            transition_key=(alert.last_seen_at or now).isoformat(),
            actor="system:policy-engine",
            note=alert.note,
        )
        return True
    return False


def _resolve_alert_if_open(
    db: Session,
    *,
    repeater: Repeater,
    rule_type: str,
    now: datetime,
    note: str,
) -> bool:
    fingerprint = _alert_fingerprint(repeater.id, rule_type)
    alert = db.scalar(
        select(Alert)
        .where(Alert.fingerprint == fingerprint, Alert.state != "resolved")
        .order_by(Alert.last_seen_at.desc(), Alert.timestamp.desc())
    )
    if alert is None:
        return False
    apply_alert_state_transition(
        alert,
        new_state="resolved",
        actor="system:policy-engine",
        note=note,
    )
    alert.last_seen_at = now
    queue_notification_event(
        db,
        alert_id=alert.id,
        channel="internal",
        event_type="alert_auto_resolved",
        payload={
            "alert_id": alert.id,
            "fingerprint": fingerprint,
            "rule_type": rule_type,
            "note": note,
        },
    )
    effective_policy_template = db.scalar(
        select(AlertPolicyTemplate)
        .where(
            AlertPolicyTemplate.rule_type == rule_type,
            AlertPolicyTemplate.enabled == 1,
        )
        .order_by(AlertPolicyTemplate.updated_at.desc())
        .limit(1)
    )
    if effective_policy_template is not None:
        enqueue_policy_action_notifications(
            db,
            alert=alert,
            repeater=repeater,
            policy_template=effective_policy_template,
            event_type="alert_auto_resolved",
            transition_key=(alert.resolved_at or now).isoformat(),
            actor="system:policy-engine",
            note=note,
        )
    return True


def serialize_policy_template_config(template: AlertPolicyTemplate) -> dict:
    return _parse_config(template.config_json)

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Alert, NotificationEvent, Repeater, User
from app.db.session import get_db_session
from app.schemas.alerts import (
    AlertDetailResponse,
    AlertLifecycleRequest,
    AlertResponse,
    AlertSummaryResponse,
    NotificationEventResponse,
)
from app.security.deps import require_roles
from app.services.alert_action_delivery import enqueue_alert_lifecycle_action_notifications
from app.services.alerts import apply_alert_state_transition, queue_notification_event
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/alerts")


def _to_alert_response(alert: Alert, node_name: str | None) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        repeater_id=alert.repeater_id,
        node_name=node_name,
        timestamp=alert.timestamp,
        alert_type=alert.alert_type,
        severity=alert.severity,
        message=alert.message,
        state=alert.state,
        first_seen_at=alert.first_seen_at,
        last_seen_at=alert.last_seen_at,
        fingerprint=alert.fingerprint,
        acked_at=alert.acked_at,
        acked_by=alert.acked_by,
        note=alert.note,
        resolved_at=alert.resolved_at,
    )


def _to_notification_response(event: NotificationEvent) -> NotificationEventResponse:
    return NotificationEventResponse(
        id=event.id,
        channel=event.channel,
        event_type=event.event_type,
        status=event.status,
        attempts=event.attempts,
        next_attempt_at=event.next_attempt_at,
        last_error=event.last_error,
        created_at=event.created_at,
        sent_at=event.sent_at,
    )


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    state: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    repeater_id: str | None = Query(default=None),
    node_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertResponse]:
    query = (
        select(Alert, Repeater.node_name)
        .outerjoin(Repeater, Repeater.id == Alert.repeater_id)
        .order_by(Alert.last_seen_at.desc(), Alert.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    if state:
        query = query.where(Alert.state == state)
    if severity:
        query = query.where(Alert.severity == severity)
    if alert_type:
        query = query.where(Alert.alert_type == alert_type)
    if repeater_id:
        query = query.where(Alert.repeater_id == repeater_id)
    if node_name:
        query = query.where(Repeater.node_name == node_name)

    rows = db.execute(query).all()
    return [_to_alert_response(alert, row_node_name) for alert, row_node_name in rows]


@router.get("/summary", response_model=AlertSummaryResponse)
def alerts_summary(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> AlertSummaryResponse:
    total = db.scalar(select(func.count(Alert.id))) or 0
    by_severity_rows = db.execute(
        select(Alert.severity, func.count(Alert.id)).group_by(Alert.severity)
    ).all()
    by_state_rows = db.execute(
        select(Alert.state, func.count(Alert.id)).group_by(Alert.state)
    ).all()
    by_state = {str(key): int(count) for key, count in by_state_rows}

    return AlertSummaryResponse(
        total=int(total),
        active=int(by_state.get("active", 0)),
        acknowledged=int(by_state.get("acknowledged", 0)),
        suppressed=int(by_state.get("suppressed", 0)),
        resolved=int(by_state.get("resolved", 0)),
        by_severity={str(key): int(count) for key, count in by_severity_rows},
        by_state=by_state,
    )


@router.get("/{alert_id}", response_model=AlertDetailResponse)
def get_alert(
    alert_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> AlertDetailResponse:
    row = db.execute(
        select(Alert, Repeater.node_name)
        .outerjoin(Repeater, Repeater.id == Alert.repeater_id)
        .where(Alert.id == alert_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert, row_node_name = row
    notifications = db.scalars(
        select(NotificationEvent)
        .where(NotificationEvent.alert_id == alert.id)
        .order_by(NotificationEvent.created_at.desc())
        .limit(100)
    ).all()
    return AlertDetailResponse(
        **_to_alert_response(alert, row_node_name).model_dump(),
        notifications=[_to_notification_response(item) for item in notifications],
    )


def _update_alert_state(
    *,
    db: Session,
    alert_id: str,
    new_state: str,
    payload: AlertLifecycleRequest,
    current_user: User,
    audit_action: str,
    notification_event_type: str,
) -> AlertResponse:
    row = db.execute(
        select(Alert, Repeater.node_name)
        .outerjoin(Repeater, Repeater.id == Alert.repeater_id)
        .where(Alert.id == alert_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert, row_node_name = row

    if new_state == "acknowledged" and alert.state == "resolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolved alerts cannot be acknowledged",
        )

    apply_alert_state_transition(
        alert,
        new_state=new_state,
        actor=current_user.email,
        note=payload.note,
    )
    queue_notification_event(
        db,
        alert_id=alert.id,
        channel="internal",
        event_type=notification_event_type,
        payload={
            "alert_id": alert.id,
            "new_state": alert.state,
            "actor": current_user.email,
            "note": payload.note,
        },
    )
    repeater = (
        db.scalar(select(Repeater).where(Repeater.id == alert.repeater_id))
        if alert.repeater_id
        else None
    )
    transition_key = (
        alert.acked_at
        if new_state == "acknowledged"
        else alert.resolved_at
        if new_state == "resolved"
        else alert.last_seen_at
    )
    enqueue_alert_lifecycle_action_notifications(
        db,
        alert=alert,
        repeater=repeater,
        event_type=notification_event_type,
        transition_key=(transition_key or alert.last_seen_at).isoformat(),
        actor=current_user.email,
        note=payload.note,
    )
    write_audit_log(
        db,
        action=audit_action,
        target_type="alert",
        target_id=alert.id,
        user_id=current_user.id,
        details={
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "state": alert.state,
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(alert)
    return _to_alert_response(alert, row_node_name)


@router.post("/{alert_id}/ack", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: str,
    payload: AlertLifecycleRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertResponse:
    return _update_alert_state(
        db=db,
        alert_id=alert_id,
        new_state="acknowledged",
        payload=payload,
        current_user=current_user,
        audit_action="alert_acknowledged",
        notification_event_type="alert_acknowledged",
    )


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: str,
    payload: AlertLifecycleRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertResponse:
    return _update_alert_state(
        db=db,
        alert_id=alert_id,
        new_state="resolved",
        payload=payload,
        current_user=current_user,
        audit_action="alert_resolved",
        notification_event_type="alert_resolved",
    )


@router.post("/{alert_id}/suppress", response_model=AlertResponse)
def suppress_alert(
    alert_id: str,
    payload: AlertLifecycleRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertResponse:
    return _update_alert_state(
        db=db,
        alert_id=alert_id,
        new_state="suppressed",
        payload=payload,
        current_user=current_user,
        audit_action="alert_suppressed",
        notification_event_type="alert_suppressed",
    )

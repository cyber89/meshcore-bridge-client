import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models import (
    Alert,
    AlertActionIntegration,
    AlertActionTemplate,
    AlertPolicyTemplate,
    NotificationEvent,
    Repeater,
    User,
)
from app.db.session import get_db_session
from app.schemas.alert_actions import (
    AlertActionDeliveryResponse,
    AlertActionDeliverySummaryResponse,
    AlertActionIntegrationTestRequest,
    AlertActionIntegrationTestResponse,
    AlertActionIntegrationCreateRequest,
    AlertActionIntegrationResponse,
    AlertActionIntegrationUpdateRequest,
    AlertPolicyActionBindingCreateRequest,
    AlertPolicyActionBindingResponse,
    AlertPolicyActionBindingUpdateRequest,
    AlertActionProviderCapabilityResponse,
    AlertActionTemplatePreviewRequest,
    AlertActionTemplatePreviewResponse,
    AlertActionTemplateCreateRequest,
    AlertActionTemplateResponse,
    AlertActionTemplateUpdateRequest,
)
from app.security.deps import require_roles
from app.services.alert_action_delivery import (
    build_alert_action_context,
    render_action_template_preview,
    resolve_policy_template_for_alert,
)
from app.services.alert_actions import (
    create_action_integration,
    create_action_binding,
    create_action_template,
    get_action_binding,
    get_action_integration,
    get_action_template,
    get_notification_provider_registry,
    list_action_bindings,
    list_action_integrations,
    list_action_templates,
    parse_action_template_payload,
    parse_integration_settings,
    to_binding_response,
    to_integration_response,
    to_template_response,
    update_action_binding,
    update_action_integration,
    update_action_template,
)
from app.services.audit import write_audit_log
from app.services.notification_providers.base import NotificationSendRequest

router = APIRouter(prefix="/api/alert-actions")


def _integration_changes_for_audit(changes: dict) -> dict:
    filtered = {key: value for key, value in changes.items() if key not in {"settings", "secrets"}}
    if "settings" in changes:
        settings = changes["settings"]
        filtered["settings_keys"] = sorted(settings.keys()) if isinstance(settings, dict) else []
    if "secrets" in changes:
        secrets = changes["secrets"]
        filtered["secrets_keys"] = sorted(secrets.keys()) if isinstance(secrets, dict) else []
    return filtered


def _template_changes_for_audit(changes: dict) -> dict:
    filtered = {
        key: value
        for key, value in changes.items()
        if key not in {"payload_template"}
    }
    if "payload_template" in changes:
        payload_template = changes["payload_template"]
        filtered["payload_template_keys"] = (
            sorted(payload_template.keys())
            if isinstance(payload_template, dict)
            else []
        )
    return filtered


def _binding_changes_for_audit(changes: dict) -> dict:
    filtered = dict(changes)
    if "event_types" in filtered:
        filtered["event_types"] = list(filtered["event_types"] or [])
    return filtered


def _parse_json_dict(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _to_delivery_response(
    event: NotificationEvent,
    *,
    integration: AlertActionIntegration | None,
    action_template: AlertActionTemplate | None,
) -> AlertActionDeliveryResponse:
    return AlertActionDeliveryResponse(
        id=event.id,
        alert_id=event.alert_id,
        integration_id=event.integration_id,
        integration_name=integration.name if integration else None,
        action_template_id=event.action_template_id,
        action_template_name=action_template.name if action_template else None,
        binding_id=event.binding_id,
        provider_type=event.provider_type,
        channel=event.channel,
        event_type=event.event_type,
        status=event.status,
        attempts=event.attempts,
        next_attempt_at=event.next_attempt_at,
        sent_at=event.sent_at,
        last_error=event.last_error,
        response_status_code=event.response_status_code,
        provider_message_id=event.provider_message_id,
        payload=_parse_json_dict(event.payload_json),
        rendered_payload=_parse_json_dict(event.rendered_payload_json) or None,
        created_at=event.created_at,
    )


def _sample_alert_for_preview(now: datetime) -> Alert:
    return Alert(
        id="preview-alert",
        repeater_id="preview-repeater",
        timestamp=now,
        alert_type="repeater_offline",
        severity="warning",
        message="Preview alert message",
        state="active",
        first_seen_at=now,
        last_seen_at=now,
        fingerprint="preview-repeater:offline_repeater",
        acked_at=None,
        acked_by=None,
        note=None,
        resolved_at=None,
    )


def _sample_repeater_for_preview(now: datetime) -> Repeater:
    return Repeater(
        id="preview-repeater",
        node_name="preview-node",
        pubkey="preview-pubkey",
        status="connected",
        firmware_version="preview",
        location="preview",
        config_hash=None,
        last_inform_at=now,
        created_at=now,
        updated_at=now,
    )


def _sample_policy_template_for_preview(now: datetime) -> AlertPolicyTemplate:
    return AlertPolicyTemplate(
        id="preview-policy",
        name="Preview Policy",
        description="Preview policy context",
        rule_type="offline_repeater",
        severity="warning",
        enabled=1,
        threshold_value=None,
        window_minutes=None,
        offline_grace_seconds=180,
        cooldown_seconds=0,
        auto_resolve=1,
        config_json="{}",
        created_at=now,
        updated_at=now,
    )


@router.get("/providers", response_model=list[AlertActionProviderCapabilityResponse])
def list_alert_action_providers(
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertActionProviderCapabilityResponse]:
    capabilities = get_notification_provider_registry().list_capabilities()
    return [
        AlertActionProviderCapabilityResponse(
            provider_type=item.provider_type,
            display_name=item.display_name,
            supports_send=item.supports_send,
            supports_templated_payload=item.supports_templated_payload,
        )
        for item in capabilities
    ]


@router.get("/integrations", response_model=list[AlertActionIntegrationResponse])
def list_integrations(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertActionIntegrationResponse]:
    return [to_integration_response(item) for item in list_action_integrations(db)]


@router.get("/integrations/{integration_id}", response_model=AlertActionIntegrationResponse)
def get_integration(
    integration_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> AlertActionIntegrationResponse:
    integration = get_action_integration(db, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action integration not found")
    return to_integration_response(integration)


@router.post("/integrations", response_model=AlertActionIntegrationResponse, status_code=status.HTTP_201_CREATED)
def create_integration(
    payload: AlertActionIntegrationCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertActionIntegrationResponse:
    try:
        integration = create_action_integration(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert action integration already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_action_integration_created",
        target_type="alert_action_integration",
        target_id=integration.id,
        user_id=current_user.id,
        details={
            "name": integration.name,
            "provider_type": integration.provider_type,
            "enabled": integration.enabled == 1,
        },
    )
    db.commit()
    db.refresh(integration)
    return to_integration_response(integration)


@router.patch("/integrations/{integration_id}", response_model=AlertActionIntegrationResponse)
def update_integration(
    integration_id: str,
    payload: AlertActionIntegrationUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertActionIntegrationResponse:
    integration = get_action_integration(db, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action integration not found")
    changes = payload.model_dump(exclude_unset=True)
    try:
        integration = update_action_integration(db, integration, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert action integration already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_action_integration_updated",
        target_type="alert_action_integration",
        target_id=integration.id,
        user_id=current_user.id,
        details={"changes": _integration_changes_for_audit(changes)},
    )
    db.commit()
    db.refresh(integration)
    return to_integration_response(integration)


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    integration = get_action_integration(db, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action integration not found")
    integration_name = integration.name
    provider_type = integration.provider_type
    db.delete(integration)
    write_audit_log(
        db,
        action="alert_action_integration_deleted",
        target_type="alert_action_integration",
        target_id=integration_id,
        user_id=current_user.id,
        details={"name": integration_name, "provider_type": provider_type},
    )
    db.commit()


@router.get("/templates", response_model=list[AlertActionTemplateResponse])
def list_templates(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertActionTemplateResponse]:
    return [to_template_response(item) for item in list_action_templates(db)]


@router.get("/templates/{template_id}", response_model=AlertActionTemplateResponse)
def get_template(
    template_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> AlertActionTemplateResponse:
    template = get_action_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action template not found")
    return to_template_response(template)


@router.post("/templates", response_model=AlertActionTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: AlertActionTemplateCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertActionTemplateResponse:
    try:
        template = create_action_template(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except KeyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert action template already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_action_template_created",
        target_type="alert_action_template",
        target_id=template.id,
        user_id=current_user.id,
        details={
            "name": template.name,
            "provider_type": template.provider_type,
            "enabled": template.enabled == 1,
        },
    )
    db.commit()
    db.refresh(template)
    return to_template_response(template)


@router.patch("/templates/{template_id}", response_model=AlertActionTemplateResponse)
def update_template(
    template_id: str,
    payload: AlertActionTemplateUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertActionTemplateResponse:
    template = get_action_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action template not found")
    changes = payload.model_dump(exclude_unset=True)
    try:
        template = update_action_template(db, template, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except KeyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert action template already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_action_template_updated",
        target_type="alert_action_template",
        target_id=template.id,
        user_id=current_user.id,
        details={"changes": _template_changes_for_audit(changes)},
    )
    db.commit()
    db.refresh(template)
    return to_template_response(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    template = get_action_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action template not found")
    template_name = template.name
    db.delete(template)
    write_audit_log(
        db,
        action="alert_action_template_deleted",
        target_type="alert_action_template",
        target_id=template_id,
        user_id=current_user.id,
        details={"name": template_name},
    )
    db.commit()


@router.get("/bindings", response_model=list[AlertPolicyActionBindingResponse])
def list_bindings(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertPolicyActionBindingResponse]:
    return [to_binding_response(item) for item in list_action_bindings(db)]


@router.get("/bindings/{binding_id}", response_model=AlertPolicyActionBindingResponse)
def get_binding(
    binding_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> AlertPolicyActionBindingResponse:
    binding = get_action_binding(db, binding_id)
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert policy action binding not found",
        )
    return to_binding_response(binding)


@router.post(
    "/bindings",
    response_model=AlertPolicyActionBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_binding(
    payload: AlertPolicyActionBindingCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertPolicyActionBindingResponse:
    try:
        binding = create_action_binding(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert policy action binding already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_policy_action_binding_created",
        target_type="alert_policy_action_binding",
        target_id=binding.id,
        user_id=current_user.id,
        details={
            "policy_template_id": binding.policy_template_id,
            "integration_id": binding.integration_id,
            "action_template_id": binding.action_template_id,
            "event_types": to_binding_response(binding).event_types,
        },
    )
    db.commit()
    db.refresh(binding)
    return to_binding_response(binding)


@router.patch("/bindings/{binding_id}", response_model=AlertPolicyActionBindingResponse)
def update_binding(
    binding_id: str,
    payload: AlertPolicyActionBindingUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertPolicyActionBindingResponse:
    binding = get_action_binding(db, binding_id)
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert policy action binding not found",
        )
    changes = payload.model_dump(exclude_unset=True)
    try:
        binding = update_action_binding(db, binding, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert policy action binding already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_policy_action_binding_updated",
        target_type="alert_policy_action_binding",
        target_id=binding.id,
        user_id=current_user.id,
        details={"changes": _binding_changes_for_audit(changes)},
    )
    db.commit()
    db.refresh(binding)
    return to_binding_response(binding)


@router.delete("/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_binding(
    binding_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    binding = get_action_binding(db, binding_id)
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert policy action binding not found",
        )
    details = {
        "policy_template_id": binding.policy_template_id,
        "integration_id": binding.integration_id,
        "action_template_id": binding.action_template_id,
    }
    db.delete(binding)
    write_audit_log(
        db,
        action="alert_policy_action_binding_deleted",
        target_type="alert_policy_action_binding",
        target_id=binding_id,
        user_id=current_user.id,
        details=details,
    )
    db.commit()


@router.post("/templates/preview", response_model=AlertActionTemplatePreviewResponse)
def preview_template(
    payload: AlertActionTemplatePreviewRequest,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> AlertActionTemplatePreviewResponse:
    now = datetime.now(UTC)
    action_template = None
    if payload.action_template_id:
        action_template = get_action_template(db, payload.action_template_id)
        if action_template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action template not found")
    title_template = (
        action_template.title_template
        if action_template is not None
        else payload.title_template
    )
    body_template = (
        action_template.body_template
        if action_template is not None
        else payload.body_template
    )
    payload_template = (
        parse_action_template_payload(action_template)
        if action_template is not None
        else payload.payload_template
    )
    if title_template is None and body_template is None and payload_template is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide action_template_id or at least one template field",
        )
    alert = _sample_alert_for_preview(now)
    repeater = _sample_repeater_for_preview(now)
    policy_template = _sample_policy_template_for_preview(now)
    if payload.alert_id:
        loaded_alert = db.scalar(select(Alert).where(Alert.id == payload.alert_id))
        if loaded_alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        alert = loaded_alert
    if payload.repeater_id:
        loaded_repeater = db.scalar(select(Repeater).where(Repeater.id == payload.repeater_id))
        if loaded_repeater is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repeater not found")
        repeater = loaded_repeater
    elif alert.repeater_id:
        repeater = db.scalar(select(Repeater).where(Repeater.id == alert.repeater_id)) or repeater
    resolved_policy_template = resolve_policy_template_for_alert(db, alert=alert)
    if resolved_policy_template is not None:
        policy_template = resolved_policy_template
    try:
        context = build_alert_action_context(
            alert=alert,
            repeater=repeater,
            policy_template=policy_template,
            event_type=payload.event_type,
            sample_context=payload.sample_context,
            occurred_at=now,
        )
        rendered = render_action_template_preview(
            title_template=title_template,
            body_template=body_template,
            payload_template=payload_template,
            event_type=payload.event_type,
            context=context,
        )
    except KeyError as exc:
        missing = str(exc).strip("'")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template variable not found in context: {missing}",
        ) from exc
    return AlertActionTemplatePreviewResponse(
        event_type=payload.event_type,
        title=rendered["title"],
        body=rendered["body"],
        payload=rendered["payload"],
        context=context,
    )


@router.post(
    "/integrations/{integration_id}/test",
    response_model=AlertActionIntegrationTestResponse,
)
def test_integration_send(
    integration_id: str,
    payload: AlertActionIntegrationTestRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertActionIntegrationTestResponse:
    integration = get_action_integration(db, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert action integration not found")
    registry = get_notification_provider_registry()
    try:
        settings = parse_integration_settings(integration)
        result = registry.send(
            provider_type=integration.provider_type,
            settings=settings,
            request=NotificationSendRequest(
                event_type=payload.event_type,
                payload=payload.payload,
                rendered_payload=payload.rendered_payload,
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Integration test failed before provider call: {exc}",
        ) from exc
    write_audit_log(
        db,
        action="alert_action_integration_tested",
        target_type="alert_action_integration",
        target_id=integration.id,
        user_id=current_user.id,
        details={
            "provider_type": integration.provider_type,
            "event_type": payload.event_type,
            "status": result.status,
            "status_code": result.status_code,
        },
    )
    db.commit()
    return AlertActionIntegrationTestResponse(
        status=result.status,
        status_code=result.status_code,
        provider_message_id=result.provider_message_id,
        response_body=result.response_body,
        error=result.error,
    )


@router.get("/deliveries", response_model=list[AlertActionDeliveryResponse])
def list_deliveries(
    status_filter: str | None = Query(default=None, alias="status"),
    provider_type: str | None = Query(default=None),
    alert_id: str | None = Query(default=None),
    integration_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertActionDeliveryResponse]:
    query = (
        select(NotificationEvent)
        .where(NotificationEvent.channel == "action")
        .order_by(NotificationEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        query = query.where(NotificationEvent.status == status_filter)
    if provider_type:
        query = query.where(NotificationEvent.provider_type == provider_type)
    if alert_id:
        query = query.where(NotificationEvent.alert_id == alert_id)
    if integration_id:
        query = query.where(NotificationEvent.integration_id == integration_id)
    events = db.scalars(query).all()
    integration_ids = sorted({event.integration_id for event in events if event.integration_id})
    action_template_ids = sorted(
        {event.action_template_id for event in events if event.action_template_id}
    )
    integrations = {
        row.id: row
        for row in db.scalars(
            select(AlertActionIntegration).where(AlertActionIntegration.id.in_(integration_ids))
        ).all()
    } if integration_ids else {}
    action_templates = {
        row.id: row
        for row in db.scalars(
            select(AlertActionTemplate).where(AlertActionTemplate.id.in_(action_template_ids))
        ).all()
    } if action_template_ids else {}
    return [
        _to_delivery_response(
            event,
            integration=integrations.get(event.integration_id),
            action_template=action_templates.get(event.action_template_id),
        )
        for event in events
    ]


@router.get("/deliveries/summary", response_model=AlertActionDeliverySummaryResponse)
def deliveries_summary(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> AlertActionDeliverySummaryResponse:
    total = db.scalar(
        select(func.count(NotificationEvent.id)).where(NotificationEvent.channel == "action")
    ) or 0
    by_status_rows = db.execute(
        select(NotificationEvent.status, func.count(NotificationEvent.id))
        .where(NotificationEvent.channel == "action")
        .group_by(NotificationEvent.status)
    ).all()
    by_provider_rows = db.execute(
        select(NotificationEvent.provider_type, func.count(NotificationEvent.id))
        .where(NotificationEvent.channel == "action")
        .group_by(NotificationEvent.provider_type)
    ).all()
    by_status = {str(status_key): int(count) for status_key, count in by_status_rows}
    by_provider = {
        str(provider_key or "unknown"): int(count)
        for provider_key, count in by_provider_rows
    }
    return AlertActionDeliverySummaryResponse(
        total=int(total),
        queued=int(by_status.get("queued", 0)),
        sent=int(by_status.get("sent", 0)),
        failed=int(by_status.get("failed", 0)),
        by_provider_type=by_provider,
    )

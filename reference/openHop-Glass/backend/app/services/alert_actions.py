from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AlertActionIntegration,
    AlertActionTemplate,
    AlertPolicyActionBinding,
    AlertPolicyTemplate,
)
from app.schemas.alert_actions import (
    VALID_ALERT_ACTION_EVENT_TYPES,
    AlertPolicyActionBindingCreateRequest,
    AlertPolicyActionBindingResponse,
    AlertPolicyActionBindingUpdateRequest,
    AlertActionIntegrationCreateRequest,
    AlertActionIntegrationResponse,
    AlertActionIntegrationUpdateRequest,
    AlertActionTemplateCreateRequest,
    AlertActionTemplateResponse,
    AlertActionTemplateUpdateRequest,
)
from app.services.notification_providers import NotificationProviderRegistry


def _parse_json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item).strip() for item in loaded if str(item).strip()]


def _serialize_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


@lru_cache(maxsize=1)
def get_notification_provider_registry() -> NotificationProviderRegistry:
    return NotificationProviderRegistry()


def validate_action_integration_settings(
    *,
    provider_type: str,
    settings: dict[str, Any],
    registry: NotificationProviderRegistry | None = None,
) -> dict[str, Any]:
    resolved_registry = registry or get_notification_provider_registry()
    normalized_provider_type = provider_type.strip().lower()
    try:
        return resolved_registry.validate_settings(normalized_provider_type, settings)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def normalize_alert_action_event_types(event_types: list[str] | None) -> list[str]:
    if not event_types:
        return []
    normalized = sorted({item.strip() for item in event_types if item and item.strip()})
    return [item for item in normalized if item in VALID_ALERT_ACTION_EVENT_TYPES]


def _has_stored_secrets(integration: AlertActionIntegration) -> bool:
    parsed = parse_integration_secrets(integration)
    return bool(parsed)


def _normalize_provider_type(provider_type: str | None) -> str | None:
    if provider_type is None:
        return None
    normalized = provider_type.strip().lower()
    return normalized or None


def parse_integration_settings(integration: AlertActionIntegration) -> dict[str, Any]:
    return _parse_json_dict(integration.settings_json)


def parse_integration_secrets(integration: AlertActionIntegration) -> dict[str, Any]:
    return _parse_json_dict(integration.secrets_json)


def serialize_integration_settings(settings: dict[str, Any]) -> str:
    return _serialize_json(settings)


def serialize_integration_secrets(secrets: dict[str, Any]) -> str:
    return _serialize_json(secrets)


def parse_action_template_payload(template: AlertActionTemplate) -> dict[str, Any] | None:
    loaded = _parse_json_dict(template.payload_template_json)
    return loaded or None


def parse_action_template_default_events(template: AlertActionTemplate) -> list[str]:
    return normalize_alert_action_event_types(_parse_json_list(template.default_event_types_json))


def parse_binding_event_types(binding: AlertPolicyActionBinding) -> list[str]:
    return normalize_alert_action_event_types(_parse_json_list(binding.event_types_json))


def serialize_action_events(event_types: list[str]) -> str:
    return _serialize_json(normalize_alert_action_event_types(event_types))


def to_integration_response(integration: AlertActionIntegration) -> AlertActionIntegrationResponse:
    return AlertActionIntegrationResponse(
        id=integration.id,
        name=integration.name,
        provider_type=integration.provider_type,
        description=integration.description,
        enabled=integration.enabled == 1,
        settings=parse_integration_settings(integration),
        has_secrets=_has_stored_secrets(integration),
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def to_template_response(template: AlertActionTemplate) -> AlertActionTemplateResponse:
    return AlertActionTemplateResponse(
        id=template.id,
        name=template.name,
        provider_type=template.provider_type,
        description=template.description,
        title_template=template.title_template,
        body_template=template.body_template,
        payload_template=parse_action_template_payload(template),
        default_event_types=parse_action_template_default_events(template),
        enabled=template.enabled == 1,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def list_action_integrations(db: Session) -> list[AlertActionIntegration]:
    return db.scalars(select(AlertActionIntegration).order_by(AlertActionIntegration.name.asc())).all()


def get_action_integration(db: Session, integration_id: str) -> AlertActionIntegration | None:
    return db.scalar(select(AlertActionIntegration).where(AlertActionIntegration.id == integration_id))


def create_action_integration(
    db: Session,
    payload: AlertActionIntegrationCreateRequest,
) -> AlertActionIntegration:
    normalized_provider_type = _normalize_provider_type(payload.provider_type)
    assert normalized_provider_type is not None
    validated_settings = validate_action_integration_settings(
        provider_type=normalized_provider_type,
        settings=payload.settings,
    )
    integration = AlertActionIntegration(
        name=payload.name.strip(),
        provider_type=normalized_provider_type,
        description=payload.description,
        enabled=1 if payload.enabled else 0,
        settings_json=serialize_integration_settings(validated_settings),
        secrets_json=(
            serialize_integration_secrets(payload.secrets)
            if payload.secrets
            else None
        ),
    )
    db.add(integration)
    db.flush()
    return integration


def update_action_integration(
    db: Session,
    integration: AlertActionIntegration,
    payload: AlertActionIntegrationUpdateRequest,
) -> AlertActionIntegration:
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        integration.name = str(changes["name"]).strip()
    if "description" in changes:
        integration.description = changes["description"]
    if "enabled" in changes and changes["enabled"] is not None:
        integration.enabled = 1 if bool(changes["enabled"]) else 0
    if "settings" in changes and changes["settings"] is not None:
        validated_settings = validate_action_integration_settings(
            provider_type=integration.provider_type,
            settings=changes["settings"],
        )
        integration.settings_json = serialize_integration_settings(validated_settings)
    if "secrets" in changes:
        secrets = changes["secrets"]
        integration.secrets_json = (
            serialize_integration_secrets(secrets)
            if isinstance(secrets, dict) and secrets
            else None
        )
    db.flush()
    return integration


def list_action_templates(db: Session) -> list[AlertActionTemplate]:
    return db.scalars(select(AlertActionTemplate).order_by(AlertActionTemplate.name.asc())).all()


def get_action_template(db: Session, template_id: str) -> AlertActionTemplate | None:
    return db.scalar(select(AlertActionTemplate).where(AlertActionTemplate.id == template_id))


def create_action_template(
    db: Session,
    payload: AlertActionTemplateCreateRequest,
) -> AlertActionTemplate:
    normalized_provider_type = _normalize_provider_type(payload.provider_type)
    if normalized_provider_type is not None:
        get_notification_provider_registry().get_provider(normalized_provider_type)
    template = AlertActionTemplate(
        name=payload.name.strip(),
        provider_type=normalized_provider_type,
        description=payload.description,
        title_template=payload.title_template,
        body_template=payload.body_template,
        payload_template_json=(
            _serialize_json(payload.payload_template)
            if payload.payload_template is not None
            else None
        ),
        default_event_types_json=serialize_action_events(payload.default_event_types),
        enabled=1 if payload.enabled else 0,
    )
    db.add(template)
    db.flush()
    return template


def update_action_template(
    db: Session,
    template: AlertActionTemplate,
    payload: AlertActionTemplateUpdateRequest,
) -> AlertActionTemplate:
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        template.name = str(changes["name"]).strip()
    if "provider_type" in changes:
        normalized_provider_type = _normalize_provider_type(changes["provider_type"])
        if normalized_provider_type is not None:
            get_notification_provider_registry().get_provider(normalized_provider_type)
        template.provider_type = normalized_provider_type
    if "description" in changes:
        template.description = changes["description"]
    if "title_template" in changes:
        template.title_template = changes["title_template"]
    if "body_template" in changes:
        template.body_template = changes["body_template"]
    if "payload_template" in changes:
        payload_template = changes["payload_template"]
        template.payload_template_json = (
            _serialize_json(payload_template)
            if isinstance(payload_template, dict)
            else None
        )
    if "default_event_types" in changes:
        default_events = changes["default_event_types"]
        template.default_event_types_json = serialize_action_events(default_events or [])
    if "enabled" in changes and changes["enabled"] is not None:
        template.enabled = 1 if bool(changes["enabled"]) else 0
    db.flush()
    return template


def to_binding_response(binding: AlertPolicyActionBinding) -> AlertPolicyActionBindingResponse:
    return AlertPolicyActionBindingResponse(
        id=binding.id,
        policy_template_id=binding.policy_template_id,
        integration_id=binding.integration_id,
        action_template_id=binding.action_template_id,
        event_types=parse_binding_event_types(binding),
        min_severity=binding.min_severity,
        enabled=binding.enabled == 1,
        sort_order=binding.sort_order,
        cooldown_seconds=binding.cooldown_seconds,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def list_action_bindings(db: Session) -> list[AlertPolicyActionBinding]:
    return db.scalars(
        select(AlertPolicyActionBinding).order_by(
            AlertPolicyActionBinding.sort_order.asc(),
            AlertPolicyActionBinding.created_at.asc(),
        )
    ).all()


def get_action_binding(db: Session, binding_id: str) -> AlertPolicyActionBinding | None:
    return db.scalar(select(AlertPolicyActionBinding).where(AlertPolicyActionBinding.id == binding_id))


def _validate_binding_relationships(
    db: Session,
    *,
    policy_template_id: str,
    integration_id: str,
    action_template_id: str,
) -> tuple[AlertPolicyTemplate, AlertActionIntegration, AlertActionTemplate]:
    policy_template = db.scalar(
        select(AlertPolicyTemplate).where(AlertPolicyTemplate.id == policy_template_id)
    )
    if policy_template is None:
        raise ValueError("Referenced alert policy template was not found")
    integration = db.scalar(
        select(AlertActionIntegration).where(AlertActionIntegration.id == integration_id)
    )
    if integration is None:
        raise ValueError("Referenced alert action integration was not found")
    action_template = db.scalar(
        select(AlertActionTemplate).where(AlertActionTemplate.id == action_template_id)
    )
    if action_template is None:
        raise ValueError("Referenced alert action template was not found")
    template_provider_type = _normalize_provider_type(action_template.provider_type)
    if (
        template_provider_type is not None
        and template_provider_type != integration.provider_type
    ):
        raise ValueError(
            "Action template provider_type must match integration provider_type when specified"
        )
    return policy_template, integration, action_template


def create_action_binding(
    db: Session,
    payload: AlertPolicyActionBindingCreateRequest,
) -> AlertPolicyActionBinding:
    _, _, action_template = _validate_binding_relationships(
        db,
        policy_template_id=payload.policy_template_id,
        integration_id=payload.integration_id,
        action_template_id=payload.action_template_id,
    )
    event_types = payload.event_types or parse_action_template_default_events(action_template)
    binding = AlertPolicyActionBinding(
        policy_template_id=payload.policy_template_id,
        integration_id=payload.integration_id,
        action_template_id=payload.action_template_id,
        event_types_json=serialize_action_events(event_types),
        min_severity=payload.min_severity,
        enabled=1 if payload.enabled else 0,
        sort_order=payload.sort_order,
        cooldown_seconds=payload.cooldown_seconds,
    )
    db.add(binding)
    db.flush()
    return binding


def update_action_binding(
    db: Session,
    binding: AlertPolicyActionBinding,
    payload: AlertPolicyActionBindingUpdateRequest,
) -> AlertPolicyActionBinding:
    changes = payload.model_dump(exclude_unset=True)
    _validate_binding_relationships(
        db,
        policy_template_id=binding.policy_template_id,
        integration_id=binding.integration_id,
        action_template_id=binding.action_template_id,
    )
    if "event_types" in changes:
        event_types = changes["event_types"] or []
        binding.event_types_json = serialize_action_events(event_types)
    if "min_severity" in changes:
        binding.min_severity = changes["min_severity"]
    if "enabled" in changes and changes["enabled"] is not None:
        binding.enabled = 1 if bool(changes["enabled"]) else 0
    if "sort_order" in changes and changes["sort_order"] is not None:
        binding.sort_order = int(changes["sort_order"])
    if "cooldown_seconds" in changes and changes["cooldown_seconds"] is not None:
        binding.cooldown_seconds = int(changes["cooldown_seconds"])
    db.flush()
    return binding

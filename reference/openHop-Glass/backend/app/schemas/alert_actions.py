from datetime import datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

VALID_ALERT_ACTION_PROVIDER_TYPES = {"webhook", "pushover", "apprise"}
VALID_ALERT_ACTION_EVENT_TYPES = {
    "alert_activated",
    "alert_reactivated",
    "alert_resolved",
    "alert_acknowledged",
    "alert_suppressed",
    "alert_auto_resolved",
}
VALID_ALERT_ACTION_SEVERITIES = {"critical", "warning", "info"}
VALID_WEBHOOK_HTTP_METHODS = {"POST", "PUT", "PATCH"}
VALID_APPRISE_NOTIFY_TYPES = {"info", "success", "warning", "failure"}
VALID_APPRISE_FORMATS = {"text", "markdown", "html"}


def _validate_provider_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_ALERT_ACTION_PROVIDER_TYPES:
        allowed = ", ".join(sorted(VALID_ALERT_ACTION_PROVIDER_TYPES))
        raise ValueError(f"provider_type must be one of: {allowed}")
    return normalized


def _validate_event_types(event_types: list[str]) -> list[str]:
    normalized = sorted({item.strip() for item in event_types if item and item.strip()})
    invalid = [item for item in normalized if item not in VALID_ALERT_ACTION_EVENT_TYPES]
    if invalid:
        allowed = ", ".join(sorted(VALID_ALERT_ACTION_EVENT_TYPES))
        raise ValueError(
            f"event_types contain unsupported values: {', '.join(invalid)}. Allowed: {allowed}"
        )
    return normalized


class WebhookIntegrationSettings(BaseModel):
    url: AnyHttpUrl
    method: str = Field(default="POST", min_length=3, max_length=16)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    verify_tls: bool = True
    max_body_bytes: int = Field(default=262_144, ge=1024, le=5_000_000)

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in VALID_WEBHOOK_HTTP_METHODS:
            allowed = ", ".join(sorted(VALID_WEBHOOK_HTTP_METHODS))
            raise ValueError(f"method must be one of: {allowed}")
        return normalized

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_val in value.items():
            key = raw_key.strip()
            if not key:
                raise ValueError("header names cannot be empty")
            normalized[key] = str(raw_val)
        return normalized


class PushoverIntegrationSettings(BaseModel):
    app_token: str = Field(min_length=1, max_length=128)
    user_key: str = Field(min_length=1, max_length=128)
    device: str | None = Field(default=None, max_length=128)
    priority: int = Field(default=0, ge=-2, le=2)
    sound: str | None = Field(default=None, max_length=64)

class AppriseIntegrationSettings(BaseModel):
    api_url: AnyHttpUrl
    urls: list[str] = Field(default_factory=list)
    tag: str | None = Field(default=None, max_length=512)
    notify_type: str = Field(default="info", min_length=1, max_length=32)
    format: str | None = Field(default=None, min_length=1, max_length=16)
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    verify_tls: bool = True
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("urls", mode="before")
    @classmethod
    def normalize_urls(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        if isinstance(value, (list, tuple, set)):
            urls = [str(item).strip() for item in value if str(item).strip()]
            return urls
        raise ValueError("urls must be a string or list of strings")

    @field_validator("notify_type")
    @classmethod
    def validate_notify_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_APPRISE_NOTIFY_TYPES:
            allowed = ", ".join(sorted(VALID_APPRISE_NOTIFY_TYPES))
            raise ValueError(f"notify_type must be one of: {allowed}")
        return normalized

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized not in VALID_APPRISE_FORMATS:
            allowed = ", ".join(sorted(VALID_APPRISE_FORMATS))
            raise ValueError(f"format must be one of: {allowed}")
        return normalized

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_val in value.items():
            key = raw_key.strip()
            if not key:
                raise ValueError("header names cannot be empty")
            normalized[key] = str(raw_val)
        return normalized


class AlertActionIntegrationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider_type: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, value: str) -> str:
        return _validate_provider_type(value)


class AlertActionIntegrationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    settings: dict[str, Any] | None = None
    secrets: dict[str, Any] | None = None


class AlertActionIntegrationResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    description: str | None = None
    enabled: bool
    settings: dict[str, Any]
    has_secrets: bool
    created_at: datetime
    updated_at: datetime


class AlertActionTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider_type: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    title_template: str | None = Field(default=None, max_length=2000)
    body_template: str | None = Field(default=None, max_length=20_000)
    payload_template: dict[str, Any] | None = None
    default_event_types: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_provider_type(value)

    @field_validator("default_event_types")
    @classmethod
    def validate_default_event_types(cls, value: list[str]) -> list[str]:
        return _validate_event_types(value)


class AlertActionTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider_type: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    title_template: str | None = Field(default=None, max_length=2000)
    body_template: str | None = Field(default=None, max_length=20_000)
    payload_template: dict[str, Any] | None = None
    default_event_types: list[str] | None = None
    enabled: bool | None = None

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_provider_type(value)

    @field_validator("default_event_types")
    @classmethod
    def validate_default_event_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _validate_event_types(value)


class AlertActionTemplateResponse(BaseModel):
    id: str
    name: str
    provider_type: str | None = None
    description: str | None = None
    title_template: str | None = None
    body_template: str | None = None
    payload_template: dict[str, Any] | None = None
    default_event_types: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AlertPolicyActionBindingCreateRequest(BaseModel):
    policy_template_id: str
    integration_id: str
    action_template_id: str
    event_types: list[str] = Field(default_factory=list)
    min_severity: str | None = Field(default=None, min_length=1, max_length=16)
    enabled: bool = True
    sort_order: int = Field(default=100, ge=0, le=1000)
    cooldown_seconds: int = Field(default=0, ge=0, le=24 * 60 * 60)

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value: list[str]) -> list[str]:
        return _validate_event_types(value)

    @field_validator("min_severity")
    @classmethod
    def validate_min_severity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in VALID_ALERT_ACTION_SEVERITIES:
            allowed = ", ".join(sorted(VALID_ALERT_ACTION_SEVERITIES))
            raise ValueError(f"min_severity must be one of: {allowed}")
        return normalized


class AlertPolicyActionBindingUpdateRequest(BaseModel):
    event_types: list[str] | None = None
    min_severity: str | None = Field(default=None, min_length=1, max_length=16)
    enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=24 * 60 * 60)

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _validate_event_types(value)

    @field_validator("min_severity")
    @classmethod
    def validate_min_severity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in VALID_ALERT_ACTION_SEVERITIES:
            allowed = ", ".join(sorted(VALID_ALERT_ACTION_SEVERITIES))
            raise ValueError(f"min_severity must be one of: {allowed}")
        return normalized


class AlertPolicyActionBindingResponse(BaseModel):
    id: str
    policy_template_id: str
    integration_id: str
    action_template_id: str
    event_types: list[str]
    min_severity: str | None = None
    enabled: bool
    sort_order: int
    cooldown_seconds: int
    created_at: datetime
    updated_at: datetime


class AlertActionProviderCapabilityResponse(BaseModel):
    provider_type: str
    display_name: str
    supports_send: bool
    supports_templated_payload: bool


class AlertActionTemplatePreviewRequest(BaseModel):
    action_template_id: str | None = None
    title_template: str | None = Field(default=None, max_length=2000)
    body_template: str | None = Field(default=None, max_length=20_000)
    payload_template: dict[str, Any] | None = None
    event_type: str = Field(default="alert_activated", min_length=1, max_length=64)
    alert_id: str | None = None
    repeater_id: str | None = None
    sample_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_ALERT_ACTION_EVENT_TYPES:
            allowed = ", ".join(sorted(VALID_ALERT_ACTION_EVENT_TYPES))
            raise ValueError(f"event_type must be one of: {allowed}")
        return normalized


class AlertActionTemplatePreviewResponse(BaseModel):
    event_type: str
    title: str | None = None
    body: str | None = None
    payload: dict[str, Any]
    context: dict[str, Any]


class AlertActionIntegrationTestRequest(BaseModel):
    event_type: str = Field(default="alert_activated", min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    rendered_payload: dict[str, Any] | None = None

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_ALERT_ACTION_EVENT_TYPES:
            allowed = ", ".join(sorted(VALID_ALERT_ACTION_EVENT_TYPES))
            raise ValueError(f"event_type must be one of: {allowed}")
        return normalized


class AlertActionIntegrationTestResponse(BaseModel):
    status: str
    status_code: int | None = None
    provider_message_id: str | None = None
    response_body: str | None = None
    error: str | None = None


class AlertActionDeliveryResponse(BaseModel):
    id: str
    alert_id: str
    integration_id: str | None = None
    integration_name: str | None = None
    action_template_id: str | None = None
    action_template_name: str | None = None
    binding_id: str | None = None
    provider_type: str | None = None
    channel: str
    event_type: str
    status: str
    attempts: int
    next_attempt_at: datetime | None = None
    sent_at: datetime | None = None
    last_error: str | None = None
    response_status_code: int | None = None
    provider_message_id: str | None = None
    payload: dict[str, Any]
    rendered_payload: dict[str, Any] | None = None
    created_at: datetime


class AlertActionDeliverySummaryResponse(BaseModel):
    total: int
    queued: int
    sent: int
    failed: int
    by_provider_type: dict[str, int]

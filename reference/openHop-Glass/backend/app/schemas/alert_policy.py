from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

VALID_SCOPE_TYPES = {"global", "group", "node"}
VALID_RULE_TYPES = {
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


class NodeGroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class NodeGroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class NodeGroupMemberAddRequest(BaseModel):
    repeater_id: str


class NodeGroupMemberResponse(BaseModel):
    repeater_id: str
    node_name: str
    status: str
    last_inform_at: datetime | None = None


class NodeGroupResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    member_count: int
    created_at: datetime
    updated_at: datetime


class NodeGroupDetailResponse(NodeGroupResponse):
    members: list[NodeGroupMemberResponse]


class AlertPolicyTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    rule_type: str = Field(min_length=1, max_length=64)
    severity: str = Field(min_length=1, max_length=16)
    enabled: bool = True
    threshold_value: float | None = None
    window_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    offline_grace_seconds: int | None = Field(default=None, ge=5, le=7 * 24 * 60 * 60)
    cooldown_seconds: int = Field(default=0, ge=0, le=24 * 60 * 60)
    auto_resolve: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rule_type")
    @classmethod
    def validate_rule_type(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in VALID_RULE_TYPES:
            raise ValueError(f"rule_type must be one of: {', '.join(sorted(VALID_RULE_TYPES))}")
        return normalized


class AlertPolicyTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    severity: str | None = Field(default=None, min_length=1, max_length=16)
    enabled: bool | None = None
    threshold_value: float | None = None
    window_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    offline_grace_seconds: int | None = Field(default=None, ge=5, le=7 * 24 * 60 * 60)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=24 * 60 * 60)
    auto_resolve: bool | None = None
    config: dict[str, Any] | None = None


class AlertPolicyTemplateResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    rule_type: str
    severity: str
    enabled: bool
    threshold_value: float | None = None
    window_minutes: int | None = None
    offline_grace_seconds: int | None = None
    cooldown_seconds: int
    auto_resolve: bool
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AlertPolicyAssignmentCreateRequest(BaseModel):
    template_id: str
    scope_type: str
    scope_id: str | None = None
    priority: int = Field(default=100, ge=0, le=1000)
    enabled: bool = True

    @field_validator("scope_type")
    @classmethod
    def validate_scope_type(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in VALID_SCOPE_TYPES:
            raise ValueError(
                f"scope_type must be one of: {', '.join(sorted(VALID_SCOPE_TYPES))}"
            )
        return normalized


class AlertPolicyAssignmentUpdateRequest(BaseModel):
    priority: int | None = Field(default=None, ge=0, le=1000)
    enabled: bool | None = None


class AlertPolicyAssignmentResponse(BaseModel):
    id: str
    template_id: str
    template_name: str
    rule_type: str
    scope_type: str
    scope_id: str | None = None
    scope_name: str | None = None
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class EffectivePolicyItemResponse(BaseModel):
    rule_type: str
    template_id: str
    template_name: str
    severity: str
    threshold_value: float | None = None
    window_minutes: int | None = None
    offline_grace_seconds: int | None = None
    cooldown_seconds: int
    auto_resolve: bool
    config: dict[str, Any]
    source_scope_type: str
    source_scope_id: str | None = None
    source_scope_name: str | None = None
    priority: int


class EffectivePolicyResponse(BaseModel):
    repeater_id: str
    node_name: str
    policies: list[EffectivePolicyItemResponse]


class AlertPolicyEvaluationRequest(BaseModel):
    repeater_id: str | None = None


class AlertPolicyEvaluationResponse(BaseModel):
    evaluated_repeaters: int
    alerts_activated: int
    alerts_resolved: int

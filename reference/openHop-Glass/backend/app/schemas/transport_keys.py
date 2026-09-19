from datetime import datetime

from pydantic import BaseModel, Field, field_validator

VALID_FLOOD_POLICIES = {"allow", "deny"}


def _validate_flood_policy(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_FLOOD_POLICIES:
        raise ValueError("flood_policy must be 'allow' or 'deny'")
    return normalized


class TransportKeyGroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_group_id: str | None = None
    flood_policy: str = Field(default="allow", min_length=1, max_length=16)
    transport_key: str | None = Field(default=None, max_length=4096)
    sort_order: int = Field(default=100, ge=0, le=10000)

    @field_validator("flood_policy")
    @classmethod
    def validate_flood_policy(cls, value: str) -> str:
        return _validate_flood_policy(value)


class TransportKeyGroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_group_id: str | None = None
    flood_policy: str | None = Field(default=None, min_length=1, max_length=16)
    transport_key: str | None = Field(default=None, max_length=4096)
    sort_order: int | None = Field(default=None, ge=0, le=10000)

    @field_validator("flood_policy")
    @classmethod
    def validate_flood_policy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_flood_policy(value)


class TransportKeyGroupMoveRequest(BaseModel):
    parent_group_id: str | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class TransportKeyGroupDeleteRequest(BaseModel):
    reassign_to_group_id: str | None = None


class TransportKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    group_id: str | None = None
    flood_policy: str = Field(default="allow", min_length=1, max_length=16)
    transport_key: str | None = Field(default=None, max_length=4096)
    sort_order: int = Field(default=100, ge=0, le=10000)

    @field_validator("flood_policy")
    @classmethod
    def validate_flood_policy(cls, value: str) -> str:
        return _validate_flood_policy(value)


class TransportKeyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    group_id: str | None = None
    flood_policy: str | None = Field(default=None, min_length=1, max_length=16)
    transport_key: str | None = Field(default=None, max_length=4096)
    sort_order: int | None = Field(default=None, ge=0, le=10000)

    @field_validator("flood_policy")
    @classmethod
    def validate_flood_policy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_flood_policy(value)


class TransportKeyGroupResponse(BaseModel):
    id: str
    name: str
    parent_group_id: str | None = None
    flood_policy: str
    transport_key: str | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TransportKeyResponse(BaseModel):
    id: str
    name: str
    group_id: str | None = None
    flood_policy: str
    transport_key: str | None = None
    sort_order: int
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TransportKeyTreeNodeResponse(BaseModel):
    id: str
    kind: str
    name: str
    flood_policy: str
    transport_key: str | None = None
    parent_id: str | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class TransportKeySyncStatusResponse(BaseModel):
    repeater_id: str
    node_name: str
    status: str
    payload_hash: str | None = None
    command_id: str | None = None
    error_message: str | None = None
    queued_at: datetime | None = None
    dispatched_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


class TransportKeyTreeResponse(BaseModel):
    nodes: list[TransportKeyTreeNodeResponse]
    sync_status: list[TransportKeySyncStatusResponse]


class TransportKeySyncTriggerResponse(BaseModel):
    payload_hash: str
    queued_commands: int
    skipped_commands: int


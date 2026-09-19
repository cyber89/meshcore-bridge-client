from datetime import datetime

from pydantic import BaseModel, Field


class ManagedMqttSettingsResponse(BaseModel):
    mqtt_enabled: bool
    mqtt_broker_host: str
    mqtt_broker_port: int
    mqtt_base_topic: str
    mqtt_tls_enabled: bool
    source: str
    updated_at: datetime | None = None


class ManagedMqttSettingsUpdateRequest(BaseModel):
    mqtt_enabled: bool
    mqtt_broker_host: str = Field(min_length=1, max_length=255)
    mqtt_broker_port: int = Field(ge=1, le=65535)
    mqtt_base_topic: str = Field(min_length=1, max_length=255)
    mqtt_tls_enabled: bool
    queue_to_repeaters: bool = False
    reason: str | None = Field(default=None, max_length=256)


class ManagedMqttSettingsUpdateResponse(BaseModel):
    settings: ManagedMqttSettingsResponse
    queued_commands: int


class ConfigSnapshotEncryptionSettingsResponse(BaseModel):
    configured: bool
    source: str
    key_ids: list[str]
    updated_at: datetime | None = None


class ConfigSnapshotEncryptionSettingsUpdateRequest(BaseModel):
    encryption_keys: str = Field(min_length=1, max_length=32768)
    reason: str | None = Field(default=None, max_length=256)


class ConfigSnapshotEncryptionKeyGenerateRequest(BaseModel):
    key_id: str | None = Field(default=None, min_length=1, max_length=64)
    replace_existing: bool = False
    reason: str | None = Field(default=None, max_length=256)


class ConfigSnapshotEncryptionKeyGenerateResponse(BaseModel):
    settings: ConfigSnapshotEncryptionSettingsResponse
    generated_entry: str

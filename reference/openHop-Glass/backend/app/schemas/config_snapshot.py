from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ConfigSnapshotExportRequest(BaseModel):
    repeater_id: str | None = Field(default=None, min_length=1, max_length=64)
    node_name: str | None = Field(default=None, min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_target(self) -> "ConfigSnapshotExportRequest":
        if not self.repeater_id and not self.node_name:
            raise ValueError("Either repeater_id or node_name is required.")
        return self


class ConfigSnapshotExportQueuedResponse(BaseModel):
    command_id: str
    repeater_id: str
    node_name: str
    status: str
    queued_at: datetime


class ConfigSnapshotResponse(BaseModel):
    id: str
    repeater_id: str
    node_name: str
    command_id: str | None
    captured_at: datetime
    created_at: datetime
    encryption_key_id: str
    payload_sha256: str
    payload_size_bytes: int


class ConfigSnapshotDetailResponse(ConfigSnapshotResponse):
    payload: dict[str, Any]

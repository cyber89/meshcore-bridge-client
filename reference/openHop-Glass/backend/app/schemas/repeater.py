from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RepeaterCreateRequest(BaseModel):
    node_name: str = Field(min_length=1, max_length=128)
    pubkey: str = Field(min_length=16, max_length=130)
    status: str = Field(default="pending_adoption", min_length=1, max_length=32)
    firmware_version: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=255)


class RepeaterUpdateRequest(BaseModel):
    status: str | None = Field(default=None, min_length=1, max_length=32)
    firmware_version: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    config_hash: str | None = Field(default=None, max_length=80)
    last_inform_at: datetime | None = None


class RepeaterResponse(BaseModel):
    id: str
    node_name: str
    pubkey: str
    status: str
    firmware_version: str | None = None
    location: str | None = None
    config_hash: str | None = None
    last_inform_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InformSnapshotPointResponse(BaseModel):
    timestamp: datetime
    cpu: float | None = None
    memory: float | None = None
    disk: float | None = None
    uptime_seconds: int | None = None
    noise_floor: float | None = None
    rx_total: int | None = None
    tx_total: int | None = None
    forwarded: int | None = None
    dropped: int | None = None
    airtime_percent: float | None = None

class RepeaterCertDiagnosticLogResponse(BaseModel):
    timestamp: datetime
    severity: str
    source: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RepeaterDetailResponse(RepeaterResponse):
    state: str | None = None
    system: dict[str, Any] | None = None
    radio: dict[str, Any] | None = None
    counters: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    snapshots: list[InformSnapshotPointResponse] = Field(default_factory=list)
    cert_diagnostics: list[RepeaterCertDiagnosticLogResponse] = Field(default_factory=list)


class DeleteStaleRepeatersResponse(BaseModel):
    removed: int


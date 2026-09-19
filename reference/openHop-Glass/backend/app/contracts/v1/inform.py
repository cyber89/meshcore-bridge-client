from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.contracts.v1.common import HexPublicKey, NodeName, Sha256Hash


class InformSystemStatsV1(BaseModel):
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)
    temperature_c: Optional[float] = None
    load_avg_1m: Optional[float] = None


class InformRadioStatsV1(BaseModel):
    frequency: int = Field(gt=0)
    spreading_factor: int = Field(ge=5, le=12)
    bandwidth: int = Field(gt=0)
    tx_power: int = Field(ge=0, le=30)
    noise_floor_dbm: Optional[float] = None
    mode: Optional[Literal["forward", "monitor", "no_tx"]] = None


class InformCountersV1(BaseModel):
    rx_total: int = Field(ge=0)
    tx_total: int = Field(ge=0)
    forwarded: int = Field(ge=0)
    dropped: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    airtime_percent: float = Field(ge=0, le=100)


class CommandResultPayloadV1(BaseModel):
    command_id: str = Field(min_length=1, max_length=64)
    status: Literal["success", "failed", "partial"]
    message: Optional[str] = Field(default=None, max_length=1024)
    completed_at: datetime
    details: Dict[str, Any] = Field(default_factory=dict)


class InformRequestV1(BaseModel):
    type: Literal["inform"] = "inform"
    version: Literal[1] = 1
    node_name: NodeName
    pubkey: HexPublicKey
    software_version: str = Field(min_length=1, max_length=64)
    state: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=255)
    uptime_seconds: int = Field(ge=0)
    config_hash: Sha256Hash
    cert_expires_at: Optional[datetime] = None
    system: InformSystemStatsV1
    radio: InformRadioStatsV1
    counters: InformCountersV1
    settings: Dict[str, Any] = Field(default_factory=dict)
    command_results: List[CommandResultPayloadV1] = Field(default_factory=list)


class InformNoopResponseV1(BaseModel):
    type: Literal["noop"] = "noop"
    interval: int = Field(default=30, ge=5, le=3600)
    status: Optional[Literal["pending_adoption", "rejected", "connected"]] = None


class InformConfigUpdateResponseV1(BaseModel):
    type: Literal["config_update"] = "config_update"
    config_hash: Sha256Hash
    merge_mode: Literal["patch", "replace"] = "patch"
    config: Dict[str, Any] = Field(default_factory=dict)


class InformCommandResponseV1(BaseModel):
    type: Literal["command"] = "command"
    command_id: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=64)
    params: Dict[str, Any] = Field(default_factory=dict)


class InformCertRenewalResponseV1(BaseModel):
    type: Literal["cert_renewal"] = "cert_renewal"
    client_cert: str
    client_key: str
    ca_cert: str


class InformUpgradeResponseV1(BaseModel):
    type: Literal["upgrade"] = "upgrade"
    version: str = Field(min_length=1, max_length=64)
    channel: str = Field(min_length=1, max_length=64)
    url: str
    sha256: str = Field(min_length=64, max_length=64)


InformResponseV1 = Union[
    InformNoopResponseV1,
    InformConfigUpdateResponseV1,
    InformCommandResponseV1,
    InformCertRenewalResponseV1,
    InformUpgradeResponseV1,
]


from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.contracts.v1.common import HexPublicKey, NodeName, RepeaterState


class RepeaterSummaryV1(BaseModel):
    node_name: NodeName
    pubkey: HexPublicKey
    state: RepeaterState
    software_version: str = Field(min_length=1, max_length=64)
    last_inform_at: Optional[datetime] = None
    last_ip: Optional[str] = None
    config_hash: Optional[str] = None


class AdoptionActionV1(BaseModel):
    node_name: NodeName
    action: str = Field(pattern=r"^(adopt|reject)$")
    requested_by: str = Field(min_length=1, max_length=128)
    note: Optional[str] = Field(default=None, max_length=512)


class AlertRecordV1(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    node_name: NodeName
    severity: str = Field(min_length=1, max_length=32)
    message: str = Field(min_length=1, max_length=1024)
    created_at: datetime
    resolved_at: Optional[datetime] = None


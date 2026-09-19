from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.contracts.v1.common import NodeName


class CommandAction(str, Enum):
    restart_service = "restart_service"
    config_update = "config_update"
    upgrade_firmware = "upgrade_firmware"
    set_radio = "set_radio"
    set_mode = "set_mode"
    send_advert = "send_advert"
    rotate_cert = "rotate_cert"
    set_inform_interval = "set_inform_interval"
    reboot = "reboot"
    export_config = "export_config"
    export_identity = "export_identity"
    run_diagnostic = "run_diagnostic"


class QueueCommandRequestV1(BaseModel):
    node_name: NodeName
    action: CommandAction
    params: Dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(min_length=1, max_length=128)
    reason: Optional[str] = Field(default=None, max_length=1024)


class QueueCommandResponseV1(BaseModel):
    command_id: str = Field(min_length=1, max_length=64)
    node_name: NodeName
    action: CommandAction
    status: str = "queued"
    queued_at: datetime


class CommandResultV1(BaseModel):
    command_id: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=32)
    message: Optional[str] = Field(default=None, max_length=1024)
    completed_at: datetime


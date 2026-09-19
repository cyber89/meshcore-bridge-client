from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CommandQueueItemResponse(BaseModel):
    command_id: str
    repeater_id: str
    node_name: str
    action: str
    status: str
    params: dict[str, Any]
    result: dict[str, Any] | None = None
    requested_by: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


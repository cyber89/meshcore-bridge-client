from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditRecordResponse(BaseModel):
    id: str
    user_id: str | None
    timestamp: datetime
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]


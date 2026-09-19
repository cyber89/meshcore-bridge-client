from datetime import datetime

from pydantic import BaseModel, Field


class AlertLifecycleRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class NotificationEventResponse(BaseModel):
    id: str
    channel: str
    event_type: str
    status: str
    attempts: int
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    sent_at: datetime | None = None


class AlertResponse(BaseModel):
    id: str
    repeater_id: str | None = None
    node_name: str | None = None
    timestamp: datetime
    alert_type: str
    severity: str
    message: str
    state: str
    first_seen_at: datetime
    last_seen_at: datetime
    fingerprint: str | None = None
    acked_at: datetime | None = None
    acked_by: str | None = None
    note: str | None = None
    resolved_at: datetime | None = None


class AlertDetailResponse(AlertResponse):
    notifications: list[NotificationEventResponse]


class AlertSummaryResponse(BaseModel):
    total: int
    active: int
    acknowledged: int
    suppressed: int
    resolved: int
    by_severity: dict[str, int]
    by_state: dict[str, int]

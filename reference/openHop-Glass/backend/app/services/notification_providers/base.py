from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class NotificationSendRequest:
    event_type: str
    payload: dict[str, Any]
    rendered_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class NotificationSendResult:
    status: str
    status_code: int | None = None
    provider_message_id: str | None = None
    response_body: str | None = None
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "sent"


@dataclass(slots=True)
class NotificationProviderCapability:
    provider_type: str
    display_name: str
    supports_send: bool
    supports_templated_payload: bool


class NotificationProvider(Protocol):
    capability: NotificationProviderCapability

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        ...

    def build_payload(self, request: NotificationSendRequest) -> dict[str, Any]:
        ...

    def send(
        self,
        *,
        settings: dict[str, Any],
        request: NotificationSendRequest,
    ) -> NotificationSendResult:
        ...

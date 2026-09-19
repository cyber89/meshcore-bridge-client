from __future__ import annotations
import json

from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from app.schemas.alert_actions import PushoverIntegrationSettings
from app.services.notification_providers.base import (
    NotificationProviderCapability,
    NotificationSendRequest,
    NotificationSendResult,
)


class PushoverNotificationProvider:
    capability = NotificationProviderCapability(
        provider_type="pushover",
        display_name="Pushover",
        supports_send=True,
        supports_templated_payload=True,
    )
    _PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
    _USER_AGENT = "pyMC_Glass/alert-actions"

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        validated = PushoverIntegrationSettings.model_validate(settings)
        return validated.model_dump(mode="json")

    def build_payload(self, request: NotificationSendRequest) -> dict[str, Any]:
        if request.rendered_payload is not None:
            return request.rendered_payload
        return {"event_type": request.event_type, "payload": request.payload}

    @staticmethod
    def _as_string(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return str(value)

    @staticmethod
    def _ensure_event_type_in_message(*, message: str, event_type: str) -> str:
        normalized_event_type = event_type.strip().lower()
        if not normalized_event_type:
            return message
        if normalized_event_type in message.lower():
            return message
        return f"[{event_type}] {message}"

    def _resolve_message(self, payload: dict[str, Any], request: NotificationSendRequest) -> str:
        for key in ("message", "body", "text"):
            resolved = self._as_string(payload.get(key))
            if resolved:
                return self._ensure_event_type_in_message(
                    message=resolved,
                    event_type=request.event_type,
                )
        fallback_payload = request.payload or payload
        if fallback_payload:
            fallback_message = json.dumps(
                fallback_payload,
                default=str,
                separators=(",", ":"),
                sort_keys=True,
            )
            return self._ensure_event_type_in_message(
                message=fallback_message,
                event_type=request.event_type,
            )
        return f"[{request.event_type}] Alert event"

    def send(
        self,
        *,
        settings: dict[str, Any],
        request: NotificationSendRequest,
    ) -> NotificationSendResult:
        validated = PushoverIntegrationSettings.model_validate(settings)
        payload = self.build_payload(request)

        form_payload: dict[str, str] = {
            "token": validated.app_token,
            "user": validated.user_key,
            "message": self._resolve_message(payload, request),
        }
        title = self._as_string(payload.get("title"))
        if title:
            form_payload["title"] = title
        url = self._as_string(payload.get("url"))
        if url:
            form_payload["url"] = url
        url_title = self._as_string(payload.get("url_title"))
        if url_title:
            form_payload["url_title"] = url_title
        timestamp = payload.get("timestamp")
        if timestamp is not None:
            form_payload["timestamp"] = str(timestamp)
        html = payload.get("html")
        if html is not None:
            form_payload["html"] = "1" if bool(html) else "0"

        priority = payload.get("priority", validated.priority)
        form_payload["priority"] = str(priority)
        sound = self._as_string(payload.get("sound")) or validated.sound
        if sound:
            form_payload["sound"] = sound
        device = self._as_string(payload.get("device")) or validated.device
        if device:
            form_payload["device"] = device

        encoded_body = urllib_parse.urlencode(form_payload).encode("utf-8")
        request_obj = urllib_request.Request(
            url=self._PUSHOVER_API_URL,
            data=encoded_body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self._USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(request_obj, timeout=15) as response:
                status_code = int(response.getcode())
                response_body = response.read(4096).decode("utf-8", errors="replace")
                response_json: dict[str, Any] = {}
                try:
                    parsed = json.loads(response_body) if response_body else {}
                    if isinstance(parsed, dict):
                        response_json = parsed
                except json.JSONDecodeError:
                    response_json = {}
                provider_message_id = self._as_string(response_json.get("request"))
                status_value = response_json.get("status")
                if 200 <= status_code < 300 and status_value in (None, 1, "1", True):
                    return NotificationSendResult(
                        status="sent",
                        status_code=status_code,
                        provider_message_id=provider_message_id,
                        response_body=response_body or None,
                    )
                errors = response_json.get("errors")
                if isinstance(errors, list) and errors:
                    error_message = "; ".join(str(item) for item in errors)
                else:
                    error_message = f"Pushover returned non-success status: {status_code}"
                return NotificationSendResult(
                    status="failed",
                    status_code=status_code,
                    provider_message_id=provider_message_id,
                    response_body=response_body or None,
                    error=error_message,
                )
        except urllib_error.HTTPError as exc:
            response_body = exc.read(4096).decode("utf-8", errors="replace")
            return NotificationSendResult(
                status="failed",
                status_code=exc.code,
                response_body=response_body or None,
                error=f"Pushover request failed with HTTP {exc.code}",
            )
        except urllib_error.URLError as exc:
            return NotificationSendResult(status="failed", error=f"Pushover request failed: {exc.reason}")
        except TimeoutError:
            return NotificationSendResult(status="failed", error="Pushover request timed out")

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from app.schemas.alert_actions import (
    VALID_APPRISE_FORMATS,
    VALID_APPRISE_NOTIFY_TYPES,
    AppriseIntegrationSettings,
)
from app.services.notification_providers.base import (
    NotificationProviderCapability,
    NotificationSendRequest,
    NotificationSendResult,
)


class AppriseNotificationProvider:
    capability = NotificationProviderCapability(
        provider_type="apprise",
        display_name="Apprise",
        supports_send=True,
        supports_templated_payload=True,
    )
    _USER_AGENT = "pyMC_Glass/alert-actions"

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        validated = AppriseIntegrationSettings.model_validate(settings)
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
    def _normalize_urls(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def _ensure_event_type_in_body(*, body: str, event_type: str) -> str:
        normalized_event_type = event_type.strip().lower()
        if not normalized_event_type:
            return body
        if normalized_event_type in body.lower():
            return body
        return f"[{event_type}] {body}"

    def _resolve_body(self, *, payload: dict[str, Any], request: NotificationSendRequest) -> str:
        for key in ("body", "message", "text"):
            resolved = self._as_string(payload.get(key))
            if resolved:
                return self._ensure_event_type_in_body(
                    body=resolved,
                    event_type=request.event_type,
                )
        fallback_payload = request.payload or payload
        if fallback_payload:
            fallback_body = json.dumps(
                fallback_payload,
                default=str,
                separators=(",", ":"),
                sort_keys=True,
            )
            return self._ensure_event_type_in_body(
                body=fallback_body,
                event_type=request.event_type,
            )
        return f"[{request.event_type}] Alert event"

    @staticmethod
    def _resolve_notify_type(*, payload: dict[str, Any], default_notify_type: str) -> str:
        candidate = payload.get("type", payload.get("notify_type", default_notify_type))
        normalized = str(candidate).strip().lower() if candidate is not None else default_notify_type
        if normalized in VALID_APPRISE_NOTIFY_TYPES:
            return normalized
        return default_notify_type

    @staticmethod
    def _resolve_format(*, payload: dict[str, Any], default_format: str | None) -> str | None:
        candidate = payload.get("format", default_format)
        if candidate is None:
            return None
        normalized = str(candidate).strip().lower()
        if not normalized:
            return None
        if normalized in VALID_APPRISE_FORMATS:
            return normalized
        return default_format

    @staticmethod
    def _is_stateless_endpoint(url: str) -> bool:
        path = urllib_parse.urlparse(url).path.rstrip("/")
        return path.endswith("/notify")

    @staticmethod
    def _build_ssl_context(*, verify_tls: bool) -> ssl.SSLContext | None:
        if verify_tls:
            return None
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    @staticmethod
    def _extract_error_message(response_body: str | None) -> str | None:
        if not response_body:
            return None
        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        for key in ("error", "message", "detail"):
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(item) for item in errors)
        return None

    def send(
        self,
        *,
        settings: dict[str, Any],
        request: NotificationSendRequest,
    ) -> NotificationSendResult:
        validated = AppriseIntegrationSettings.model_validate(settings)
        payload = self.build_payload(request)
        request_payload: dict[str, Any] = {
            "body": self._resolve_body(payload=payload, request=request),
        }

        title = self._as_string(payload.get("title"))
        if title:
            request_payload["title"] = title
        notify_type = self._resolve_notify_type(
            payload=payload,
            default_notify_type=validated.notify_type,
        )
        request_payload["type"] = notify_type
        body_format = self._resolve_format(payload=payload, default_format=validated.format)
        if body_format:
            request_payload["format"] = body_format
        tag = self._as_string(payload.get("tag")) or validated.tag
        if tag:
            request_payload["tag"] = tag
        urls = self._normalize_urls(payload.get("urls"))
        if not urls:
            urls = self._normalize_urls(payload.get("url"))
        if not urls:
            urls = validated.urls
        if urls:
            request_payload["urls"] = urls

        endpoint_url = str(validated.api_url)
        if self._is_stateless_endpoint(endpoint_url) and not urls:
            return NotificationSendResult(
                status="failed",
                error="Apprise stateless endpoint requires at least one URL destination",
            )

        encoded_body = json.dumps(
            request_payload,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self._USER_AGENT,
        }
        headers.update(validated.headers)
        request_obj = urllib_request.Request(
            url=endpoint_url,
            data=encoded_body,
            headers=headers,
            method="POST",
        )
        ssl_context = self._build_ssl_context(verify_tls=validated.verify_tls)
        try:
            with urllib_request.urlopen(
                request_obj,
                timeout=validated.timeout_seconds,
                context=ssl_context,
            ) as response:
                status_code = int(response.getcode())
                response_body = response.read(4096).decode("utf-8", errors="replace")
                if 200 <= status_code < 300:
                    return NotificationSendResult(
                        status="sent",
                        status_code=status_code,
                        response_body=response_body or None,
                    )
                error_message = self._extract_error_message(response_body)
                return NotificationSendResult(
                    status="failed",
                    status_code=status_code,
                    response_body=response_body or None,
                    error=error_message or f"Apprise returned non-success status: {status_code}",
                )
        except urllib_error.HTTPError as exc:
            response_body = exc.read(4096).decode("utf-8", errors="replace")
            error_message = self._extract_error_message(response_body)
            return NotificationSendResult(
                status="failed",
                status_code=exc.code,
                response_body=response_body or None,
                error=error_message or f"Apprise request failed with HTTP {exc.code}",
            )
        except urllib_error.URLError as exc:
            return NotificationSendResult(status="failed", error=f"Apprise request failed: {exc.reason}")
        except TimeoutError:
            return NotificationSendResult(status="failed", error="Apprise request timed out")

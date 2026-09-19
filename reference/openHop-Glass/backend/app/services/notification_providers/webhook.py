from __future__ import annotations

import json
import ssl
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.schemas.alert_actions import WebhookIntegrationSettings
from app.services.notification_providers.base import (
    NotificationProviderCapability,
    NotificationSendRequest,
    NotificationSendResult,
)


class WebhookNotificationProvider:
    capability = NotificationProviderCapability(
        provider_type="webhook",
        display_name="Webhook",
        supports_send=True,
        supports_templated_payload=True,
    )

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        validated = WebhookIntegrationSettings.model_validate(settings)
        return validated.model_dump(mode="json")

    def build_payload(self, request: NotificationSendRequest) -> dict[str, Any]:
        if request.rendered_payload is not None:
            return request.rendered_payload
        return {"event_type": request.event_type, "payload": request.payload}

    def send(
        self,
        *,
        settings: dict[str, Any],
        request: NotificationSendRequest,
    ) -> NotificationSendResult:
        validated = WebhookIntegrationSettings.model_validate(settings)
        payload = self.build_payload(request)
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
        if len(body) > validated.max_body_bytes:
            return NotificationSendResult(
                status="failed",
                error=(
                    "Rendered payload exceeded max_body_bytes "
                    f"({len(body)} > {validated.max_body_bytes})"
                ),
            )

        headers = {"Content-Type": "application/json", "User-Agent": "pyMC_Glass/alert-actions"}
        headers.update(validated.headers)
        request_obj = urllib_request.Request(
            url=str(validated.url),
            data=body,
            headers=headers,
            method=validated.method,
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
                return NotificationSendResult(
                    status="failed",
                    status_code=status_code,
                    response_body=response_body or None,
                    error=f"Webhook returned non-success status: {status_code}",
                )
        except urllib_error.HTTPError as exc:
            response_body = exc.read(4096).decode("utf-8", errors="replace")
            return NotificationSendResult(
                status="failed",
                status_code=exc.code,
                response_body=response_body or None,
                error=f"Webhook request failed with HTTP {exc.code}",
            )
        except urllib_error.URLError as exc:
            return NotificationSendResult(status="failed", error=f"Webhook request failed: {exc.reason}")
        except TimeoutError:
            return NotificationSendResult(status="failed", error="Webhook request timed out")

    @staticmethod
    def _build_ssl_context(*, verify_tls: bool) -> ssl.SSLContext | None:
        if verify_tls:
            return None
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

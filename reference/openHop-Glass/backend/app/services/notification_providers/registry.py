from __future__ import annotations

from typing import Any, Iterable

from app.services.notification_providers.base import (
    NotificationProvider,
    NotificationProviderCapability,
    NotificationSendRequest,
    NotificationSendResult,
)
from app.services.notification_providers.apprise import AppriseNotificationProvider
from app.services.notification_providers.pushover import PushoverNotificationProvider
from app.services.notification_providers.webhook import WebhookNotificationProvider


class NotificationProviderRegistry:
    def __init__(self, providers: Iterable[NotificationProvider] | None = None):
        self._providers: dict[str, NotificationProvider] = {}
        if providers is None:
            providers = (
                WebhookNotificationProvider(),
                PushoverNotificationProvider(),
                AppriseNotificationProvider(),
            )
        for provider in providers:
            self.register(provider)

    def register(self, provider: NotificationProvider) -> None:
        provider_type = provider.capability.provider_type.strip().lower()
        if provider_type in self._providers:
            raise ValueError(f"Notification provider already registered: {provider_type}")
        self._providers[provider_type] = provider

    def get_provider(self, provider_type: str) -> NotificationProvider:
        normalized = provider_type.strip().lower()
        provider = self._providers.get(normalized)
        if provider is None:
            raise KeyError(f"Unsupported notification provider: {normalized}")
        return provider

    def list_provider_types(self) -> list[str]:
        return sorted(self._providers.keys())

    def list_capabilities(self) -> list[NotificationProviderCapability]:
        return sorted(
            (provider.capability for provider in self._providers.values()),
            key=lambda item: item.provider_type,
        )

    def validate_settings(self, provider_type: str, settings: dict[str, Any]) -> dict[str, Any]:
        provider = self.get_provider(provider_type)
        return provider.validate_settings(settings)

    def send(
        self,
        *,
        provider_type: str,
        settings: dict[str, Any],
        request: NotificationSendRequest,
    ) -> NotificationSendResult:
        provider = self.get_provider(provider_type)
        return provider.send(settings=settings, request=request)

"""Framework-neutral seam shared by the native server and future ASGI transport."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from src.web.api_router import WebAPIRouter


class WebServerProtocol(Protocol):
    """Preserve existing lifecycle, event-history and shared-channel consumers."""

    router: WebAPIRouter
    bridge: Any

    async def start(self) -> None:
        """Return after the listener is ready, or propagate its startup failure."""
        ...

    async def stop(self) -> None:
        """Stop this transport without stopping the bridge or its radio."""
        ...

    async def broadcast_event(self, event_data: dict[str, Any]) -> None:
        """Record an event once, then deliver it to this transport's clients."""
        ...

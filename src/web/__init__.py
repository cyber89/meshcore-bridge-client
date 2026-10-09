"""
MeshCore Web Client & Embedded Server Package.
Proporciona servidor HTTP asíncrono y WebSocket Hub para la interfaz SPA de MeshCore Bridge.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.web.api_router import WebAPIRouter
    from src.web.asgi_server import AsgiWebServer
    from src.web.http_server import MeshCoreWebServer

__all__ = ["AsgiWebServer", "MeshCoreWebServer", "WebAPIRouter"]


def __getattr__(name: str) -> Any:
    """Load compatibility exports only when the web component is requested."""
    if name == "AsgiWebServer":
        from src.web.asgi_server import AsgiWebServer

        return AsgiWebServer
    if name == "MeshCoreWebServer":
        from src.web.http_server import MeshCoreWebServer

        return MeshCoreWebServer
    if name == "WebAPIRouter":
        from src.web.api_router import WebAPIRouter

        return WebAPIRouter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

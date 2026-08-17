"""
MeshCore Web Client & Embedded Server Package.
Proporciona servidor HTTP asíncrono y WebSocket Hub para la interfaz SPA de MeshCore Bridge.
"""

from src.web.api_router import WebAPIRouter
from src.web.http_server import MeshCoreWebServer

__all__ = ["MeshCoreWebServer", "WebAPIRouter"]

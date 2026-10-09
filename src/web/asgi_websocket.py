"""Per-connection logging policy for Uvicorn 0.54.0 WebSocket SansIO.

The upstream backend logs upgrade paths including queries even when HTTP access
logging is disabled. Keep authentication inputs intact and sanitize only the
instance's log arguments; no logger handlers or process-wide levels are changed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from uvicorn import Config
from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol
from uvicorn.server import ServerState

from src.web.asgi_logging import SafeProtocolLogger


class BridgeWebSocketProtocol(WebSocketsSansIOProtocol):
    """Retain SansIO behavior with a private logging adapter for this connection."""

    def __init__(
        self,
        config: Config,
        server_state: ServerState,
        app_state: dict[str, Any],
        _loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__(config, server_state, app_state, _loop)
        safe_logger = SafeProtocolLogger(self.logger, {})
        # Upstream annotates self.logger as Logger but uses this adapter's .level,
        # .info/.error/.exception and .log interfaces. The cast confines that
        # version-specific annotation boundary; it does not change the object.
        self.logger = cast(logging.Logger, safe_logger)
        self.conn.logger = safe_logger
        # websockets 16.1.1 caches DEBUG availability in its constructor, before
        # the private adapter can replace the logger assigned by Uvicorn.
        self.conn.debug = False

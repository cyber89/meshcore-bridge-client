"""Transport-neutral, per-instance logging for the evaluated ASGI protocols.

Keep stack frames and exception types while omitting exception messages that can
contain body values or credentials. No framework, handler or global level changes.
"""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType
from typing import TYPE_CHECKING, Any

from src.web.access_policy import safe_log_path

if TYPE_CHECKING:
    _BaseLoggerAdapter = logging.LoggerAdapter[logging.Logger]
else:
    _BaseLoggerAdapter = logging.LoggerAdapter

_UPGRADE_LOG_PATTERNS = frozenset(
    (
        '%s - "WebSocket %s" [accepted]',
        '%s - "WebSocket %s" 403',
        '%s - "WebSocket %s" %d',
    )
)
_INVALID_RESULT_LOG = "ASGI callable should return None, but returned '%s'."


class SafeProtocolLogger(_BaseLoggerAdapter):
    """Suppress frame/header tracing and retain error frames without raw values."""

    @property
    def level(self) -> int:
        # Uvicorn accesses .level directly; LoggerAdapter does not provide it.
        effective = self.logger.getEffectiveLevel()
        return max(logging.INFO, int(effective))

    def isEnabledFor(self, level: int) -> bool:  # noqa: N802 - stdlib logger interface
        return level >= logging.INFO and self.logger.isEnabledFor(level)

    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
        if not self.isEnabledFor(level):
            return
        if isinstance(msg, str) and msg in _UPGRADE_LOG_PATTERNS and len(args) >= 2:
            # The second interpolation argument is the upstream URL path/query.
            # The request scope still holds the untouched query for auth checks.
            args = (args[0], safe_log_path(str(args[1])), *args[2:])
        elif msg == _INVALID_RESULT_LOG:
            # An invalid app return value can itself contain request credentials.
            msg = "ASGI callable returned a value instead of None."
            args = ()

        exc_info = kwargs.get("exc_info")
        if exc_info:
            exception_type: type[BaseException] | None
            exception_traceback: TracebackType | None
            if isinstance(exc_info, BaseException):
                exception_type = type(exc_info)
                exception_traceback = exc_info.__traceback__
            elif isinstance(exc_info, tuple) and len(exc_info) == 3:
                exception_type, _, exception_traceback = exc_info
            else:
                exception_type, _, exception_traceback = sys.exc_info()
            # A validation exception's message can expose input values. Preserve
            # stack frames and exception type, without formatting that message or
            # passing the exception object to downstream logging handlers.
            frames = "".join(traceback.format_tb(exception_traceback))
            type_name = exception_type.__name__ if exception_type is not None else "unknown"
            msg = f"{msg}\nException type: {type_name}\n{frames}"
            kwargs["exc_info"] = False

        super().log(level, msg, *args, **kwargs)

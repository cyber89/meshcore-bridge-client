"""Production ASGI lifecycle foundation for the evaluated Uvicorn 0.54.0 stack.

This module provides the primary FastAPI/Uvicorn production server for MeshCore Bridge.
It registers REST, WebSocket, static, tile and OpenAPI documentation adapters.
"""

from __future__ import annotations

import asyncio
import logging
import math
import socket
from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI
from starlette.routing import WebSocketRoute
from starlette.types import ASGIApp
from uvicorn import Config, Server
from uvicorn.lifespan.on import LifespanOn

from src.web.access_policy import (
    HTTP_MAX_HEADER_BYTES,
    WS_MAX_PAYLOAD_BYTES,
)
from src.web.asgi_assets import install_asset_routes
from src.web.asgi_docs import install_documentation_routes
from src.web.asgi_errors import install_error_handlers
from src.web.asgi_http import BridgeH11Protocol
from src.web.asgi_openapi import build_openapi_schema
from src.web.asgi_routes import install_rest_routes
from src.web.asgi_security import BridgeSecurityMiddleware
from src.web.asgi_websocket import BridgeWebSocketProtocol
from src.web.asgi_ws_hub import WebSocketHub

if TYPE_CHECKING:
    from src.web.api_router import WebAPIRouter

logger = logging.getLogger(__name__)


class _SecuredFastAPI(FastAPI):
    """Place perimeter controls outside framework-generated error responses.

    The build hook is localized to the evaluated FastAPI 0.143 / Starlette 1.7
    stack. add_middleware alone would leave ServerErrorMiddleware outside the
    security-header wrapper. Re-audit the ordering on a framework update.
    """

    def build_middleware_stack(self) -> ASGIApp:
        return BridgeSecurityMiddleware(super().build_middleware_stack())


def create_asgi_app(
    router: WebAPIRouter, *, shutdown_budget_s: float, static_dir: Path | None = None
) -> FastAPI:
    """Borrow the existing context; construct neither services nor import-time tasks."""

    if not math.isfinite(shutdown_budget_s) or shutdown_budget_s <= 0:
        raise ValueError("shutdown_budget_s must be finite and positive")
    hub = WebSocketHub(router)

    @asynccontextmanager
    async def web_lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Uvicorn creates this task. Retain its identity so a cancelled startup
        # or shutdown can cancel this instance's lifespan, never unrelated tasks.
        app.state.web_lifespan_task = asyncio.current_task()
        try:
            await hub.start()
            yield
        finally:
            try:
                deadline = app.state.web_shutdown_deadline
                if deadline is None:
                    deadline = asyncio.get_running_loop().time() + shutdown_budget_s
                await hub.stop(deadline)
            finally:
                app.state.web_lifespan_task = None

    app = _SecuredFastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=web_lifespan,
    )
    install_error_handlers(app)
    install_rest_routes(app, router)
    # The native handshake accepts upgrades on any path, including API paths.
    # HTTP route adapters match HTTP scopes only; no WS path restriction is added.
    app.router.routes.append(WebSocketRoute("/{path:path}", hub.endpoint))
    install_documentation_routes(app, build_openapi_schema)
    install_asset_routes(app, router, static_dir)
    app.state.router = router
    app.state.api_context = router.api_ctx
    app.state.web_lifespan_task = None
    app.state.web_shutdown_deadline = None
    app.state.websocket_hub = hub
    return app


class _OwnedLifespan(LifespanOn):
    """Retain Uvicorn's lifespan task before its first scheduling opportunity.

    startup() mirrors uvicorn 0.54.0 uvicorn/lifespan/on.py:47-64, retaining the
    task that upstream only keeps in a local variable. This version-specific
    ownership change avoids leaking lifespan when startup is cancelled before
    the application enters its context. Re-audit this hook on a Uvicorn update.
    """

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.main_task: asyncio.Task[None] | None = None

    async def startup(self) -> None:
        self.logger.info("Waiting for application startup.")
        self.main_task = asyncio.create_task(self.main(), name="MeshCoreASGILifespan")
        await self.receive_queue.put({"type": "lifespan.startup"})
        await self.startup_event.wait()
        if self.startup_failed or (self.error_occurred and self.config.lifespan == "on"):
            self.logger.error("Application startup failed. Exiting.")
            self.should_exit = True
        else:
            self.logger.info("Application startup complete.")


class _EmbeddedUvicornServer(Server):
    """Localize the two Uvicorn 0.54 hooks used by the embedded lifecycle."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.ready = asyncio.Event()

    @contextmanager
    def capture_signals(self) -> Generator[None]:
        """Leave installation, restoration and re-emission of signals to the core."""
        yield

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        # serve() constructed the default lifespan without starting it. Replace
        # that inert object before super().startup() schedules any lifespan work.
        self.lifespan = _OwnedLifespan(self.config)
        await super().startup(sockets=sockets)
        if self.started:
            self.ready.set()


class AsgiWebServer:
    """Production FastAPI/Uvicorn server for MeshCore Bridge.

    REST endpoints and web adapters borrow the existing dispatcher and services.
    The metrics timer publishes passive web snapshots only.
    """

    def __init__(
        self,
        router: WebAPIRouter | Any = None,
        host: str = "0.0.0.0",  # nosec B104
        port: int = 8080,
        *,
        shutdown_budget_s: float = 1.5,
        on_failure: Callable[[Exception], None] | None = None,
        static_dir: Path | None = None,
        bridge: Any | None = None,
        owns_tile_service: bool | None = None,
    ) -> None:
        if not math.isfinite(shutdown_budget_s) or shutdown_budget_s <= 0:
            raise ValueError("shutdown_budget_s must be finite and positive")
        from src.web.api_router import WebAPIRouter

        if isinstance(router, WebAPIRouter):
            actual_router = router
            actual_bridge = router.bridge
            created_router = False
        elif bridge is not None:
            actual_bridge = bridge
            actual_router = WebAPIRouter(bridge)
            created_router = True
        elif router is not None:
            actual_bridge = router
            actual_router = WebAPIRouter(router)
            created_router = True
        else:
            raise ValueError("Either router or bridge must be provided")

        self.router = actual_router
        self.bridge = actual_bridge
        self.host = host
        self.port = port
        self.shutdown_budget_s = shutdown_budget_s
        self._static_dir = static_dir or (Path(__file__).resolve().parent / "static")
        self.app = create_asgi_app(
            actual_router, shutdown_budget_s=shutdown_budget_s, static_dir=self._static_dir
        )
        self.websocket_hub: WebSocketHub = self.app.state.websocket_hub
        self.tile_service = actual_router.map_tile_service
        self._owns_tile_service = created_router if owns_tile_service is None else owns_tile_service
        self._tiles_closed = False
        self._tile_operation_task: asyncio.Task[None] | None = None
        self._tile_operation_kind: str | None = None
        self._tile_tasks: set[asyncio.Task[None]] = set()
        self.running = False
        self.failure: Exception | None = None
        self._on_failure = on_failure
        self._server: _EmbeddedUvicornServer | None = None
        self._serve_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._pending_tasks: set[asyncio.Task[Any]] = set()
        self._start_lock = asyncio.Lock()
        self._stopping = False

    @property
    def static_dir(self) -> Path:
        adapter = getattr(self.app.state, "assets_adapter", None)
        if adapter is not None and getattr(adapter, "static_dir", None) is not None:
            return cast(Path, adapter.static_dir)
        return self._static_dir

    @static_dir.setter
    def static_dir(self, value: Path | str) -> None:
        path_val = Path(value) if isinstance(value, str) else value
        self._static_dir = path_val
        adapter = getattr(self.app.state, "assets_adapter", None)
        if adapter is not None:
            adapter.static_dir = path_val
            with adapter._cache_lock:
                adapter._cache.clear()

    @property
    def server(self) -> Any:
        """Expose underlying server socket interface for tests and telemetry."""
        if not self.running:
            return None
        if self._server is not None and getattr(self._server, "servers", None):
            return self._server.servers[0]
        return None

    @property
    def active_websockets(self) -> set[Any]:
        """Expose active websocket connections for tests and diagnostic inspection."""
        if hasattr(self, "websocket_hub"):
            return set(self.websocket_hub._peers.keys())
        return set()

    @property
    def system_logs(self) -> Any:
        """Expose recent system log buffer for diagnostic consumers and CLI."""
        return getattr(self.router, "recent_system_logs", None)

    def _retain_task(self, task: asyncio.Task[Any]) -> None:
        self._pending_tasks.add(task)
        task.add_done_callback(self._consume_task)

    def _consume_task(self, task: asyncio.Task[Any]) -> None:
        self._pending_tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _tile_operation_done(self, task: asyncio.Task[None]) -> None:
        self._tile_tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.error(
                    "ASGI map lifecycle failed: %s", type(error).__name__,
                    extra={"skip_broadcast": True},
                )

    def _start_tile_operation(self, kind: str) -> asyncio.Task[None]:
        """Serialize owned map workers; cancelling a waiter never cancels disk I/O."""
        previous = self._tile_operation_task
        if kind == "reload":
            # A partial reload can open connections before reporting failure.
            # Its cancellation/failure therefore always needs a later close.
            self._tiles_closed = False

        async def operate() -> None:
            if previous is not None:
                try:
                    await asyncio.shield(previous)
                except Exception:
                    # Its result callback already reports failures. A close
                    # must still follow a failed or interrupted reload attempt.
                    pass
            if kind == "close":
                await asyncio.to_thread(self.tile_service.close)
                self._tiles_closed = True
            else:
                await asyncio.to_thread(self.tile_service.reload_mbtiles)
                self._tiles_closed = False

        task = asyncio.create_task(operate(), name=f"MeshCoreASGIMap{kind.title()}")
        self._tile_operation_task = task
        self._tile_operation_kind = kind
        self._tile_tasks.add(task)
        self._retain_task(task)
        task.add_done_callback(self._tile_operation_done)
        return task

    def _schedule_tile_close(self) -> asyncio.Task[None] | None:
        if not self._owns_tile_service:
            return None
        previous = self._tile_operation_task
        if previous is not None and not previous.done() and self._tile_operation_kind == "close":
            return previous
        if self._tiles_closed and (previous is None or previous.done()):
            return None
        return self._start_tile_operation("close")

    def _serve_done(self, task: asyncio.Task[None]) -> None:
        unexpected = self.running and not self._stopping
        self.running = False
        if task.cancelled():
            error: Exception | None = RuntimeError("ASGI server was cancelled unexpectedly")
        else:
            task_error = task.exception()
            error = (
                task_error
                if isinstance(task_error, Exception) or task_error is None
                else RuntimeError(f"ASGI server failed: {type(task_error).__name__}")
            )
        if unexpected:
            failure = error or RuntimeError("ASGI server stopped unexpectedly")
            self.failure = failure
            self._force_close()
            logger.error(
                "Embedded ASGI server failed with %s", type(failure).__name__,
                extra={"skip_broadcast": True},
            )
            if self._on_failure is not None:
                try:
                    self._on_failure(failure)
                except Exception as callback_error:
                    logger.error(
                        "ASGI owner failure callback failed with %s",
                        type(callback_error).__name__,
                        extra={"skip_broadcast": True},
                    )

    async def _serve(self, server: _EmbeddedUvicornServer) -> None:
        try:
            # serve() uses the running loop; neither run() nor a new loop is used.
            await server.serve()
        except asyncio.CancelledError:
            raise
        except SystemExit as error:
            # Uvicorn uses sys.exit for bind/lifespan failures. A SystemExit must
            # never escape this task and terminate the bridge's event loop.
            raise RuntimeError(f"Uvicorn startup failed (exit {error.code})") from error
        except Exception:
            raise
        except BaseException as error:
            raise RuntimeError(f"ASGI server failed ({type(error).__name__})") from error
        finally:
            self._close_listeners(server)

    async def start(self) -> None:
        """Restore owned maps and wait for lifespan and listener readiness."""
        async with self._start_lock:
            if self.running:
                return
            if any(
                not task.done() for task in self._pending_tasks | self._server_tasks()
            ):
                raise RuntimeError("Previous ASGI lifecycle has not finished")
            self._stopping = False
            self.failure = None
            self._stop_task = None
            self.app.state.web_shutdown_deadline = None
            if self._owns_tile_service and (
                self._tiles_closed or self._tile_operation_kind == "close"
            ):
                try:
                    await asyncio.shield(self._start_tile_operation("reload"))
                except BaseException:
                    self._stopping = True
                    self._force_close()
                    raise
            if self._stopping:
                self._force_close()
                raise RuntimeError("ASGI startup interrupted by shutdown")
            self.router.resume_notifications()
            config = Config(
                self.app,
                host=self.host,
                port=self.port,
                loop="asyncio",
                http=BridgeH11Protocol,
                ws=BridgeWebSocketProtocol,
                lifespan="on",
                workers=1,
                reload=False,
                log_config=None,
                proxy_headers=False,
                access_log=False,
                server_header=False,
                date_header=False,
                h11_max_incomplete_event_size=HTTP_MAX_HEADER_BYTES,
                ws_max_size=WS_MAX_PAYLOAD_BYTES,
                ws_per_message_deflate=False,
                ws_ping_interval=None,
                ws_ping_timeout=None,
            )
            # 0.54 annotates this as int|None but passes it to asyncio.wait_for,
            # which accepts float seconds. Preserve the owner's existing 1.5 s
            # budget instead of rounding it or introducing a separate timeout.
            config.timeout_graceful_shutdown = self.shutdown_budget_s  # type: ignore[assignment]
            server = _EmbeddedUvicornServer(config)
            self._server = server
            task = asyncio.create_task(self._serve(server), name="MeshCoreASGIServer")
            self._serve_task = task
            self._retain_task(task)
            task.add_done_callback(self._serve_done)
            ready_waiter = asyncio.create_task(server.ready.wait(), name="MeshCoreASGIReadiness")
            self._retain_task(ready_waiter)
            try:
                await asyncio.wait((task, ready_waiter), return_when=asyncio.FIRST_COMPLETED)
                if task.done():
                    await task
                    raise RuntimeError("ASGI server terminated before readiness")
                if self._stopping or not server.started:
                    raise RuntimeError("ASGI startup interrupted by shutdown")
                self.running = True
                if self._server is not None and getattr(self._server, "servers", None):
                    sockets = getattr(self._server.servers[0], "sockets", None)
                    if sockets and len(sockets) > 0:
                        bound_port = sockets[0].getsockname()[1]
                        if self.port == 0:
                            self.port = bound_port
            except asyncio.CancelledError:
                self._stopping = True
                self._force_close()
                raise
            except Exception:
                await self.stop()
                raise
            finally:
                ready_waiter.cancel()

    async def wait_closed(self) -> None:
        """Let the owner observe later termination/failure without cancelling serve."""
        task = self._serve_task
        if task is not None:
            await asyncio.shield(task)
        if self.failure is not None:
            raise self.failure

    @staticmethod
    def _close_listeners(server: _EmbeddedUvicornServer) -> None:
        for listener in getattr(server, "servers", ()):
            listener.close()

    def _server_tasks(self) -> set[asyncio.Task[Any]]:
        tasks: set[asyncio.Task[Any]] = self.websocket_hub.owned_tasks()
        tasks.update(self.router.owned_notification_tasks())
        tasks.update(self._tile_tasks)
        if self._serve_task is not None:
            tasks.add(self._serve_task)
        if self._server is not None:
            tasks.update(self._server.server_state.tasks)
            lifespan = getattr(self._server, "lifespan", None)
            if isinstance(lifespan, _OwnedLifespan) and lifespan.main_task is not None:
                tasks.add(lifespan.main_task)
        lifespan_task = self.app.state.web_lifespan_task
        if isinstance(lifespan_task, asyncio.Task):
            tasks.add(lifespan_task)
        return tasks

    def _force_close(self) -> None:
        """Close resources synchronously even if the caller cancels stop()."""
        # Force cleanup must not give an endpoint's finally a fresh close budget.
        deadline = asyncio.get_running_loop().time()
        self.app.state.web_shutdown_deadline = deadline
        self.websocket_hub.force_stop(deadline=deadline)
        self.router.cancel_notifications()
        server = self._server
        if server is not None:
            server.should_exit = True
            server.force_exit = True
            self._close_listeners(server)
            for connection in list(server.server_state.connections):
                try:
                    connection.shutdown()
                    transport = getattr(connection, "transport", None)
                    if transport is not None:
                        transport.abort()
                except Exception as close_error:
                    logger.debug(
                        "ASGI forced closure failed with %s", type(close_error).__name__,
                        extra={"skip_broadcast": True},
                    )
        current = asyncio.current_task()
        for task in self._server_tasks():
            if task is not current and task not in self._tile_tasks and not task.done():
                self._retain_task(task)
                task.cancel()
        # Retain an off-loop closer even when the caller has no remaining
        # budget. Map workers cannot safely be force-cancelled while their
        # underlying thread still owns SQLite or the storage lock.
        self._schedule_tile_close()

    async def _shutdown(self, deadline: float) -> None:
        loop = asyncio.get_running_loop()
        server = self._server
        task = self._serve_task
        self.app.state.web_shutdown_deadline = deadline
        self.router.cancel_notifications()
        try:
            if server is not None:
                server.should_exit = True
                self._close_listeners(server)
            # Reject admission and abort peers before waiting on Uvicorn, whose
            # shutdown otherwise waits for those same WebSocket application tasks.
            await self.websocket_hub.stop(deadline)
            if task is not None and not task.done():
                await asyncio.wait({task}, timeout=max(0.0, deadline - loop.time()))
        finally:
            self._force_close()
        remaining = {owned for owned in self._server_tasks() if not owned.done()}
        if remaining:
            _, pending = await asyncio.wait(
                remaining, timeout=max(0.0, deadline - loop.time())
            )
            if pending:
                # Retained tasks already have cancellation requested and result
                # callbacks; refuse restart until they finish. Never extend the
                # owner's deadline waiting for cancellation-resistant handlers.
                logger.warning(
                    "ASGI tasks exceeded shutdown budget: %s", len(pending),
                    extra={"skip_broadcast": True},
                )

    async def stop(self) -> None:
        """Share one bounded cleanup; cancellation closes sockets and cancels owned tasks."""
        self.running = False
        self._stopping = True
        if self._stop_task is None or self._stop_task.cancelled():
            deadline = asyncio.get_running_loop().time() + self.shutdown_budget_s
            self._stop_task = asyncio.create_task(
                self._shutdown(deadline), name="MeshCoreASGIShutdown"
            )
            self._retain_task(self._stop_task)
        try:
            await asyncio.shield(self._stop_task)
        except asyncio.CancelledError:
            self._force_close()
            self._stop_task.cancel()
            raise
        # Keep server/map/task references until they finish. start() refuses a
        # new generation while any retained work remains, including map I/O.

    async def broadcast_event(self, event_data: dict[str, Any]) -> None:
        """Delegate history and event delivery once through the borrowed-state hub."""
        await self.websocket_hub.broadcast_event(event_data)

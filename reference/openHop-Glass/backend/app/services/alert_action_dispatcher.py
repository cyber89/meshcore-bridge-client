from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.alert_action_delivery import run_action_dispatch_batch
from app.services.notification_providers.registry import NotificationProviderRegistry

logger = logging.getLogger("alert-action-dispatcher")


class AlertActionDispatcherService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        provider_registry: NotificationProviderRegistry,
    ):
        self._enabled = settings.alert_action_dispatcher_enabled
        self._interval_seconds = max(1, settings.alert_action_dispatcher_interval_seconds)
        self._batch_size = max(1, settings.alert_action_dispatcher_batch_size)
        self._max_attempts = max(1, settings.alert_action_dispatcher_max_attempts)
        self._backoff_seconds = max(1, settings.alert_action_dispatcher_backoff_seconds)
        self._session_factory = session_factory
        self._provider_registry = provider_registry
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if not self._enabled:
            logger.info("Alert action dispatcher disabled via configuration")
            return
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._run_loop(),
            name="alert-action-dispatcher",
        )
        logger.info(
            "Alert action dispatcher started (interval=%ss, batch=%s, max_attempts=%s)",
            self._interval_seconds,
            self._batch_size,
            self._max_attempts,
        )

    async def stop(self) -> None:
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(self._dispatch_once)
            except Exception:
                logger.exception("Alert action dispatcher pass failed")
            try:
                await asyncio.sleep(self._interval_seconds)
            except asyncio.CancelledError:
                break

    def _dispatch_once(self) -> None:
        with self._session_factory() as db:
            try:
                processed = run_action_dispatch_batch(
                    db,
                    registry=self._provider_registry,
                    batch_size=self._batch_size,
                    max_attempts=self._max_attempts,
                    backoff_seconds=self._backoff_seconds,
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            if processed > 0:
                logger.debug("Alert action dispatcher processed %s queued event(s)", processed)


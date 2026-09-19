from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.alert_policy import evaluate_policies_for_fleet

logger = logging.getLogger("alert-policy-monitor")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AlertPolicyMonitorService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
    ):
        self._enabled = settings.alert_policy_monitor_enabled
        self._interval_seconds = max(15, settings.alert_policy_monitor_interval_seconds)
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if not self._enabled:
            logger.info("Alert policy monitor disabled via configuration")
            return
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="alert-policy-monitor")
        logger.info(
            "Alert policy monitor started (interval=%ss)",
            self._interval_seconds,
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
            started_at = _utc_now()
            try:
                await asyncio.to_thread(self._evaluate_once)
            except Exception:
                logger.exception("Alert policy monitor evaluation failed")
            elapsed_seconds = max(0, int((_utc_now() - started_at).total_seconds()))
            sleep_seconds = max(1, self._interval_seconds - elapsed_seconds)
            try:
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                break

    def _evaluate_once(self) -> None:
        with self._session_factory() as db:
            try:
                summary = evaluate_policies_for_fleet(db)
                db.commit()
            except Exception:
                db.rollback()
                raise
            logger.debug(
                "Alert policy monitor evaluated %s repeaters (activated=%s, resolved=%s)",
                summary.evaluated_repeaters,
                summary.alerts_activated,
                summary.alerts_resolved,
            )

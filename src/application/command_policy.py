"""
Command Policy and Idempotency Ledger Service (ADR 0021 / F1.2).
Handles command idempotency, conflict detection, and state tracking for integration commands.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.station_database import StationDatabase


class CommandStatus(StrEnum):
    ADMITTED = "admitted"
    DISPATCHING = "dispatching"
    COMPLETED = "completed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CommandReservation:
    """Outcome of attempting to admit a command into the station ledger."""

    admitted: bool
    status: CommandStatus
    is_legacy: bool
    command_id: str | None
    existing_result: dict[str, Any] | None = None
    error_message: str | None = None


class CommandLedgerPolicy:
    """Policy for checking and enforcing command idempotency via StationDatabase."""

    def __init__(self, database: StationDatabase | None, station_id: str | None = None) -> None:
        self.database = database
        self._station_id = station_id
        self._workers: set[asyncio.Task[Any]] = set()

    @property
    def station_id(self) -> str:
        if self._station_id:
            return self._station_id
        if self.database is None:
            raise RuntimeError("Command ledger is unavailable")
        self._station_id = self.database.get_station_id()
        return self._station_id

    async def _in_worker[T](self, callback: Callable[..., T], *args: Any) -> T:
        task = asyncio.create_task(asyncio.to_thread(callback, *args), name="CommandLedgerPersistence")
        self._workers.add(task)
        task.add_done_callback(self._worker_done)
        return await asyncio.shield(task)

    def _worker_done(self, task: asyncio.Task[Any]) -> None:
        self._workers.discard(task)
        if not task.cancelled():
            task.exception()

    async def drain(self) -> None:
        """Keep admitted SQLite workers owned through caller cancellation."""
        while self._workers:
            await asyncio.gather(*(asyncio.shield(task) for task in list(self._workers)), return_exceptions=True)

    async def reserve_async(
        self, integration_scope: str, command_id: str | None, action_type: str,
        semantic_payload: dict[str, Any],
    ) -> CommandReservation:
        return await self._in_worker(self.reserve, integration_scope, command_id, action_type, semantic_payload)

    async def mark_dispatching_async(self, integration_scope: str, command_id: str | None) -> None:
        await self._in_worker(self.mark_dispatching, integration_scope, command_id)

    async def record_result_async(
        self, integration_scope: str, command_id: str | None, status: CommandStatus,
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        await self._in_worker(self.record_result, integration_scope, command_id, status, result_payload)

    @staticmethod
    def compute_fingerprint(action_type: str, semantic_payload: dict[str, Any]) -> str:
        """Create a stable hash of the normalized semantic payload."""
        # Normalize fields: sort keys, omit ephemeral identifiers and timestamps
        filtered = {
            k: v
            for k, v in semantic_payload.items()
            if k not in ("request_id", "command_id", "id", "timestamp", "iso_time")
        }
        serialized = json.dumps(
            {"type": str(action_type).lower().strip(), "data": filtered},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]

    def reserve(
        self,
        integration_scope: str,
        command_id: str | None,
        action_type: str,
        semantic_payload: dict[str, Any],
    ) -> CommandReservation:
        """
        Reserve execution of a command.
        In legacy mode (no command_id), logs warning and allows execution without deduplication.
        In idempotent mode, verifies fingerprint and deduplicates.
        """
        if not command_id or not str(command_id).strip():
            logging.warning(
                "[MQTT-COMMAND] Legacy command without command_id (no deduplication guarantee)",
            )
            return CommandReservation(
                admitted=True,
                status=CommandStatus.ADMITTED,
                is_legacy=True,
                command_id=None,
            )

        cid = str(command_id).strip()
        if not self.database:
            return CommandReservation(
                admitted=False,
                status=CommandStatus.UNAVAILABLE,
                is_legacy=False,
                command_id=cid,
                error_message="Command ledger is unavailable; command was not dispatched",
            )

        fingerprint = self.compute_fingerprint(action_type, semantic_payload)
        try:
            admitted, status_str, prior_result = self.database.reserve_command(
                station_id=self.station_id,
                integration_scope=integration_scope,
                command_id=cid,
                fingerprint=fingerprint,
            )
        except Exception as e:
            logging.error("[MQTT-COMMAND] Command ledger reservation failed: %s", type(e).__name__)
            return CommandReservation(
                admitted=False,
                status=CommandStatus.UNAVAILABLE,
                is_legacy=False,
                command_id=cid,
                error_message="Command ledger is unavailable; command was not dispatched",
            )

        try:
            status = CommandStatus(status_str)
        except ValueError:
            status = CommandStatus.UNCERTAIN

        if not admitted:
            if status == CommandStatus.CONFLICT:
                logging.warning(
                    "[MQTT-COMMAND] Conflict detected for command_id=%s in scope=%s: payload fingerprint differs",
                    cid,
                    integration_scope,
                )
                return CommandReservation(
                    admitted=False,
                    status=CommandStatus.CONFLICT,
                    is_legacy=False,
                    command_id=cid,
                    error_message=f"Command ID {cid} already exists with different payload",
                )
            else:
                logging.info(
                    "[MQTT-COMMAND] Deduplicated command_id=%s in scope=%s: prior status=%s",
                    cid,
                    integration_scope,
                    status,
                )
                return CommandReservation(
                    admitted=False,
                    status=status,
                    is_legacy=False,
                    command_id=cid,
                    existing_result=prior_result,
                )

        return CommandReservation(
            admitted=True,
            status=CommandStatus.ADMITTED,
            is_legacy=False,
            command_id=cid,
        )

    def mark_dispatching(self, integration_scope: str, command_id: str | None) -> None:
        """Mark command as actively dispatching across the RF/SDK boundary."""
        if not command_id:
            return
        if self.database is None:
            raise RuntimeError("Command ledger is unavailable")
        try:
            self.database.update_command_status(
                station_id=self.station_id,
                integration_scope=integration_scope,
                command_id=str(command_id).strip(),
                status=CommandStatus.DISPATCHING.value,
            )
        except Exception as e:
            logging.error("[MQTT-COMMAND] Dispatch reservation failed: %s", type(e).__name__)
            raise RuntimeError("Command dispatch reservation failed") from None

    def record_result(
        self,
        integration_scope: str,
        command_id: str | None,
        status: CommandStatus,
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        """Record final outcome of an integration command."""
        if not command_id or not self.database:
            return
        try:
            self.database.update_command_status(
                station_id=self.station_id,
                integration_scope=integration_scope,
                command_id=str(command_id).strip(),
                status=status.value,
                result_payload=result_payload,
            )
        except Exception as e:
            logging.error("[MQTT-COMMAND] Result persistence failed: %s", type(e).__name__)

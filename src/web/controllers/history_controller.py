"""Durable chat history; operations never enqueue radio transmissions."""

from __future__ import annotations

import asyncio
from typing import Any

from src.station_database import StationDatabase, StationIdentityMismatch
from src.web.controllers.base import BaseController, problem_details


class HistoryController(BaseController):
    async def handle(self, method: str, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        database = getattr(self.ctx.bridge, "database", None)
        if not isinstance(database, StationDatabase):
            return problem_details(503, "Service Unavailable", "Station storage is unavailable", "storage_unavailable")
        try:
            if method == "GET" and path == "/api/messages/history":
                limit = self._integer(body.get("limit", 100), 1, 200)
                before = self._integer(body["before"], 1, None) if "before" in body else None
                feed = body.get("feed_key")
                if feed is not None and not isinstance(feed, str):
                    raise ValueError("Invalid feed key")
                data = await asyncio.to_thread(database.history, feed, limit, before)
            elif method == "GET" and path == "/api/messages/conversations":
                conversations = await asyncio.to_thread(database.conversations)
                page = await asyncio.to_thread(database.history, None, 1)
                data = {"conversations": conversations, "station_id": page["station_id"]}
            elif method == "POST" and path == "/api/messages/import":
                messages = body.get("messages")
                if not isinstance(messages, list) or not 1 <= len(messages) <= 200 or any(not isinstance(item, dict) for item in messages):
                    raise ValueError("Import requires between 1 and 200 message objects")
                station_id = body.get("station_id")
                if station_id is not None and not isinstance(station_id, str):
                    raise ValueError("Invalid station identity")
                data = await asyncio.to_thread(database.import_messages, messages, station_id=station_id)
            else:
                return problem_details(405, "Method Not Allowed", "Unsupported history operation", "method_not_allowed")
        except StationIdentityMismatch:
            return problem_details(409, "Conflict", "Station identity changed; reload before importing", "station_changed")
        except (ValueError, TypeError, OverflowError):
            return problem_details(422, "Unprocessable Entity", "Invalid history query or message batch", "invalid_history_input")
        return 200, {"status": "ok", "data": data}

    @staticmethod
    def _integer(value: Any, minimum: int, maximum: int | None) -> int:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("Integer required")
        result = int(value)
        if result < minimum or (maximum is not None and result > maximum):
            raise ValueError("Integer outside range")
        return result

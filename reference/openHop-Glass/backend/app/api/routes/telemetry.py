from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.db.models import User
from app.security.deps import get_current_user_bearer_or_query
from app.services.telemetry_stream import get_mqtt_telemetry_broadcaster

router = APIRouter(prefix="/api/telemetry")


def _format_sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    return f"event: {event}\ndata: {data}\n\n"


@router.get("/stream")
async def stream_mqtt_telemetry(
    request: Request,
    max_events: int | None = Query(default=None, ge=1, le=1000),
    current_user: User = Depends(get_current_user_bearer_or_query),
) -> StreamingResponse:
    if current_user.role not in {"admin", "operator", "viewer"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    broadcaster = get_mqtt_telemetry_broadcaster()
    queue = broadcaster.subscribe()

    async def _stream() -> AsyncGenerator[str, None]:
        emitted_events = 0
        yield _format_sse("ready", {"status": "connected"})
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _format_sse("mqtt_ingest", event)
                emitted_events += 1
                if max_events is not None and emitted_events >= max_events:
                    break
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

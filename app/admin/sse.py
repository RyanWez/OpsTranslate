"""Server-Sent Events (SSE) Broadcaster for real-time admin sync."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

log = logging.getLogger("opstranslate.admin.sse")


class EventBroadcaster:
    """Manages active SSE client streams and broadcasts real-time events."""

    def __init__(self) -> None:
        self._listeners: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._listeners.add(q)
        log.info("SSE client connected, active listeners: %d", len(self._listeners))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._listeners.discard(q)
        log.info("SSE client disconnected, active listeners: %d", len(self._listeners))

    def broadcast(self, event_type: str, data: Any) -> None:
        """Broadcast an event to all connected SSE clients."""
        if not self._listeners:
            return
        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
        message = f"event: {event_type}\ndata: {payload}\n\n"
        for q in list(self._listeners):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                self._listeners.discard(q)


broadcaster = EventBroadcaster()


async def sse_event_stream(q: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Stream events to client with 15-second keep-alive comments."""
    try:
        # Initial greeting
        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=15.0)
                yield msg
            except asyncio.TimeoutError:
                # Keep-alive comment to prevent proxy/tunnel timeout
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        broadcaster.unsubscribe(q)

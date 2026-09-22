"""Server-Sent Events (SSE) Broadcaster for real-time admin sync."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from starlette.requests import Request

log = logging.getLogger("opstranslate.admin.sse")


class EventBroadcaster:
    """Manages active SSE client streams and broadcasts real-time events."""

    def __init__(self) -> None:
        self._listeners: set[asyncio.Queue] = set()
        self._closing: bool = False

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        if self._closing:
            q.put_nowait(None)
            return q
        self._listeners.add(q)
        log.info("SSE client connected, active listeners: %d", len(self._listeners))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._listeners.discard(q)
        log.info("SSE client disconnected, active listeners: %d", len(self._listeners))

    def broadcast(self, event_type: str, data: Any) -> None:
        """Broadcast an event to all connected SSE clients."""
        if not self._listeners or self._closing:
            return
        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
        message = f"event: {event_type}\ndata: {payload}\n\n"
        for q in list(self._listeners):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                self._listeners.discard(q)

    def close(self) -> None:
        """Signal all active SSE streams to terminate immediately on shutdown."""
        self._closing = True
        log.info("Closing all SSE streams for shutdown (%d active)", len(self._listeners))
        for q in list(self._listeners):
            try:
                q.put_nowait(None)
            except Exception:
                pass
        self._listeners.clear()


broadcaster = EventBroadcaster()


async def sse_event_stream(q: asyncio.Queue, request: Request | None = None) -> AsyncGenerator[str, None]:
    """Stream events to client with keep-alive comments and disconnect detection."""
    try:
        # Initial greeting
        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
        while not broadcaster._closing:
            if request is not None and await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(q.get(), timeout=2.0)
                if msg is None:
                    break
                yield msg
            except asyncio.TimeoutError:
                if request is not None and await request.is_disconnected():
                    break
                # Keep-alive comment to prevent proxy/tunnel timeout
                yield ": keepalive\n\n"
    except (asyncio.CancelledError, GeneratorExit):
        pass
    finally:
        broadcaster.unsubscribe(q)

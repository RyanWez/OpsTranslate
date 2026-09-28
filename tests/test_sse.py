"""SSE broadcaster tests: subscribe/broadcast/close and the stream generator.

app/admin/sse.py drives every real-time admin update and had no coverage.
"""
import asyncio
import json

import pytest

from app.admin.sse import EventBroadcaster, broadcaster as global_broadcaster, sse_event_stream


def test_broadcast_delivers_formatted_event():
    b = EventBroadcaster()
    q = b.subscribe()
    b.broadcast("providers_changed", {"id": 5})
    msg = q.get_nowait()
    assert msg.startswith("event: providers_changed\n")
    payload = json.loads(msg.split("data: ", 1)[1].strip())
    assert payload == {"event": "providers_changed", "data": {"id": 5}}


def test_broadcast_without_listeners_is_noop():
    EventBroadcaster().broadcast("x", {"a": 1})  # must not raise


def test_unsubscribe_stops_delivery():
    b = EventBroadcaster()
    q = b.subscribe()
    b.unsubscribe(q)
    b.broadcast("x", {"a": 1})
    with pytest.raises(asyncio.QueueEmpty):
        q.get_nowait()


def test_close_signals_sentinel_and_disables():
    b = EventBroadcaster()
    q = b.subscribe()
    b.close()
    assert q.get_nowait() is None  # shutdown sentinel pushed to live streams
    # Subscribing after close hands back an already-terminated queue.
    assert b.subscribe().get_nowait() is None
    # Broadcast while closing is a no-op.
    b.broadcast("x", {})


def test_full_listener_queue_is_dropped():
    b = EventBroadcaster()
    q = b.subscribe()
    for _ in range(q.maxsize):
        q.put_nowait("filler")
    b.broadcast("x", {"n": 1})  # QueueFull -> listener discarded
    assert q not in b._listeners


async def test_stream_greeting_event_then_sentinel():
    # sse_event_stream reads the module-global broadcaster state.
    global_broadcaster._closing = False
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    global_broadcaster._listeners.add(q)
    gen = sse_event_stream(q, request=None)

    greeting = await gen.__anext__()
    assert "event: connected" in greeting

    q.put_nowait("event: users_changed\ndata: {}\n\n")
    assert "users_changed" in await gen.__anext__()

    q.put_nowait(None)  # shutdown sentinel terminates the stream
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert q not in global_broadcaster._listeners  # unsubscribed in finally

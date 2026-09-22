"""Sliding-window rate limiter: 2 messages per rolling 30 seconds, in-process.

In-process (not Redis) on purpose: a single instance serving <=120 users
needs no network round trip, and it consumes zero Upstash commands.
Swap in a Redis Lua script only if a second instance ever appears.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict, deque

from .. import config

WINDOW_S = 30.0
LIMIT = 2

_hits: dict[int, deque[float]] = defaultdict(deque)


def check(
    user_id: int,
    now: float | None = None,
    limit: int | None = None,
    window_s: float | None = None,
) -> int:
    """Return 0 if the message is allowed, else the seconds to wait.

    A rejected message never consumes a slot; callers must only call this
    for messages that passed Gates 1-7. The countdown reply itself must
    not call this function.
    """
    if not getattr(config, "RATE_LIMIT_ENABLED", True):
        return 0

    lim = limit if limit is not None else getattr(config, "RATE_LIMIT_COUNT", LIMIT)
    win = window_s if window_s is not None else getattr(config, "RATE_LIMIT_WINDOW_S", WINDOW_S)

    if lim <= 0:
        return 0

    now = time.monotonic() if now is None else now
    q = _hits[user_id]
    while q and now - q[0] >= win:
        q.popleft()  # evict entries outside the window
    if len(q) >= lim:
        return max(1, math.ceil(win - (now - q[0])))
    q.append(now)
    return 0


def reset(user_id: int | None = None) -> None:
    """Clear state (tests, or admin override)."""
    if user_id is None:
        _hits.clear()
    else:
        _hits.pop(user_id, None)

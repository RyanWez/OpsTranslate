"""In-memory runtime stats for /status and /healthz.

Always in-process (no Redis/DB needed). DB-backed aggregates can be added
later; these counters are what /status reports. Also tracks a 5-minute
sliding window for the watchdog (error rate, p95).
"""

from __future__ import annotations

import time
from collections import deque


class Stats:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.translations_ok = 0
        self.translations_failed = 0
        self.cache_hits = 0
        self.cache_lookups = 0
        self.policy_leaks = 0
        self.latencies: deque[float] = deque(maxlen=500)
        self.last_success_at: float = 0.0
        # Watchdog window: 5 minutes of events
        self._recent: deque[tuple[float, bool]] = deque(maxlen=1000)  # (ts, is_ok)
        self._recent_latencies: deque[tuple[float, float]] = deque(maxlen=500)  # (ts, latency)
        self.policy_engine_errors: int = 0
        self._recent_policy_errors: deque[float] = deque(maxlen=500)

    def record_ok(self, latency_s: float, cache_hit: bool) -> None:
        now = time.time()
        self.translations_ok += 1
        self.latencies.append(latency_s)
        self._recent.append((now, True))
        self._recent_latencies.append((now, latency_s))
        self.last_success_at = now
        self.cache_lookups += 1
        if cache_hit:
            self.cache_hits += 1

    def record_failure(self) -> None:
        self.translations_failed += 1
        self._recent.append((time.time(), False))

    def record_leak(self) -> None:
        self.policy_leaks += 1

    def record_policy_engine_error(self) -> None:
        self.policy_engine_errors += 1
        self._recent_policy_errors.append(time.time())

    @property
    def cache_hit_rate(self) -> float:
        if not self.cache_lookups:
            return 0.0
        return self.cache_hits / self.cache_lookups

    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]

    def last_success_within(self, seconds: float) -> bool:
        return (time.time() - self.last_success_at) <= seconds

    # -- watchdog helpers -------------------------------------------------
    def _window_events(self, window_s: float = 300) -> list[bool]:
        now = time.time()
        cutoff = now - window_s
        # purge old
        while self._recent and self._recent[0][0] < cutoff:
            self._recent.popleft()
        return [is_ok for _, is_ok in self._recent]

    def error_rate_5m(self) -> float:
        events = self._window_events(300)
        if not events:
            return 0.0
        failures = sum(1 for ok in events if not ok)
        return failures / len(events)

    def count_5m(self) -> int:
        return len(self._window_events(300))

    def p95_5m(self) -> float:
        now = time.time()
        cutoff = now - 300
        while self._recent_latencies and self._recent_latencies[0][0] < cutoff:
            self._recent_latencies.popleft()
        vals = [lat for _, lat in self._recent_latencies]
        if not vals:
            return 0.0
        vals.sort()
        return vals[min(len(vals) - 1, int(len(vals) * 0.95))]

    def policy_error_rate_5m(self) -> float:
        now = time.time()
        cutoff = now - 300
        while self._recent_policy_errors and self._recent_policy_errors[0] < cutoff:
            self._recent_policy_errors.popleft()
        total = len(self._window_events(300))
        if not total:
            return 0.0
        return len(self._recent_policy_errors) / total

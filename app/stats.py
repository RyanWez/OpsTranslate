"""In-memory runtime stats for /status and /healthz.

Always in-process (no Redis/DB needed). DB-backed aggregates can be added
later; these counters are what /status reports.
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

    def record_ok(self, latency_s: float, cache_hit: bool) -> None:
        self.translations_ok += 1
        self.latencies.append(latency_s)
        self.last_success_at = time.time()
        self.cache_lookups += 1
        if cache_hit:
            self.cache_hits += 1

    def record_failure(self) -> None:
        self.translations_failed += 1

    def record_leak(self) -> None:
        self.policy_leaks += 1

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

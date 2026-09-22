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
        self.recent_logs: deque[dict] = deque(maxlen=1000)
        self._log_counter: int = 0

    def record_usage_log(self, fields: dict) -> None:
        self._log_counter += 1
        now_ts = fields.get("timestamp") or time.time()
        raw_status = fields.get("status", 200)
        norm_status = 200 if raw_status == "ok" else raw_status
        prov = fields.get("provider") or fields.get("provider_name")
        if not prov or prov == "unknown":
            prov = "cache" if fields.get("cache_hit") else "Gemini"

        log_entry = {
            "id": fields.get("id") or self._log_counter,
            "timestamp": now_ts,
            "user_id": fields.get("user_id", 0),
            "char_len": fields.get("char_len", 0),
            "provider": prov,
            "latency_ms": fields.get("latency_ms", 0),
            "status": norm_status,
            "policy_hits": fields.get("policy_hits") or [],
            "created_at": fields.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.recent_logs.appendleft(log_entry)
        try:
            from ..admin.sse import broadcaster
            broadcaster.broadcast("usage_log", log_entry)
            broadcaster.broadcast("telemetry_update", self.get_telemetry())
        except Exception:
            pass

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

    def get_telemetry(self) -> dict:
        """Calculate dynamic telemetry points and current throughput/latency metrics."""
        import datetime
        from zoneinfo import ZoneInfo

        now = time.time()
        slot_hours = [0, 4, 8, 12, 16, 20, 24]
        labels = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "Live (Now)"]

        try:
            tz = ZoneInfo("Asia/Yangon")
            dt = datetime.datetime.now(tz)
            today_prefix = dt.strftime("%Y-%m-%d")
        except Exception:
            today_prefix = ""

        points = []
        for i, label in enumerate(labels):
            if label == "Live (Now)":
                # Last 15 minutes window
                window_logs = [
                    l for l in self.recent_logs
                    if l.get("timestamp") and (now - l["timestamp"] < 900)
                ]
            else:
                h_start = slot_hours[i]
                h_end = slot_hours[i + 1] if i + 1 < len(slot_hours) else 24
                window_logs = []
                for l in self.recent_logs:
                    ca = l.get("created_at", "")
                    if today_prefix and not ca.startswith(today_prefix):
                        continue
                    if len(ca) >= 13:
                        try:
                            hh = int(ca[11:13])
                            if h_start <= hh < h_end:
                                window_logs.append(l)
                        except Exception:
                            pass

            count = len(window_logs)
            if window_logs:
                lats = [l.get("latency_ms", 0) for l in window_logs]
                lats.sort()
                p95_val = lats[min(len(lats) - 1, int(len(lats) * 0.95))]
            else:
                p95_val = 0

            points.append({
                "label": label,
                "throughput": count,
                "latency_ms": round(p95_val),
            })

        p95_5m = self.p95_5m()
        overall_p95 = p95_5m if p95_5m > 0 else self.p95_latency()

        return {
            "current_throughput_5m": self.count_5m(),
            "current_p95_ms": round(overall_p95 * 1000) if overall_p95 > 0 else 0,
            "total_ok": self.translations_ok,
            "total_failed": self.translations_failed,
            "points": points,
        }


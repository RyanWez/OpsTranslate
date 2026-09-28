"""Watchdog health-check tests: alert firing/resolving and the daily digest.

The watchdog module previously had no coverage; these exercise every check
against RecordingAlerts so a regression in the thresholds is caught.
"""
from datetime import datetime

from .fakes import make_services


def _seed(stats, ok=0, fail=0):
    for _ in range(ok):
        stats.record_ok(0.2, cache_hit=False)
    for _ in range(fail):
        stats.record_failure()


async def test_error_rate_alert_fires_above_threshold():
    from app.services.watchdog import _check_error_rate

    svc = make_services()
    _seed(svc.stats, ok=8, fail=4)  # 12 events, 33% errors
    await _check_error_rate(svc)
    assert any(t == "HIGH_ERROR_RATE" for _, t, _ in svc.alerts.sent)


async def test_error_rate_resolves_when_healthy():
    from app.services.watchdog import _check_error_rate

    svc = make_services()
    _seed(svc.stats, ok=20, fail=0)
    await _check_error_rate(svc)
    assert any(t == "HIGH_ERROR_RATE" for t, _ in svc.alerts.resolved)
    assert not any(t == "HIGH_ERROR_RATE" for _, t, _ in svc.alerts.sent)


async def test_error_rate_ignores_small_samples():
    from app.services.watchdog import _check_error_rate

    svc = make_services()
    _seed(svc.stats, ok=1, fail=4)  # high rate but only 5 events (< 10 floor)
    await _check_error_rate(svc)
    assert not any(t == "HIGH_ERROR_RATE" for _, t, _ in svc.alerts.sent)


async def test_p95_alert_fires_when_slow():
    from app.services.watchdog import _check_p95

    svc = make_services()
    for _ in range(12):
        svc.stats.record_ok(6.0, cache_hit=False)  # 6s > 4s ceiling
    await _check_p95(svc)
    assert any(t == "HIGH_P95_LATENCY" for _, t, _ in svc.alerts.sent)


async def test_p95_resolves_when_fast():
    from app.services.watchdog import _check_p95

    svc = make_services()
    for _ in range(12):
        svc.stats.record_ok(0.3, cache_hit=False)
    await _check_p95(svc)
    assert any(t == "HIGH_P95_LATENCY" for t, _ in svc.alerts.resolved)


async def test_policy_engine_alert_fires():
    from app.services.watchdog import _check_policy_engine

    svc = make_services()
    _seed(svc.stats, ok=10, fail=0)
    for _ in range(3):
        svc.stats.record_policy_engine_error()  # 30% > 20% ceiling
    await _check_policy_engine(svc)
    assert any(t == "POLICY_ENGINE_ERROR_RATE" for _, t, _ in svc.alerts.sent)


async def test_daily_digest_sends_once_per_day(monkeypatch):
    import app.services.watchdog as wd

    class _FakeDT:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 9, 28, 9, 0, 0)

    monkeypatch.setattr(wd, "datetime", _FakeDT)
    svc = make_services()
    last = [""]

    await wd._maybe_digest(svc, last)
    digests = [t for _, t, _ in svc.alerts.sent if t == "DAILY_DIGEST"]
    assert len(digests) == 1

    # Same calendar day: must not resend.
    await wd._maybe_digest(svc, last)
    digests = [t for _, t, _ in svc.alerts.sent if t == "DAILY_DIGEST"]
    assert len(digests) == 1


async def test_no_digest_outside_window(monkeypatch):
    import app.services.watchdog as wd

    class _FakeDT:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 9, 28, 14, 30, 0)  # not 09:00

    monkeypatch.setattr(wd, "datetime", _FakeDT)
    svc = make_services()
    await wd._maybe_digest(svc, [""])
    assert not any(t == "DAILY_DIGEST" for _, t, _ in svc.alerts.sent)

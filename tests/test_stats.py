"""Direct unit tests for the 5-minute sliding-window metrics.

These were previously only exercised indirectly through the pipeline; the
watchdog and /healthz depend on them, so pin the maths down here.
"""
from app.services.stats import Stats


def test_count_and_error_rate_5m():
    s = Stats()
    for _ in range(8):
        s.record_ok(0.2, cache_hit=False)
    for _ in range(2):
        s.record_failure()
    assert s.count_5m() == 10
    assert abs(s.error_rate_5m() - 0.2) < 1e-9


def test_empty_window_is_zero():
    s = Stats()
    assert s.count_5m() == 0
    assert s.error_rate_5m() == 0.0
    assert s.p95_5m() == 0.0
    assert s.policy_error_rate_5m() == 0.0


def test_p95_5m_tracks_high_percentile():
    fast = Stats()
    for i in range(100):
        fast.record_ok(0.1 if i < 99 else 9.0, cache_hit=False)
    # 95th percentile of 99x0.1 + 1x9.0 sits in the fast band.
    assert fast.p95_5m() == 0.1

    slow = Stats()
    for _ in range(20):
        slow.record_ok(5.0, cache_hit=False)
    assert slow.p95_5m() == 5.0


def test_policy_error_rate_5m():
    s = Stats()
    for _ in range(10):
        s.record_ok(0.2, cache_hit=False)
    for _ in range(3):
        s.record_policy_engine_error()
    assert abs(s.policy_error_rate_5m() - 0.3) < 1e-9


def test_cache_hit_rate_and_last_success():
    s = Stats()
    assert s.cache_hit_rate == 0.0
    assert s.last_success_within(60) is False
    s.record_ok(0.1, cache_hit=True)
    s.record_ok(0.1, cache_hit=False)
    assert abs(s.cache_hit_rate - 0.5) < 1e-9
    assert s.last_success_within(60) is True


def test_window_purges_events_older_than_5m():
    import app.services.stats as stats_mod

    s = Stats()
    # A failure 10 minutes ago must fall out of the 5-minute window.
    s._recent.append((stats_mod.time.time() - 600, False))
    s.record_ok(0.1, cache_hit=False)
    assert s.count_5m() == 1
    assert s.error_rate_5m() == 0.0

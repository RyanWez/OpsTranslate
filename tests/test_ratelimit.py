"""Tests for the sliding-window rate limiter (2 per rolling 30s)."""
from app.services import ratelimit


def test_allows_two_then_rejects():
    ratelimit.reset(7)
    assert ratelimit.check(7, now=1000.0) == 0
    assert ratelimit.check(7, now=1001.0) == 0
    wait = ratelimit.check(7, now=1002.0)
    assert wait > 0
    assert wait <= 30


def test_sliding_not_bucketed():
    # A fixed 30s bucket would allow 2 at t=29 and 2 at t=31 (4 in 3s).
    ratelimit.reset(8)
    assert ratelimit.check(8, now=1029.0) == 0
    assert ratelimit.check(8, now=1029.5) == 0
    assert ratelimit.check(8, now=1031.0) > 0  # still inside the window


def test_window_evicts_old_entries():
    ratelimit.reset(9)
    assert ratelimit.check(9, now=1000.0) == 0
    assert ratelimit.check(9, now=1001.0) == 0
    assert ratelimit.check(9, now=1002.0) > 0
    # After 30s from the first hit, a slot frees up.
    assert ratelimit.check(9, now=1030.5) == 0
    assert ratelimit.check(9, now=1031.0) == 0
    assert ratelimit.check(9, now=1031.5) > 0


def test_countdown_is_live():
    ratelimit.reset(10)
    ratelimit.check(10, now=1000.0)
    ratelimit.check(10, now=1001.0)
    # At t=1015 the oldest hit (t=1000) expires at t=1030 -> wait ~15s.
    wait = ratelimit.check(10, now=1015.0)
    assert 14 <= wait <= 16


def test_rate_limit_disabled(monkeypatch):
    from app import config
    ratelimit.reset(11)
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    # Should never be rejected when disabled
    for i in range(10):
        assert ratelimit.check(11, now=1000.0 + i) == 0


def test_custom_limit_and_window(monkeypatch):
    from app import config
    ratelimit.reset(12)
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "RATE_LIMIT_COUNT", 4)
    monkeypatch.setattr(config, "RATE_LIMIT_WINDOW_S", 10.0)

    # 4 allowed
    for i in range(4):
        assert ratelimit.check(12, now=1000.0 + i) == 0
    # 5th rejected
    wait = ratelimit.check(12, now=1004.0)
    assert wait > 0
    assert wait <= 10.0

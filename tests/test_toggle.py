"""Tests for the auto EN<->MM toggle (owner request 2026-09-19)."""
from app.services.pipeline import resolve_toggle_dst


def test_myanmar_input_goes_to_english():
    assert resolve_toggle_dst("my", "my") == "en"
    assert resolve_toggle_dst("my", "en") == "en"


def test_english_input_goes_to_myanmar():
    assert resolve_toggle_dst("en", "en") == "my"
    assert resolve_toggle_dst("en", "my") == "my"


def test_auto_keeps_stored_target():
    # Uncertain/mixed input: fall back to the caller's dst.
    assert resolve_toggle_dst("auto", "en") == "en"
    assert resolve_toggle_dst("auto", "my") == "my"

"""Gates 3-10 of `run_translation`, and the delivery contract around them.

The assertions are written from the user's point of view: what was sent, as
a reply to what, what the placeholder finally said, and whether the provider
was ever called (Gate 10 is the only gate that costs money).
"""
import asyncio

import pytest

from app import config
from app.bot import strings
from app.services import pipeline, ratelimit
from app.services.cache import duplicate_key
from app.services.pipeline import _today_key, run_translation

from .fakes import (
    FakeBot,
    RecordingAlerts,
    StubRouter,
    StubUserStore,
    make_services,
    seed_cache,
)

USER = 11
CHAT = 11
ANCHOR = 555

MY_TEXT = "ဂိမ်းအိုင်ဒီ မှားနေတယ်"        # -> "User ID ..." (src=my)
EN_TEXT = "check my game points"                # -> "ပမာဏ ..."     (src=en)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Fresh rate-limit state and known product rules for every test."""
    ratelimit.reset()
    monkeypatch.setattr(config, "MAX_INPUT_CHARS", 500)
    monkeypatch.setattr(config, "AUTO_TOGGLE", True)
    monkeypatch.setattr(config, "DAILY_SPEND_CAP_USD", 5.0)
    monkeypatch.setattr(config, "PROVIDER_COST_PER_MSG_USD", 0.0004)
    yield
    ratelimit.reset()


async def run(services, text, dst="en", anchor=ANCHOR, user=USER, chat=CHAT):
    await run_translation(
        services, user_id=user, chat_id=chat, raw_text=text,
        anchor_message_id=anchor, dst=dst,
    )


def header(src: str, dst: str) -> str:
    return strings.TRANSLATION_HEADER.format(SRC=src.upper(), DST=dst.upper())


# ---------------------------------------------------------------------------
# Gate 5 - length cap
# ---------------------------------------------------------------------------

async def test_too_long_shows_the_count_and_spends_nothing():
    bot, router = FakeBot(), StubRouter()
    services = make_services(bot, router)
    await run(services, "a" * 501)

    assert bot.sent[0].text == strings.TOO_LONG.format(n=501)
    assert bot.sent[0].reply_to == ANCHOR      # rejection is reply-anchored too
    assert router.calls == 0                   # never reached the paid gate
    assert ratelimit.check(USER) == 0          # no rate slot consumed


async def test_exactly_at_the_cap_is_accepted():
    # Global (EN) -> MY is now relaxed and needs a Myanmar answer to pass
    # script_ok. 500-char Latin input still needs a similarly long Myanmar
    # answer to pass the ratio band.
    bot, router = FakeBot(), StubRouter(["မ" * 400])
    services = make_services(bot, router)
    await run(services, "b" * 500, dst="en")
    assert router.calls == 1
    assert "too long" not in bot.last_text().lower()


# ---------------------------------------------------------------------------
# Gate 6 - language
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "游戏里的积分怎么转",
    "สวัสดีครับ ผมมีปัญหา",
])
async def test_global_language_translated_to_myanmar(text):
    # 2026-09-20: Global => Myanmar is relaxed, no UNSUPPORTED_LANG rejection.
    # Any global language (Chinese, Thai, etc.) is translated to Myanmar
    # literally, with no term-policy.
    bot, router = FakeBot(), StubRouter(["မြန်မာပြန် အဖြေ"])
    services = make_services(bot, router)
    await run(services, text, dst="en")

    # Should have gone to the provider and returned a Myanmar answer
    assert router.calls == 1
    assert bot.edits[-1].text.startswith(header("AUTO", "MY")) or bot.edits[-1].text.startswith(header("ZH", "MY")) or "မြန်မာ" in bot.last_text()
    assert "Detected language" not in bot.last_text()


# ---------------------------------------------------------------------------
# Gate 10 + delivery: the happy path
# ---------------------------------------------------------------------------

async def test_happy_path_masks_anchors_and_reveals():
    bot, router = FakeBot(), StubRouter(["User ID is wrong"])
    services = make_services(bot, router)
    await run(services, MY_TEXT, dst="en")

    # Placeholder first, with the reply anchor set on THIS call (Locked Rule 5).
    assert bot.sent[0].text == strings.TRANSLATING
    assert bot.sent[0].reply_to == ANCHOR
    assert len(bot.sent) == 1                  # one send, then edits

    # Every edit targets the placeholder; the last one is the answer.
    assert {e.message_id for e in bot.edits} == {bot.sent[0].message_id}
    assert bot.edits[-1].text.startswith(header("MY", "EN"))
    assert "User ID is wrong" in bot.edits[-1].text

    # The provider only ever saw the masked text.
    assert "ဂိမ်း" not in router.masked[0]
    assert "⟦T:user_id⟧" in router.masked[0]
    assert services.stats.translations_ok == 1


async def test_entities_survive_the_round_trip():
    # English (global) -> Myanmar is relaxed (no term-policy). Entities must
    # still survive verbatim, but the answer is literal - no ⟦T:…⟧ placeholder
    # is expected. Provide a plain Myanmar answer that echoes the entities.
    burmese_answer = "https://x.co/a @ops 42 စစ်ပေးပါ"
    bot, router = FakeBot(), StubRouter([burmese_answer])
    services = make_services(bot, router)
    await run(services, "https://x.co/a @ops game id 42", dst="en")

    final = bot.edits[-1].text
    assert "https://x.co/a" in final
    assert "@ops" in final
    assert " 42" in final
    assert "⟦" not in final and "⟧" not in final
    # Relaxed Global->MY keeps original terms literally, so "game id" in
    # the *input* is not masked; the provider's literal answer may or may
    # not contain it - we only check entities survive.


async def test_meta_response_is_rejected_not_shipped():
    bot, router = FakeBot(), StubRouter(["As an AI, I cannot help"])
    services = make_services(bot, router)
    await run(services, "my points here", dst="en")

    assert router.calls == 2                   # one retry, then give up
    assert bot.last_text() == strings.ERROR_GENERIC
    assert "As an AI" not in " ".join(e.text for e in bot.edits)


async def test_spend_counter_increments_only_after_success():
    bot, router = FakeBot(), StubRouter(["User ID is wrong"])
    services = make_services(bot, router)
    await run(services, MY_TEXT, dst="en")

    spent = await services.cache.get_float(_today_key("spend"))
    assert spent == pytest.approx(config.PROVIDER_COST_PER_MSG_USD)


# ---------------------------------------------------------------------------
# Auto EN <-> MM toggle
# ---------------------------------------------------------------------------

async def test_auto_toggle_overrides_the_stored_target():
    bot, router = FakeBot(), StubRouter(["ပမာဏ စစ်ပေး"])
    services = make_services(bot, router)
    # Stored target says English; English input must still go to Myanmar.
    await run(services, EN_TEXT, dst="en")
    assert bot.edits[-1].text.startswith(header("EN", "MY"))


async def test_auto_toggle_can_be_disabled(monkeypatch):
    # 2026-09-20: Global=>MY is canonical. Even with AUTO_TOGGLE False the
    # new pipeline still routes any non-Myanmar input to Myanmar (the
    # disable path is kept for backward compat but the direction is now
    # always Global=>MY). Provide a Myanmar answer so script_ok passes.
    monkeypatch.setattr(config, "AUTO_TOGGLE", False)
    bot, router = FakeBot(), StubRouter(["ပမာဏ စစ်ပေးပါ"])
    services = make_services(bot, router)
    await run(services, EN_TEXT, dst="en")
    assert bot.edits[-1].text.startswith(header("EN", "MY"))


# ---------------------------------------------------------------------------
# Gates 7 + 9 - duplicates and cache
# ---------------------------------------------------------------------------

async def test_duplicate_within_30s_resends_without_a_rate_slot():
    bot, router = FakeBot(), StubRouter(["User ID is wrong"])
    services = make_services(bot, router)
    await run(services, MY_TEXT, dst="en")
    assert router.calls == 1

    await run(services, MY_TEXT, dst="en")
    assert router.calls == 1                   # served from cache, not the AI
    assert "User ID is wrong" in bot.last_text()
    # The resend path returns before Gate 8, so only one slot is used.
    assert ratelimit.check(USER) == 0


async def test_inflight_duplicate_is_dropped_silently():
    bot, router = FakeBot(), StubRouter()
    services = make_services(bot, router)
    await services.cache.mark_inflight(duplicate_key(USER, MY_TEXT, "en"))

    await run(services, MY_TEXT, dst="en")
    assert bot.calls == []                     # not even a placeholder
    assert router.calls == 0


async def test_cache_hit_skips_the_provider():
    bot, router = FakeBot(), StubRouter()
    services = make_services(bot, router)
    # Aged past the 30s duplicate-resend window -> the plain Gate 9 hit.
    seed_cache(services.cache, "Cached answer", "my", "en", 1, MY_TEXT,
               age_s=120)

    await run(services, MY_TEXT, dst="en")
    assert router.calls == 0
    assert "Cached answer" in bot.last_text()
    assert services.stats.cache_hits == 1


async def test_success_is_cached_for_the_next_caller():
    bot, router = FakeBot(), StubRouter(["User ID is wrong"])
    services = make_services(bot, router)
    await run(services, MY_TEXT, dst="en")
    assert router.calls == 1

    # Age the entry out of the duplicate window; a fresh user must hit Gate 9.
    seed_cache(services.cache, "User ID is wrong", "my", "en", 1, MY_TEXT,
               age_s=120)
    await run(services, MY_TEXT, dst="en", user=22)
    assert router.calls == 1


# ---------------------------------------------------------------------------
# Gate 8 - rate limit
# ---------------------------------------------------------------------------

async def test_third_message_in_30s_gets_a_countdown():
    # Rate limiter test - direction is now always Global=>MY, so provide
    # Myanmar answers to pass script_ok.
    bot, router = FakeBot(), StubRouter(["အဖြေ တစ်ခု", "အဖြေ နှစ်ခု"])
    services = make_services(bot, router)
    for text in ("first message here", "second message here",
                 "third message here"):
        await run(services, text, dst="en")

    assert "Please wait" in bot.last_text()
    assert "Limit: 2 messages per 30 seconds." in bot.last_text()
    assert router.calls == 2                   # the third never reached Gate 10


# ---------------------------------------------------------------------------
# Volume guards: per-user soft cap and the daily spend cap
# ---------------------------------------------------------------------------

async def test_daily_soft_cap_stops_before_the_provider():
    bot, router = FakeBot(), StubRouter()
    services = make_services(bot, router, user_store=StubUserStore(daily_cap=0))
    await run(services, "hello there friend", dst="en")

    assert bot.last_text() == strings.DAILY_CAP_REACHED
    assert router.calls == 0


async def test_spend_cap_degrades_and_alerts(monkeypatch):
    monkeypatch.setattr(config, "DAILY_SPEND_CAP_USD", 0.001)
    bot, router = FakeBot(), StubRouter()
    alerts = RecordingAlerts()
    services = make_services(bot, router, alerts=alerts)
    await services.cache.incr_float(_today_key("spend"), 0.01, 86400)

    await run(services, MY_TEXT, dst="en")
    assert bot.last_text() == strings.SPEND_CAP_REACHED
    assert router.calls == 0
    assert ("P2", "SPEND_CAP") in [(lvl, typ) for lvl, typ, _ in alerts.sent]


# ---------------------------------------------------------------------------
# Withhold-on-leak, and the failure paths that must still resolve the
# placeholder (a stuck "Translating..." is the worst possible outcome)
# ---------------------------------------------------------------------------

async def test_policy_refusal_withholds_and_alerts():
    # Myanmar input, so the auto toggle resolves the target to English and
    # the English deny list is the one that applies.
    bot, router = FakeBot(), StubRouter(["send game chips"])
    alerts = RecordingAlerts()
    services = make_services(bot, router, alerts=alerts)
    await run(services, "ပွိုင့်တွေ လွှဲပေးပါ", dst="my")

    assert router.calls == 2                   # initial + exactly one repair
    assert ("P2", "POLICY_LEAK") in [(lvl, typ) for lvl, typ, _ in alerts.sent]
    assert bot.deleted, "the placeholder must be deleted, not edited"
    assert bot.deleted[0].message_id == bot.sent[0].message_id
    assert "game" not in " ".join(e.text for e in bot.edits).lower()
    assert services.stats.policy_leaks == 1
    assert services.stats.translations_failed == 1


async def test_provider_outage_resolves_the_placeholder_and_alerts_p1():
    bot, router = FakeBot(), StubRouter(fail=True)
    alerts = RecordingAlerts()
    services = make_services(bot, router, alerts=alerts)
    await run(services, "my points here", dst="en")

    assert bot.last_text() == strings.ERROR_GENERIC
    assert ("P1", "PROVIDER_OUTAGE") in [(lvl, typ) for lvl, typ, _ in alerts.sent]
    assert services.stats.translations_failed == 1


async def test_handler_budget_resolves_the_placeholder(monkeypatch):
    monkeypatch.setattr(pipeline, "HANDLER_BUDGET_S", 0.2)
    bot, router = FakeBot(), StubRouter(hang=True)
    services = make_services(bot, router)

    await asyncio.wait_for(run(services, "my points here", dst="en"), timeout=5)
    assert bot.last_text() == strings.ERROR_GENERIC


async def test_typing_indicator_is_sent_while_the_provider_works():
    bot, router = FakeBot(), StubRouter(["User ID is wrong"], delay=0.02)
    services = make_services(bot, router)
    await run(services, MY_TEXT, dst="en")
    assert [c.text for c in bot.chat_actions] == ["typing"]


# ---------------------------------------------------------------------------
# Script check (the gap these tests found, now closed)
# ---------------------------------------------------------------------------

async def test_answer_in_the_wrong_script_is_not_shipped():
    # English input -> auto toggle resolves the target to Myanmar. A provider
    # that answers in English must not be delivered as a Myanmar translation.
    bot, router = FakeBot(), StubRouter(["send chips now"])
    alerts = RecordingAlerts()
    services = make_services(bot, router, alerts=alerts)
    await run(services, EN_TEXT, dst="en")

    assert router.calls == 2                   # one retry, then give up
    assert bot.last_text() == strings.ERROR_GENERIC
    assert "send chips now" not in " ".join(e.text for e in bot.edits)
    assert ("P1", "PROVIDER_OUTAGE") in [(lvl, typ) for lvl, typ, _ in alerts.sent]
    assert any("wrong script" in detail for _, _, detail in alerts.sent)
    assert services.stats.translations_failed == 1


async def test_proper_noun_heavy_answer_in_the_target_script_still_ships():
    bot, router = FakeBot(), StubRouter(["Facebook ပါ"])
    services = make_services(bot, router)
    await run(services, "please check Facebook", dst="en")   # toggle -> MY

    assert router.calls == 1                   # no false positive, no retry
    assert "Facebook ပါ" in bot.last_text()
    assert bot.last_text().startswith(header("EN", "MY"))


async def test_a_corrected_answer_on_retry_is_shipped():
    bot, router = FakeBot(), StubRouter(["send chips now", "ပမာဏ လွှဲပေး"])
    services = make_services(bot, router)
    await run(services, EN_TEXT, dst="en")     # toggle -> MY

    assert router.calls == 2
    assert "ပမာဏ လွှဲပေး" in bot.last_text()
    assert services.stats.translations_ok == 1


def test_copy_keyboard_length_guard():
    assert pipeline.copy_keyboard("") is None
    short_text = "Hello world"
    kb = pipeline.copy_keyboard(short_text)
    assert kb is not None
    assert kb.inline_keyboard[0][0].copy_text.text == short_text

    long_text = "a" * 257
    assert pipeline.copy_keyboard(long_text) is None

    max_text = "a" * 256
    assert pipeline.copy_keyboard(max_text) is not None


async def test_rate_limit_hits_and_admin_bypasses(monkeypatch):
    bot, router = FakeBot(), StubRouter(["User ID is wrong", "User ID is wrong", "User ID is wrong"])
    services = make_services(bot, router)
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "RATE_LIMIT_COUNT", 2)
    monkeypatch.setattr(config, "RATE_LIMIT_WINDOW_S", 30.0)
    monkeypatch.setattr(config, "RATE_LIMIT_BYPASS_ADMINS", True)

    # 1. Normal user (USER=11, role='staff') sends 2 messages with different text to avoid duplicate gate
    await run(services, "ဂိမ်းအိုင်ဒီ တစ်", user=USER)
    await run(services, "ဂိမ်းအိုင်ဒီ နှစ်", user=USER)
    assert router.calls == 2

    # 3rd message from normal user hits rate limit
    await run(services, "ဂိမ်းအိုင်ဒီ သုံး", user=USER)
    assert router.calls == 2
    assert "Limit: 2 messages per 30 seconds." in bot.sent[-1].text

    # 2. Admin user (user=999 in ADMIN_USER_IDS) bypasses rate limit
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [999])
    await run(services, "ဂိမ်းအိုင်ဒီ admin 1", user=999)
    await run(services, "ဂိမ်းအိုင်ဒီ admin 2", user=999)
    await run(services, "ဂိမ်းအိုင်ဒီ admin 3", user=999)
    # Admin calls went through to router without being rate-limited
    assert router.calls == 5


"""Tests for the Term Policy engine: mask, render, deny-scan, entities."""
import pytest

from app.policy.policy import (
    compile_policy,
    deny_scan,
    is_meta_response,
    mask,
    normalise,
    protect_entities,
    ratio_ok,
    render,
    restore_entities,
    script_ok,
)


@pytest.fixture(scope="module")
def policy():
    return compile_policy(1)


def test_longest_match_first_myanmar(policy):
    # "ဂိမ်းပွိုင့်" (balance) must match before "ဂိမ်း" (platform).
    out = mask("ဂိမ်းပွိုင့်လွှဲမယ်", "my", policy)
    assert out == "⟦T:balance⟧လွှဲမယ်"
    assert "⟦T:platform⟧" not in out


def test_longest_match_first_english(policy):
    out = mask("my game points balance", "en", policy)
    assert out == "my ⟦T:balance⟧ balance"


def test_english_word_boundaries(policy):
    # "gamer" must NOT be split by a game-related rule; "checkpoint"
    # must not match the "points" variant.
    assert mask("gamer points", "en", policy) == "gamer ⟦T:balance⟧"
    assert mask("checkpoint reached", "en", policy) == "checkpoint reached"


def test_english_case_insensitive(policy):
    assert mask("My GAME ID is wrong", "en", policy) == "My ⟦T:user_id⟧ is wrong"
    assert mask("GAME POINTS", "en", policy) == "⟦T:balance⟧"


def test_chinese_substring(policy):
    out = mask("游戏里的积分怎么转", "zh", policy)
    assert out == "⟦T:platform⟧里的⟦T:balance⟧怎么转"


def test_enabled_member_concept_masked(policy):
    # "member" was approved+enabled by the owner 2026-09-19 (player -> Customer).
    assert mask("player one", "en", policy) == "⟦T:member⟧ one"
    assert mask("ကစားသမား", "my", policy) == "⟦T:member⟧"
    assert mask("玩家", "zh", policy) == "⟦T:member⟧"
    # Longest-match-first: "player id" still belongs to user_id, not member.
    assert mask("player id", "en", policy) == "⟦T:user_id⟧"


def test_render_per_target_language(policy):
    assert render("⟦T:balance⟧", "en", policy) == "Amount"
    assert render("⟦T:balance⟧", "my", policy) == "ပမာဏ"
    assert render("⟦T:balance⟧", "zh", policy) == "金额"
    assert render("⟦T:member⟧", "en", policy) == "Customer"
    assert render("⟦T:member⟧", "my", policy) == "ဖောက်သည်"
    assert render("⟦T:user_id⟧", "en", policy) == "User ID"
    assert render("⟦T:platform⟧", "zh", policy) == "平台"


def test_render_unknown_placeholder_kept(policy):
    assert render("⟦T:nope⟧", "en", policy) == "⟦T:nope⟧"


def test_deny_scan_per_language(policy):
    assert deny_scan("this is a game", "en", policy) == ["game"]
    assert deny_scan("this is a game", "my", policy) == []
    assert deny_scan("ဂိမ်းအကြောင်း", "my", policy) == ["ဂိမ်း"]
    assert deny_scan("关于游戏", "zh", policy) == ["游戏"]
    assert deny_scan("How do I transfer my Balance?", "en", policy) == []


def test_deny_scan_casefold(policy):
    assert deny_scan("CASINO night", "en", policy) == ["casino"]


def test_entity_protection_separate_namespace(policy):
    text = "my game id 0912345678 https://x.co/a @ops pls"
    protected, restore = protect_entities(text)
    assert "⟦E:id:" in protected
    assert "⟦E:url:" in protected
    assert "⟦E:mention:" in protected
    assert "⟦T:" not in protected  # entities never use the policy namespace
    # Masking still works around entities.
    masked = mask(protected, "en", policy)
    assert "⟦T:user_id⟧" in masked
    # Render must not touch entity placeholders; restore is verbatim.
    rendered = render(masked, "en", policy)
    final = restore_entities(rendered, restore)
    assert "0912345678" in final and "https://x.co/a" in final and "@ops" in final
    assert "⟦E:" not in final and "⟦T:" not in final


def test_normalise():
    assert normalise("a  b\u200bc") == "a bc"  # zero-width removed, space collapsed
    assert normalise("  x  ") == "x"


def test_ratio_ok():
    assert ratio_ok("a" * 100, "b" * 100)
    assert ratio_ok("a" * 100, "b" * 30)
    assert not ratio_ok("a" * 100, "b" * 29)
    assert not ratio_ok("a" * 100, "b" * 301)
    assert not ratio_ok("", "b")
    # Script-aware bands: dense scripts legitimately expand into Latin.
    assert ratio_ok("我" * 9, "b" * 35, src="zh", dst="en")  # 3.9x
    assert not ratio_ok("我" * 9, "b" * 60, src="zh", dst="en")  # 6.7x
    assert ratio_ok("မ" * 20, "b" * 70, src="my", dst="en")  # 3.5x
    assert ratio_ok("a" * 100, "我" * 20, src="en", dst="zh")  # contraction


def test_is_meta_response():
    assert is_meta_response("As an AI, I cannot help")
    assert is_meta_response("I'm sorry, I can't do that")
    assert not is_meta_response("The user ID is incorrect.")


def test_deny_scan_evasion(policy):
    # Separator tricks must not smuggle a deny term through.
    assert deny_scan("play g-a-m-e now", "en", policy) == ["game"]
    assert deny_scan("play g a m e now", "en", policy) == ["game"]
    assert deny_scan("play G.A.M.E now", "en", policy) == ["game"]
    assert deny_scan("play g​am​e now", "en", policy) == ["game"]
    assert deny_scan("来赌-场玩", "zh", policy) == ["赌场"]
    # Clean text stays clean.
    assert deny_scan("hello world", "en", policy) == []


def test_myanmar_id_transliteration_variants(policy):
    # The spec's few-shot uses the "အိုင်" spelling; §4.2 lists "အိုက်".
    # Both must mask as user_id (longest-match-first, no orphan fragment).
    assert mask("ဂိမ်းအိုင်ဒီ မှားနေတယ်", "my", policy) == "⟦T:user_id⟧ မှားနေတယ်"
    assert mask("ဂိမ်းအိုက်ဒီ မှားနေတယ်", "my", policy) == "⟦T:user_id⟧ မှားနေတယ်"


def test_script_ok_requires_the_target_script():
    # The guard exists for one failure: a provider answering a Myanmar
    # request in English, which the ratio check and the deny scan both miss.
    assert script_ok("ပမာဏ လွှဲပေးပါ", "my")
    assert script_ok("The Amount was sent", "en")
    assert script_ok("金额已转", "zh")

    assert not script_ok("The Amount was sent", "my")
    assert not script_ok("send chips now", "my")
    assert not script_ok("The amount was sent", "zh")


def test_script_ok_tolerates_proper_nouns_and_placeholders():
    # Narrow on purpose: reject only when the target script is ENTIRELY
    # absent, so real answers are never withheld over a brand name.
    assert script_ok("Facebook ပါ", "my")            # proper noun + particles
    assert script_ok("⟦T:user_id⟧", "my")           # placeholder only
    assert script_ok("⟦E:id:1⟧", "my")              # entity only
    assert script_ok("⟦T:user_id⟧ ကို စစ်ပေးပါ", "my")
    assert script_ok("12 34", "my")                  # no letters to judge
    assert script_ok("anything at all", "auto")      # unknown target


def test_regular_customer_and_activity_masked_and_rendered(policy):
    # Tests zero-gaming compliance: regular playing fan -> regular customer, etc.
    from app.policy.policy import sanitize_leaks

    # English input
    masked_en = mask("THIS CUSTOMER IS REGULAR PLAYING FAN", "en", policy)
    assert "⟦T:regular_customer⟧" in masked_en
    rendered_en = render(masked_en, "en", policy)
    assert "regular customer" in rendered_en
    assert "playing" not in rendered_en.lower()
    assert "fan" not in rendered_en.lower()

    # Myanmar input
    masked_my = mask("ဒီ customer က ပုံမှန်ကစားနေကျ fan ပါ", "my", policy)
    assert "⟦T:regular_customer⟧" in masked_my
    rendered_my_to_en = render(masked_my, "en", policy)
    assert "regular customer" in rendered_my_to_en

    # Activity masking
    masked_act = mask("customer ကစားနေတယ်", "my", policy)
    assert "⟦T:activity⟧" in masked_act
    rendered_act_to_en = render(masked_act, "en", policy)
    assert "active" in rendered_act_to_en


def test_sanitize_leaks():
    from app.policy.policy import sanitize_leaks

    # Residual leaks sanitized in English
    raw_en = "This customer is regular playing fan and game points 100"
    cleaned_en = sanitize_leaks(raw_en, "en")
    assert "regular customer" in cleaned_en
    assert "Amount" in cleaned_en
    assert "playing" not in cleaned_en.lower()
    assert "game" not in cleaned_en.lower()

    # Residual leaks sanitized in Myanmar
    raw_my = "ဒီ customer က ကစားသမား ဖြစ်ပြီး ဂိမ်းပွိုင့် ၁၀၀ ကစားနေတယ်"
    cleaned_my = sanitize_leaks(raw_my, "my")
    assert "Customer" in cleaned_my
    assert "Amount" in cleaned_my
    assert "အသုံးပြုနေတယ်" in cleaned_my
    assert "ဂိမ်း" not in cleaned_my
    assert "ကစားသမား" not in cleaned_my

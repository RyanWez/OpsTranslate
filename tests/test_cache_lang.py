"""Tests for cache-key normalization and the language detector."""
from app.services.cache import cache_key, normalize_for_key
from app.policy.langdetect import detect


def test_cache_key_normalization():
    # Case, whitespace and fullwidth punctuation must not change the key.
    a = cache_key("How do I check my balance?", "en", "en", 1)
    b = cache_key("how do i check my balance?", "en", "en", 1)
    c = cache_key("  How  do I check my balance\uff1f ", "en", "en", 1)
    assert a == b == c


def test_cache_key_differs_by_lang_and_version():
    a = cache_key("hello", "en", "en", 1)
    assert a != cache_key("hello", "en", "my", 1)
    assert a != cache_key("hello", "en", "en", 2)
    assert a != cache_key("hello!", "en", "en", 1)


def test_normalize_fullwidth():
    assert normalize_for_key("\u3000\uff28\uff45\uff4c\uff4c\uff4f\uff01 ") == "hello!"


def test_detect_myanmar():
    src, conf, oos = detect("ဂိမ်းအိုင်ဒီ မှားနေတယ်")
    assert src == "my" and oos is None and conf >= 0.60


def test_detect_english():
    src, conf, oos = detect("check my balance please")
    assert src == "en" and oos is None


def test_detect_chinese_is_unsupported():
    # Chinese support was cut by the owner 2026-09-19: confident CJK
    # detection is now out-of-scope, not src="zh".
    src, conf, oos = detect("游戏里的积分怎么转")
    assert oos == "Chinese"


def test_mixed_language_falls_back_to_auto():
    # The common real-world case: Burmese + English in one message.
    # Must NOT be rejected - src="auto", provider handles it.
    src, conf, oos = detect("ပွိုင့်လွှဲမယ် points transfer")
    assert oos is None
    assert src == "auto"


def test_confident_thai_is_unsupported():
    src, conf, oos = detect("สวัสดีครับ ผมมีปัญหา")
    assert oos == "Thai"


def test_no_letters_is_auto():
    src, conf, oos = detect("0912345678 !!!")
    assert src == "auto" and oos is None

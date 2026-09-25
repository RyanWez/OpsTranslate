"""The complete English UI surface. Every user-facing string lives here.

Locked Rule 1: the only non-English content in the system is translation
*data* (source text typed by staff, and translated output). Nothing else.
"""
from __future__ import annotations

from .. import config
from .emojis import get_emoji, get_custom_emoji_id, get_slot_fallback


import html

def _limit() -> int:
    """Single source of truth: read the cap live so env/monkeypatch changes
    are reflected in the UI without a restart/reimport."""
    try:
        return int(config.MAX_INPUT_CHARS)
    except (TypeError, ValueError):
        return 500


def welcome_text(name: str | None = None, username: str | None = None) -> str:
    wave = get_emoji("start_welcome")
    globe = get_emoji("header_globe")
    toggle = get_emoji("auto_mode")
    arrow = get_emoji("arrow")
    privacy = get_emoji("help_privacy")

    if name and name.strip():
        user_tag = f" (@{html.escape(username.strip())})" if username and username.strip() else ""
        header = f"{wave} Welcome, <b>{html.escape(name.strip())}</b>{user_tag}!"
    else:
        header = f"{wave} Welcome to <b>OpsTranslate</b>!"

    return (
        f"{header}\n\n"
        f"{globe} Send any message and I'll translate it instantly.\n"
        f"{toggle} <b>Auto Mode:</b> Myanmar {arrow} English, English {arrow} Myanmar.\n"
        f"{privacy} <b>Security:</b> Nothing you send is stored.\n"
        f"<b>Limit:</b> {_limit()} characters per message."
    )


def custom_emoji_detected_text(items: list[tuple[str, str]]) -> str:
    if len(items) == 1:
        cid, char = items[0]
        escaped_char = html.escape(char)
        return (
            "✨ <b>Custom Emoji Detected</b>\n\n"
            f"• <b>Emoji:</b> <tg-emoji emoji-id=\"{cid}\">{escaped_char}</tg-emoji>\n"
            f"• <b>Custom ID:</b> <code>{cid}</code> (tap to copy)\n"
            f"• <b>HTML Tag:</b> <code>&lt;tg-emoji emoji-id=\"{cid}\"&gt;{escaped_char}&lt;/tg-emoji&gt;</code>\n\n"
            "<i>💡 You can copy this ID into the Admin Panel under <b>Animated Emojis</b>!</i>"
        )
    lines = [
        f"{idx}. <tg-emoji emoji-id=\"{cid}\">{html.escape(char)}</tg-emoji> ID: <code>{cid}</code>"
        for idx, (cid, char) in enumerate(items, 1)
    ]
    list_str = "\n".join(lines)
    return (
        "✨ <b>Custom Emojis Detected</b> (tap ID to copy)\n\n"
        f"{list_str}\n\n"
        "<i>💡 You can copy these IDs into the Admin Panel under <b>Animated Emojis</b>!</i>"
    )


def standard_emoji_info_text(raw_text: str) -> str:
    escaped = html.escape(raw_text.strip())
    return (
        "ℹ️ <b>Standard Emoji</b>\n\n"
        f"You sent: {escaped}\n"
        "This is a standard Unicode emoji, not a Telegram Premium animated emoji.\n\n"
        "<i>💡 To inspect an Animated Emoji ID, send an emoji from a Telegram Premium custom emoji pack. The bot will automatically detect its <b>Custom Emoji ID</b>!</i>"
    )


def help_text() -> str:
    book = get_emoji("help_book")
    arrow = get_emoji("arrow")
    privacy = get_emoji("help_privacy")
    count = getattr(config, "RATE_LIMIT_COUNT", 2)
    win = int(getattr(config, "RATE_LIMIT_WINDOW_S", 30))
    limit_clause = f", {count} messages per {win} seconds" if getattr(config, "RATE_LIMIT_ENABLED", True) else ""
    return (
        f"{book} How to use:\n"
        f"\u2022 Send a Myanmar message {arrow} I'll translate it to English.\n"
        f"\u2022 Send an English message {arrow} I'll translate it to Myanmar.\n"
        "\u2022 Reply to a message with /tr to translate that message.\n"
        f"\u2022 Limits: {_limit()} characters per message{limit_clause}.\n"
        f"\u2022 {privacy} Nothing you send is stored."
    )


def too_long_text(n: int) -> str:
    warn = get_emoji("warning")
    return (
        f"{warn} Message is too long \u2014 {n} / {_limit()} characters.\n"
        "Please split it and send again."
    )


def unsupported_type_text() -> str:
    warn = get_emoji("warning")
    return f"{warn} I can only translate text messages (max {_limit()} characters)."


def translating_text(dots: str = "\u2026") -> str:
    loading = get_emoji("loading")
    return f"{loading} Translating{dots}"


def translation_header(src: str, dst: str) -> str:
    globe = get_emoji("header_globe")
    arrow = get_emoji("arrow")
    return f"{globe} {src} {arrow} {dst}"


def copy_button_text() -> str:
    icon = get_slot_fallback("copy_button") or "📋"
    return f"{icon} Copy"


def not_authorized_text(user_id: int) -> str:
    lock = get_emoji("unauthorized")
    return f"{lock} This bot is restricted to authorised staff.\nYour ID: {user_id}"


def rate_limit_text(n: int) -> str:
    timer = get_emoji("rate_limit")
    count = getattr(config, "RATE_LIMIT_COUNT", 2)
    win = int(getattr(config, "RATE_LIMIT_WINDOW_S", 30))
    return (
        f"{timer} Please wait {n}s and send again.\n"
        f"Limit: {count} messages per {win} seconds."
    )


def maintenance_text(custom: str | None = None) -> str:
    """Return the maintenance notice sent to users.

    If *custom* is provided (DB-configured message) it is returned verbatim
    (HTML allowed).  Otherwise a sensible bilingual default is used.
    """
    if custom and custom.strip():
        return custom.strip()
    return (
        "🔧 <b>Bot ကို Update လုပ်နေပါတယ်</b>\n\n"
        "လောလောဆယ် ဘာသာပြန်ဝန်ဆောင်မှု ခေတ္တ ရပ်ဆိုင်းထားပါတယ်။\n"
        "မကြာခင် ပြန်လည်အသုံးပြုနိုင်ပါမယ် — ခဏစောင့်ပေးပါ။\n\n"
        "🔧 <b>Bot is under maintenance</b>\n\n"
        "Translation service is temporarily unavailable.\n"
        "Please try again in a few minutes."
    )


def auto_mode_text() -> str:
    toggle = get_emoji("auto_mode")
    arrow = get_emoji("arrow")
    return (
        f"{toggle} Auto mode is on: Myanmar {arrow} English, English {arrow} Myanmar.\n"
        "Just send your message - no need to pick a language."
    )


def __getattr__(name: str) -> str:
    """Keep ``strings.WELCOME`` / ``strings.TOO_LONG.format(n=..)`` working
    while computing the limit lazily from config."""
    if name == "WELCOME":
        return welcome_text()
    if name == "HELP":
        return help_text()
    if name == "TOO_LONG":
        return too_long_text("{n}")
    if name == "UNSUPPORTED_TYPE":
        return unsupported_type_text()
    if name == "RATE_LIMIT":
        return (
            f"{get_emoji('rate_limit')} Please wait {{n}}s and send again.\n"
            f"Limit: {getattr(config, 'RATE_LIMIT_COUNT', 2)} messages per {int(getattr(config, 'RATE_LIMIT_WINDOW_S', 30))} seconds."
        )
    if name == "TRANSLATING":
        return translating_text()
    if name == "TRANSLATION_HEADER":
        return f"{get_emoji('header_globe')} {{SRC}} {get_emoji('arrow')} {{DST}}"
    if name == "COPY_BUTTON":
        return copy_button_text()
    if name == "AUTO_MODE":
        return auto_mode_text()
    if name == "NOT_AUTHORIZED":
        return not_authorized_text("{user_id}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        list(globals().keys())
        + ["WELCOME", "HELP", "TOO_LONG", "UNSUPPORTED_TYPE", "RATE_LIMIT", "TRANSLATING", "TRANSLATION_HEADER", "COPY_BUTTON", "AUTO_MODE", "NOT_AUTHORIZED"]
    )


TARGET_SET = "Target language set to {LANG}."
LANG_BUTTONS = ["Myanmar", "English"]
LANG_CODE = {"Myanmar": "my", "English": "en"}
LANG_NAME = {"my": "Myanmar", "en": "English"}

UNSUPPORTED_LANG = (
    "Detected language: {lang}. I translate Myanmar and English only."
)
ALREADY_TRANSLATED = "That is already a translation. Send the text you want translated."
ERROR_GENERIC = "Translation is unavailable right now. Please try again in a moment."
DAILY_CAP_REACHED = (
    "You have reached your daily message limit. Please try again tomorrow."
)
SPEND_CAP_REACHED = (
    "Translation is temporarily unavailable. Please try again later."
)

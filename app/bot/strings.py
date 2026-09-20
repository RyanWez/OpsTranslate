"""The complete English UI surface. Every user-facing string lives here.

Locked Rule 1: the only non-English content in the system is translation
*data* (source text typed by staff, and translated output). Nothing else.
"""
from __future__ import annotations

from .. import config


def _limit() -> int:
    """Single source of truth: read the cap live so env/monkeypatch changes
    are reflected in the UI without a restart/reimport."""
    try:
        return int(config.MAX_INPUT_CHARS)
    except (TypeError, ValueError):
        return 500


def welcome_text() -> str:
    return (
        "Hi. Send me a message and I'll translate it.\n"
        "Auto mode: Myanmar \u2192 English, English \u2192 Myanmar.\n"
        f"Limit: {_limit()} characters per message."
    )


def help_text() -> str:
    return (
        "How to use:\n"
        "\u2022 Send a Myanmar message - I'll translate it to English.\n"
        "\u2022 Send an English message - I'll translate it to Myanmar.\n"
        "\u2022 Reply to a message with /tr to translate that message.\n"
        f"\u2022 Limits: {_limit()} characters per message, 2 messages per 30 seconds.\n"
        "\u2022 Nothing you send is stored."
    )


def too_long_text(n: int) -> str:
    return (
        f"Message is too long \u2014 {n} / {_limit()} characters.\n"
        "Please split it and send again."
    )


def unsupported_type_text() -> str:
    return f"I can only translate text messages (max {_limit()} characters)."


def __getattr__(name: str) -> str:
    """Keep ``strings.WELCOME`` / ``strings.TOO_LONG.format(n=..)`` working
    while computing the limit lazily from config."""
    if name == "WELCOME":
        return welcome_text()
    if name == "HELP":
        return help_text()
    if name == "TOO_LONG":
        return (
            f"Message is too long \u2014 {{n}} / {_limit()} characters.\n"
            "Please split it and send again."
        )
    if name == "UNSUPPORTED_TYPE":
        return unsupported_type_text()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        list(globals().keys())
        + ["WELCOME", "HELP", "TOO_LONG", "UNSUPPORTED_TYPE"]
    )

TARGET_SET = "Target language set to {LANG}."
AUTO_MODE = (
    "Auto mode is on: Myanmar \u2192 English, English \u2192 Myanmar.\n"
    "Just send your message - no need to pick a language."
)
LANG_BUTTONS = ["Myanmar", "English"]
LANG_CODE = {"Myanmar": "my", "English": "en"}
LANG_NAME = {"my": "Myanmar", "en": "English"}

TRANSLATING = "\u23f3 Translating\u2026"
TRANSLATION_HEADER = "\U0001f310 {SRC} \u2192 {DST}"
COPY_BUTTON = "Copy"

RATE_LIMIT = (
    "Please wait {n}s and send again.\n"
    "Limit: 2 messages per 30 seconds."
)
NOT_AUTHORIZED = (
    "This bot is restricted to authorised staff.\n"
    "Your ID: {user_id}"
)
UNSUPPORTED_LANG = (
    "Detected language: {lang}. I translate Myanmar and English only."
)
ALREADY_TRANSLATED = "That is already a translation. Send the text you want translated."
# (POLICY_FALLBACK intentionally absent: on a second deny hit the bot
# withholds entirely - the placeholder is deleted, nothing is sent.)
ERROR_GENERIC = "Translation is unavailable right now. Please try again in a moment."
DAILY_CAP_REACHED = (
    "You have reached your daily message limit. Please try again tomorrow."
)
SPEND_CAP_REACHED = (
    "Translation is temporarily unavailable. Please try again later."
)

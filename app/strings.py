"""The complete English UI surface. Every user-facing string lives here.

Locked Rule 1: the only non-English content in the system is translation
*data* (source text typed by staff, and translated output). Nothing else.
"""
from __future__ import annotations

WELCOME = (
    "Hi. Send me a message and I'll translate it.\n"
    "Auto mode: Myanmar \u2192 English, English \u2192 Myanmar.\n"
    "Limit: 250 characters per message."
)

HELP = (
    "How to use:\n"
    "\u2022 Send a Myanmar message - I'll translate it to English.\n"
    "\u2022 Send an English message - I'll translate it to Myanmar.\n"
    "\u2022 Reply to a message with /tr to translate that message.\n"
    "\u2022 Limits: 250 characters per message, 2 messages per 30 seconds.\n"
    "\u2022 Nothing you send is stored."
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

TOO_LONG = (
    "Message is too long \u2014 {n} / 250 characters.\n"
    "Please split it and send again."
)
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
UNSUPPORTED_TYPE = "I can only translate text messages (max 250 characters)."
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

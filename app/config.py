"""Central configuration. Everything comes from environment variables.

Required for a live run:
    BOT_TOKEN, PROVIDER_BASE_URL, PROVIDER_API_KEY, PROVIDER_MODEL

Optional:
    ALERT_BOT_TOKEN, ADMIN_CHAT_ID, WEBHOOK_SECRET, WEBHOOK_PATH_SECRET,
    DATABASE_URL (Neon pooled connection string), REDIS_URL,
    ALLOWED_USER_IDS (comma-separated, seeded as staff),
    ADMIN_USER_IDS (comma-separated, seeded as admin),
    TEST_ALLOW_ALL (default false - bypasses the allowlist gate),
    MAX_INPUT_CHARS (default 500), POLICY_VERSION (default 1),
    MODE (polling | webhook, default polling),
    PROVIDER_TIMEOUT_S (default 8), PROVIDER_MAX_CONCURRENCY (default 8),
    PROVIDER_MAX_OUTPUT_TOKENS (default 1024),
    DAILY_SPEND_CAP_USD (default 5.0), PROVIDER_COST_PER_MSG_USD (default 0.0004),
    HEALTHZ_PUBLIC_URL (used by the keep-warm workflow only).
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import find_dotenv, load_dotenv

    _env_file = find_dotenv(usecwd=True)
    if _env_file:
        load_dotenv(_env_file, override=False)
except ImportError:
    pass



def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except (ValueError, AttributeError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except (ValueError, AttributeError):
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _get_id_list(name: str) -> list[int]:
    raw = os.environ.get(name, "").strip()
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.append(int(part))
    return ids


# --- Run mode ---------------------------------------------------------------
MODE = get("MODE", "polling").lower()  # polling | webhook
TEST_ALLOW_ALL = _get_bool("TEST_ALLOW_ALL", False)
# Auto EN<->MM toggle: Myanmar input -> English output, English input ->
# Myanmar output, no manual target switching. Enabled by the owner 2026-09-19.
AUTO_TOGGLE = _get_bool("AUTO_TOGGLE", True)

# --- Telegram ---------------------------------------------------------------
BOT_TOKEN = get("BOT_TOKEN")
ALERT_BOT_TOKEN = get("ALERT_BOT_TOKEN")
ADMIN_CHAT_ID = get("ADMIN_CHAT_ID")
WEBHOOK_SECRET = get("WEBHOOK_SECRET")            # X-Telegram-Bot-Api-Secret-Token header
WEBHOOK_PATH_SECRET = get("WEBHOOK_PATH_SECRET")  # path segment of the webhook URL

# --- AI provider (OpenAI-compatible chat completions) ------------------------
PROVIDER_BASE_URL = get("PROVIDER_BASE_URL").rstrip("/")
PROVIDER_API_KEY = get("PROVIDER_API_KEY")
PROVIDER_MODEL = get("PROVIDER_MODEL")
PROVIDER_TIMEOUT_S = _get_float("PROVIDER_TIMEOUT_S", 8.0)
PROVIDER_MAX_CONCURRENCY = _get_int("PROVIDER_MAX_CONCURRENCY", 8)
# Keep enough output budget for a full translation of the 500-character input cap.
PROVIDER_MAX_OUTPUT_TOKENS = _get_int("PROVIDER_MAX_OUTPUT_TOKENS", 1024)
# Optional JSON list of backup providers, e.g.
# PROVIDERS_JSON='[{"name":"backup","base_url":"https://...","api_key":"...","model":"...","priority":2}]'
# When set, it replaces the single PROVIDER_* vars (which remain the default).
PROVIDERS_JSON = get("PROVIDER_JSON") or get("PROVIDERS_JSON")


def provider_defs() -> list[dict]:
    """Provider configs: optional PROVIDERS_JSON, else the single PROVIDER_* set."""
    import json

    if PROVIDERS_JSON:
        try:
            defs = json.loads(PROVIDERS_JSON)
            if isinstance(defs, list) and defs:
                return defs
        except (ValueError, TypeError):
            pass
    return [
        {
            "name": "primary",
            "base_url": PROVIDER_BASE_URL,
            "api_key": PROVIDER_API_KEY,
            "model": PROVIDER_MODEL,
            "priority": 1,
        }
    ]

# --- Storage ----------------------------------------------------------------
DATABASE_URL = get("DATABASE_URL")  # Neon pooled connection string
REDIS_URL = get("REDIS_URL")

# --- Product rules ----------------------------------------------------------
MAX_INPUT_CHARS = _get_int("MAX_INPUT_CHARS", 500)
POLICY_VERSION = _get_int("POLICY_VERSION", 1)

# --- Spending guard ---------------------------------------------------------
DAILY_SPEND_CAP_USD = _get_float("DAILY_SPEND_CAP_USD", 5.0)
PROVIDER_COST_PER_MSG_USD = _get_float("PROVIDER_COST_PER_MSG_USD", 0.0004)
IGNORE_DAILY_CAPS = _get_bool("IGNORE_DAILY_CAPS", False)
WITHHOLD_ON_LEAK = _get_bool("WITHHOLD_ON_LEAK", True)

# --- Group gate (Phase 0: GP-member-only access) ---------------------------
# Private DM requests are served ONLY to members of this group chat:
# getChatMember(GROUP_CHAT_ID, user_id) -> member/administrator/creator.
# Empty = gate disabled (falls back to the static allowlist only).
GROUP_CHAT_ID = _get_int("GROUP_CHAT_ID", 0)
GROUP_CACHE_TTL_S = _get_int("GROUP_CACHE_TTL_S", 6 * 3600)  # default 6h
# Deny verdicts expire fast: a user added to the group gets in within
# minutes instead of waiting out the 6h allow cache. Joins are rare,
# leaves are sticky - fail-closed stays, join-latency shrinks.
GROUP_DENY_TTL_S = _get_int("GROUP_DENY_TTL_S", 300)  # default 5 min

# --- Seeding ----------------------------------------------------------------
ALLOWED_USER_IDS = _get_id_list("ALLOWED_USER_IDS")
ADMIN_USER_IDS = _get_id_list("ADMIN_USER_IDS")


def validate_live() -> list[str]:
    """Return a list of missing required settings for a live run."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not PROVIDER_BASE_URL:
        missing.append("PROVIDER_BASE_URL")
    if not PROVIDER_API_KEY:
        missing.append("PROVIDER_API_KEY")
    if not PROVIDER_MODEL:
        missing.append("PROVIDER_MODEL")
    if MODE == "webhook" and not WEBHOOK_PATH_SECRET:
        missing.append("WEBHOOK_PATH_SECRET (required in webhook mode)")
    return missing


def telegram_session():
    """Build an aiogram session that honors the egress proxy when one is set.

    aiohttp (unlike httpx/curl) ignores proxy environment variables by
    default, so on hosts where all egress goes through a proxy the Bot
    must be given it explicitly - otherwise every Telegram API call fails
    with an SSL error and polling stops instantly. Returns None when no
    proxy is configured (aiogram default: direct connection).
    """
    proxy = (
        get("HTTPS_PROXY")
        or get("https_proxy")
        or get("ALL_PROXY")
        or get("all_proxy")
    )
    if not proxy:
        return None
    from aiogram.client.session.aiohttp import AiohttpSession

    return AiohttpSession(proxy=proxy)

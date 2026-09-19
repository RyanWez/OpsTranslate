"""aiogram handlers: commands, language-button callbacks, plain messages.

Input resolution (spec section 03), implemented exactly:
  plain message, no reply            -> translate that message
  plain message sent as a reply      -> translate the NEW message
                                       (reply relationship ignored)
  /tr as a reply to a message        -> translate the replied-to message
  /tr <text>                         -> translate the text after the command
  forwarded message                  -> translate the forwarded text
  reply to a message from the bot    -> ALREADY_TRANSLATED (plain messages)

Callback-query handlers (the language buttons) pass the allowlist gate
before doing anything else.
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyParameters

from . import strings
from .pipeline import Services, run_translation

log = logging.getLogger("opstranslate.handlers")

router = Router()

_bot_id_cache: dict[int, int] = {}


async def _bot_id(bot: Bot) -> int:
    """Resolve once per bot instance (one getMe call per process lifetime)."""
    key = id(bot)
    if key not in _bot_id_cache:
        _bot_id_cache[key] = (await bot.get_me()).id
    return _bot_id_cache[key]


def _strip_command(text: str) -> tuple[str, str]:
    """Split '/cmd@bot rest...' -> (cmd, rest)."""
    first, _, rest = text.partition(" ")
    cmd = first.split("@")[0]
    return cmd, rest.strip()


async def _gate_allowlist(services: Services, user_id: int) -> tuple[bool, str]:
    return await services.user_store.is_allowed(user_id)


async def _not_authorized(message: Message, user_id: int) -> None:
    await message.reply(strings.NOT_AUTHORIZED.format(user_id=user_id))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, services: Services) -> None:
    allowed, _ = await _gate_allowlist(services, message.from_user.id)
    if not allowed:
        await _not_authorized(message, message.from_user.id)
        return
    await services.user_store.set_target(message.from_user.id, "en")
    await message.answer(strings.WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message, services: Services) -> None:
    allowed, _ = await _gate_allowlist(services, message.from_user.id)
    if not allowed:
        await _not_authorized(message, message.from_user.id)
        return
    await message.answer(strings.HELP)


@router.message(Command("whoami"))
async def cmd_whoami(message: Message, services: Services) -> None:
    # EXEMPT from the allowlist gate: this is how new staff learn the ID
    # they need to be added with.
    await message.answer(f"Your Telegram user ID: {message.from_user.id}")


@router.message(Command("status"))
async def cmd_status(message: Message, services: Services) -> None:
    allowed, role = await _gate_allowlist(services, message.from_user.id)
    if not allowed or role != "admin":
        await _not_authorized(message, message.from_user.id)
        return
    states = services.router.states()
    prov_lines = "\n".join(f"- {name}: {state}" for name, state in states.items()) or "- none"
    stats = services.stats
    await message.answer(
        "Status\n"
        f"Policy: v{services.policy.version}\n"
        f"Providers:\n{prov_lines}\n"
        f"Today: {stats.translations_ok} ok / {stats.translations_failed} failed\n"
        f"Cache hit rate: {stats.cache_hit_rate:.1%}\n"
        f"p95 latency: {stats.p95_latency():.2f}s\n"
        f"Policy leaks (withheld): {stats.policy_leaks}"
    )


@router.message(Command("tr"))
async def cmd_tr(message: Message, services: Services, bot: Bot) -> None:
    allowed, _ = await _gate_allowlist(services, message.from_user.id)
    if not allowed:
        await _not_authorized(message, message.from_user.id)
        return

    text = message.text or ""
    _, rest = _strip_command(text)

    replied = message.reply_to_message
    if replied and not rest:
        # /tr as a reply: translate the replied-to message.
        rtext = replied.text or replied.caption or ""
        if not rtext.strip():
            await message.reply(strings.UNSUPPORTED_TYPE)
            return
        dst = await services.user_store.get_target(message.from_user.id)
        await run_translation(
            services,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            raw_text=rtext,
            anchor_message_id=replied.message_id,
            dst=dst,
        )
        return

    if rest:
        # /tr <text>: translate the text after the command.
        dst = await services.user_store.get_target(message.from_user.id)
        await run_translation(
            services,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            raw_text=rest,
            anchor_message_id=message.message_id,
            dst=dst,
        )
        return

    # Bare /tr: auto toggle mode needs no language choice.
    await message.answer(strings.AUTO_MODE)


# ---------------------------------------------------------------------------
# Language-button callbacks (allowlist-gated like any other request)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery, services: Services) -> None:
    allowed, _ = await _gate_allowlist(services, call.from_user.id)
    if not allowed:
        await call.answer("Not authorized.", show_alert=True)
        return
    lang = call.data.split(":", 1)[1]
    if lang not in ("my", "en"):
        await call.answer("Unknown language.")
        return
    await services.user_store.set_target(call.from_user.id, lang)
    await call.answer(strings.TARGET_SET.format(LANG=strings.LANG_NAME[lang]))
    try:
        await call.message.edit_text(
            strings.TARGET_SET.format(LANG=strings.LANG_NAME[lang])
        )
    except Exception:  # noqa: BLE001 - message may already be edited
        pass


# ---------------------------------------------------------------------------
# Plain messages
# ---------------------------------------------------------------------------

@router.message(F.text | F.caption)
async def on_text(message: Message, services: Services, bot: Bot) -> None:
    text = message.text or message.caption or ""

    # Gate 3: type check (empty text/caption cannot happen here, but be safe).
    if not text.strip():
        await message.reply(strings.UNSUPPORTED_TYPE)
        return

    # Reply to a message from the bot: it is already a translation.
    # This keeps the stateless guarantee - no translation->original map.
    me_id = await _bot_id(bot)
    replied = message.reply_to_message
    if replied and replied.from_user and replied.from_user.id == me_id:
        await message.reply(strings.ALREADY_TRANSLATED)
        return

    # Gate 4: allowlist.
    allowed, _ = await _gate_allowlist(services, message.from_user.id)
    if not allowed:
        await _not_authorized(message, message.from_user.id)
        return

    # Plain message sent as a reply: the reply relationship is ignored and
    # the NEW message is translated (avoids surprises).
    dst = await services.user_store.get_target(message.from_user.id)
    await run_translation(
        services,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        raw_text=text,
        anchor_message_id=message.message_id,
        dst=dst,
    )


def setup(router_services: Services, dp) -> None:
    """Make the Services object available to handlers via workflow data."""
    dp["services"] = router_services
    dp.include_router(router)

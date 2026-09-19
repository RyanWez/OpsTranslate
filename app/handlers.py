"""aiogram handlers: commands, language-button callbacks, plain messages.

Access control (Phase 0 - GP-member-only):
  * Private-DM only: group/supergroup/channel updates are ignored silently.
  * The sender must be a member of the ops group (GROUP_CHAT_ID), verified
    via getChatMember and cached; the static allowlist survives as an admin
    override. TEST_ALLOW_ALL=true bypasses everything for local tests.
  * Non-members get NOTHING (silent drop) - no placeholder, no error text,
    no provider credit spent. The bot is invisible to outsiders.

Input resolution (spec section 03), implemented exactly:
  plain message, no reply            -> translate that message
  plain message sent as a reply      -> translate the NEW message
                                       (reply relationship ignored)
  /tr as a reply to a message        -> translate the replied-to message
  /tr <text>                         -> translate the text after the command
  forwarded message                  -> translate the forwarded text
  reply to a message from the bot    -> ALREADY_TRANSLATED (plain messages)

Callback-query handlers (the language buttons) pass the access gate
before doing anything else. /whoami stays exempt (it only reveals the
caller's own user id, needed for allowlist seeding).
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyParameters

from . import strings
from . import config as configmod
from .groupgate import is_group_member
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


def _is_private(message: Message) -> bool:
    """Private-DM only: group/supergroup/channel updates are ignored."""
    return getattr(message.chat, "type", "private") == "private"


async def _gate_access(
    services: Services, message: Message, start_cmd: bool = False
) -> bool:
    """Phase 0 access gate: private chat AND group member (or allowlist).

    Non-members get NOTHING (silent drop). TEST_ALLOW_ALL=true bypasses
    everything for local tests. start_cmd=True forces a fresh Telegram
    lookup so /start works the moment a user joins the group.
    """
    if not _is_private(message):
        return False
    allowed, reason = await is_group_member(
        services.bot, services.cache, message.from_user.id,
        start_cmd=start_cmd,
    )
    if not allowed:
        log.info("access_denied user=%s reason=%s", message.from_user.id, reason)
    return allowed


async def _gate_allowlist(services: Services, user_id: int) -> tuple[bool, str]:
    """Static allowlist (admin override). The group gate already grants
    seeded staff/admin; /status consults this directly for the admin role."""
    return await services.user_store.is_allowed(user_id)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, services: Services) -> None:
    # Fresh lookup: a user added to the group must get in on the first
    # /start, never wait out a cached deny from before they joined.
    if not await _gate_access(services, message, start_cmd=True):
        return
    await services.user_store.set_target(message.from_user.id, "en")
    await message.answer(strings.WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message, services: Services) -> None:
    if not await _gate_access(services, message):
        return
    await message.answer(strings.HELP)


@router.message(Command("whoami"))
async def cmd_whoami(message: Message, services: Services) -> None:
    # EXEMPT from the access gate: this is how new staff learn the ID
    # they need to be added with. It reveals only the caller's own id,
    # costs nothing, and works even for non-members. Still private-only
    # so group chats stay quiet.
    if not _is_private(message):
        return
    await message.answer(f"Your Telegram user ID: {message.from_user.id}")


@router.message(Command("status"))
async def cmd_status(message: Message, services: Services) -> None:
    # Admin-only: group members without the admin role get nothing here
    # (silent, like every other non-member path).
    if not await _gate_access(services, message):
        return
    _, role = await _gate_allowlist(services, message.from_user.id)
    # TEST_ALLOW_ALL grants admin in test mode; otherwise the static
    # allowlist decides. Group membership alone is NOT enough for /status.
    is_admin = role == "admin" or configmod.TEST_ALLOW_ALL
    if not is_admin:
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
    if not await _gate_access(services, message):
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
# Language-button callbacks (access-gated like any other request)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery, services: Services) -> None:
    # Buttons only exist on the bot's own private-chat messages, but verify
    # anyway: dismiss the spinner silently for outsiders, change nothing.
    allowed, _ = await is_group_member(
        services.bot, services.cache, call.from_user.id
    )
    if not allowed:
        await call.answer()
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
    # Gate 0 (Phase 0): private chat + group member, else silent drop.
    # This runs BEFORE the type check so non-members never even learn the
    # bot only handles text - the bot is fully invisible to outsiders.
    if not await _gate_access(services, message):
        return

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

    # Gate 4 (static allowlist) is subsumed by the Phase 0 group gate above:
    # is_group_member already grants seeded staff/admin. No second check.

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

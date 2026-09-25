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

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    Message,
)

from . import strings
from .. import config as configmod
from .groupgate import status_of, drop_cached_verdict, is_group_member
from ..services.maintenance import get_config as get_maintenance_config
from ..services.pipeline import Services, run_translation

log = logging.getLogger("opstranslate.handlers")

router = Router()

_bot_id_cache: dict[int, int] = {}

import re

_WORD_CHAR_RE = re.compile(
    r"[a-zA-Z0-9\u1000-\u109F\uAA60-\uAA7F\uA9E0-\uA9FE\u4E00-\u9FFF\u3040-\u30FF\u0400-\u04FF\u0E00-\u0E7F]"
)


def _is_text_message_for_translation(text: str, custom_entities: list) -> bool:
    """Returns True if the message contains actual words/sentences to translate.
    Returns False if the message is purely custom emojis, standard emojis, or symbols.
    """
    if not text.strip():
        return False
    if custom_entities:
        text_utf16 = text.encode("utf-16-le")
        mask = [False] * (len(text_utf16) // 2)
        for e in custom_entities:
            for idx in range(e.offset, min(e.offset + e.length, len(mask))):
                mask[idx] = True
        remaining_utf16 = b"".join(
            text_utf16[i * 2 : (i + 1) * 2] for i in range(len(mask)) if not mask[i]
        )
        remaining_text = remaining_utf16.decode("utf-16-le", errors="ignore").strip()
        return bool(_WORD_CHAR_RE.search(remaining_text))
    return bool(_WORD_CHAR_RE.search(text))


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

    Uses the Services-scoped UserStore so the hot path benefits from the
    60 s allowlist memo (P1.4) instead of constructing a fresh UserStore
    per message and hitting Postgres every time.
    """
    if not _is_private(message):
        return False
    allowed, reason = await is_group_member(
        services.bot, services.cache, message.from_user.id,
        start_cmd=start_cmd, user_store=services.user_store,
    )
    if not allowed:
        log.info("access_denied user=%s reason=%s", message.from_user.id, reason)
        if reason == "suspended":
            try:
                warn = strings.get_emoji("warning")
                await message.answer(f"{warn} Your account access has been suspended by an administrator.", parse_mode="HTML")
            except Exception:
                pass
        return False
    else:
        try:
            if message.from_user and hasattr(services.user_store, "sync_user_profile"):
                asyncio.create_task(
                    services.user_store.sync_user_profile(
                        message.from_user.id,
                        full_name=getattr(message.from_user, "full_name", None),
                        username=getattr(message.from_user, "username", None),
                        auto_allow=True,
                    )
                )
        except Exception:  # noqa: BLE001
            log.warning("user_profile_sync_failed", exc_info=True)
    return allowed


async def _gate_allowlist(services: Services, user_id: int) -> tuple[bool, str]:
    """Static allowlist (admin override). The group gate already grants
    seeded staff/admin; /status consults this directly for the admin role."""
    return await services.user_store.is_allowed(user_id)


async def _check_maintenance(
    services: Services, message: Message
) -> bool:
    """Return True if maintenance is active and the user should be blocked.

    Admins are exempt when ``allow_admin_bypass`` is enabled.  When blocked
    the maintenance notice is sent and the caller should ``return``.
    """
    try:
        cfg = await get_maintenance_config()
        if not cfg.enabled:
            return False
        # Admin bypass
        if cfg.allow_admin_bypass:
            try:
                _, role = await services.user_store.is_allowed(message.from_user.id)
                if role == "admin":
                    return False
            except Exception:
                pass
            # Also check env-seeded admins
            if message.from_user.id in configmod.ADMIN_USER_IDS:
                return False
        try:
            await message.answer(strings.maintenance_text(cfg.message), parse_mode="HTML")
        except Exception:
            pass
        log.info("maintenance_blocked user=%s", message.from_user.id)
        return True
    except Exception:
        log.warning("maintenance_check_failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, services: Services) -> None:
    # Fresh lookup: a user added to the group must get in on the first
    # /start, never wait out a cached deny from before they joined.
    if not await _gate_access(services, message, start_cmd=True):
        return
    if await _check_maintenance(services, message):
        return
    await services.user_store.set_target(message.from_user.id, "en")
    try:
        from .commands import register_bot_commands
        asyncio.create_task(register_bot_commands(services.bot))
    except Exception:
        pass
    name = (
        getattr(message.from_user, "first_name", None)
        or getattr(message.from_user, "full_name", None)
    ) if message.from_user else None
    username = getattr(message.from_user, "username", None) if message.from_user else None
    await message.answer(strings.welcome_text(name=name, username=username), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message, services: Services) -> None:
    if not await _gate_access(services, message):
        return
    if await _check_maintenance(services, message):
        return
    await message.answer(strings.help_text(), parse_mode="HTML")


@router.message(Command("whoami"))
async def cmd_whoami(message: Message, services: Services) -> None:
    # EXEMPT from the access gate: this is how new staff learn the ID
    # they need to be added with. It reveals only the caller's own id,
    # costs nothing, and works even for non-members. Still private-only
    # so group chats stay quiet.
    if not _is_private(message):
        return
    badge = strings.get_emoji("whoami_badge")
    await message.answer(f"{badge} Your Telegram user ID: <code>{message.from_user.id}</code>", parse_mode="HTML")
    # P3: a /whoami from a non-member is the onboarding signal. Alert so
    # staff notice without polling the logs, but never include message text.
    try:
        allowed, _ = await is_group_member(
            services.bot, services.cache, message.from_user.id,
            user_store=services.user_store,
        )
        if message.from_user and hasattr(services.user_store, "sync_user_profile"):
            asyncio.create_task(
                services.user_store.sync_user_profile(
                    message.from_user.id,
                    full_name=getattr(message.from_user, "full_name", None),
                    username=getattr(message.from_user, "username", None),
                    auto_allow=allowed,
                )
            )
        if not allowed:
            await services.alerts.send(
                "P3",
                "UNKNOWN_WHOAMI",
                "onboarding",
                f"Unknown user requested /whoami: id={message.from_user.id}",
                "Add to allowlist or invite to the ops group if legitimate.",
            )
    except Exception:  # noqa: BLE001 - alert must never break the command
        log.warning("whoami_alert_failed", exc_info=True)


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
    chart = strings.get_emoji("status_chart")
    shield = strings.get_emoji("help_privacy")
    ok_icon = strings.get_emoji("status_ok")
    fail_icon = strings.get_emoji("status_fail")
    await message.answer(
        f"{chart} <b>Status</b>\n"
        f"{shield} Policy: v{services.policy.version}\n"
        f"Providers:\n{prov_lines}\n"
        f"Today: {ok_icon} {stats.translations_ok} ok / {fail_icon} {stats.translations_failed} failed\n"
        f"Cache hit rate: {stats.cache_hit_rate:.1%}\n"
        f"p95 latency: {stats.p95_latency():.2f}s\n"
        f"Policy leaks (withheld): {stats.policy_leaks}",
        parse_mode="HTML",
    )


@router.message(Command("report"))
async def cmd_report(message: Message, services: Services) -> None:
    """Spec §12: Bad-translation feedback reporter.
    
    Staff reply to a translation with /report [reason] or send /report [reason]
    to flag bad output or policy issues.
    """
    if not await _gate_access(services, message):
        return
    if await _check_maintenance(services, message):
        return

    reply = message.reply_to_message
    _, note = _strip_command(message.text or "")
    note = note.strip() or "No details provided"

    # Privacy by construction: never send raw message text in alerts.
    ref_id = reply.message_id if reply else message.message_id
    check = strings.get_emoji("report_success")
    try:
        await services.alerts.send(
            "P3",
            "TRANSLATION_REPORT",
            f"user_{message.from_user.id}",
            f"Staff translation report: user={message.from_user.id} ref_msg={ref_id} note={note[:200]}",
            "Review translation quality and policy dictionary if terminology leaked.",
        )
        await message.reply(f"{check} Feedback received. Thank you for reporting to the ops team.", parse_mode="HTML")
    except Exception:
        log.warning("translation_report_failed", exc_info=True)
        await message.reply(f"{check} Feedback recorded.", parse_mode="HTML")


@router.message(Command("tr"))
async def cmd_tr(message: Message, services: Services, bot: Bot) -> None:
    if not await _gate_access(services, message):
        return
    if await _check_maintenance(services, message):
        return

    text = message.text or ""
    _, rest = _strip_command(text)

    replied = message.reply_to_message
    if replied and not rest:
        # /tr as a reply: translate the replied-to message.
        rtext = replied.text or replied.caption or ""
        if not rtext.strip():
            await message.reply(strings.unsupported_type_text(), parse_mode="HTML")
            return
        dst = await services.user_store.get_target(message.from_user.id)
        await run_translation(
            services,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            raw_text=rtext,
            anchor_message_id=replied.message_id,
            dst=dst,
            username=getattr(message.from_user, "username", None) if message.from_user else None,
            display_name=getattr(message.from_user, "full_name", None) if message.from_user else None,
        )
        return

    if rest:
        # /tr <text>: translate the text after the command.
        entities = message.entities or message.caption_entities or []
        custom_entities = [
            e for e in entities
            if getattr(e, "type", None) == "custom_emoji" and getattr(e, "custom_emoji_id", None)
        ]
        if not _is_text_message_for_translation(rest, custom_entities):
            if custom_entities:
                items = []
                seen_ids = set()
                for e in custom_entities:
                    cid = str(e.custom_emoji_id)
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        try:
                            char = e.extract_from(text)
                        except Exception:
                            char = "✨"
                        items.append((cid, char))
                await message.reply(strings.custom_emoji_detected_text(items), parse_mode="HTML")
                return
            else:
                await message.reply(strings.standard_emoji_info_text(rest), parse_mode="HTML")
                return

        dst = await services.user_store.get_target(message.from_user.id)
        await run_translation(
            services,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            raw_text=rest,
            anchor_message_id=message.message_id,
            dst=dst,
            username=getattr(message.from_user, "username", None) if message.from_user else None,
            display_name=getattr(message.from_user, "full_name", None) if message.from_user else None,
        )
        return

    # Bare /tr: auto toggle mode needs no language choice.
    await message.answer(strings.auto_mode_text(), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Language-button callbacks (access-gated like any other request)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery, services: Services) -> None:
    # Buttons only exist on the bot's own private-chat messages, but verify
    # anyway: dismiss the spinner silently for outsiders, change nothing.
    allowed, _ = await is_group_member(
        services.bot, services.cache, call.from_user.id,
        user_store=services.user_store,
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
    if await _check_maintenance(services, message):
        return

    text = message.text or message.caption or ""

    # Gate 3: type check (empty text/caption cannot happen here, but be safe).
    if not text.strip():
        await message.reply(strings.unsupported_type_text(), parse_mode="HTML")
        return

    # Reply to a message from the bot: it is already a translation.
    # This keeps the stateless guarantee - no translation->original map.
    me_id = await _bot_id(bot)
    replied = message.reply_to_message
    if replied and replied.from_user and replied.from_user.id == me_id:
        await message.reply(strings.ALREADY_TRANSLATED)
        return

    # Check for custom animated emojis or pure emojis
    entities = message.entities or message.caption_entities or []
    custom_entities = [
        e for e in entities
        if getattr(e, "type", None) == "custom_emoji" and getattr(e, "custom_emoji_id", None)
    ]

    if not _is_text_message_for_translation(text, custom_entities):
        if custom_entities:
            items: list[tuple[str, str]] = []
            seen_ids = set()
            for e in custom_entities:
                cid = str(e.custom_emoji_id)
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    try:
                        char = e.extract_from(text)
                    except Exception:
                        char = "✨"
                    items.append((cid, char))
            await message.reply(strings.custom_emoji_detected_text(items), parse_mode="HTML")
            return
        else:
            await message.reply(strings.standard_emoji_info_text(text), parse_mode="HTML")
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
        username=getattr(message.from_user, "username", None) if message.from_user else None,
        display_name=getattr(message.from_user, "full_name", None) if message.from_user else None,
    )


def setup(router_services: Services, dp) -> None:
    """Make the Services object available to handlers via workflow data."""
    dp["services"] = router_services
    if router.parent_router != dp:
        router._parent_router = None
        dp.include_router(router)


# ---------------------------------------------------------------------------
# Membership changes: keep the gate cache honest
# ---------------------------------------------------------------------------

@router.chat_member()
async def on_group_membership_change(
    event: ChatMemberUpdated, services: Services
) -> None:
    """A user joined or left the GP: drop THEIR cached verdict at once.

    `chat_member` updates describe OTHER users and need both the bot to be
    admin in the group and "chat_member" in allowed_updates (see
    main.ALLOWED_UPDATES). The subject is `event.new_chat_member.user`;
    `event.from_user` is the admin who made the change, so invalidating
    from_user would drop the wrong person's verdict.

    A kick must lock the door immediately - not after the 6h allow cache
    expires - and a join must open it immediately, not after the 5-minute
    deny TTL. Dropping the verdict costs one getChatMember on the next
    message. Failures here must never break event handling.
    """
    try:
        if not configmod.GROUP_CHAT_ID:
            return
        if event.chat.id != configmod.GROUP_CHAT_ID:
            return
        new_member = getattr(event, "new_chat_member", None)
        subject = getattr(new_member, "user", None)
        if subject is None:
            return
        await drop_cached_verdict(services.cache, subject.id)
        log.info("verdict_dropped user=%s status=%s",
                 subject.id, status_of(new_member))
    except Exception:  # noqa: BLE001 - bookkeeping must never raise
        log.warning("verdict_drop_failed", exc_info=True)


@router.my_chat_member()
async def on_bot_membership_change(
    event: ChatMemberUpdated, services: Services
) -> None:
    """The BOT's own membership changed (this is all `my_chat_member` sees).

    If the bot loses the group, getChatMember fails for everyone and the
    gate fails closed - the bot goes silent for every non-allowlisted
    member. That must be loud rather than silent, so it raises a P2 alert
    and resolves it when the bot is back.
    """
    try:
        if not configmod.GROUP_CHAT_ID:
            return
        if event.chat.id != configmod.GROUP_CHAT_ID:
            return
        status = status_of(getattr(event, "new_chat_member", None))
        if status in ("left", "kicked"):
            log.error("bot_removed_from_group status=%s", status)
            await services.alerts.send(
                "P2", "GROUP_GATE_UNAVAILABLE", "group",
                f"Bot is no longer in the ops group (status: {status}); "
                "membership checks fail closed for every non-allowlisted user.",
                "Re-add the bot to the group as an admin.",
            )
        elif status in ("member", "administrator", "creator"):
            await services.alerts.resolve(
                "GROUP_GATE_UNAVAILABLE", "group",
                "Bot is back in the ops group; membership checks restored.",
            )
    except Exception:  # noqa: BLE001 - bookkeeping must never raise
        log.warning("bot_membership_handler_failed", exc_info=True)

"""Request pipeline: Gates 3-10, the policied translation flow, and delivery.

Gate order (spec section 2) - cheap deterministic checks sit in front of
the paid provider call:
  1. Webhook security        (main.py - path secret + header)
  2. Idempotency             (main.py - Redis SET NX EX 300 on update_id)
  3. Type check              (here)
  4. Allowlist               (here; /whoami is exempt)
  5. Length cap              (here; counted on the RAW text)
  6. Language + support      (here; low-confidence/mixed -> src="auto")
  7. Duplicate               (here; in-flight -> drop, answered -> resend)
  8. Rate limit              (here; 2 per rolling 30s, in-process)
  9. Cache                   (here; sha1 of normalized text + src + dst + policy)
 10. Policy pipeline         (here; mask -> provider -> render -> deny-scan)

Only Gate 10 costs money.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyParameters,
)
from aiogram.utils.chat_action import ChatActionSender

from . import config, strings
from .cache import Cache, cache_key, duplicate_key
from .langdetect import detect
from . import ratelimit
from .policy import (
    PLACEHOLDER_RE,
    Policy,
    build_system_prompt,
    deny_scan,
    is_meta_response,
    mask,
    normalise,
    protect_entities,
    ratio_ok,
    render,
    restore_entities,
    strict_suffix,
)
from .provider import AllProvidersDown, ProviderRouter
from .alerts import AlertManager
from .stats import Stats

log = logging.getLogger("opstranslate.pipeline")

HANDLER_BUDGET_S = 60.0


class PolicyRefusal(Exception):
    """Raised when the deny-scan still fires after the repair attempt."""

    def __init__(self, leaks: list[str]):
        super().__init__("policy refusal")
        self.leaks = leaks


@dataclass
class Services:
    bot: object  # aiogram Bot (typed loosely to keep imports light)
    policy: Policy
    router: ProviderRouter
    cache: Cache
    alerts: AlertManager
    stats: Stats
    user_store: "UserStore" = field(default=None)  # set in userstore module
    started_at: float = field(default_factory=time.monotonic)


def copy_keyboard(result_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.COPY_BUTTON,
                    copy_text=CopyTextButton(text=result_text),
                )
            ]
        ]
    )


def lang_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=name, callback_data=f"lang:{code}")
                for name, code in [
                    ("Myanmar", "my"),
                    ("English", "en"),
                ]
            ]
        ]
    )


def _today_key(prefix: str) -> str:
    return time.strftime(f"{prefix}:%Y-%m-%d")


# ---------------------------------------------------------------------------
# Gate 10 - the policied translation pipeline
# ---------------------------------------------------------------------------

async def translate_policied(
    text: str,
    src: str,
    dst: str,
    policy: Policy,
    router: ProviderRouter,
    alerts: AlertManager,
) -> tuple[str, str, dict]:
    """Run mask -> provider -> render -> deny-scan -> repair.

    Returns (final_text, provider_name, meta). Raises PolicyRefusal when the
    deny-scan still fires after one repair attempt - the translation is then
    withheld, never shipped.
    """
    protected, restore = protect_entities(normalise(text))
    masked = mask(protected, src, policy)
    prompt = build_system_prompt(src, dst, policy)

    out, provider = await router.translate(masked, prompt)

    def _sane(o: str) -> bool:
        return ratio_ok(text, o, src=src, dst=dst) and not is_meta_response(o)

    # Sanity gate: one retry on garbage output, then give up.
    if not _sane(out):
        out, provider = await router.translate(masked, prompt, force=provider)
        if not _sane(out):
            raise AllProvidersDown("unstable output")

    rendered = render(out, dst, policy)  # Layer 2 post
    leaks = deny_scan(rendered, dst, policy)  # Layer 3
    if leaks:
        log.warning("policy_leak_attempt", extra={"leaks": leaks, "provider": provider})
        # One stricter repair retry. On a second hit: withhold, log, alert.
        out, provider = await router.translate(
            masked, prompt + strict_suffix(leaks), force=provider
        )
        if not _sane(out):
            raise AllProvidersDown("unstable output after repair")
        rendered = render(out, dst, policy)
        leaks = deny_scan(rendered, dst, policy)
        if leaks:
            await alerts.send(
                "P2",
                "POLICY_LEAK",
                f"v{policy.version}",
                f"1 leak survived repair \u00b7 provider {provider} \u00b7 policy v{policy.version}",
                "Review the deny list.",
            )
            raise PolicyRefusal(leaks)

    final = restore_entities(rendered, restore)
    # Report the concepts that actually fired (placeholders in the masked
    # text), not raw substring hits - "ဂိမ်း" inside "ဂိမ်းအိုင်ဒီ" must not
    # double-count as a separate platform hit.
    fired = list(dict.fromkeys(PLACEHOLDER_RE.findall(masked)))
    return final, provider, {
        "policy_hits": fired,
        "deny_hits": 0,
        "ratio": round(len(final) / max(len(text), 1), 2),
    }


# ---------------------------------------------------------------------------
# Delivery: placeholder first (reply anchor set on THIS call), then edit.
# editMessageText cannot add a reply relationship afterwards.
# ---------------------------------------------------------------------------

async def _send_placeholder(services: Services, chat_id: int, anchor_id: int) -> int:
    msg = await services.bot.send_message(
        chat_id,
        strings.TRANSLATING,
        reply_parameters=ReplyParameters(
            message_id=anchor_id, allow_sending_without_reply=True
        ),
    )
    return msg.message_id


async def _edit_text(
    services: Services,
    chat_id: int,
    placeholder_id: int,
    text: str,
    reply_markup=None,
) -> None:
    """Best-effort message edit: a FAILED_PRECONDITION (message not modified)
    is normal when two frames render identically - swallow it, let real
    errors propagate."""
    try:
        await services.bot.edit_message_text(
            chat_id=chat_id,
            message_id=placeholder_id,
            text=text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except Exception as exc:  # noqa: BLE001
        if "message is not modified" in str(exc).lower():
            return
        raise


async def animate_working(
    services: Services,
    chat_id: int,
    placeholder_id: int,
    stop: "asyncio.Event",
) -> None:
    """Cycle the placeholder dots (Translating. -> .. -> ...) while the
    provider works, so the message feels alive during the 4-11s wait.
    ~1 edit per 1.2s: far under Telegram's ~30 edits/min/chat limit."""
    frames = [
        "\u23f3 Translating.",
        "\u23f3 Translating..",
        "\u23f3 Translating...",
    ]
    i = 0
    try:
        while not stop.is_set():
            try:
                async with asyncio.timeout(1.2):
                    await stop.wait()
                break  # stop was set: provider finished, exit quietly
            except (asyncio.TimeoutError, TimeoutError):
                pass  # 1.2s elapsed: advance one frame
            if stop.is_set():
                break
            i = (i + 1) % len(frames)
            try:
                await _edit_text(services, chat_id, placeholder_id, frames[i])
            except Exception:  # noqa: BLE001 - animation must never break delivery
                break
    except asyncio.CancelledError:
        pass


def reveal_frames(header: str, result: str) -> list[str]:
    """Split the validated result into progressive typewriter frames.

    Word-boundary chunks of ~12 words: a 250-char message yields 3-5 edits
    over ~1.5s. Only ever called on fully validated text - a policy leak
    must never be partially shown (withhold guarantee)."""
    words = result.split()
    if len(words) <= 4:
        return [f"{header}\n{result}"]
    step = max(4, (len(words) + 3) // 4)  # ~4 frames
    frames = []
    for end in range(step, len(words), step):
        frames.append(f"{header}\n{' '.join(words[:end])} \u2026")
    frames.append(f"{header}\n{result}")
    return frames


async def _edit_result(
    services: Services,
    chat_id: int,
    placeholder_id: int,
    src: str,
    dst: str,
    result: str,
    animate: bool = True,
) -> None:
    header = strings.TRANSLATION_HEADER.format(SRC=src.upper(), DST=dst.upper())
    if not animate:
        # Cache-hit path: the answer was instant, reveal it at once.
        await _edit_text(
            services, chat_id, placeholder_id,
            f"{header}\n{result}", reply_markup=copy_keyboard(result),
        )
        return
    frames = reveal_frames(header, result)
    for frame in frames[:-1]:
        await _edit_text(services, chat_id, placeholder_id, frame)
        await asyncio.sleep(0.35)
    await _edit_text(
        services, chat_id, placeholder_id,
        frames[-1], reply_markup=copy_keyboard(result),
    )


async def _edit_error(services: Services, chat_id: int, placeholder_id: int, text: str) -> None:
    # Not-modified-safe: the animation's last frame can equal the error text
    # path only in theory, but a 400 from Telegram must never mask delivery.
    await _edit_text(services, chat_id, placeholder_id, text)


async def _delete_placeholder(services: Services, chat_id: int, placeholder_id: int) -> None:
    """Remove the 'Translating…' placeholder so a policy refusal leaves
    nothing behind (spec: on a second deny hit, send nothing)."""
    try:
        await services.bot.delete_message(chat_id=chat_id, message_id=placeholder_id)
    except Exception:
        # Message may already be gone; the withhold guarantee is what matters.
        pass


# ---------------------------------------------------------------------------
# Usage logging (metadata only - NEVER message text)
# ---------------------------------------------------------------------------

async def log_usage(services: Services, **fields) -> None:
    from . import db as dbmod
    from .models import UsageLog

    if not dbmod.is_configured():
        return
    try:
        async with dbmod.session() as sess:
            sess.add(UsageLog(**fields))
            await sess.commit()
    except Exception as exc:  # noqa: BLE001 - logging must never break the flow
        log.warning("usage_log_failed: %s", exc)


def _text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# The message pipeline (Gates 3-10)
# ---------------------------------------------------------------------------

def resolve_toggle_dst(src: str, dst: str) -> str:
    """Auto EN<->MM toggle (owner request 2026-09-19).

    Myanmar input -> English output; English input -> Myanmar output.
    "auto" (uncertain/mixed input) keeps the caller's dst, which is the
    user's stored target (default English).
    """
    if src == "my":
        return "en"
    if src == "en":
        return "my"
    return dst


async def run_translation(
    services: Services,
    *,
    user_id: int,
    chat_id: int,
    raw_text: str,
    anchor_message_id: int,
    dst: str,
) -> None:
    """Translate *raw_text* to *dst* and deliver it. Gates 3-10.

    Gate 4 (allowlist) must be checked by the caller before invoking this,
    because /whoami is exempt from it.
    """
    t0 = time.monotonic()

    # -- Gate 5: length cap, counted on the RAW text, pre-mask -------------
    if not (1 <= len(raw_text) <= config.MAX_INPUT_CHARS):
        await services.bot.send_message(
            chat_id,
            strings.TOO_LONG.format(n=len(raw_text)),
            reply_parameters=ReplyParameters(
                message_id=anchor_message_id, allow_sending_without_reply=True
            ),
        )
        await log_usage(
            services, user_id=user_id, char_len=len(raw_text),
            status="too_long", policy_version=services.policy.version,
        )
        return

    # -- Gate 6: language ----------------------------------------------------
    src, confidence, oos_name = detect(raw_text)
    if oos_name is not None:
        await services.bot.send_message(
            chat_id,
            strings.UNSUPPORTED_LANG.format(lang=oos_name),
            reply_parameters=ReplyParameters(
                message_id=anchor_message_id, allow_sending_without_reply=True
            ),
        )
        await log_usage(
            services, user_id=user_id, src_lang=src, dst_lang=dst,
            char_len=len(raw_text), status="unsupported_lang",
            policy_version=services.policy.version,
        )
        return

    # -- Auto EN<->MM toggle --------------------------------------------------
    if config.AUTO_TOGGLE and oos_name is None:
        dst = resolve_toggle_dst(src, dst)

    # -- Gate 7: duplicate ---------------------------------------------------
    dup = duplicate_key(user_id, raw_text, dst)
    if not await services.cache.mark_inflight(dup):
        return  # identical message still in flight: drop silently, one slot

    try:
        ckey = cache_key(raw_text, src, dst, services.policy.version)
        cached = await services.cache.get(ckey)

        if cached is not None and (time.time() - cached.stored_at) < 30:
            # Already answered within 30s: resend, NO rate slot consumed.
            placeholder_id = await _send_placeholder(services, chat_id, anchor_message_id)
            await _edit_result(services, chat_id, placeholder_id, src, dst, cached.text,
                               animate=False)
            services.stats.record_ok(time.monotonic() - t0, cache_hit=True)
            return

        # -- Gate 8: rate limit (sliding window, in-process) ----------------
        wait_s = ratelimit.check(user_id)
        if wait_s:
            await services.bot.send_message(
                chat_id,
                strings.RATE_LIMIT.format(n=wait_s),
                reply_parameters=ReplyParameters(
                    message_id=anchor_message_id, allow_sending_without_reply=True
                ),
            )
            await log_usage(
                services, user_id=user_id, src_lang=src, dst_lang=dst,
                char_len=len(raw_text), status="rate_limited",
                policy_version=services.policy.version,
            )
            return

        # Per-user daily soft cap (admin-overridable via allowed_users).
        soft_cap = await services.user_store.daily_soft_cap(user_id)
        used = await services.cache.incr(_today_key(f"softcap:{user_id}"), 86400)
        if used > soft_cap:
            await services.bot.send_message(
                chat_id, strings.DAILY_CAP_REACHED,
                reply_parameters=ReplyParameters(
                    message_id=anchor_message_id, allow_sending_without_reply=True
                ),
            )
            return

        # -- Gate 9: cache ---------------------------------------------------
        if cached is not None:
            placeholder_id = await _send_placeholder(services, chat_id, anchor_message_id)
            await _edit_result(services, chat_id, placeholder_id, src, dst, cached.text,
                               animate=False)
            services.stats.record_ok(time.monotonic() - t0, cache_hit=True)
            await log_usage(
                services, user_id=user_id, src_lang=src, dst_lang=dst,
                text_hash=_text_hash(raw_text), char_len=len(raw_text),
                cache_hit=True, latency_ms=int((time.monotonic() - t0) * 1000),
                policy_version=services.policy.version, status="ok",
            )
            return

        # -- Gate 10: policy pipeline (the only gate that costs money) -------
        placeholder_id = await _send_placeholder(services, chat_id, anchor_message_id)

        # Spend cap: degrade to cache-only past the cap (cache already missed).
        spent = await services.cache.get_float(_today_key("spend"))
        if spent >= config.DAILY_SPEND_CAP_USD:
            await services.alerts.send(
                "P2", "SPEND_CAP", "daily",
                f"Daily spend cap reached (${spent:.2f}). Serving cache-only.",
                "Raise the cap in settings or wait for tomorrow.",
            )
            await _edit_error(services, chat_id, placeholder_id, strings.SPEND_CAP_REACHED)
            return

        # Animated dots keep the placeholder alive while the provider
        # works (4-11s). Cancelled the moment translation finishes so the
        # typewriter reveal starts on a clean handoff.
        anim_stop = asyncio.Event()
        anim_task = asyncio.create_task(
            animate_working(services, chat_id, placeholder_id, anim_stop)
        )
        async def _stop_animation() -> None:
            anim_stop.set()
            try:
                await asyncio.wait_for(asyncio.shield(anim_task), timeout=5)
            except (asyncio.TimeoutError, TimeoutError):
                anim_task.cancel()

        try:
            # Typing indicator while the provider works - Telegram shows
            # "typing..." next to the bot name and auto-expires it after ~5s,
            # so the sender re-emits it until this block exits.
            async with (
                ChatActionSender(bot=services.bot, chat_id=chat_id, action="typing"),
                asyncio.timeout(HANDLER_BUDGET_S),
            ):
                result, provider_name, meta = await translate_policied(
                    raw_text, src, dst, services.policy, services.router, services.alerts
                )
        except PolicyRefusal:
            services.stats.record_leak()
            services.stats.record_failure()
            await _stop_animation()
            # Withhold: delete the placeholder so the user receives nothing.
            # The P2 alert (concept/provider/version only, never message
            # text) is the staff-visible signal.
            await _delete_placeholder(services, chat_id, placeholder_id)
            await log_usage(
                services, user_id=user_id, src_lang=src, dst_lang=dst,
                text_hash=_text_hash(raw_text), char_len=len(raw_text),
                cache_hit=False, latency_ms=int((time.monotonic() - t0) * 1000),
                policy_version=services.policy.version, deny_hits=1, status="policy_refusal",
            )
            return
        except AllProvidersDown as exc:
            services.stats.record_failure()
            await _stop_animation()
            await services.alerts.send(
                "P1", "PROVIDER_OUTAGE", "all",
                f"All providers failed. {exc}",
                "Bot is serving cache-only until a provider recovers.",
            )
            await _edit_error(services, chat_id, placeholder_id, strings.ERROR_GENERIC)
            await log_usage(
                services, user_id=user_id, src_lang=src, dst_lang=dst,
                text_hash=_text_hash(raw_text), char_len=len(raw_text),
                cache_hit=False, status="provider_outage",
                policy_version=services.policy.version, error_code="all_providers_down",
            )
            return
        except (asyncio.TimeoutError, TimeoutError):
            services.stats.record_failure()
            await _stop_animation()
            await _edit_error(services, chat_id, placeholder_id, strings.ERROR_GENERIC)
            return

        await _stop_animation()
        await services.cache.incr_float(
            _today_key("spend"), config.PROVIDER_COST_PER_MSG_USD, 86400
        )
        await services.cache.put(ckey, result)
        await _edit_result(services, chat_id, placeholder_id, src, dst, result)
        services.stats.record_ok(time.monotonic() - t0, cache_hit=False)
        await log_usage(
            services, user_id=user_id, src_lang=src, dst_lang=dst,
            text_hash=_text_hash(raw_text), char_len=len(raw_text),
            provider_id=None, cache_hit=False,
            latency_ms=int((time.monotonic() - t0) * 1000),
            policy_version=services.policy.version,
            policy_hits=meta.get("policy_hits"), deny_hits=meta.get("deny_hits"),
            ratio=meta.get("ratio"), status="ok",
        )
    finally:
        await services.cache.clear_inflight(dup)

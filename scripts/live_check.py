"""Live environment check - run this on a machine that can reach Telegram
and the AI provider (the build sandbox cannot; its egress firewall blocks
both).

    set -a && . .env && set +a
    python -m scripts.live_check              # connectivity + 3 probe translations
    python -m scripts.live_check --regression # plus the 40-case set (spec 4.6)

Reads everything from the environment, prints no secret, and never writes
anywhere. Exit code 0 = every step passed.

Steps:
  1. config    - required vars present, provider defs usable, JSON valid
  2. telegram  - getMe proves the bot token
  3. group     - getChatMember proves the bot is an ADMIN of the GP
                 (without admin rights no chat_member updates arrive, so a
                 kicked member's cached verdict would never be dropped)
  4. translate - three probe messages through the real policy pipeline
  5. policy    - optional: the 40-case regression set against the provider
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from app import config

FAILURES: list[str] = []


def report(ok: bool, label: str, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(label)
    return ok


def mask(value: str) -> str:
    return f"{value[:10]}...{value[-4:]}" if len(value) > 16 else "***"


# ---------------------------------------------------------------------------
# 1. config
# ---------------------------------------------------------------------------

def check_config() -> bool:
    print("== 1. configuration ==")
    missing = config.validate_live()
    report(not missing, "required settings present", ", ".join(missing) or "ok")
    report(config.MODE in ("polling", "webhook"), "MODE is polling or webhook",
           config.MODE)
    report(bool(config.BOT_TOKEN), "BOT_TOKEN set", mask(config.BOT_TOKEN))

    if config.PROVIDERS_JSON:
        try:
            json.loads(config.PROVIDERS_JSON)
            report(True, "PROVIDERS_JSON parses")
        except (ValueError, TypeError) as exc:
            # provider_defs() swallows this and silently falls back to the
            # single PROVIDER_* set - which is never what the operator meant.
            report(False, "PROVIDERS_JSON parses",
                   f"{type(exc).__name__}: the single PROVIDER_* set would be "
                   "used instead, silently")

    defs = config.provider_defs()
    names = [d.get("name") for d in defs]
    report(len(defs) >= 1, "at least one provider configured", ", ".join(names))
    for d in defs:
        base = (d.get("base_url") or "").rstrip("/")
        report(base.startswith("http"), f"provider {d.get('name')} base_url",
               f"{base}/chat/completions")
        report(bool(d.get("api_key")), f"provider {d.get('name')} api_key",
               mask(d.get("api_key") or ""))

    print(f"      group gate      : GROUP_CHAT_ID={config.GROUP_CHAT_ID or '(disabled)'}"
          f" TEST_ALLOW_ALL={config.TEST_ALLOW_ALL}")
    print(f"      budget          : provider timeout {config.PROVIDER_TIMEOUT_S}s")
    return not FAILURES


# ---------------------------------------------------------------------------
# 2-3. telegram
# ---------------------------------------------------------------------------

async def check_telegram() -> bool:
    from aiogram import Bot
    from aiogram.exceptions import TelegramAPIError

    print("\n== 2. telegram ==")
    bot = Bot(token=config.BOT_TOKEN, session=config.telegram_session())
    try:
        me = await bot.get_me()
        report(True, "getMe (bot token valid)",
               f"@{me.username} id={me.id}")

        print("\n== 3. group gate ==")
        if not config.GROUP_CHAT_ID:
            report(True, "GROUP_CHAT_ID unset - gate disabled, allowlist only")
            return True
        try:
            member = await bot.get_chat_member(config.GROUP_CHAT_ID, me.id)
            status = str(getattr(member.status, "value", member.status)).lower()
            is_admin = status in ("administrator", "creator")
            report(is_admin, "bot is an admin of the GP",
                   f"status={status}"
                   + ("" if is_admin else
                      " - chat_member updates will NOT arrive, so a kicked "
                      "member's cached verdict survives until the TTL"))
        except TelegramAPIError as exc:
            report(False, "getChatMember on the GP", f"{type(exc).__name__}: {exc}")
        return True
    except TelegramAPIError as exc:
        report(False, "getMe", f"{type(exc).__name__}: {exc}")
        return False
    finally:
        await bot.session.close()


# ---------------------------------------------------------------------------
# 4. real translations through the real pipeline
# ---------------------------------------------------------------------------

PROBES = [
    ("my", "ဂိမ်းအိုင်ဒီ မှားနေတယ်"),
    ("en", "please check my game points"),
    ("auto", "ဂိမ်းအကောင့် ကို https://x.co/a မှာ ဖွင့်ပေးပါ"),
]


async def check_translate() -> None:
    from app.policy.langdetect import detect
    from app.policy.policy import compile_policy, mask, normalise, protect_entities
    from app.services.alerts import AlertManager
    from app.services.pipeline import resolve_toggle_dst, translate_policied
    from app.services.provider import Provider, ProviderRouter

    print("\n== 4. probe translations (real provider) ==")
    policy = compile_policy(config.POLICY_VERSION)
    router = ProviderRouter(
        providers=[
            Provider(
                name=d.get("name", "primary"),
                base_url=(d.get("base_url") or "").rstrip("/"),
                api_key=d.get("api_key") or "",
                model=d.get("model") or "",
                priority=int(d.get("priority", 1)),
                timeout_s=float(d.get("timeout_s", config.PROVIDER_TIMEOUT_S)),
            )
            for d in config.provider_defs()
        ],
        max_concurrency=config.PROVIDER_MAX_CONCURRENCY,
    )
    alerts = AlertManager(config.ALERT_BOT_TOKEN, config.ADMIN_CHAT_ID)
    try:
        for label, text in PROBES:
            src, confidence, oos = detect(text)
            if oos:
                report(False, f"probe {label}", f"detected out-of-scope {oos}")
                continue
            dst = resolve_toggle_dst(src, "en") if config.AUTO_TOGGLE else "en"
            t0 = time.monotonic()
            try:
                final, provider, meta = await translate_policied(
                    text, src, dst, policy, router, alerts
                )
            except Exception as exc:  # noqa: BLE001 - report, keep going
                report(False, f"probe {label}", f"{type(exc).__name__}: {exc}")
                continue
            ms = int((time.monotonic() - t0) * 1000)
            protected, _ = protect_entities(normalise(text))
            print(f"  {label}: {src} -> {dst} via {provider} in {ms}ms")
            print(f"    masked : {mask_text(protected)}")
            print(f"    input  : {text}")
            print(f"    output : {final}")
            ok = bool(final.strip()) and "⟦" not in final
            report(ok, f"probe {label} returned a clean translation",
                   f"policy_hits={meta.get('policy_hits')} ratio={meta.get('ratio')}")
            report(ms < config.PROVIDER_TIMEOUT_S * 1000,
                   f"probe {label} inside the provider timeout", f"{ms}ms")
    finally:
        await router.close()


def mask_text(text: str) -> str:
    from app.policy.policy import compile_policy, mask

    return mask(text, "auto", compile_policy(config.POLICY_VERSION))


# ---------------------------------------------------------------------------
# 5. the regression set, live
# ---------------------------------------------------------------------------

async def check_regression() -> None:
    from app.policy.policy import compile_policy
    from app.policy.regression_set import run_live
    from app.services.provider import Provider, ProviderRouter

    print("\n== 5. 40-case regression set (live provider) ==")
    router = ProviderRouter(
        providers=[
            Provider(
                name=d.get("name", "primary"),
                base_url=(d.get("base_url") or "").rstrip("/"),
                api_key=d.get("api_key") or "",
                model=d.get("model") or "",
                timeout_s=float(d.get("timeout_s", config.PROVIDER_TIMEOUT_S)),
            )
            for d in config.provider_defs()
        ],
        max_concurrency=config.PROVIDER_MAX_CONCURRENCY,
    )
    try:
        results = await run_live(compile_policy(config.POLICY_VERSION), router)
    finally:
        await router.close()
    failures = {k: v for k, v in results.items() if v}
    for case_id, problems in failures.items():
        print(f"    {case_id}: {problems}")
    report(not failures, "all 40 cases pass against the live provider",
           f"{len(results) - len(failures)}/{len(results)}")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--regression", action="store_true",
                        help="also run the 40-case set through the provider")
    args = parser.parse_args()

    check_config()
    if not await check_telegram():
        print("\nstopping: Telegram is unreachable or the token is invalid")
        return 1
    await check_translate()
    if args.regression:
        await check_regression()

    print(f"\n{len(FAILURES)} failure(s)" + (f": {FAILURES}" if FAILURES else ""))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

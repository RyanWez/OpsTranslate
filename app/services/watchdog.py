"""Watchdog: periodic health checks that raise Telegram alerts.

Runs every 60 s. Checks:
- error rate >5 % in last 5 min (P2)
- p95 latency >4 s in last 5 min (P2)
- policy engine error rate >20 % in last 5 min (P1)

Daily digest at 09:00 Asia/Yangon (P3) via SHOULD 21.

All alerts carry only metadata, never message text.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("opstranslate.watchdog")

YANGON = ZoneInfo("Asia/Yangon")


async def _check_error_rate(services) -> None:
    rate = services.stats.error_rate_5m()
    total = services.stats.count_5m()
    # Require at least 10 events to avoid flapping on tiny samples
    if total >= 10 and rate > 0.05:
        await services.alerts.send(
            "P2",
            "HIGH_ERROR_RATE",
            "pipeline",
            f"Error rate {rate:.1%} over last 5 min ({total} requests).",
            "Check provider health and recent error_code in logs.",
        )
    else:
        # Resolve if previously active and now healthy
        await services.alerts.resolve(
            "HIGH_ERROR_RATE",
            "pipeline",
            f"Error rate recovered to {rate:.1%} over last 5 min.",
        )


async def _check_p95(services) -> None:
    p95 = services.stats.p95_5m()
    if p95 > 4.0 and services.stats.count_5m() >= 10:
        await services.alerts.send(
            "P2",
            "HIGH_P95_LATENCY",
            "pipeline",
            f"p95 latency {p95:.2f}s over last 5 min exceeds 4s.",
            "Check provider latency, concurrency, and Neon cold start.",
        )
    else:
        await services.alerts.resolve(
            "HIGH_P95_LATENCY",
            "pipeline",
            f"p95 recovered to {p95:.2f}s.",
        )


async def _check_policy_engine(services) -> None:
    rate = services.stats.policy_error_rate_5m()
    total = services.stats.count_5m()
    if total >= 10 and rate > 0.20:
        await services.alerts.send(
            "P1",
            "POLICY_ENGINE_ERROR_RATE",
            "policy",
            f"Policy engine failing on {rate:.1%} of requests over last 5 min.",
            "Check policy_data, deny lists, and recent deploys; roll back if needed.",
        )
    else:
        await services.alerts.resolve(
            "POLICY_ENGINE_ERROR_RATE",
            "policy",
            f"Policy engine error rate recovered to {rate:.1%}.",
        )


async def _maybe_digest(services, last_digest_date: list[str]) -> None:
    """Send daily digest once at 09:00 Yangon."""
    now = datetime.now(YANGON)
    if now.hour == 9 and now.minute < 2:
        today = now.strftime("%Y-%m-%d")
        if last_digest_date[0] == today:
            return
        last_digest_date[0] = today
        # Gather digest data: only metadata
        stats = services.stats
        states = services.router.states()
        prov_lines = ", ".join(f"{n}:{s}" for n, s in states.items()) or "none"
        # Spend from cache (best-effort)
        try:
            from .pipeline import _today_key
            spent = await services.cache.get_float(_today_key("spend"))
        except Exception:
            spent = 0.0
        text = (
            f"Daily digest {today}\n"
            f"Translations: {stats.translations_ok} ok / {stats.translations_failed} failed\n"
            f"Cache hit rate: {stats.cache_hit_rate:.1%}\n"
            f"p95: {stats.p95_latency():.2f}s\n"
            f"Policy leaks withheld: {stats.policy_leaks}\n"
            f"Spend: ${spent:.2f}\n"
            f"Providers: {prov_lines}"
        )
        await services.alerts.send(
            "P3",
            "DAILY_DIGEST",
            "summary",
            text,
            "Review dashboard for details.",
        )


async def watchdog_loop(services) -> None:
    """Run forever; call from lifespan."""
    last_digest = [""]
    # Initial delay so startup traffic can settle
    await asyncio.sleep(60)
    while True:
        try:
            await _check_error_rate(services)
            await _check_p95(services)
            await _check_policy_engine(services)
            await _maybe_digest(services, last_digest)
            # Multi-worker / Multi-replica sync: reload active providers from DB if configured
            from ..store import db as dbmod
            if dbmod.is_configured():
                from ..store.providers import sync_router_providers
                await sync_router_providers(services.router)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("watchdog_tick_failed: %s", exc)
        await asyncio.sleep(60)

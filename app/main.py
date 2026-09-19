"""Application entrypoint: FastAPI + aiogram.

Two run modes via MODE:
  polling - local testing, no public URL needed.
  webhook - production (Koyeb). POST /webhook/{WEBHOOK_PATH_SECRET}.

Gate 1 (webhook security) is enforced on the webhook endpoint: the path
secret must match AND the X-Telegram-Bot-Api-Secret-Token header must
match, otherwise 403 and the update is dropped silently.
Gate 2 (idempotency) runs as an update outer-middleware in both modes:
update_id not seen in the last 5 minutes (Redis SET NX EX 300).

/healthz is a real check (db, cache, policy loaded, any provider circuit
closed, recent successful traffic OR outside working hours) and returns
503 when degraded.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from . import config
from .alerts import AlertManager
from .cache import Cache
from .handlers import setup as setup_handlers
from .pipeline import Services
from .policy import compile_policy
from .provider import Provider, ProviderRouter
from .stats import Stats
from .userstore import UserStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("opstranslate.main")

YANGON = ZoneInfo("Asia/Yangon")
WORK_START_HOUR, WORK_END_HOUR = 8, 22


def build_services(bot: Bot) -> Services:
    policy = compile_policy(config.POLICY_VERSION)
    providers = []
    for d in config.provider_defs():
        providers.append(
            Provider(
                name=d.get("name", "primary"),
                base_url=(d.get("base_url") or "").rstrip("/"),
                api_key=d.get("api_key") or "",
                model=d.get("model") or "",
                priority=int(d.get("priority", 1)),
                enabled=bool(d.get("enabled", True)),
                timeout_s=float(d.get("timeout_s", config.PROVIDER_TIMEOUT_S)),
            )
        )
    router = ProviderRouter(
        providers=providers,
        max_concurrency=config.PROVIDER_MAX_CONCURRENCY,
    )
    services = Services(
        bot=bot,
        policy=policy,
        router=router,
        cache=Cache(config.REDIS_URL),
        alerts=AlertManager(config.ALERT_BOT_TOKEN, config.ADMIN_CHAT_ID),
        stats=Stats(),
        user_store=UserStore(),
    )
    return services


async def idempotency_middleware(handler, event: Update, data: dict):
    """Gate 2: drop duplicate update_ids (Telegram retries deliveries)."""
    services: Services = data["services"]
    if await services.cache.check_idempotent(event.update_id):
        return None
    return await handler(event, data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = config.validate_live()
    if missing:
        log.warning("missing configuration for live run: %s", ", ".join(missing))

    bot = Bot(token=config.BOT_TOKEN or "0:placeholder", session=config.telegram_session())
    services = build_services(bot)
    dp = Dispatcher()
    dp.update.outer_middleware(idempotency_middleware)
    setup_handlers(services, dp)

    app.state.services = services
    app.state.dp = dp
    app.state.bot = bot

    polling_task = None
    if config.MODE == "polling":
        import asyncio

        async def _poll():
            log.info("starting polling mode")
            await dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query", "my_chat_member"],
            )

        polling_task = asyncio.create_task(_poll())
    elif config.MODE == "webhook":
        base = config._get("PUBLIC_URL", "").rstrip("/")
        if base and config.WEBHOOK_PATH_SECRET:
            url = f"{base}/webhook/{config.WEBHOOK_PATH_SECRET}"
            await bot.set_webhook(
                url,
                secret_token=config.WEBHOOK_SECRET or None,
                allowed_updates=["message", "callback_query", "my_chat_member"],
                drop_pending_updates=True,
            )
            log.info("webhook registered")

    yield

    if polling_task is not None:
        polling_task.cancel()
    await services.router.close()
    from . import db as dbmod

    await dbmod.close()
    await bot.session.close()


app = FastAPI(title="OpsTranslate Bot", lifespan=lifespan)


@app.post("/webhook/{path_secret}")
async def webhook(
    path_secret: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Gate 1: path secret + secret-token header must both match."""
    if (
        not config.WEBHOOK_PATH_SECRET
        or path_secret != config.WEBHOOK_PATH_SECRET
        or (config.WEBHOOK_SECRET and x_telegram_bot_api_secret_token != config.WEBHOOK_SECRET)
    ):
        raise HTTPException(status_code=403, detail="forbidden")
    data = await request.json()
    update = Update.model_validate(data)
    await app.state.dp.feed_update(app.state.bot, update)
    return {"ok": True}


@app.get("/healthz")
async def healthz():
    from . import db as dbmod

    services: Services = app.state.services
    now_yangon = datetime.now(YANGON)
    in_working_hours = WORK_START_HOUR <= now_yangon.hour < WORK_END_HOUR
    # A silent process serving 200 OK while failing every translation is
    # still broken - but no traffic at 3 AM is normal, not an outage.
    # A fresh deploy also gets a 10-minute startup grace before the traffic
    # check can fail (the spec's quiet-hours window is retained).
    within_grace = (time.monotonic() - services.started_at) < 600
    traffic_ok = (
        within_grace or services.stats.last_success_within(600) or not in_working_hours
    )

    checks = {
        "db": await dbmod.ping(),
        "cache": await services.cache.ping(),
        "policy": services.policy.loaded,
        "provider": services.router.any_closed(),
        "traffic": traffic_ok,
    }
    ok = all(checks.values())
    return JSONResponse(checks, status_code=200 if ok else 503)

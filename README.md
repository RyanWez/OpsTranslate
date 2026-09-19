# OpsTranslate Bot

Telegram translation bot with a **term-policy engine** (no free translation of
sensitive gaming/ops terminology) and **entity protection** (URLs, @mentions,
numbers and /commands pass through untouched).

Scope: EN / MY / ZH <-> EN. This v1 ships **polling** (local testing) and
**webhook** (production) modes. No admin dashboard.

## Quick start (local polling test)

Needs only: Python 3.12, a Telegram bot token, and an OpenAI-compatible
provider (base URL + API key + model). Neon and Redis are **optional** - the
bot degrades gracefully without them (in-memory idempotency/cache, silent
alerts, metadata logging skipped).

```bash
cd opstranslate-bot
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt

export BOT_TOKEN=... PROVIDER_BASE_URL=... PROVIDER_API_KEY=... PROVIDER_MODEL=...
export MODE=polling TEST_ALLOW_ALL=true
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Open the bot in Telegram and send a message. Useful test inputs:

| Input | Expectation |
|---|---|
| `မင်္ဂလာပါ` | Translated (Myanmar detected) |
| `ဂိမ်းအိုင်ဒီ မှားနေတယ်` | `ဂိမ်း` masked to policy term, "User ID" in output |
| `https://x.co/a @ops 0912345678` | URL / mention / number copied verbatim |
| `/whoami` | Replies with your user id (works even unregistered) |
| `/status` | Bot identity + traffic light |
| 3 messages in <30s | 3rd gets a rate-limit countdown reply |
| sticker / photo (no caption) | "This message type isn't supported." |

### Credential fields for a live test

| Field | Where from |
|---|---|
| `BOT_TOKEN` | @BotFather |
| `PROVIDER_BASE_URL` | Your OpenAI-compatible provider (e.g. `https://api.example.com/v1`) |
| `PROVIDER_API_KEY` | Same provider |
| `PROVIDER_MODEL` | Model name, e.g. `translate-pro` |

Hand them over **transiently** (paste, never commit). Rotate the test bot
token afterwards (`@BotFather` -> `/revoke`).

## Database (Neon) + seed

```bash
export DATABASE_URL="postgresql://...neon.tech/db?sslmode=require"
.venv/bin/alembic upgrade head
.venv/bin/python -m app.store.seed
```

With `DATABASE_URL` set, `alembic upgrade head && python -m app.store.seed` also run
at container start (see `Dockerfile`). Seeding is idempotent: allowlist ids
from `ALLOWED_USER_IDS` get the `staff` role; ids in `ADMIN_USER_IDS` get
`admin`; if `ADMIN_USER_IDS` is unset, the first `ALLOWED_USER_IDS` id becomes
admin.

The schema logs **metadata only** (`usage_log` has no message-text column).

## Deploy to Koyeb (webhook mode)

1. Push this repo to GitHub. Set the GitHub secret `HEALTHZ_URL` to
   `https://<your-app>.koyeb.app/healthz` (enables the keep-warm workflow).
2. Koyeb: create a Web Service from the repo. Build: `pip install -r
   requirements.txt`. Run command: the `Dockerfile`'s default CMD.
3. Env vars: `MODE=webhook`, `BOT_TOKEN`, `PROVIDER_*`, `PUBLIC_URL`,
   `WEBHOOK_SECRET`, `WEBHOOK_PATH_SECRET`, `DATABASE_URL`, `REDIS_URL`,
   `ALLOWED_USER_IDS`, `ADMIN_USER_IDS`.
4. The bot registers its webhook on startup; Telegram must present the
   `X-Telegram-Bot-Api-Secret-Token` header or the update is rejected.
5. External monitor: point an UptimeRobot/BetterStack monitor at
   `/healthz` and alert your Telegram admin chat (see `ALERT_BOT_TOKEN`,
   `ADMIN_CHAT_ID`). **This is the dead-man's switch** - if it doesn't fire,
   nobody knows the bot is down.

## Security notes

- Config is **env-only**; never hardcode secrets or commit `.env`.
- The provider's API key is sent only to `PROVIDER_BASE_URL`, via HTTPS.
- Usage logs contain metadata only - no message text, no translation text.
- P1/P2 alerts never include message content (concept/provider/version only).

## Spec deviations (from `opstranslte-bot-v3.1.html`)

- Placeholders use the spec's Unicode brackets: `⟦T:concept⟧` for
  term-policy, `⟦E:url:N⟧` / `⟦E:id:N⟧` / `⟦E:mention:N⟧` / `⟦E:cmd:N⟧` for
  entities (separate namespaces, never mixed).
- `游戏` added as a `platform` zh variant: the spec's own §4.4 few-shot masks
  bare `游戏` as `⟦T:platform⟧`; longest-match-first keeps longer concepts
  (`游戏积分`, `游戏账号`) winning where they overlap.
- `ဂိမ်းအိုင်ဒီ` (aing spelling of "ID") added as a `user_id` my variant: the
  spec's §4.4 few-shot input uses this spelling while §4.2 lists only
  `ဂိမ်းအိုက်ဒီ` (aik). Without it, the few-shot input fragmented into
  `⟦T:platform⟧⟦T:user_id⟧`; both transliterations now seed the same concept.
- Layer 3 deny-scan strips separator evasion (spaces, hyphens, dots,
  zero-width chars) before matching, so `g-a-m-e` still reads as `game`.
  Fail-closed by design; the P2 alert path absorbs false positives.
- `policy_hits` in usage metadata reports concepts that actually produced
  placeholders, not raw substring hits (so `ဂိမ်း` inside `ဂိမ်းအိုင်ဒီ` does
  not double-count as a platform hit).
- Backup providers are configured via optional `PROVIDERS_JSON`
  (`[{"name":...,"base_url":...,"api_key":...,"model":...,"priority":2}]`);
  without it the single `PROVIDER_*` set is used as before.
- `/healthz` grants a 10-minute startup grace before the working-hours
  traffic check can fail; the spec's quiet-hours window is unchanged.
- After a **second** policy deny hit the bot sends **nothing**: the
  "Translating…" placeholder is deleted, no fallback text is shown. The P2
  alert (concept/provider/version only, never message text) is the
  staff-visible signal.
- After a **second** policy deny hit the bot sends **nothing** (no final
  fallback message) - matches the spec's "send nothing, log, alert".
- Backup providers are not yet config-driven (router supports them, wiring is
  TODO).
- `/healthz` has a 10-minute startup grace before the working-hours traffic
  check can fail; the spec's 4h quiet-hours window is retained.

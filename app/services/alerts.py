"""Telegram-only alerting with two paths (spec section 07).

Path A - internal alerts from the running bot, via a SEPARATE alert bot
token so a token problem in the user-facing bot cannot silence alerts.
Path B - an external uptime monitor polling /healthz (not implemented here;
see README and the keep-warm workflow).

Rules:
- Every alert is fingerprinted as {type}:{component}. Repeats inside the
  15-minute cooldown increment a counter instead of sending.
- A resolution message is always sent when the condition clears.
- Capped at 20 alerts per hour; beyond that, one summary line.
- Every alert ends with an action line.
- NEVER include message text in an alert (privacy guarantee).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

log = logging.getLogger("opstranslate.alerts")

COOLDOWN_S = 15 * 60
HOURLY_CAP = 20

LEVEL_EMOJI = {"P1": "\U0001f534", "P2": "\u26a0\ufe0f", "P3": "\u2139\ufe0f"}


@dataclass
class _AlertRecord:
    first_seen: float
    last_sent: float
    count: int = 1
    active: bool = True


class AlertManager:
    def __init__(self, bot_token: str = "", admin_chat_id: str = ""):
        self.bot_token = bot_token
        self.admin_chat_id = admin_chat_id
        self._records: dict[str, _AlertRecord] = {}
        self._sent_times: deque[float] = deque()
        self._bot = None  # lazy aiogram Bot

    def _get_bot(self):
        if self._bot is None and self.bot_token:
            from aiogram import Bot

            from .. import config as app_config

            self._bot = Bot(token=self.bot_token, session=app_config.telegram_session())
        return self._bot

    async def _deliver(self, text: str) -> None:
        bot = self._get_bot()
        if bot is None or not self.admin_chat_id:
            # No alert channel configured: log to stdout instead.
            log.warning("alert_unconfigured_delivery:\n%s", text)
            return
        try:
            await bot.send_message(self.admin_chat_id, text)
        except Exception as exc:  # noqa: BLE001
            log.error("alert_delivery_failed: %s", exc)

    def _under_hourly_cap(self, now: float) -> bool:
        while self._sent_times and now - self._sent_times[0] > 3600:
            self._sent_times.popleft()
        return len(self._sent_times) < HOURLY_CAP

    async def send(
        self,
        level: str,
        alert_type: str,
        component: str,
        detail: str,
        action: str,
    ) -> None:
        """Send (or coalesce) an alert. Fingerprint is {type}:{component}."""
        now = time.time()
        fingerprint = f"{alert_type}:{component}"
        rec = self._records.get(fingerprint)

        if rec is not None and rec.active and now - rec.last_sent < COOLDOWN_S:
            rec.count += 1
            return  # coalesced inside the cooldown window

        if not self._under_hourly_cap(now):
            log.warning("alert_hourly_cap_reached, dropping: %s", fingerprint)
            return

        ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(
            rec.count + 1 if rec else 1, f"{rec.count + 1 if rec else 1}th"
        )
        text = (
            f"{LEVEL_EMOJI.get(level, '')} {level} \u00b7 {alert_type}\n"
            f"{detail}\n"
            f"Action: {action}\n"
            f"fp {fingerprint} \u00b7 {ordinal}"
        )
        await self._deliver(text)
        self._sent_times.append(now)
        if rec is None:
            self._records[fingerprint] = _AlertRecord(
                first_seen=now, last_sent=now
            )
        else:
            rec.last_sent = now
            rec.count += 1
            rec.active = True

    async def resolve(self, alert_type: str, component: str, detail: str) -> None:
        """Send a resolution message when a condition clears."""
        fingerprint = f"{alert_type}:{component}"
        rec = self._records.get(fingerprint)
        if rec is None or not rec.active:
            return
        rec.active = False
        duration_s = int(time.time() - rec.first_seen)
        mins, secs = divmod(duration_s, 60)
        text = (
            f"\u2705 RESOLVED \u00b7 {alert_type}\n"
            f"{detail}\n"
            f"Down {mins}m {secs}s \u00b7 occurrences: {rec.count}\n"
            f"fp {fingerprint}"
        )
        await self._deliver(text)

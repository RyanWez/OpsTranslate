"""Shared test doubles for the delivery path (Gates 3-10).

The pipeline touches Telegram through four calls - send_message,
edit_message_text, delete_message, send_chat_action - and the provider
through ProviderRouter.translate. Recording both makes the whole flow
testable with no network, and lets the assertions stay on what the USER
sees: which message was sent, as a reply to what, and what the placeholder
ended up saying.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from types import SimpleNamespace

from app.policy.policy import compile_policy
from app.services.alerts import AlertManager
from app.services.cache import Cache, cache_key
from app.services.pipeline import Services
from app.services.provider import AllProvidersDown, ProviderRouter
from app.services.stats import Stats


@dataclass
class Outbound:
    """One Telegram API call the bot made."""

    kind: str                      # send | edit | delete | chat_action
    chat_id: int
    text: str = ""
    message_id: int | None = None
    reply_to: int | None = None    # only for send: the reply anchor
    reply_markup: object | None = None


class FakeBot:
    """Records every Telegram call and hands out sequential message ids."""

    def __init__(self, me_id: int = 777, member_status: str = "member"):
        self.id = me_id            # ChatActionSender reads bot.id
        self.me_id = me_id
        self.member_status = member_status
        self.calls: list[Outbound] = []
        self._next_id = 1000
        self.edit_error: Exception | None = None

    # -- read helpers -------------------------------------------------------
    @property
    def sent(self) -> list[Outbound]:
        return [c for c in self.calls if c.kind == "send"]

    @property
    def edits(self) -> list[Outbound]:
        return [c for c in self.calls if c.kind == "edit"]

    @property
    def deleted(self) -> list[Outbound]:
        return [c for c in self.calls if c.kind == "delete"]

    @property
    def chat_actions(self) -> list[Outbound]:
        return [c for c in self.calls if c.kind == "chat_action"]

    def last_text(self) -> str:
        """What the user is looking at: newest edit, else newest send."""
        for call in reversed(self.calls):
            if call.kind in ("send", "edit"):
                return call.text
        return ""

    # -- Telegram API -------------------------------------------------------
    async def send_message(self, chat_id, text, reply_parameters=None,
                           reply_markup=None, **kw):
        self._next_id += 1
        self.calls.append(Outbound(
            "send", chat_id, text, self._next_id,
            getattr(reply_parameters, "message_id", None), reply_markup,
        ))
        return SimpleNamespace(message_id=self._next_id)

    async def edit_message_text(self, chat_id=None, message_id=None, text=None,
                                reply_markup=None, **kw):
        if self.edit_error is not None:
            raise self.edit_error
        self.calls.append(Outbound("edit", chat_id, text, message_id,
                                   reply_markup=reply_markup))
        return SimpleNamespace(message_id=message_id)

    async def delete_message(self, chat_id=None, message_id=None):
        self.calls.append(Outbound("delete", chat_id, "", message_id))
        return True

    async def send_chat_action(self, chat_id=None, action=None,
                               message_thread_id=None):
        self.calls.append(Outbound("chat_action", chat_id, action))
        return True

    async def get_me(self):
        return SimpleNamespace(id=self.me_id)

    async def get_chat_member(self, chat_id, user_id):
        """Real gate path: status_of() accepts the plain string."""
        return SimpleNamespace(status=self.member_status, is_member=True)


class StubRouter(ProviderRouter):
    """Provider stand-in: scripted outputs, no HTTP.

    `outputs` is consumed in order and the last entry repeats, so a repair
    loop sees the same answer twice unless two are given.
    """

    def __init__(self, outputs=None, fail: bool = False, hang: bool = False,
                 name: str = "stub", delay: float = 0.0):
        super().__init__(providers=[])
        self.name = name
        self.outputs = list(outputs) if outputs else ["ok"]
        self.fail = fail
        self.hang = hang
        self.delay = delay        # real providers take time; the typing
                                  # indicator only appears when they do
        self.calls = 0
        self.masked: list[str] = []
        self.prompts: list[str] = []

    async def translate(self, masked_text, system_prompt, force=None):
        self.calls += 1
        self.masked.append(masked_text)
        self.prompts.append(system_prompt)
        if self.hang:
            await asyncio.sleep(3600)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise AllProvidersDown("stub provider down")
        return self.outputs[min(self.calls - 1, len(self.outputs) - 1)], self.name


class RecordingAlerts(AlertManager):
    """AlertManager that records instead of delivering."""

    def __init__(self):
        super().__init__()
        self.sent: list[tuple[str, str, str]] = []      # (level, type, detail)
        self.resolved: list[tuple[str, str]] = []       # (type, detail)

    async def send(self, level, alert_type, component, detail, action):
        self.sent.append((level, alert_type, detail))

    async def resolve(self, alert_type, component, detail):
        self.resolved.append((alert_type, detail))


class StubUserStore:
    """Allowlist + settings stand-in (no Postgres, no in-memory drift)."""

    def __init__(self, allowed: bool = True, role: str = "staff",
                 target: str = "en", daily_cap: int = 200):
        self.allowed = allowed
        self.role = role
        self.target = target
        self.daily_cap = daily_cap
        self.targets_set: list[tuple[int, str]] = []

    async def is_allowed(self, user_id):
        return self.allowed, self.role

    async def get_target(self, user_id):
        return self.target

    async def set_target(self, user_id, lang):
        self.target = lang
        self.targets_set.append((user_id, lang))

    async def daily_soft_cap(self, user_id):
        return self.daily_cap


def make_services(bot=None, router=None, cache=None, alerts=None,
                  user_store=None, policy=None) -> Services:
    return Services(
        bot=bot if bot is not None else FakeBot(),
        policy=policy if policy is not None else compile_policy(1),
        router=router if router is not None else StubRouter(),
        cache=cache if cache is not None else Cache(""),
        alerts=alerts if alerts is not None else RecordingAlerts(),
        stats=Stats(),
        user_store=user_store if user_store is not None else StubUserStore(),
    )


def seed_cache(cache: Cache, text: str, src: str, dst: str, policy_version: int,
               source: str, age_s: float = 0.0) -> str:
    """Pre-seed a translation-cache entry, optionally aged past the 30s
    duplicate-resend window so the plain Gate 9 hit path is exercised."""
    key = cache_key(source, src, dst, policy_version)
    raw = f"{text}\x01{time.time() - age_s}"
    if cache._redis is not None:  # pragma: no cover - tests use the memory store
        raise AssertionError("seed_cache expects the in-memory store")
    cache._mem._data[key] = (raw, time.time() + 3600)
    return key


class FakeMessage:
    """Enough of aiogram.types.Message for the handlers under test."""

    def __init__(self, message_id=1, text=None, caption=None,
                 chat_type="private", from_id=11, chat_id=11, reply_to=None):
        self.message_id = message_id
        self.text = text
        self.caption = caption
        self.chat = SimpleNamespace(type=chat_type, id=chat_id)
        self.from_user = SimpleNamespace(id=from_id, username=None, full_name=None, first_name=None)
        self.reply_to_message = reply_to
        self.entities = None
        self.caption_entities = None
        self.answers: list[str] = []
        self.replies: list[str] = []

    async def answer(self, text, **kw):
        self.answers.append(text)
        return SimpleNamespace(message_id=9000 + len(self.answers))

    async def reply(self, text, **kw):
        self.replies.append(text)
        return SimpleNamespace(message_id=9100 + len(self.replies))

"""AI provider router: OpenAI-compatible chat completions with failover.

- Priority-ordered provider list (config-driven; starts with one provider).
- Circuit breaker: opens after 5 consecutive failures, half-opens after 60s.
- Concurrency capped by a semaphore (default 8).
- 8s provider timeout (configurable).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from .. import config

log = logging.getLogger("opstranslate.provider")

FAIL_THRESHOLD = 5
HALF_OPEN_AFTER_S = 60.0


def _sanitize_no_proxy() -> None:
    """httpx 0.28.x crashes building its proxy patterns when no_proxy holds
    already-bracketed IPv6 literals (e.g. "[::1]" becomes the pattern
    "all://*[::1]", whose port parses as ":1]" -> InvalidURL on the first
    request). Drop the bracketed forms; the unbracketed equivalents
    (also present) keep the same bypass coverage."""
    import os

    for var in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(var)
        if not val:
            continue
        kept = [p for p in val.split(",") if not p.strip().startswith("[")]
        if len(kept) != len(val.split(",")):
            os.environ[var] = ",".join(kept)
            log.info("sanitised bracketed IPv6 entries out of %s", var)


_sanitize_no_proxy()


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    priority: int = 1
    enabled: bool = True
    timeout_s: float = 8.0


@dataclass
class _Breaker:
    state: str = "closed"  # closed | open | half_open
    fail_count: int = 0
    opened_at: float = 0.0

    def can_try(self, now: float) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open" and now - self.opened_at >= HALF_OPEN_AFTER_S:
            self.state = "half_open"
            return True
        return self.state == "half_open"

    def record_success(self) -> None:
        self.state = "closed"
        self.fail_count = 0

    def record_failure(self, now: float) -> bool:
        """Returns True if the breaker just opened."""
        self.fail_count += 1
        if self.fail_count >= FAIL_THRESHOLD and self.state != "open":
            self.state = "open"
            self.opened_at = now
            return True
        return False


class ProviderError(Exception):
    pass


class AllProvidersDown(ProviderError):
    pass


class ProviderRouter:
    def __init__(self, providers: list[Provider], max_concurrency: int = 8):
        self.providers = sorted(
            [p for p in providers if p.enabled], key=lambda p: p.priority
        )
        self.breakers: dict[str, _Breaker] = {p.name: _Breaker() for p in self.providers}
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self._client: httpx.AsyncClient | None = None

    async def _client_get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def states(self) -> dict[str, str]:
        return {name: b.state for name, b in self.breakers.items()}

    def any_closed(self) -> bool:
        now = time.monotonic()
        return any(b.can_try(now) for b in self.breakers.values())

    async def translate(
        self,
        masked_text: str,
        system_prompt: str,
        force: str | None = None,
    ) -> tuple[str, str]:
        """Translate; returns (output_text, provider_name).

        Raises AllProvidersDown if every provider failed. *force* pins the
        call to one provider (used by the repair loop so retries do not
        bounce between providers).
        """
        now = time.monotonic()
        candidates = self.providers
        if force is not None:
            candidates = [p for p in self.providers if p.name == force]
            if not candidates:
                raise ProviderError(f"unknown provider: {force}")

        errors: list[str] = []
        for provider in candidates:
            breaker = self.breakers[provider.name]
            if not breaker.can_try(now):
                continue
            async with self.semaphore:
                try:
                    text = await self._call(provider, masked_text, system_prompt)
                except Exception as exc:  # noqa: BLE001 - any failure trips the breaker
                    opened = breaker.record_failure(time.monotonic())
                    errors.append(f"{provider.name}: {exc}")
                    log.warning("provider_failed", extra={"provider": provider.name})
                    if opened:
                        log.error("circuit_opened", extra={"provider": provider.name})
                    continue
                breaker.record_success()
                return text, provider.name

        raise AllProvidersDown("; ".join(errors) or "no providers configured")

    async def _call(self, provider: Provider, masked_text: str, system_prompt: str) -> str:
        client = await self._client_get()
        url = provider.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"<src>{masked_text}</src>"},
            ],
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": config.PROVIDER_MAX_OUTPUT_TOKENS,
        }
        headers = {"Authorization": f"Bearer {provider.api_key}"}
        resp = await client.post(url, json=payload, headers=headers, timeout=provider.timeout_s)
        resp.raise_for_status()
        data = resp.json()
        try:
            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                raise ProviderError(
                    "provider output reached max token limit "
                    f"({config.PROVIDER_MAX_OUTPUT_TOKENS})"
                )
            return choice["message"]["content"].strip()
        except ProviderError:
            raise
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError(f"bad response shape: {exc}") from exc

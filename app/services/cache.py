"""Cache + idempotency + duplicate helpers.

Redis when REDIS_URL is set; otherwise a small in-process TTL store so the
behaviour (idempotency, duplicate handling, translation cache) is preserved
in local testing. The in-process store is per-process and best-effort -
production should set REDIS_URL.

Cache key (spec Gate 9): sha1(normalized_text + src + dst + policy_version)
where normalization = casefold + collapse whitespace + fullwidth->halfwidth
punctuation. TTL 7 days.

Fail-soft (P1.4): every Redis-touching method degrades to the in-process
store on Redis errors. The correctness trade is documented: in-memory
idempotency/duplicate locks are per-process and best-effort when Redis is
down. A P1 CACHE_UNREACHABLE is raised once on the first consecutive
failure and resolved on the first successful Redis call.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .alerts import AlertManager

log = logging.getLogger("opstranslate.cache")

CACHE_TTL_S = 7 * 24 * 3600
IDEMPOTENCY_TTL_S = 300
DUPLICATE_WINDOW_S = 30


def normalize_for_key(text: str) -> str:
    """Normalize before hashing: casefold, collapse whitespace,
    fullwidth punctuation -> halfwidth."""
    text = text.casefold()
    # Fullwidth ASCII range -> halfwidth.
    text = "".join(
        chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in text
    )
    # Fullwidth space -> normal space.
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def cache_key(text: str, src: str, dst: str, policy_version: int) -> str:
    norm = normalize_for_key(text)
    raw = f"{norm}\x00{src}\x00{dst}\x00{policy_version}"
    return "tr:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def duplicate_key(user_id: int, text: str, dst: str) -> str:
    norm = normalize_for_key(text)
    raw = f"{user_id}\x00{norm}\x00{dst}"
    return "dup:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


class _MemoryStore:
    """Minimal TTL key-value store used when Redis is unavailable."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}

    def _purge(self, key: str) -> None:
        value = self._data.get(key)
        if value is not None and value[1] <= time.time():
            del self._data[key]

    def get(self, key: str) -> str | None:
        self._purge(key)
        value = self._data.get(key)
        return value[0] if value is not None else None

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = (value, time.time() + (ex if ex else 3600))

    def setnx(self, key: str, value: str, ex: int) -> bool:
        self._purge(key)
        if key in self._data:
            return False
        self._data[key] = (value, time.time() + ex)
        return True


@dataclass
class CacheEntry:
    text: str       # translated result
    stored_at: float


class Cache:
    def __init__(self, redis_url: str = "", alerts: "AlertManager | None" = None):
        self._redis = None
        if redis_url:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._mem = _MemoryStore()
        self._alerts: "AlertManager | None" = alerts
        self._fail_count: int = 0
        self._alert_active: bool = False

    def bind_alerts(self, alerts: "AlertManager | None") -> None:
        """Attach an AlertManager after construction (used by build_services)."""
        self._alerts = alerts

    async def _on_redis_error(self, exc: Exception) -> None:
        self._fail_count += 1
        log.warning("cache_redis_error: %s (fail_count=%s)", exc, self._fail_count)
        if self._alerts and not self._alert_active:
            self._alert_active = True
            try:
                await self._alerts.send(
                    "P1",
                    "CACHE_UNREACHABLE",
                    "redis",
                    f"Redis unreachable ({type(exc).__name__}: {exc}); degraded to in-memory cache.",
                    "Check Upstash/Redis status, REDIS_URL, and network; bot is serving best-effort from local memory.",
                )
            except Exception:  # noqa: BLE001
                log.warning("cache_alert_send_failed", exc_info=True)

    async def _on_redis_success(self) -> None:
        if self._fail_count > 0:
            self._fail_count = 0
        if self._alert_active and self._alerts:
            self._alert_active = False
            try:
                await self._alerts.resolve(
                    "CACHE_UNREACHABLE",
                    "redis",
                    "Redis recovered; cache restored to Redis.",
                )
            except Exception:  # noqa: BLE001
                log.warning("cache_alert_resolve_failed", exc_info=True)

    async def ping(self) -> bool:
        if self._redis is None:
            return True
        try:
            await self._redis.ping()
            await self._on_redis_success()
            return True
        except Exception as exc:  # noqa: BLE001
            await self._on_redis_error(exc)
            return False

    # -- idempotency (Gate 2): update_id not seen in the last 5 minutes ------
    async def check_idempotent(self, update_id: int) -> bool:
        """Return True if this update was already seen (caller should skip)."""
        key = f"idem:{update_id}"
        if self._redis is not None:
            try:
                result = not bool(await self._redis.set(key, "1", nx=True, ex=IDEMPOTENCY_TTL_S))
                await self._on_redis_success()
                return result
            except Exception as exc:  # noqa: BLE001 - degrade to memory on Redis errors
                await self._on_redis_error(exc)
        return not self._mem.setnx(key, "1", IDEMPOTENCY_TTL_S)

    # -- duplicate tracking (Gate 7) ------------------------------------------
    async def mark_inflight(self, dup_key: str) -> bool:
        """Return False if the same request is already in flight."""
        key = dup_key + ":lock"
        if self._redis is not None:
            try:
                result = bool(await self._redis.set(key, "1", nx=True, ex=DUPLICATE_WINDOW_S))
                await self._on_redis_success()
                return result
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
        return self._mem.setnx(key, "1", DUPLICATE_WINDOW_S)

    async def clear_inflight(self, dup_key: str) -> None:
        key = dup_key + ":lock"
        if self._redis is not None:
            try:
                await self._redis.delete(key)
                await self._on_redis_success()
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
                # Still clear the local fallback so the in-memory lock does not leak.
                self._mem._data.pop(key, None)
                return
        self._mem._data.pop(key, None)

    # -- translation cache (Gate 9) -------------------------------------------
    async def get(self, key: str) -> CacheEntry | None:
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                await self._on_redis_success()
                if raw is None:
                    return None
                text, _, ts = raw.partition("\x01")
                try:
                    return CacheEntry(text=text, stored_at=float(ts))
                except ValueError:
                    return None
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
                # Fall through to memory fallback
        raw = self._mem.get(key)
        if raw is None:
            return None
        text, _, ts = raw.partition("\x01")
        try:
            return CacheEntry(text=text, stored_at=float(ts))
        except ValueError:
            return None

    async def put(self, key: str, text: str) -> None:
        raw = f"{text}\x01{time.time()}"
        if self._redis is not None:
            try:
                await self._redis.set(key, raw, ex=CACHE_TTL_S)
                await self._on_redis_success()
                # Also mirror to _mem so a subsequent read after a Redis blip
                # still finds the entry via fallback.
                self._mem.set(key, raw, ex=CACHE_TTL_S)
                return
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
        self._mem.set(key, raw, ex=CACHE_TTL_S)

    # -- generic string kv (group-membership cache, misc flags) ------------
    async def get_str(self, key: str) -> str | None:
        if self._redis is not None:
            try:
                val = await self._redis.get(key)
                await self._on_redis_success()
                return val
            except Exception as exc:  # noqa: BLE001 - degrade to miss on Redis errors
                await self._on_redis_error(exc)
                # Treat as miss but also check local memory (e.g. a prior
                # degraded write). This keeps a kick/join invalidation from
                # being invisible while Redis is down.
                mem_val = self._mem.get(key)
                if mem_val is not None:
                    return mem_val
                return None
        return self._mem.get(key)

    async def set_str(self, key: str, value: str, ex: int) -> None:
        if self._redis is not None:
            try:
                await self._redis.set(key, value, ex=ex)
                await self._on_redis_success()
                self._mem.set(key, value, ex=ex)
                return
            except Exception as exc:  # noqa: BLE001 - degrade to memory on Redis errors
                await self._on_redis_error(exc)
        self._mem.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(key)
                await self._on_redis_success()
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
        self._mem._data.pop(key, None)

    # -- generic counters (spend cap, daily soft cap) --------------------------
    async def incr(self, key: str, ex: int) -> int:
        if self._redis is not None:
            try:
                n = await self._redis.incr(key)
                if n == 1:
                    await self._redis.expire(key, ex)
                await self._on_redis_success()
                # Mirror to _mem for fallback reads
                self._mem.set(key, str(n), ex=ex)
                return n
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
        raw = self._mem.get(key)
        n = (int(raw) + 1) if raw else 1
        self._mem.set(key, str(n), ex=ex)
        return n

    async def get_float(self, key: str) -> float:
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                await self._on_redis_success()
                return float(raw) if raw else 0.0
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
                mem_raw = self._mem.get(key)
                return float(mem_raw) if mem_raw else 0.0
        raw = self._mem.get(key)
        return float(raw) if raw else 0.0

    async def incr_float(self, key: str, amount: float, ex: int) -> float:
        if self._redis is not None:
            try:
                total = await self._redis.incrbyfloat(key, amount)
                # Keep the TTL bounded: only set expiry on first write.
                ttl = await self._redis.ttl(key)
                if ttl == -1:
                    await self._redis.expire(key, ex)
                await self._on_redis_success()
                self._mem.set(key, str(total), ex=ex)
                return float(total)
            except Exception as exc:  # noqa: BLE001
                await self._on_redis_error(exc)
                mem_total = (float(self._mem.get(key)) if self._mem.get(key) else 0.0) + amount
                self._mem.set(key, str(mem_total), ex=ex)
                return mem_total
        total = (await self.get_float(key)) + amount
        self._mem.set(key, str(total), ex=ex)
        return total

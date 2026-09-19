"""Cache + idempotency + duplicate helpers.

Redis when REDIS_URL is set; otherwise a small in-process TTL store so the
behaviour (idempotency, duplicate handling, translation cache) is preserved
in local testing. The in-process store is per-process and best-effort -
production should set REDIS_URL.

Cache key (spec Gate 9): sha1(normalized_text + src + dst + policy_version)
where normalization = casefold + collapse whitespace + fullwidth->halfwidth
punctuation. TTL 7 days.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass

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
    def __init__(self, redis_url: str = ""):
        self._redis = None
        if redis_url:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._mem = _MemoryStore()

    async def ping(self) -> bool:
        if self._redis is None:
            return True
        try:
            await self._redis.ping()
            return True
        except Exception:  # noqa: BLE001
            return False

    # -- idempotency (Gate 2): update_id not seen in the last 5 minutes ------
    async def check_idempotent(self, update_id: int) -> bool:
        """Return True if this update was already seen (caller should skip)."""
        key = f"idem:{update_id}"
        if self._redis is not None:
            return not bool(await self._redis.set(key, "1", nx=True, ex=IDEMPOTENCY_TTL_S))
        return not self._mem.setnx(key, "1", IDEMPOTENCY_TTL_S)

    # -- duplicate tracking (Gate 7) ------------------------------------------
    async def mark_inflight(self, dup_key: str) -> bool:
        """Return False if the same request is already in flight."""
        key = dup_key + ":lock"
        if self._redis is not None:
            return bool(await self._redis.set(key, "1", nx=True, ex=DUPLICATE_WINDOW_S))
        return self._mem.setnx(key, "1", DUPLICATE_WINDOW_S)

    async def clear_inflight(self, dup_key: str) -> None:
        key = dup_key + ":lock"
        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except Exception:  # noqa: BLE001
                pass
        else:
            self._mem._data.pop(key, None)

    # -- translation cache (Gate 9) -------------------------------------------
    async def get(self, key: str) -> CacheEntry | None:
        if self._redis is not None:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            text, _, ts = raw.partition("\x01")
            try:
                return CacheEntry(text=text, stored_at=float(ts))
            except ValueError:
                return None
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
            await self._redis.set(key, raw, ex=CACHE_TTL_S)
        else:
            self._mem.set(key, raw, ex=CACHE_TTL_S)

    # -- generic string kv (group-membership cache, misc flags) ------------
    async def get_str(self, key: str) -> str | None:
        if self._redis is not None:
            try:
                return await self._redis.get(key)
            except Exception:  # noqa: BLE001 - degrade to miss on Redis errors
                return None
        return self._mem.get(key)

    async def set_str(self, key: str, value: str, ex: int) -> None:
        if self._redis is not None:
            try:
                await self._redis.set(key, value, ex=ex)
                return
            except Exception:  # noqa: BLE001 - degrade to memory on Redis errors
                pass
        self._mem.set(key, value, ex=ex)

    # -- generic counters (spend cap, daily soft cap) --------------------------
    async def incr(self, key: str, ex: int) -> int:
        if self._redis is not None:
            n = await self._redis.incr(key)
            if n == 1:
                await self._redis.expire(key, ex)
            return n
        raw = self._mem.get(key)
        n = (int(raw) + 1) if raw else 1
        self._mem.set(key, str(n), ex=ex)
        return n

    async def get_float(self, key: str) -> float:
        if self._redis is not None:
            raw = await self._redis.get(key)
            return float(raw) if raw else 0.0
        raw = self._mem.get(key)
        return float(raw) if raw else 0.0

    async def incr_float(self, key: str, amount: float, ex: int) -> float:
        if self._redis is not None:
            total = await self._redis.incrbyfloat(key, amount)
            # Keep the TTL bounded: only set expiry on first write.
            ttl = await self._redis.ttl(key)
            if ttl == -1:
                await self._redis.expire(key, ex)
            return float(total)
        total = (await self.get_float(key)) + amount
        self._mem.set(key, str(total), ex=ex)
        return total

"""Fixed-window rate limiting with in-process and Valkey backends."""

from __future__ import annotations

import asyncio
import time
from typing import Protocol


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        """Count one request. Returns (allowed, retry_after_seconds)."""
        ...

    async def reset(self, key: str) -> None: ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        async with self._lock:
            count, start = self._hits.get(key, (0, now))
            if now - start >= window:
                count, start = 0, now
            count += 1
            self._hits[key] = (count, start)
            if len(self._hits) > 100_000:  # bound memory
                self._hits = {k: v for k, v in self._hits.items() if now - v[1] < window}
            if count > limit:
                return False, max(1, int(window - (now - start)) + 1)
            return True, 0

    async def reset(self, key: str) -> None:
        self._hits.pop(key, None)


class ValkeyRateLimiter:
    """Fixed window using INCR and EXPIRE, shared across API instances."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._r = redis.from_url(url, decode_responses=True)

    async def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        k = f"rl:{key}"
        pipe = self._r.pipeline()
        pipe.incr(k)
        pipe.ttl(k)
        count, ttl = await pipe.execute()
        if ttl < 0:
            await self._r.expire(k, window)
            ttl = window
        if count > limit:
            return False, max(1, int(ttl))
        return True, 0

    async def reset(self, key: str) -> None:
        await self._r.delete(f"rl:{key}")


def make_limiter(valkey_url: str) -> RateLimiter:
    return ValkeyRateLimiter(valkey_url) if valkey_url else MemoryRateLimiter()

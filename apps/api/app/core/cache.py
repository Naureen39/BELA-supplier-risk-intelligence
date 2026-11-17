"""Response cache for analytics: in-process, or Valkey when configured.

Entries expire after a TTL and all entries are dropped together when the underlying views are
refreshed (a version counter is part of every key). Values are JSON documents.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int) -> None: ...
    def invalidate(self) -> None:
        """Drop every entry."""


class MemoryCache:
    def __init__(self, max_entries: int = 512) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        self._max = max_entries

    def get(self, key: str) -> Any | None:
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            if hit[0] < time.monotonic():
                del self._data[key]
                return None
            return json.loads(hit[1])

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            if len(self._data) >= self._max:
                now = time.monotonic()
                for k in [k for k, (exp, _) in self._data.items() if exp < now] or [next(iter(self._data))]:
                    del self._data[k]
            self._data[key] = (time.monotonic() + ttl, json.dumps(value))

    def invalidate(self) -> None:
        with self._lock:
            self._data.clear()


class ValkeyCache:
    """Synchronous client: the routes that use it are plain `def` endpoints run in a thread pool."""

    VERSION_KEY = "bela:cache:version"

    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)

    def _version(self) -> str:
        return str(self._r.get(self.VERSION_KEY) or "0")

    def get(self, key: str) -> Any | None:
        try:
            raw = self._r.get(f"bela:cache:{self._version()}:{key}")
        except Exception:  # a cache outage must never break the endpoint
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            self._r.set(f"bela:cache:{self._version()}:{key}", json.dumps(value), ex=ttl)
        except Exception:
            return

    def invalidate(self) -> None:
        try:
            self._r.incr(self.VERSION_KEY)
        except Exception:
            return


def make_cache(valkey_url: str) -> Cache:
    return ValkeyCache(valkey_url) if valkey_url else MemoryCache()


def cached(cache: Cache, key: str, ttl: int, compute: Callable[[], Any]) -> tuple[Any, bool]:
    """Return (value, hit). The value must be JSON-serializable."""
    value = cache.get(key)
    if value is not None:
        return value, True
    value = compute()
    cache.set(key, value, ttl)
    return value, False

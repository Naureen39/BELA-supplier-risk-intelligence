"""Pub/sub for live alerts: Valkey in deployment, in-process for tests and single instances."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Protocol

_CLOSE = object()


class Broker(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None: ...

    def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]: ...

    async def close(self) -> None: ...


class MemoryBroker:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        for q in list(self._subs[channel]):
            q.put_nowait(message)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue[Any] = asyncio.Queue()
        self._subs[channel].append(q)
        try:
            while True:
                item = await q.get()
                if item is _CLOSE:
                    return
                yield item
        finally:
            self._subs[channel].remove(q)

    async def close(self) -> None:
        for queues in self._subs.values():
            for q in queues:
                q.put_nowait(_CLOSE)


class ValkeyBroker:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._r = redis.from_url(url, decode_responses=True)

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        await self._r.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        pubsub = self._r.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    await asyncio.sleep(0)
                    continue
                yield json.loads(msg["data"])
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    async def close(self) -> None:
        await self._r.aclose()


def make_broker(valkey_url: str) -> Broker:
    return ValkeyBroker(valkey_url) if valkey_url else MemoryBroker()


def alert_channel(tenant_id: str) -> str:
    return f"alerts:{tenant_id}"

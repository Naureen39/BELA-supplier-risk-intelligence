"""Cluster the same incident across news articles and regulator records into one event."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from app.events.schema import REGULATOR, NormalizedEvent

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"the", "a", "an", "of", "at", "in", "on", "and", "to", "for", "by", "after",
                   "over", "with", "is", "has", "its", "from", "said", "says"})

Similarity = Callable[[str, str], float]


def title_similarity(a: str, b: str) -> float:
    """Jaccard overlap of content words. Replaced by embedding cosine when an embedder is given."""
    ta = {t for t in _TOKEN.findall(a.lower()) if t not in _STOP}
    tb = {t for t in _TOKEN.findall(b.lower()) if t not in _STOP}
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


@dataclass(frozen=True)
class DedupConfig:
    window_days: int = 7
    min_similarity: float = 0.35
    require_same_type: bool = True


DEFAULT_DEDUP = DedupConfig()


@dataclass
class EventCluster:
    id: int
    members: list[int]  # indexes into the input list
    sources: set[str] = field(default_factory=set)


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def cluster_events(
    events: Sequence[NormalizedEvent],
    entity_keys: Sequence[frozenset[int]],
    cfg: DedupConfig = DEFAULT_DEDUP,
    similarity: Similarity = title_similarity,
) -> list[EventCluster]:
    """Group events that share a resolved company, type, location compatibility, and time window.

    `entity_keys[i]` holds the resolved company ids of event i (empty for unresolved events, which
    never merge, so a wrong link cannot pull unrelated events together).
    """
    uf = _UnionFind(len(events))
    by_company: dict[int, list[int]] = defaultdict(list)
    for i, keys in enumerate(entity_keys):
        for cid in keys:
            by_company[cid].append(i)
    window = timedelta(days=cfg.window_days)
    for indexes in by_company.values():
        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1 :]:
                a, b = events[i], events[j]
                if uf.find(i) == uf.find(j):
                    continue
                if cfg.require_same_type and a.event_type != b.event_type:
                    continue
                if a.source == b.source and a.source_class == REGULATOR:
                    continue  # two records from one regulator are distinct actions
                if abs(a.effective_time - b.effective_time) > window:
                    continue
                if a.state and b.state and a.state != b.state:
                    continue
                # News about a regulator record merges on company, type, place, and time alone.
                # Two items of the same class must also have similar titles.
                if a.source_class == b.source_class and similarity(a.title, b.title) < cfg.min_similarity:
                    continue
                uf.union(i, j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(events)):
        groups[uf.find(i)].append(i)
    clusters = []
    for n, members in enumerate(sorted(groups.values(), key=lambda m: m[0]), start=1):
        clusters.append(EventCluster(n, members, {events[i].source for i in members}))
    return clusters


def representative(events: Sequence[NormalizedEvent], cluster: EventCluster) -> int:
    """Index of the event that represents a cluster: regulator first, then highest severity."""
    return max(
        cluster.members,
        key=lambda i: (events[i].source_class == REGULATOR, events[i].severity, -i),
    )

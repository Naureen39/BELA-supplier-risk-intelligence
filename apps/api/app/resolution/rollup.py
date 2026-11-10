"""Corporate family roll-up: which suppliers does an event on a company reach, and by what path."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

# Relation labels from the point of view of the event company.
DIRECT = "direct"
SUBSIDIARY_TO_PARENT = "subsidiary_event_to_parent"
PARENT_TO_SUBSIDIARY = "parent_event_to_subsidiary"
SIBLING = "sibling"


@dataclass(frozen=True)
class RollupPath:
    supplier_id: int
    event_company_id: int
    relation: str
    depth: int
    path: tuple[int, ...]  # company ids from the event company to the supplier


class CorporateGraph:
    """Parent to child ownership edges. Cycle-safe; traversal depth is limited."""

    def __init__(self, edges: Iterable[tuple[int, int]]) -> None:
        self.parents: dict[int, set[int]] = {}
        self.children: dict[int, set[int]] = {}
        for parent, child in edges:
            if parent == child:
                continue
            self.parents.setdefault(child, set()).add(parent)
            self.children.setdefault(parent, set()).add(child)

    def _walk(self, start: int, nxt: dict[int, set[int]], max_depth: int) -> dict[int, list[int]]:
        paths: dict[int, list[int]] = {start: [start]}
        queue: deque[int] = deque([start])
        while queue:
            node = queue.popleft()
            if len(paths[node]) - 1 >= max_depth:
                continue
            for other in sorted(nxt.get(node, ())):
                if other not in paths:
                    paths[other] = [*paths[node], other]
                    queue.append(other)
        return paths

    def ancestors(self, company_id: int, max_depth: int = 2) -> dict[int, list[int]]:
        paths = self._walk(company_id, self.parents, max_depth)
        paths.pop(company_id)
        return paths

    def descendants(self, company_id: int, max_depth: int = 2) -> dict[int, list[int]]:
        paths = self._walk(company_id, self.children, max_depth)
        paths.pop(company_id)
        return paths

    def reach(
        self, event_company_id: int, supplier_ids: Iterable[int], max_depth: int = 2
    ) -> list[RollupPath]:
        """Suppliers affected by an event at `event_company_id`, each with its explaining path.

        The shortest path wins when several relations connect the same pair. Sibling reach uses a
        shared direct parent only.
        """
        suppliers = set(supplier_ids)
        found: dict[int, RollupPath] = {}

        def add(supplier: int, path: RollupPath) -> None:
            current = found.get(supplier)
            if current is None or path.depth < current.depth:
                found[supplier] = path

        if event_company_id in suppliers:
            found[event_company_id] = RollupPath(
                event_company_id, event_company_id, DIRECT, 0, (event_company_id,)
            )
        for anc, path in self.ancestors(event_company_id, max_depth).items():
            if anc in suppliers:
                add(
                    anc,
                    RollupPath(anc, event_company_id, SUBSIDIARY_TO_PARENT, len(path) - 1, tuple(path)),
                )
        for desc, path in self.descendants(event_company_id, max_depth).items():
            if desc in suppliers:
                add(
                    desc,
                    RollupPath(desc, event_company_id, PARENT_TO_SUBSIDIARY, len(path) - 1, tuple(path)),
                )
        for parent in sorted(self.parents.get(event_company_id, ())):
            for sibling in sorted(self.children.get(parent, ())):
                if sibling != event_company_id and sibling in suppliers:
                    add(
                        sibling,
                        RollupPath(sibling, event_company_id, SIBLING, 2,
                                   (event_company_id, parent, sibling)),
                    )
        return sorted(found.values(), key=lambda p: (p.depth, p.supplier_id))

    def ultimate_parent(self, company_id: int, max_steps: int = 20) -> int:
        """Follow the lowest-id parent upward until a root (cycle-safe)."""
        seen = {company_id}
        current = company_id
        for _ in range(max_steps):
            parents = sorted(self.parents.get(current, ()))
            if not parents or parents[0] in seen:
                break
            current = parents[0]
            seen.add(current)
        return current

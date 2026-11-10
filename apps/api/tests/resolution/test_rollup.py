from __future__ import annotations

from app.resolution.rollup import (
    DIRECT,
    PARENT_TO_SUBSIDIARY,
    SIBLING,
    SUBSIDIARY_TO_PARENT,
    CorporateGraph,
)

G = CorporateGraph([(1, 2), (1, 3), (2, 4)])
CYCLE = CorporateGraph([(1, 2), (2, 4), (4, 1)])


def paths(event: int, suppliers: list[int]) -> dict[int, tuple[str, tuple[int, ...]]]:
    return {p.supplier_id: (p.relation, p.path) for p in G.reach(event, suppliers)}


def test_subsidiary_event_reaches_parent_with_path() -> None:
    assert paths(4, [1])[1] == (SUBSIDIARY_TO_PARENT, (4, 2, 1))


def test_parent_event_reaches_subsidiary() -> None:
    assert paths(1, [2])[2] == (PARENT_TO_SUBSIDIARY, (1, 2))


def test_sibling_and_direct() -> None:
    assert paths(2, [3])[3][0] == SIBLING
    assert paths(2, [2])[2] == (DIRECT, (2,))


def test_depth_limit_and_cycle_safety() -> None:
    chain = CorporateGraph([(1, 2), (2, 3), (3, 4)])
    assert chain.reach(4, [1], max_depth=2) == []
    assert [p.supplier_id for p in chain.reach(4, [2], max_depth=2)] == [2]
    assert G.ultimate_parent(4) == 1
    assert CYCLE.ultimate_parent(4) in {1, 2, 4}
    assert CYCLE.reach(1, [2, 4])

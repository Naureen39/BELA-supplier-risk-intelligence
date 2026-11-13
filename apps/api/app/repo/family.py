"""Corporate family lookups used by supplier event views, the family endpoint, and the graph."""

from __future__ import annotations

from typing import Any

from app.resolution.rollup import (
    DIRECT,
    PARENT_TO_SUBSIDIARY,
    SIBLING,
    SUBSIDIARY_TO_PARENT,
)


def _edges(conn: Any, ids: list[int], by: str) -> list[tuple[int, int]]:
    col, other = ("child_id", "parent_id") if by == "child" else ("parent_id", "child_id")
    rows = conn.execute(
        f"SELECT parent_id, child_id FROM company_relationships WHERE {col} = ANY(%s) "
        f"AND rel_type IN ('direct_parent','subsidiary','owned_by')", (ids,)).fetchall()
    return [(r["parent_id"], r["child_id"]) for r in rows]


def related_companies(conn: Any, company_id: int, depth: int = 2) -> dict[int, tuple[str, tuple[int, ...]]]:
    """Companies whose events reach `company_id`: relation label and path (event company first)."""
    out: dict[int, tuple[str, tuple[int, ...]]] = {company_id: (DIRECT, (company_id,))}
    frontier: dict[int, tuple[int, ...]] = {company_id: (company_id,)}
    for _ in range(depth):  # ancestors: their events reach the subsidiary (parent to subsidiary)
        nxt: dict[int, tuple[int, ...]] = {}
        for parent, child in _edges(conn, list(frontier), "child"):
            path = (parent, *frontier[child])
            if parent not in out:
                out[parent] = (PARENT_TO_SUBSIDIARY, path)
                nxt[parent] = path
        frontier = nxt
    frontier = {company_id: (company_id,)}
    for _ in range(depth):  # descendants: their events reach the parent (subsidiary to parent)
        nxt = {}
        for parent, child in _edges(conn, list(frontier), "parent"):
            path = (*frontier[parent], child)[::-1]
            if child not in out:
                out[child] = (SUBSIDIARY_TO_PARENT, path)
                nxt[child] = (*frontier[parent], child)
        frontier = nxt
    for parent in [p for p, (rel, path) in out.items() if rel == PARENT_TO_SUBSIDIARY and len(path) == 2]:
        for _p, child in _edges(conn, [parent], "parent"):
            if child not in out:
                out[child] = (SIBLING, (child, parent, company_id))
    return out


def neighbors(conn: Any, company_id: int, depth: int, cap: int = 500
              ) -> tuple[dict[int, int], list[tuple[int, int, str, str | None]]]:
    """Undirected expansion up to `depth` hops. Returns ({company: hop}, edges with source/as_of)."""
    seen: dict[int, int] = {company_id: 0}
    edges: dict[tuple[int, int], tuple[str, str | None]] = {}
    frontier = [company_id]
    for hop in range(1, depth + 1):
        if not frontier or len(seen) >= cap:
            break
        rows = conn.execute(
            "SELECT parent_id, child_id, source, as_of FROM company_relationships "
            "WHERE parent_id = ANY(%s) OR child_id = ANY(%s)", (frontier, frontier)).fetchall()
        nxt: list[int] = []
        for r in rows:
            for node in (r["parent_id"], r["child_id"]):
                if node not in seen and len(seen) < cap:
                    seen[node] = hop
                    nxt.append(node)
            if r["parent_id"] in seen and r["child_id"] in seen:
                edges[(r["parent_id"], r["child_id"])] = (r["source"], r["as_of"])
        frontier = nxt
    return seen, [(p, c, s, a) for (p, c), (s, a) in edges.items()]


def load_edges(conn: Any, seeds: list[int], depth: int = 2) -> list[tuple[int, int]]:
    """All ownership edges within `depth` hops (undirected) of the seed companies."""
    seen = set(seeds)
    edges: set[tuple[int, int]] = set()
    frontier = list(seen)
    for _ in range(depth):
        if not frontier:
            break
        rows = conn.execute(
            "SELECT parent_id, child_id FROM company_relationships WHERE (parent_id = ANY(%s) "
            "OR child_id = ANY(%s)) AND rel_type IN ('direct_parent','subsidiary','owned_by')",
            (frontier, frontier)).fetchall()
        nxt = []
        for r in rows:
            edges.add((r["parent_id"], r["child_id"]))
            for node in (r["parent_id"], r["child_id"]):
                if node not in seen:
                    seen.add(node)
                    nxt.append(node)
        frontier = nxt
    return sorted(edges)

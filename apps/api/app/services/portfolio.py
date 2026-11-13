"""Portfolio views shared by the API and reports: concentration by ultimate parent."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

HIGH_LEVELS = ("high", "critical")
MAX_LEVELS = 12


def parent_map(conn: Any, company_ids: list[int]) -> dict[int, int]:
    """child -> chosen parent (lowest id) for every ancestor reachable from `company_ids`."""
    parents: dict[int, int] = {}
    frontier = set(company_ids)
    for _ in range(MAX_LEVELS):
        if not frontier:
            break
        rows = conn.execute(
            "SELECT parent_id, child_id FROM company_relationships WHERE child_id = ANY(%s) "
            "AND rel_type IN ('direct_parent','subsidiary','owned_by') ORDER BY parent_id",
            (list(frontier),)).fetchall()
        nxt: set[int] = set()
        for r in rows:
            if r["child_id"] not in parents:
                parents[r["child_id"]] = r["parent_id"]
                if r["parent_id"] not in parents:
                    nxt.add(r["parent_id"])
        frontier = nxt
    return parents


def ultimate(parents: dict[int, int], company_id: int) -> int:
    seen = {company_id}
    cur = company_id
    while cur in parents and parents[cur] not in seen:
        cur = parents[cur]
        seen.add(cur)
    return cur


def concentration(conn: Any, top: int = 20) -> dict[str, Any]:
    """Suppliers grouped under their ultimate parent, with the share at high or critical level."""
    rows = conn.execute(
        "SELECT s.id, s.resolved_company_id AS cid, rs.level FROM suppliers s "
        "LEFT JOIN LATERAL (SELECT level FROM risk_scores r WHERE r.supplier_id = s.id "
        "ORDER BY computed_at DESC, id DESC LIMIT 1) rs ON true "
        "WHERE s.resolved_company_id IS NOT NULL AND s.duplicate_of IS NULL").fetchall()
    total = len(rows)
    if not total:
        return {"total_suppliers": 0, "groups": []}
    parents = parent_map(conn, sorted({int(r["cid"]) for r in rows}))
    groups: dict[int, dict[str, int]] = defaultdict(lambda: {"suppliers": 0, "high": 0})
    for r in rows:
        g = groups[ultimate(parents, int(r["cid"]))]
        g["suppliers"] += 1
        g["high"] += r["level"] in HIGH_LEVELS
    names = {r["id"]: r["canonical_name"] for r in conn.execute(
        "SELECT id, canonical_name FROM companies WHERE id = ANY(%s)", (list(groups),)).fetchall()}
    high_total = sum(g["high"] for g in groups.values())
    ordered = sorted(groups.items(), key=lambda kv: (-kv[1]["suppliers"], kv[0]))
    out, cumulative = [], 0
    for cid, g in ordered[:top]:
        cumulative += g["suppliers"]
        out.append({"company_id": cid, "name": names.get(cid), "suppliers": g["suppliers"],
                    "share_of_suppliers": g["suppliers"] / total, "high_risk_suppliers": g["high"],
                    "share_of_high_risk": (g["high"] / high_total) if high_total else 0.0,
                    "cumulative_share": cumulative / total})
    return {"total_suppliers": total, "high_risk_suppliers": high_total, "groups": out}

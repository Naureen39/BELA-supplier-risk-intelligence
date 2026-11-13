"""Supplier profile data: canonical record, family, facilities, events, risk, and source links."""

from __future__ import annotations

from typing import Any

from app.core.serialize import jsonable
from app.repo.family import related_companies

DISCLAIMER = "Risk signals are leads for human review and not statements of fault."


def source_url(source: str, key: str) -> str | None:
    s = source.lower()
    if "edgar" in s or s == "sec":
        return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={key}"
    if "gleif" in s:
        return f"https://search.gleif.org/#/record/{key}"
    if "wikidata" in s:
        return f"https://www.wikidata.org/wiki/{key}"
    if "echo" in s or "frs" in s or "epa" in s:
        return f"https://echo.epa.gov/detailed-facility-report?fid={key}"
    return None


def canonical_record(conn: Any, company_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, canonical_name, legal_form, cik, lei, wikidata_qid, tickers, sic_code, "
        "state_of_incorporation, hq_city, hq_state, hq_country, is_public, status, description "
        "FROM companies WHERE id = %s", (company_id,)).fetchone()
    if not row:
        return None
    aliases = conn.execute("SELECT alias, alias_type, source FROM company_aliases WHERE company_id = %s "
                           "ORDER BY alias_type, alias", (company_id,)).fetchall()
    return jsonable(row) | {"aliases": [jsonable(a) for a in aliases]}


def family_tree(conn: Any, company_id: int, depth: int = 2) -> dict[str, Any]:
    """Ancestors and descendants with source, as-of date, and a portfolio overlay."""
    nodes: dict[int, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def walk(start: list[int], direction: str) -> None:
        frontier = start
        for hop in range(1, depth + 1):
            if not frontier:
                return
            col, other = ("child_id", "parent_id") if direction == "up" else ("parent_id", "child_id")
            rows = conn.execute(
                f"SELECT parent_id, child_id, rel_type, ownership_share, source, as_of "
                f"FROM company_relationships WHERE {col} = ANY(%s)", (frontier,)).fetchall()
            nxt = []
            for r in rows:
                edges.append(jsonable(r))
                node = r[other]
                if node not in nodes and node != company_id:
                    nodes[node] = {"id": node, "hop": hop, "direction": direction}
                    nxt.append(node)
            frontier = nxt

    walk([company_id], "up")
    walk([company_id], "down")
    if nodes:
        names = {r["id"]: r["canonical_name"] for r in conn.execute(
            "SELECT id, canonical_name FROM companies WHERE id = ANY(%s)", (list(nodes),)).fetchall()}
        mine = {int(r["resolved_company_id"]) for r in conn.execute(
            "SELECT DISTINCT resolved_company_id FROM suppliers WHERE resolved_company_id = ANY(%s) "
            "AND duplicate_of IS NULL", (list(nodes),)).fetchall()}
        for n, node in nodes.items():
            node["name"] = names.get(n)
            node["in_portfolio"] = n in mine
    return {"nodes": sorted(nodes.values(), key=lambda n: (n["direction"], n["hop"], n["id"])),
            "edges": edges}


def facilities(conn: Any, company_id: int, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT registry_id, name, address, city, state, postal_code, latitude, longitude, "
        "industry_code, source, link_confidence FROM facilities WHERE company_id = %s "
        "ORDER BY state, city, name LIMIT %s", (company_id, limit)).fetchall()
    return [jsonable(r) for r in rows]


def event_timeline(conn: Any, company_id: int, limit: int = 50) -> list[dict[str, Any]]:
    related = related_companies(conn, company_id)
    rows = conn.execute(
        "SELECT DISTINCT ON (e.reported_at, e.id) e.id, e.source, e.event_type, e.severity, "
        "e.occurred_at, e.reported_at, e.title, e.summary, e.url, e.state, ee.company_id AS via "
        "FROM events e JOIN event_entities ee ON ee.event_id = e.id "
        "WHERE ee.company_id = ANY(%s) AND ee.route = 'accepted' "
        "ORDER BY e.reported_at DESC, e.id DESC LIMIT %s", (list(related), limit)).fetchall()
    out = []
    for r in rows:
        rel, path = related[r["via"]]
        out.append(jsonable(r) | {"relation": rel, "path": list(path)})
    return out


def latest_risk(conn: Any, supplier_id: str) -> dict[str, Any] | None:
    score = conn.execute("SELECT id, score, level, config_version, computed_at FROM risk_scores "
                         "WHERE supplier_id = %s ORDER BY computed_at DESC, id DESC LIMIT 1",
                         (supplier_id,)).fetchone()
    if not score:
        return None
    comps = conn.execute(
        "SELECT c.event_id, c.category, c.severity_weight, c.recency_decay, c.link_confidence, "
        "c.relation_weight, c.source_reliability, c.event_impact, e.title, e.source, e.url, "
        "e.reported_at FROM risk_score_components c JOIN events e ON e.id = c.event_id "
        "WHERE c.risk_score_id = %s ORDER BY c.event_impact DESC", (score["id"],)).fetchall()
    categories: dict[str, float] = {}
    for c in comps:
        categories[c["category"]] = 1 - (1 - categories.get(c["category"], 0.0)) * (1 - c["event_impact"])
    return {"score": float(score["score"]), "level": score["level"],
            "config_version": score["config_version"], "computed_at": score["computed_at"],
            "components": [jsonable(c) for c in comps],
            "category_scores": {k: round(v * 100, 2) for k, v in sorted(categories.items())}}


def source_links(conn: Any, company_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT source, source_key, record_type, name, method, score FROM source_records "
                        "WHERE company_id = %s ORDER BY source, source_key", (company_id,)).fetchall()
    return [jsonable(r) | {"url": source_url(r["source"], r["source_key"])} for r in rows]


def supplier_profile(conn: Any, supplier: dict[str, Any]) -> dict[str, Any]:
    cid = supplier["resolved_company_id"]
    out: dict[str, Any] = {
        "supplier": jsonable({k: supplier[k] for k in ("id", "uploaded_name", "tier", "status",
                                                       "confidence", "attributes", "resolution_detail")}),
        "company": None, "family": None, "facilities": [], "events": [], "sources": [],
        "risk": latest_risk(conn, str(supplier["id"])), "disclaimer": DISCLAIMER}
    if cid is not None:
        out["company"] = canonical_record(conn, int(cid))
        out["family"] = family_tree(conn, int(cid))
        out["facilities"] = facilities(conn, int(cid))
        out["events"] = event_timeline(conn, int(cid))
        out["sources"] = source_links(conn, int(cid))
    return out

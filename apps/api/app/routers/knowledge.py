"""Events, companies, and the corporate graph (global data, read-only for tenants)."""

from __future__ import annotations

from typing import Any

import networkx as nx
from fastapi import APIRouter, Depends, Query

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.errors import ApiError
from app.repo.family import neighbors
from app.routers.common import jsonable, keyset, page

router = APIRouter(tags=["knowledge"])
viewer = deps.require(P.VIEW)
DISCLAIMER = "Risk signals are leads for human review and not statements of fault."


@router.get("/events", summary="Events with an accepted company link")
def events(cursor: str | None = None, limit: int = 50, source: str | None = None,
           event_type: str | None = None, min_severity: int = Query(1, ge=1, le=4),
           state: str | None = None, since: str | None = None, company_id: int | None = None,
           p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB,
           c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, "
        "e.summary, e.url, e.state, e.city, e.cluster_id FROM events e "
        "WHERE EXISTS (SELECT 1 FROM event_entities ee WHERE ee.event_id = e.id AND ee.route = 'accepted' "
        "AND (%s::bigint IS NULL OR ee.company_id = %s::bigint)) "
        "AND (%s::text IS NULL OR e.source = %s) AND (%s::text IS NULL OR e.event_type = %s) "
        "AND e.severity >= %s AND (%s::text IS NULL OR e.state = %s) "
        "AND (%s::timestamptz IS NULL OR e.reported_at >= %s::timestamptz) "
        "AND (%s::text IS NULL OR (e.reported_at, e.id) < (%s::timestamptz, %s::bigint)) "
        "ORDER BY e.reported_at DESC, e.id DESC LIMIT %s",
        (company_id, company_id, source, source, event_type, event_type, min_severity, state, state,
         since, since, pos and pos[0], pos and pos[0], pos and pos[1], lim + 1)).fetchall()
    return page(c, rows, lim, ("reported_at", "id")) | {"disclaimer": DISCLAIMER}


@router.get("/events/{event_id}", summary="Event with linked companies and candidates considered")
def event_detail(event_id: int, p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB
                 ) -> dict[str, Any]:
    ev = conn.execute("SELECT * FROM events WHERE id = %s AND EXISTS (SELECT 1 FROM event_entities ee "
                      "WHERE ee.event_id = events.id AND ee.route = 'accepted')", (event_id,)).fetchone()
    if not ev:
        raise ApiError(404, "The event was not found.", code="not-found")
    ents = conn.execute(
        "SELECT ee.id, ee.company_id, co.canonical_name, ee.role, ee.method, ee.score, ee.route "
        "FROM event_entities ee LEFT JOIN companies co ON co.id = ee.company_id "
        "WHERE ee.event_id = %s ORDER BY ee.id", (event_id,)).fetchall()
    out = []
    for e in ents:
        if e["route"] != "accepted":
            continue  # unreviewed links are not shown to tenants
        cands = conn.execute(
            "SELECT lc.rank, lc.company_id, co.canonical_name, lc.bela_score, lc.blink_score, "
            "lc.splink_score, lc.llm_label FROM link_candidates lc JOIN companies co ON co.id = lc.company_id "
            "WHERE lc.event_entity_id = %s ORDER BY lc.rank", (e["id"],)).fetchall()
        out.append(jsonable(e) | {"candidates": [jsonable(x) for x in cands]})
    return jsonable(ev) | {"entities": out, "disclaimer": DISCLAIMER}


@router.get("/companies/search", summary="Search canonical companies")
def company_search(q: str = Query(min_length=2, max_length=120), limit: int = 20,
                   p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB
                   ) -> dict[str, Any]:
    from app.kb.normalize import normalize_name

    norm = normalize_name(q)
    rows = conn.execute(
        "SELECT id, canonical_name, cik, lei, wikidata_qid, tickers, hq_city, hq_state, is_public, "
        "similarity(normalized_name, %s) AS score FROM companies WHERE normalized_name %% %s "
        "OR normalized_name LIKE %s || '%%' OR upper(%s) = ANY(tickers) "
        "ORDER BY score DESC, id LIMIT %s", (norm, norm, norm, q, min(max(limit, 1), 50))).fetchall()
    return {"items": [jsonable(r) for r in rows]}


@router.get("/companies/{company_id}", summary="Canonical company record")
def company(company_id: int, p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB
            ) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, canonical_name, legal_form, cik, lei, wikidata_qid, tickers, sic_code, "
        "state_of_incorporation, hq_city, hq_state, hq_country, is_public, status, description "
        "FROM companies WHERE id = %s", (company_id,)).fetchone()
    if not row:
        raise ApiError(404, "The company was not found.", code="not-found")
    aliases = conn.execute("SELECT alias, alias_type, source FROM company_aliases WHERE company_id = %s "
                           "ORDER BY alias", (company_id,)).fetchall()
    return jsonable(row) | {"aliases": [jsonable(a) for a in aliases]}


@router.get("/companies/{company_id}/family", summary="Parents and subsidiaries with provenance")
def family(company_id: int, p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB
           ) -> dict[str, Any]:
    if not conn.execute("SELECT 1 FROM companies WHERE id = %s", (company_id,)).fetchone():
        raise ApiError(404, "The company was not found.", code="not-found")
    rel = conn.execute(
        "SELECT r.parent_id, pc.canonical_name AS parent_name, r.child_id, cc.canonical_name AS child_name, "
        "r.rel_type, r.ownership_share, r.source, r.as_of FROM company_relationships r "
        "JOIN companies pc ON pc.id = r.parent_id JOIN companies cc ON cc.id = r.child_id "
        "WHERE r.parent_id = %s OR r.child_id = %s ORDER BY r.as_of DESC NULLS LAST", (company_id,) * 2
    ).fetchall()
    return {"company_id": company_id,
            "parents": [jsonable(r) for r in rel if r["child_id"] == company_id],
            "subsidiaries": [jsonable(r) for r in rel if r["parent_id"] == company_id]}


@router.get("/graph/neighbors", summary="Neighbor expansion (depth up to 3, at most 500 nodes)")
def graph_neighbors(company_id: int, depth: int = Query(1, ge=1, le=3),
                    p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB
                    ) -> dict[str, Any]:
    seen, edges = neighbors(conn, company_id, depth, cap=500)
    if len(seen) == 1 and not conn.execute("SELECT 1 FROM companies WHERE id = %s",
                                           (company_id,)).fetchone():
        raise ApiError(404, "The company was not found.", code="not-found")
    names = {r["id"]: r["canonical_name"] for r in conn.execute(
        "SELECT id, canonical_name FROM companies WHERE id = ANY(%s)", (list(seen),)).fetchall()}
    in_portfolio = {int(r["resolved_company_id"]) for r in conn.execute(
        "SELECT DISTINCT resolved_company_id FROM suppliers WHERE resolved_company_id = ANY(%s)",
        (list(seen),)).fetchall()}
    return {"nodes": [{"id": n, "name": names.get(n), "hop": h, "in_portfolio": n in in_portfolio}
                      for n, h in seen.items()],
            "edges": [{"parent_id": a, "child_id": b, "source": s, "as_of": d} for a, b, s, d in edges],
            "truncated": len(seen) >= 500}


@router.get("/graph/path", summary="Shortest ownership path between two companies")
def graph_path(source: int, target: int, p: Principal = Depends(viewer),
               conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    seen, edges = neighbors(conn, source, 3, cap=500)
    g: nx.Graph[int] = nx.Graph()
    g.add_nodes_from(seen)
    g.add_edges_from((a, b) for a, b, _s, _d in edges)
    if target not in g or not nx.has_path(g, source, target):
        return {"found": False, "path": []}
    path = nx.shortest_path(g, source, target)
    names = {r["id"]: r["canonical_name"] for r in conn.execute(
        "SELECT id, canonical_name FROM companies WHERE id = ANY(%s)", (path,)).fetchall()}
    return {"found": True, "path": [{"id": n, "name": names.get(n)} for n in path]}

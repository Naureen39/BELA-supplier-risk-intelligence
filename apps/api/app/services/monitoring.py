"""Database-backed monitoring: rescore suppliers, record scores, raise alerts, notify.

Wraps the Phase 4 library (clustering, roll-up, scoring, alert drafting) around the tables.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.container import Container
from app.events.dedup import cluster_events, representative
from app.events.monitor import AlertRule, EventFacts, SupplierFacts, draft_alerts
from app.events.risk import ScoredEvent, SupplierScore, score_supplier
from app.events.schema import NEWS, REGULATOR, EntityRef, NormalizedEvent
from app.events.store import insert_score
from app.repo.family import load_edges
from app.resolution.rollup import CorporateGraph
from app.services.alerts import create_alerts
from app.services.notify import Notifier
from app.services.risk_config import current_risk_config

LOOKBACK_DAYS = 3 * 365


def _load_events(conn: Any, now: datetime) -> tuple[list[NormalizedEvent], list[int], list[dict[int, float]]]:
    rows = conn.execute(
        "SELECT e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, e.state, "
        "ee.company_id, ee.score FROM events e JOIN event_entities ee ON ee.event_id = e.id "
        "WHERE ee.route = 'accepted' AND ee.company_id IS NOT NULL AND e.reported_at >= %s "
        "ORDER BY e.id", (now - timedelta(days=LOOKBACK_DAYS),)).fetchall()
    by_event: dict[int, dict[str, Any]] = {}
    links: dict[int, dict[int, float]] = defaultdict(dict)
    for r in rows:
        by_event.setdefault(int(r["id"]), r)
        links[int(r["id"])][int(r["company_id"])] = max(links[int(r["id"])].get(int(r["company_id"]), 0.0),
                                                       float(r["score"]))
    ids = sorted(by_event)
    events = [NormalizedEvent(
        source=by_event[i]["source"], source_id=str(i),
        source_class=NEWS if by_event[i]["source"] == "news" else REGULATOR,
        event_type=by_event[i]["event_type"], severity=int(by_event[i]["severity"]),
        reported_at=by_event[i]["reported_at"], occurred_at=by_event[i]["occurred_at"],
        title=by_event[i]["title"], entities=[EntityRef("", "operator")], state=by_event[i]["state"])
        for i in ids]
    return events, ids, [links[i] for i in ids]


def _rules(conn: Any) -> list[AlertRule]:
    return [AlertRule(id=str(r["id"]), event_types=frozenset(r["event_types"]),
                      min_severity=int(r["min_severity"]), supplier_tiers=frozenset(r["supplier_tiers"]),
                      states=frozenset(r["states"]), is_active=bool(r["is_active"]))
            for r in conn.execute("SELECT * FROM alert_rules WHERE is_active").fetchall()]


async def recompute_tenant(c: Container, tenant_id: str, now: datetime | None = None,
                           notifier: Notifier | None = None) -> dict[str, int]:
    """Rescore every resolved supplier of a tenant. Returns counters for the run."""
    now = now or datetime.now(UTC)
    drafts = []
    written = 0
    with c.db.tenant(tenant_id) as conn:
        _version, cfg = current_risk_config(conn)
        suppliers = conn.execute(
            "SELECT id, tier, resolved_company_id AS cid FROM suppliers WHERE resolved_company_id IS NOT NULL "
            "AND duplicate_of IS NULL ORDER BY created_at, id").fetchall()
        events, ids, links = _load_events(conn, now)
        keys = [frozenset(link) for link in links]
        clusters = cluster_events(events, keys)
        cluster_rows = [(ids[representative(events, cl)], [ids[i] for i in cl.members])
                        for cl in clusters if len(cl.members) > 1]
        seeds = sorted({int(s["cid"]) for s in suppliers} | {cid for link in links for cid in link})
        graph = CorporateGraph(load_edges(conn, seeds, cfg.max_depth))
        rules = _rules(conn)
        for sup in suppliers:
            scored: list[ScoredEvent] = []
            for cl in clusters:
                rep_i = representative(events, cl)
                conf: dict[int, float] = {}
                for i in cl.members:
                    for cid, score in links[i].items():
                        conf[cid] = max(conf.get(cid, 0.0), score)
                is_reg = any(events[i].source_class == REGULATOR for i in cl.members)
                for cid, link_conf in conf.items():
                    for p in graph.reach(cid, [int(sup["cid"])], cfg.max_depth):
                        scored.append(ScoredEvent(
                            event_id=ids[rep_i], category=events[rep_i].event_type,
                            severity=events[rep_i].severity,
                            source_class=REGULATOR if is_reg else NEWS, time=events[rep_i].effective_time,
                            link_confidence=link_conf, relation=p.relation, depth=p.depth, path=p.path))
            current = score_supplier(scored, now, cfg)
            prev_row = conn.execute(
                "SELECT id, score, level, config_version FROM risk_scores WHERE supplier_id = %s "
                "ORDER BY computed_at DESC, id DESC LIMIT 1", (sup["id"],)).fetchone()
            prev_events: set[int] = set()
            previous: SupplierScore | None = None
            if prev_row:
                prev_events = {int(r["event_id"]) for r in conn.execute(
                    "SELECT event_id FROM risk_score_components WHERE risk_score_id = %s",
                    (prev_row["id"],)).fetchall()}
                previous = SupplierScore(float(prev_row["score"]), prev_row["level"],
                                         prev_row["config_version"], (), {})
            cur_events = {comp.event_id for comp in current.components}
            if (previous is None or abs(previous.score - current.score) > 1e-9
                    or prev_events != cur_events or previous.config_version != current.config_version):
                insert_score(conn, tenant_id, str(sup["id"]), current,
                             {e: e for e in cur_events})  # component event ids are events.id
                written += 1
            facts = []
            for comp in current.components:
                if comp.event_id in prev_events:
                    continue
                ev = events[ids.index(comp.event_id)]
                facts.append(EventFacts(comp.event_id, ev.event_type, ev.severity, ev.state))
            for d in draft_alerts(SupplierFacts(str(sup["id"]), sup["tier"]), previous, current, facts,
                                  rules):
                drafts.append((str(sup["id"]), d))
    with c.db.system() as sconn:  # events are global: cluster ids are written by the system role
        for rep, members in cluster_rows:
            sconn.execute("UPDATE events SET cluster_id = %s WHERE id = ANY(%s) AND "
                          "cluster_id IS DISTINCT FROM %s", (rep, members, rep))
    created = await create_alerts(c, tenant_id, drafts)
    (notifier or Notifier(c)).dispatch(tenant_id, created)
    return {"suppliers": len(suppliers), "scores_written": written, "alerts_created": len(created)}


async def recompute_all(c: Container, now: datetime | None = None) -> dict[str, dict[str, int]]:
    """Entry point for the scheduled task: every tenant that has resolved suppliers."""
    with c.db.system() as conn:
        tenants = [str(r["tenant_id"]) for r in conn.execute(
            "SELECT DISTINCT tenant_id FROM suppliers WHERE resolved_company_id IS NOT NULL").fetchall()]
    return {t: await recompute_tenant(c, t, now) for t in tenants}

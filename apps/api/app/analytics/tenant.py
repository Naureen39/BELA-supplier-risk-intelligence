"""Portfolio, quality, and usage analytics for one tenant (plan section 9.2).

All functions take a tenant-scoped connection, so row level security limits every query to the
caller's data. Daily series come from `portfolio_stats_daily` (demo data) when it has rows for the
window and fall back to live tables otherwise; responses say which one they used.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.analytics.common import Window, change, plain
from app.services.portfolio import concentration as portfolio_concentration

LEVEL_BANDS = {"medium": 30, "high": 50, "critical": 70}
LEVEL_RANK = "CASE {c} WHEN 'low' THEN 1 WHEN 'medium' THEN 2 WHEN 'high' THEN 3 WHEN 'critical' THEN 4 END"
RANK_LEVEL = {1: "low", 2: "medium", 3: "high", 4: "critical"}
# Days after which a source is flagged. Configured defaults, not measured service levels.
FRESH_DAYS = {"news": 2}
DEFAULT_FRESH_DAYS = 10

LATEST = ("SELECT DISTINCT ON (r.supplier_id) r.supplier_id, r.score, r.level, r.computed_at "
          "FROM risk_scores r ORDER BY r.supplier_id, r.computed_at DESC, r.id DESC")

EVENTS = """
SELECT e.id, e.source, e.event_type, e.severity, e.reported_at, e.title, e.state, e.latitude, e.longitude,
       s.id AS supplier_id, s.tier
FROM events e
JOIN event_entities ee ON ee.event_id = e.id AND ee.route = 'accepted'
JOIN suppliers s ON s.resolved_company_id = ee.company_id AND s.duplicate_of IS NULL
WHERE e.reported_at >= %(start)s AND e.reported_at < %(end_excl)s
  AND (%(source)s::text IS NULL OR (%(source)s = 'regulator' AND e.source <> 'news') OR e.source = %(source)s)
"""


def default_end(conn: Any) -> date:
    row = conn.execute("SELECT max(day) AS d FROM portfolio_stats_daily").fetchone()
    return row["d"] if row and row["d"] else date.today()


def _p(win: Window, g: str = "day", source: str | None = None) -> dict[str, Any]:
    return {"start": win.start, "end": win.end, "end_excl": win.end + timedelta(days=1), "g": g,
            "source": source}


def _stats_exist(conn: Any, win: Window) -> bool:
    return conn.execute("SELECT 1 FROM portfolio_stats_daily WHERE day BETWEEN %s AND %s LIMIT 1",
                        (win.start, win.end)).fetchone() is not None


def _stats_at(conn: Any, win: Window) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT day, risk_index, suppliers_by_level, auto_resolved, reviewed, unresolved, median_review_minutes "
        "FROM portfolio_stats_daily WHERE day BETWEEN %s AND %s ORDER BY day DESC LIMIT 1",
        (win.start, win.end)).fetchone()
    return dict(row) if row else None


def _event_count(conn: Any, win: Window, source: str | None) -> int:
    return int(conn.execute(f"SELECT count(DISTINCT id) AS n FROM ({EVENTS}) q",
                            _p(win, source=source)).fetchone()["n"])


def _live_levels(conn: Any) -> dict[str, int]:
    rows = conn.execute(
        f"SELECT l.level, count(*) AS n FROM suppliers s JOIN ({LATEST}) l ON l.supplier_id = s.id "
        "WHERE s.duplicate_of IS NULL GROUP BY l.level").fetchall()
    return {r["level"]: int(r["n"]) for r in rows}


def _decided(conn: Any, win: Window) -> dict[str, Any]:
    row = conn.execute(
        "SELECT count(*) AS decided, count(*) FILTER (WHERE status IN ('rejected','chose_other')) AS changed, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM decided_at - created_at) / 60) AS median_min "
        "FROM resolution_reviews WHERE decided_at >= %(start)s AND decided_at < %(end_excl)s",
        _p(win)).fetchone()
    return dict(row)


def _false_links(conn: Any, win: Window) -> dict[str, Any]:
    """Wrong-link corrections filed in the window per 1,000 resolved suppliers."""
    wrong = conn.execute("SELECT count(*) AS n FROM corrections WHERE kind = 'wrong_link' "
                         "AND created_at >= %(start)s AND created_at < %(end_excl)s", _p(win)).fetchone()["n"]
    resolved = conn.execute("SELECT count(*) AS n FROM suppliers WHERE duplicate_of IS NULL AND "
                            "status IN ('auto_resolved','resolved')").fetchone()["n"]
    return {"wrong_link_corrections": int(wrong), "resolved_suppliers": int(resolved),
            "per_1000": round(1000 * wrong / resolved, 2) if resolved else None}


def _kpi(key: str, label: str, unit: str, value: Any, prev: Any, better: str) -> dict[str, Any]:
    v = float(value) if value is not None else None
    pv = float(prev) if prev is not None else None
    return {"key": key, "label": label, "unit": unit, "better": better, "value": v, "previous": pv,
            "change_pct": change(v, pv)}


# ------------------------------------------------------------------------------------ portfolio
def portfolio(conn: Any, win: Window, g: str, compare: bool, source: str | None) -> dict[str, Any]:
    prev = win.previous() if compare else None
    use_stats = _stats_exist(conn, win)

    if use_stats:
        trend = conn.execute(
            "SELECT date_trunc(%(g)s, day)::date AS period, round(avg(risk_index), 2) AS risk_index, "
            "round(avg((suppliers_by_level->>'low')::numeric), 1) AS low, "
            "round(avg((suppliers_by_level->>'medium')::numeric), 1) AS medium, "
            "round(avg((suppliers_by_level->>'high')::numeric), 1) AS high, "
            "round(avg((suppliers_by_level->>'critical')::numeric), 1) AS critical "
            "FROM portfolio_stats_daily WHERE day BETWEEN %(start)s AND %(end)s GROUP BY 1 ORDER BY 1",
            _p(win, g)).fetchall()
    else:
        trend = conn.execute(
            "SELECT date_trunc(%(g)s, computed_at)::date AS period, round(avg(score), 2) AS risk_index, "
            "count(*) FILTER (WHERE level = 'low') AS low, count(*) FILTER (WHERE level = 'medium') AS medium, "
            "count(*) FILTER (WHERE level = 'high') AS high, count(*) FILTER (WHERE level = 'critical') AS critical "
            "FROM risk_scores WHERE computed_at >= %(start)s AND computed_at < %(end_excl)s GROUP BY 1 ORDER BY 1",
            _p(win, g)).fetchall()
    trend_rows = [dict(r) for r in trend]

    p = _p(win, g, source)
    by_type = conn.execute(
        f"SELECT date_trunc(%(g)s, reported_at)::date AS period, event_type, count(DISTINCT id) AS events "
        f"FROM ({EVENTS}) q GROUP BY 1, 2 ORDER BY 1, 2", p).fetchall()
    mix = conn.execute(
        f"SELECT CASE WHEN source = 'news' THEN 'news' ELSE 'regulator' END AS source_class, "
        f"count(DISTINCT id) AS events FROM ({EVENTS}) q GROUP BY 1 ORDER BY 2 DESC", p).fetchall()
    by_state = conn.execute(
        f"SELECT state, count(DISTINCT id) AS events, sum(severity) AS weighted_events FROM "
        f"(SELECT DISTINCT id, state, severity FROM ({EVENTS}) q0) q WHERE state IS NOT NULL "
        f"GROUP BY state ORDER BY weighted_events DESC, state", p).fetchall()
    facility_events = conn.execute(
        f"SELECT DISTINCT ON (id) id, title, event_type, severity, state, latitude, longitude, reported_at "
        f"FROM ({EVENTS}) q WHERE latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY id, reported_at DESC",
        p).fetchall()
    facility_events = sorted((dict(r) for r in facility_events), key=lambda r: r["reported_at"], reverse=True)[:200]

    heat = conn.execute(
        f"SELECT coalesce(q.tier, 'untiered') AS tier, q.event_type, count(DISTINCT q.id) AS events, "
        f"max({LEVEL_RANK.format(c='l.level')}) AS max_rank FROM ({EVENTS}) q "
        f"LEFT JOIN ({LATEST}) l ON l.supplier_id = q.supplier_id GROUP BY 1, 2 ORDER BY 1, 2", p).fetchall()
    heatmap = [{"tier": r["tier"], "event_type": r["event_type"], "events": r["events"],
                "max_level": RANK_LEVEL.get(r["max_rank"])} for r in heat]

    top = conn.execute(
        f"SELECT s.id AS supplier_id, s.uploaded_name AS name, s.tier, l.score, l.level, "
        f"(SELECT jsonb_build_object('title', e.title, 'reported_at', e.reported_at, 'event_type', e.event_type) "
        f"   FROM events e JOIN event_entities ee ON ee.event_id = e.id AND ee.route = 'accepted' "
        f"   WHERE ee.company_id = s.resolved_company_id ORDER BY e.reported_at DESC LIMIT 1) AS last_event, "
        f"(SELECT r2.score FROM risk_scores r2 WHERE r2.supplier_id = s.id "
        f"   AND r2.computed_at <= l.computed_at - interval '30 days' ORDER BY r2.computed_at DESC, r2.id DESC LIMIT 1) "
        f"   AS score_30d_ago, "
        f"(SELECT array_agg(x.score ORDER BY x.computed_at) FROM (SELECT score, computed_at FROM risk_scores r3 "
        f"   WHERE r3.supplier_id = s.id ORDER BY computed_at DESC, id DESC LIMIT 12) x) AS sparkline "
        f"FROM suppliers s JOIN ({LATEST}) l ON l.supplier_id = s.id WHERE s.duplicate_of IS NULL "
        f"ORDER BY l.score DESC, s.uploaded_name LIMIT 20").fetchall()
    top_rows = []
    for r in top:
        d = dict(r)
        old = d.pop("score_30d_ago")
        d["change_30d"] = round(float(d["score"]) - float(old), 2) if old is not None else None
        top_rows.append(d)

    by_status = conn.execute("SELECT status, count(*) AS n FROM suppliers WHERE duplicate_of IS NULL "
                             "GROUP BY status").fetchall()
    open_alerts = conn.execute("SELECT count(*) AS n FROM alerts WHERE status IN ('new','in_review')"
                               ).fetchone()["n"]
    queue = conn.execute("SELECT count(*) AS n FROM resolution_reviews WHERE status = 'open'").fetchone()["n"]

    # KPI cards
    cur_stats = _stats_at(conn, win) if use_stats else None
    prev_stats = _stats_at(conn, prev) if prev and use_stats else None
    live_levels = _live_levels(conn)

    def hc(levels: dict[str, Any]) -> int:
        return int(levels.get("high", 0)) + int(levels.get("critical", 0))

    def res_rate(s: dict[str, Any] | None) -> float | None:
        if not s:
            return None
        total = s["auto_resolved"] + s["reviewed"] + s["unresolved"]
        return 100 * s["auto_resolved"] / total if total else None

    live_risk = conn.execute(f"SELECT avg(score) AS a FROM ({LATEST}) l").fetchone()["a"]
    decided = _decided(conn, win)
    prev_decided = _decided(conn, prev) if prev else None
    live_status = {r["status"]: int(r["n"]) for r in by_status}
    live_total = sum(live_status.values())
    live_auto = 100 * live_status.get("auto_resolved", 0) / live_total if live_total else None
    fl = _false_links(conn, win)
    prev_fl = _false_links(conn, prev) if prev else None
    cur_median = decided["median_min"] if decided["median_min"] is not None else (
        cur_stats["median_review_minutes"] if cur_stats else None)
    kpis = [
        _kpi("risk_index", "Portfolio risk index", "score",
             cur_stats["risk_index"] if cur_stats else live_risk,
             prev_stats["risk_index"] if prev_stats else None, "down"),
        _kpi("high_critical_suppliers", "Suppliers at high or critical", "count",
             hc(cur_stats["suppliers_by_level"]) if cur_stats else hc(live_levels),
             hc(prev_stats["suppliers_by_level"]) if prev_stats else None, "down"),
        _kpi("events_in_period", "Events in period", "count", _event_count(conn, win, source),
             _event_count(conn, prev, source) if prev else None, "down"),
        _kpi("auto_resolution_rate", "Auto-resolution rate", "percent",
             res_rate(cur_stats) if cur_stats else live_auto, res_rate(prev_stats), "up"),
        _kpi("review_queue_size", "Review queue size", "count", queue, None, "down"),
        _kpi("median_review_minutes", "Median review time", "minutes", cur_median,
             prev_decided["median_min"] if prev_decided else None, "down"),
        _kpi("false_links_per_1000", "False links per 1,000 resolved (reviewer corrections)", "per 1000",
             fl["per_1000"], prev_fl["per_1000"] if prev_fl else None, "down"),
    ]
    return plain({
        "window": {"from": win.start, "to": win.end,
                   "previous": {"from": prev.start, "to": prev.end} if prev else None},
        "granularity": g, "source_filter": source,
        "demo_data": use_stats, "series_source": "portfolio_stats_daily" if use_stats else "live",
        "kpis": kpis,
        "totals": {"suppliers_by_status": live_status, "suppliers_by_level": live_levels,
                   "events_by_type": _sum_by(by_type, "event_type"), "open_alerts": int(open_alerts)},
        "risk_index_trend": {"bands": LEVEL_BANDS, "items": [
            {"period": r["period"], "risk_index": r["risk_index"]} for r in trend_rows]},
        "suppliers_by_level_trend": [{k: r[k] for k in ("period", "low", "medium", "high", "critical")}
                                     for r in trend_rows],
        "events_by_type": [dict(r) for r in by_type],
        "event_source_mix": [dict(r) for r in mix],
        "risk_by_state": [dict(r) for r in by_state],
        "facility_events": facility_events,
        "category_heatmap": heatmap,
        "concentration_by_parent": portfolio_concentration(conn),
        "top_risk_suppliers": top_rows,
        "disclaimer": "Risk signals are leads for human review and not statements of fault.",
        "notes": ["Events are counted when they link directly to a supplier's resolved company. "
                  "Events reaching a supplier through its corporate family appear in risk scores and alerts."],
    })


def _sum_by(rows: list[Any], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + int(r["events"])
    return out


# --------------------------------------------------------------------------------------- quality
def read_eval_metrics(path: str) -> dict[str, Any] | None:
    f = Path(path)
    if not f.is_file():
        return None
    try:
        raw = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    systems = []
    for name, m in sorted((raw.get("systems") or {}).items()):
        v = m.get("false_links_per_1000")
        systems.append({"system": name, "false_links_per_1000": None if v != v else v,
                        "accuracy_at_1": m.get("accuracy@1")})
    return {"data": raw.get("data"), "records": raw.get("n"), "config_status": raw.get("config_status"),
            "systems": systems}


def freshness_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT source, count(*) AS records, max(reported_at) AS latest, "
                        "extract(epoch FROM now() - max(reported_at)) / 86400 AS age_days "
                        "FROM events GROUP BY source ORDER BY source").fetchall()
    out = []
    for r in rows:
        limit = FRESH_DAYS.get(r["source"], DEFAULT_FRESH_DAYS)
        age = float(r["age_days"])
        status = "fresh" if age <= limit else ("aging" if age <= 3 * limit else "stale")
        out.append({"source": r["source"], "records": r["records"], "latest_record_at": r["latest"],
                    "age_days": round(age, 1), "status": status, "fresh_within_days": limit})
    return out


def routing(conn: Any) -> dict[str, Any]:
    """Records flowing from upload to outcome. Counts come from the stored resolution detail."""
    r = conn.execute(
        "SELECT count(*) AS total, "
        "count(*) FILTER (WHERE resolution_detail->>'route' = 'exact_id') AS exact_identifier, "
        "count(*) FILTER (WHERE resolution_detail->>'route' = 'accepted') AS accepted_by_model, "
        "count(*) FILTER (WHERE resolution_detail->>'route' = 'review') AS human_review, "
        "count(*) FILTER (WHERE resolution_detail->>'route' = 'nil') AS unresolved_by_model, "
        "count(*) FILTER (WHERE resolution_detail->>'route' = 'review' AND status = 'resolved') AS review_resolved, "
        "count(*) FILTER (WHERE resolution_detail->>'route' = 'review' AND status = 'unresolved') AS review_unresolved, "
        "count(*) FILTER (WHERE resolution_detail->>'route' = 'review' AND status = 'needs_review') AS review_open "
        "FROM suppliers WHERE duplicate_of IS NULL AND status <> 'pending'").fetchone()
    d = {k: int(v) for k, v in dict(r).items()}
    links = [("Records", "Exact identifier", d["exact_identifier"]),
             ("Records", "Accepted by model", d["accepted_by_model"]),
             ("Records", "Human review", d["human_review"]),
             ("Records", "Unresolved", d["unresolved_by_model"]),
             ("Human review", "Resolved by reviewer", d["review_resolved"]),
             ("Human review", "Unresolved by reviewer", d["review_unresolved"]),
             ("Human review", "Awaiting review", d["review_open"])]
    return {"total": d["total"], "links": [{"source": a, "target": b, "value": n} for a, b, n in links if n],
            "note": "Adjudication by BLINK or a language model applies to news mentions. Uploaded "
                    "supplier records are routed by identifier, the match model, or a reviewer."}


def quality(conn: Any, win: Window, g: str, compare: bool, metrics_path: str) -> dict[str, Any]:
    use_stats = _stats_exist(conn, win)
    status = conn.execute("SELECT status, count(*) AS n FROM suppliers GROUP BY status").fetchall()
    reviews = conn.execute("SELECT status, count(*) AS n FROM resolution_reviews GROUP BY status").fetchall()
    decided = _decided(conn, win)
    total = sum(r["n"] for r in status) or 1
    auto = sum(r["n"] for r in status if r["status"] == "auto_resolved")

    if use_stats:
        quality_rows = conn.execute(
            "SELECT date_trunc(%(g)s, day)::date AS period, round(avg(auto_resolved), 1) AS auto_resolved, "
            "round(avg(reviewed), 1) AS reviewed, round(avg(unresolved), 1) AS unresolved "
            "FROM portfolio_stats_daily WHERE day BETWEEN %(start)s AND %(end)s GROUP BY 1 ORDER BY 1",
            _p(win, g)).fetchall()
    else:
        quality_rows = conn.execute(
            "SELECT date_trunc(%(g)s, created_at)::date AS period, "
            "count(*) FILTER (WHERE status = 'auto_resolved') AS auto_resolved, "
            "count(*) FILTER (WHERE status IN ('resolved','needs_review')) AS reviewed, "
            "count(*) FILTER (WHERE status = 'unresolved') AS unresolved "
            "FROM suppliers WHERE created_at >= %(start)s AND created_at < %(end_excl)s GROUP BY 1 ORDER BY 1",
            _p(win, g)).fetchall()

    workload = conn.execute(
        "SELECT date_trunc(%(g)s, decided_at)::date AS period, count(*) AS reviews_completed, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM decided_at - created_at) / 60) "
        "AS median_review_minutes FROM resolution_reviews WHERE decided_at >= %(start)s AND "
        "decided_at < %(end_excl)s GROUP BY 1 ORDER BY 1", _p(win, g)).fetchall()
    if not workload and use_stats:
        workload = conn.execute(
            "SELECT date_trunc(%(g)s, day)::date AS period, NULL::bigint AS reviews_completed, "
            "round(avg(median_review_minutes), 2) AS median_review_minutes FROM portfolio_stats_daily "
            "WHERE day BETWEEN %(start)s AND %(end)s GROUP BY 1 ORDER BY 1", _p(win, g)).fetchall()

    latency = conn.execute(
        "SELECT date_trunc(%(g)s, day)::date AS period, round(avg(p50_latency_ms), 2) AS p50_ms, "
        "round(avg(p95_latency_ms), 2) AS p95_ms, round(avg(throughput_rps), 2) AS records_per_second, "
        "round(avg(false_links_per_1000), 3) AS false_links_per_1000, round(avg(review_rate) * 100, 2) AS review_rate_pct "
        "FROM platform_stats_daily WHERE day BETWEEN %(start)s AND %(end)s GROUP BY 1 ORDER BY 1",
        _p(win, g)).fetchall()

    fl = _false_links(conn, win)
    return plain({
        "window": {"from": win.start, "to": win.end}, "granularity": g,
        "demo_data": use_stats, "series_source": "portfolio_stats_daily" if use_stats else "live",
        "resolution_status": {r["status"]: r["n"] for r in status},
        "reviews": {r["status"]: r["n"] for r in reviews},
        "auto_resolution_rate": auto / total,
        "median_review_minutes": decided["median_min"],
        "reviewer_correction_rate_pct": round(100 * decided["changed"] / decided["decided"], 2)
        if decided["decided"] else None,
        "false_links": fl,
        "resolution_quality": [dict(r) for r in quality_rows],
        "review_workload": [dict(r) for r in workload],
        "hybrid_vs_baselines": read_eval_metrics(metrics_path),
        "latency_throughput": [dict(r) for r in latency],
        "routing": routing(conn),
        "data_freshness": freshness_rows(conn),
        "notes": ["Latency and throughput are platform-wide demo statistics.",
                  "False links per 1,000 uses wrong-link corrections filed by reviewers, so it "
                  "undercounts links nobody noticed."],
    })


# ----------------------------------------------------------------------------------------- usage
def usage(conn: Any, win: Window, g: str, compare: bool) -> dict[str, Any]:
    def series(w: Window) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT date_trunc(%(g)s, day)::date AS period, max(monitored_suppliers) AS monitored_suppliers, "
            "sum(resolutions) AS resolutions, sum(events_matched) AS events_matched, sum(alerts) AS alerts, "
            "sum(api_calls) AS api_calls FROM usage_daily WHERE day BETWEEN %(start)s AND %(end)s "
            "GROUP BY 1 ORDER BY 1", _p(w, g)).fetchall()
        return [dict(r) for r in rows]

    def totals(w: Window) -> dict[str, Any]:
        r = conn.execute("SELECT coalesce(sum(resolutions), 0) AS resolutions, "
                         "coalesce(sum(events_matched), 0) AS events_matched, coalesce(sum(alerts), 0) AS alerts, "
                         "coalesce(sum(api_calls), 0) AS api_calls FROM usage_daily "
                         "WHERE day BETWEEN %s AND %s", (w.start, w.end)).fetchone()
        return {k: int(v) for k, v in dict(r).items()}

    cur = totals(win)
    prev = totals(win.previous()) if compare else None
    return plain({
        "demo_data": True, "window": {"from": win.start, "to": win.end}, "granularity": g,
        "items": series(win), "totals": cur,
        "comparison": None if prev is None else {
            "window": {"from": win.previous().start, "to": win.previous().end}, "totals": prev,
            "change_pct": {k: change(cur[k], prev[k]) for k in cur}},
    })

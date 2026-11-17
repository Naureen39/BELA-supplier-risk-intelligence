"""Phase 7: demo business data, revenue metrics, forecast, tenant analytics, cache, and export."""

from __future__ import annotations

import csv
import json
import random
import time
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from app.analytics import revenue as rv
from app.analytics.common import add_months
from app.analytics.forecast import forecast_mrr
from app.analytics.loader import load_business_data
from app.container import Container
from app.core.errors import ApiError
from app.core.mailer import MemoryMailer
from app.core.ratelimit import MemoryRateLimiter
from app.db import Database
from app.events_bus import MemoryBroker
from conftest import PASSWORD, Api, World, _admin, _seed
from conftest import test_settings as make_settings

from data.scripts import generate_demo_business_data as gen
from data.scripts import generate_demo_portfolios as portfolios


# ---------------------------------------------------------------------------- fixtures
def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def mrr_python(subs: list[dict[str, str]], month_end: date) -> dict[str, float]:
    """Monthly recurring revenue per tenant at `month_end`, straight from the CSV rules."""
    out: dict[str, float] = defaultdict(float)
    for s in subs:
        start = date.fromisoformat(s["start"])
        end = date.fromisoformat(s["end"]) if s["end"] else None
        if start <= month_end and (end is None or end > month_end):
            price = float(s["price"])
            out[s["tenant_id"]] += round(price / 12, 2) if s["billing_cycle"] == "annual" else price
    return dict(out)


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("synthetic")
    gen.generate(out)
    return out


@pytest.fixture(scope="module")
def demo(template_db: str, synthetic: Path, tmp_path_factory: pytest.TempPathFactory) -> Any:
    admin = _admin()
    name = f"d_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template_db}"')
    url = admin.rsplit("/", 1)[0] + f"/{name}"
    metrics = tmp_path_factory.mktemp("eval") / "metrics.json"
    metrics.write_text(json.dumps({"data": "synthetic split", "n": 100, "config_status": "provisional",
                                   "systems": {"fuzzy": {"false_links_per_1000": 40.0, "accuracy@1": 0.7},
                                               "hybrid": {"false_links_per_1000": 9.0, "accuracy@1": 0.9},
                                               "broken": {"false_links_per_1000": float("nan")}}}))
    container = Container.build(make_settings(url, eval_metrics_path=str(metrics)), Database(url, max_size=6),
                                MemoryMailer(), MemoryRateLimiter(), MemoryBroker())
    with container.db.system() as conn:
        load_business_data(conn, synthetic)
        rv.refresh_views(conn)
    world = _seed(container, container.mailer)  # type: ignore[arg-type]
    tenants = _read(synthetic / "tenants.csv")
    demo_tenant = next(t for t in tenants if not t["churned_at"])
    with container.db.system() as conn:
        conn.execute("INSERT INTO users (tenant_id, email, password_hash, role) VALUES (%s,%s,%s,'manager')",
                     (demo_tenant["id"], world.email("demo", "manager"), container.passwords.hash(PASSWORD)))
    world.demo_tenant = demo_tenant["id"]  # type: ignore[attr-defined]
    yield world
    container.db.close()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.fixture()
def fin(demo: World) -> Api:
    demo.container.cache.invalidate()
    return Api(demo).as_role("platform", "finance_analyst")


@pytest.fixture()
def mgr(demo: World) -> Api:
    demo.container.cache.invalidate()
    api = Api(demo)
    r = api.login("demo", "manager")
    assert r.status_code == 200, r.text
    return api


# ---------------------------------------------------------------------------- generator
def test_generator_is_deterministic(synthetic: Path, tmp_path: Path) -> None:
    gen.generate(tmp_path)
    names = sorted(p.name for p in synthetic.glob("*.csv"))
    assert names == sorted(p.name for p in tmp_path.glob("*.csv")) and len(names) == 10
    for n in names:
        assert (synthetic / n).read_bytes() == (tmp_path / n).read_bytes(), n


def test_generated_data_meets_acceptance_rules(synthetic: Path) -> None:
    tenants, subs = _read(synthetic / "tenants.csv"), _read(synthetic / "subscriptions.csv")
    assert len({t["name"] for t in tenants}) == len(tenants)  # unique, fictional word pairs
    series = []
    for month in gen._months(gen.START, gen.END):
        series.append(sum(mrr_python(subs, gen.month_end(month)).values()))
    assert all(v >= 0 for v in series) and series[-1] > 0
    assert all(abs(b - a) / a < 0.35 for a, b in zip(series[6:], series[7:], strict=False))  # continuous
    arr = series[-1] * 12
    assert 5_000_000 <= arr <= 9_000_000, arr  # plan envelope
    # invoice totals reconcile to subscriptions plus overage
    lines = defaultdict(list)
    for ln in _read(synthetic / "invoice_lines.csv"):
        lines[(ln["tenant_id"], ln["period_month"])].append(ln)
    checked = 0
    for inv in _read(synthetic / "invoices.csv"):
        items = lines[(inv["tenant_id"], inv["period_month"])]
        assert float(inv["total"]) == pytest.approx(sum(float(i["amount"]) for i in items), abs=0.005)
        month_end = gen.month_end(date.fromisoformat(inv["period_month"]))
        sub_line = sum(float(i["amount"]) for i in items if i["line_type"] == "subscription")
        assert sub_line == pytest.approx(mrr_python(subs, month_end)[inv["tenant_id"]], abs=0.005)
        checked += 1
    assert checked > 1000
    assert {r["status"] for r in _read(synthetic / "invoices.csv")} == {"paid", "open", "overdue"}
    # the one-time price increase for new customers at month 20
    starter = [float(s["price"]) for s in subs if s["plan"] == "starter" and s["change_reason"] == "new"
               and s["billing_cycle"] == "monthly"]
    assert min(starter) == 499.0 and max(starter) == pytest.approx(548.9)


def test_portfolio_generator_degrades_names_and_keeps_answers(tmp_path: Path) -> None:
    rng = random.Random(1)
    first = ("Amber", "Birch", "Cedar", "Delta", "Ember", "Flint", "Grove", "Harbor", "Iron", "Jade")
    second = ("Works", "Foods", "Steel", "Motors", "Labs", "Energy", "Plastics", "Textiles")
    catalog = [{"company_id": i, "name": f"{rng.choice(first)} {rng.choice(second)} {i} Inc",
                "state": rng.choice(["OH", "TX", "PA", None]), "city": "Springfield"} for i in range(1, 501)]
    files = portfolios.generate(catalog, count=2, out_dir=tmp_path)
    again = portfolios.generate(catalog, count=2, out_dir=tmp_path / "again")
    for a, b in zip(files, again, strict=True):
        assert a.read_bytes() == b.read_bytes()
        rows = _read(a)
        answers = _read(a.with_name(a.stem + "_answers.csv"))
        assert 150 <= len(rows) <= 420 and len(rows) == len(answers)
        truth = {int(r["company_id"]): r["true_name"] for r in answers}
        changed = sum(1 for r, ans in zip(rows, answers, strict=True) if r["supplier_name"] != ans["true_name"])
        assert changed > len(rows) * 0.5  # most names are degraded
        assert sum(1 for r in rows if not r["state"]) > 0 and len(truth) < len(rows) + 1
        assert any("duplicate" in ans["operations"] for ans in answers)


# ---------------------------------------------------------------------------- loader and views
def test_loader_counts_and_reconciliation(demo: World, synthetic: Path) -> None:
    subs = _read(synthetic / "subscriptions.csv")
    with demo.container.db.system() as conn:
        for table, fname in (("tenants", "tenants"), ("subscriptions", "subscriptions"),
                             ("invoices", "invoices"), ("invoice_lines", "invoice_lines"),
                             ("usage_daily", "usage_daily"), ("portfolio_stats_daily", "portfolio_stats_daily")):
            n = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            expected = len(_read(synthetic / f"{fname}.csv")) + (2 if table == "tenants" else 0)
            assert n == expected, table  # two seeded test tenants
        rows = conn.execute(
            "SELECT month_start, sum(new_mrr + expansion_mrr - contraction_mrr - churn_mrr) AS net, "
            "sum(mrr) AS mrr, sum(prev_mrr) AS prev FROM mrr_movements GROUP BY 1 ORDER BY 1").fetchall()
        assert len(rows) == 36
        for a, b in zip(rows, rows[1:], strict=False):
            assert a["net"] == a["mrr"] - a["prev"]  # movements sum to the MRR delta, exactly
            assert b["prev"] == a["mrr"]  # and each month starts where the last one ended
        for r in rows:
            expected = sum(mrr_python(subs, rv_month_end(r["month_start"])).values())
            assert float(r["mrr"]) == pytest.approx(expected, abs=0.01)  # SQL matches the CSV rules


def rv_month_end(d: date) -> date:
    return add_months(d, 1) - timedelta(days=1)


def test_views_fast_path_equals_live_queries(demo: World) -> None:
    with demo.container.db.system() as conn:
        f = rv.Filters()
        month = date(2026, 10, 1)
        for dim in rv.DIMENSIONS:
            assert rv.breakdown(conn, dim, month, f) == rv.breakdown(conn, dim, month, f, live=True), dim
        fast, live = rv.cohorts(conn, f), rv.cohorts(conn, f, live=True)
        key = lambda r: (r["cohort_month"], r["months_since_signup"])  # noqa: E731
        assert [(key(r), r["retention_pct"]) for r in fast] == [(key(r), r["retention_pct"]) for r in live]
        assert fast and all(r["retention_pct"] == 100 for r in fast if r["months_since_signup"] == 0)


def test_tenant_role_cannot_read_platform_revenue_tables(demo: World) -> None:
    for table in ("mrr_monthly", "mrr_movements", "cohort_retention", "revenue_by_dimension",
                  "marketing_spend", "business_events"):
        with demo.container.db.tenant(demo.tenant_a) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1")


# ---------------------------------------------------------------------------- revenue API
def test_kpis_follow_the_definitions(fin: Api, demo: World, synthetic: Path) -> None:
    subs = _read(synthetic / "subscriptions.csv")
    r = fin.get("/platform/revenue/kpis?from=2026-05-01&to=2026-10-31&compare=true")
    assert r.status_code == 200 and r.headers["X-Cache"] == "miss"
    body = r.json()
    assert body["demo_data"] is True and body["month"] == "2026-10-01" and body["compare_month"] == "2026-04-01"
    k = {i["key"]: i for i in body["items"]}
    mrr, customers = k["mrr"]["value"], k["customers"]["value"]
    assert mrr == pytest.approx(sum(mrr_python(subs, date(2026, 10, 31)).values()), abs=0.01)
    assert k["arr"]["value"] == pytest.approx(12 * mrr) and k["arpa"]["value"] == pytest.approx(mrr / customers)
    assert len(k["mrr"]["sparkline"]) == 6 and k["mrr"]["change_pct"] is not None
    # revenue retention over 12 months, recomputed from the CSV rules
    base, now = mrr_python(subs, date(2025, 10, 31)), mrr_python(subs, date(2026, 10, 31))
    assert k["nrr_pct"]["value"] == pytest.approx(100 * sum(now.get(t, 0) for t in base) / sum(base.values()), abs=0.01)
    assert k["grr_pct"]["value"] == pytest.approx(
        100 * sum(min(now.get(t, 0), v) for t, v in base.items()) / sum(base.values()), abs=0.01)
    assert 0 < k["grr_pct"]["value"] <= k["nrr_pct"]["value"] + 1e-9 and k["grr_pct"]["value"] <= 100
    # quick ratio over the trailing three months matches the movements endpoint
    mv = fin.get("/platform/revenue/movements?from=2026-08-01&to=2026-10-31").json()["items"]
    gain = sum(m["new_mrr"] + m["expansion_mrr"] for m in mv)
    loss = sum(m["contraction_mrr"] + m["churn_mrr"] for m in mv)
    assert k["quick_ratio"]["value"] == pytest.approx(gain / loss, rel=1e-6)
    assert k["cac_payback_months"]["value"] > 0 and body["gross_margin_assumption"] == 0.8
    assert fin.get("/platform/revenue/kpis?from=2026-05-01&to=2026-10-31&compare=true").headers["X-Cache"] == "hit"


def test_movements_reconcile_through_the_api(fin: Api) -> None:
    items = fin.get("/platform/revenue/movements").json()["items"]
    assert len(items) == 36
    for m in items:
        net = m["new_mrr"] + m["expansion_mrr"] - m["contraction_mrr"] - m["churn_mrr"]
        assert m["net_new_mrr"] == pytest.approx(net, abs=0.01)
        assert m["end_mrr"] - m["start_mrr"] == pytest.approx(net, abs=0.01)
    for a, b in zip(items, items[1:], strict=False):
        assert b["start_mrr"] == pytest.approx(a["end_mrr"], abs=0.01)


def test_cross_filters_agree_with_the_breakdown(fin: Api) -> None:
    total = fin.get("/platform/revenue/kpis?to=2026-10-31").json()
    total_mrr = {i["key"]: i for i in total["items"]}["mrr"]["value"]
    parts = fin.get("/platform/revenue/breakdown?dimension=region&month=2026-10-01").json()["items"]
    assert sum(p["mrr"] for p in parts) == pytest.approx(total_mrr, abs=0.05)
    assert sum(p["share_pct"] for p in parts) == pytest.approx(100, abs=0.1)
    for p in parts:
        k = fin.get(f"/platform/revenue/kpis?to=2026-10-31&region={p['value']}").json()
        assert {i["key"]: i for i in k["items"]}["mrr"]["value"] == pytest.approx(p["mrr"], abs=0.05)
    by_plan = fin.get("/platform/revenue/mrr?plan=starter&from=2026-01-01").json()
    assert by_plan["items"] and {i["plan_code"] for i in by_plan["items"]} == {"starter"}
    assert by_plan["annotations"]  # business events for the chart
    filtered = fin.get("/platform/revenue/kpis?to=2026-10-31&plan=starter").json()
    assert {i["key"]: i for i in filtered["items"]}["cac_payback_months"]["value"] is None  # unfiltered only


def test_revenue_mix_keeps_overage_out_of_mrr(fin: Api) -> None:
    mix = fin.get("/platform/revenue/mix?from=2026-10-01&to=2026-10-31").json()["items"]
    mrr = {i["key"]: i for i in fin.get("/platform/revenue/kpis?to=2026-10-31").json()["items"]}["mrr"]["value"]
    assert len(mix) == 1 and mix[0]["subscription"] == pytest.approx(mrr, abs=0.05)
    assert mix[0]["overage"] >= 0 and mix[0]["credit"] <= 0


def test_unit_economics_and_concentration(fin: Api) -> None:
    ue = fin.get("/platform/revenue/unit-economics?from=2026-01-01&to=2026-10-31").json()
    last = ue["items"][-1]
    assert last["cac"] > 0 and last["ltv"] > 0 and last["ltv_to_cac"] == pytest.approx(last["ltv"] / last["cac"])
    assert last["cac_payback_months"] == pytest.approx(last["cac"] / (last["arpa"] * 0.8), rel=1e-6)
    conc = fin.get("/platform/revenue/concentration").json()
    shares = [i["share_pct"] for i in conc["items"]]
    assert len(shares) == 10 and shares == sorted(shares, reverse=True)
    assert conc["items"][-1]["cumulative_share_pct"] == pytest.approx(sum(shares), abs=0.1)
    assert conc["top_share_pct"] < 100 and conc["total_arr"] > 5_000_000


def test_forecast_is_labelled_and_backtested(fin: Api) -> None:
    f = fin.get("/platform/revenue/forecast").json()
    assert f["label"] == "Estimate" and f["interval_level_pct"] == 80 and f["history_months"] == 36
    assert len(f["forecast"]) == 6 and f["forecast"][0]["month_start"] == "2026-11-01"
    last = f["history"][-1]["mrr"]
    for p in f["forecast"]:
        assert p["lower"] <= p["mean"] <= p["upper"]
    assert f["forecast"][0]["mean"] == pytest.approx(last, rel=0.15)
    assert f["forecast"][-1]["mean"] > last * 0.9
    bt = f["backtest"]
    assert bt["months"] == 6 and 0 <= bt["mape_pct"] < 50 and 0 <= bt["interval_coverage_pct"] <= 100
    assert "not a commitment" in f["note"]
    assert fin.get("/platform/revenue/forecast?horizon=3").json()["forecast"].__len__() == 3
    assert fin.get("/platform/revenue/forecast?horizon=13").status_code == 422


def test_forecast_rejects_short_history_and_tracks_a_trend() -> None:
    with pytest.raises(ApiError):
        forecast_mrr([(date(2025, 1, 1), 100.0)] * 5)
    rng = random.Random(3)
    pts = [(add_months(date(2024, 1, 1), i), 1000 * 1.03 ** i + rng.gauss(0, 15)) for i in range(30)]
    out = forecast_mrr(pts)
    assert out["forecast"][0]["mean"] == pytest.approx(pts[-1][1] * 1.03, rel=0.1)
    assert out["forecast"][-1]["upper"] > out["forecast"][-1]["lower"]


def test_cohorts_billing_and_customers(fin: Api) -> None:
    cohorts = fin.get("/platform/revenue/cohorts").json()["items"]
    assert cohorts and all(0 <= c["retention_pct"] for c in cohorts)
    health = fin.get("/platform/revenue/billing-health").json()
    assert health["as_of"] == "2026-10-31"
    assert sum(b["amount"] for b in health["buckets"]) == pytest.approx(health["total_outstanding"], abs=0.05)
    assert {i["status"] for i in health["items"]} <= {"open", "overdue"}
    table = fin.get("/platform/revenue/customers?limit=10").json()
    customers = {i["key"]: i for i in fin.get("/platform/revenue/kpis").json()["items"]}["customers"]["value"]
    assert table["total"] == customers and len(table["items"]) == 10
    mrrs = [r["mrr"] for r in table["items"]]
    assert mrrs == sorted(mrrs, reverse=True)
    assert {r["health"] for r in table["items"]} <= {"healthy", "declining", "overdue", "over_limit"}
    assert len(table["items"][0]["mrr_trend"]) >= 1
    names = [r["name"] for r in fin.get("/platform/revenue/customers?sort=name&order=asc&limit=5").json()["items"]]
    assert names == sorted(names)
    page2 = fin.get("/platform/revenue/customers?limit=10&offset=10").json()["items"]
    assert not {r["id"] for r in page2} & {r["id"] for r in table["items"]}
    churned = fin.get("/platform/revenue/customers?status=churned&limit=5").json()
    assert churned["total"] > 0 and all(r["health"] == "churned" for r in churned["items"])
    detail = fin.get(f"/platform/revenue/customers/{table['items'][0]['id']}").json()
    assert detail["subscriptions"] and detail["invoices"] and detail["usage"] and detail["mrr_history"]
    assert fin.get(f"/platform/revenue/customers/{uuid.uuid4()}").status_code == 404
    assert fin.get("/platform/revenue/customers/not-a-uuid").status_code == 404


def test_revenue_csv_cache_refresh_and_permissions(fin: Api, demo: World) -> None:
    r = fin.get("/platform/revenue/mrr?format=csv&from=2026-09-01")
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0] == "month_start,plan_code,mrr,customers" and len(lines) > 2
    assert fin.get("/platform/revenue/mrr?granularity=week").status_code == 422
    assert fin.get("/platform/revenue/mrr?from=2026-05-01&to=2026-01-01").status_code == 422
    assert fin.get("/platform/revenue/kpis").headers["X-Cache"] == "miss"
    assert fin.get("/platform/revenue/kpis").headers["X-Cache"] == "hit"
    refreshed = fin.post("/platform/revenue/refresh")
    assert refreshed.status_code == 200 and refreshed.json()["refreshed"]["mrr_movements"] > 0
    assert fin.get("/platform/revenue/kpis").headers["X-Cache"] == "miss"  # the refresh dropped the cache
    assert fin.get("/platform/revenue/summary").json()["customers"] > 100
    for role in ("manager", "analyst", "viewer", "tenant_admin"):
        other = Api(demo).as_role("a", role)
        assert other.get("/platform/revenue/kpis").status_code == 403, role
        assert other.post("/platform/revenue/refresh").status_code == 403


def test_revenue_endpoints_answer_under_500_ms_on_seeded_data(fin: Api, demo: World) -> None:
    paths = ["/kpis?compare=true", "/mrr", "/movements", "/mix", "/cohorts", "/breakdown?dimension=industry",
             "/concentration", "/unit-economics", "/billing-health", "/customers", "/forecast",
             "/kpis?region=EMEA&plan=professional"]
    slowest = 0.0
    for path in paths:
        demo.container.cache.invalidate()
        started = time.perf_counter()
        r = fin.get(f"/platform/revenue{path}")
        elapsed = time.perf_counter() - started
        assert r.status_code == 200 and r.headers["X-Cache"] == "miss", path
        slowest = max(slowest, elapsed)
        assert elapsed < 0.5, f"{path} took {elapsed:.3f}s"
    print(f"slowest cold revenue endpoint: {slowest * 1000:.0f} ms")


# ---------------------------------------------------------------------------- tenant analytics
def test_usage_series_totals_and_isolation(mgr: Api, demo: World) -> None:
    r = mgr.get("/analytics/usage?from=2026-10-01&to=2026-10-31&granularity=week&compare=true")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_data"] is True and len(body["items"]) == 5  # Monday-based weeks
    with demo.container.db.system() as conn:
        own = conn.execute("SELECT sum(api_calls) AS n FROM usage_daily WHERE tenant_id = %s AND "
                           "day BETWEEN '2026-10-01' AND '2026-10-31'", (demo.demo_tenant,)).fetchone()["n"]  # type: ignore[attr-defined]
        everyone = conn.execute("SELECT sum(api_calls) AS n FROM usage_daily WHERE day BETWEEN "
                                "'2026-10-01' AND '2026-10-31'").fetchone()["n"]
    assert body["totals"]["api_calls"] == own and own < everyone  # row level security
    assert sum(i["api_calls"] for i in body["items"]) == own
    assert body["comparison"]["window"]["to"] == "2026-09-30"
    assert set(body["comparison"]["change_pct"]) == {"resolutions", "events_matched", "alerts", "api_calls"}
    daily = mgr.get("/analytics/usage?from=2026-10-01&to=2026-10-31").json()["items"]
    assert len(daily) == 31
    other = Api(demo).as_role("a", "manager").get("/analytics/usage?from=2026-10-01&to=2026-10-31").json()
    assert other["items"] == [] and other["totals"]["api_calls"] == 0
    csv_resp = mgr.get("/analytics/usage?from=2026-10-01&to=2026-10-07&format=csv")
    assert csv_resp.text.splitlines()[0].startswith("period,monitored_suppliers") and len(csv_resp.text.splitlines()) == 8


def test_portfolio_analytics_from_daily_stats(mgr: Api, demo: World) -> None:
    r = mgr.get("/analytics/portfolio?from=2026-07-01&to=2026-10-31&granularity=month&compare=true")
    assert r.status_code == 200 and r.headers["X-Cache"] == "miss"
    b = r.json()
    assert b["series_source"] == "portfolio_stats_daily" and b["demo_data"] is True
    assert [i["period"] for i in b["risk_index_trend"]["items"]] == ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"]
    assert b["risk_index_trend"]["bands"] == {"medium": 30, "high": 50, "critical": 70}
    k = {i["key"]: i for i in b["kpis"]}
    assert set(k) == {"risk_index", "high_critical_suppliers", "events_in_period", "auto_resolution_rate",
                      "review_queue_size", "median_review_minutes", "false_links_per_1000"}
    with demo.container.db.system() as conn:
        last = conn.execute("SELECT * FROM portfolio_stats_daily WHERE tenant_id = %s AND day = '2026-10-31'",
                            (demo.demo_tenant,)).fetchone()  # type: ignore[attr-defined]
        prev = conn.execute("SELECT risk_index FROM portfolio_stats_daily WHERE tenant_id = %s AND day = '2026-06-30'",
                            (demo.demo_tenant,)).fetchone()  # type: ignore[attr-defined]
    assert k["risk_index"]["value"] == float(last["risk_index"])
    assert k["high_critical_suppliers"]["value"] == last["suppliers_by_level"]["high"] + last["suppliers_by_level"]["critical"]
    total = last["auto_resolved"] + last["reviewed"] + last["unresolved"]
    assert k["auto_resolution_rate"]["value"] == pytest.approx(100 * last["auto_resolved"] / total)
    assert k["risk_index"]["previous"] == float(prev["risk_index"])
    assert b["disclaimer"].endswith("not statements of fault.")
    assert mgr.get("/analytics/portfolio?from=2026-07-01&to=2026-10-31&granularity=month&compare=true").headers["X-Cache"] == "hit"
    assert mgr.get("/analytics/portfolio?format=csv").status_code == 422
    one = mgr.get("/analytics/portfolio?from=2026-07-01&to=2026-10-31&format=csv&section=risk_index_trend")
    assert one.text.splitlines()[0] == "period,risk_index" and len(one.text.splitlines()) > 2
    assert mgr.get("/analytics/portfolio?from=2026-10-31&to=2026-01-01").status_code == 422
    assert mgr.get("/analytics/portfolio?granularity=year").status_code == 422


def test_quality_analytics(mgr: Api) -> None:
    b = mgr.get("/analytics/quality?from=2026-01-01&to=2026-10-31&granularity=month").json()
    assert b["series_source"] == "portfolio_stats_daily"
    lat = b["latency_throughput"]
    assert len(lat) == 10 and all(r["p95_ms"] > r["p50_ms"] > 0 and r["records_per_second"] > 0 for r in lat)
    assert all(r["auto_resolved"] + r["reviewed"] + r["unresolved"] > 0 for r in b["resolution_quality"])
    assert b["review_workload"] and b["data_freshness"] == [] and b["routing"]["links"] == []
    hv = b["hybrid_vs_baselines"]
    assert hv["config_status"] == "provisional"
    by = {s["system"]: s["false_links_per_1000"] for s in hv["systems"]}
    assert by["fuzzy"] == 40.0 and by["hybrid"] == 9.0 and by["broken"] is None  # NaN is not served
    csv_resp = mgr.get("/analytics/quality?from=2026-01-01&to=2026-10-31&format=csv&section=latency_throughput")
    assert csv_resp.text.splitlines()[0].startswith("period,p50_ms,p95_ms")
    assert mgr.get("/analytics/quality?format=csv&section=nope").status_code == 422


def test_quality_routing_and_freshness_from_live_tables(world: World) -> None:
    from conftest import seed_catalog, seed_event

    ids = seed_catalog(world)
    seed_event(world, ids["Harborline Foods, Inc.|OH"])
    mgr = Api(world).as_role("a", "manager")
    mgr.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"})
    b = mgr.get("/analytics/quality").json()
    assert b["series_source"] == "live" and b["routing"]["total"] == 1
    assert sum(link["value"] for link in b["routing"]["links"] if link["source"] == "Records") == 1
    fresh = b["data_freshness"]
    assert fresh[0]["source"] == "osha" and fresh[0]["status"] == "fresh" and fresh[0]["records"] == 1
    p = mgr.get("/analytics/portfolio").json()
    assert p["series_source"] == "live" and p["demo_data"] is False
    assert {i["key"]: i for i in p["kpis"]}["events_in_period"]["value"] == 1
    assert p["event_source_mix"] == [{"source_class": "regulator", "events": 1}]
    assert p["category_heatmap"][0]["event_type"] == "workplace_safety"
    assert mgr.get("/analytics/portfolio?source=news").json()["totals"]["events_by_type"] == {}
    assert mgr.get("/analytics/portfolio?source=osha").json()["totals"]["events_by_type"] == {"workplace_safety": 1}
    assert mgr.get("/analytics/portfolio?source=regulator").headers["X-Cache"] == "miss"


def test_decimal_values_are_plain_json() -> None:
    from app.analytics.common import plain

    out = plain({"a": Decimal("1.50"), "d": date(2026, 1, 1), "n": [Decimal("2")]})
    assert out == {"a": 1.5, "d": "2026-01-01", "n": [2.0]}


# ---------------------------------------------------------------------------- cache and migration
def test_memory_cache_expires_and_evicts() -> None:
    from app.core.cache import MemoryCache, cached

    cache = MemoryCache(max_entries=2)
    cache.set("old", {"v": 1}, ttl=-1)
    assert cache.get("old") is None  # expired
    cache.set("a", [1], ttl=60)
    cache.set("b", [2], ttl=60)
    cache.set("c", [3], ttl=60)
    assert cache.get("c") == [3] and sum(cache.get(k) is not None for k in "abc") == 2
    cache.invalidate()
    assert cache.get("c") is None
    calls: list[int] = []
    assert cached(cache, "k", 60, lambda: calls.append(1) or {"x": 1}) == ({"x": 1}, False)
    assert cached(cache, "k", 60, lambda: calls.append(1) or {"x": 2}) == ({"x": 1}, True) and len(calls) == 1


def test_valkey_cache_round_trip_and_invalidation() -> None:
    import os

    from app.core.cache import ValkeyCache

    url = os.environ.get("VALKEY_URL")
    if not url:
        pytest.skip("VALKEY_URL is not set")
    cache = ValkeyCache(url)
    key = f"test:{uuid.uuid4().hex}"
    cache.set(key, {"a": [1, 2]}, ttl=60)
    assert cache.get(key) == {"a": [1, 2]}
    cache.invalidate()
    assert cache.get(key) is None
    dead = ValkeyCache("redis://127.0.0.1:1/0")  # an outage must not break an endpoint
    assert dead.get("x") is None
    dead.set("x", 1, 5)
    dead.invalidate()


def test_loader_names_missing_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="generate_demo_business_data"):
        load_business_data(None, tmp_path)


def test_analytics_migration_downgrades_and_upgrades(template_db: str) -> None:
    import os

    from alembic import command
    from alembic.config import Config

    admin = _admin()
    name = f"mig_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template_db}"')
    url = admin.rsplit("/", 1)[0] + f"/{name}"
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
        command.downgrade(cfg, "0005")
        with psycopg.connect(url) as conn:
            views = {r[0] for r in conn.execute("SELECT matviewname FROM pg_matviews")}
            assert views == {"mrr_monthly", "cohort_retention"}
        command.upgrade(cfg, "head")
        with psycopg.connect(url) as conn:
            views = {r[0] for r in conn.execute("SELECT matviewname FROM pg_matviews")}
            assert views == set(rv.VIEWS)
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s "
                         "AND pid <> pg_backend_pid()", (name,))
            conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')

"""Generate the synthetic business dataset (plan section 5.4). All figures are demo data.

Fixed seed (42), pure standard library, so two runs produce identical files. Output goes to
data/synthetic/*.csv. Tenant names are neutral word pairs plus generic suffixes and are fictional.

Files: plans, tenants, subscriptions, invoices, invoice_lines, usage_daily, portfolio_stats_daily,
platform_stats_daily, marketing_spend, business_events.

Simplifications (also stated in docs/metrics.md): annual customers are invoiced monthly at the
monthly equivalent; price changes apply on their change date; a tenant that churns in a month has
no invoice for that month because MRR is measured at month end.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import math
import random
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SEED = 42
START = date(2023, 11, 1)
END = date(2026, 10, 31)
OUT_DIR = Path(__file__).resolve().parents[1] / "synthetic"
NAMESPACE = uuid.UUID("5a0f2c1e-7b3d-4c2e-9d55-0a6b1f4e2c11")

# code: (name, list price per month, supplier limit, overage per 100 suppliers above the limit)
PLANS: dict[str, tuple[str, float, int, float]] = {
    "starter": ("Starter", 499.0, 250, 40.0),
    "professional": ("Professional", 1999.0, 2500, 120.0),
    "enterprise": ("Enterprise", 8000.0, 10000, 300.0),
}
PLAN_MIX = (("starter", 0.50), ("professional", 0.35), ("enterprise", 0.15))
MONTHLY_CHURN = {"starter": 0.030, "professional": 0.015, "enterprise": 0.006}
EXPANSION_P, CONTRACTION_P, UPGRADE_P = 0.04, 0.012, 0.012
ANNUAL_SHARE, ANNUAL_DISCOUNT = 0.40, 0.10
PRICE_INCREASE_MONTH = date(2025, 6, 1)  # month 20 of the history
PRICE_INCREASE = 1.10
REGIONS = (("North America", 0.60), ("EMEA", 0.25), ("APAC", 0.12), ("LATAM", 0.03))
COUNTRIES = {
    "North America": ("US", "US", "US", "CA"), "EMEA": ("GB", "DE", "FR", "NL", "SE"),
    "APAC": ("JP", "AU", "SG"), "LATAM": ("BR", "MX"),
}
INDUSTRIES = ("manufacturing", "automotive", "food and beverage", "consumer products",
              "healthcare and life sciences", "logistics", "insurance", "banking")
CHANNELS = (("paid_search", 0.25), ("content", 0.25), ("events", 0.20), ("partners", 0.15),
            ("outbound", 0.15))
BUSINESS_EVENTS = (
    (date(2024, 2, 15), "Product launch: supplier alerts"),
    (date(2024, 9, 1), "New data source: news monitoring"),
    (date(2025, 1, 15), "Latency optimization release"),
    (date(2025, 6, 1), "Pricing change: new customer list prices up 10 percent"),
    (date(2025, 10, 1), "New data source: FDA enforcement records"),
    (date(2026, 3, 1), "Product launch: corporate family graph"),
)
DATA_SOURCE_EVENTS = (date(2024, 9, 1), date(2025, 10, 1))
OPTIMIZATION_EVENT = date(2025, 1, 15)

_FIRST = ("Amber", "Birchwood", "Cobalt", "Dunmore", "Eastgate", "Fernhill", "Granite", "Harbor",
          "Ironwood", "Juniper", "Kestrel", "Larkspur", "Maple", "Northfield", "Oakridge",
          "Pinecrest", "Quartz", "Redwood", "Silverline", "Tidewater", "Umber", "Valley",
          "Westbrook", "Yarrow", "Zephyr", "Alder", "Brightwater", "Clearbrook", "Drift",
          "Elmstead", "Foxglove", "Greystone")
_SECOND = ("Meadow", "Summit", "Harvest", "Anchor", "Beacon", "Canyon", "Delta", "Ember",
           "Forge", "Grove", "Haven", "Island", "Junction", "Keystone", "Lantern", "Mesa",
           "Orchard", "Prairie", "Ridge", "Stream", "Terrace", "Union", "Vista", "Willow")
_SUFFIX = ("Partners", "Holdings", "Group", "Works", "Supply", "Systems", "Brands", "Labs")


def _month_add(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _months(first: date, last: date) -> list[date]:
    out, cur = [], first
    while cur <= last:
        out.append(cur)
        cur = _month_add(cur, 1)
    return out


def _pick(rng: random.Random, options: Sequence[tuple[str, float]]) -> str:
    x, acc = rng.random(), 0.0
    for key, weight in options:
        acc += weight
        if x < acc:
            return key
    return options[-1][0]


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _noisy(rng: random.Random, mean: float, spread: float = 0.2) -> int:
    return max(0, round(mean * (1 + spread * rng.gauss(0, 1))))


@dataclass
class Sub:
    plan: str
    cycle: str
    monthly: float  # monthly equivalent
    started: date
    ended: date | None = None
    reason: str = "new"

    @property
    def price(self) -> float:
        return round(self.monthly * 12, 2) if self.cycle == "annual" else self.monthly


@dataclass
class Tenant:
    id: str
    name: str
    industry: str
    region: str
    country: str
    channel: str
    created: date
    churned: date | None = None
    subs: list[Sub] = field(default_factory=list)

    def active_sub(self, day: date) -> Sub | None:
        for s in self.subs:
            if s.started <= day and (s.ended is None or s.ended > day):
                return s
        return None


def _list_price(rng: random.Random, plan: str, signup: date) -> float:
    if plan == "enterprise":
        base = min(25000.0, max(8000.0, rng.lognormvariate(math.log(13000), 0.35)))
    else:
        base = PLANS[plan][1]
    if signup >= PRICE_INCREASE_MONTH:
        base *= PRICE_INCREASE
    return round(base, 2)


def _tenant_name(rng: random.Random, used: set[str]) -> str:
    for _ in range(1000):
        name = f"{rng.choice(_FIRST)} {rng.choice(_SECOND)} {rng.choice(_SUFFIX)}"
        if name not in used:
            used.add(name)
            return name
    name = f"{rng.choice(_FIRST)} {rng.choice(_SECOND)} {rng.choice(_SUFFIX)} {len(used)}"
    used.add(name)
    return name


def build_tenants(rng: random.Random, first: date = START, last: date = END) -> list[Tenant]:
    months = _months(first, last)
    tenants: list[Tenant] = []
    used: set[str] = set()
    span = max(len(months) - 1, 1)
    for mi, month in enumerate(months):
        for _ in range(_poisson(rng, 2.0 + 5.0 * mi / span)):
            signup = month + timedelta(days=rng.randint(0, 26))
            plan = _pick(rng, PLAN_MIX)
            cycle = "annual" if rng.random() < ANNUAL_SHARE else "monthly"
            monthly = _list_price(rng, plan, signup)
            if cycle == "annual":
                monthly = round(monthly * (1 - ANNUAL_DISCOUNT), 2)
            region = _pick(rng, REGIONS)
            t = Tenant(
                id=str(uuid.uuid5(NAMESPACE, f"tenant-{len(tenants)}")),
                name=_tenant_name(rng, used), industry=rng.choice(INDUSTRIES), region=region,
                country=rng.choice(COUNTRIES[region]), channel=_pick(rng, CHANNELS), created=signup)
            t.subs.append(Sub(plan, cycle, monthly, signup))
            tenants.append(t)
    for t in tenants:
        _evolve(rng, t, last)
    return tenants


def _evolve(rng: random.Random, t: Tenant, last: date) -> None:
    cur = t.subs[0]
    for month in _months(_month_add(t.created.replace(day=1), 1), last):
        tenure = (month.year - t.created.year) * 12 + month.month - t.created.month
        day = month + timedelta(days=rng.randint(0, 27))
        if tenure >= 2 and rng.random() < MONTHLY_CHURN[cur.plan]:
            cur.ended = day
            t.churned = day
            return
        r = rng.random()
        if r < EXPANSION_P:
            new = Sub(cur.plan, cur.cycle, round(cur.monthly * (1 + rng.uniform(0.10, 0.40)), 2),
                      day, None, "expansion")
        elif r < EXPANSION_P + CONTRACTION_P:
            new = Sub(cur.plan, cur.cycle, round(cur.monthly * (1 - rng.uniform(0.10, 0.25)), 2),
                      day, None, "contraction")
        elif cur.plan == "starter" and r < EXPANSION_P + CONTRACTION_P + UPGRADE_P:
            price = round(PLANS["professional"][1] * (1 - (ANNUAL_DISCOUNT if cur.cycle == "annual" else 0)), 2)
            new = Sub("professional", cur.cycle, price, day, None, "upgrade")
        else:
            continue
        cur.ended = day
        t.subs.append(new)
        cur = new


def _write(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow(row)
            n += 1
    return n


def _usage_levels(rng: random.Random, tenants: list[Tenant], last: date) -> dict[str, dict[date, int]]:
    """Monitored suppliers per tenant and month: grows about 2 percent a month, capped near the limit."""
    levels: dict[str, dict[date, int]] = {}
    for t in tenants:
        plan0 = t.subs[0].plan
        base = {"starter": rng.uniform(60, 220), "professional": rng.uniform(500, 2000),
                "enterprise": rng.uniform(2500, 9000)}[plan0]
        value, per_month = base, {}
        for month in _months(t.created.replace(day=1), last):
            sub = t.active_sub(month_end(month)) or t.subs[-1]
            value *= 1 + rng.gauss(0.02, 0.015)
            value = min(value, PLANS[sub.plan][2] * 1.3)
            per_month[month] = max(1, round(value))
        levels[t.id] = per_month
    return levels


def _weekday_factor(d: date) -> float:
    return 0.25 if d.weekday() >= 5 else 1.0


def _quarter_end_factor(d: date) -> float:
    return 1.6 if d.month in (3, 6, 9, 12) and d.day >= 20 else 1.0


def _source_lift(d: date) -> float:
    return 1.0 + 0.15 * sum(d >= e for e in DATA_SOURCE_EVENTS)


def generate(out_dir: Path = OUT_DIR, seed: int = SEED, first: date = START, last: date = END
             ) -> dict[str, int]:
    rng = random.Random(seed)  # nosec B311
    tenants = build_tenants(rng, first, last)
    counts: dict[str, int] = {}

    counts["plans"] = _write(out_dir / "plans.csv", ["code", "name", "monthly_price", "supplier_limit",
                                                    "overage_per_100"],
                             [[c, *v] for c, v in PLANS.items()])
    counts["tenants"] = _write(
        out_dir / "tenants.csv",
        ["id", "name", "industry", "region", "country", "created_at", "churned_at", "acquisition_channel"],
        [[t.id, t.name, t.industry, t.region, t.country, t.created.isoformat(),
          t.churned.isoformat() if t.churned else "", t.channel] for t in tenants])
    counts["subscriptions"] = _write(
        out_dir / "subscriptions.csv",
        ["tenant_id", "plan", "billing_cycle", "price", "start", "end", "change_reason"],
        [[t.id, s.plan, s.cycle, f"{s.price:.2f}", s.started.isoformat(),
          s.ended.isoformat() if s.ended else "", s.reason] for t in tenants for s in t.subs])

    levels = _usage_levels(rng, tenants, last)

    usage_rows: list[list[Any]] = []
    stats_rows: list[list[Any]] = []
    day_count = (last - first).days + 1
    for t in tenants:
        risk = rng.uniform(25, 55)
        base_risk = risk
        for i in range((last - t.created).days + 1):
            d = t.created + timedelta(days=i)
            if t.churned and d >= t.churned:
                break
            monitored = levels[t.id][d.replace(day=1)]
            scale = monitored / 100
            wd = _weekday_factor(d)
            lift = _source_lift(d)
            resolutions = _noisy(rng, scale * 3 * wd * _quarter_end_factor(d))
            matched = _noisy(rng, scale * 1.2 * wd * lift)
            usage_rows.append([t.id, d.isoformat(), monitored, resolutions, matched,
                               _noisy(rng, matched * 0.15 + 0.2), _noisy(rng, scale * 40 * wd)])

            risk += 0.1 * (base_risk - risk) + rng.gauss(0, 1.2)
            risk = min(95.0, max(2.0, risk))
            progress = (d - first).days / max(day_count - 1, 1)
            unresolved_share = 0.04
            reviewed_share = max(0.04, 0.24 - 0.14 * progress)
            reviewed = round(monitored * reviewed_share)
            unresolved = round(monitored * unresolved_share)
            auto = monitored - reviewed - unresolved
            weights = [max(0.02, 1 - risk / 60), 0.35, max(0.02, risk / 120), max(0.005, (risk - 30) / 400)]
            total_w = sum(weights)
            cnt = [int(monitored * w / total_w) for w in weights]
            cnt[0] += monitored - sum(cnt)
            review_minutes = round(max(8.0, 190 - 140 * progress + rng.gauss(0, 12)), 2) if reviewed else ""
            stats_rows.append([
                t.id, d.isoformat(), f"{risk:.2f}",
                f'{{"low": {cnt[0]}, "medium": {cnt[1]}, "high": {cnt[2]}, "critical": {cnt[3]}}}',
                auto, reviewed, unresolved, review_minutes])
    counts["usage_daily"] = _write(
        out_dir / "usage_daily.csv",
        ["tenant_id", "date", "monitored_suppliers", "resolutions", "events_matched", "alerts", "api_calls"],
        usage_rows)
    counts["portfolio_stats_daily"] = _write(
        out_dir / "portfolio_stats_daily.csv",
        ["tenant_id", "date", "risk_index", "suppliers_by_level", "auto_resolved", "reviewed",
         "unresolved", "median_review_minutes"], stats_rows)

    # ---- invoices
    invoices: list[list[Any]] = []
    lines: list[list[Any]] = []
    horizon = last
    for t in tenants:
        for month in _months(t.created.replace(day=1), last):
            issued = month_end(month)
            sub = t.active_sub(issued)
            if sub is None:
                continue
            monitored = levels[t.id].get(month, 0)
            limit, over_rate = PLANS[sub.plan][2], PLANS[sub.plan][3]
            items: list[tuple[str, str, float]] = [
                ("subscription", f"{PLANS[sub.plan][0]} plan, {month:%B %Y}", sub.monthly)]
            excess = monitored - limit
            if excess > 0:
                blocks = math.ceil(excess / 100)
                items.append(("overage", f"{blocks} x 100 suppliers above the plan limit",
                              round(blocks * over_rate, 2)))
            if rng.random() < 0.02:
                items.append(("credit", "Service credit", -round(sub.monthly * 0.10, 2)))
            due = issued + timedelta(days=30)
            if due <= horizon:
                status = "paid" if rng.random() < 0.95 else "overdue"
            else:
                status = "paid" if rng.random() < 0.15 else "open"
            total = round(sum(a for _, _, a in items), 2)
            invoices.append([t.id, month.isoformat(), issued.isoformat(), due.isoformat(), status,
                             f"{total:.2f}"])
            lines.extend([t.id, month.isoformat(), kind, desc, f"{amt:.2f}"] for kind, desc, amt in items)
    counts["invoices"] = _write(out_dir / "invoices.csv",
                                ["tenant_id", "period_month", "issued_on", "due_on", "status", "total"],
                                invoices)
    counts["invoice_lines"] = _write(
        out_dir / "invoice_lines.csv",
        ["tenant_id", "period_month", "line_type", "description", "amount"], lines)

    # ---- marketing spend: tracks new logos with a roughly constant blended CAC
    new_by_month: dict[date, int] = defaultdict(int)
    for t in tenants:
        new_by_month[t.created.replace(day=1)] += 1
    spend_rows = []
    for month in _months(first, last):
        total = 8000 + new_by_month[month] * 24000 * (1 + 0.2 * rng.gauss(0, 1))
        total = max(4000.0, total)
        for ch, share in CHANNELS:
            spend_rows.append([month.isoformat(), ch, f"{total * share * (1 + 0.1 * rng.gauss(0, 1)):.2f}"])
    counts["marketing_spend"] = _write(out_dir / "marketing_spend.csv", ["month", "channel", "spend"],
                                       spend_rows)

    # ---- platform quality statistics
    plat = []
    for i in range(day_count):
        d = first + timedelta(days=i)
        progress = i / max(day_count - 1, 1)
        opt = 0.7 if d >= OPTIMIZATION_EVENT else 1.0
        p50 = max(80.0, (420 - 90 * progress + rng.gauss(0, 12)) * opt)
        p95 = p50 * (2.6 + rng.gauss(0, 0.12))
        false_links = max(0.5, 14 * math.exp(-1.4 * progress) + 2.0 + rng.gauss(0, 0.4))
        review_rate = min(0.5, max(0.03, 0.22 - 0.13 * progress + rng.gauss(0, 0.006)))
        throughput = (40 + 45 * progress) / opt * (1 + 0.05 * rng.gauss(0, 1))
        plat.append([d.isoformat(), f"{p50:.2f}", f"{p95:.2f}", f"{false_links:.3f}",
                     f"{review_rate:.4f}", f"{throughput:.2f}"])
    counts["platform_stats_daily"] = _write(
        out_dir / "platform_stats_daily.csv",
        ["date", "p50_latency_ms", "p95_latency_ms", "false_links_per_1000", "review_rate",
         "throughput_rps"], plat)
    counts["business_events"] = _write(out_dir / "business_events.csv", ["date", "label"],
                                       [[d.isoformat(), label] for d, label in BUSINESS_EVENTS
                                        if first <= d <= last])
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    for name, n in generate(args.out, args.seed).items():
        print(f"{name}: {n} rows")


if __name__ == "__main__":
    main()

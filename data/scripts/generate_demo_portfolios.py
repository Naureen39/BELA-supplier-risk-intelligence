"""Generate demo supplier portfolios degraded the way ERP exports are (plan section 5.4).

Each portfolio has 150 to 400 suppliers sampled from a canonical company list (real public company
and facility operator names when the catalog comes from the database), then degraded: suffix
variants, abbreviations, typos, missing states, duplicate rows, and plant-level names. The true
mapping goes to a separate `*_answers.csv`, used only by tests and evaluation, never by the app.

Catalog sources:
    --from-db            read companies and one facility location each (DATABASE_URL)
    --catalog FILE.csv   columns: company_id, name, state, city (state and city may be empty)

Usage:
    PYTHONPATH=.:apps/api python -m data.scripts.generate_demo_portfolios --from-db --count 5
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
from pathlib import Path
from typing import Any

from app.resolution.perturb import perturb_name, plant_suffix

SEED = 42
OUT_DIR = Path(__file__).resolve().parents[1] / "synthetic" / "portfolios"
MIN_SIZE, MAX_SIZE = 150, 400
TIERS = (("tier_1", 0.15), ("tier_2", 0.35), ("tier_3", 0.50))
HEADER = ["supplier_name", "city", "state", "country", "annual_spend_usd", "tier"]


def load_catalog_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{"company_id": int(r["company_id"]), "name": r["name"].strip(),
                 "state": (r.get("state") or "").strip() or None, "city": (r.get("city") or "").strip() or None}
                for r in csv.DictReader(fh) if r.get("name", "").strip()]


def load_catalog_db(url: str) -> list[dict[str, Any]]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT c.id AS company_id, c.canonical_name AS name, f.state, f.city FROM companies c "
            "LEFT JOIN LATERAL (SELECT state, city FROM facilities WHERE company_id = c.id "
            "ORDER BY id LIMIT 1) f ON true ORDER BY c.id").fetchall()
    return [dict(r) for r in rows]


def _tier(rng: random.Random) -> str:
    x, acc = rng.random(), 0.0
    for tier, w in TIERS:
        acc += w
        if x < acc:
            return tier
    return TIERS[-1][0]


def build_portfolio(catalog: list[dict[str, Any]], rng: random.Random, size: int | None = None
                    ) -> tuple[list[list[Any]], list[list[Any]]]:
    """Return (rows, answers). `answers` rows: row number, company_id, true name, operations."""
    size = min(size or rng.randint(MIN_SIZE, MAX_SIZE), len(catalog))
    chosen = rng.sample(catalog, size)
    rows: list[list[Any]] = []
    answers: list[list[Any]] = []

    def emit(co: dict[str, Any], dup: bool = False) -> None:
        state = co["state"]
        r = rng.random()
        if r < 0.12:
            name, ops = plant_suffix(co["name"], rng, state), ["plant_suffix"]
        elif r < 0.85:
            name, ops = perturb_name(co["name"], rng, state)
        else:
            name, ops = co["name"], []
        shown_state = None if rng.random() < 0.10 else state
        shown_city = co["city"] if rng.random() < 0.70 else None
        rows.append([name, shown_city or "", shown_state or "", "US",
                     round(math.exp(rng.gauss(12.5, 1.4)), 2), _tier(rng)])
        answers.append([len(rows), co["company_id"], co["name"], "+".join(ops) + ("+duplicate" if dup else "")])

    for co in chosen:
        emit(co)
        if rng.random() < 0.05:
            emit(co, dup=True)
    order = list(range(len(rows)))
    rng.shuffle(order)
    shuffled_rows = [rows[i] for i in order]
    # Row numbers in the answers follow the shuffled order.
    new_answers = [[pos + 1, answers[i][1], answers[i][2], answers[i][3]] for pos, i in enumerate(order)]
    return shuffled_rows, new_answers


def generate(catalog: list[dict[str, Any]], count: int = 5, out_dir: Path = OUT_DIR, seed: int = SEED,
             size: int | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for i in range(1, count + 1):
        rng = random.Random(seed * 1000 + i)
        rows, answers = build_portfolio(catalog, rng, size)
        path = out_dir / f"portfolio_{i:02d}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(HEADER)
            w.writerows(rows)
        with (out_dir / f"portfolio_{i:02d}_answers.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["row", "company_id", "true_name", "operations"])
            w.writerows(answers)
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-db", action="store_true")
    src.add_argument("--catalog", type=Path)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if args.from_db:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL is not set.")
        catalog = load_catalog_db(url)
    else:
        catalog = load_catalog_csv(args.catalog)
    if len(catalog) < MIN_SIZE:
        raise SystemExit(f"The catalog has {len(catalog)} companies; at least {MIN_SIZE} are needed.")
    for path in generate(catalog, args.count, args.out):
        print(path)


if __name__ == "__main__":
    main()

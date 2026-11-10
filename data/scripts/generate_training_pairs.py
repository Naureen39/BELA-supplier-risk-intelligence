"""Generate synthetic BLINK training data from the canonical company table.

Usage:
    python -m data.scripts.generate_training_pairs --out data/training
    python -m data.scripts.generate_training_pairs --catalog-jsonl companies.jsonl

Gold-set companies (data/gold/*.jsonl, field "company_id") are excluded from all splits.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.resolution.catalog import Catalog, CompanyRecord, load_catalog  # noqa: E402
from app.resolution.training_data import build_training_data  # noqa: E402


def gold_company_ids(gold_dir: Path) -> set[int]:
    ids: set[int] = set()
    for path in gold_dir.glob("*.jsonl"):
        for line in path.read_text().splitlines():
            if line.strip():
                cid = json.loads(line).get("company_id")
                if cid is not None:
                    ids.add(int(cid))
    return ids


def catalog_from_jsonl(path: Path) -> Catalog:
    records = []
    for line in path.read_text().splitlines():
        d = json.loads(line)
        d["aliases"] = tuple(d.get("aliases", ()))
        d["tickers"] = tuple(d.get("tickers", ()))
        records.append(CompanyRecord(**d))
    return Catalog(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "training")
    parser.add_argument("--gold", type=Path, default=ROOT / "data" / "gold")
    parser.add_argument("--catalog-jsonl", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--per-company", type=int, default=6)
    args = parser.parse_args()

    if args.catalog_jsonl:
        catalog = catalog_from_jsonl(args.catalog_jsonl)
    else:
        import psycopg

        url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(url) as conn:
            catalog = load_catalog(conn)
    summary = build_training_data(catalog, args.out, gold_company_ids(args.gold), args.seed,
                                  args.per_company)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

"""`make eval`: compare systems and write docs/eval/report.md, per-run CSVs, and metrics.json.

Data sources, in priority order: gold JSONL (data/gold/structured.jsonl), otherwise a synthetic
held-out company split built from the catalog. The report states which one was used. Results on
synthetic data must never be presented as gold-set results.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.resolution.catalog import Catalog
from app.resolution.config import DEFAULT_CONFIG
from app.resolution.evaluation.metrics import Prediction, pr_curve, rollup_accuracy, summarize
from app.resolution.evaluation.systems import (
    RapidFuzzSystem,
    ResolverSystem,
    System,
    run_system,
)
from app.resolution.models import QueryRecord
from app.resolution.retrievers import TrigramRetriever, VectorRetriever
from app.resolution.structured import Resolver
from app.resolution.training_data import mention_rows, split_companies


def load_gold(path: Path) -> tuple[list[QueryRecord], dict[str, int | None], dict[str, frozenset[str]]]:
    records, truth, tags = [], {}, {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        rid = str(d["id"])
        records.append(QueryRecord(
            id=rid, name=d["name"], state=d.get("state"), city=d.get("city"),
            country=d.get("country"), address=d.get("address"), website=d.get("website"),
            cik=d.get("cik"), lei=d.get("lei"), ticker=d.get("ticker"),
            industry_code=d.get("industry_code"), context=d.get("context")))
        truth[rid] = d.get("company_id")
        tags[rid] = frozenset({"hard"}) if d.get("hard_case") else frozenset()
    return records, truth, tags


def synthetic_test(
    catalog: Catalog, seed: int = 42, nil_share: float = 0.1
) -> tuple[list[QueryRecord], dict[str, int | None], dict[str, frozenset[str]]]:
    """Held-out company split: queries are perturbed names of test-split companies plus NIL names."""
    split = split_companies([r.id for r in catalog.records], seed=seed)
    rows = mention_rows(catalog, split.test, seed, per_company=3)
    records, truth, tags = [], {}, {}
    for i, row in enumerate(rows):
        rid = f"syn-{i}"
        records.append(QueryRecord(rid, row["mention"], state=row["state"], city=row["city"]))
        truth[rid] = row["label_id"]
        tags[rid] = frozenset({"hard"}) if len(row["ops"]) > 1 else frozenset()
    rng = random.Random(seed)
    syll = ["zor", "quil", "vex", "mar", "tun", "bel", "kra", "dun", "fyl", "sor"]
    for j in range(max(1, int(len(rows) * nil_share))):
        rid = f"syn-nil-{j}"
        name = " ".join("".join(rng.choices(syll, k=2)).title() for _ in range(2)) + " Holdings Inc"
        records.append(QueryRecord(rid, name, state=rng.choice(["OH", "TX", "CA", "NY"])))
        truth[rid] = None
        tags[rid] = frozenset()
    return records, truth, tags


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fmt(v: float) -> str:
    return "n/a" if isinstance(v, float) and math.isnan(v) else f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}"


def render_report(
    results: dict[str, dict[str, float]], data_label: str, n: int, notes: Sequence[str]
) -> str:
    cols = ["accuracy@1", "recall@5", "recall@10", "precision", "recall", "nil_f1",
            "false_links_per_1000", "precision@recall_target", "review_rate", "p50_ms", "p95_ms",
            "records_per_second"]
    lines = [
        "# Resolution evaluation report", "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Data: {data_label} ({n} records)", "",
        "| System | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols),
    ]
    for name, m in results.items():
        lines.append(f"| {name} | " + " | ".join(_fmt(m.get(c, math.nan)) for c in cols) + " |")
    lines += ["", "Precision and recall use each system's accept rule (the routing rule for the hybrid,",
              "a fixed score threshold for baselines). `precision@recall_target` is read from the",
              "precision-recall curve at the target recall.", ""]
    lines += [f"- {n_}" for n_ in notes]
    return "\n".join(lines) + "\n"


def evaluate(
    catalog: Catalog, systems: Sequence[System], records: Sequence[QueryRecord],
    truth: dict[str, int | None], tags: dict[str, frozenset[str]], out_dir: Path,
    data_label: str, notes: Sequence[str] = (), recall_target: float = 0.8,
) -> dict[str, dict[str, float]]:
    results: dict[str, dict[str, float]] = {}
    parent_of = {c: p for p, c in catalog.edges}
    for system in systems:
        preds: list[Prediction] = run_system(system, records, truth, tags)
        m = summarize(preds, system.accept_threshold, recall_target)
        m["rollup_accuracy"] = rollup_accuracy(preds, parent_of)
        hard = [p for p in preds if "hard" in p.tags]
        if hard:
            m["accuracy@1_hard"] = summarize(hard, system.accept_threshold)["accuracy@1"]
        results[system.name] = m
        write_csv(out_dir / f"{system.name}.csv", [
            {"record_id": p.record_id, "truth": p.truth, "predicted": p.predicted,
             "score": p.score, "route": p.route, "latency_ms": round(p.latency_ms, 3)}
            for p in preds])
        write_csv(out_dir / f"{system.name}_pr_curve.csv", pr_curve(preds))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(render_report(results, data_label, len(records), notes))
    (out_dir / "metrics.json").write_text(json.dumps(
        {"data": data_label, "n": len(records), "config": DEFAULT_CONFIG.version,
         "config_status": DEFAULT_CONFIG.status, "systems": results}, indent=2, sort_keys=True))
    return results


def build_systems(catalog: Catalog, with_vector: bool) -> list[System]:
    cfg = DEFAULT_CONFIG
    systems: list[System] = [
        RapidFuzzSystem(catalog),
        ResolverSystem("fellegi_sunter_only", Resolver(catalog, [TrigramRetriever(catalog, cfg)])),
    ]
    if with_vector:
        from app.kb.embeddings import BgeM3Embedder

        embedder = BgeM3Embedder()
        vec = VectorRetriever(catalog, embedder)
        systems.append(ResolverSystem("bge_m3_retrieval_only", Resolver(catalog, [vec])))
        systems.append(ResolverSystem("hybrid", Resolver(
            catalog, [TrigramRetriever(catalog, cfg), vec])))
    else:
        systems.append(ResolverSystem("hybrid_trigram_only", Resolver(catalog)))
    return systems


def main() -> None:
    from app.resolution.catalog import load_catalog

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=Path("data/gold/structured.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("docs/eval"))
    parser.add_argument("--with-vector", action="store_true", help="include bge-m3 (needs GPU or time)")
    args = parser.parse_args()

    import os

    import psycopg

    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        catalog = load_catalog(conn)
    if args.gold.exists() and args.gold.stat().st_size > 0:
        records, truth, tags = load_gold(args.gold)
        label = "structured gold set"
    else:
        records, truth, tags = synthetic_test(catalog)
        label = "SYNTHETIC held-out company split (no gold set available yet; not a gold result)"
    notes = [
        f"Resolution config: {DEFAULT_CONFIG.version} ({DEFAULT_CONFIG.status}).",
        "BLINK and BELA systems require their services; run with the service URLs configured.",
    ]
    results = evaluate(catalog, build_systems(catalog, args.with_vector), records, truth, tags,
                       args.out, label, notes)
    print((args.out / "report.md").read_text())
    print(f"systems evaluated: {', '.join(results)}")


if __name__ == "__main__":
    main()

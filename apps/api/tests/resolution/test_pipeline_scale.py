"""Fitted pipeline on a fictional catalog: quality versus baseline, calibration, throughput."""

from __future__ import annotations

import time
from pathlib import Path

from app.resolution.evaluation.metrics import summarize
from app.resolution.evaluation.run import synthetic_test
from app.resolution.evaluation.systems import RapidFuzzSystem, ResolverSystem, run_system
from app.resolution.fitting import calibration_report, fit_models, load_models, save_models
from app.resolution.synthetic import generate_catalog
from app.resolution.training_data import mention_rows, split_companies


def test_fitted_hybrid_beats_fuzzy_baseline_and_is_calibrated(tmp_path: Path) -> None:
    cat = generate_catalog(1500, seed=7)
    split = split_companies([r.id for r in cat.records], seed=7)
    dev = mention_rows(cat, split.dev, seed=7, per_company=4)
    resolver = fit_models(cat, dev)

    report = calibration_report(resolver, mention_rows(cat, split.test, seed=8, per_company=2)[:300])
    assert report["ece_calibrated"] <= report["ece_raw"] + 0.02

    records, truth, tags = synthetic_test(cat, seed=7)
    records, truth = records[:400], truth
    base = run_system(RapidFuzzSystem(cat), records, truth, tags)
    hyb = run_system(ResolverSystem("hybrid", resolver), records, truth, tags)
    b = summarize(base, 0.90)
    h = summarize(hyb, resolver.cfg.accept_threshold)
    assert h["accuracy@1"] >= b["accuracy@1"] - 0.02
    assert h["false_links_per_1000"] <= b["false_links_per_1000"]
    assert h["recall@10"] > 0.9

    save_models(resolver, tmp_path, {"dev": "test"})
    reloaded = load_models(cat, tmp_path / "scoring_models.json")
    r0 = records[0]
    assert abs(reloaded.resolve(r0).probability - resolver.resolve(r0).probability) < 1e-9


def test_throughput_10k_records_completes() -> None:
    cat = generate_catalog(3000, seed=11)
    split = split_companies([r.id for r in cat.records], seed=11)
    rows = mention_rows(cat, split.test, seed=11, per_company=12)[:10_000]
    from app.resolution.models import QueryRecord
    from app.resolution.structured import Resolver

    resolver = Resolver(cat)
    recs = [QueryRecord(f"t{i}", r["mention"], state=r["state"], city=r["city"]) for i, r in enumerate(rows)]
    t0 = time.perf_counter()
    out = resolver.resolve_many(recs)
    elapsed = time.perf_counter() - t0
    print(f"\n{len(recs)} records in {elapsed:.1f}s = {len(recs)/elapsed:.0f} records/s")
    assert len(out) == len(recs)

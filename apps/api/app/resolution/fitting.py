"""Fit and persist the scoring models: Fellegi-Sunter, logistic combiner, calibrator.

Fitting uses the dev split only (plan: "trained on the dev split"). Models are saved as JSON with the
data hashes of their inputs so the model card can reference them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from app.resolution.catalog import Catalog
from app.resolution.models import QueryRecord, ScoredCandidate
from app.resolution.scoring import (
    FellegiSunter,
    IsotonicCalibrator,
    LogisticCombiner,
    calibrator_from_dict,
    expected_calibration_error,
    matrix,
    reliability_table,
)
from app.resolution.structured import Resolver


def _pairs(
    resolver: Resolver, rows: Sequence[dict[str, Any]]
) -> list[tuple[ScoredCandidate, bool]]:
    pairs: list[tuple[ScoredCandidate, bool]] = []
    for i, row in enumerate(rows):
        rec = QueryRecord(f"fit-{i}", row["mention"], state=row.get("state"), city=row.get("city"))
        cands, _ = resolver.score_candidates(rec)
        pairs.extend((c, c.company_id == row["label_id"]) for c in cands)
    return pairs


def fit_models(catalog: Catalog, dev_rows: Sequence[dict[str, Any]], seed: int = 0) -> Resolver:
    """Return a Resolver with fitted FS, combiner, and isotonic calibrator."""
    base = Resolver(catalog)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(dev_rows))
    half = len(dev_rows) // 2
    part_a = [dev_rows[i] for i in order[:half]]  # fits FS and combiner
    part_b = [dev_rows[i] for i in order[half:]]  # fits the calibrator

    pairs_a = _pairs(base, part_a)
    fs = FellegiSunter()
    fs.fit([(c.features, y) for c, y in pairs_a])

    fitted = Resolver(catalog, fs=fs)
    pairs_a = _pairs(fitted, part_a)
    X = matrix([(c.features, c.splink_weight) for c, _ in pairs_a])
    y = np.array([float(lbl) for _, lbl in pairs_a])
    combiner = LogisticCombiner()
    combiner.fit(X, y, l2=1.0)

    with_comb = Resolver(catalog, fs=fs, combiner=combiner)
    pairs_b = _pairs(with_comb, part_b)
    cal = IsotonicCalibrator()
    cal.fit([c.raw_probability for c, _ in pairs_b], [float(lbl) for _, lbl in pairs_b])
    return Resolver(catalog, fs=fs, combiner=combiner, calibrator=cal)


def calibration_report(resolver: Resolver, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    pairs = _pairs(resolver, rows)
    probs = [c.probability for c, _ in pairs]
    labels = [float(lbl) for _, lbl in pairs]
    raw = [c.raw_probability for c, _ in pairs]
    return {
        "ece_calibrated": expected_calibration_error(probs, labels),
        "ece_raw": expected_calibration_error(raw, labels),
        "reliability": reliability_table(probs, labels),
    }


def save_models(resolver: Resolver, directory: Path, input_hashes: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if resolver.combiner is None or resolver.calibrator is None:
        raise ValueError("resolver is not fully fitted")
    (directory / "scoring_models.json").write_text(json.dumps({
        "fellegi_sunter": resolver.fs.to_dict(), "combiner": resolver.combiner.to_dict(),
        "calibrator": resolver.calibrator.to_dict(), "input_hashes": input_hashes,
        "config_version": resolver.cfg.version,
    }, indent=2, sort_keys=True))


def load_models(catalog: Catalog, path: Path) -> Resolver:
    data = json.loads(path.read_text())
    return Resolver(
        catalog, fs=FellegiSunter.from_dict(data["fellegi_sunter"]),
        combiner=LogisticCombiner.from_dict(data["combiner"]),
        calibrator=calibrator_from_dict(data["calibrator"]),
    )

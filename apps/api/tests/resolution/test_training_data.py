from __future__ import annotations

import json
import random
from pathlib import Path

from app.resolution.perturb import PERTURBATIONS, perturb_name
from app.resolution.training_data import build_training_data, split_companies
from resolution_fixtures import catalog


def test_split_is_deterministic_disjoint_and_excludes_gold() -> None:
    ids = range(1, 2001)
    a = split_companies(ids, exclude={5, 6}, seed=1)
    b = split_companies(ids, exclude={5, 6}, seed=1)
    assert a == b
    assert not (a.train & a.dev) and not (a.train & a.test) and not (a.dev & a.test)
    assert 5 not in a.train | a.dev | a.test
    assert 0.75 < len(a.train) / 1998 < 0.85


def test_every_perturbation_runs_and_changes_or_keeps_text() -> None:
    rng = random.Random(0)
    for name, fn in PERTURBATIONS.items():
        out = fn("Harborline Foods International Inc.", rng, "OH")
        assert isinstance(out, str) and out, name
    variant, ops = perturb_name("Northgate Metals Corporation", rng, "PA")
    assert variant and ops


def test_build_training_data_writes_hashes_and_no_leakage(tmp_path: Path) -> None:
    summary = build_training_data(catalog(), tmp_path, gold_company_ids={7}, seed=3, per_company=4)
    assert set(summary["sha256"]) == {"entities.jsonl", "train.jsonl", "dev.jsonl", "test.jsonl"}
    seen = {}
    for part in ("train", "dev", "test"):
        for line in (tmp_path / f"{part}.jsonl").read_text().splitlines():
            row = json.loads(line)
            assert row["label_id"] != 7
            seen.setdefault(row["label_id"], set()).add(part)
    assert all(len(v) == 1 for v in seen.values())
    again = build_training_data(catalog(), tmp_path / "again", gold_company_ids={7}, seed=3, per_company=4)
    assert again["sha256"] == summary["sha256"]

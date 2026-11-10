from __future__ import annotations

import json
import math
from pathlib import Path

from app.resolution.evaluation.metrics import (
    Prediction,
    at_routes,
    at_threshold,
    operating_point,
    percentile,
    recall_at_k,
    rollup_accuracy,
)
from app.resolution.evaluation.run import build_systems, evaluate, synthetic_test
from resolution_fixtures import catalog


def P(rid: str, truth: int | None, pred: int | None, score: float, ranked=(), route=None) -> Prediction:
    return Prediction(rid, truth, pred, score, tuple(ranked) or ((pred,) if pred else ()), route)


PREDS = [P("a", 1, 1, 0.99), P("b", 2, 2, 0.95), P("c", 3, 9, 0.92, [9, 3]), P("d", None, 5, 0.91),
         P("e", 4, 4, 0.40), P("f", None, None, 0.0)]


def test_threshold_metrics() -> None:
    m = at_threshold(PREDS, 0.9)
    assert m["precision"] == 2 / 4 and m["recall"] == 2 / 4
    assert m["false_links_per_1000"] == 1000 * 2 / 6
    assert at_threshold(PREDS, 0.99)["precision"] == 1.0


def test_nil_f1_counts_abstentions() -> None:
    m = at_threshold(PREDS, 0.9)
    # NIL truth: d (accepted wrongly), f (abstained). predicted NIL: e, f. tp=1.
    assert math.isclose(m["nil_f1"], 2 * 0.5 * 0.5 / 1.0)


def test_recall_at_k_and_operating_point() -> None:
    assert recall_at_k(PREDS, 1) == 3 / 4 and recall_at_k(PREDS, 2) == 1.0
    op = operating_point(PREDS, 0.5)
    assert op["recall"] >= 0.5 and op["threshold"] >= 0.9


def test_route_based_acceptance_excludes_review() -> None:
    preds = [P("a", 1, 1, 0.95, route="accepted"), P("b", 2, 3, 0.95, route="review")]
    m = at_routes(preds)
    assert m["precision"] == 1.0 and m["recall"] == 0.5


def test_percentile_and_rollup() -> None:
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert rollup_accuracy([P("a", 4, 3, 1.0)], {4: 3}) == 1.0


def test_end_to_end_synthetic_eval_writes_report(tmp_path: Path) -> None:
    cat = catalog()
    records, truth, tags = synthetic_test(cat)
    assert any(v is None for v in truth.values())
    results = evaluate(cat, build_systems(cat, with_vector=False), records, truth, tags, tmp_path,
                       "SYNTHETIC test")
    assert {"rapidfuzz_state_blocking", "fellegi_sunter_only", "hybrid_trigram_only"} <= set(results)
    report = (tmp_path / "report.md").read_text()
    assert "SYNTHETIC" in report and "—" not in report
    assert json.loads((tmp_path / "metrics.json").read_text())["systems"]

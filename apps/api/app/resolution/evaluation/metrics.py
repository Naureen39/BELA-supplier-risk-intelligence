"""Evaluation metrics for entity resolution and linking."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Prediction:
    record_id: str
    truth: int | None  # None means NIL
    predicted: int | None  # top candidate, None when the system proposes nothing
    score: float  # confidence of the top candidate
    ranked: tuple[int, ...] = ()
    route: str | None = None  # exact_id, accepted, review, nil (systems with routing only)
    latency_ms: float = 0.0
    tags: frozenset[str] = field(default_factory=frozenset)  # for example {"hard"}


def recall_at_k(preds: Sequence[Prediction], k: int) -> float:
    """Share of non-NIL records whose true company is within the top k candidates."""
    rows = [p for p in preds if p.truth is not None]
    if not rows:
        return math.nan
    return sum(p.truth in p.ranked[:k] for p in rows) / len(rows)


def accuracy_at_1(preds: Sequence[Prediction]) -> float:
    """Share of non-NIL records whose top candidate is the true company."""
    rows = [p for p in preds if p.truth is not None]
    return sum(p.predicted == p.truth for p in rows) / len(rows) if rows else math.nan


def _accepted(p: Prediction, threshold: float) -> bool:
    return p.predicted is not None and p.score >= threshold


def _summary_for(preds: Sequence[Prediction], accepted_flags: Sequence[bool]) -> dict[str, float]:
    accepted = [p for p, a in zip(preds, accepted_flags, strict=True) if a]
    correct = sum(p.predicted == p.truth for p in accepted)
    positives = sum(p.truth is not None for p in preds)
    nil_flags = [(p, not a) for p, a in zip(preds, accepted_flags, strict=True)]
    nil_truth = [pred_nil for p, pred_nil in nil_flags if p.truth is None]
    nil_tp = sum(nil_truth)
    nil_pred = sum(pred_nil for _p, pred_nil in nil_flags)
    nil_prec = nil_tp / nil_pred if nil_pred else math.nan
    nil_rec = nil_tp / len(nil_truth) if nil_truth else math.nan
    nil_f1 = (
        2 * nil_prec * nil_rec / (nil_prec + nil_rec)
        if nil_prec == nil_prec and nil_rec == nil_rec and (nil_prec + nil_rec) > 0
        else math.nan
    )
    return {
        "precision": correct / len(accepted) if accepted else math.nan,
        "recall": correct / positives if positives else math.nan,
        "false_links_per_1000": 1000 * (len(accepted) - correct) / len(preds) if preds else math.nan,
        "nil_f1": nil_f1,
        "accepted_share": len(accepted) / len(preds) if preds else math.nan,
    }


def at_threshold(preds: Sequence[Prediction], threshold: float) -> dict[str, float]:
    """Precision, recall, false links per 1000, and NIL F1 when accepting score >= threshold."""
    flags = [_accepted(p, threshold) for p in preds]
    return {"threshold": threshold, **_summary_for(preds, flags)}


def at_routes(preds: Sequence[Prediction]) -> dict[str, float]:
    """Same metrics where accepted means routed `accepted` or `exact_id` (review is not accepted)."""
    flags = [p.predicted is not None and p.route in ("accepted", "exact_id") for p in preds]
    return {"threshold": math.nan, **_summary_for(preds, flags)}


def pr_curve(preds: Sequence[Prediction]) -> list[dict[str, float]]:
    thresholds = sorted({p.score for p in preds if p.predicted is not None}, reverse=True)
    return [at_threshold(preds, t) for t in thresholds]


def operating_point(preds: Sequence[Prediction], recall_target: float) -> dict[str, float]:
    """Highest-threshold point that reaches `recall_target` (best precision at that recall)."""
    best: dict[str, float] | None = None
    for row in pr_curve(preds):
        if row["recall"] >= recall_target:
            best = row
            break  # thresholds descend, so this is the strictest qualifying point
    return best or {"threshold": math.nan, "precision": math.nan, "recall": math.nan,
                    "false_links_per_1000": math.nan, "nil_f1": math.nan, "accepted_share": math.nan}


def review_rate(preds: Sequence[Prediction]) -> float:
    routed = [p for p in preds if p.route is not None]
    return sum(p.route == "review" for p in routed) / len(routed) if routed else math.nan


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def latency_summary(preds: Sequence[Prediction]) -> dict[str, float]:
    lat = [p.latency_ms for p in preds]
    total_s = sum(lat) / 1000
    return {
        "p50_ms": percentile(lat, 0.5), "p95_ms": percentile(lat, 0.95),
        "records_per_second": len(lat) / total_s if total_s > 0 else math.nan,
    }


def rollup_accuracy(
    preds: Sequence[Prediction], parent_of: dict[int, int]
) -> float:
    """Accuracy of the ultimate-parent assignment for non-NIL records."""
    def top(cid: int | None) -> int | None:
        seen: set[int] = set()
        while cid is not None and cid in parent_of and cid not in seen:
            seen.add(cid)
            cid = parent_of[cid]
        return cid

    rows = [p for p in preds if p.truth is not None]
    return sum(top(p.predicted) == top(p.truth) for p in rows) / len(rows) if rows else math.nan


def summarize(preds: Sequence[Prediction], accept_threshold: float,
              recall_target: float = 0.8) -> dict[str, float]:
    point = at_routes(preds) if any(p.route for p in preds) else at_threshold(preds, accept_threshold)
    op = operating_point(preds, recall_target)
    return {
        "n": float(len(preds)),
        "recall@1": recall_at_k(preds, 1), "recall@5": recall_at_k(preds, 5),
        "recall@10": recall_at_k(preds, 10), "accuracy@1": accuracy_at_1(preds),
        "precision": point["precision"], "recall": point["recall"],
        "nil_f1": point["nil_f1"], "false_links_per_1000": point["false_links_per_1000"],
        "precision@recall_target": op["precision"],
        "false_links_per_1000@recall_target": op["false_links_per_1000"],
        "review_rate": review_rate(preds), **latency_summary(preds),
    }

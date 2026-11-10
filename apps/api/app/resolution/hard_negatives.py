"""Mine hard negatives from a retriever's own top-k errors (BLINK bi-encoder retrain round)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

Retrieve = Callable[[str, str, int], list[int]]


def mine_hard_negatives(
    rows: Sequence[dict[str, Any]], retrieve: Retrieve, k: int = 30, keep: int = 10
) -> list[dict[str, Any]]:
    """Add `mined_negative_ids`: top-k candidates that rank above or around the true company
    but are wrong. Also records the rank of the true company (None when outside the top k)."""
    out = []
    for row in rows:
        ranked = retrieve(row["mention"], row.get("context_right", ""), k)
        true_id = row["label_id"]
        rank = ranked.index(true_id) + 1 if true_id in ranked else None
        wrong = [c for c in ranked if c != true_id]
        out.append({**row, "true_rank": rank,
                    "mined_negative_ids": wrong[:keep]})
    return out


def retrieval_recall(rows: Sequence[dict[str, Any]], k: int) -> float:
    ranks = [r["true_rank"] for r in rows]
    return sum(1 for x in ranks if x is not None and x <= k) / len(ranks) if ranks else 0.0

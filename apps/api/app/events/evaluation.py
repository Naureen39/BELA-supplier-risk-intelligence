"""Evaluate event labeling on gold sentences: per-class precision and recall, severity accuracy.

Gold file (JSONL): {"id", "sentence", "event_type", "severity", "lang"}. Target size is 200
sentences (plan Phase 4). Without a gold file the CLI refuses to report, so synthetic numbers are
never mistaken for gold results.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.events.classifier import (
    Classification,
    KeywordClassifier,
    LlmEventClassifier,
    classify_with_fallback,
)
from app.events.schema import EVENT_TYPES


def evaluate_labels(
    gold: Sequence[dict[str, Any]], classify: Callable[[str], Classification]
) -> dict[str, Any]:
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    confusion: Counter[tuple[str, str]] = Counter()
    sev_exact = sev_near = sev_n = 0
    for row in gold:
        pred = classify(row["sentence"])
        truth = row["event_type"]
        confusion[(truth, pred.event_type)] += 1
        if pred.event_type == truth:
            tp[truth] += 1
        else:
            fp[pred.event_type] += 1
            fn[truth] += 1
        if truth != "none" and pred.event_type == truth:
            sev_n += 1
            sev_exact += pred.severity == row["severity"]
            sev_near += abs(pred.severity - row["severity"]) <= 1
    classes = {}
    for c in EVENT_TYPES:
        support = tp[c] + fn[c]
        if support == 0 and fp[c] == 0:
            continue
        p = tp[c] / (tp[c] + fp[c]) if tp[c] + fp[c] else float("nan")
        r = tp[c] / support if support else float("nan")
        classes[c] = {"precision": p, "recall": r, "support": support}
    total = len(gold)
    return {
        "n": total,
        "accuracy": sum(tp.values()) / total if total else float("nan"),
        "classes": classes,
        "severity_exact": sev_exact / sev_n if sev_n else float("nan"),
        "severity_within_one": sev_near / sev_n if sev_n else float("nan"),
        "confusion": {f"{t}->{p}": n for (t, p), n in sorted(confusion.items())},
    }


def render(result: dict[str, Any], label: str) -> str:
    lines = [f"# Event labeling evaluation ({label})", "", f"Sentences: {result['n']}",
             f"Type accuracy: {result['accuracy']:.3f}",
             f"Severity exact (correct type only): {result['severity_exact']:.3f}",
             f"Severity within one level: {result['severity_within_one']:.3f}", "",
             "| Class | Precision | Recall | Support |", "|---|---|---|---|"]
    for c, m in result["classes"].items():
        lines.append(f"| {c} | {m['precision']:.3f} | {m['recall']:.3f} | {m['support']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=Path("data/gold/events.jsonl"))
    parser.add_argument("--llm-url", default=None, help="llama-server URL; omit for keyword baseline")
    parser.add_argument("--out", type=Path, default=Path("docs/eval/event_labeling.md"))
    args = parser.parse_args()
    if not args.gold.exists() or args.gold.stat().st_size == 0:
        raise SystemExit(f"No gold sentences at {args.gold}. Annotate them first (200 sentences).")
    gold = [json.loads(line) for line in args.gold.read_text().splitlines() if line.strip()]
    if args.llm_url:
        llm = LlmEventClassifier(args.llm_url)
        result = evaluate_labels(gold, lambda s: classify_with_fallback(llm, s))
        label = f"local LLM {llm.model}"
    else:
        result = evaluate_labels(gold, KeywordClassifier().classify)
        label = "keyword baseline"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(result, label))
    print(render(result, label))


if __name__ == "__main__":
    main()

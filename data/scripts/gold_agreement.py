"""Cohen's kappa between two annotators' JSONL label files keyed by task id.

Each line: {"id": ..., "label": ...}. Usage: python -m data.scripts.gold_agreement a.jsonl b.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load(path: Path) -> dict[str, str]:
    rows = (json.loads(x) for x in path.read_text().splitlines() if x.strip())
    return {str(r["id"]): str(r["label"]) for r in rows}


def cohens_kappa(a: dict[str, str], b: dict[str, str]) -> float:
    ids = sorted(set(a) & set(b))
    if not ids:
        raise ValueError("no shared task ids")
    observed = sum(a[i] == b[i] for i in ids) / len(ids)
    ca, cb = Counter(a[i] for i in ids), Counter(b[i] for i in ids)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / len(ids) ** 2
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    args = parser.parse_args(argv)
    print(f"kappa = {cohens_kappa(load(args.a), load(args.b)):.3f}")


if __name__ == "__main__":
    main()

"""Publish the latest evaluation as valid JSON for the web app: apps/web/public/metrics.json.

    python infra/publish_metrics.py [docs/eval/metrics.json]

The evaluation writes NaN for measures that are undefined (for example the review rate of a baseline that never
routes to review). NaN is not valid JSON, so it becomes null here. The data label is kept, so the site can say
whether a figure comes from a gold set or from synthetic data.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

KEEP = ("accuracy@1", "recall@5", "precision", "recall", "false_links_per_1000", "nil_f1", "review_rate", "p50_ms", "p95_ms")


def clean(v: object) -> object:
    return None if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else v


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/eval/metrics.json")
    raw = json.loads(src.read_text())
    out = {
        "data": raw.get("data"), "records": raw.get("n"), "config": raw.get("config"),
        "config_status": raw.get("config_status"),
        "systems": {name: {k: clean(m.get(k)) for k in KEEP} for name, m in sorted(raw["systems"].items())},
    }
    dest = Path("apps/web/public/metrics.json")
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {dest} ({len(out['systems'])} systems, data: {out['data']})")


if __name__ == "__main__":
    main()

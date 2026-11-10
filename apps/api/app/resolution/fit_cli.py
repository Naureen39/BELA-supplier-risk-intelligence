"""Fit the Fellegi-Sunter model, logistic combiner, and calibrator on the dev split.

    python -m app.resolution.fit_cli --training-dir data/training --out models/scoring
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from app.resolution.catalog import load_catalog
from app.resolution.fitting import calibration_report, fit_models, save_models


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", type=Path, default=Path("data/training"))
    parser.add_argument("--out", type=Path, default=Path("models/scoring"))
    args = parser.parse_args()

    import psycopg

    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        catalog = load_catalog(conn)
    dev_path = args.training_dir / "dev.jsonl"
    dev = [json.loads(line) for line in dev_path.read_text().splitlines() if line.strip()]
    resolver = fit_models(catalog, dev)
    digest = hashlib.sha256(dev_path.read_bytes()).hexdigest()
    save_models(resolver, args.out, {"dev.jsonl": digest})
    report = calibration_report(resolver, dev)
    (args.out / "calibration.json").write_text(json.dumps(report, indent=2))
    print(f"ECE raw {report['ece_raw']:.4f} -> calibrated {report['ece_calibrated']:.4f} "
          "(in-sample on dev; report held-out numbers from make eval)")


if __name__ == "__main__":
    main()

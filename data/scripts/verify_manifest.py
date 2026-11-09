"""Verify every file recorded in manifest.yaml: existence, size, SHA-256. Print a row count report.

Usage: python -m data.scripts.verify_manifest [--counts]
Exit status is non-zero when any recorded file is missing or altered.
"""

from __future__ import annotations

import argparse
import sys

from data.scripts.common import DATA_DIR, load_manifest, setup_logging, sha256_file


def verify() -> list[str]:
    problems: list[str] = []
    for source in load_manifest()["sources"]:
        for entry in source.get("files", []):
            path = DATA_DIR / entry["path"]
            if not path.exists():
                problems.append(f"missing: {entry['path']}")
            elif path.stat().st_size != entry["bytes"]:
                problems.append(f"size mismatch: {entry['path']}")
            elif sha256_file(path) != entry["sha256"]:
                problems.append(f"hash mismatch: {entry['path']}")
    return problems


def row_counts() -> dict[str, int]:
    """Count rows in each parquet, JSON array, and JSONL file under raw/."""
    import json

    counts: dict[str, int] = {}
    for path in sorted((DATA_DIR / "raw").rglob("*")):
        rel = str(path.relative_to(DATA_DIR))
        if path.suffix == ".parquet":
            import pyarrow.parquet as pq

            counts[rel] = pq.ParquetFile(path).metadata.num_rows
        elif path.suffix == ".jsonl":
            counts[rel] = sum(1 for line in path.open() if line.strip())
        elif path.suffix == ".json" and path.stat().st_size < 500_000_000:
            data = json.loads(path.read_text())
            counts[rel] = len(data) if isinstance(data, list) else len(data.get("data", data))
    return counts


def main(argv: list[str] | None = None) -> int:
    log = setup_logging("verify_manifest")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", action="store_true")
    args = parser.parse_args(argv)
    problems = verify()
    for problem in problems:
        log.error(problem)
    if args.counts:
        for rel, count in row_counts().items():
            print(f"{count:>12,}  {rel}")
    log.info("manifest verification %s", "failed" if problems else "passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

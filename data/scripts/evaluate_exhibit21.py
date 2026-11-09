"""Report the Exhibit 21 parser success rate on downloaded filings.

A filing counts as parsed when at least one subsidiary row is extracted. A filing is
"fully annotated" when it is listed in data/gold/exhibit21_expected.json with an expected
row count, in which case the extracted count must be within 10 percent of expected.

Usage: python -m data.scripts.evaluate_exhibit21 [--min-files 50]
"""

from __future__ import annotations

import argparse
import json
import sys

from data.scripts.common import DATA_DIR, RAW_DIR, setup_logging
from data.scripts.parse_exhibit21 import parse_exhibit21


def main(argv: list[str] | None = None) -> int:
    log = setup_logging("evaluate_exhibit21")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-files", type=int, default=50)
    args = parser.parse_args(argv)
    files = sorted((RAW_DIR / "edgar" / "exhibit21").glob("*.htm"))
    if len(files) < args.min_files:
        log.error("only %d filings available, need %d", len(files), args.min_files)
        return 1
    expected_path = DATA_DIR / "gold" / "exhibit21_expected.json"
    expected = json.loads(expected_path.read_text()) if expected_path.exists() else {}
    parsed = checked = accurate = 0
    for path in files:
        cik = int(path.name.split("_")[0])
        rows = parse_exhibit21(path.read_text(errors="replace"), cik)
        parsed += bool(rows)
        if path.name in expected:
            checked += 1
            want = expected[path.name]
            accurate += abs(len(rows) - want) <= max(1, 0.1 * want)
    print(f"filings: {len(files)}")
    print(f"non-empty parse rate: {parsed / len(files):.1%}")
    if checked:
        print(f"count accuracy on {checked} annotated filings: {accurate / checked:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Pull openFDA enforcement reports (food, drug, device) with pagination.

The openFDA API limits `skip` to 25,000; results are windowed by report date to stay below it.
Usage: python -m data.scripts.download_fda --start-year 2015
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from typing import Any

from data.scripts.common import RAW_DIR, CachedClient, record_file, setup_logging, user_agent

ENDPOINTS = {
    "food": "https://api.fda.gov/food/enforcement.json",
    "drug": "https://api.fda.gov/drug/enforcement.json",
    "device": "https://api.fda.gov/device/enforcement.json",
}
OUT = RAW_DIR / "regulators" / "fda"
PAGE = 1000


def fetch_window(client: CachedClient, url: str, start: str, end: str, use_cache: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    skip = 0
    key = os.environ.get("OPENFDA_API_KEY")
    while True:
        params = {"search": f"report_date:[{start} TO {end}]", "limit": PAGE, "skip": skip}
        if key:
            params["api_key"] = key
        try:
            data = client.get_json(url, params=params, use_cache=use_cache)
        except RuntimeError:
            break  # openFDA returns 404 when a window has no results
        batch = data.get("results", [])
        results.extend(batch)
        skip += PAGE
        if len(batch) < PAGE or skip >= 25000:
            break
    return results


def main(argv: list[str] | None = None) -> None:
    log = setup_logging("download_fda")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2015)
    args = parser.parse_args(argv)
    client = CachedClient({"User-Agent": user_agent()}, min_interval=0.5, retries=2)
    today = dt.date.today()
    for kind, url in ENDPOINTS.items():
        for year in range(args.start_year, today.year + 1):
            dest = OUT / f"{kind}_{year}.json"
            if dest.exists() and year < today.year:
                continue
            records: list[dict[str, Any]] = []
            for half in (("0101", "0630"), ("0701", "1231")):
                records += fetch_window(
                    client, url, f"{year}{half[0]}", f"{year}{half[1]}", use_cache=year < today.year
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(records))
            record_file("openfda", dest, url)
            log.info("fda %s %s: %d records", kind, year, len(records))


if __name__ == "__main__":
    main()

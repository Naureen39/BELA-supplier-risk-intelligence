"""Pull CPSC recalls as JSON from the SaferProducts REST service, one file per year.

Usage: python -m data.scripts.download_cpsc --start-year 2015
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

from data.scripts.common import RAW_DIR, CachedClient, record_file, setup_logging, user_agent

URL = "https://www.saferproducts.gov/RestWebServices/Recall"
OUT = RAW_DIR / "regulators" / "cpsc"


def main(argv: list[str] | None = None) -> None:
    log = setup_logging("download_cpsc")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2015)
    args = parser.parse_args(argv)
    client = CachedClient({"User-Agent": user_agent()}, min_interval=2.0)
    today = dt.date.today()
    for year in range(args.start_year, today.year + 1):
        dest = OUT / f"recalls_{year}.json"
        # Past years are immutable; only the current year is refreshed.
        if dest.exists() and year < today.year:
            continue
        params = {
            "format": "json",
            "RecallDateStart": f"{year}-01-01",
            "RecallDateEnd": f"{year}-12-31",
        }
        data = client.get_json(URL, params=params, use_cache=year < today.year)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data))
        record_file("cpsc", dest, URL)
        log.info("cpsc %s: %d recalls", year, len(data))


if __name__ == "__main__":
    main()

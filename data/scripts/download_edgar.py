"""Download SEC EDGAR company identity files and the quarterly full index.

Usage: python -m data.scripts.download_edgar [--years 2023 2024 2025]
Requires SEC_USER_AGENT. Requests are capped at 5 per second and cached.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from data.scripts.common import RAW_DIR, CachedClient, record_file, setup_logging, user_agent

OUT = RAW_DIR / "edgar"
STATIC_FILES = {
    "company_tickers.json": "https://www.sec.gov/files/company_tickers.json",
    "company_tickers_exchange.json": "https://www.sec.gov/files/company_tickers_exchange.json",
    "cik-lookup-data.txt": "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt",
}
FULL_INDEX = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.idx"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


def make_client() -> CachedClient:
    return CachedClient({"User-Agent": user_agent(sec=True)}, min_interval=0.2)


def fetch_submissions(client: CachedClient, cik: int) -> dict[str, Any]:
    """Submissions JSON for one company (former names, SIC, state of incorporation)."""
    result: dict[str, Any] = json.loads(client.get_bytes(SUBMISSIONS.format(cik=cik)))
    return result


def main(argv: list[str] | None = None) -> None:
    log = setup_logging("download_edgar")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025])
    args = parser.parse_args(argv)
    client = make_client()
    for name, url in STATIC_FILES.items():
        dest = client.download(url, OUT / name)
        record_file("sec_edgar", dest, url)
    for year in args.years:
        for quarter in (1, 2, 3, 4):
            url = FULL_INDEX.format(year=year, q=quarter)
            dest = OUT / "full-index" / str(year) / f"QTR{quarter}" / "form.idx"
            try:
                client.download(url, dest)
            except Exception as exc:  # future quarters do not exist yet
                log.warning("skipping %s Q%s: %s", year, quarter, exc)
                continue
            record_file("sec_edgar", dest, url)
    log.info("EDGAR download complete: %s", Path(OUT))


if __name__ == "__main__":
    main()

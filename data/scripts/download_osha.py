"""Download OSHA inspection and violation data.

Access method is recorded in docs/adr/ADR-003-osha-access.md. This script supports:
  api      US Department of Labor data portal (requires DOL_API_KEY, free registration)
  archive  a local or hosted bulk copy given with --archive-url (for example the DataLumos copy)

Usage: python -m data.scripts.download_osha --method api
       python -m data.scripts.download_osha --method archive --archive-url URL
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from data.scripts.common import RAW_DIR, CachedClient, record_file, setup_logging, user_agent

OUT = RAW_DIR / "regulators" / "osha"
API = "https://apiprod.dol.gov/v4/get/OSHA/{table}/json"
TABLES = {"inspection": "inspection", "violation": "violation"}
PAGE = 10000


def fetch_table(client: CachedClient, table: str, api_key: str, max_pages: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset, pages = 0, 0
    while max_pages is None or pages < max_pages:
        params = {"limit": PAGE, "offset": offset, "X-API-KEY": api_key}
        data = client.get_json(API.format(table=table), params=params, use_cache=False)
        batch = data.get("data", data) if isinstance(data, dict) else data
        if not batch:
            break
        rows.extend(batch)
        offset += PAGE
        pages += 1
    return rows


def main(argv: list[str] | None = None) -> None:
    log = setup_logging("download_osha")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=["api", "archive"], required=True)
    parser.add_argument("--archive-url")
    parser.add_argument("--max-pages", type=int)
    args = parser.parse_args(argv)
    client = CachedClient({"User-Agent": user_agent()}, min_interval=1.0, timeout=300)
    if args.method == "archive":
        if not args.archive_url:
            parser.error("--archive-url is required with --method archive")
        dest = client.download(args.archive_url, OUT / args.archive_url.rsplit("/", 1)[-1])
        record_file("osha", dest, args.archive_url)
        return
    api_key = os.environ.get("DOL_API_KEY")
    if not api_key:
        raise RuntimeError("DOL_API_KEY is not set. See .env.example and ADR-003.")
    for name, table in TABLES.items():
        rows = fetch_table(client, table, api_key, args.max_pages)
        dest = OUT / f"{name}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(rows))
        record_file("osha", dest, API.format(table=table))
        log.info("osha %s: %d rows", name, len(rows))


if __name__ == "__main__":
    main()

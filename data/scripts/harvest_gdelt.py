"""Harvest news metadata from the GDELT DOC 2.0 API into one JSONL file per day.

Two query families: event topics, and per-supplier name queries (from a names file).
Rate limit: one request per 5 seconds. Each run is idempotent: records are de-duplicated by URL
within the day's file. Metadata only; article text is fetched separately and never redistributed.

Usage: python -m data.scripts.harvest_gdelt [--names-file FILE] [--timespan 1d]
Schedule hourly or every few hours (see infra/cron/gdelt.cron).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from data.scripts.common import RAW_DIR, CachedClient, setup_logging, user_agent

API = "https://api.gdeltproject.org/api/v2/doc/doc"
OUT = RAW_DIR / "news" / "gdelt"
EVENT_TOPICS = [
    "plant fire", "factory explosion", "product recall", "workers strike", "bankruptcy",
    "data breach", "chemical spill", "plant closure", "lawsuit", "workplace accident",
    "production halt", "supply disruption",
]


def build_queries(topics: list[str], names: list[str]) -> list[tuple[str, str]]:
    """Return (family, query) pairs: topic queries and quoted per-supplier name queries."""
    queries = [("topic", f'"{t}" sourcelang:english') for t in topics]
    queries += [("supplier", f'"{n}"') for n in names]
    return queries


def day_file(day: dt.date) -> Path:
    return OUT / f"{day.isoformat()}.jsonl"


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["url"] for line in path.read_text().splitlines() if line.strip()}


def harvest(client: CachedClient, queries: list[tuple[str, str]], timespan: str) -> int:
    log = setup_logging("harvest_gdelt")
    today = dt.datetime.now(dt.UTC).date()
    path = day_file(today)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = load_seen(path)
    added = 0
    with path.open("a") as handle:
        for family, query in queries:
            params = {
                "query": query,
                "mode": "ArtList",
                "format": "json",
                "maxrecords": 250,
                "timespan": timespan,
                "sort": "datedesc",
            }
            try:
                payload = client.get_json(API, params=params, use_cache=False)
            except (RuntimeError, ValueError) as exc:
                log.warning("query failed (%s): %s", query, exc)
                continue
            for article in payload.get("articles", []) if isinstance(payload, dict) else []:
                url = article.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                record = {
                    "url": url,
                    "title": article.get("title"),
                    "seendate": article.get("seendate"),
                    "domain": article.get("domain"),
                    "language": article.get("language"),
                    "sourcecountry": article.get("sourcecountry"),
                    "query_family": family,
                    "query": query,
                    "harvested_at": dt.datetime.now(dt.UTC).isoformat(),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                added += 1
    log.info("gdelt run complete: %d new records in %s", added, path.name)
    return added


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--names-file", type=Path, help="one supplier name per line")
    parser.add_argument("--timespan", default="1d")
    args = parser.parse_args(argv)
    names = []
    if args.names_file:
        names = [n.strip() for n in args.names_file.read_text().splitlines() if n.strip()]
    client = CachedClient({"User-Agent": user_agent()}, min_interval=5.0, retries=2)
    harvest(client, build_queries(EVENT_TOPICS, names), args.timespan)


if __name__ == "__main__":
    main()

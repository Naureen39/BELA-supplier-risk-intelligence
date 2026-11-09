"""Download the GLEIF Golden Copy (Level 1 LEI records, Level 2 relationship records), CSV.

The Golden Copy publication endpoint is listed on the GLEIF download page; the latest
publish record is read from the public API and the file URLs are taken from it.
Usage: python -m data.scripts.download_gleif
"""

from __future__ import annotations

from typing import Any

from data.scripts.common import RAW_DIR, CachedClient, record_file, setup_logging, user_agent

LATEST = "https://leidata-preprod.gleif.org/api/v2/golden-copies/publishes/latest"
OUT = RAW_DIR / "registry" / "gleif"
# lei2 = Level 1 LEI-CDF, rr = Level 2 relationship records.
KINDS = {"lei2": "level1_lei2.zip", "rr": "level2_relationships.zip"}


def csv_urls(payload: dict[str, Any]) -> dict[str, str]:
    """Extract CSV zip URLs for each kind from a publish record."""
    urls: dict[str, str] = {}
    for kind in KINDS:
        entry = payload.get(kind) or {}
        full = (entry.get("full_file") or {}).get("csv") or {}
        if full.get("url"):
            urls[kind] = full["url"]
    return urls


def main() -> None:
    log = setup_logging("download_gleif")
    client = CachedClient({"User-Agent": user_agent()}, min_interval=1.0)
    payload = client.get_json(LATEST, use_cache=False)
    urls = csv_urls(payload)
    missing = set(KINDS) - set(urls)
    if missing:
        raise RuntimeError(f"GLEIF publish record is missing CSV links for {sorted(missing)}")
    for kind, url in urls.items():
        dest = client.download(url, OUT / KINDS[kind])
        record_file("gleif", dest, url)
    log.info("GLEIF download complete")


if __name__ == "__main__":
    main()

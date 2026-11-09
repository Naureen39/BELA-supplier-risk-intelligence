"""Locate and download Exhibit 21 documents for 10-K filings listed in the EDGAR full index.

Usage: python -m data.scripts.download_exhibit21 --year 2025 --quarter 1 --limit 200
Reads raw/edgar/full-index/<year>/QTR<q>/form.idx (run download_edgar first).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from bs4 import BeautifulSoup

from data.scripts.common import RAW_DIR, CachedClient, setup_logging, user_agent

BASE = "https://www.sec.gov/Archives/"
OUT = RAW_DIR / "edgar" / "exhibit21"


def list_10k_filings(index_path: Path) -> list[tuple[int, str]]:
    """Return (cik, filename) pairs for 10-K rows of a form.idx file."""
    rows = []
    for line in index_path.read_text(errors="replace").splitlines():
        if not line.startswith("10-K "):
            continue
        match = re.search(r"(\d+)\s+\d{4}-\d{2}-\d{2}\s+(edgar/data/\S+)$", line)
        if match:
            rows.append((int(match[1]), match[2]))
    return rows


def find_exhibit21_link(index_html: str) -> str | None:
    """Find the Exhibit 21 document link in a filing index page."""
    soup = BeautifulSoup(index_html, "lxml")
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        text = " ".join(cells).upper()
        if re.search(r"\bEX-?21(\.\d+)?\b", text) or "SUBSIDIARIES" in text:
            link = row.find("a", href=True)
            if link:
                return str(link["href"])
    return None


def main(argv: list[str] | None = None) -> None:
    log = setup_logging("download_exhibit21")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv)
    index = RAW_DIR / "edgar" / "full-index" / str(args.year) / f"QTR{args.quarter}" / "form.idx"
    client = CachedClient({"User-Agent": user_agent(sec=True)}, min_interval=0.2)
    done = failed = 0
    for cik, filename in list_10k_filings(index)[: args.limit]:
        accession = filename.rsplit("/", 1)[-1].removesuffix(".txt")
        dest = OUT / f"{cik}_{accession}.htm"
        if dest.exists():
            continue
        folder = filename.rsplit("/", 1)[0] + "/" + accession.replace("-", "")
        try:
            html = client.get_bytes(f"{BASE}{folder}/{accession}-index.htm").decode(errors="replace")
            link = find_exhibit21_link(html)
            if not link:
                failed += 1
                continue
            url = link if link.startswith("http") else "https://www.sec.gov" + link
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(client.get_bytes(url))
            done += 1
        except Exception as exc:
            failed += 1
            log.warning("filing %s failed: %s", accession, exc)
    log.info("exhibit21 downloaded=%d no_exhibit_or_failed=%d", done, failed)


if __name__ == "__main__":
    main()

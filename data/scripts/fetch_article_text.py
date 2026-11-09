"""Fetch article text for linking: robots.txt, per-domain rate limits, retries, language detection.

Stores extracted text in a working directory only for mention extraction. Persisted output keeps
a snippet of at most 300 characters and the detected language; full articles are never redisplayed.
SSRF protection: only http(s), hosts resolving to public addresses, response size and time limits.

Usage: python -m data.scripts.fetch_article_text --input raw/news/gdelt/2026-11-09.jsonl --limit 100
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import time
import urllib.robotparser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura

from data.scripts.common import RAW_DIR, RateLimiter, setup_logging, user_agent

MAX_BYTES = 3_000_000
SNIPPET_CHARS = 300
OUT = RAW_DIR / "news" / "articles"

_detector = None


def is_public_host(host: str) -> bool:
    """Reject hosts resolving to private, loopback, link-local, or reserved addresses."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            return False
    return bool(infos)


def make_snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 3].rstrip() + "..."


def detect_language(text: str) -> str | None:
    """Return an ISO 639-1 code using lingua-py, or None when undetermined."""
    global _detector
    if _detector is None:
        from lingua import LanguageDetectorBuilder

        _detector = LanguageDetectorBuilder.from_all_spoken_languages().with_low_accuracy_mode().build()
    language = _detector.detect_language_of(text[:2000])
    return language.iso_code_639_1.name.lower() if language else None


class ArticleFetcher:
    def __init__(self, contact_agent: str, per_domain_interval: float = 5.0) -> None:
        self.agent = contact_agent
        self.limiter = RateLimiter(per_domain_interval)
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.client = httpx.Client(
            headers={"User-Agent": contact_agent}, timeout=20.0, follow_redirects=False
        )
        self.log = setup_logging("fetch_article_text")

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                response = self.client.get(f"{origin}/robots.txt")
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                    self.robots[origin] = parser
                elif response.status_code in (404, 410):
                    self.robots[origin] = None  # no robots file: allowed
                else:
                    parser.disallow_all = True  # type: ignore[attr-defined]
                    self.robots[origin] = parser
            except httpx.HTTPError:
                parser.disallow_all = True  # type: ignore[attr-defined]
                self.robots[origin] = parser
        parser_or_none = self.robots[origin]
        return parser_or_none is None or parser_or_none.can_fetch(self.agent, url)

    def fetch(self, url: str, retries: int = 2, max_redirects: int = 3) -> str | None:
        for _ in range(max_redirects + 1):
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return None
            if not is_public_host(parsed.hostname) or not self.allowed(url):
                return None
            for attempt in range(retries + 1):
                self.limiter.wait(parsed.hostname)
                try:
                    with self.client.stream("GET", url) as response:
                        if response.is_redirect:
                            url = str(response.headers.get("location", ""))
                            break
                        if response.status_code != 200:
                            if response.status_code in (429, 500, 502, 503, 504):
                                raise httpx.HTTPError(f"status {response.status_code}")
                            return None
                        body = b""
                        for block in response.iter_bytes():
                            body += block
                            if len(body) > MAX_BYTES:
                                return None
                        return body.decode(response.encoding or "utf-8", errors="replace")
                except httpx.HTTPError as exc:
                    self.log.warning("fetch failed %s: %s", url, exc)
                    time.sleep(2**attempt)
            else:
                return None
        return None


def process(fetcher: ArticleFetcher, record: dict[str, Any]) -> dict[str, Any] | None:
    html = fetcher.fetch(record["url"])
    if not html:
        return None
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not text:
        return None
    return {
        "url": record["url"],
        "title": record.get("title"),
        "domain": record.get("domain"),
        "language": detect_language(text) or record.get("language"),
        "snippet": make_snippet(text),
        "chars": len(text),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)
    fetcher = ArticleFetcher(user_agent())
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / args.input.name
    done = {json.loads(x)["url"] for x in out_path.read_text().splitlines()} if out_path.exists() else set()
    lines = [json.loads(x) for x in args.input.read_text().splitlines() if x.strip()]
    with out_path.open("a") as handle:
        for record in [r for r in lines if r["url"] not in done][: args.limit]:
            result = process(fetcher, record)
            if result:
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

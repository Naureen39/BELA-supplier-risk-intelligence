"""Shared helpers for data acquisition scripts.

Provides a rate-limited, cached, resumable HTTP client, SHA-256 hashing,
manifest updates, and logging setup. All download scripts build on this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

DATA_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR.parent / ".cache" / "http"
MANIFEST_PATH = DATA_DIR / "manifest.yaml"

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(name: str) -> logging.Logger:
    """Configure root logging once and return a named logger."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
    return logging.getLogger(name)


def user_agent(*, sec: bool = False) -> str:
    """Return the declared User-Agent. SEC requests require organization and email."""
    if sec:
        value = os.environ.get("SEC_USER_AGENT", "").strip()
        if not value or "@" not in value:
            raise RuntimeError(
                "SEC_USER_AGENT must be set to '<organization> <contact email>' "
                "(SEC fair access policy). See .env.example."
            )
        return value
    contact = os.environ.get("CONTACT_EMAIL", "").strip()
    if not contact:
        raise RuntimeError("CONTACT_EMAIL must be set. See .env.example.")
    return f"ProvenanceRiskResearch/0.1 ({contact})"


class RateLimiter:
    """Thread-safe limiter enforcing a minimum interval between calls per key."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, key: str = "default") -> None:
        with self._lock:
            now = time.monotonic()
            last = self._last.get(key)
            delay = 0.0 if last is None else self.min_interval - (now - last)
            if delay > 0:
                time.sleep(delay)
            self._last[key] = time.monotonic()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


class CachedClient:
    """HTTP client with rate limiting, retries, and an on-disk response cache."""

    def __init__(
        self,
        headers: dict[str, str],
        min_interval: float,
        cache_dir: Path = CACHE_DIR,
        retries: int = 4,
        timeout: float = 60.0,
    ) -> None:
        self.client = httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)
        self.limiter = RateLimiter(min_interval)
        self.cache_dir = cache_dir
        self.retries = retries
        self.log = setup_logging("http")

    def _cache_path(self, url: str, params: dict[str, Any] | None) -> Path:
        key = hashlib.sha256(
            json.dumps([url, params or {}], sort_keys=True).encode()
        ).hexdigest()
        return self.cache_dir / key[:2] / key

    def get_bytes(
        self, url: str, params: dict[str, Any] | None = None, use_cache: bool = True
    ) -> bytes:
        path = self._cache_path(url, params)
        if use_cache and path.exists():
            return path.read_bytes()
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.wait(httpx.URL(url).host)
            try:
                response = self.client.get(url, params=params)
                if response.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"status {response.status_code}", request=response.request, response=response
                    )
                response.raise_for_status()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
                return response.content
            except (httpx.HTTPError, httpx.TransportError) as exc:
                last_error = exc
                backoff = 2**attempt
                self.log.warning("request failed (%s), retry in %ss: %s", url, backoff, exc)
                time.sleep(backoff)
        raise RuntimeError(f"giving up on {url}: {last_error}")

    def get_json(self, url: str, params: dict[str, Any] | None = None, use_cache: bool = True) -> Any:
        return json.loads(self.get_bytes(url, params, use_cache))

    def download(self, url: str, dest: Path, expected_sha256: str | None = None) -> Path:
        """Stream a large file to dest. Resumes partial downloads, verifies the checksum."""
        log = self.log
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and (expected_sha256 is None or sha256_file(dest) == expected_sha256):
            log.info("already present: %s", dest.name)
            return dest
        part = dest.with_suffix(dest.suffix + ".part")
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        self.limiter.wait(httpx.URL(url).host)
        with self.client.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:  # range not satisfiable: part is complete
                part.rename(dest)
            else:
                response.raise_for_status()
                mode = "ab" if response.status_code == 206 else "wb"
                with part.open(mode) as handle:
                    for block in response.iter_bytes(1 << 20):
                        handle.write(block)
                part.rename(dest)
        digest = sha256_file(dest)
        if expected_sha256 and digest != expected_sha256:
            dest.unlink()
            raise RuntimeError(f"checksum mismatch for {dest.name}: {digest}")
        log.info("downloaded %s sha256=%s", dest.name, digest)
        return dest


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open() as handle:
        return yaml.safe_load(handle) or {"sources": []}


def record_file(source: str, path: Path, url: str) -> None:
    """Record a downloaded file (size, hash, retrieval date) in the manifest."""
    manifest = load_manifest()
    entry = next(s for s in manifest["sources"] if s["name"] == source)
    files = entry.setdefault("files", [])
    rel = str(path.relative_to(DATA_DIR))
    record = {
        "path": rel,
        "url": url,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "retrieved": time.strftime("%Y-%m-%d", time.gmtime()),
    }
    files[:] = [f for f in files if f["path"] != rel] + [record]
    with MANIFEST_PATH.open("w") as handle:
        yaml.safe_dump(manifest, handle, sort_keys=False, width=100)

"""Download NHTSA recall flat files (post-2010) and the field layout document.

Usage: python -m data.scripts.download_nhtsa
"""

from __future__ import annotations

import yaml

from data.scripts.common import (
    DATA_DIR,
    RAW_DIR,
    CachedClient,
    record_file,
    setup_logging,
    user_agent,
)

OUT = RAW_DIR / "regulators" / "nhtsa"


def main() -> None:
    log = setup_logging("download_nhtsa")
    with (DATA_DIR / "scripts" / "sources.yaml").open() as handle:
        urls: dict[str, str] = yaml.safe_load(handle)["nhtsa"]
    client = CachedClient({"User-Agent": user_agent()}, min_interval=1.0, timeout=300)
    for name, url in urls.items():
        dest = client.download(url, OUT / url.rsplit("/", 1)[-1])
        record_file("nhtsa", dest, url)
        log.info("fetched %s", name)


if __name__ == "__main__":
    main()

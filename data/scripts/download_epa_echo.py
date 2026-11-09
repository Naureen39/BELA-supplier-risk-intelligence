"""Download EPA ECHO bulk files: ECHO Exporter, Facility Registry Service, ICIS FE&C.

URLs are read from data/scripts/sources.yaml so they can be updated without code changes.
Usage: python -m data.scripts.download_epa_echo
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

OUT = RAW_DIR / "regulators" / "epa_echo"


def load_urls() -> dict[str, str]:
    with (DATA_DIR / "scripts" / "sources.yaml").open() as handle:
        return dict(yaml.safe_load(handle)["epa_echo"])


def main() -> None:
    log = setup_logging("download_epa_echo")
    client = CachedClient({"User-Agent": user_agent()}, min_interval=1.0, timeout=300)
    for name, url in load_urls().items():
        dest = client.download(url, OUT / f"{name}.zip")
        record_file("epa_echo", dest, url)
    log.info("EPA ECHO download complete")


if __name__ == "__main__":
    main()

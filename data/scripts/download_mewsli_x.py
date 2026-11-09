"""Download the optional Mewsli-X benchmark (thin wrapper over download_hf_datasets)."""

from __future__ import annotations

from data.scripts.download_hf_datasets import main as hf_main

if __name__ == "__main__":
    hf_main(["--mewsli"])

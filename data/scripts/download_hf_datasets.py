"""Download optional Hugging Face datasets: multilingual CC-News slices and Mewsli-X.

Usage: python -m data.scripts.download_hf_datasets --cc-news-langs en de es --mewsli
Requires `pip install huggingface_hub`.
"""

from __future__ import annotations

import argparse

from data.scripts.common import RAW_DIR, setup_logging


def main(argv: list[str] | None = None) -> None:
    from huggingface_hub import snapshot_download

    log = setup_logging("download_hf_datasets")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc-news-langs", nargs="*", default=[])
    parser.add_argument("--mewsli", action="store_true")
    args = parser.parse_args(argv)
    for lang in args.cc_news_langs:
        snapshot_download(
            "intfloat/multilingual_cc_news",
            repo_type="dataset",
            allow_patterns=f"{lang}/*.parquet",
            local_dir=RAW_DIR / "news" / "cc_news",
        )
        log.info("cc_news slice %s downloaded", lang)
    if args.mewsli:
        snapshot_download(
            "izhx/mewsli-x", repo_type="dataset", local_dir=RAW_DIR / "eval" / "mewsli_x"
        )
        log.info("mewsli-x downloaded")


if __name__ == "__main__":
    main()

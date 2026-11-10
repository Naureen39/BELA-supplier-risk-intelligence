"""Download the GGUF model for llama-server and verify its checksum.

The expected SHA-256 is pinned in `models.lock.json`. A file is never used unless its hash matches.
On the first download, pass `--record` after reading the license on the model card: the hash is
then written to the lock file for review and commit. Spike C (plan section 6) records the choice.

    python services/llm/fetch_model.py --repo <hf-repo> --file <name>.gguf --record
    python services/llm/fetch_model.py            # verify and download from the lock file
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = HERE / "models.lock.json"
DEST = HERE / "models"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo")
    parser.add_argument("--file")
    parser.add_argument("--record", action="store_true", help="write the downloaded hash to the lock")
    args = parser.parse_args()

    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    repo = args.repo or lock.get("repo")
    filename = args.file or lock.get("file")
    if not repo or not filename:
        print("No model pinned. Pass --repo and --file, then --record.", file=sys.stderr)
        return 2

    from huggingface_hub import hf_hub_download

    DEST.mkdir(exist_ok=True)
    path = Path(hf_hub_download(repo_id=repo, filename=filename, local_dir=DEST))
    actual = sha256_of(path)
    if args.record:
        LOCK.write_text(json.dumps({"repo": repo, "file": filename, "sha256": actual,
                                    "license_reviewed": False}, indent=2) + "\n")
        print(f"Recorded {actual}. Review the model card license, then set license_reviewed.")
        return 0
    expected = lock.get("sha256")
    if not expected or actual != expected:
        path.unlink(missing_ok=True)
        print(f"Checksum mismatch or missing pin (got {actual}). File removed.", file=sys.stderr)
        return 1
    print(f"Verified {path.name} {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

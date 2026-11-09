"""Fail if the Unicode em dash (U+2014) appears in any tracked or candidate text file."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EM_DASH = chr(0x2014)
SKIP_DIRS = {".venv", ".git", "node_modules", ".cache", "__pycache__", "raw"}


def candidate_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.split()
        if out:
            return [root / p for p in out]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return [p for p in root.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.parts)]


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    bad = 0
    for path in candidate_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if EM_DASH in line:
                print(f"{path.relative_to(root)}:{number}: em dash found")
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

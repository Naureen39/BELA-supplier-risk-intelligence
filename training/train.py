"""`make train`: build training data, then run the configured BLINK stages.

Stages: data -> bi-encoder round 1 -> mine hard negatives -> bi-encoder round 2 -> cross-encoder
-> record checkpoint metadata. Stages that need GPU training are skipped with `--dry-run`, which
prints the commands (used by CI to validate the configuration).
"""

from __future__ import annotations

import argparse
import json
import shlex
import string
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"data_dir", "output_dir", "round", "init_model", "epochs", "batch_size", "accum"}


def render(template: str, **values: object) -> list[str]:
    fields = {f for _, f, _, _ in string.Formatter().parse(template) if f}
    unknown = fields - ALLOWED
    if unknown:
        raise ValueError(f"unknown placeholders in command template: {sorted(unknown)}")
    return shlex.split(template.format(**values))


def stage_commands(cfg: dict[str, Any]) -> list[tuple[str, list[str]]]:
    out_dir = cfg["output_dir"]
    data_dir = str(Path(cfg["data"]["train"]).parent)
    bi, cross = cfg["biencoder"], cfg["crossencoder"]
    cmds: list[tuple[str, list[str]]] = []
    init = cfg["init"]["biencoder"]
    for rnd in range(1, int(bi["rounds"]) + 1):
        cmds.append((f"biencoder_round_{rnd}", render(
            bi["command"], data_dir=data_dir, output_dir=out_dir, round=rnd, init_model=init,
            epochs=bi["epochs"], batch_size=bi["batch_size"], accum=bi["accum"])))
        init = f"{out_dir}/biencoder_{rnd}/pytorch_model.bin"
    cmds.append(("crossencoder", render(
        cross["command"], data_dir=data_dir, output_dir=out_dir, round=0,
        init_model=cfg["init"]["crossencoder"], epochs=cross["epochs"],
        batch_size=cross["batch_size"], accum=cross["accum"])))
    return cmds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "training/blink/config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text())

    gen = [sys.executable, "-m", "data.scripts.generate_training_pairs"]
    commands = [("generate_data", gen), *stage_commands(cfg)]
    for name, cmd in commands:
        print(f"[{name}] {shlex.join(cmd)}")
        if args.dry_run:
            continue
        subprocess.run(cmd, check=True, cwd=ROOT)  # noqa: S603
    meta = {"config": cfg, "stages": [n for n, _ in commands]}
    if not args.dry_run:
        Path(cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
        (Path(cfg["output_dir"]) / "train_meta.json").write_text(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

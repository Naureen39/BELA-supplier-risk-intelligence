from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.resolution.hard_negatives import mine_hard_negatives, retrieval_recall

from training.train import render, stage_commands

CONFIG = Path(__file__).resolve().parents[1] / "training/blink/config.yaml"


def test_config_renders_all_stages() -> None:
    cfg = yaml.safe_load(CONFIG.read_text())
    stages = stage_commands(cfg)
    assert [n for n, _ in stages] == ["biencoder_round_1", "biencoder_round_2", "crossencoder"]
    assert "--fp16" in stages[0][1] and "--path_to_model" in stages[0][1]
    assert "biencoder_1" in " ".join(stages[1][1])


def test_unknown_placeholder_fails_fast() -> None:
    with pytest.raises(ValueError):
        render("run {nonexistent}")


def test_hard_negative_mining() -> None:
    rows = [{"mention": "a", "label_id": 1}, {"mention": "b", "label_id": 2}]
    mined = mine_hard_negatives(rows, lambda m, c, k: [9, 1, 7] if m == "a" else [5, 6], k=3)
    assert mined[0]["true_rank"] == 2 and mined[0]["mined_negative_ids"] == [9, 7]
    assert mined[1]["true_rank"] is None
    assert retrieval_recall(mined, 2) == 0.5

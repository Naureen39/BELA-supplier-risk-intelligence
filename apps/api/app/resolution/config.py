"""Versioned resolution configuration.

`resolution_config_v1` holds the initial thresholds from the plan. Values marked provisional must
be recalibrated on the gold sets and then frozen. The version string is stored with every decision.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ResolutionConfig:
    version: str = "resolution_config_v1"
    status: str = "provisional"  # becomes "frozen" after calibration on the gold sets

    # Structured routing (calibrated probabilities)
    accept_threshold: float = 0.90
    review_threshold: float = 0.50
    min_margin: float = 0.10

    # Candidate generation
    trigram_k: int = 30
    vector_k: int = 30
    blink_k: int = 30
    candidates_kept: int = 10
    state_bonus: float = 0.05  # soft blocking: ranking bonus, never an exclusion

    # News linking
    news_accept_threshold: float = 0.85
    news_review_threshold: float = 0.50
    bela_trust_el_score: float = 0.60  # minimum BELA link score to trust a company link directly
    blink_confident: float = 0.90  # skip the LLM when BLINK is at least this sure with a margin
    llm_candidates: int = 5
    chunk_max_chars: int = 1800
    chunk_overlap_sentences: int = 1

    # Names that are too generic to accept on retrieval alone
    min_name_tokens_for_accept: int = 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_file(cls, path: Path) -> ResolutionConfig:
        data = json.loads(path.read_text())
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass(frozen=True)
class ModelVersions:
    nel: str = "unset"
    blink_bi: str = "unset"
    blink_cross: str = "unset"
    llm: str = "unset"
    prompt: str = "adjudication_v1"
    embedder: str = "BAAI/bge-m3"
    extra: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, str]:
        base = {k: v for k, v in asdict(self).items() if k != "extra"}
        return {**base, **self.extra}


DEFAULT_CONFIG = ResolutionConfig()

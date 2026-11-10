"""BLINK model adapters for the blink service.

The service is self-contained (no import from apps/api) because the upstream BLINK code needs an
older Python and PyTorch and runs in an isolated environment (ADR-002).

`BlinkModels` is the interface the spike-B adapter implements around the fine-tuned bi-encoder and
cross-encoder: `encode_entities` and `encode_mentions` return L2-normalized vectors; `score_pairs`
returns cross-encoder probabilities in 0..1. `DevModels` is a dependency-free stand-in for tests
and local runs and is not a BLINK result.
"""

from __future__ import annotations

import hashlib
import importlib
import math
import os
from collections.abc import Sequence
from typing import Protocol

from rapidfuzz import fuzz

DIM = 256


class BlinkModels(Protocol):
    biencoder_version: str
    crossencoder_version: str

    def encode_entities(self, texts: Sequence[str]) -> list[list[float]]: ...

    def encode_mentions(
        self, mentions: Sequence[str], contexts: Sequence[str]
    ) -> list[list[float]]: ...

    def score_pairs(
        self, mention: str, context: str, candidate_texts: Sequence[str]
    ) -> list[float]: ...


class DevModels:
    biencoder_version = "dev-hashed-trigram"
    crossencoder_version = "dev-fuzzy"

    @staticmethod
    def _vec(text: str) -> list[float]:
        padded = f"  {text.casefold()}  "
        v = [0.0] * DIM
        for i in range(len(padded) - 2):
            h = hashlib.blake2b(padded[i : i + 3].encode(), digest_size=4).digest()
            v[int.from_bytes(h, "big") % DIM] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def encode_entities(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vec(t.split(". ")[0]) for t in texts]  # title carries the signal

    def encode_mentions(self, mentions: Sequence[str], contexts: Sequence[str]) -> list[list[float]]:
        return [self._vec(m) for m in mentions]

    def score_pairs(self, mention: str, context: str, candidate_texts: Sequence[str]) -> list[float]:
        return [fuzz.token_set_ratio(mention.casefold(), t.split(". ")[0].casefold()) / 100.0
                for t in candidate_texts]


def load_models() -> BlinkModels:
    spec = os.environ.get("BLINK_BACKEND", "")
    if not spec:
        return DevModels()
    module_name, _, factory = spec.partition(":")
    models: BlinkModels = getattr(importlib.import_module(module_name), factory)()
    return models

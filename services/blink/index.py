"""Company embedding index. Uses FAISS when installed, otherwise exact numpy search."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

try:  # optional dependency
    import faiss
except ImportError:  # pragma: no cover
    faiss = None


class CompanyIndex:
    """Entities (idx, company_id, title, text) with an inner-product index over bi-encoder vectors."""

    def __init__(self) -> None:
        self.entities: list[dict[str, Any]] = []
        self._matrix = np.zeros((0, 1), dtype=np.float32)
        self._faiss: Any = None
        self._lock = threading.RLock()
        self.source_mtime: float = 0.0

    @property
    def size(self) -> int:
        return len(self.entities)

    def build(self, entities: Sequence[dict[str, Any]], vectors: Sequence[Sequence[float]]) -> None:
        mat = np.asarray(vectors, dtype=np.float32)
        index = None
        if faiss is not None and len(mat):
            index = faiss.IndexFlatIP(mat.shape[1])
            index.add(mat)
        with self._lock:  # swap atomically so searches never see a half-built index
            self.entities = list(entities)
            self._matrix = mat
            self._faiss = index

    def search(self, vector: Sequence[float], k: int) -> list[tuple[dict[str, Any], float]]:
        with self._lock:
            if not self.entities:
                return []
            q = np.asarray(vector, dtype=np.float32)[None, :]
            k = min(k, len(self.entities))
            if self._faiss is not None:
                scores, ids = self._faiss.search(q, k)
                pairs = list(zip(ids[0].tolist(), scores[0].tolist(), strict=True))
            else:
                sims = (self._matrix @ q[0])
                top = np.argsort(-sims)[:k]
                pairs = [(int(i), float(sims[i])) for i in top]
            return [(self.entities[i], float(s)) for i, s in pairs if i >= 0]

    def by_company(self, company_id: int) -> dict[str, Any] | None:
        with self._lock:
            return next((e for e in self.entities if e["company_id"] == company_id), None)


def read_entities(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

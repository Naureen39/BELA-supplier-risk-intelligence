"""Embeddings for canonical names, aliases, and short descriptions (bge-m3, 1024 dimensions).

`BgeM3Embedder` loads the real model lazily (sentence-transformers, fp16 on GPU when available).
`HashedNgramEmbedder` is a deterministic, dependency-free stand-in used by tests and CPU-only
smoke runs. Results measured with the stand-in must never be reported as bge-m3 results.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator, Sequence
from typing import Protocol

import psycopg

DIM = 1024


class Embedder(Protocol):
    model_name: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class BgeM3Embedder:
    model_name = "BAAI/bge-m3"

    def __init__(self, batch_size: int = 64) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = SentenceTransformer(self.model_name, device=device)
        if device == "cuda":
            self._model.half()
        self._batch = batch_size

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts), batch_size=self._batch, normalize_embeddings=True, show_progress_bar=False
        )
        return [v.tolist() for v in vectors]


class HashedNgramEmbedder:
    """Character trigram feature hashing into 1024 dimensions, L2 normalized."""

    model_name = "test-hashed-trigram-1024"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        padded = f"  {text.casefold()}  "
        vec = [0.0] * DIM
        for i in range(len(padded) - 2):
            digest = hashlib.blake2b(padded[i : i + 3].encode(), digest_size=4).digest()
            vec[int.from_bytes(digest, "big") % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def to_vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


def entity_texts(conn: psycopg.Connection) -> Iterator[tuple[int, str, str]]:
    """Yield (company_id, kind, text) for names, aliases, and short descriptions."""
    for company_id, name, description in conn.execute(
        "SELECT id, canonical_name, description FROM companies"
    ):
        yield company_id, "name", name
        if description:
            yield company_id, "description", f"{name}. {description}"[:500]
    for company_id, alias in conn.execute("SELECT company_id, alias FROM company_aliases"):
        yield company_id, "alias", alias


def embed_entities(conn: psycopg.Connection, embedder: Embedder, batch_size: int = 256) -> int:
    """Embed all entity texts not yet stored for this model. Returns rows inserted."""
    existing = {
        (cid, kind, text)
        for cid, kind, text in conn.execute(
            "SELECT company_id, kind, text FROM entity_embeddings WHERE model = %s",
            (embedder.model_name,),
        )
    }
    pending = [row for row in entity_texts(conn) if row not in existing]
    inserted = 0
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        vectors = embedder.encode([text for _cid, _kind, text in chunk])
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO entity_embeddings (company_id, kind, text, model, embedding) "
                "VALUES (%s,%s,%s,%s,%s::vector) ON CONFLICT DO NOTHING",
                [
                    (cid, kind, text, embedder.model_name, to_vector_literal(vec))
                    for (cid, kind, text), vec in zip(chunk, vectors, strict=True)
                ],
            )
        inserted += len(chunk)
    return inserted


def search(
    conn: psycopg.Connection, embedder: Embedder, query: str, k: int = 5, ef_search: int = 100
) -> list[int]:
    """Top-k distinct company ids by cosine distance over all stored entity embeddings."""
    conn.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
    vector = to_vector_literal(embedder.encode([query])[0])
    rows = conn.execute(
        "SELECT company_id FROM entity_embeddings WHERE model = %s "
        "ORDER BY embedding <=> %s::vector LIMIT %s",
        (embedder.model_name, vector, k * 4),
    ).fetchall()
    seen: list[int] = []
    for (company_id,) in rows:
        if company_id not in seen:
            seen.append(company_id)
        if len(seen) == k:
            break
    return seen

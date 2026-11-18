"""Recall and latency of the HNSW name index as hnsw.ef_search changes.

Usage: PYTHONPATH=.:apps/api python infra/perf/hnsw_sweep.py DATABASE_URL [--queries 500]
Embeds every company name with the hashed character n-gram stand-in (the production model, bge-m3, is not loaded
here), then looks up noisy variants of names and checks whether the right company is in the top 5.
Results depend on the embedder: use them to choose the speed and recall trade-off, not as model accuracy.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time

import psycopg
from app.kb.embeddings import HashedNgramEmbedder, embed_entities, search
from app.resolution.perturb import perturb_name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("--queries", type=int, default=500)
    a = ap.parse_args()
    rng = random.Random(11)  # nosec B311
    embedder = HashedNgramEmbedder()
    with psycopg.connect(a.url.replace("postgresql+psycopg://", "postgresql://")) as conn:
        have = conn.execute("SELECT count(*) FROM entity_embeddings").fetchone()[0]
        if not have:
            t = time.perf_counter()
            embed_entities(conn, embedder)
            conn.commit()
            print(json.dumps({"embedded_seconds": round(time.perf_counter() - t, 1)}))
        rows = conn.execute("SELECT id, canonical_name FROM companies ORDER BY id").fetchall()
        sample = rng.sample(rows, a.queries)
        queries = [(cid, perturb_name(name, rng, None, max_ops=3)[0]) for cid, name in sample]
        for _cid, q in queries:  # warm the cache first, or the first settings look slow
            search(conn, embedder, q, k=5, ef_search=100)
        for ef in (10, 20, 40, 100, 200, 400):
            hits, times = 0, []
            for cid, q in queries:
                t = time.perf_counter()
                found = search(conn, embedder, q, k=5, ef_search=ef)
                times.append((time.perf_counter() - t) * 1000)
                hits += cid in found
            times.sort()
            print(json.dumps({"ef_search": ef, "recall_at_5": round(hits / len(queries), 3),
                              "mean_ms": round(statistics.mean(times), 2), "p95_ms": round(times[int(0.95 * len(times))], 2)}))


if __name__ == "__main__":
    main()

"""Synthetic training data for BLINK and the combiner (plan section 5.4).

Splits are by company, so evaluation measures generalization to unseen companies. Companies that
appear in the gold sets are excluded from every split.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.resolution.catalog import Catalog, CompanyRecord
from app.resolution.perturb import perturb_name

PROGRAMS = ("air permit", "hazardous waste", "water discharge", "workplace inspection",
            "product recall", "stormwater", "chemical reporting")


@dataclass(frozen=True)
class SplitIds:
    train: frozenset[int]
    dev: frozenset[int]
    test: frozenset[int]


def split_companies(
    ids: Iterable[int], exclude: Collection[int] = (), seed: int = 42,
    fractions: tuple[float, float] = (0.8, 0.1),
) -> SplitIds:
    """Deterministic split by company id. `exclude` (gold companies) never enters any split."""
    banned = set(exclude)
    buckets: dict[str, set[int]] = {"train": set(), "dev": set(), "test": set()}
    for cid in ids:
        if cid in banned:
            continue
        h = int.from_bytes(hashlib.blake2b(f"{seed}:{cid}".encode(), digest_size=8).digest(), "big")
        u = (h % 10_000) / 10_000
        key = "train" if u < fractions[0] else "dev" if u < fractions[0] + fractions[1] else "test"
        buckets[key].add(cid)
    return SplitIds(frozenset(buckets["train"]), frozenset(buckets["dev"]), frozenset(buckets["test"]))


def entity_rows(catalog: Catalog) -> list[dict[str, Any]]:
    """BLINK entity catalog rows: idx, title, text. Confirm the exact keys in the training spike."""
    return [
        {"idx": rec.id, "title": rec.name, "text": catalog.blink_entity_text(rec),
         "company_id": rec.id}
        for rec in sorted(catalog.records, key=lambda r: r.id)
    ]


def _hard_negatives(catalog: Catalog, rec: CompanyRecord, allowed: Collection[int], n: int) -> list[int]:
    """Same or similar names elsewhere, parent or child, and shared-word companies."""
    out: list[int] = []
    for cid, _score in catalog.trigram_search(rec.name, 40):
        if cid != rec.id and cid in allowed and cid not in out:
            out.append(cid)
        if len(out) >= n:
            break
    return out


def mention_rows(
    catalog: Catalog, company_ids: Collection[int], seed: int, per_company: int = 6,
    negatives: int = 5,
) -> list[dict[str, Any]]:
    """Structured-record mentions in BLINK format (context_left, mention, context_right, label)."""
    rng = random.Random(f"{seed}:{sorted(company_ids)[:3]}:{len(company_ids)}")
    rows: list[dict[str, Any]] = []
    for cid in sorted(company_ids):
        rec = catalog.by_id[cid]
        names = [rec.name, *rec.aliases]
        for i in range(per_company):
            base = rng.choice(names)
            variant, ops = (base, []) if i == 0 else perturb_name(base, rng, rec.hq_state)
            drop_state = rng.random() < 0.15
            right = " ".join(
                p for p in (rec.hq_city, None if drop_state else rec.hq_state, rng.choice(PROGRAMS))
                if p
            )
            rows.append({
                "context_left": "", "mention": variant, "context_right": right,
                "label_id": cid, "label_title": rec.name, "state": None if drop_state else rec.hq_state,
                "city": rec.hq_city, "ops": ops,
                "hard_negative_ids": _hard_negatives(catalog, rec, set(catalog.by_id), negatives),
            })
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> str:
    """Write rows and return the SHA-256 of the file (stored in the model card)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            fh.write(line)
            digest.update(line.encode())
    return digest.hexdigest()


def build_training_data(
    catalog: Catalog, out_dir: Path, gold_company_ids: Collection[int] = (), seed: int = 42,
    per_company: int = 6,
) -> dict[str, Any]:
    split = split_companies([r.id for r in catalog.records], gold_company_ids, seed)
    hashes = {"entities.jsonl": write_jsonl(out_dir / "entities.jsonl", entity_rows(catalog))}
    counts = {}
    for name, ids in (("train", split.train), ("dev", split.dev), ("test", split.test)):
        rows = mention_rows(catalog, ids, seed, per_company)
        hashes[f"{name}.jsonl"] = write_jsonl(out_dir / f"{name}.jsonl", rows)
        counts[name] = {"companies": len(ids), "mentions": len(rows)}
    summary = {"seed": seed, "excluded_gold_companies": len(set(gold_company_ids)),
               "counts": counts, "sha256": hashes}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary

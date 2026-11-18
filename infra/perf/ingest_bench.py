"""Ingestion throughput: 10,000 synthetic news articles and 10,000 regulator records through the event pipeline.

Usage: PYTHONPATH=.:apps/api python infra/perf/ingest_bench.py [--articles 10000] [--records 10000] [--companies 20000]

What is measured: sentence chunking, the topic filter, linking (identifier, retrieval, and Fellegi-Sunter scoring),
event classification with the keyword fallback, event construction, de-duplication keys, and regulator
normalization and attachment. What is NOT measured: BELA, BLINK, and the language model. Mention detection here
is a regular expression over capitalized names ending in a legal form, which stands in for BELA. Throughput of the
neural services depends on the GPU and must be measured when those spikes are run.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from app.events.normalizers import osha
from app.events.pipeline import EventPipeline
from app.events.rules import load_rules
from app.resolution.clients import MentionInput
from app.resolution.models import Mention
from app.resolution.news import NewsLinker
from app.resolution.perturb import perturb_name
from app.resolution.rollup import CorporateGraph
from app.resolution.structured import Resolver
from app.resolution.synthetic import generate_catalog

NAME = re.compile(r"((?:[A-Z][\w&.'-]*\s){1,6}(?:Inc\.?|LLC|Corp\.?|Co\.?|Ltd\.?|Group|Company|Holdings))")
VERBS = ["reported a fire at its plant", "announced a recall of a product line", "faces a lawsuit over a contract",
         "said a data breach exposed customer records", "filed for bankruptcy protection", "reached a new supply agreement",
         "opened a new office", "named a new chief executive"]
FILLER = ["Analysts expect the quarter to be difficult.", "Regional officials were notified.", "The market closed slightly lower.",
          "A spokesperson declined to comment further.", "Shares were little changed in early trading."]


class RegexNel:
    """A stand-in mention detector: capitalized names that end in a legal form."""

    def link(self, items: Sequence[MentionInput]) -> list[list[Mention]]:
        out: list[list[Mention]] = []
        for it in items:
            ms = []
            for m in NAME.finditer(it.text):
                end = it.text.find(".", m.end())
                sentence = it.text[it.text.rfind(".", 0, m.start()) + 1: end + 1 if end >= 0 else len(it.text)].strip()
                ms.append(Mention(it.id, m.start(), m.end(), m.group(1).strip(), sentence, None, 0.9, 0.0))
            out.append(ms)
        return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--articles", type=int, default=10_000)
    ap.add_argument("--records", type=int, default=10_000)
    ap.add_argument("--companies", type=int, default=20_000)
    a = ap.parse_args()
    rng = random.Random(3)  # nosec B311
    t0 = time.perf_counter()
    cat = generate_catalog(a.companies)
    resolver = Resolver(cat)
    pipe = EventPipeline(resolver, CorporateGraph(cat.edges), linker=NewsLinker(cat, RegexNel()))
    setup = time.perf_counter() - t0

    now = datetime(2026, 11, 1, tzinfo=UTC)
    arts = []
    for i in range(a.articles):
        co = rng.choice(cat.records)
        shown = perturb_name(co.name, rng, co.hq_state)[0] if rng.random() < 0.3 else co.name  # 30 percent are variants
        body = " ".join([rng.choice(FILLER), f"{shown} {rng.choice(VERBS)}.", rng.choice(FILLER), rng.choice(FILLER)])
        arts.append((f"art-{i}", f"https://example.org/a/{i}", f"Update {i}", body))
    t1 = time.perf_counter()
    events = 0
    for aid, url, title, body in arts:
        events += pipe.ingest_article(aid, url, title, now, body)
    news_s = time.perf_counter() - t1

    rules = load_rules()
    rows = []
    for i in range(a.records):
        co = rng.choice(cat.records)
        rows.append({"activity_nr": str(100000 + i), "estab_name": co.name.upper(), "site_state": co.hq_state or "",
                     "site_city": co.hq_city or "", "citation_id": "01", "viol_type": "S",
                     "current_penalty": str(rng.randint(500, 90000)), "issuance_date": "2026-09-15", "open_date": "2026-09-01"})
    t2 = time.perf_counter()
    added = 0
    for r in rows:
        added += pipe.ingest_regulator(osha.normalize_row(r, rules))
    reg_s = time.perf_counter() - t2
    print(json.dumps({
        "companies": a.companies, "setup_seconds": round(setup, 2),
        "articles": a.articles, "news_events_created": events, "article_seconds": round(news_s, 2),
        "articles_per_second": round(a.articles / news_s, 1),
        "regulator_records": a.records, "regulator_events_created": added, "regulator_seconds": round(reg_s, 2),
        "regulator_records_per_second": round(a.records / reg_s, 1),
        "mention_detector": "regular expression stand-in, not BELA",
    }))


if __name__ == "__main__":
    main()

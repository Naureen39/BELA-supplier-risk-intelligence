# Entity resolution and linking engine (Phase 3)

Code: `apps/api/app/resolution/`, services in `services/`, training in `training/`.
Run `make training-data`, `make train`, `make eval`. Unit tests: `make test`.

## Components

| Part | Location | Purpose |
|---|---|---|
| Catalog | `catalog.py` | In-memory view of companies, aliases, identifiers, trigram index |
| Features | `features.py` | Name, state, city, industry, and model-score features per candidate |
| Scoring | `scoring.py` | Fellegi-Sunter weights, logistic combiner, isotonic and Platt calibration |
| Structured pipeline | `structured.py` | Problems A and C: identifiers, candidates, scoring, routing |
| News pipeline | `news.py`, `llm.py` | Problem B: chunking, topic pre-filter, BELA, BLINK fallback, LLM adjudication |
| Roll-up | `rollup.py` | Parent, subsidiary, and sibling reach with the explaining path, depth limit 2 |
| Evaluation | `evaluation/` | Metrics, systems, report writer |
| Services | `services/nel`, `services/blink`, `services/llm` | HTTP model services |

## Routing

Exact identifier (CIK, LEI, ticker, website domain) accepts immediately; identifiers that point to
different companies go to review. Otherwise candidates from trigram search, vector search, and
BLINK are merged, scored, and routed with `resolution_config_v1`: accept at calibrated probability
0.90 or higher with a margin of 0.10 over the runner-up, review from 0.50, NIL below. When a model
service is unavailable the record is flagged `degraded` and is never accepted automatically.

News mentions: BELA links that map to a canonical company are accepted at the configured threshold.
Unlinked or non-company links go to BLINK retrieve and rerank, then to the local LLM when
ambiguous. The LLM chooses among at most five candidates and its output is one input to the final
score; it cannot accept a link alone. Every candidate is stored for the transparency panel.

## Status of each piece

| Piece | State |
|---|---|
| Resolution library, scoring, routing, roll-up, evaluation harness | Implemented and unit tested |
| Fellegi-Sunter scorer | Implemented in this repository (supervised m and u estimation). The Splink library is not integrated; add it as an evaluation baseline |
| `services/nel` | API, batching limits, backpressure, metrics implemented and tested with a gazetteer backend. **BELA is not wired in**: spike A (ADR-001) must supply the adapter (`NEL_BACKEND=module:factory`) |
| `services/blink` | API, FAISS or numpy index, rebuild on file change implemented and tested with a stand-in model. **Fine-tuned BLINK models are not wired in**: spike B (ADR-002) must supply the adapter (`BLINK_BACKEND=module:factory`) |
| `services/llm` | Launch script, checksum-verified model fetch, schema-constrained client implemented. No model is pinned yet (spike C) |
| BLINK training | Orchestration and hard-negative mining implemented; command flags in `training/blink/config.yaml` are unconfirmed against upstream |
| Database persistence (`store.py`, `load_catalog`) | Written against migration 0002; not run, no PostgreSQL server was available |
| `config` thresholds | Initial plan values, status `provisional`. Not calibrated on gold data |

## Not yet measured

No result below exists yet, and none may be quoted on the website until it does:
BELA, BLINK pretrained, and fine-tuned BLINK accuracy; bge-m3 retrieval recall; any gold-set
precision or recall; the plan targets (95 percent precision at 80 percent recall, 50 percent fewer
false links than RapidFuzz, +20 points from fine-tuning, review rate at most 20 percent, 20
passages per second). Gold sets must be annotated first (`data/labeling/README.md`).

Offline checks so far use a fictional generated catalog (`synthetic.py`). On that data the
fuzzy baseline with state blocking is already strong, so it does not separate the systems. These
numbers verify that the code works; they are not evidence about real data.

Measured on a laptop CPU with stub services (pipeline overhead only): about 580 structured records
per second with the trigram retriever, and 10,000 articles through chunking and routing in seconds.
Real throughput depends on BELA, BLINK, and the LLM.

## Next steps

1. Run spikes A to C and write ADR-001, ADR-002; implement the two backend adapters.
2. Load real data (`make data`, `make etl`), then annotate both gold sets.
3. `make training-data`, `make train`, `make eval --with-vector`; calibrate and freeze `resolution_config_v1`.
4. Add Splink as a baseline in `evaluation/systems.py` and the BELA-only and BLINK zero-shot news systems.

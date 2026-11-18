# Model card: resolution models

Status: draft. Sections marked "not measured" have no result yet.

## Models

| Model | Role | Source | State |
|---|---|---|---|
| BELA | Mention detection and linking to Wikidata | Open-source BELA release (MIT) | Not integrated (spike A) |
| BLINK bi-encoder and cross-encoder | Retrieval and re-ranking over the company catalog | Open-source BLINK release (MIT), fine-tuned here | Not trained (spike B) |
| bge-m3 | Name and description embeddings, 1024 dimensions | BAAI/bge-m3 (MIT) | Used by the knowledge base build |
| Fellegi-Sunter scorer and logistic combiner | Combine match features | This repository | Implemented; fitted by `make fit` |
| Isotonic calibration | Calibrated match probabilities | This repository | Implemented; fitted by `make fit` |
| Local LLM | Adjudicates ambiguous news links among five candidates | Pinned build recorded in `services/llm/models.lock.json` | Not pinned (spike C) |

This project builds on the open-source BELA and BLINK releases and is not affiliated with their authors.

## Intended use

Linking company names in regulator records, supplier lists, and news text to canonical companies so
that public records can be reviewed by people. Outputs are leads for human review, not
determinations about any company.

## Training data

Synthetic mentions generated from the canonical company table (`make training-data`): name
perturbations (legal suffixes, abbreviations, typos, token order, location and plant suffixes),
hard negatives, and splits by company. Gold-set companies are excluded. Data hashes are written to
`data/training/summary.json` and must be copied here after each run.

## Evaluation

Not measured on a gold set (none exists yet); a synthetic run is reported below. The harness (`make eval`) reports recall at 1, 5, 10, accuracy at 1, precision and
recall at the accept rule, precision at 80 percent recall, NIL F1, review rate, false links per
1,000 records, parent roll-up accuracy, p50 and p95 latency, and throughput.

### Evaluation re-run, 2026-11-18 (`make eval`, then `make publish-metrics`)

Data: **synthetic** held-out company split built from 20,000 fictional companies (6,497 queries: perturbed names of
companies the models never saw, plus 10 percent names that exist in no catalog). No gold set exists yet, so this is not a gold
result. Configuration `resolution_config_v1`, status provisional (thresholds not yet fitted on gold labels).

| System | Precision of accepted | Matched automatically | Sent to review | False links per 1,000 | accuracy@1 | recall@5 |
|---|---|---|---|---|---|---|
| RapidFuzz with state blocking | 97.9% | 76.8% | n/a | 14.6 | 0.966 | 0.998 |
| Fellegi-Sunter only | 100% | 39.3% | 55.1% | 0.0 | 0.979 | 1.000 |
| Hybrid (trigram retrieval and Fellegi-Sunter; no BELA, BLINK, or learned retriever) | 100% | 39.3% | 55.1% | 0.0 | 0.979 | 1.000 |

How to read it:

- The routed systems made no false link in this sample, and the fuzzy baseline made 14.6 per 1,000. That is the benefit of
  routing uncertain cases to people.
- The price is workload: the routed systems matched 39 percent of records automatically and sent 55 percent to review, against 77
  percent matched automatically by the baseline. Precision alone hides this, so the website shows all three figures together.
- The hybrid row equals the Fellegi-Sunter row because no second retriever, BLINK model, or language model was in the run, so
  nothing could change the result. It is not evidence that those components do not help.
- The accept threshold (0.90 with a 0.10 margin over the runner-up) is provisional and conservative. Fitting it on gold
  labels is the largest lever on the review rate. The NIL F1 values (0.25 and 0.48) show that names absent from the catalog are
  the weak spot: the models rarely say "none of these" confidently.
- Synthetic perturbations are the ones the generator knows about. Do not expect real supplier files to behave the same way.

## Limits and failure modes

- Coverage of structured sources is US only; non-US companies are mostly reachable through news.
- Similar names (for example food versus food service), common words in names, and parent versus
  subsidiary confusion are the expected main error classes; they are the hard cases in the gold set.
- Generic or very short names can match many companies; such records are routed to review.
- Names absent from the catalog must resolve to NIL; the NIL F1 metric tracks this.
- When BLINK or the LLM is unavailable, results carry a reduced-confidence flag and go to review.
- Article text is untrusted input to the LLM; output is schema-constrained and validated.

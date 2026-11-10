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

Not measured. The harness (`make eval`) reports recall at 1, 5, 10, accuracy at 1, precision and
recall at the accept rule, precision at 80 percent recall, NIL F1, review rate, false links per
1,000 records, parent roll-up accuracy, p50 and p95 latency, and throughput.

## Limits and failure modes

- Coverage of structured sources is US only; non-US companies are mostly reachable through news.
- Similar names (for example food versus food service), common words in names, and parent versus
  subsidiary confusion are the expected main error classes; they are the hard cases in the gold set.
- Generic or very short names can match many companies; such records are routed to review.
- Names absent from the catalog must resolve to NIL; the NIL F1 metric tracks this.
- When BLINK or the LLM is unavailable, results carry a reduced-confidence flag and go to review.
- Article text is untrusted input to the LLM; output is schema-constrained and validated.

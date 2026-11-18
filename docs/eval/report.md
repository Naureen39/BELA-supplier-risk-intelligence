# Resolution evaluation report

Generated: 2026-11-18 13:18 UTC
Data: SYNTHETIC held-out company split (no gold set available yet; not a gold result) (6497 records)

| System | accuracy@1 | recall@5 | recall@10 | precision | recall | nil_f1 | false_links_per_1000 | precision@recall_target | review_rate | p50_ms | p95_ms | records_per_second |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rapidfuzz_state_blocking | 0.966 | 0.998 | 0.999 | 0.979 | 0.768 | 0.480 | 14.622 | 0.979 | n/a | 1.725 | 18.047 | 251.9 |
| fellegi_sunter_only | 0.979 | 1.000 | 1.000 | 1.000 | 0.393 | 0.248 | 0.000 | 0.998 | 0.551 | 2.333 | 2.730 | 435.0 |
| hybrid_trigram_only | 0.979 | 1.000 | 1.000 | 1.000 | 0.393 | 0.248 | 0.000 | 0.998 | 0.551 | 2.279 | 2.596 | 447.4 |

Precision and recall use each system's accept rule (the routing rule for the hybrid,
a fixed score threshold for baselines). `precision@recall_target` is read from the
precision-recall curve at the target recall.

- Resolution config: resolution_config_v1 (provisional).
- BLINK and BELA systems require their services; run with the service URLs configured.

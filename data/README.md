# Data folder

Purpose: acquisition, registry, and evaluation data for the supplier risk platform. Raw downloads
are git-ignored and rebuilt by scripts. Small curated files (gold sets, seed, labeling config)
are committed. Every source is registered in `manifest.yaml` (URL, terms, retrieval date, size,
SHA-256 of each downloaded file).

## Rebuild

```
cp .env.example .env      # set SEC_USER_AGENT and CONTACT_EMAIL, then export them
make setup
make data                 # downloads, records hashes, prints row counts
make gdelt                # one harvest run; schedule with infra/cron/gdelt.cron
make test lint
```

Scripts are idempotent and resumable: completed files are skipped, partial downloads resume,
HTTP responses are cached under `.cache/http`. Run `python -m data.scripts.verify_manifest --counts`
to verify hashes and print row counts.

## Layout

See `PLAN_supplier_risk.md` section 5.1. Source URLs for bulk files live in `scripts/sources.yaml`.

## Scripts

| Script | Output |
|---|---|
| download_edgar, download_exhibit21 | `raw/edgar/` |
| parse_exhibit21, evaluate_exhibit21 | subsidiary rows; parse success rate |
| download_gleif | `raw/registry/gleif/` |
| build_wikidata_subset | `raw/knowledge_base/wikidata/*.parquet` |
| download_epa_echo, download_osha, download_nhtsa, download_cpsc, download_fda | `raw/regulators/*` |
| harvest_gdelt | `raw/news/gdelt/YYYY-MM-DD.jsonl` |
| fetch_article_text | `raw/news/articles/*.jsonl` (snippets only) |
| download_hf_datasets, download_mewsli_x | `raw/news/cc_news/`, `raw/eval/mewsli_x/` |
| gold_agreement | Cohen's kappa for annotator pairs |

## Licensing register

| Source | License or terms | Attribution | Redistribution |
|---|---|---|---|
| SEC EDGAR | Public filings; fair access policy (declared User-Agent, request limit) | Credit SEC | Facts may be republished; do not mirror bulk files |
| GLEIF Golden Copy | GLEIF LEI data terms of use (CC0 1.0) | Credit GLEIF | Permitted under the terms |
| Wikidata | CC0 1.0 | Credit Wikidata | Permitted |
| EPA ECHO | US government data; quality before Nov 2000 unknown | Credit EPA | Confirm before redistribution |
| OSHA (US Department of Labor) | US government data; terms to be confirmed (ADR-003) | Credit US Department of Labor | Confirm before redistribution |
| NHTSA recalls | No terms stated; treat as US government data and confirm | Credit NHTSA | Confirm before redistribution |
| CPSC recalls | US government API; confirm terms | Credit CPSC | Confirm before redistribution |
| openFDA | US government data; confirm terms | Credit FDA | Confirm before redistribution |
| GDELT | Free for research use; metadata only | Credit GDELT | Store metadata only |
| Article text | Publisher copyright | Link to the source | Store snippets of at most 300 characters; no full text |
| Multilingual CC-News | Publisher copyright; non-commercial testing | Credit dataset authors | Do not redistribute |
| Mewsli-X | Apache-2.0 per dataset card | Credit dataset authors | Permitted under the license |
| Models (later phases) | Per model card (BELA MIT, BLINK MIT, bge-m3 MIT, Qwen3 Apache-2.0) | Credit model authors | Per license |

This project builds on the open-source BELA and BLINK releases and is not affiliated with their authors.

## Status of Phase 1 exit criteria

Implemented and unit tested: all download and harvest scripts, checksum manifest, Exhibit 21
parser, article fetcher, Wikidata subset builder, labeling configuration, em dash CI check.
Requires running with network access and credentials (not yet done): populated `raw/`, 48 hour
harvester run, Exhibit 21 success rate on 50 or more real filings, OSHA access confirmation.

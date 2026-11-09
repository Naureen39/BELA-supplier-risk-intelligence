# ADR-003: OSHA enforcement data access method

Status: Proposed (decision pending verification, see below)
Date: 2026-11-09

## Context

The plan requires OSHA inspection, violation, and penalty records. The legacy enforcement data
catalog redirects to the US Department of Labor data portal (https://data.dol.gov/). Current
access terms and bulk file availability have not yet been confirmed from this repository.

## Options

1. DOL data portal API (free registration, API key). Preferred: official, current, incremental.
2. Bulk files from the portal, if offered.
3. Archived copy on DataLumos (https://www.datalumos.org/datalumos/project/100441/view). Fallback;
   snapshot in time, terms to be confirmed on the project page.

## Decision

Implement option 1 and option 3 in `data/scripts/download_osha.py` (`--method api` and
`--method archive`). Select the production method after the verification steps below, then
update this ADR to Accepted.

## Verification steps (owner: data engineer)

1. Register for a DOL API key; confirm the OSHA inspection and violation datasets and their
   field names (data dictionary) and record them in `data/README.md`.
2. Confirm rate limits and terms of use; record in the licensing register.
3. If the API lacks full history, download the archive copy and record its terms.
4. Record the 2015-onward row counts for inspections and violations in the row count report.

## Consequences

The ETL in phase 2 reads `raw/regulators/osha/` regardless of method; the field mapping is
isolated in the phase 4 normalizer.

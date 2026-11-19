# Data guide

## Two kinds of data

| | Demo data (what `make demo` loads) | Source data (what the downloaders fetch) |
|---|---|---|
| Companies | 1,500 fictional companies from the catalog generator (`app/resolution/synthetic.py`), 15 percent with a parent | Real companies: SEC EDGAR, GLEIF, Wikidata |
| Events | 3,000 generated records in the shape of regulator and news events | EPA ECHO, OSHA, NHTSA, CPSC, openFDA, GDELT |
| Business data | A generated subscription business: tenants, plans, invoices, usage (`data/scripts/generate_demo_business_data.py`) | none |
| Suppliers | A messy list of 250 names made from the catalog (case changes, dropped suffixes, abbreviations, typos), resolved through the real pipeline | the customer's own list |
| Use | Trying every page and the API; tests | Real use |

**The demo contains no real company data.** Names are fictional (a coincidence with a real name is possible and
unintended) and the screens label tenant, revenue, and portfolio figures as demo data.

**Real source data has not been downloaded in this repository.** The downloaders and checksum manifest are built and unit
tested, but running them needs network access and credentials (`SEC_USER_AGENT` with a contact address, `CONTACT_EMAIL`,
optionally an openFDA key) and the OSHA access decision in `docs/adr/ADR-003-osha-access.md`. Nothing in the demo depends
on them.

## Rebuilding the source data

```
cp .env.example .env     # set SEC_USER_AGENT and CONTACT_EMAIL, then export them
make setup
make data                # downloads, records SHA-256 of every file in data/manifest.yaml, prints row counts
make gdelt               # one news harvest run; schedule with infra/cron/gdelt.cron
make migrate && make etl # build the canonical company table in PostgreSQL
make data-verify         # re-check every file against the manifest
```

Scripts are idempotent and resumable. Raw files stay out of git (`data/raw/`); the manifest records each source's URL,
terms, retrieval date, size, and checksum. Per-script outputs are in `data/README.md`.

## What the platform stores

- **Companies:** canonical name, aliases, identifiers (CIK, LEI, Wikidata id), headquarters, industry, ownership edges
  with source and as-of date, facilities with coordinates.
- **Events:** source, type, severity, dates, a title and short summary, the URL of the public record, and the links to
  companies with method, score, route, and candidates. Article text is not stored: snippets are capped at 300 characters.
- **Tenant data:** uploaded supplier names and attributes, resolution results, scores and their components, alerts, review
  decisions, reports, and the audit log. Tenant identifiers (for example a tax number) are encrypted with `DATA_KEY`.
  Retention per tenant is enforced by the purge job (`docs/runbook.md`).

## Custom data and corrections

Customers flag wrong links and outdated records in the application; the request goes to the platform review queue.
Customer lists are not used to train models unless the tenant allows it, and feedback is stripped of tenant identifiers
before any use.

## Licensing

Terms for every source are in `docs/licensing.md` and `data/manifest.yaml`. Several US government sources state no terms:
confirm them before redistributing any data.

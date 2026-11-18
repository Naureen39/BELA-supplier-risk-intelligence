# Product application (Phase 9)

Code: `apps/web/src/app/app/` (pages), `apps/web/src/components/app/` (shell and shared components),
`apps/web/src/lib/app/` (data hooks, session, store, formatting). The application is client rendered, reads the live
API through the same-origin `/api` proxy, and is served under `/app`. Tests: `apps/web/e2e/app.spec.ts` (Playwright
with axe-core), `apps/web/tests/app-lib.test.ts` (Vitest), and `apps/api/tests/api/test_event_evidence.py`.

## Running the end-to-end suite

```
E2E_ADMIN_URL=postgresql://user@host:port/postgres VALKEY_URL=redis://host:port/0 apps/web/e2e/reset.sh
cd apps/web && npm run build && PSQL=/path/to/psql E2E_DB_URL=<url printed by reset.sh> npm run e2e
```

`reset.sh` rebuilds the `web_e2e` database (migrations, the synthetic business data, a demo tenant with a user for
every role, twelve companies with ownership edges, facilities, and events), starts the API, uploads a messy supplier
list through the API, scores it, and clears the login rate limit counters. The suite changes data (reviews are decided,
alerts dismissed, users invited), so reset before every full run. `PSQL` and `E2E_DB_URL` are used by one test that adds an
event directly in the database to prove that a live alert reaches an open page; that test is skipped without them.

## What is built

- **Shell:** grouped sidebar that shows only the entries a role's permissions allow, top bar with search (Ctrl K or
  Cmd K command palette over suppliers, companies, and pages), tenant name, live alert bell (server-sent events), theme
  toggle (light and dark), user menu, skip link, error boundary, mobile navigation drawer. Sessions renew silently when
  the access token expires (one shared refresh for concurrent requests), and the application signs out after 30 minutes
  without activity. A failed route guard sends the user to `/login`. The browser never relies on hidden entries for
  protection: the API enforces every permission.
- **Components:** DataTable (sorting, column chooser, saved views kept in the browser, CSV export), ChartCard (ECharts
  with a table view, CSV and PNG export, loading, empty, and error states), US map (choropleth plus facility points,
  no tiles), KPI card with sparkline, date range bar (presets, custom range, granularity, comparison), confirm dialog,
  toasts, upload wizard, correction dialog.
- **Overview:** six KPIs, portfolio risk index, live alert feed, events by type, US map, top risk suppliers. Viewers see
  figures computed from the lists they may read; managers also get the analytics charts.
- **Suppliers:** search, resolution status, risk level, and tier filters; column chooser; saved views; bulk tier change;
  upload wizard (template download, drag and drop, column mapping, validation preview, progress, result counts and export).
- **Supplier detail:** header with identifiers and confidence, tabs for the score breakdown (every component and its
  weights), events timeline with source links and the path from a subsidiary or parent, family, facilities (map and
  table), source records, and activity; tier change, report request, and correction request.
- **Review queue:** the uploaded record beside ranked candidates with field-by-field agreement and model scores, accept,
  choose another, none of these, mark unresolved, not in the database, bulk accept above a chosen confidence, and
  keyboard shortcuts (J, K, A, R, U). Destructive choices ask for confirmation.
- **Events and event detail:** filtered feed with grouped duplicates; evidence viewer (the stored sentence with company
  names highlighted for news, the record fields for regulators), the suppliers the event reaches with the path, and the
  resolution transparency panel listing every candidate with its scores and the final decision.
- **Alerts:** queue with filters, bulk acknowledge, a drawer with history, comments, assignment, status changes, and a
  dismissal that requires a reason; a rules tab (create, edit, turn on and off) for managers.
- **Explorer:** company search, graph (Cytoscape with the fcose layout), neighbor expansion, edge source filter,
  details with source and as-of date, shortest path, events as nodes, concentration chart, PNG and CSV export.
- **Analytics:** every chart in the plan's section 9.2 with range, granularity, comparison, source filter, "as of" date,
  and the Demo data label. **Revenue:** the ten KPIs and the charts in section 9.1, cross-filtering by clicking a plan,
  region, or industry bar, billing health, and a customer table with a drill-down drawer.
- **Reports, data sources, billing, administration, settings:** report list and creation with PDF download; source
  freshness and license notes; plan, supplier usage meter, and invoices; users and roles, API keys (shown once, revoke with
  confirmation), audit log with hash chain verification and export, risk configuration with version history, security
  settings; profile, multi-factor setup with a QR code, sessions, theme.
- **Backend changes made for this phase:** the event detail now returns `evidence` (text, highlighted spans, record
  fields) and `reaches_suppliers` (with the path); live alerts carry the supplier name; Next.js compression is off so the
  proxied alert stream is not buffered (the reverse proxy compresses in deployment).

## Measured results

| Check | Result |
|---|---|
| End-to-end suite (marketing, authentication, application) | 94 tests, run against the live API and a seeded database |
| Application pages through axe-core (WCAG 2.0 to 2.2 A and AA plus best practices) | 0 violations on 11 manager pages in the light theme and in the dark theme; light theme on the revenue, billing, and administration pages |
| Role restrictions | viewer and finance navigation checked, restricted pages show the API's refusal |
| Silent token renewal | the access cookie is removed and the next page load still works |
| Live alert | an event inserted in the database shows as a toast and on the bell within 20 seconds |
| Vitest | 20 tests including permission names matched against the API matrix and spreadsheet formula neutralization |
| Backend | evidence, highlighted spans, and the supplier path checked in three tests, including row level security |

Axe results are saved in `docs/quality/axe-app.json`.

## Not done or not verified

- **No virtualization.** Tables page with a "Load more" button instead.
- **Fields the API does not provide.** The supplier list cannot filter by state, industry, or parent; bulk tagging
  changes the tier only; alerts cannot filter by level or rule; there is no supplier note, no invoice PDF, and no way to
  end other sessions. These need API endpoints first.
- **Merge duplicates** is not in the review screen (the endpoint exists). Language model scores are not shown because
  the pipeline stores none for these links.
- **Explorer** has no facility nodes and no relationship-type filter (the edge payload has no type).
- **Maps** show the contiguous states. Alaska, Hawaii, and territories appear in the table view only. ARR by region is a
  bar chart because the data has no state-level revenue.
- **Idle timeout** (30 minutes) is implemented but not tested, because the test would have to wait that long.
- **Not measured:** Lighthouse on application pages, layouts at 375 to 1920 px for every application page (axe ran at
  1280 px, and the mobile drawer was not exercised), the dark theme on the revenue, billing, and administration pages,
  and the platform administrator role (it requires multi-factor enrollment; its pages are covered through the finance
  role).
- **Saved views** are stored in the browser, so they are not shared between devices or people.
- **Comparison and filters** on analytics depend on `portfolio_stats_daily`, which is demo data; live tenants without it
  fall back to live tables with fewer series.
- **CI:** the web and end-to-end jobs are defined but have not run on GitHub.

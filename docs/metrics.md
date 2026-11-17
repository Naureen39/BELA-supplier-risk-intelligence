# Business data, revenue metrics, and analytics (Phase 7)

All revenue, usage, and portfolio statistics here are **demo data**. The tenants are fictional and
the figures come from a seeded generator. Responses that contain them carry `"demo_data": true`.

Code: `apps/api/app/analytics/` (`revenue.py`, `forecast.py`, `tenant.py`, `loader.py`, `common.py`),
`routers/revenue.py`, `routers/analytics.py`, `core/cache.py`, migration `0006_analytics.py`.
Generators: `data/scripts/generate_demo_business_data.py`, `generate_demo_portfolios.py`.
Tests: `apps/api/tests/api/test_phase7.py`.

## Running it

```
make load-demo-data    # generate data/synthetic/*.csv (seed 42), load them, refresh the views
make metrics-refresh   # rebuild the views only; run nightly from cron or the scheduler
make demo-portfolios   # ERP-style supplier files plus answer files, sampled from the companies table
```

`POST /platform/revenue/refresh` rebuilds the views on demand (finance and platform roles) and drops
the response cache. Loading replaces the demo tenants listed in `tenants.csv` and everything that
belongs to them. `data/synthetic/` is git-ignored because it is regenerable (identical bytes for the
same seed).

## Metric definitions (single source of truth)

The definitions are SQL: the views in migration `0006` and `KPI_SQL` in `analytics/revenue.py`.
Python only slices the monthly series and shapes the response.

| Metric | Definition |
|---|---|
| MRR | Sum of monthly-equivalent recurring fees of subscriptions active at month end. Annual price divided by 12. A subscription is active when `started_on <= month end` and `ended_on` is empty or after month end. Overage is reported separately and is never MRR. |
| ARR | MRR times 12. |
| New, expansion, contraction, churn MRR | Per tenant and month, comparing MRR to the previous month: new (0 to positive), expansion (up), contraction (down but positive), churn (positive to 0). A plan change is an expansion or a contraction. Reactivation counts as new. |
| Net new MRR | new + expansion - contraction - churn. It equals the MRR change of the month exactly (tested). |
| Gross and net revenue retention | Over the 12 months to the month shown, for tenants with MRR 12 months earlier: GRR = sum(min(MRR now, MRR then)) / sum(MRR then). NRR = sum(MRR now) / sum(MRR then). Shown as percent. |
| Logo churn | Tenants that churned in the month divided by tenants active at the start of the month, in percent. |
| ARPA | MRR divided by active customers. |
| Quick ratio | (new + expansion) / (contraction + churn), summed over the trailing 3 months to dampen noise. Empty when there were no losses. |
| CAC | Marketing spend divided by new customers, trailing 3 months. Empty when a filter is active, because spend is not attributed to plan, region, or industry. |
| CAC payback (months) | CAC divided by (ARPA times gross margin). |
| LTV | ARPA times gross margin divided by monthly logo churn (trailing 3 months). Empty when churn is zero. |
| Gross margin | A fixed 80 percent assumption, returned as `gross_margin_assumption` so the interface can show it in a tooltip. |
| Cohort retention | For tenants grouped by first subscription month: cohort MRR in month N divided by cohort MRR in month 0, in percent. With a plan filter the plan at the signup month is used. |

Views (refreshed by `refresh_views`, recorded in `metric_refresh_log`): `mrr_monthly` (month, tenant,
plan), `mrr_movements` (tenant and month with the four movements), `cohort_retention`, and
`revenue_by_dimension` (plan, region, industry, channel). They span the first subscription month to
the latest month with billing data, not a fixed window. Fast paths (`cohort_retention`,
`revenue_by_dimension`) serve unfiltered requests, and a live query serves filtered ones; a test
asserts both return the same numbers.

Modelling choices in the demo data (also in the generator header): annual customers are invoiced
monthly at the monthly equivalent; price changes apply on their change date; a tenant that churns in
a month has no invoice for that month because MRR is measured at month end; invoice dates are
month ends and an invoice is `open` only before its due date as of the last invoice date in the data.

## Forecast

`GET /platform/revenue/forecast` fits exponential smoothing (statsmodels `ETSModel`) to the monthly
MRR history. It tries four specifications (additive or multiplicative error, with a damped, plain, or
no additive trend), keeps the lowest AICc, and returns a 6 month projection with an 80 percent
prediction interval. It is labelled `Estimate` and is not a commitment. At least 12 months of history
are required. A hold-out backtest on the last 6 observed months is returned next to it.

Measured on the seeded dataset: selected model ETS(additive error, additive trend); backtest MAPE
4.25 percent; the 80 percent interval covered 66.7 percent of the six actual values (4 of 6). With six
points that is a weak check, but it points the same way as common experience with short series: treat
the interval as optimistic.

## Endpoints

Revenue (prefix `/api/v1/platform/revenue`, roles `finance_analyst` and `platform_admin`):

| Path | Content |
|---|---|
| `GET /summary` | Latest MRR, ARR, customers (unchanged shape from Phase 5). |
| `GET /kpis` | The ten KPI cards: value at the last month of the window, the same metric one window earlier, percent change, sparkline. |
| `GET /mrr` | MRR by month and plan, plus `business_events` annotations. |
| `GET /movements` | Start MRR, new, expansion, contraction, churn, net new, end MRR per month. |
| `GET /mix` | Invoiced subscription, overage, and credits per month. |
| `GET /forecast` | Projection described above (`horizon` 1 to 12). |
| `GET /cohorts` | Retention heatmap data. |
| `GET /breakdown` | ARR and share by `dimension` = plan, region, industry, or channel. |
| `GET /concentration` | Top 10 customers by ARR share with a cumulative share. |
| `GET /unit-economics` | CAC, LTV, LTV to CAC, payback, ARPA per month. |
| `GET /billing-health` | Open and overdue invoices, aging buckets (current, 1-30, 31-60, 61-90, 90+). |
| `GET /customers`, `/customers/{id}` | Customer table (sort, status, paging) and drill-down. |
| `POST /refresh` | Rebuild the views now. |

Common query parameters: `from`, `to` (months in the range), `granularity` (`month` only; revenue is
recorded monthly and other values return 422), `compare=true` (previous period of equal length),
`plan`, `region`, `industry` (cross-filters), and `format=csv`. Every JSON response includes
`demo_data` and `data_as_of` (when the views were refreshed and the latest month they cover).

Tenant analytics (prefix `/api/v1/analytics`, role manager and above, API keys with the rules scope):

| Path | Content |
|---|---|
| `GET /portfolio` | KPI cards (risk index, suppliers at high or critical, events in period, auto-resolution rate, review queue size, median review time, false links per 1,000), risk index trend with level bands, suppliers by level, events by type, event source mix, risk by state with facility events, tier by category heatmap, concentration by parent, top risk suppliers with sparklines and 30 day change. `source` filters events (`regulator`, `news`, or one source). |
| `GET /quality` | Resolution quality over time, review workload, reviewer correction rate, false links, hybrid versus baselines (from `docs/eval/metrics.json`), latency and throughput, routing flows (Sankey data), data freshness. |
| `GET /usage` | Daily usage, bucketed by `granularity`, with a comparison period. |

Parameters: `from`, `to`, `granularity` (`day`, `week`, `month`), `compare`, `format=csv` with `section=`
(required for `portfolio` and `quality`, which hold several tables). Series come from
`portfolio_stats_daily` when it has rows for the window (and the response says so with
`series_source` and `demo_data`); otherwise from live tables.

Caching: revenue responses are cached for 5 minutes and tenant analytics for 1 minute, in Valkey when
`VALKEY_URL` is set and in process otherwise. A refresh drops every entry. The `X-Cache` header says
`hit` or `miss`. Tenant entries are keyed by tenant and are not invalidated by writes, so they can lag
by up to a minute.

## Security notes

Materialized views cannot carry row level security, so the tenant database role has no access to the
revenue views, `marketing_spend`, or `business_events` (migration `0006` revokes it; a test confirms
`InsufficientPrivilege`). The revenue API checks the permission and then reads with the system
connection. Tenant analytics run on the tenant connection, so row level security scopes every query,
and a test checks one tenant's totals exclude all others. CSV cells starting with `=`, `+`, `-`, or
`@` are prefixed to prevent formula injection.

## Verification

Measured locally (PostgreSQL 17, in-process test client, 187 demo tenants, 36 months, 74,627 usage
rows):

| Step | Result |
|---|---|
| Generate all files | 0.37 s, byte-identical on a second run |
| Load all tables | 0.58 s |
| Refresh the four views | 0.03 s |
| KPI query (execution) | 2 ms |
| Slowest cold revenue endpoint over 12 request shapes | 38 ms (limit 500 ms) |
| Ending ARR of the demo data | 8.60 million USD with 144 customers (plan envelope 5 to 9 million) |

Reconciliation tests: for every month, new + expansion - contraction - churn equals the change in
total MRR exactly, each month starts where the previous one ended, MRR from SQL equals MRR computed
independently from the CSV rules, NRR and GRR equal an independent computation, invoice totals equal
the sum of their lines, and invoiced subscription fees equal MRR for the month.

## Not done or not verified

- **Frontend charts** (ECharts, maps, Sankey rendering) belong to Phase 9. These endpoints return the
  data they need. The US state boundary file for the choropleth is not bundled yet.
- **Scheduling:** the nightly refresh is a command (`make metrics-refresh`), not a scheduled job.
- **Latency figures are not a benchmark.** They come from an in-process client on a small dataset;
  Phase 10 measures with Locust against the running stack.
- **The platform latency and throughput series are synthetic.** The `throughput_rps` column was added
  for the dashboard; no real ingestion path writes it yet.
- **Data freshness** reports the latest event time per source, not the last successful run, because
  no run log exists yet. The fresh and stale thresholds (2 days for news, 10 days otherwise) are
  configured defaults.
- **False links per 1,000** counts wrong-link corrections filed by reviewers, so it undercounts links
  nobody noticed. The hybrid versus baselines chart shows `null` until `make eval` has written
  `docs/eval/metrics.json`, and that file currently reflects a synthetic split, not a gold set.
- **Portfolio events** count events linked directly to a supplier's company. Events reaching a
  supplier through its corporate family appear in risk scores and alerts, not in these counts.
- **Routing flows** include only the routes uploaded suppliers take (identifier, model, reviewer).
  BLINK and language model adjudication apply to news mentions.
- **Customer table** reads up to 5,000 customers and sorts in memory.
- **The portfolio generator** was tested on a generated catalog, not on a populated `companies`
  table, because none is loaded here. It has not been run with `--from-db`.
- **Forecast backtest** covered 66.7 percent of actuals for an 80 percent interval (6 points).
- **Plan filters:** retention and cohorts use the plan at the base month; other metrics use each
  month's plan.

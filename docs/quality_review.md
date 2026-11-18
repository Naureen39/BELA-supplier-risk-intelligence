# Quality review (Phase 10)

Accessibility, cross-browser testing, defects found, and the state of the Definition of Done. Reviewed 2026-11-18.

## Accessibility audit

**Automated (axe-core 4, rules WCAG 2.0 A and AA, 2.1 A and AA, 2.2 AA, and best practices).**

| Scope | Runs | Violations |
|---|---|---|
| 32 marketing and sign-in pages at 375 px and 1280 px, in Chrome | 64 | 0 |
| The same pages in Firefox | 64 | 0 |
| The same pages in WebKit (the engine behind Safari) | 64 | 0 |
| Application pages in Chrome: 11 manager pages in the light theme and in the dark theme, plus revenue, billing, and administration in the light theme | 25 | 0 |
| Lighthouse accessibility score, 5 pages (Phase 8) | 5 | 100 on each |

Results are saved in `docs/quality/axe.json` (marketing, Chrome) and `docs/quality/axe-app.json` (application).

**Keyboard and focus (automated tests).** Skip link on the marketing site and in the application; the mega menu opens with
Enter, moves with Tab, and closes with Escape; the mobile drawer opens and a link in it works; the command palette opens
with Ctrl K and results can be chosen; the review queue and alert queue have keyboard shortcuts; dialogs hold focus (Radix);
charts have a table alternative that is a focusable region; wide tables are focusable scroll regions with their own label.

**Design rules checked by construction.** Focus rings are visible everywhere (a global rule); controls have labels, hints,
and error messages wired with `aria-describedby`; risk levels and statuses are always text as well as color; the live alert
toast has `role="status"`; reduced motion is honored for animation and the sign-in carousel.

**Not done.**

- **Screen reader testing.** I did not run VoiceOver, NVDA, or JAWS. Axe finds structural problems, not whether the reading
  experience makes sense. Do a manual pass before relying on this.
- **Reflow at 320 px and 400 percent zoom, text spacing overrides, and high contrast mode.** Axe at 375 px passes and the
  marketing pages have no horizontal overflow at 375 to 1920 px, but the stricter WCAG reflow and spacing checks were not
  run, and the application pages were checked at 1280 px only.
- **The ECharts canvases** are an image to assistive technology. The chart card exposes the same numbers in a table, but the
  chart itself has no per-point description.
- **The graph canvas** has the same limit: the details panel and edge list are the accessible path.
- **Color contrast of charts** (series colors against the background) is a designed palette that is color blind safe. It was
  not measured against the 3 to 1 non-text contrast rule.

## Cross-browser tests

`apps/web/playwright.config.ts` runs three projects. Chrome runs the whole suite; Firefox and WebKit run the read-only specs
(`a11y.spec.ts` and `cross-browser.spec.ts`), because the other specs change data and are not repeatable per browser.

| Browser | Version | Tests passed |
|---|---|---|
| Chrome (the full suite: site, flows, application, security) | 157 | 99 of 99 |
| Firefox (Playwright build) | current at install | 69 of 69: accessibility on every marketing page, and the cross-browser spec |
| WebKit (Playwright build, the engine behind Safari) | 27.2 | 69 of 69 |
| Microsoft Edge | **not run** | Edge shares Chrome's engine but is not installed here, so it was not run. |

The cross-browser spec covers: five marketing pages render with their headings and no horizontal scroll; security headers are
served; the skip link and mega menu work by keyboard and the mobile drawer opens; the demo form validates and the cookie
notice is remembered; sign-in, then charts (canvas), the graph, the review queue, and the table's CSV export.

Two browser differences are handled in the tests, not hidden: Safari does not move focus to links with Tab unless a system
setting is on, so the skip link is asserted in Chrome and Firefox only.

**Not done.** Real devices (iOS Safari, Android Chrome) and older browser versions were not tested; Playwright's WebKit is a
build of the engine, not Safari itself.

## Defects found in this phase

Found by the tests and measurements of this phase; each is fixed and covered by a test or a measurement.

| Defect | Found by | Impact |
|---|---|---|
| Rescoring was quadratic in suppliers and events | profiling the monitoring job with 3,000 suppliers and 60,000 events | would have taken minutes per run |
| Supplier and alert lists slowed with portfolio size (row level security and an index with the wrong sort direction) | pg_stat_statements and EXPLAIN | 21 ms at 23,000 suppliers, growing |
| Company search scanned every company | query profile | 27 ms per search |
| Event ingestion rebuilt its index on every call | code review while profiling | quadratic |
| The web application had no content security policy or HSTS | security review | a missing defense in depth |
| Form validation tripped the policy (`new Function`) | the new policy test | policy violation report on `/contact` |
| A database outage returned a 500 | resilience review | wrong signal for clients |
| `assert` used as a runtime guard in three places | Bandit | skipped under `python -O` |
| Failed uploads, webhooks, and email were lost | resilience review | no way to recover them |
| Retention was stored but never enforced | security review | privacy policy promise unmet |
| The single-supplier endpoint did not record the "reduced confidence" flag | resilience test | the flag was invisible on that path |
| Two scroll regions on the methodology page shared a label | axe, after adding a second table | accessibility landmark rule |
| Login rate limits blocked the end-to-end suite | suite failures | made the limits configurable (defaults unchanged) |

## Definition of Done (plan section 11), where it stands

See `PLAN_supplier_risk.md` for the full list. The items that Phase 10 touches:

| Item | State |
|---|---|
| No open high severity defects | No known high severity defect is open. The one high rated dependency advisory (picomatch) has no patched release and is documented with an expiry. |
| Performance targets met or documented | Documented in `docs/perf.md`. Model throughput (BELA, BLINK, the language model) is not measured. |
| Runbook complete | `docs/runbook.md` covers operation, backup and restore (drilled), jobs, and failures. Deployment topology, monitoring, and failover are not covered (Phase 11). |
| ZAP baseline, Trivy image scan | not run (no containers, no Docker here) |
| Screen reader audit | not done |
| Gold evaluation set | does not exist; the evaluation re-run is synthetic and labeled so |
| BELA and BLINK spikes | not run, so the neural linking path is unverified |

## Test inventory at the end of this phase

- Backend: 252 tests, 93 percent coverage of `app`, strict typing clean, lint clean.
- Web unit tests: 20 (Vitest).
- End to end: the full suite is described in `docs/app.md` and `docs/web.md`; this phase added the security spec, the
  cross-browser spec, and the Firefox and WebKit projects.

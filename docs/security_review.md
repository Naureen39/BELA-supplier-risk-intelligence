# Security review (Phase 10)

Reviewed 2026-11-18 against the plan's security specification (section 10). This is a review of the code and the
running application on a development machine. It is not a penetration test and it is not an audit.

## Scanner results

| Tool | Scope | Result |
|---|---|---|
| Bandit | `apps/api/app`, `data`, `services`, `training` (about 11,700 lines) | 0 high, 0 medium, 0 low after review. See the notes below. |
| pip-audit | the Python environment (every dependency of `pyproject.toml`) | No known vulnerabilities. |
| npm audit | `apps/web` | 17 findings, all one advisory (picomatch, GHSA-fc5q-39xc-vjpf, denial of service through crafted glob patterns). No patched release exists: 4.0.7 is the latest and is affected. Reviewed and allowed with an expiry date (see below). |
| Trivy (filesystem: vulnerabilities, secrets, misconfiguration) | the repository without `node_modules` and the virtual environment | The same single picomatch advisory in `package-lock.json`. Nothing else at high or critical. |
| gitleaks | the full git history (8 commits at the time) | 6 matches, all false positives (a throwaway test password and a column name). Allowlisted in `.gitleaks.toml` with the reason. 0 leaks after the allowlist. |
| OWASP ZAP baseline | **not run** | It needs the stack in containers. There is no Docker here and no container images exist yet (Phase 11). The browser tests under "Checks I could run instead" cover part of what the baseline looks for, not all of it. |
| Trivy image scan | **not run** | No images exist yet. |

### Bandit notes

- **B608 (SQL built from strings), 33 places.** Each one was read. In all of them only fixed identifiers are
  interpolated (a column from a fixed map, a view name from a constant tuple, a column name taken from a pydantic model's
  field names, or a SQL fragment that is itself a module constant). Values always go through bound parameters. They carry a
  `# nosec B608` marker so a new, unreviewed case still fails the scan.
- **B101 (assert), 3 places, fixed.** Two in the authentication router and one in the PDF renderer would have been stripped
  under `python -O`. They are now explicit checks that raise.
- **B615 (Hugging Face download without a pinned revision), 3 places, accepted.** The commit hashes were not available to
  pin. Mitigation: model downloads are verified against SHA-256 values in the checksum manifest (`services/llm/fetch_model.py`
  and `data/scripts/verify_manifest.py`). Pin the revisions when the models are fetched for the first time.
- **B311, B112, B105, B404, B603.** Seeded random generators for synthetic data (not security), a deliberate skip of a failed
  model fit, an example value in API documentation, and a subprocess call whose command is fixed by the training
  configuration.

### The npm advisory

The vulnerable package is reached only by development tooling (eslint and vitest) and by the file watcher inside
`next-intl`, which handle patterns the developers write and never user input, and none of it runs in the production
server. `apps/web/audit-allowlist.json` records this, and `npm run audit:gate` (used by CI) fails on any other high or
critical advisory, and fails again on this one after 2026-12-31 so it is revisited.

## Defects found and fixed in this phase

| Finding | Severity | Fix |
|---|---|---|
| The web application sent no content security policy and no HSTS header (the API did). | Medium | Added a policy (`default-src 'self'`, no objects, no framing, forms and connections to the same origin), HSTS, and a cross-origin opener policy. Browser tests confirm the policy blocks nothing the site needs. |
| Form validation (zod) probed for code generation with `new Function`, which the policy reports as a violation. | Low | Switched it to the interpreted path (`jitless`). |
| `assert` statements used as runtime guards. | Low | Replaced with explicit checks (above). |
| Rate limits were fixed in code. | Low | Now configurable per environment (`RATE_LIMIT_*`), defaults unchanged. |
| The retention period was stored but never enforced. | Medium (privacy) | Added the purge job `python -m app.services.retention` with tests, a cron entry, and a dry-run mode. It is a command, not yet a scheduler: install `infra/cron/retention.cron`. |
| Failed background work was lost. | Medium (reliability) | Dead letter queue and retry (see `docs/runbook.md`). |
| A database outage returned a 500 error. | Low | Now a 503 with `Retry-After`, with no internal detail. |

## Requirement by requirement (plan section 10)

Status words: **verified** (an automated test or a measurement in this repository), **implemented** (built, no dedicated
test), **partial**, **not done**.

| Requirement | Status | Evidence or gap |
|---|---|---|
| Argon2id, strength check, common password rejection | verified | `apps/api/tests/api/test_auth.py` |
| Login rate limits, lockout, generic errors, audited failures | verified | `test_auth.py` (login rate limit, failed logins audited without secrets) |
| TOTP with recovery codes, mandatory for administrators | verified | `test_auth.py`, and the end-to-end test that enrolls an administrator |
| Access token cookie (httpOnly, strict), rotating refresh tokens with reuse detection | verified | `test_auth.py`; the browser suite checks the cookie flags |
| CSRF double submit | verified | API tests, and a browser test that a cookie-authenticated write without the header is refused |
| Single-use reset tokens, no account enumeration | verified | `test_auth.py` |
| API keys hashed, scoped, shown once, expiring | verified | `test_auth.py`, `test_rbac.py`, administration end-to-end test |
| Role matrix on the server, every role against every endpoint group | verified | `test_rbac.py` |
| Row level security and cross-tenant tests, through the API and through SQL | verified | `test_rbac.py`, `test_workflows.py`, and the per-phase tests |
| TLS 1.2 or higher with HSTS | partial | HSTS is sent by the site and by the API when enabled. TLS itself is terminated by a reverse proxy (Caddy) that is set up in Phase 11. |
| Encrypted disk volumes for the database host | not done | An infrastructure setting; nothing to verify on a development machine. |
| pgcrypto encryption of tenant identifiers | implemented | `routers/suppliers.py`; the list endpoint reports only whether identifiers exist, and exports leave them out. |
| Tenant lists never used to train without a setting; feedback stripped of tenant ids | verified | `test_workflows.py` |
| Snippets only, not full article text | implemented | Article snippets are capped at 300 characters by a database check, and the news event builder cuts the stored sentence and title to the same limits. |
| Retention with a scheduled purge job | partial | The job exists and is tested. It still has to be scheduled (cron entry provided). |
| Logs free of passwords, tokens, and identifiers | partial | Logs are structured with request identifiers and the code does not log secrets. One test checks that failed logins are audited without secrets. There is no scan of log output for secrets. |
| Hash-chained, append-only audit log, verification | verified | `test_workflows.py`; the restore drill verifies the chain on a restored copy. |
| Upload limits, formula injection protection, content type checks | verified | `test_workflows.py`, and `tests/app-lib.test.ts` for the browser-side CSV export |
| Security headers; CORS off by default | verified | Browser tests check the headers; the API has no CORS middleware. The policy keeps `'unsafe-inline'` for scripts and styles (below). |
| Pinned versions and lock files; Trivy and gitleaks in CI | partial | `package-lock.json` is committed. Python dependencies are not pinned to exact versions and there is no Python lock file. CI runs gitleaks, Trivy, Bandit, pip-audit, and the npm gate. |
| Non-root containers, read-only file systems, internal networks | not done | No container images exist yet (Phase 11). |
| Untrusted article text for the model: delimiters, schema-constrained output, no tools | verified | Phase 3 tests (`apps/api/tests/resolution/`) |
| The model never decides alone; evidence always shown; versions recorded on decisions | verified | Phase 3 and 4 tests; the application shows the candidates and scores |
| Fetcher safety: private ranges blocked, size and time limits, robots.txt | implemented | `data/scripts/fetch_article_text.py` (no redirects, 20 second timeout, size cap, robots). The webhook sender has its own tested guard. Not covered by an automated test. |
| Disclaimers, record-based wording, correction process | verified | Content tests in `apps/web/tests`, and the correction tests |

## Known limitations

- **`'unsafe-inline'` in the content security policy.** Next.js writes inline scripts for hydration. A nonce based policy
  would remove the keyword but makes every page dynamic (no static generation). The remaining protection against script
  injection is that the application never renders untrusted HTML (React escapes text, article text is displayed as text, and
  the one place that writes JSON into a page escapes `<`).
- **Webhook payloads are unsigned**, and there is a small DNS rebinding window between the address check and the connection.
- **Sessions cannot be ended individually** from the interface (no endpoint).
- **No penetration test, no ZAP baseline, no image scan.** Do these before any real use.

## Checks I could run instead of ZAP

Browser tests in `apps/web/e2e/security.spec.ts` (Chrome): the policy reports no violation on any marketing page or on
the main application pages (charts and graph included); a cross-origin request from the page is blocked; pages cannot be
framed; a cookie-authenticated write without the CSRF header gets 403; the session cookie is httpOnly and strict; an
unauthenticated API request gets 401 with `Cache-Control: no-store`. These are checks of known behavior, not a scan for
unknown problems.

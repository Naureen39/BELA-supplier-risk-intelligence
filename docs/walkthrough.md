# Product walkthrough

A script for showing the whole product in about 20 minutes with the seeded demo (`make demo`). Each step names the account,
the page, what to do, and what it shows. Say at the start: **the companies and events are synthetic**; the point is how
the product behaves, not what it says about any real company.

Screens for each step are captured by `make screenshots` (`docs/screenshots/`).

## 1. The marketing site (no sign-in, 3 minutes)

1. `/` : the claim and the product in one screen. Point out the proof strip: precision shown together with how much was
   matched automatically and how much went to a person, labeled synthetic.
2. `/platform` and `/security` : what the product does and how data is protected, in plain language.
3. `/methodology` : data sources and their terms, what has been measured, what has not (the neural linkers, a gold
   evaluation set), and how to correct the record. This page is the honest account of the limits.
4. `/pricing`, then `/contact` : request-a-demo form (submissions are stored; email goes to Mailpit in the demo).

## 2. A manager's day (`manager@demo.example`, 10 minutes)

1. **Sign in** at `/login`. The panel under the form lists the demo accounts.
2. **Overview** (`/app`) : six KPIs, the portfolio risk index, the live alert feed, events by type, and the map. Click an
   alert to open its supplier.
3. **Suppliers** : filter by risk level and tier, change columns, save a view, export CSV. Open a supplier.
4. **Supplier detail** : the score and every component with its weight (severity, recency, link confidence, relationship,
   source reliability), the events timeline with links to the public records, the path from a parent or subsidiary
   ("why does this event reach this supplier"), the family tree, facilities on the map.
5. **Upload** (Suppliers, Upload) : download the template, upload a short CSV with messy names, map the columns, watch
   the counts: automatically resolved, sent to review, unresolved.
6. **Review queue** : the uploaded record beside ranked candidates, field by field agreement and the scores behind each.
   Accept one with `A`, move with `J` and `K`. Say what the system will not do: attach a record to a company without a
   stored score and route.
7. **Event detail** (open any event) : the evidence, the highlighted text for news, the suppliers it reaches, and the
   transparency panel listing every candidate and the final decision.
8. **Alerts** : acknowledge, comment, dismiss with a required reason; the **Rules** tab to change a threshold.
9. **Explorer** : search a company, expand its neighbors, show the shortest path between two companies, the concentration
   chart.
10. **Analytics** and **Reports** : the quality dashboard (resolution rates and review load), then request a supplier PDF
    report and download it.

## 3. Administration (`admin@demo.example`, 3 minutes)

First sign-in asks for multi-factor setup: scan the QR code with an authenticator app and keep the recovery codes.
Then **Administration** : users and roles, create an API key (shown once; use it with `docs/api_guide.md`), the audit
log (the page reports whether the hash chain verifies), risk configuration and its version history.

## 4. The read-only role (`viewer@demo.example`, 1 minute)

Sign in as the viewer: the sidebar shows only what the role may see, and the API refuses anything else (try opening
`/app/admin`). This is the role to use for a public demo.

## 5. The business side (`finance@demo.example`, 3 minutes)

**Revenue** : the KPIs (MRR, ARR, net revenue retention, churn, ARPA), cohort retention, revenue by plan, region, and
industry (click a bar to cross-filter), billing health, and the customer drill-down. Everything is labeled demo data.
`platform@demo.example` (also MFA) adds tenants and the platform review queue, where customer correction requests land.

## 6. Failure behavior (optional, 2 minutes)

`docker compose stop db`, reload any page: the API answers 503 with `Retry-After`, and the pages show their error state with a retry action rather than crashing (check this on your build before showing it).
`docker compose start db`: it recovers without a restart. Mention the dead letter queue and the "Reduced confidence"
notice shown when a model service is down (`docs/runbook.md`).

## Talking points that keep the demo honest

- Scores are leads for human review, not statements of fault; absence of a record is not evidence of good practice.
- Structured regulator coverage is mostly the United States.
- Matching is probabilistic; uncertain cases go to a person.
- The neural linkers and the language model are not trained or run in this build; say so if asked how matching works.

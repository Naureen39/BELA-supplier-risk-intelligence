# Web app and marketing website (Phase 8)

Code: `apps/web/` (Next.js App Router, TypeScript strict, Tailwind CSS 4). Marketing pages are statically
generated. The few pages that show live figures (home and methodology) revalidate hourly. Tests:
`apps/web/tests` (Vitest) and `apps/web/e2e` (Playwright with axe-core). Reports: `docs/quality/`.

```
make web-install       # npm ci (Node 22 or newer)
make web-dev           # development server on :3000, API proxied from :8000
make web-check         # prettier, eslint, tsc, vitest
make web-build         # production build
make web-e2e           # Playwright suite (needs the API and a seeded database, see below)
make web-quality       # build, then Lighthouse on five pages -> docs/quality/
```

End to end setup: `PYTHONPATH=.:apps/api python apps/web/e2e/seed_api.py <admin database URL>` creates and seeds
`web_e2e` and prints its URL; start the API with that `DATABASE_URL`, `COOKIE_SECURE=false`, and
`ALLOW_EPHEMERAL_SECRETS=true`, then run `make web-e2e`.

## What is built

- **Design system:** tokens from the plan in `src/app/globals.css` (colors, type scale, radii, elevations,
  breakpoints), Inter and JetBrains Mono self-hosted through `@fontsource`. Components built on Radix:
  Button, Input, Textarea, Select, Checkbox, Field (label, hint, and error wiring), Badge (risk levels),
  Card, Tabs, Accordion, Drawer, Breadcrumbs, Stepper, Skeleton, EmptyState, BrowserFrame, and a
  `ResponsivePicture` for optimized images. Navigation uses Radix NavigationMenu (keyboard operable).
- **Layout:** utility bar, sticky header with three mega menus and a mobile drawer, footer with a
  newsletter form (double opt-in), cookie notice, skip link, landmarks.
- **Pages:** home, platform, four solutions, six industries (shared template with a labeled illustrative
  scenario), pricing, security, developers, methodology, resources with tag filter and six articles
  (900 to 1,400 words each), company, contact with confirmation page, privacy, terms, and cookies.
- **Authentication screens:** `/login` (including the multi-factor step, enrollment with a QR code and
  recovery codes, and recovery code entry), `/forgot-password`, `/reset-password`, and `/app`, a landing
  page that shows the signed-in user and signs out. The browser calls the API on its own origin: Next.js
  proxies `/api` to the backend, so cookies are same-site and the double-submit CSRF header is sent from
  the `pr_csrf` cookie.
- **SEO:** metadata and canonical URLs, Open Graph images generated at build time for the site, articles,
  industries, and solutions, `sitemap.xml`, `robots.txt`, JSON-LD (Organization, WebSite, Article,
  FAQPage).
- **Image pipeline:** `npm run images` converts `public/images/source/*` to AVIF and WebP at 640, 1024,
  1600, and 2400 px and writes a manifest (tested). No photographs are used yet; see below.
- **Backend additions:** `POST /newsletter` and `POST /newsletter/confirm` (hashed single-use token,
  confirmation email, same reply for known addresses, rate limited) and `GET /public/stats` (counts
  and evaluation figures only), with migration `0007`.

## Measured results

Saved in `docs/quality/` (Lighthouse HTML reports and a JSON summary, and the axe results).

| Check | Result |
|---|---|
| Lighthouse, desktop preset, home | performance 100, accessibility 100, best practices 96, SEO 100, LCP 289 ms, CLS 0, TBT 0 ms |
| Lighthouse, other four pages | performance 100 and accessibility 100 on each; SEO 66 on `/login` because the page is deliberately `noindex` |
| axe-core (WCAG 2.0, 2.1, 2.2 A and AA, plus best practices) | 0 violations on 32 pages at 375 and 1280 px (64 runs) |
| Layout shift on the home hero | below 0.01 (tested with a layout shift observer) |
| Horizontal overflow at 375, 768, 1024, 1440, 1920 px | none on five pages |
| Keyboard | skip link, mega menu open with Enter, move with Tab, close with Escape |
| Vitest | 13 tests: no em dash anywhere in the web app, no AI or vendor tool names, no hype words, article lengths, pricing matches the demo price list, scenarios labeled fictional, message catalogs have equal keys |

Lighthouse ran against the local production build with simulated throttling (40 ms round trip, 10 Mbit/s),
so the absolute numbers say little about a deployed site. They show that the pages are light and stable.

## Not done or not verified

- **No photography.** The plan calls for Unsplash or Pexels photographs with credits. Choosing and
  downloading them needs a person to review each image, so the site uses in-house SVG and CSS
  illustrations instead, and `CREDITS.md` says so. The pipeline and component are ready for photos.
- **No real product screenshots.** The product application is built in Phase 9. Product views on the site
  are drawn illustrations labeled "Illustration of the interface. Demo data." Replace them with
  Playwright captures of the seeded demo tenant once the application exists.
- **Languages.** The language selector lists English, Spanish, French, and German, but only English is
  served. Message catalogs for the other three hold the shell strings (navigation, footer, cookie
  notice) and a test keeps their keys equal. Page content is English, and routes are not locale-prefixed.
- **Proof strip and data coverage** show only figures the API returns. In an environment with no data
  loaded or no evaluation run, the home page says so instead of showing numbers. Precision on the gold set
  and the reduction in false links versus fuzzy matching appear only after `make eval` writes
  `docs/eval/metrics.json`; the file states whether the data is synthetic.
- **Components for the application** (DataTable, Combobox, DatePicker, Dialog variants, Popover, Toast,
  CommandPalette, KPI card, MatchComparison, EvidenceViewer, ChartCard, GraphCanvas, FamilyTree, FileDropzone,
  Timeline, Pagination, Switch) are built in Phase 9 with the pages that use them.
- **State and data libraries** (TanStack Query and Table, Zustand) are not installed yet for the same reason.
- **Visual review** was done on screenshots of the home page at 375, 1440, and the other widths in the
  script, plus automated overflow checks. Every page was not inspected by eye at all five widths.
- **Lighthouse and the end-to-end suite are not in CI as gates.** CI runs lint, types, unit tests, the
  build, `npm audit`, and the end-to-end job; that workflow was written but has not run on GitHub.
- **Mailpit** is not set up here. The newsletter and reset flows were tested with the API's in-memory
  mailer (unit tests) and a seeded reset token (end to end), not with a real mailbox.
- **Contact address** uses a reserved example domain.
- **Legal text** is professional boilerplate for a demonstration product and has not had legal review.

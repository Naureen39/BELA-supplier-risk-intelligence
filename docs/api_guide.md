# API guide

Base URL: `https://localhost/api/v1` in the demo (the examples use `$API`). Interactive reference: `/api/docs`
(OpenAPI at `/api/openapi.json`). Authentication, roles, and rate limits are described in `docs/api.md`.

All examples below were run against the seeded demo.

## Authentication

Two ways, never mixed in one request:

- **API key** (for integrations): `Authorization: Bearer pk_...`. A tenant administrator creates keys in the application
  (Administration, API keys) or with `POST /admin/api-keys`. The secret is shown once. A key carries scopes (`view`,
  `upload_review`, `alert_action`, `manage_rules`), expires, and has its own rate limit. Keys cannot use session-only or
  administration endpoints.
- **Browser session** (for the application): `POST /auth/login` sets httpOnly cookies; state-changing requests also send
  the `X-CSRF-Token` header (the value of the `pr_csrf` cookie).

```
export API=https://localhost   # add -k to curl for Caddy's local certificate
export KEY=pk_...              # from Administration, API keys
```

## curl

List suppliers with their risk (cursor paginated, newest first):

```
curl -s -H "Authorization: Bearer $KEY" "$API/api/v1/suppliers?limit=5"
```

Resolve one record (the matching decision comes back with its evidence: route, probability, and ranked candidates):

```
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"name": "Crescent Pharma Holdings"}' "$API/api/v1/resolve"
```

`route` is `accepted` (matched automatically), `review` (a person decides), or `nil` (no company matched). `degraded:
true` means a model service was unavailable and the result carries reduced confidence.

Upload a supplier list (CSV with a `name` column; `city`, `state`, `tier`, and identifiers are optional), then poll it:

```
curl -s -X POST -H "Authorization: Bearer $KEY" -F "file=@suppliers.csv;type=text/csv" "$API/api/v1/uploads"
curl -s -H "Authorization: Bearer $KEY" "$API/api/v1/uploads/$UPLOAD_ID"     # status, auto_resolved, needs_review, unresolved
```

Score breakdown and events for one supplier:

```
curl -s -H "Authorization: Bearer $KEY" "$API/api/v1/suppliers/$SUPPLIER_ID/risk"
curl -s -H "Authorization: Bearer $KEY" "$API/api/v1/suppliers/$SUPPLIER_ID/events"
```

## Python

```python
import os, httpx

client = httpx.Client(base_url=os.environ.get("API", "https://localhost") + "/api/v1",
                      headers={"Authorization": f"Bearer {os.environ['API_KEY']}"}, timeout=30)

page = client.get("/suppliers", params={"limit": 5}).json()
for s in page["items"]:
    print(f'{s["company_name"] or s["uploaded_name"]:<45} {s["risk_level"] or "unscored":<9} {s["risk_score"]}')

m = client.post("/resolve", json={"name": "Crescent Pharma Holdings"}).json()
print(m["route"], m["probability"], [c["name"] for c in m["candidates"][:2]])
```

For the demo's self-signed certificate pass `verify=False` to `httpx.Client` (development only).

## JavaScript (Node 22 or newer, or a browser with a key you control)

```js
const base = (process.env.API ?? "https://localhost") + "/api/v1";
const headers = { Authorization: `Bearer ${process.env.API_KEY}` };

const page = await (await fetch(`${base}/suppliers?limit=5`, { headers })).json();
for (const s of page.items) console.log(s.company_name ?? s.uploaded_name, s.risk_level, s.risk_score);

const m = await (await fetch(`${base}/resolve`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ name: "Crescent Pharma Holdings" }),
})).json();
console.log(m.route, m.probability);
```

Do not put an API key in browser code that other people load: keys belong on a server.

## Conventions

- **Pagination:** list endpoints take `limit` and return `items` plus a `next_cursor` when there is more. Cursors are opaque
  and signed.
- **Errors:** problem details (`application/problem+json`) with a stable `type`, a `detail`, and the request id. `401` not
  signed in, `403` not allowed or missing CSRF header, `422` invalid input, `429` rate limited (`Retry-After` is set),
  `503` the database is unavailable (`Retry-After: 5`).
- **Idempotency:** uploads accept an `Idempotency-Key` header; repeating a key returns the original upload.
- **Live alerts:** `GET /stream/alerts` is a server-sent event stream for a signed-in browser session.
- **Webhooks:** alert rules can post to a URL. Payloads are not signed yet (`docs/security_review.md`).

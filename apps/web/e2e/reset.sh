#!/usr/bin/env bash
# Rebuild the end-to-end fixtures and restart the API. The suite changes data (reviews, alerts, users),
# so run this before each full run.
# Usage: E2E_ADMIN_URL=postgresql://user@host:port/postgres [VALKEY_URL=redis://...] apps/web/e2e/reset.sh
set -euo pipefail
: "${E2E_ADMIN_URL:?set E2E_ADMIN_URL to an administrative database URL}"
pkill -f "uvicorn --factory app.main:create_app" || true
if [ -n "${VALKEY_URL:-}" ]; then
  python - <<PY
import redis, os
redis.Redis.from_url(os.environ["VALKEY_URL"]).flushall()
PY
fi
export PYTHONPATH=.:apps/api
DATABASE_URL=$(python apps/web/e2e/seed_api.py "$E2E_ADMIN_URL" | tail -1)
# The suite signs in many times; the login limits stay at their defaults everywhere else (backend tests cover them).
export RATE_LIMIT_LOGIN_ACCOUNT=1000/900 RATE_LIMIT_LOGIN_IP=1000/60
export DATABASE_URL COOKIE_SECURE=false ALLOW_EPHEMERAL_SECRETS=true WEB_BASE_URL=http://127.0.0.1:3000
PYTHONPATH=apps/api:. nohup uvicorn --factory app.main:create_app --port 8000 > api.log 2>&1 &
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:8000/api/v1/health/ready >/dev/null && break; sleep 1; done
python apps/web/e2e/seed_suppliers.py http://127.0.0.1:8000
if [ -n "${VALKEY_URL:-}" ]; then
  python - <<PY
import redis, os
redis.Redis.from_url(os.environ["VALKEY_URL"]).flushall()
PY
fi

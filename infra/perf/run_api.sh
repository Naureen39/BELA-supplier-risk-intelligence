#!/usr/bin/env bash
# Start the API for load tests: generous rate limits, fixed secrets (so several workers agree), pooled connections.
# Usage: infra/perf/run_api.sh DATABASE_URL VALKEY_URL [WORKERS]
set -euo pipefail
export DATABASE_URL="$1" VALKEY_URL="$2"
export COOKIE_SECURE=false ALLOW_EPHEMERAL_SECRETS=true
export CURSOR_SECRET=perf-cursor-secret-not-for-production DATA_KEY=perf-data-key-not-for-production
export RATE_LIMIT_IP=10000000/60 RATE_LIMIT_USER=10000000/60 RATE_LIMIT_KEY=10000000/60
export DB_POOL_MIN=4 DB_POOL_MAX=${DB_POOL_MAX:-20}
export PYTHONPATH=apps/api:.
exec uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000 --workers "${3:-1}" --log-level warning

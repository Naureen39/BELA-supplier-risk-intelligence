#!/usr/bin/env bash
# Backup and restore drill: dump a database, restore it into a new one, and prove the copy is complete.
#
# Usage: infra/backup/drill.sh SOURCE_DB_URL ADMIN_URL [RESTORE_DB_NAME]
#   SOURCE_DB_URL   postgresql://user:pass@host:port/dbname   (the database to protect)
#   ADMIN_URL       postgresql://user:pass@host:port/postgres (can create databases)
# Needs pg_dump, pg_restore, and psql on PATH (use the same major version as the server).
# Prints a JSON summary: sizes, durations, and the result of each check. Exits non-zero if any check fails.
set -euo pipefail
SRC="$1"; ADMIN="$2"; NAME="${3:-restore_drill}"
BASE="${ADMIN%/*}"; DEST="$BASE/$NAME"
DUMP="$(mktemp -d)/backup.dump"
now() { python3 -c 'import time; print(time.time())'; }

t0=$(now)
pg_dump --format=custom --no-owner --compress=6 --file="$DUMP" "$SRC"
t1=$(now)
psql "$ADMIN" -qc "DROP DATABASE IF EXISTS \"$NAME\" WITH (FORCE)" -c "CREATE DATABASE \"$NAME\""
# Roles belong to the cluster, not the database. On a new server the application role must exist before the
# restore, or the grants in the dump fail.
psql "$ADMIN" -qc "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN CREATE ROLE app_user NOLOGIN; END IF; END \$\$"
t2=$(now)
pg_restore --no-owner --dbname="$DEST" --exit-on-error "$DUMP"
t3=$(now)

fail=0
check() { # name, sql, expectation: both databases must return the same single value
  a=$(psql "$SRC" -Atc "$2"); b=$(psql "$DEST" -Atc "$2")
  if [ "$a" = "$b" ]; then echo "ok    $1: $a" >&2; else echo "FAIL  $1: source=$a restored=$b" >&2; fail=1; fi
}
for t in companies company_relationships facilities events event_entities link_candidates tenants users suppliers \
         risk_scores risk_score_components alerts alert_events resolution_reviews audit_log subscriptions invoices \
         usage_daily portfolio_stats_daily dead_letters; do
  check "rows in $t" "SELECT count(*) FROM $t"
done
check "schema version" "SELECT version_num FROM alembic_version"
check "row level security policies" "SELECT count(*) FROM pg_policies"
check "indexes" "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'"
check "materialized views populated" "SELECT sum(ispopulated::int) FROM pg_matviews"
check "audit chain tail" "SELECT coalesce((SELECT row_hash FROM audit_log ORDER BY seq DESC LIMIT 1), 'none')"
check "checksum of supplier names" "SELECT md5(string_agg(uploaded_name || status, ',' ORDER BY id)) FROM suppliers"
# The restored database must still enforce isolation: the application role exists and is restricted.
a=$(psql "$DEST" -Atc "SELECT count(*) FROM pg_roles WHERE rolname = 'app_user'")
if [ "$a" = "1" ]; then echo "ok    application role present" >&2; else echo "FAIL  application role missing in the restored database" >&2; fail=1; fi
a=$(psql "$DEST" -Atc "SELECT relrowsecurity::int FROM pg_class WHERE relname = 'suppliers'")
if [ "$a" = "1" ]; then echo "ok    row level security enabled on suppliers" >&2; else echo "FAIL  row level security lost" >&2; fail=1; fi

# The audit log is a hash chain: verify it end to end on the restored copy, not just its last row.
if PYTHONPATH="${PYTHONPATH:-apps/api}" python3 - "$DEST" <<'PY' >&2
import sys
from app.core import audit
from app.db import Database
ok, bad, n = audit.verify_chain(Database(sys.argv[1], 1, 2))
print(f"{'ok   ' if ok else 'FAIL '} audit hash chain verified on the restored copy: {n} entries, first bad entry {bad}")
sys.exit(0 if ok else 1)
PY
then :; else fail=1; fi

python3 - "$DUMP" "$t0" "$t1" "$t2" "$t3" "$fail" <<'PY'
import json, os, sys
dump, t0, t1, t2, t3, fail = sys.argv[1], *map(float, sys.argv[2:5]), float(sys.argv[5]), int(sys.argv[6])
print(json.dumps({"dump_bytes": os.path.getsize(dump), "dump_seconds": round(t1 - t0, 2),
                  "restore_seconds": round(t3 - t2, 2), "passed": fail == 0}))
PY
rm -rf "$(dirname "$DUMP")"
exit "$fail"

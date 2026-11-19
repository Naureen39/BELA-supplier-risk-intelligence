PY := .venv/bin/python
export PYTHONPATH := .
# WeasyPrint finds Pango here on macOS with Homebrew; harmless elsewhere.
export DYLD_FALLBACK_LIBRARY_PATH ?= /opt/homebrew/lib

.PHONY: env demo demo-down demo-reset demo-logs demo-credentials-help screenshots models-fetch licenses compose-check publish-metrics web-install web-dev web-build web-check web-e2e web-quality demo-data load-demo-data metrics-refresh demo-portfolios ingest-events eval-events training-data train fit eval services-nel services-blink migrate etl db-test setup data data-edgar data-registry data-regulators data-news data-verify counts test lint check-dash gdelt

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e . pytest pytest-cov ruff mypy types-PyYAML

# Full download. Requires SEC_USER_AGENT and CONTACT_EMAIL (see .env.example).
data: data-edgar data-registry data-regulators data-verify counts

data-edgar:
	$(PY) -m data.scripts.download_edgar
	$(PY) -m data.scripts.download_exhibit21 --year 2025 --quarter 1 --limit 300

data-registry:
	$(PY) -m data.scripts.download_gleif

data-regulators:
	$(PY) -m data.scripts.download_epa_echo
	$(PY) -m data.scripts.download_nhtsa
	$(PY) -m data.scripts.download_cpsc
	$(PY) -m data.scripts.download_fda
	@echo "OSHA: run download_osha with the method chosen in docs/adr/ADR-003-osha-access.md"

gdelt:
	$(PY) -m data.scripts.harvest_gdelt

data-verify:
	$(PY) -m data.scripts.verify_manifest

counts:
	$(PY) -m data.scripts.verify_manifest --counts

test:
	PYTHONPATH=.:apps/api .venv/bin/python -m pytest --cov=data.scripts --cov=app --cov-report=term-missing

# Phase 2: database. DATABASE_URL example: postgresql+psycopg://user:pw@localhost:5432/provenance
migrate:
	cd apps/api && ../../.venv/bin/alembic upgrade head

etl:
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.kb.pipeline

lint: check-dash
	.venv/bin/ruff check apps data tests infra training services
	.venv/bin/mypy -p data.scripts
	.venv/bin/mypy services training
	MYPYPATH=apps/api:. .venv/bin/mypy --strict -p app

check-dash:
	$(PY) infra/ci/check_no_em_dash.py

# Phase 3: resolution engine. Requires DATABASE_URL (populated by make etl).
training-data:
	$(PY) -m data.scripts.generate_training_pairs

fit:
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.resolution.fit_cli --training-dir ../../data/training --out ../../models/scoring

# GPU stages run through the isolated BLINK environment; see training/blink/config.yaml.
train:
	$(PY) -m training.train
	$(MAKE) fit

publish-metrics:
	$(PY) infra/publish_metrics.py

eval:
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.resolution.evaluation.run --out ../../docs/eval

services-nel:
	.venv/bin/uvicorn services.nel.main:app --host 127.0.0.1 --port 8101

services-blink:
	.venv/bin/uvicorn services.blink.main:app --host 127.0.0.1 --port 8102

# Phase 4: events. Example: make ingest-events SOURCE=osha FILE=data/raw/regulators/osha/violations.json
ingest-events:
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.events.ingest --source $(SOURCE) --path ../../$(FILE)

eval-events:
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.events.evaluation --gold ../../data/gold/events.jsonl --out ../../docs/eval/event_labeling.md

# Phase 5: API. Needs DATABASE_URL (after make migrate) and, outside development, the secrets in .env.example.
# Phase 7: demo business data, revenue views, and demo portfolios. Demo data only.
demo-data:
	$(PY) -m data.scripts.generate_demo_business_data

load-demo-data: demo-data
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.analytics.loader --dir ../../data/synthetic

# Run nightly (cron or the scheduler) and after loading data.
metrics-refresh:
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.analytics.loader --refresh-only

demo-portfolios:
	PYTHONPATH=.:apps/api $(PY) -m data.scripts.generate_demo_portfolios --from-db

# Phase 8: web app. Needs Node 22 or newer.
web-install:
	cd apps/web && npm ci

web-dev:
	cd apps/web && API_ORIGIN=http://127.0.0.1:8000 npm run dev

web-build:
	cd apps/web && npm run build

web-check:
	cd apps/web && npx prettier --check . && npm run lint && npm run typecheck && npm test

# End to end tests. Run apps/web/e2e/reset.sh first (see docs/app.md): it seeds the database, starts the API,
# and uploads the demo supplier list. The suite changes data, so reset before every full run.
web-e2e:
	cd apps/web && API_ORIGIN=http://127.0.0.1:8000 npm run e2e

web-quality:
	cd apps/web && npm run build && npm run quality

api:
	PYTHONPATH=apps/api:. .venv/bin/uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000 --reload

# Run the database tests locally: TEST_DATABASE_ADMIN_URL=postgresql+psycopg://user@host/postgres make test

# Phase 11: packaging and the demo. Needs Docker with the compose plugin (v2.23 or newer).
# `make demo` builds the images, starts the stack behind Caddy (https://localhost), migrates, seeds, and prints the
# demo account passwords once. Trained checkpoints are not shipped (none exist yet); see docs/deploy.md.
env:
	infra/demo/make_env.sh --demo

demo: env
	docker compose --profile demo up -d --build
	docker compose --profile demo wait seed
	@docker compose --profile demo logs --no-log-prefix seed | sed -n '/^upload/,$$p'
	@echo "Open https://localhost (accept the local certificate, or run: docker compose exec caddy caddy trust)"
	@echo "Password reset and invitation emails: http://localhost:8025"

demo-logs:
	docker compose --profile demo logs -f api web caddy

demo-down:
	docker compose --profile demo down

# Wipes the demo database and volumes, then seeds again with new passwords.
demo-reset:
	docker compose --profile demo down -v
	$(MAKE) demo

models-fetch:
	$(PY) infra/models/fetch_checkpoints.py

# Captures docs/screenshots from a running site. For application pages add APP_EMAIL and APP_PASSWORD.
screenshots:
	cd apps/web && node scripts/screenshots.mjs

licenses:
	$(PY) infra/licenses.py

compose-check:
	$(PY) -c "import yaml,sys; yaml.safe_load(open('compose.yaml')); print('compose.yaml parses')"

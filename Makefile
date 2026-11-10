PY := .venv/bin/python
export PYTHONPATH := .

.PHONY: ingest-events eval-events training-data train fit eval services-nel services-blink migrate etl db-test setup data data-edgar data-registry data-regulators data-news data-verify counts test lint check-dash gdelt

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
	PYTHONPATH=.:apps/api .venv/bin/python -m pytest --cov=data.scripts --cov=app.kb --cov=app.resolution --cov=app.events --cov-report=term-missing

# Phase 2: database. DATABASE_URL example: postgresql+psycopg://user:pw@localhost:5432/provenance
migrate:
	cd apps/api && ../../.venv/bin/alembic upgrade head

etl:
	cd apps/api && PYTHONPATH=.:../.. ../../.venv/bin/python -m app.kb.pipeline

lint: check-dash
	.venv/bin/ruff check apps data tests infra training services
	.venv/bin/mypy -p data.scripts
	.venv/bin/mypy services training
	MYPYPATH=apps/api:. .venv/bin/mypy --strict -p app.kb -p app.resolution -p app.events

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

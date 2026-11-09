PY := .venv/bin/python
export PYTHONPATH := .

.PHONY: setup data data-edgar data-registry data-regulators data-news data-verify counts test lint check-dash gdelt

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
	$(PY) -m pytest --cov=data.scripts --cov-report=term-missing

lint: check-dash
	.venv/bin/ruff check data tests infra
	.venv/bin/mypy data/scripts

check-dash:
	$(PY) infra/ci/check_no_em_dash.py

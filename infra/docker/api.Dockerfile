# API image. Build from the repository root: docker build -f infra/docker/api.Dockerfile -t provenance-api .
# Not built or run in the environment where this file was written (no Docker there). See docs/deploy.md.
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# WeasyPrint needs Pango for the PDF reports; curl serves the health check.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements/api.txt requirements/api.txt
RUN pip install -r requirements/api.txt
COPY apps/api apps/api
COPY data/__init__.py data/__init__.py
COPY data/scripts data/scripts
COPY infra/demo infra/demo
COPY infra/backup infra/backup
COPY docs/eval/metrics.json docs/eval/metrics.json
ENV PYTHONPATH=/srv/apps/api:/srv REPORT_DIR=/var/lib/provenance/reports EVAL_METRICS_PATH=/srv/docs/eval/metrics.json
RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin app \
 && mkdir -p /var/lib/provenance/reports && chown -R app /var/lib/provenance
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health/ready || exit 1
CMD ["sh", "-c", "exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2} --proxy-headers --forwarded-allow-ips='*'"]

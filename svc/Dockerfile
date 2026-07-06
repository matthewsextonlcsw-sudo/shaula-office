# shaula-svc — multi-tenant office runtime (Cloud Run).
# Build context = the REPO ROOT (the svc imports engine/ + workflows/):
#   docker build -f svc/Dockerfile -t shaula-svc .
FROM python:3.12-slim

WORKDIR /app

# Hash-pinned lockfile (uv pip compile --generate-hashes). Reproducible builds,
# and --require-hashes rejects a swapped/compromised artifact on the weekly
# rebuild. Regenerate: uv pip compile svc/requirements.txt --generate-hashes \
#   --python-version 3.12 -o svc/requirements.lock
COPY svc/requirements.lock /app/svc/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/svc/requirements.lock

# Only what the svc imports — never the vendored Hermes (2.3GB stays home).
COPY svc/ /app/svc/
COPY engine/ /app/engine/
COPY workflows/ /app/workflows/
COPY templates/ /app/templates/

ENV SHAULA_STATE_BACKEND=gcs \
    SHAULA_SITES_DIR=/tmp/sites \
    PYTHONUNBUFFERED=1

# Drop root (defense-in-depth atop Cloud Run's sandbox). State lives in GCS and
# sites build under /tmp (world-writable), so the unprivileged uid needs no grants.
RUN useradd --create-home --uid 10001 app
USER 10001

EXPOSE 8080
CMD ["uvicorn", "svc.app:app", "--host", "0.0.0.0", "--port", "8080"]

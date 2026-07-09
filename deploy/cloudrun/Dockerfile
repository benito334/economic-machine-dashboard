# Google Cloud Run — public, read-only Economic Machine Dashboard.
#
# Build context is just this folder: it needs the Dockerfile + the data bundle
# emd_data.tar.gz (compacted DuckDB + cache). The app CODE is cloned from the
# public GitHub repo at build time, so a redeploy always picks up latest main;
# only the data bundle is supplied locally.
#
# Deploy (from this folder, with emd_data.tar.gz present):
#   gcloud run deploy economic-machine --source . \
#     --region us-central1 --allow-unauthenticated \
#     --memory 2Gi --cpu 1
# See DEPLOY-cloudrun.md for the full walkthrough.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

ARG REPO=https://github.com/benito334/economic-machine-dashboard.git
RUN git clone --depth 1 "$REPO" /app

RUN pip install --no-cache-dir -r requirements.txt

# Data bundle from the build context → /db (database) + /data (cache).
COPY emd_data.tar.gz /tmp/emd_data.tar.gz
RUN mkdir -p /db /data \
    && tar -xzf /tmp/emd_data.tar.gz -C /data \
    && mv /data/signals.duckdb /db/signals.duckdb \
    && rm /tmp/emd_data.tar.gz

# PUBLIC_MODE hides every control that writes shared state. The app only reads.
ENV PUBLIC_MODE=1 \
    DB_PATH=/db/signals.duckdb \
    DATA_DIR=/data \
    RAW_CACHE_DIR=/data/raw_cache \
    SNAPSHOTS_DIR=/data/snapshots \
    DASH_DEBUG=0
# TRAFFIC_KEY is not baked in — set it with --set-env-vars to unlock /traffic?key=…

# Cloud Run injects $PORT (default 8080) and expects the app to listen on it.
# Shell form so $PORT expands; `exec` makes gunicorn PID 1 for clean shutdowns.
CMD ["sh", "-c", "exec gunicorn dashboard.charting:server --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 120"]

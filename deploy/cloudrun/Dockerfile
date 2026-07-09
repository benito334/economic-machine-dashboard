# Google Cloud Run — public, read-only Economic Machine Dashboard.
#
# Fully self-contained: both the app CODE and the DATA bundle are fetched from
# the public GitHub repo at build time, so nothing needs to be supplied in the
# build context. This is what lets Cloud Run's "Connect repository" click-flow
# build it with no file uploads.
#
#   - code : cloned from the repo (latest main)
#   - data : downloaded from the "data-latest" GitHub Release asset
#
# Deploy either way:
#   • Console: Cloud Run → Connect repository → this Dockerfile path
#   • CLI:     gcloud run deploy economic-machine --source deploy/cloudrun ...
# See DEPLOY-cloudrun.md for the full walkthrough.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

ARG REPO=https://github.com/benito334/economic-machine-dashboard.git
RUN git clone --depth 1 "$REPO" /app

RUN pip install --no-cache-dir -r requirements.txt

# Data bundle from the public GitHub Release → /db (database) + /data (cache).
# Refresh the deployed data by re-uploading this asset (see DEPLOY-cloudrun.md).
ARG DATA_URL=https://github.com/benito334/economic-machine-dashboard/releases/download/data-latest/emd_data.tar.gz
RUN curl -fsSL "$DATA_URL" -o /tmp/emd_data.tar.gz \
    && mkdir -p /db /data \
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

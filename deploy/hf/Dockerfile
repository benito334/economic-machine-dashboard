# Hugging Face Space (Docker SDK) — public, read-only Economic Machine Dashboard.
#
# Build context (the Space repo) only needs THREE files:
#   Dockerfile   (this file)
#   README.md    (HF Space metadata — sets app_port: 7860)
#   emd_data.tar.gz   (compacted DuckDB + raw_cache + snapshots; see DEPLOY.md)
#
# The application code is cloned fresh from the public GitHub repo at build
# time, so a rebuild always picks up the latest main. Only the data bundle
# lives in the Space; to publish fresh data you re-upload emd_data.tar.gz and
# the Space rebuilds.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

# App code (public repo). Pin to a tag/commit with --branch if you want to
# freeze a version; default is latest main.
ARG REPO=https://github.com/benito334/economic-machine-dashboard.git
RUN git clone --depth 1 "$REPO" /app

RUN pip install --no-cache-dir -r requirements.txt

# Data bundle from the Space build context → /db (database) + /data (cache).
COPY emd_data.tar.gz /tmp/emd_data.tar.gz
RUN mkdir -p /db /data \
    && tar -xzf /tmp/emd_data.tar.gz -C /data \
    && mv /data/signals.duckdb /db/signals.duckdb \
    && rm /tmp/emd_data.tar.gz \
    && chmod -R a+rwX /db /data          # HF runs the container as UID 1000

# PUBLIC_MODE hides every control that writes shared state (scheduler, weight
# editor, saved views). The app is a pure reader here — no writes to the DB.
ENV PUBLIC_MODE=1 \
    DB_PATH=/db/signals.duckdb \
    DATA_DIR=/data \
    RAW_CACHE_DIR=/data/raw_cache \
    SNAPSHOTS_DIR=/data/snapshots \
    CHARTING_PORT=7860 \
    DASH_DEBUG=0
# TRAFFIC_KEY is NOT baked in — set it as a Space secret to unlock /traffic?key=…

EXPOSE 7860

# Flask/Dash served by gunicorn. 2 workers is plenty for a class-sized audience;
# per-viewer state is browser-side (localStorage), so multiple workers are safe.
CMD ["gunicorn", "dashboard.charting:server", \
     "--bind", "0.0.0.0:7860", \
     "--workers", "2", "--threads", "4", "--timeout", "120"]

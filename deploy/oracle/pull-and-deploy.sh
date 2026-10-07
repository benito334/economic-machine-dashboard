#!/usr/bin/env bash
# Polls the repo for new commits on main; if any landed, rebuilds and
# restarts the compose stack. Never triggered by an inbound webhook, so
# nothing needs to be exposed to the internet for this to work.
#
# ── NOT INSTALLED, BY DECISION (2026-10-06) ──────────────────────────────────
# The VM is deployed MANUALLY. indicators-deploy.timer is deliberately not
# enabled: now that this VM serves the live public site, auto-deploying every
# commit to main would put a mistake in front of visitors within 15 minutes.
# That coupling was fine for Cloud Run's frozen snapshot; it is a different
# risk here. If automation is ever wanted, prefer triggering on a release tag
# rather than every commit.
#
# Nightly DATA imports are unaffected — the scheduler container handles those
# independently, so data stays current whether or not code is deployed.
#
# Manual deploy (what is actually used), from the repo root on the VM:
#   git pull --ff-only origin main
#   sudo docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.caddy.yml build charting pipeline scheduler
#   sudo docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.caddy.yml up -d caddy charting scheduler goaccess
# ─────────────────────────────────────────────────────────────────────────────
#
# Exits 0 on "nothing to do" and on a successful deploy; exits non-zero (and
# the systemd service unit below reports failure) if git or docker compose
# error out, so a failed deploy is visible in `systemctl status` / journalctl.
set -euo pipefail

# NB: the live VM clones to /home/opc/economic-machine-dashboard, not here —
# override REPO_DIR (or the Environment= line in indicators-deploy.service)
# before enabling this anywhere, or the first `cd` fails.
REPO_DIR="${REPO_DIR:-/opt/economic-machine-dashboard}"
cd "$REPO_DIR"

git fetch origin main --quiet
LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse origin/main)

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
    exit 0
fi

echo "$(date -Is) deploying $LOCAL_SHA -> $REMOTE_SHA"
git merge --ff-only origin/main

# BOTH compose files. Without the second one Caddy and GoAccess are not in the
# project definition at all — they were added after this script was written.
COMPOSE="docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.caddy.yml"
$COMPOSE build charting pipeline scheduler
$COMPOSE up -d caddy charting scheduler goaccess
echo "$(date -Is) deploy complete"

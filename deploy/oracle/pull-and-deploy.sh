#!/usr/bin/env bash
# Polls the repo for new commits on main; if any landed, rebuilds and
# restarts the compose stack. Run on a timer (see indicators-deploy.timer) —
# never triggered by an inbound webhook, so nothing needs to be exposed to
# the internet for this to work.
#
# Exits 0 on "nothing to do" and on a successful deploy; exits non-zero (and
# the systemd service unit below reports failure) if git or docker compose
# error out, so a failed deploy is visible in `systemctl status` / journalctl.
set -euo pipefail

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
docker compose build
docker compose up -d
echo "$(date -Is) deploy complete"

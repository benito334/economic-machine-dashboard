"""Deployment mode flag.

``PUBLIC_MODE`` (env var) hardens the dashboard for an untrusted public/cloud
audience by hiding every control that writes SHARED server-side state — so many
concurrent viewers can't step on each other or take the app down. Per-browser
settings (theme, selected country, look-back windows, regime thresholds) are
localStorage and stay fully available; only shared-write surfaces are gated:

  * Settings → Data updates (the daily-import scheduler + "Update now")
  * Weight Audit / Weight History (importance editor writes YAML + the DB)
  * Workbench "save/delete view" (shared saved_views.json)

Set ``PUBLIC_MODE=1`` in the deployment environment. Off by default (the local
single-operator experience is unchanged). When on, configure the daily import
via env vars instead (see indicators/schedule_config.py: AUTO_IMPORT_*).
"""
from __future__ import annotations

import os

PUBLIC_MODE: bool = os.environ.get("PUBLIC_MODE", "").strip().lower() in (
    "1", "true", "yes", "on")

# Routes that mutate shared state — blocked in public mode even by direct URL.
OPERATOR_ONLY_ROUTES = frozenset({"/weight-audit", "/weight-history"})

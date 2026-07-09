"""Shared read/write for the daily-import schedule + status.

The dashboard's Settings UI writes ``schedule.json``; the scheduler service
(``indicators.scheduler``) reads it, writes ``schedule_status.json`` back, and
consumes a ``run_now.trigger`` file for on-demand imports. All three live in
``DATA_DIR`` (bind-mounted into both containers), so the dashboard and the
scheduler coordinate purely through files — never through the single-writer DB.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(os.environ.get(
    "DATA_DIR", "/mnt/data/project_data/all_weather/indicators_machine"))

SCHEDULE_PATH = DATA_DIR / "schedule.json"
STATUS_PATH   = DATA_DIR / "schedule_status.json"
TRIGGER_PATH  = DATA_DIR / "run_now.trigger"

# Host/container timezone by default (falls back to UTC if TZ unset).
DEFAULT_TZ = os.environ.get("TZ") or "UTC"
DEFAULT_SCHEDULE = {"enabled": False, "time": "03:00", "tz": DEFAULT_TZ}

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def valid_time(s: str) -> bool:
    """True if s is a 24h 'HH:MM' string."""
    return bool(_TIME_RE.match((s or "").strip()))


def _atomic_write(path: Path, payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


# ── schedule.json (written by the dashboard, read by the scheduler) ───────────

def load_schedule() -> dict:
    """Return the current schedule, falling back to defaults on any problem."""
    out = dict(DEFAULT_SCHEDULE)
    try:
        data = json.loads(SCHEDULE_PATH.read_text())
    except Exception:
        return out
    if isinstance(data, dict):
        if isinstance(data.get("enabled"), bool):
            out["enabled"] = data["enabled"]
        if valid_time(str(data.get("time", ""))):
            out["time"] = str(data["time"]).strip()
        if data.get("tz"):
            out["tz"] = str(data["tz"])
    return out


def save_schedule(enabled: bool, time_str: str, tz: str | None = None) -> dict:
    """Persist the schedule. Invalid time falls back to the current/default."""
    time_str = (time_str or "").strip()
    if not valid_time(time_str):
        time_str = load_schedule()["time"]
    sched = {"enabled": bool(enabled), "time": time_str,
             "tz": tz or load_schedule().get("tz", DEFAULT_TZ)}
    _atomic_write(SCHEDULE_PATH, sched)
    return sched


# ── schedule_status.json (written by the scheduler, read by the dashboard) ────

def load_status() -> dict:
    try:
        data = json.loads(STATUS_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_status(**fields) -> None:
    """Merge fields into the status file (last_run, last_status, next_run, ...)."""
    cur = load_status()
    cur.update(fields)
    _atomic_write(STATUS_PATH, cur)


# ── run_now.trigger (dashboard 'Update now' → scheduler) ──────────────────────

def request_run_now() -> None:
    """Ask the scheduler to run an import as soon as it next polls."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TRIGGER_PATH.write_text(datetime.datetime.now().isoformat(timespec="seconds"))


def consume_run_now() -> bool:
    """True (and clears the trigger) if an on-demand run was requested."""
    if TRIGGER_PATH.exists():
        try:
            TRIGGER_PATH.unlink()
        except FileNotFoundError:
            pass
        return True
    return False

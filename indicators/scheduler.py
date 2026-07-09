"""Daily auto-import scheduler (opt-in, configured from the dashboard Settings).

This automates the *exact manual workflow* the project has always used —
**stop the dashboard → run the pipeline → start the dashboard** — at the time
set in Settings, plus an on-demand "Update now" trigger. It runs as its own
docker-compose service with the docker socket mounted so it can bounce the
`charting` container (the DuckDB file is single-writer, so the dashboard must be
down during the import — same reason you stop it by hand).

Coordination is entirely file-based (see ``schedule_config``): the dashboard
writes ``schedule.json`` / ``run_now.trigger``; this process reads them and
writes ``schedule_status.json`` back.

Graceful degradation: if the docker SDK or socket isn't available (e.g. running
outside compose, or in a test), it skips the container bounce and just runs the
pipeline, logging a warning — the import still happens.

Run:  python -m indicators.scheduler
"""
from __future__ import annotations

import datetime
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from indicators import schedule_config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] scheduler: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

_REPO = Path(__file__).parents[1]
_POLL_SECONDS = 20                       # how often to re-check config + trigger
_CHARTING_SERVICE = "charting"           # docker-compose service to bounce


# ── docker container control (graceful if unavailable) ───────────────────────

def _charting_container():
    """The compose 'charting' container via the docker SDK, or None."""
    try:
        import docker  # optional dependency; only needed at runtime in compose
    except Exception as exc:
        logger.warning("docker SDK unavailable (%s) — skipping container bounce", exc)
        return None
    try:
        client = docker.from_env()
        found = client.containers.list(
            all=True,
            filters={"label": f"com.docker.compose.service={_CHARTING_SERVICE}"},
        )
        if not found:
            logger.warning("no '%s' container found — skipping bounce", _CHARTING_SERVICE)
            return None
        return found[0]
    except Exception as exc:
        logger.warning("cannot reach docker (%s) — skipping container bounce", exc)
        return None


def _stop_charting() -> bool:
    c = _charting_container()
    if c is None:
        return False
    logger.info("stopping dashboard container '%s' for the import…", c.name)
    c.stop(timeout=30)
    return True


def _start_charting(was_stopped: bool) -> None:
    if not was_stopped:
        return
    c = _charting_container()
    if c is not None:
        logger.info("restarting dashboard container '%s'", c.name)
        c.start()


# ── the import job = the manual workflow ─────────────────────────────────────

def run_import(reason: str = "scheduled") -> None:
    """Stop the dashboard, run the pipeline, restart the dashboard. Records status."""
    started = datetime.datetime.now()
    logger.info("import starting (%s)", reason)
    cfg.save_status(last_status="running",
                    last_run=started.isoformat(timespec="seconds"),
                    last_reason=reason, last_message="import in progress")
    was_stopped = False
    try:
        was_stopped = _stop_charting()
        proc = subprocess.run(
            [sys.executable, "-m", "indicators.pipeline"],
            cwd=str(_REPO), capture_output=True, text=True,
        )
        tail = "\n".join((proc.stdout or "").strip().splitlines()[-3:])
        # NOTE: the pipeline exits 1 on the documented EZ current-account empty
        # even on a healthy run, so completion — not exit code — is "done".
        ok = "Summary" in (proc.stdout or "") or "Country files processed" in (proc.stdout or "")
        status = "success" if ok else "failed"
        msg = f"exit {proc.returncode}; {tail[-300:]}" if tail else f"exit {proc.returncode}"
        logger.info("import %s (exit %s)", status, proc.returncode)
    except Exception as exc:
        status, msg = "failed", str(exc)
        logger.exception("import crashed: %s", exc)
    finally:
        _start_charting(was_stopped)
    cfg.save_status(last_status=status,
                    last_run=started.isoformat(timespec="seconds"),
                    last_finished=datetime.datetime.now().isoformat(timespec="seconds"),
                    last_reason=reason, last_message=msg)


# ── scheduling loop ──────────────────────────────────────────────────────────

def _next_run_iso(hour: int, minute: int, tzname: str) -> str:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tzname)
    except Exception:
        tz = None
    now = datetime.datetime.now(tz)
    nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= now:
        nxt += datetime.timedelta(days=1)
    return nxt.isoformat(timespec="minutes")


def _apply_schedule(scheduler) -> None:
    """(Re)install the daily cron job from the current config; update status."""
    from apscheduler.triggers.cron import CronTrigger
    try:
        scheduler.remove_job("daily_import")
    except Exception:
        pass
    sched = cfg.load_schedule()
    if not sched["enabled"]:
        cfg.save_status(enabled=False, next_run=None,
                        schedule_time=sched["time"], schedule_tz=sched["tz"])
        logger.info("auto-import disabled")
        return
    hh, mm = (int(x) for x in sched["time"].split(":"))
    try:
        trigger = CronTrigger(hour=hh, minute=mm, timezone=sched["tz"])
    except Exception:
        trigger = CronTrigger(hour=hh, minute=mm)  # fall back to naive/local
    scheduler.add_job(run_import, trigger, id="daily_import",
                      replace_existing=True, kwargs={"reason": "scheduled"})
    nxt = _next_run_iso(hh, mm, sched["tz"])
    cfg.save_status(enabled=True, next_run=nxt,
                    schedule_time=sched["time"], schedule_tz=sched["tz"])
    logger.info("auto-import enabled — daily at %s %s (next: %s)",
                sched["time"], sched["tz"], nxt)


def main() -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    logger.info("scheduler starting; config=%s", cfg.SCHEDULE_PATH)
    scheduler = BackgroundScheduler()
    scheduler.start()
    _apply_schedule(scheduler)
    last_mtime = cfg.SCHEDULE_PATH.stat().st_mtime if cfg.SCHEDULE_PATH.exists() else 0.0
    # clear any stale trigger left over from a previous run
    cfg.consume_run_now()
    while True:
        time.sleep(_POLL_SECONDS)
        try:
            mtime = cfg.SCHEDULE_PATH.stat().st_mtime if cfg.SCHEDULE_PATH.exists() else 0.0
            if mtime != last_mtime:
                last_mtime = mtime
                logger.info("schedule.json changed — re-applying")
                _apply_schedule(scheduler)
            if cfg.consume_run_now():
                logger.info("on-demand 'Update now' requested")
                run_import(reason="manual (Update now)")
                _apply_schedule(scheduler)  # refresh next_run in status
        except Exception as exc:
            logger.exception("scheduler loop error: %s", exc)


if __name__ == "__main__":
    main()

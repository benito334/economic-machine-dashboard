"""Daily auto-import scheduler — config round-trip + status/trigger + apply logic."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from indicators import schedule_config
    importlib.reload(schedule_config)
    return schedule_config


# ── schedule_config ───────────────────────────────────────────────────────────

def test_defaults_when_no_file(cfg):
    s = cfg.load_schedule()
    assert s["enabled"] is False
    assert cfg.valid_time(s["time"])


def test_save_and_load_roundtrip(cfg):
    cfg.save_schedule(True, "04:30", "America/Chicago")
    s = cfg.load_schedule()
    assert s == {"enabled": True, "time": "04:30", "tz": "America/Chicago"}


def test_invalid_time_is_rejected(cfg):
    assert cfg.valid_time("00:00")
    assert cfg.valid_time("23:59")
    assert not cfg.valid_time("24:00")
    assert not cfg.valid_time("9:60")
    assert not cfg.valid_time("nope")
    # saving an invalid time falls back to the prior/default, never persists garbage
    cfg.save_schedule(True, "03:15", "UTC")
    cfg.save_schedule(True, "banana", "UTC")
    assert cfg.load_schedule()["time"] == "03:15"


def test_corrupt_file_falls_back_to_defaults(cfg):
    cfg.SCHEDULE_PATH.write_text("{ not json")
    assert cfg.load_schedule()["enabled"] is False


def test_run_now_trigger_is_one_shot(cfg):
    assert cfg.consume_run_now() is False
    cfg.request_run_now()
    assert cfg.consume_run_now() is True
    assert cfg.consume_run_now() is False


def test_status_merges(cfg):
    cfg.save_status(last_status="running")
    cfg.save_status(next_run="2026-07-10T03:00")
    st = cfg.load_status()
    assert st["last_status"] == "running"
    assert st["next_run"] == "2026-07-10T03:00"


# ── scheduler apply-logic (no docker / no real scheduler needed) ──────────────

class _FakeScheduler:
    def __init__(self):
        self.jobs = {}
    def add_job(self, func, trigger, id, replace_existing=True, kwargs=None):
        self.jobs[id] = (func, trigger, kwargs)
    def remove_job(self, id):
        if id not in self.jobs:
            raise KeyError(id)
        del self.jobs[id]


def test_apply_schedule_adds_job_when_enabled(cfg, monkeypatch):
    from indicators import scheduler
    importlib.reload(scheduler)
    cfg.save_schedule(True, "05:45", "UTC")
    sched = _FakeScheduler()
    scheduler._apply_schedule(sched)
    assert "daily_import" in sched.jobs
    st = cfg.load_status()
    assert st["enabled"] is True and st["next_run"]


def test_apply_schedule_removes_job_when_disabled(cfg):
    from indicators import scheduler
    importlib.reload(scheduler)
    cfg.save_schedule(False, "05:45", "UTC")
    sched = _FakeScheduler()
    sched.jobs["daily_import"] = ("x", "y", None)   # pretend one exists
    scheduler._apply_schedule(sched)
    assert "daily_import" not in sched.jobs
    assert cfg.load_status()["enabled"] is False


def test_charting_container_none_without_docker(cfg, monkeypatch):
    """Graceful: no docker SDK/socket -> returns None, never raises."""
    from indicators import scheduler
    importlib.reload(scheduler)
    monkeypatch.setitem(__import__("sys").modules, "docker", None)  # force import fail
    assert scheduler._charting_container() is None
    assert scheduler._stop_charting() is False

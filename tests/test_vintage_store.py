"""Vintage store — append-only point-in-time capture (history.duckdb)."""
import datetime

import duckdb
import pandas as pd
import pytest

from indicators.vintage_store import capture_raw_cache


def _write_cache(tmp_path, name, values: dict):
    idx = pd.to_datetime(list(values.keys()))
    pd.DataFrame({"value": list(values.values())}, index=idx).to_parquet(
        tmp_path / f"{name}.parquet")


@pytest.fixture
def store(tmp_path):
    cache = tmp_path / "cache"; cache.mkdir()
    db = tmp_path / "history.duckdb"
    return cache, db


def test_initial_capture_appends_everything(store):
    cache, db = store
    _write_cache(cache, "fred_TEST", {"2026-01-01": 1.0, "2026-02-01": 2.0})
    s = capture_raw_cache(cache, db, vintage_date=datetime.date(2026, 7, 1))
    assert s["files"] == 1 and s["new_rows"] == 2 and s["new_series"] == 1


def test_unchanged_recapture_appends_nothing(store):
    cache, db = store
    _write_cache(cache, "fred_TEST", {"2026-01-01": 1.0})
    capture_raw_cache(cache, db, vintage_date=datetime.date(2026, 7, 1))
    s2 = capture_raw_cache(cache, db, vintage_date=datetime.date(2026, 7, 2))
    assert s2["new_rows"] == 0


def test_revision_and_new_obs_append_with_new_vintage(store):
    cache, db = store
    _write_cache(cache, "fred_TEST", {"2026-01-01": 1.0, "2026-02-01": 2.0})
    capture_raw_cache(cache, db, vintage_date=datetime.date(2026, 7, 1))
    # Feb revised 2.0 → 2.5; March is brand new
    _write_cache(cache, "fred_TEST", {"2026-01-01": 1.0, "2026-02-01": 2.5,
                                      "2026-03-01": 3.0})
    s2 = capture_raw_cache(cache, db, vintage_date=datetime.date(2026, 8, 1))
    assert s2["new_rows"] == 2
    con = duckdb.connect(str(db), read_only=True)
    # Both vintages of Feb are retained (point-in-time truth)
    feb = con.execute("select vintage_date, value from raw_observations "
                      "where obs_date='2026-02-01' order by vintage_date").fetchall()
    assert [(str(v), x) for v, x in feb] == [("2026-07-01", 2.0), ("2026-08-01", 2.5)]
    # Publication calendar: first vintage per obs
    first_seen = con.execute("select obs_date, min(vintage_date) from raw_observations "
                             "group by 1 order by 1").fetchall()
    assert str(first_seen[2][1]) == "2026-08-01"   # March first seen in August
    con.close()


def test_alfred_parquets_excluded(store):
    cache, db = store
    _write_cache(cache, "alfred_PAYEMS", {"2026-01-01": 5.0})
    s = capture_raw_cache(cache, db, vintage_date=datetime.date(2026, 7, 1))
    assert s["files"] == 0 and s["new_rows"] == 0

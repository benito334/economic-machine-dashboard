"""Append-only point-in-time vintage store → history.duckdb.

The raw-data backbone for the hypothesis_machine (the rules-R&D project):
every pipeline run, snapshot the RAW fetched series (the raw_cache parquets —
all providers cache there per build rule 5) and append any value that is new
or has changed, stamped with today's vintage date. Nothing is ever updated or
deleted — the store answers "what did we believe series X's value for date D
was, as of date V?".

Two tables:
  raw_observations(series_key, obs_date, value, vintage_date)  — append-only log
  latest_values(series_key, obs_date, value)                   — current mirror,
      used only to detect changes cheaply (O(changed rows) per run)

series_key = raw-cache filename stem (e.g. "fred_PAYEMS", "wb_USA_SI_POV_GINI",
"estat_sts_inpr_m_geo=EA20...") — provider-prefixed and stable.

Consumers (hypothesis_machine) open history.duckdb READ-ONLY. The publication
calendar falls out of the log: MIN(vintage_date) per (series_key, obs_date) is
the first day we saw that observation.

Excluded: alfred_*.parquet (already vintage data, different shape) and *_meta
sidecars. A capture where nothing changed appends nothing.
"""
from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

HISTORY_DB = Path(os.environ.get(
    "HISTORY_DB_PATH", "/mnt/data/db/all_weather/indicators_machine/history.duckdb"))
RAW_CACHE_DIR = Path(os.environ.get(
    "RAW_CACHE_DIR", "/mnt/data/project_data/all_weather/indicators_machine/raw_cache"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_observations (
    series_key   VARCHAR NOT NULL,
    obs_date     DATE    NOT NULL,
    value        DOUBLE  NOT NULL,
    vintage_date DATE    NOT NULL,
    PRIMARY KEY (series_key, obs_date, vintage_date)
);
CREATE TABLE IF NOT EXISTS latest_values (
    series_key   VARCHAR NOT NULL,
    obs_date     DATE    NOT NULL,
    value        DOUBLE  NOT NULL,
    PRIMARY KEY (series_key, obs_date)
);
"""


def _read_cache_parquet(path: Path) -> "pd.DataFrame | None":
    """Return DataFrame(obs_date, value) from a raw-cache parquet, or None."""
    try:
        df = pd.read_parquet(path)
    except Exception as exc:                     # noqa: BLE001 — skip unreadable
        logger.warning("[vintage] unreadable %s: %s", path.name, exc)
        return None
    if df.empty:
        return None
    # Value column: 'value' by convention; fall back to the first numeric column.
    col = "value" if "value" in df.columns else None
    if col is None:
        numeric = df.select_dtypes("number").columns
        if len(numeric) == 0:
            return None
        col = numeric[0]
    out = pd.DataFrame({
        "obs_date": pd.to_datetime(df.index, errors="coerce"),
        "value": pd.to_numeric(df[col], errors="coerce"),
    }).dropna()
    if out.empty:
        return None
    out["obs_date"] = out["obs_date"].dt.date
    # De-dup within a file (guard) — keep last
    out = out.drop_duplicates(subset=["obs_date"], keep="last")
    return out


def capture_raw_cache(
    raw_cache_dir: Path | None = None,
    history_db: Path | None = None,
    vintage_date: datetime.date | None = None,
) -> dict:
    """Snapshot every raw-cache parquet into the vintage store.

    Appends one row per (series, obs) whose value is NEW or CHANGED versus the
    stored mirror, stamped with `vintage_date` (default: today). Returns stats.
    """
    raw_cache_dir = raw_cache_dir or RAW_CACHE_DIR
    history_db = history_db or HISTORY_DB
    vintage_date = vintage_date or datetime.date.today()

    files = sorted(
        p for p in raw_cache_dir.glob("*.parquet")
        if not p.name.startswith("alfred_")
    )
    history_db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(history_db))
    con.execute(_SCHEMA)

    stats = {"files": 0, "new_rows": 0, "new_series": 0}
    try:
        known_series = {r[0] for r in con.execute(
            "SELECT DISTINCT series_key FROM latest_values").fetchall()}
        for path in files:
            frame = _read_cache_parquet(path)
            if frame is None:
                continue
            key = path.stem
            stats["files"] += 1
            if key not in known_series:
                stats["new_series"] += 1
            frame = frame.assign(series_key=key)
            con.register("_incoming", frame)
            # Changed or brand-new observations only.
            con.execute("""
                INSERT INTO raw_observations
                SELECT i.series_key, i.obs_date, i.value, ?::DATE
                FROM _incoming i
                LEFT JOIN latest_values l
                  ON l.series_key = i.series_key AND l.obs_date = i.obs_date
                WHERE l.series_key IS NULL OR l.value IS DISTINCT FROM i.value
            """, [vintage_date])
            # Mirror upsert (DuckDB: delete+insert of changed rows)
            con.execute("""
                DELETE FROM latest_values WHERE (series_key, obs_date) IN (
                    SELECT i.series_key, i.obs_date FROM _incoming i
                    LEFT JOIN latest_values l
                      ON l.series_key = i.series_key AND l.obs_date = i.obs_date
                    WHERE l.series_key IS NOT NULL
                      AND l.value IS DISTINCT FROM i.value)
            """)
            con.execute("""
                INSERT OR IGNORE INTO latest_values
                SELECT series_key, obs_date, value FROM _incoming
            """)
            con.unregister("_incoming")
        stats["new_rows"] = con.execute(
            "SELECT count(*) FROM raw_observations WHERE vintage_date = ?",
            [vintage_date]).fetchone()[0]
    finally:
        con.close()
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = capture_raw_cache()
    print(f"captured: {s['files']} series scanned, {s['new_rows']} vintage rows "
          f"written today, {s['new_series']} new series")

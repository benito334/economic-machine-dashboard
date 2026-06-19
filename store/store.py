from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List

import duckdb
import pandas as pd

from indicators.models import Signal

DB_PATH = Path(os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"))

_CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id              VARCHAR   NOT NULL,
    country         VARCHAR   NOT NULL,
    force           VARCHAR   NOT NULL,
    lead_lag        VARCHAR   NOT NULL,
    as_of           DATE      NOT NULL,
    value           DOUBLE,
    units           VARCHAR   DEFAULT '',
    level_percentile DOUBLE,
    zscore          DOUBLE,
    change_1m       DOUBLE,
    change_3m       DOUBLE,
    change_12m      DOUBLE,
    direction       VARCHAR,
    equilibrium_estimate       DOUBLE,
    distance_from_equilibrium  DOUBLE,
    surprise        DOUBLE,
    is_constructed  BOOLEAN   DEFAULT FALSE,
    is_proxy        BOOLEAN   DEFAULT FALSE,
    is_stale        BOOLEAN   DEFAULT FALSE,
    low_history     BOOLEAN   DEFAULT FALSE,
    provider        VARCHAR   DEFAULT '',
    source_tier     VARCHAR   DEFAULT 'free',
    vintage_available BOOLEAN DEFAULT FALSE,
    linkage         VARCHAR   DEFAULT '',
    source          VARCHAR   DEFAULT '',
    ingested_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (id, as_of)
)
"""

_SIGNAL_COLUMNS = [
    "id", "country", "force", "lead_lag", "as_of", "value", "units",
    "level_percentile", "zscore", "change_1m", "change_3m", "change_12m",
    "direction", "equilibrium_estimate", "distance_from_equilibrium",
    "surprise", "is_constructed", "is_proxy", "is_stale", "low_history",
    "provider", "source_tier", "vintage_available", "linkage", "source",
    "ingested_at",
]


def get_connection(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_CREATE_SIGNALS)
    conn.execute(_CREATE_COMPOSITES)


def delete_future_signals(conn: duckdb.DuckDBPyConnection) -> int:
    """Remove forecast-like rows that violate the observation-date contract."""
    count = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE as_of > CURRENT_DATE"
    ).fetchone()[0]
    if count:
        conn.execute("DELETE FROM signals WHERE as_of > CURRENT_DATE")
    return count


def upsert_signals(conn: duckdb.DuckDBPyConnection, signals: List[Signal]) -> int:
    if not signals:
        return 0

    now = datetime.now(timezone.utc)
    rows = []
    for s in signals:
        row = s.model_dump()
        row["as_of"] = row["as_of"].isoformat()
        row["ingested_at"] = now
        rows.append(row)

    df = pd.DataFrame(rows)
    conn.register("_staging", df)

    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute("""
            DELETE FROM signals
            WHERE EXISTS (
                SELECT 1 FROM _staging
                WHERE _staging.id = signals.id
                  AND _staging.as_of::DATE = signals.as_of
            )
        """)
        columns = ", ".join(_SIGNAL_COLUMNS)
        conn.execute(
            f"INSERT INTO signals ({columns}) SELECT {columns} FROM _staging"
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_staging")

    return len(df)


def query_latest(conn: duckdb.DuckDBPyConnection, country: str = "US") -> pd.DataFrame:
    """Return the most recent Signal for every concept in a given country."""
    return conn.execute("""
        SELECT * FROM signals
        WHERE (id, as_of) IN (
            SELECT id, MAX(as_of) FROM signals
            WHERE country = ?
            GROUP BY id
        )
        ORDER BY force, lead_lag, id
    """, [country]).df()


_CREATE_COMPOSITES = """
CREATE TABLE IF NOT EXISTS composites (
    country              VARCHAR   NOT NULL,
    as_of                DATE      NOT NULL,
    growth_score         DOUBLE,
    inflation_score      DOUBLE,
    quadrant             VARCHAR,
    confidence           DOUBLE,
    disequilibrium_score DOUBLE,
    n_growth_signals     INTEGER   DEFAULT 0,
    n_inflation_signals  INTEGER   DEFAULT 0,
    n_forces             INTEGER   DEFAULT 0,
    low_coverage         BOOLEAN   DEFAULT FALSE,
    created_at           TIMESTAMP NOT NULL,
    PRIMARY KEY (country, as_of)
)
"""

_COMPOSITE_COLUMNS = [
    "country", "as_of", "growth_score", "inflation_score", "quadrant",
    "confidence", "disequilibrium_score", "n_growth_signals",
    "n_inflation_signals", "n_forces", "low_coverage", "created_at",
]


def init_composites_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_CREATE_COMPOSITES)


def upsert_composites(conn: duckdb.DuckDBPyConnection, snapshots: list) -> int:
    if not snapshots:
        return 0

    now = datetime.now(timezone.utc)
    rows = []
    for s in snapshots:
        row = s.model_dump()
        if row["as_of"] > date.today():
            continue
        row["as_of"] = row["as_of"].isoformat()
        row["created_at"] = now
        rows.append(row)

    if not rows:
        conn.execute("DELETE FROM composites WHERE as_of > CURRENT_DATE")
        return 0

    df = pd.DataFrame(rows)
    conn.register("_composite_staging", df)
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute("DELETE FROM composites WHERE as_of > CURRENT_DATE")
        conn.execute("""
            DELETE FROM composites
            WHERE EXISTS (
                SELECT 1 FROM _composite_staging
                WHERE _composite_staging.country = composites.country
                  AND DATE_TRUNC('month', _composite_staging.as_of::DATE)
                      = DATE_TRUNC('month', composites.as_of)
            )
        """)
        cols = ", ".join(_COMPOSITE_COLUMNS)
        conn.execute(f"INSERT INTO composites ({cols}) SELECT {cols} FROM _composite_staging")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_composite_staging")

    return len(df)


def query_composite_history(
    conn: duckdb.DuckDBPyConnection,
    country: str,
    start: str | None = None,
) -> pd.DataFrame:
    if start:
        return conn.execute(
            "SELECT * FROM composites WHERE country = ? AND as_of >= ? ORDER BY as_of",
            [country, start],
        ).df()
    return conn.execute(
        "SELECT * FROM composites WHERE country = ? ORDER BY as_of", [country]
    ).df()


def query_series(
    conn: duckdb.DuckDBPyConnection,
    signal_id: str,
    start: str | None = None,
) -> pd.DataFrame:
    """Return the full time-series for one signal ID."""
    if start:
        return conn.execute(
            "SELECT * FROM signals WHERE id = ? AND as_of >= ? ORDER BY as_of",
            [signal_id, start],
        ).df()
    return conn.execute(
        "SELECT * FROM signals WHERE id = ? ORDER BY as_of", [signal_id]
    ).df()

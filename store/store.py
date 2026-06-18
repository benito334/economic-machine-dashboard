from __future__ import annotations

import os
from datetime import datetime, timezone
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


def get_connection(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_CREATE_SIGNALS)


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
        conn.execute("""
            DELETE FROM signals
            WHERE EXISTS (
                SELECT 1 FROM _staging
                WHERE _staging.id = signals.id
                  AND _staging.as_of::DATE = signals.as_of
            )
        """)
        conn.execute("INSERT INTO signals SELECT * FROM _staging")
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

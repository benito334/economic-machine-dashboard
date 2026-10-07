from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

import duckdb
import pandas as pd

from indicators.models import Signal

DB_PATH = Path(os.environ.get("DB_PATH", "/mnt/data/db/finance/indicators_machine/signals.duckdb"))

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
    momentum_percentile DOUBLE,
    direction       VARCHAR,
    equilibrium_estimate       DOUBLE,
    distance_from_equilibrium  DOUBLE,
    surprise        DOUBLE,
    zscore_12m      DOUBLE,
    zscore_18m      DOUBLE,
    zscore_24m      DOUBLE,
    zscore_36m      DOUBLE,
    zscore_48m      DOUBLE,
    zscore_60m      DOUBLE,
    zscore_90m      DOUBLE,
    zscore_120m     DOUBLE,
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
    "momentum_percentile", "direction", "equilibrium_estimate", "distance_from_equilibrium",
    "surprise",
    "zscore_12m", "zscore_18m", "zscore_24m", "zscore_36m", "zscore_48m", "zscore_60m",
    "zscore_90m", "zscore_120m",
    "is_constructed", "is_proxy", "is_stale", "low_history",
    "provider", "source_tier", "vintage_available", "linkage", "source",
    "ingested_at",
]


def get_connection(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


_CREATE_WEIGHT_CHANGE_LOG = """
CREATE TABLE IF NOT EXISTS weight_change_log (
    log_id      BIGINT    NOT NULL,
    changed_at  TIMESTAMP NOT NULL,
    country     VARCHAR   NOT NULL,
    signal_id   VARCHAR   NOT NULL,
    basket      VARCHAR   NOT NULL,
    old_importance DOUBLE NOT NULL,
    new_importance DOUBLE NOT NULL,
    delta       DOUBLE    NOT NULL,
    reason      VARCHAR   DEFAULT '',
    source      VARCHAR   DEFAULT 'manual'
)
"""


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_CREATE_SIGNALS)
    conn.execute(_CREATE_COMPOSITES)
    conn.execute(_CREATE_DEBT_STRESS)
    conn.execute(_CREATE_DEBT_CYCLE_STAGE)
    conn.execute(_CREATE_WEIGHT_CHANGE_LOG)
    conn.execute(_CREATE_VALIDATOR_VERDICTS)
    # Migrations for databases created by earlier releases.
    conn.execute(
        "ALTER TABLE debt_stress_snapshots "
        "ADD COLUMN IF NOT EXISTS stale_components VARCHAR DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE debt_stress_snapshots "
        "ADD COLUMN IF NOT EXISTS extrapolated_components VARCHAR DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE composites "
        "ADD COLUMN IF NOT EXISTS stale_signals VARCHAR DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE composites ADD COLUMN IF NOT EXISTS growth_momentum DOUBLE"
    )
    conn.execute(
        "ALTER TABLE composites ADD COLUMN IF NOT EXISTS inflation_momentum DOUBLE"
    )
    conn.execute(
        "ALTER TABLE composites ADD COLUMN IF NOT EXISTS weight_audit VARCHAR DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS momentum_percentile DOUBLE"
    )
    # Sovereign-aware stage classifier (Ray Dalio ruling, 2026-07-06 session).
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS stage_private VARCHAR"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS stage_sovereign VARCHAR"
    )
    # NOTE: no DEFAULT clause on this ALTER — DuckDB (verified 1.5.4) silently
    # RESETS EVERY EXISTING ROW to the default when a BOOLEAN column with an
    # explicit DEFAULT is re-added via ADD COLUMN IF NOT EXISTS on a column
    # that already exists (VARCHAR/DOUBLE/INTEGER defaults and BOOLEAN with
    # no default are all unaffected — reproduced and confirmed in isolation).
    # Since init_schema() runs on every process start, a DEFAULT here would
    # wipe sovereign_squeeze back to NULL/false on every restart. New rows
    # always set it explicitly via model_dump(); the CREATE TABLE above still
    # carries DEFAULT FALSE for genuinely fresh databases.
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS sovereign_squeeze BOOLEAN"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS feat_gov_interest_z DOUBLE"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS feat_refi_gap DOUBLE"
    )
    # Debt-growth-vs-income-growth spread (Ray Dalio consult, 2026-08-19 session).
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS feat_spread_household DOUBLE"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS feat_spread_corporate DOUBLE"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS feat_spread_government DOUBLE"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS debt_income_spread_flag VARCHAR"
    )
    # Foreign-vs-domestic-currency government debt split (coverage-audit High item #4, 2026-10-03).
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS feat_fx_debt_share DOUBLE"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS fx_debt_share_flag VARCHAR"
    )
    # FX reserve runway (coverage-audit follow-up, 2026-10-03).
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS feat_fx_reserve_runway DOUBLE"
    )
    conn.execute(
        "ALTER TABLE debt_cycle_stage_snapshots ADD COLUMN IF NOT EXISTS fx_reserve_runway_flag VARCHAR"
    )
    for _col in ("zscore_12m", "zscore_18m", "zscore_24m", "zscore_36m", "zscore_48m", "zscore_60m",
                 "zscore_90m", "zscore_120m"):
        conn.execute(f"ALTER TABLE signals ADD COLUMN IF NOT EXISTS {_col} DOUBLE")
    for _col in (
        "growth_score_36m", "growth_score_48m", "growth_score_60m",
        "inflation_score_36m", "inflation_score_48m", "inflation_score_60m",
        "inflation_score_90m", "inflation_score_120m",
        "disequilibrium_12m", "disequilibrium_18m", "disequilibrium_24m",
        "rate_score", "credit_score", "rate_momentum", "credit_momentum",
        "volatility_score", "volatility_momentum",
        "productivity_score", "productivity_momentum",
    ):
        conn.execute(f"ALTER TABLE composites ADD COLUMN IF NOT EXISTS {_col} DOUBLE")


def delete_future_signals(conn: duckdb.DuckDBPyConnection) -> int:
    """Remove forecast-like rows that violate the observation-date contract."""
    count = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE as_of > CURRENT_DATE"
    ).fetchone()[0]
    if count:
        conn.execute("DELETE FROM signals WHERE as_of > CURRENT_DATE")
    return count


def _upsert_in_place(
    conn: duckdb.DuckDBPyConnection, table: str, staging: str,
    columns: list, keys: list,
) -> None:
    """INSERT … ON CONFLICT (keys) DO UPDATE — the one way every table here is upserted.

    Why not DELETE-then-INSERT (what this module used to do everywhere): on a table with
    a PRIMARY KEY, DuckDB cannot physically reclaim DELETEd tuples — they stay in their
    row groups forever. A pipeline that rewrites its whole history each run therefore
    leaked one full copy of the table per run (measured 2026-10-04: signals went from
    368,150 live rows to 52,051,808 physical rows / 10.9 GB over ~140 runs; replaying the
    same churn on a copy with the PK dropped stayed flat, and ON CONFLICT DO UPDATE with
    the PK kept also stayed flat). An UPDATE of non-key columns happens in place, so it
    leaves nothing behind, and the PK stays as the actual idempotency guarantee
    (CLAUDE.md rule #6) instead of being worked around.

    Only the listed columns are SET, so columns owned by a later pass (e.g. composites'
    rolling-window columns) are left intact rather than blanked by the baseline write.

    Guards against a silent data loss case verified against this DuckDB build: if the
    staging batch itself contains two rows sharing the same conflict key, ON CONFLICT DO
    UPDATE applies only the first and drops the rest with no error — whereas the old
    DELETE-then-INSERT this replaced hit the table's PRIMARY KEY and raised loudly on the
    same input. A duplicate key in one batch means a loader/transform bug produced two
    observations for the same (id, as_of) (or equivalent); that must fail the pipeline
    pass the same way CLAUDE.md requires other bad-ingestion cases to fail, not silently
    keep an arbitrary one of the two values.
    """
    key_cols = ", ".join(keys)
    dupes = conn.execute(
        f"SELECT {key_cols}, COUNT(*) FROM {staging} GROUP BY {key_cols} HAVING COUNT(*) > 1"
    ).fetchall()
    if dupes:
        raise ValueError(
            f"{table}: staging batch has {len(dupes)} duplicate-key row group(s) on "
            f"({key_cols}) — refusing to upsert (ON CONFLICT would silently drop all but "
            f"one row per group). First few: {dupes[:5]}"
        )
    cols = ", ".join(columns)
    sets = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in keys)
    conn.execute(
        f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {staging} "
        f"ON CONFLICT ({key_cols}) DO UPDATE SET {sets}"
    )


def _delete_stale_bucket_rows(
    conn: duckdb.DuckDBPyConnection, table: str, staging: str, bucket: str,
) -> None:
    """Remove rows that share a (country, month|quarter) bucket with a staged row but
    carry a *different* as_of — e.g. yesterday's mid-month snapshot once today's has
    moved the latest date. Rows whose as_of matches a staged row are left for
    _upsert_in_place to update. Normally a handful of rows per run, not the table."""
    conn.execute(f"""
        DELETE FROM {table}
        WHERE EXISTS (
            SELECT 1 FROM {staging} s
            WHERE s.country = {table}.country
              AND DATE_TRUNC('{bucket}', s.as_of::DATE) = DATE_TRUNC('{bucket}', {table}.as_of)
        )
        AND NOT EXISTS (
            SELECT 1 FROM {staging} s
            WHERE s.country = {table}.country AND s.as_of::DATE = {table}.as_of
        )
    """)


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
        _upsert_in_place(conn, "signals", "_staging", _SIGNAL_COLUMNS, ["id", "as_of"])
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
    stale_signals        VARCHAR   DEFAULT '',
    growth_momentum      DOUBLE,
    inflation_momentum   DOUBLE,
    weight_audit         VARCHAR   DEFAULT '',
    growth_score_36m     DOUBLE,
    growth_score_48m     DOUBLE,
    growth_score_60m     DOUBLE,
    inflation_score_36m  DOUBLE,
    inflation_score_48m  DOUBLE,
    inflation_score_60m  DOUBLE,
    inflation_score_90m  DOUBLE,
    inflation_score_120m DOUBLE,
    disequilibrium_12m   DOUBLE,
    disequilibrium_18m   DOUBLE,
    disequilibrium_24m   DOUBLE,
    rate_score           DOUBLE,
    credit_score         DOUBLE,
    rate_momentum        DOUBLE,
    credit_momentum      DOUBLE,
    volatility_score     DOUBLE,
    volatility_momentum  DOUBLE,
    productivity_score   DOUBLE,
    productivity_momentum DOUBLE,
    created_at           TIMESTAMP NOT NULL,
    PRIMARY KEY (country, as_of)
)
"""

_COMPOSITE_COLUMNS = [
    "country", "as_of", "growth_score", "inflation_score", "quadrant",
    "confidence", "disequilibrium_score", "n_growth_signals",
    "n_inflation_signals", "n_forces", "low_coverage", "stale_signals",
    "growth_momentum", "inflation_momentum",
    "rate_score", "credit_score", "rate_momentum", "credit_momentum",
    "volatility_score", "volatility_momentum",
    "productivity_score", "productivity_momentum",
    "weight_audit",
    "created_at",
]
# Rolling composite columns are written by update_rolling_composites() after the baseline insert.
_ROLLING_COMPOSITE_SUFFIXES = [
    ("36m", "12m"),
    ("48m", "18m"),
    ("60m", "24m"),
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
        _delete_stale_bucket_rows(conn, "composites", "_composite_staging", "month")
        _upsert_in_place(conn, "composites", "_composite_staging",
                         _COMPOSITE_COLUMNS, ["country", "as_of"])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_composite_staging")

    return len(df)


def update_rolling_composites(
    conn: duckdb.DuckDBPyConnection,
    snapshots: list,
    force_suffix: str,
    diseq_suffix: str,
) -> int:
    """
    Batch-update rolling composite columns on existing rows.

    snapshots: list of CompositeSnapshot produced by compute_composite_history()
               with a non-default zscore_col / diseq_window.
    force_suffix: e.g. "36m" → writes growth_score_36m, inflation_score_36m
    diseq_suffix:  e.g. "12m" → writes disequilibrium_12m
    """
    if not snapshots:
        return 0

    rows = [
        {
            "country": s.country,
            "as_of": s.as_of.isoformat(),
            f"growth_score_{force_suffix}": s.growth_score,
            f"inflation_score_{force_suffix}": s.inflation_score,
            f"disequilibrium_{diseq_suffix}": s.disequilibrium_score,
        }
        for s in snapshots
        if s.as_of <= date.today()
    ]
    if not rows:
        return 0

    df = pd.DataFrame(rows)
    conn.register("_rolling_staging", df)
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute(f"""
            UPDATE composites
            SET
                growth_score_{force_suffix}    = s.growth_score_{force_suffix},
                inflation_score_{force_suffix} = s.inflation_score_{force_suffix},
                disequilibrium_{diseq_suffix}  = s.disequilibrium_{diseq_suffix}
            FROM _rolling_staging AS s
            WHERE composites.country = s.country
              AND DATE_TRUNC('month', composites.as_of) = DATE_TRUNC('month', s.as_of::DATE)
        """)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_rolling_staging")

    return len(df)


def update_inflation_rolling(
    conn: duckdb.DuckDBPyConnection,
    snapshots: list,
    force_suffix: str,
) -> int:
    """Batch-update inflation-only rolling column on existing rows.

    Used for inflation-specific look-back windows (90m / 120m) that are
    longer than the growth windows and have no matching disequilibrium column.
    force_suffix: e.g. "90m" → writes inflation_score_90m only.
    """
    if not snapshots:
        return 0

    rows = [
        {
            "country": s.country,
            "as_of":   s.as_of.isoformat(),
            f"inflation_score_{force_suffix}": s.inflation_score,
        }
        for s in snapshots
        if s.as_of <= date.today()
    ]
    if not rows:
        return 0

    df = pd.DataFrame(rows)
    conn.register("_infl_rolling_staging", df)
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute(f"""
            UPDATE composites
            SET inflation_score_{force_suffix} = s.inflation_score_{force_suffix}
            FROM _infl_rolling_staging AS s
            WHERE composites.country = s.country
              AND DATE_TRUNC('month', composites.as_of) = DATE_TRUNC('month', s.as_of::DATE)
        """)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_infl_rolling_staging")

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


# ─── Long-Term Debt Stress table ─────────────────────────────────────────────

_CREATE_DEBT_STRESS = """
CREATE TABLE IF NOT EXISTS debt_stress_snapshots (
    country                        VARCHAR   NOT NULL,
    as_of                          DATE      NOT NULL,
    stress_score                   DOUBLE,
    n_components                   INTEGER   DEFAULT 0,
    retained_weight                DOUBLE,
    low_coverage                   BOOLEAN   DEFAULT FALSE,
    stale_components               VARCHAR   DEFAULT '',
    z_gov_household_debt_gdp       DOUBLE,
    z_corporate_debt_gdp           DOUBLE,
    z_household_debt_service       DOUBLE,
    z_federal_interest_gdp         DOUBLE,
    z_primary_balance_gdp          DOUBLE,
    z_structural_balance           DOUBLE,
    z_govt_revenue_gdp             DOUBLE,
    val_gov_household_debt_gdp     DOUBLE,
    val_corporate_debt_gdp         DOUBLE,
    val_household_debt_service     DOUBLE,
    val_federal_interest_gdp       DOUBLE,
    val_primary_balance_gdp        DOUBLE,
    val_structural_balance         DOUBLE,
    val_govt_revenue_gdp           DOUBLE,
    extrapolated_components        VARCHAR   DEFAULT '',
    created_at                     TIMESTAMP NOT NULL,
    PRIMARY KEY (country, as_of)
)
"""

_DEBT_STRESS_COLUMNS = [
    "country", "as_of", "stress_score", "n_components", "retained_weight",
    "low_coverage", "stale_components",
    "z_gov_household_debt_gdp", "z_corporate_debt_gdp", "z_household_debt_service",
    "z_federal_interest_gdp", "z_primary_balance_gdp", "z_structural_balance",
    "z_govt_revenue_gdp",
    "val_gov_household_debt_gdp", "val_corporate_debt_gdp", "val_household_debt_service",
    "val_federal_interest_gdp", "val_primary_balance_gdp", "val_structural_balance",
    "val_govt_revenue_gdp",
    "extrapolated_components",
    "created_at",
]


def upsert_debt_stress(conn: duckdb.DuckDBPyConnection, snapshots: list) -> int:
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
        # Serialise lists → comma-separated strings for VARCHAR storage
        row["stale_components"] = ",".join(row.get("stale_components") or [])
        row["extrapolated_components"] = ",".join(row.get("extrapolated_components") or [])
        rows.append(row)

    if not rows:
        conn.execute("DELETE FROM debt_stress_snapshots WHERE as_of > CURRENT_DATE")
        return 0

    df = pd.DataFrame(rows)
    conn.register("_debt_stress_staging", df)
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute("DELETE FROM debt_stress_snapshots WHERE as_of > CURRENT_DATE")
        _delete_stale_bucket_rows(conn, "debt_stress_snapshots", "_debt_stress_staging", "quarter")
        _upsert_in_place(conn, "debt_stress_snapshots", "_debt_stress_staging",
                         _DEBT_STRESS_COLUMNS, ["country", "as_of"])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_debt_stress_staging")

    return len(df)


def query_debt_stress_history(
    conn: duckdb.DuckDBPyConnection,
    country: str,
    start: str | None = None,
) -> pd.DataFrame:
    if start:
        return conn.execute(
            "SELECT * FROM debt_stress_snapshots WHERE country = ? AND as_of >= ? ORDER BY as_of",
            [country, start],
        ).df()
    return conn.execute(
        "SELECT * FROM debt_stress_snapshots WHERE country = ? ORDER BY as_of", [country]
    ).df()


# ─── Long-Term Debt-Cycle Stage table (roadmap Phase C) ──────────────────────

_CREATE_DEBT_CYCLE_STAGE = """
CREATE TABLE IF NOT EXISTS debt_cycle_stage_snapshots (
    country                 VARCHAR   NOT NULL,
    as_of                   DATE      NOT NULL,
    stage                   VARCHAR,
    stage_raw               VARCHAR,
    stage_private           VARCHAR,
    stage_sovereign         VARCHAR,
    sovereign_squeeze        BOOLEAN   DEFAULT FALSE,
    confidence              DOUBLE,
    n_features              INTEGER   DEFAULT 0,
    missing_features        VARCHAR   DEFAULT '',
    score_leveraging        DOUBLE,
    score_squeeze           DOUBLE,
    score_deleveraging      DOUBLE,
    score_reflation         DOUBLE,
    feat_debt_pct           DOUBLE,
    feat_debt_traj          DOUBLE,
    feat_dsr_trend          DOUBLE,
    feat_r_minus_g          DOUBLE,
    feat_ngdp_minus_yield   DOUBLE,
    feat_real_growth        DOUBLE,
    feat_gov_interest_z     DOUBLE,
    feat_refi_gap           DOUBLE,
    feat_spread_household   DOUBLE,
    feat_spread_corporate   DOUBLE,
    feat_spread_government  DOUBLE,
    debt_income_spread_flag VARCHAR,
    feat_fx_debt_share      DOUBLE,
    fx_debt_share_flag      VARCHAR,
    feat_fx_reserve_runway  DOUBLE,
    fx_reserve_runway_flag  VARCHAR,
    created_at              TIMESTAMP NOT NULL,
    PRIMARY KEY (country, as_of)
)
"""

_DEBT_CYCLE_STAGE_COLUMNS = [
    "country", "as_of", "stage", "stage_raw",
    "stage_private", "stage_sovereign", "sovereign_squeeze",
    "confidence", "n_features",
    "missing_features",
    "score_leveraging", "score_squeeze", "score_deleveraging", "score_reflation",
    "feat_debt_pct", "feat_debt_traj", "feat_dsr_trend", "feat_r_minus_g",
    "feat_ngdp_minus_yield", "feat_real_growth",
    "feat_gov_interest_z", "feat_refi_gap",
    "feat_spread_household", "feat_spread_corporate", "feat_spread_government",
    "debt_income_spread_flag",
    "feat_fx_debt_share", "fx_debt_share_flag",
    "feat_fx_reserve_runway", "fx_reserve_runway_flag",
    "created_at",
]


def upsert_debt_cycle_stage(conn: duckdb.DuckDBPyConnection, snapshots: list) -> int:
    """Idempotent upsert of DebtCycleStageSnapshot rows on (country, quarter)."""
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
        row["missing_features"] = ",".join(row.get("missing_features") or [])
        rows.append(row)

    if not rows:
        return 0

    df = pd.DataFrame(rows)
    conn.register("_stage_staging", df)
    try:
        conn.execute("BEGIN TRANSACTION")
        _delete_stale_bucket_rows(conn, "debt_cycle_stage_snapshots", "_stage_staging", "quarter")
        _upsert_in_place(conn, "debt_cycle_stage_snapshots", "_stage_staging",
                         _DEBT_CYCLE_STAGE_COLUMNS, ["country", "as_of"])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_stage_staging")

    return len(df)


def query_debt_cycle_stage_history(
    conn: duckdb.DuckDBPyConnection,
    country: str,
    start: str | None = None,
) -> pd.DataFrame:
    if start:
        return conn.execute(
            "SELECT * FROM debt_cycle_stage_snapshots WHERE country = ? AND as_of >= ? ORDER BY as_of",
            [country, start],
        ).df()
    return conn.execute(
        "SELECT * FROM debt_cycle_stage_snapshots WHERE country = ? ORDER BY as_of", [country]
    ).df()


# ── External validator verdicts (docs/external_validators_plan.md, 2026-10-03) ─
#
# Schema is locked to CreovaOne's existing consumer query
# (IndicatorsMachineMacroAdapter.validator_verdicts() in that project) — column
# names/order must not change without updating that side too. Keeps full
# history (as_of is part of the primary key, not just the latest row) so a
# detail page can show how a verdict evolved; the consumer picks the latest
# per (axis, validator_key) itself (e.g. CreovaOne's own QUALIFY ROW_NUMBER()).

_CREATE_VALIDATOR_VERDICTS = """
CREATE TABLE IF NOT EXISTS validator_verdicts (
    country          VARCHAR   NOT NULL,
    as_of            DATE      NOT NULL,
    axis             VARCHAR   NOT NULL,
    validator_key    VARCHAR   NOT NULL,
    chip_label       VARCHAR,
    benchmark_state  VARCHAR,
    verdict          VARCHAR   NOT NULL,
    spearman_full    DOUBLE,
    best_lag_months  INTEGER,
    latest_value     DOUBLE,
    latest_date      DATE,
    note             VARCHAR   DEFAULT '',
    created_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (country, as_of, axis, validator_key)
)
"""

_VALIDATOR_VERDICTS_COLUMNS = [
    "country", "as_of", "axis", "validator_key", "chip_label", "benchmark_state",
    "verdict", "spearman_full", "best_lag_months", "latest_value", "latest_date",
    "note", "created_at",
]


def upsert_validator_verdicts(conn: duckdb.DuckDBPyConnection, verdicts: list) -> int:
    """Idempotent upsert of ValidatorVerdict rows on (country, as_of, axis,
    validator_key) — re-running the same day's job overwrites that day's rows
    rather than duplicating them; prior days' rows are untouched history."""
    if not verdicts:
        return 0

    now = datetime.now(timezone.utc)
    rows = []
    for v in verdicts:
        row = v.model_dump()
        row["as_of"] = row["as_of"].isoformat()
        if row.get("latest_date") is not None:
            row["latest_date"] = row["latest_date"].isoformat()
        row["created_at"] = now
        rows.append(row)

    df = pd.DataFrame(rows)
    conn.register("_validator_staging", df)
    try:
        conn.execute("BEGIN TRANSACTION")
        _upsert_in_place(conn, "validator_verdicts", "_validator_staging",
                         _VALIDATOR_VERDICTS_COLUMNS,
                         ["country", "as_of", "axis", "validator_key"])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("_validator_staging")

    return len(df)


def query_latest_validator_verdicts(
    conn: duckdb.DuckDBPyConnection, country: str = "US",
) -> pd.DataFrame:
    """The most recent row per (axis, validator_key) for one country — the
    same "latest per benchmark" grain CreovaOne's own QUALIFY query picks."""
    return conn.execute("""
        SELECT * FROM validator_verdicts
        WHERE country = ?
        QUALIFY row_number() OVER (
            PARTITION BY axis, validator_key ORDER BY as_of DESC, created_at DESC
        ) = 1
        ORDER BY axis ASC, validator_key ASC
    """, [country]).df()


def log_weight_changes(
    conn: duckdb.DuckDBPyConnection,
    changes: list[dict],
    reason: str = "",
    source: str = "manual",
) -> int:
    """Insert rows into weight_change_log.

    Each entry in `changes` must have:
        country, signal_id, basket, old_importance, new_importance
    """
    if not changes:
        return 0

    # Determine next log_id
    result = conn.execute("SELECT COALESCE(MAX(log_id), 0) FROM weight_change_log").fetchone()
    next_id = (result[0] if result else 0) + 1

    now = datetime.now(timezone.utc)
    rows = []
    for i, c in enumerate(changes):
        old = float(c["old_importance"])
        new = float(c["new_importance"])
        if round(abs(new - old), 4) < 0.001:
            continue
        rows.append((
            next_id + i,
            now,
            c["country"],
            c["signal_id"],
            c.get("basket", ""),
            old,
            new,
            round(new - old, 4),
            reason or "",
            source,
        ))

    if not rows:
        return 0

    conn.executemany(
        """INSERT INTO weight_change_log
           (log_id, changed_at, country, signal_id, basket,
            old_importance, new_importance, delta, reason, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


def query_weight_change_log(
    conn: duckdb.DuckDBPyConnection,
    country: Optional[str] = None,
) -> pd.DataFrame:
    if country:
        return conn.execute(
            "SELECT * FROM weight_change_log WHERE country = ? ORDER BY changed_at DESC",
            [country],
        ).df()
    return conn.execute(
        "SELECT * FROM weight_change_log ORDER BY changed_at DESC"
    ).df()


def update_weight_change_reason(
    conn: duckdb.DuckDBPyConnection,
    log_id: int,
    reason: str,
) -> None:
    conn.execute(
        "UPDATE weight_change_log SET reason = ? WHERE log_id = ?",
        [reason, log_id],
    )

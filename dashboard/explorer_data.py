"""Data access layer for the Phase 1E Data Explorer tab."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

DB_PATH = Path(os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"))
RAW_CACHE_DIR = Path(os.environ.get("RAW_CACHE_DIR", "/mnt/data/project_data/all_weather/indicators_machine/raw_cache"))

# Days since last update that constitutes staleness, by inferred frequency
_STALE_THRESHOLDS = {
    "daily": 5,
    "weekly": 14,
    "monthly": 50,
    "quarterly": 120,
    "annual": 400,
}


# ── Signal overview (all 59 signals, one row each) ────────────────────────────

def load_signal_overview() -> pd.DataFrame:
    """
    Return one row per US signal containing the latest snapshot values plus
    aggregate statistics.  Used to populate the signal browser table.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute("""
            WITH latest AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) AS rn
                FROM signals
                WHERE country = 'US'
            ),
            stats AS (
                SELECT id,
                       COUNT(*) AS obs_count,
                       MIN(as_of) AS first_obs,
                       MAX(as_of) AS last_obs
                FROM signals
                WHERE country = 'US'
                GROUP BY id
            )
            SELECT
                l.id,
                l.force,
                l.lead_lag,
                l.as_of         AS latest_as_of,
                l.value         AS latest_value,
                l.units,
                l.level_percentile,
                l.zscore,
                l.direction,
                l.equilibrium_estimate,
                l.distance_from_equilibrium,
                l.is_constructed,
                l.is_proxy,
                l.is_stale,
                l.low_history,
                l.vintage_available,
                l.provider,
                l.source_tier,
                l.source,
                l.linkage,
                l.ingested_at,
                s.obs_count,
                s.first_obs
            FROM latest l
            JOIN stats s ON l.id = s.id
            WHERE l.rn = 1
            ORDER BY l.force, l.id
        """).df()
    finally:
        con.close()

    df["latest_as_of"] = pd.to_datetime(df["latest_as_of"])
    df["first_obs"] = pd.to_datetime(df["first_obs"])

    today = pd.Timestamp.today().normalize()
    df["days_since_update"] = (today - df["latest_as_of"]).dt.days

    # Infer native frequency label per signal
    df["freq"] = df.apply(lambda r: _infer_freq_label(r["id"]), axis=1)

    # Build a compact flags string for display
    def _flags(row: pd.Series) -> str:
        flags = []
        if row["is_stale"]:       flags.append("STALE")
        if row["is_proxy"]:       flags.append("PROXY")
        if row["low_history"]:    flags.append("LOW-HIST")
        if not row["vintage_available"]: flags.append("NO-VINTAGE")
        return " · ".join(flags)

    df["flags"] = df.apply(_flags, axis=1)

    # Absolute Z-score for sorting
    df["abs_zscore"] = df["zscore"].abs()

    return df


def _infer_freq_label(signal_id: str) -> str:
    """Map a signal to its native frequency label based on known patterns."""
    # Daily series (rates, yields, spreads)
    daily_forces = {"policy", "premium"}
    force = signal_id.split(".")[1] if signal_id.count(".") >= 1 else ""
    if force in daily_forces and "balance_sheet" not in signal_id and "monetary_base" not in signal_id:
        return "daily"
    if "breakeven" in signal_id or "bank_loans" in signal_id:
        return "daily"
    # Weekly
    if "bank_loans" in signal_id or "balance_sheet" in signal_id:
        return "weekly"
    # Annual (WB, IMF, some FRED)
    annual_patterns = ["fdi_net", "reer_xcountry", "age_dependency", "labor_force_part_wb",
                       "population_growth", "urbanization", "current_account_gdp",
                       "exports_gdp", "imports_gdp", "rnd_intensity", "tfp",
                       "federal_deficit", "interest_payments", "primary_balance_gdp",
                       "structural_balance", "govt_revenue_gdp"]
    if any(p in signal_id for p in annual_patterns):
        return "annual"
    # Quarterly
    quarterly_patterns = ["corporate_debt", "debt_service_ratio", "gov_debt_gdp",
                          "household_debt_gdp", "lending_standards", "productivity",
                          "gdp_real", "gdp_nominal", "gdp_deflator", "monetary_base",
                          "ngdp_minus_yield", "spending_vs_labor", "current_account", "niip"]
    if any(p in signal_id for p in quarterly_patterns):
        return "quarterly"
    # Default monthly
    return "monthly"


# ── Full signal history ───────────────────────────────────────────────────────

def load_signal_detail(signal_id: str, limit: Optional[int] = None) -> pd.DataFrame:
    """
    Return all observations for one signal, all columns, newest first.
    Pass limit to cap rows (useful for the observations table pagination).
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        limit_clause = f"LIMIT {limit}" if limit else ""
        df = con.execute(
            f"""
            SELECT as_of, value, zscore, level_percentile, direction,
                   change_1m, change_3m, change_12m, distance_from_equilibrium,
                   is_stale, ingested_at
            FROM signals
            WHERE id = ?
            ORDER BY as_of DESC
            {limit_clause}
            """,
            [signal_id],
        ).df()
    finally:
        con.close()

    df["as_of"] = pd.to_datetime(df["as_of"])
    return df


# ── Gap detection ─────────────────────────────────────────────────────────────

def detect_gaps(signal_id: str) -> pd.DataFrame:
    """
    Return a DataFrame of time gaps larger than 2× the expected release cycle.
    Columns: period_end, period_start, gap_days, expected_days.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            """
            SELECT as_of,
                   LAG(as_of) OVER (ORDER BY as_of) AS prev_as_of,
                   DATEDIFF('day',
                       LAG(as_of) OVER (ORDER BY as_of),
                       as_of) AS gap_days
            FROM signals
            WHERE id = ?
            ORDER BY as_of
            """,
            [signal_id],
        ).df()
    finally:
        con.close()

    df = df.dropna(subset=["prev_as_of", "gap_days"])
    df["as_of"] = pd.to_datetime(df["as_of"])
    df["prev_as_of"] = pd.to_datetime(df["prev_as_of"])

    freq_label = _infer_freq_label(signal_id)
    freq_days = {"daily": 1, "weekly": 7, "monthly": 30, "quarterly": 91, "annual": 365}
    expected = freq_days.get(freq_label, 30)

    threshold = expected * 2
    gaps = df[df["gap_days"] > threshold].copy()
    gaps = gaps.rename(columns={"as_of": "period_end", "prev_as_of": "period_start"})
    gaps["expected_days"] = expected
    return gaps[["period_start", "period_end", "gap_days", "expected_days"]].reset_index(drop=True)


# ── Anomaly detection ─────────────────────────────────────────────────────────

def flag_anomalies(df: pd.DataFrame) -> pd.Series:
    """
    Return a boolean Series aligned to df marking rows as anomalous.
    Criteria: |zscore| > 3, or value is NaN.
    """
    return df["zscore"].abs().gt(3) | df["value"].isna()


# ── Raw cache vs processed ────────────────────────────────────────────────────

def _cache_path_for_source(source: str) -> Optional[Path]:
    """
    Resolve a source string (e.g. 'FRED:PAYEMS', 'WorldBank:NE.EXP.GNFS.ZS',
    'IMF:pb') to the parquet cache path, or None if no cache exists.
    """
    if not source or ":" not in source:
        return None
    provider, series_id = source.split(":", 1)
    provider = provider.strip()
    series_id = series_id.strip()

    if provider == "FRED":
        p = RAW_CACHE_DIR / f"fred_{series_id}.parquet"
    elif provider == "WorldBank":
        safe_id = series_id.replace(".", "_")
        p = RAW_CACHE_DIR / f"wb_US_{safe_id}.parquet"
    elif provider == "IMF":
        safe_id = series_id.replace(".", "_")
        p = RAW_CACHE_DIR / f"imf_US_{safe_id}.parquet"
    else:
        return None

    return p if p.exists() else None


def load_raw_cache_series(source: str) -> Optional[pd.Series]:
    """
    Load the raw (pre-transform) series from the parquet cache for a given source string.
    Returns a pandas Series indexed by date, or None if unavailable.
    """
    path = _cache_path_for_source(source)
    if path is None:
        return None
    df = pd.read_parquet(path)
    s = df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    s.name = "raw_value"
    return s.sort_index()


def compare_raw_vs_processed(signal_id: str, source: str, n_recent: int = 36) -> pd.DataFrame:
    """
    Return a DataFrame comparing raw cache values with DB processed values for
    the most recent n_recent observations.

    Columns: as_of, raw_value, db_value, units, delta, pct_delta
    delta = db_value - raw_value  (useful for level signals; meaningless for YoY)
    """
    # DB side: last n observations
    detail = load_signal_detail(signal_id, limit=n_recent)
    detail = detail[["as_of", "value"]].rename(columns={"value": "db_value"})
    detail = detail.set_index("as_of").sort_index()

    # Raw cache side
    raw = load_raw_cache_series(source)
    if raw is None:
        detail["raw_value"] = None
        detail["delta"] = None
        detail["pct_delta"] = None
        return detail.reset_index()

    # Align on dates: for daily raw series, take month-end or closest date
    # Use a merge_asof approach: for each DB date find the closest raw date
    raw_df = raw.reset_index()
    raw_df.columns = ["raw_date", "raw_value"]

    detail_reset = detail.reset_index()
    detail_reset = detail_reset.sort_values("as_of")
    raw_df = raw_df.sort_values("raw_date")

    merged = pd.merge_asof(
        detail_reset,
        raw_df,
        left_on="as_of",
        right_on="raw_date",
        tolerance=pd.Timedelta("35 days"),
        direction="nearest",
    )
    merged["delta"] = merged["db_value"] - merged["raw_value"]
    merged["pct_delta"] = (merged["delta"] / merged["raw_value"].abs() * 100).round(3)

    return merged[["as_of", "raw_value", "db_value", "delta", "pct_delta"]].sort_values("as_of", ascending=False)


# ── Summary statistics ────────────────────────────────────────────────────────

def compute_signal_stats(signal_id: str) -> dict:
    """Return descriptive statistics for a signal."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        row = con.execute("""
            SELECT
                COUNT(*)                       AS obs_count,
                MIN(value)                     AS min_val,
                MAX(value)                     AS max_val,
                AVG(value)                     AS mean_val,
                STDDEV(value)                  AS std_val,
                MEDIAN(value)                  AS median_val,
                MIN(as_of)                     AS first_obs,
                MAX(as_of)                     AS last_obs,
                SUM(CASE WHEN is_stale THEN 1 ELSE 0 END) AS stale_count,
                SUM(CASE WHEN ABS(zscore) > 3  THEN 1 ELSE 0 END) AS outlier_count
            FROM signals
            WHERE id = ?
        """, [signal_id]).fetchone()
    finally:
        con.close()

    keys = ["obs_count", "min_val", "max_val", "mean_val", "std_val", "median_val",
            "first_obs", "last_obs", "stale_count", "outlier_count"]
    return dict(zip(keys, row)) if row else {}

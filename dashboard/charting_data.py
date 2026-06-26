"""DuckDB and FRED query helpers for the Phase 1D Dash charting view."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import yaml

from indicators.composites import normalized_nominal_weights, load_composites_config

DB_PATH = Path(os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"))
RAW_CACHE_DIR = Path(os.environ.get("RAW_CACHE_DIR", "/mnt/data/project_data/all_weather/indicators_machine/raw_cache"))
_CHART_SERIES_YAML = Path(__file__).parent.parent / "config" / "chart_series.yaml"


# ── Catalog ───────────────────────────────────────────────────────────────────

def load_catalog() -> tuple[list[dict], list[dict]]:
    """Return (series_list, yield_curve_maturities) from chart_series.yaml."""
    doc = yaml.safe_load(_CHART_SERIES_YAML.read_text()) or {}
    if not isinstance(doc, dict):
        raise ValueError("chart_series.yaml must contain a top-level mapping")
    return doc.get("series", []), doc.get("yield_curve_maturities", [])


def _load_catalog_raw() -> tuple[list[dict], list[dict]]:
    """Parse chart_series.yaml into (series_entries, maturity_entries)."""
    return load_catalog()


def load_series_catalog() -> list[dict]:
    """Return the flat list of chartable series from chart_series.yaml."""
    return load_catalog()[0]


def load_yield_curve_maturities() -> list[dict]:
    """Return the yield_curve_maturities list from chart_series.yaml."""
    return load_catalog()[1]


# ── Signal history ────────────────────────────────────────────────────────────

def load_signal_history(
    signal_id: str,
    value_col: str = "value",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Return a DataFrame with columns [as_of, value] for one signal.

    value_col: "value" for the raw observation, "zscore" for the normalised Z-score.
    """
    allowed = {"value", "zscore", "level_percentile", "change_1m", "change_3m", "change_12m"}
    if value_col not in allowed:
        raise ValueError(f"value_col must be one of {allowed}")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        clauses = ["id = ?"]
        params: list = [signal_id]
        if start_date:
            clauses.append("as_of >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("as_of <= ?")
            params.append(end_date)
        where = " AND ".join(clauses)
        df = con.execute(
            f"SELECT as_of, {value_col} AS value FROM signals WHERE {where} ORDER BY as_of",
            params,
        ).df()
    finally:
        con.close()

    df["as_of"] = pd.to_datetime(df["as_of"])
    return df.dropna(subset=["value"])


def load_multi_signal_history(
    signal_ids: list[str],
    value_col: str = "value",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Return a wide DataFrame indexed by as_of with one column per signal_id.
    Missing dates across series are left as NaN (not forward-filled).
    """
    frames: dict[str, pd.DataFrame] = {}
    for sid in signal_ids:
        df = load_signal_history(sid, value_col=value_col, start_date=start_date, end_date=end_date)
        frames[sid] = df.set_index("as_of")["value"]

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, axis=1)
    combined.index.name = "as_of"
    return combined.sort_index()


# ── Composite history ─────────────────────────────────────────────────────────

def load_composite_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: str = "US",
) -> pd.DataFrame:
    """Return point-in-time composite scores, rolling variants, and component-weight audit."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        clauses = ["country = ?"]
        params: list = [country]
        if start_date:
            clauses.append("as_of >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("as_of <= ?")
            params.append(end_date)
        where = "WHERE " + " AND ".join(clauses)
        df = con.execute(
            f"SELECT as_of, growth_score, inflation_score, quadrant, confidence, "
            f"disequilibrium_score, n_growth_signals, n_inflation_signals, n_forces, stale_signals, "
            f"growth_momentum, inflation_momentum, weight_audit, "
            f"growth_score_36m, growth_score_48m, growth_score_60m, "
            f"inflation_score_36m, inflation_score_48m, inflation_score_60m, "
            f"inflation_score_90m, inflation_score_120m, "
            f"disequilibrium_12m, disequilibrium_18m, disequilibrium_24m, "
            f"rate_score, credit_score, rate_momentum, credit_momentum "
            f"FROM composites {where} ORDER BY as_of",
            params,
        ).df()
    finally:
        con.close()

    df["as_of"] = pd.to_datetime(df["as_of"])
    return df


# ── Yield curve term structure ────────────────────────────────────────────────

def _read_fred_parquet(fred_id: str) -> Optional[pd.Series]:
    """Read a FRED series from the raw_cache parquet file, or return None."""
    path = RAW_CACHE_DIR / f"fred_{fred_id}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    # Parquet written by loader.py: index is the date, single column is the value
    if df.index.name in (None, "date", "Date") or hasattr(df.index, "freq"):
        s = df.iloc[:, 0]
    else:
        s = df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    s.name = fred_id
    return s


def _fetch_fred_live(fred_id: str) -> Optional[pd.Series]:
    """Fetch a FRED series live and cache it; returns None on failure."""
    from indicators.loader import fetch_series
    try:
        s = fetch_series(fred_id, frequency="D", force_refresh=False)
        return s
    except Exception:
        return None


def load_yield_curve_term_structure(date: str) -> pd.DataFrame:
    """
    Return a DataFrame with columns [maturity_years, label, yield_pct] for the
    given date (YYYY-MM-DD).  Maturities come from chart_series.yaml.
    Missing maturities are dropped.
    """
    maturities = load_yield_curve_maturities()
    target = pd.Timestamp(date)
    rows = []
    for m in maturities:
        fred_id = m["fred_id"]
        s = _read_fred_parquet(fred_id)
        if s is None:
            s = _fetch_fred_live(fred_id)
        if s is None or s.empty:
            continue
        # Find the closest available date on or before the target
        s_sorted = s.sort_index().dropna()
        valid = s_sorted[s_sorted.index <= target]
        if valid.empty:
            continue
        rows.append({
            "maturity_years": m["maturity_years"],
            "label": m["label"],
            "yield_pct": float(valid.iloc[-1]),
        })
    return pd.DataFrame(rows).sort_values("maturity_years")


def available_dates_for_yield_curve() -> list[str]:
    """Return sorted list of dates where the 10Y yield is available (proxy for all maturities)."""
    s = _read_fred_parquet("DGS10")
    if s is None or s.empty:
        return []
    return [d.strftime("%Y-%m-%d") for d in sorted(s.dropna().index)]


# ── Regime Composites — component status ──────────────────────────────────────

# Human-readable labels for composite constituent signal concept IDs
_COMPOSITE_SIGNAL_LABELS: dict[str, str] = {
    "growth.payrolls":          "Payrolls",
    "growth.industrial_prod":   "Industrial Production",
    "growth.retail_sales":      "Retail Sales",
    "growth.real_pce":          "Real PCE",
    "growth.capacity_util":     "Capacity Utilisation",
    "growth.job_openings":      "Job Openings (JOLTS)",
    "growth.pmi_proxy":         "PMI Proxy",
    "growth.labor_force_part":  "Labor Force Participation",
    "growth.unemployment":      "Unemployment",
    "inflation.pce_core":       "Core PCE",
    "inflation.cpi_core":       "Core CPI",
    "inflation.wages":          "Wages",
    "inflation.breakeven_5y":   "5Y Breakeven",
    "inflation.breakeven_10y":  "10Y Breakeven",
    "inflation.cpi_headline":   "CPI Headline",
    "inflation.crude_oil":      "Crude Oil",
    "inflation.ppi_broad":      "PPI Broad",
    # EZ-specific signals (added 2026-06-23)
    "inflation.ppi":            "PPI (Producer Prices)",
    "inflation.wages_lci":      "Wages & Salaries (LCI)",
    "inflation.hicp_energy":    "HICP Energy",
    "inflation.hicp_food":      "HICP Food",
}


def load_composite_component_status(
    country: str = "US",
    as_of: Optional[str] = None,
    g_zscore_col: str = "zscore",
    i_zscore_col: str = "zscore",
) -> pd.DataFrame:
    """Return the as-of signal snapshot for each regime composite component.

    Columns returned: composite, concept_id, signal_id, label, weight, invert,
    zscore, direction, change_3m, as_of, is_stale, low_history.

    g_zscore_col / i_zscore_col: which signals-table column to use as the Z-score
    for growth and inflation signals respectively (e.g. "zscore_36m", "zscore_60m").
    Defaults to "zscore" (full-history).  The returned "zscore" column always holds
    the appropriate rolling value so downstream code needs no changes.
    """
    cfg = load_composites_config(country)
    country_prefix = country.lower()

    rows_meta: list[dict] = []
    for comp_name in ("growth_score", "inflation_score", "rate_score", "credit_score"):
        force = comp_name.split("_")[0]  # "growth", "inflation", "rate", or "credit"
        indicators = cfg.get(comp_name, {}).get("indicators", [])
        if not indicators:
            continue
        nominal_weights = normalized_nominal_weights(indicators)
        for ind in indicators:
            concept_id = ind["id"]
            rows_meta.append({
                "composite":  force,
                "concept_id": concept_id,
                "signal_id":  f"{country_prefix}.{concept_id}",
                "label":      _COMPOSITE_SIGNAL_LABELS.get(concept_id, concept_id.split(".")[-1].replace("_", " ").title()),
                "weight":     float(nominal_weights[concept_id]),
                "base_share": float(ind.get("base_share", ind.get("weight", 1.0))),
                "importance": float(ind.get("importance", 1.0)),
                "quality_factor": float(ind.get("quality_factor", 1.0)),
                "invert":     bool(ind.get("invert", False)),
            })

    if not rows_meta:
        return pd.DataFrame()

    signal_ids = [r["signal_id"] for r in rows_meta]
    placeholders = ",".join("?" * len(signal_ids))

    # Build SELECT list — always include base zscore; add rolling cols if requested
    extra_cols: set[str] = set()
    if g_zscore_col != "zscore":
        extra_cols.add(g_zscore_col)
    if i_zscore_col != "zscore":
        extra_cols.add(i_zscore_col)
    extra_select = "".join(f", {col}" for col in sorted(extra_cols))

    cutoff_clause = "AND as_of <= ?" if as_of else ""
    inner_params = signal_ids + ([as_of] if as_of else [])
    outer_params = signal_ids + ([as_of] if as_of else [])
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            f"""
            SELECT id, as_of, zscore{extra_select}, direction, change_3m, is_stale, low_history
            FROM signals
            WHERE id IN ({placeholders})
              {cutoff_clause}
              AND (id, as_of) IN (
                  SELECT id, MAX(as_of) FROM signals
                  WHERE id IN ({placeholders})
                    {cutoff_clause}
                  GROUP BY id
              )
            """,
            outer_params + inner_params,
        ).df()
    finally:
        con.close()

    df["as_of"] = pd.to_datetime(df["as_of"])
    sig_map = df.set_index("id").to_dict("index")

    # Map composite → which zscore column to read (rate/credit always use base zscore)
    _zscore_col_for = {"growth": g_zscore_col, "inflation": i_zscore_col,
                       "rate": "zscore", "credit": "zscore"}

    result_rows = []
    for meta in rows_meta:
        sig = sig_map.get(meta["signal_id"], {})
        col = _zscore_col_for.get(meta["composite"], "zscore")
        # Use the rolling col if available; fall back to base zscore
        z_val = sig.get(col)
        if z_val is None or (isinstance(z_val, float) and pd.isna(z_val)):
            z_val = sig.get("zscore")
        result_rows.append({
            **meta,
            "zscore":      z_val,
            "direction":   sig.get("direction"),
            "change_3m":   sig.get("change_3m"),
            "as_of":       sig.get("as_of"),
            "is_stale":    bool(sig.get("is_stale", False)),
            "low_history": bool(sig.get("low_history", False)),
        })

    return pd.DataFrame(result_rows)


# ── Long-Term Debt Stress ─────────────────────────────────────────────────────

# Maps each component ID to the underlying signal IDs in the signals table.
# Derived components (built from raw FRED parquet) have empty lists.
_COMPONENT_SIGNAL_SUFFIXES: dict[str, list[str]] = {
    "gov_household_debt_gdp": ["credit.gov_debt_gdp", "credit.household_debt_gdp"],
    "corporate_debt_gdp": [],
    "household_debt_service": ["credit.debt_service_ratio"],
    "federal_interest_gdp": [],
    "primary_balance_gdp": ["fiscal.primary_balance_gdp"],
    "structural_balance": ["fiscal.structural_balance"],
    "govt_revenue_gdp": ["fiscal.govt_revenue_gdp"],
}

_COMPONENT_RAW_FRED_MAP: dict[str, list[str]] = {
    "corporate_debt_gdp": ["BCNSDODNS", "GDP"],
    "federal_interest_gdp": ["FYOINT", "GDP"],
}


def load_debt_stress_component_dates(
    country: str = "US",
    as_of: Optional[str] = None,
) -> dict[str, Optional[pd.Timestamp]]:
    """Return the last as_of date per debt-stress component from the signals table.

    For components that use multiple underlying signals, the *earliest* (most
    restrictive) last-date is returned. Components derived purely from raw FRED
    parquet (no signal record) return None.
    """
    prefix = country.lower()
    signal_map = {
        cid: [f"{prefix}.{suffix}" for suffix in suffixes]
        for cid, suffixes in _COMPONENT_SIGNAL_SUFFIXES.items()
    }
    all_ids = [sid for sids in signal_map.values() for sid in sids]

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        placeholders = ",".join("?" * len(all_ids))
        cutoff_clause = "AND as_of <= ?" if as_of else ""
        params = all_ids + ([as_of] if as_of else [])
        df = con.execute(
            f"SELECT id, MAX(as_of) AS last_as_of FROM signals "
            f"WHERE id IN ({placeholders}) {cutoff_clause} GROUP BY id",
            params,
        ).df()
    finally:
        con.close()

    signal_dates: dict[str, pd.Timestamp] = {}
    for _, row in df.iterrows():
        signal_dates[row["id"]] = pd.Timestamp(row["last_as_of"])

    result: dict[str, Optional[pd.Timestamp]] = {}
    cutoff = pd.Timestamp(as_of) if as_of else None
    for cid, sids in signal_map.items():
        if not sids:
            raw_dates: list[pd.Timestamp] = []
            for fred_id in _COMPONENT_RAW_FRED_MAP.get(cid, []):
                series = _read_fred_parquet(fred_id)
                if series is None or series.empty:
                    continue
                eligible = series.index[series.index <= cutoff] if cutoff is not None else series.index
                if len(eligible):
                    raw_dates.append(pd.Timestamp(eligible[-1]))
            result[cid] = min(raw_dates) if raw_dates else None
        else:
            dates = [signal_dates[sid] for sid in sids if sid in signal_dates]
            result[cid] = min(dates) if dates else None
    return result


def load_debt_stress_history(
    country: str = "US",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Return all debt_stress_snapshots for one country within the optional date window."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        clauses = ["country = ?"]
        params: list = [country]
        if start_date:
            clauses.append("as_of >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("as_of <= ?")
            params.append(end_date)
        where = " AND ".join(clauses)
        df = con.execute(
            f"SELECT * FROM debt_stress_snapshots WHERE {where} ORDER BY as_of",
            params,
        ).df()
    finally:
        con.close()

    df["as_of"] = pd.to_datetime(df["as_of"])
    return df


# ── Signal overview helpers (for Regime Map panels) ───────────────────────────

def load_latest_signals(
    country: str = "US",
    as_of: Optional[str] = None,
) -> pd.DataFrame:
    """Return each signal's most-recent observation at an optional as-of date."""
    reference_date = as_of or pd.Timestamp.today().date().isoformat()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            """
            SELECT *
            FROM signals
            WHERE country = ? AND as_of <= ?
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
            ORDER BY force, id
            """,
            [country, reference_date],
        ).df()
    finally:
        con.close()
    return df


def load_change_feed(
    country: str = "US",
    as_of: Optional[str] = None,
) -> pd.DataFrame:
    """Return recent signals ranked by change from their actual prior observation."""
    import datetime
    reference_date = pd.Timestamp(as_of).date() if as_of else datetime.date.today()
    cutoff = (reference_date - datetime.timedelta(days=120)).isoformat()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            """
            WITH ranked AS (
                SELECT id, force, lead_lag, as_of, value, zscore, direction,
                       ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) AS rn
                FROM signals
                WHERE country = ? AND as_of <= ?
            ),
            latest AS (SELECT * FROM ranked WHERE rn = 1),
            prior  AS (SELECT * FROM ranked WHERE rn = 2)
            SELECT
                l.id, l.force, l.lead_lag, l.as_of, l.value, l.zscore, l.direction,
                p.zscore  AS prior_zscore,
                p.as_of   AS prior_as_of,
                ABS(l.zscore - COALESCE(p.zscore, l.zscore)) AS zscore_delta
            FROM latest l
            LEFT JOIN prior p ON l.id = p.id
            WHERE l.lead_lag IN ('leading', 'coincident') AND l.as_of >= ?
            ORDER BY zscore_delta DESC
            """,
            [country, reference_date.isoformat(), cutoff],
        ).df()
    finally:
        con.close()
    return df


def load_composite_signal_values(country: str = "US") -> pd.DataFrame:
    """Bulk-load all historical transformed values for growth+inflation composite signals.

    Returns a DataFrame with columns: id, as_of, value, frequency.
    Used by the dashboard to recompute force Z-scores with a configurable rolling window.
    """
    cfg = load_composites_config(country)
    prefix = country.lower()
    ids: list[str] = []
    for section in ("growth_score", "inflation_score"):
        for ind in cfg.get(section, {}).get("indicators", []):
            ids.append(f"{prefix}.{ind['id']}")

    if not ids:
        return pd.DataFrame()

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        placeholders = ",".join(["?"] * len(ids))
        df = con.execute(
            f"SELECT id, as_of, value FROM signals "
            f"WHERE id IN ({placeholders}) ORDER BY id, as_of",
            ids,
        ).df()
    finally:
        con.close()

    df["as_of"] = pd.to_datetime(df["as_of"])
    return df.dropna(subset=["value"])


def load_all_signal_histories(
    country: str = "US",
    n_months: int = 36,
    as_of: Optional[str] = None,
) -> pd.DataFrame:
    """Bulk-load value history for all signals (used for sparkline generation)."""
    import datetime
    reference_date = pd.Timestamp(as_of).date() if as_of else datetime.date.today()
    cutoff = (reference_date - datetime.timedelta(days=n_months * 31)).isoformat()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            """
            SELECT id, as_of, value
            FROM signals
            WHERE country = ? AND as_of >= ? AND as_of <= ?
            ORDER BY id, as_of
            """,
            [country, cutoff, reference_date.isoformat()],
        ).df()
    finally:
        con.close()
    return df


def load_signal_units(signal_ids: list[str]) -> dict[str, str]:
    """Return {signal_id: units} for each signal in the list.  Missing IDs get 'value'."""
    if not signal_ids:
        return {}
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        placeholders = ",".join("?" * len(signal_ids))
        rows = con.execute(
            f"SELECT DISTINCT id, units FROM signals WHERE id IN ({placeholders})",
            signal_ids,
        ).fetchall()
    finally:
        con.close()
    result = {sid: "value" for sid in signal_ids}
    for sid, units in rows:
        result[sid] = units or "value"
    return result

"""DuckDB and FRED query helpers for the Phase 1D Dash charting view."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import yaml

DB_PATH = Path(os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"))
RAW_CACHE_DIR = Path(os.environ.get("RAW_CACHE_DIR", "/mnt/data/project_data/all_weather/indicators_machine/raw_cache"))
_CHART_SERIES_YAML = Path(__file__).parent.parent / "config" / "chart_series.yaml"


# ── Catalog ───────────────────────────────────────────────────────────────────

def load_catalog() -> tuple[list[dict], list[dict]]:
    """Return (series_list, yield_curve_maturities) from chart_series.yaml."""
    raw = yaml.safe_load(_CHART_SERIES_YAML.read_text())
    maturities = raw.pop("yield_curve_maturities", [])
    series = [item for item in raw.values() if isinstance(item, list)]
    # yaml.safe_load with a list-of-dicts at root returns them flattened
    # Re-load cleanly: the yaml is a list of dicts + one mapping key
    raw2 = yaml.safe_load(_CHART_SERIES_YAML.read_text())
    maturities2 = raw2.pop("yield_curve_maturities", [])
    flat = []
    for v in raw2.values():
        if isinstance(v, list):
            flat.extend(v)
    return flat, maturities2


def _load_catalog_raw() -> tuple[list[dict], list[dict]]:
    """Parse chart_series.yaml into (series_entries, maturity_entries)."""
    text = _CHART_SERIES_YAML.read_text()
    # Split at the yield_curve_maturities key — parse the whole doc as YAML
    # and separate the special key from the series list
    doc = yaml.safe_load(text)
    if isinstance(doc, list):
        # No yield_curve_maturities key in this version — shouldn't happen
        return doc, []
    if isinstance(doc, dict):
        maturities = doc.pop("yield_curve_maturities", [])
        series = list(doc.values())
        if series and isinstance(series[0], list):
            series = series[0]
        return series, maturities
    return [], []


def load_series_catalog() -> list[dict]:
    """Return the flat list of chartable series from chart_series.yaml."""
    text = _CHART_SERIES_YAML.read_text()
    # The yaml file is a list of series dicts followed by a mapping key.
    # We use a two-pass parse: collect list items then the mapping.
    import re
    # Strip the yield_curve_maturities block before parsing as a list
    clean = re.sub(r"\nyield_curve_maturities:.*", "", text, flags=re.DOTALL)
    return yaml.safe_load(clean) or []


def load_yield_curve_maturities() -> list[dict]:
    """Return the yield_curve_maturities list from chart_series.yaml."""
    text = _CHART_SERIES_YAML.read_text()
    import re
    m = re.search(r"\nyield_curve_maturities:(.*)", text, flags=re.DOTALL)
    if not m:
        return []
    block = "yield_curve_maturities:" + m.group(1)
    result = yaml.safe_load(block)
    return result.get("yield_curve_maturities", []) if result else []


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
) -> pd.DataFrame:
    """Return the composites table with columns: as_of, growth_score, inflation_score, quadrant."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        clauses = []
        params: list = []
        if start_date:
            clauses.append("as_of >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("as_of <= ?")
            params.append(end_date)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        df = con.execute(
            f"SELECT as_of, growth_score, inflation_score, quadrant, confidence, "
            f"disequilibrium_score, n_growth_signals, n_inflation_signals, n_forces "
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

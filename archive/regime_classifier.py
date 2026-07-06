"""Threshold-based macro regime classifier.

Standalone module — does not modify the composites pipeline or any existing tables.
Classifies each calendar month using hard rolling Z-score thresholds per macro
dimension, independently of the composites engine.

Five dimensions: Growth · Inflation · Rate · Credit · Volatility.
The quadrant label (Expansion / Inflationary Boom / Stagflation /
Disinflationary Slowdown) is derived from Growth × Inflation flags only,
matching the composites engine's 4-season taxonomy.

The function returns a plain DataFrame; callers decide whether to persist it.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Signal map ────────────────────────────────────────────────────────────────
# Keys per country:
#   growth / inflation / rate  → {"id": str, "invert": bool}
#   credit                     → {option_key: {"id": str|None, "invert": bool}}
#   volatility                 → {"id": str|None, "vix_fred": bool, "invert": bool}

_SIGNAL_MAP: dict[str, dict] = {
    "US": {
        "growth":    {"id": "us.master.gdp_real",           "invert": False},
        "inflation": {"id": "us.inflation.cpi_headline",    "invert": False},
        "rate":      {"id": "us.policy.real_fed_funds",     "invert": False},
        "credit": {
            "baa_spread":   {"id": "us.premium.credit_spread_corp", "invert": True},
            "gov_debt_gdp": {"id": "us.credit.gov_debt_gdp",        "invert": False},
        },
        "volatility": {"id": "VIXCLS", "vix_fred": True, "invert": False},
    },
    "EZ": {
        "growth":    {"id": "ez.master.gdp_real",           "invert": False},
        "inflation": {"id": "ez.inflation.cpi_headline",    "invert": False},
        "rate":      {"id": "ez.policy.real_yield_10y",     "invert": False},
        "credit": {
            "baa_spread":   {"id": "ez.credit.btp_bund_spread", "invert": True},
            "gov_debt_gdp": {"id": "ez.credit.gov_debt_gdp",    "invert": False},
        },
        "volatility": None,
    },
    "KR": {
        "growth":    {"id": "kr.master.gdp_real",           "invert": False},
        "inflation": {"id": "kr.inflation.cpi_headline",    "invert": False},
        "rate":      {"id": "kr.policy.yield_10y",          "invert": False},
        "credit": {
            "baa_spread":   None,
            "gov_debt_gdp": {"id": "kr.credit.gov_debt_gdp",    "invert": False},
        },
        "volatility": None,
    },
}

# Human-readable labels for credit signal dropdown options
CREDIT_SIGNAL_LABELS: dict[str, str] = {
    "baa_spread":   "BAA / Corporate Spread",
    "gov_debt_gdp": "Government Debt / GDP",
}

_DIMS = ["growth", "inflation", "rate", "credit", "volatility"]

_QUADRANT_MAP: dict[tuple[int, int], str] = {
    (1,  1): "Inflationary Boom",
    (1, -1): "Expansion",
    (-1, 1): "Stagflation",
    (-1, -1): "Disinflationary Slowdown",
}

_RAW_CACHE_DIR = Path(
    os.environ.get(
        "RAW_CACHE_DIR",
        "/mnt/data/project_data/all_weather/indicators_machine/raw_cache",
    )
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """Compute rolling Z-score independent of the pipeline's pre-computed column."""
    roll = series.rolling(window, min_periods=max(12, window // 4))
    return (series - roll.mean()) / roll.std()


def _decay_fill_z(
    z: pd.Series,
    quarterly_source: pd.Series,
    halflife_months: float,
) -> pd.Series:
    """Decay Z-scores toward 0 between quarterly observations.

    Where quarterly_source has no observation for a given month, the Z-score
    from the previous observation month is multiplied by decay^k (k = months
    since last obs). This represents diminishing confidence as the GDP release
    ages.
    """
    decay = float(np.exp(-np.log(2) / halflife_months))
    result = z.copy().astype(float)
    months_since = 0
    for idx in z.index:
        if pd.notna(quarterly_source.get(idx)):
            months_since = 0
        else:
            months_since += 1
        if months_since > 0 and not np.isnan(result.get(idx, np.nan)):
            result[idx] = result[idx] * (decay ** months_since)
    return result


def _load_signal_from_db(conn, signal_id: str) -> pd.Series:
    """Pull raw value series from signals table."""
    df = conn.execute(
        "SELECT as_of, value FROM signals WHERE id = ? AND value IS NOT NULL ORDER BY as_of",
        [signal_id],
    ).df()
    if df.empty:
        return pd.Series(dtype=float)
    df["as_of"] = pd.to_datetime(df["as_of"])
    return df.set_index("as_of")["value"]


def _load_vix(freq: str = "monthly") -> Optional[pd.Series]:
    """Load VIXCLS from raw cache or FRED API, resampled to month-start."""
    cache = _RAW_CACHE_DIR / "fred_VIXCLS.parquet"
    if cache.exists():
        try:
            df = pd.read_parquet(cache)
            s = df["value"] if "value" in df.columns else df.iloc[:, 0]
            s.index = pd.to_datetime(s.index)
            return s.resample("MS").mean().dropna()
        except Exception as exc:
            logger.warning("VIX cache read failed: %s", exc)

    try:
        from indicators.loader import fetch_series
        raw = fetch_series("VIXCLS", "daily")
        if raw is not None and not raw.empty:
            return raw.resample("MS").mean().dropna()
    except Exception as exc:
        logger.warning("VIX FRED fetch failed: %s", exc)
    return None


def _to_quadrant(g_flag: float, i_flag: float) -> str:
    if pd.isna(g_flag) or pd.isna(i_flag):
        return "Insufficient Data"
    if g_flag == 0 or i_flag == 0:
        return "Transitional"
    gi = 1 if g_flag > 0 else -1
    ii = 1 if i_flag > 0 else -1
    return _QUADRANT_MAP.get((gi, ii), "Unknown")


# ── Main function ─────────────────────────────────────────────────────────────

def classify_regimes_threshold(
    country: str,
    conn,
    lookback_years: int = 10,
    upper_threshold: float = 0.5,
    lower_threshold: float = -0.5,
    quarterly_fill: Literal["ffill", "decay"] = "ffill",
    decay_halflife: float = 2.0,
    credit_signal: str = "baa_spread",
    signal_overrides: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """Classify each month into a macro regime using hard Z-score thresholds.

    Parameters
    ----------
    country         : Two-letter code (US / EZ / KR …).
    conn            : DuckDB connection (read-only is fine).
    lookback_years  : Rolling window length in years (e.g. 10 → 120-month window).
    upper_threshold : Z-score above which flag = +1 (default 0.5).
    lower_threshold : Z-score below which flag = -1 (default -0.5).
    quarterly_fill  : How to fill months between quarterly GDP releases.
                      "ffill"  — plain forward-fill (hold last obs, max 3 months).
                      "decay"  — forward-fill then decay Z-score toward 0 with
                                 half-life = decay_halflife months.
    decay_halflife  : Half-life in months for decay fill (default 2).
    credit_signal   : Which credit proxy to use: "baa_spread" or "gov_debt_gdp".
    signal_overrides: Optional dict mapping dim → signal_id to override defaults.

    Returns
    -------
    DataFrame with columns:
        as_of, country, lookback_years,
        growth_z, inflation_z, rate_z, credit_z, volatility_z,
        growth_flag, inflation_flag, rate_flag, credit_flag, volatility_flag,
        regime_vector, quadrant_label
    """
    country = country.upper()
    window  = lookback_years * 12
    cfg     = _SIGNAL_MAP.get(country, {})

    if not cfg:
        raise ValueError(f"No signal map defined for country '{country}'. "
                         f"Available: {list(_SIGNAL_MAP)}")

    # ── Resolve signal IDs ────────────────────────────────────────────────────
    def _resolve(dim: str) -> Optional[dict]:
        if signal_overrides and dim in signal_overrides:
            return {"id": signal_overrides[dim], "invert": False}
        if dim == "credit":
            opts = cfg.get("credit", {})
            return opts.get(credit_signal) if isinstance(opts, dict) else None
        return cfg.get(dim)

    # ── Load raw series ───────────────────────────────────────────────────────
    raw: dict[str, pd.Series] = {}
    meta_invert: dict[str, bool] = {}

    for dim in _DIMS:
        if dim == "volatility":
            continue
        info = _resolve(dim)
        if not info or not info.get("id"):
            logger.info("classify_regimes[%s]: no signal configured for %s", country, dim)
            continue
        s = _load_signal_from_db(conn, info["id"])
        if s.empty:
            logger.warning("classify_regimes[%s]: empty DB result for %s (%s)",
                           country, dim, info["id"])
            continue
        raw[dim] = s
        meta_invert[dim] = bool(info.get("invert", False))

    # Volatility — VIX for US, skip otherwise
    vix_info = cfg.get("volatility")
    if vix_info and vix_info.get("vix_fred"):
        vix = _load_vix()
        if vix is not None and not vix.empty:
            raw["volatility"] = vix
            meta_invert["volatility"] = False

    if not raw:
        raise ValueError(f"No signal data found for country {country}. "
                         "Ensure the pipeline has been run at least once.")

    # ── Build unified monthly date index ─────────────────────────────────────
    all_dates = pd.date_range(
        start=min(s.index.min() for s in raw.values()),
        end=max(s.index.max() for s in raw.values()),
        freq="MS",
    )

    # ── Resample + fill + rolling Z-score ────────────────────────────────────
    zscores:  dict[str, pd.Series] = {}
    raw_quarterly: dict[str, pd.Series] = {}  # sparse (for decay reference)

    for dim, s in raw.items():
        monthly = s.resample("MS").last().reindex(all_dates)

        if dim == "growth":
            raw_quarterly["growth"] = monthly.copy()
            monthly = monthly.ffill(limit=3)
        else:
            monthly = monthly.ffill(limit=3)

        z = _rolling_zscore(monthly, window)

        if dim == "growth" and quarterly_fill == "decay":
            z = _decay_fill_z(z, raw_quarterly["growth"], decay_halflife)

        if meta_invert.get(dim, False):
            z = -z

        zscores[dim] = z

    # ── Apply threshold flags ─────────────────────────────────────────────────
    flags: dict[str, pd.Series] = {}
    for dim in _DIMS:
        if dim not in zscores:
            flags[dim] = pd.Series(np.nan, index=all_dates, dtype=float)
            continue
        z = zscores[dim].reindex(all_dates)
        f = pd.Series(0.0, index=all_dates)
        f[z >  upper_threshold] =  1.0
        f[z <  lower_threshold] = -1.0
        f[z.isna()]             = np.nan
        flags[dim] = f

    # ── Build output DataFrame ────────────────────────────────────────────────
    out = pd.DataFrame(index=all_dates)
    out.index.name = "as_of"

    for dim in _DIMS:
        z_s = zscores.get(dim, pd.Series(np.nan, index=all_dates)).reindex(all_dates)
        out[f"{dim}_z"]    = z_s.round(4)
        out[f"{dim}_flag"] = flags[dim]

    # Regime vector string: e.g. "+1/-1/+1/0/?"
    def _fmt(v) -> str:
        if pd.isna(v):   return "?"
        if v == 0:       return "0"
        return f"{int(v):+d}"

    out["regime_vector"] = out.apply(
        lambda r: "/".join(_fmt(r[f"{d}_flag"]) for d in _DIMS), axis=1
    )

    out["quadrant_label"] = out.apply(
        lambda r: _to_quadrant(r["growth_flag"], r["inflation_flag"]), axis=1
    )

    out["country"]       = country
    out["lookback_years"] = lookback_years

    # Trim leading rows where no Z-score could be computed (< window months of data)
    first_valid = out[["growth_z", "inflation_z"]].dropna(how="all").index
    if len(first_valid):
        out = out.loc[first_valid[0]:]

    return out.reset_index()

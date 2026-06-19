"""
Long-Term Debt Stress Indicator computation.

Entry point: compute_debt_stress_history(conn, country, config, data_dir)
             → list[DebtStressSnapshot], ready for store.upsert_debt_stress().

All tunable parameters (weights, windows, coverage threshold, bands) live in
config/longterm_stress.yaml. Change them there; do not hardcode values here.

Design choices and their TUNABLE parameters are annotated inline.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "config"


# ── Config loading ────────────────────────────────────────────────────────────

def load_longterm_stress_config(path: Path | None = None) -> dict:
    p = path or (_CONFIG_DIR / "longterm_stress.yaml")
    with open(p) as f:
        return yaml.safe_load(f)


def stress_band_label(score: float, bands: dict) -> str:
    """Map a stress score to its descriptive band label (for display only).

    ⚠ Bands are NOT validated risk thresholds — see config bands section.
    TUNABLE: thresholds are in config/longterm_stress.yaml bands.*
    """
    if score < bands["below_normal_upper"]:
        return "Below-normal stress"
    if score < bands["elevated_lower"]:
        return "Near historical norm"
    if score < bands["high_lower"]:
        return "Elevated stress"
    return "High relative stress"


# ── Raw data loading ──────────────────────────────────────────────────────────

def _load_raw_fred(series_id: str, data_dir: Path) -> pd.Series:
    """Load a FRED series from the parquet raw cache. Returns a DatetimeIndex series."""
    path = data_dir / "raw_cache" / f"fred_{series_id}.parquet"
    df = pd.read_parquet(path)
    # Parquet files store a single column named after the series or "value"
    col = series_id if series_id in df.columns else df.columns[0]
    s = df[col].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_signal_values(conn, signal_id: str) -> pd.Series:
    """Load the `value` column for a signal from DuckDB. Returns a DatetimeIndex series."""
    df = conn.execute(
        "SELECT as_of, value FROM signals WHERE id = ? AND value IS NOT NULL ORDER BY as_of",
        [signal_id],
    ).df()
    if df.empty:
        return pd.Series(dtype=float)
    df["as_of"] = pd.to_datetime(df["as_of"])
    return df.set_index("as_of")["value"].sort_index()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extend_to_current_quarter(s: pd.Series, limit: int) -> pd.Series:
    """Extend a quarterly series to the current quarter-end, then forward-fill.

    resample().last() stops at the last data point — it does NOT add future dates
    as NaN rows, so a plain ffill() on the resampled series cannot reach the
    current quarter. This helper extends the index explicitly before filling.

    TUNABLE: `limit` (passed from config ffill_limit_quarterly) controls how far
    a stale observation is carried forward. Too large → stale data silently ages;
    too small → the indicator produces NaN unnecessarily.
    """
    if s.empty:
        return s
    current_qe = pd.Timestamp.today().to_period("Q").to_timestamp("Q")
    if s.index[-1] >= current_qe:
        return s
    extended_idx = pd.date_range(s.index[0], current_qe, freq="QE")
    return s.reindex(extended_idx).ffill(limit=limit).dropna()


# ── Derived ratio construction ────────────────────────────────────────────────

def _build_gov_household_debt_gdp(conn, country_prefix: str) -> pd.Series:
    """Sum government debt/GDP and household debt/GDP at quarterly frequency.

    Forward-fills each component up to 6 quarters (≈ 18 months) before summing.
    This matches the typical BIS household-debt publication lag (~3–4 quarters)
    while still using the latest available data rather than producing NaN.
    The caller should check _component_last_dates to flag which components are stale.
    """
    gov = _load_signal_values(conn, f"{country_prefix}.credit.gov_debt_gdp")
    hh = _load_signal_values(conn, f"{country_prefix}.credit.household_debt_gdp")
    if gov.empty and hh.empty:
        return pd.Series(dtype=float)
    # Extend each sub-series to the current quarter before merging, so the
    # combined series covers the current quarter even when one sub-series lags.
    gov = _extend_to_current_quarter(gov.resample("QE").last(), limit=6)
    hh  = _extend_to_current_quarter(hh.resample("QE").last(),  limit=6)
    idx = gov.index.union(hh.index)
    gov_q = gov.reindex(idx).ffill(limit=6)
    hh_q  = hh.reindex(idx).ffill(limit=6)
    combined = gov_q.add(hh_q).dropna()
    return combined.resample("QE").last().dropna()


def _build_corporate_debt_gdp(data_dir: Path) -> pd.Series:
    """Construct corporate debt / GDP from raw FRED level series at quarterly frequency.

    BCNSDODNS: Nonfinancial corporate debt, billions $, quarterly.
    GDP: Nominal GDP, billions $ at annualised rate, quarterly.
    Both are quarterly so no frequency conversion is needed.
    """
    corp = _load_raw_fred("BCNSDODNS", data_dir).resample("QE").last().dropna()
    gdp = _load_raw_fred("GDP", data_dir).resample("QE").last().dropna()
    ratio = corp.divide(gdp).dropna()
    return ratio


def _build_federal_interest_gdp(data_dir: Path) -> pd.Series:
    """Construct federal interest outlays / GDP ratio.

    FYOINT: Federal interest outlays, millions $, annual (US fiscal year Oct–Sept).
    GDP: Nominal GDP, billions $, quarterly (annualised rate).

    Unit conversion: FYOINT millions → billions (÷ 1000).
    Frequency alignment: forward-fill the annual FYOINT to quarterly grid before dividing.
    Z-score is computed AFTER this function returns, at annual frequency — see
    _rolling_z_annual_then_ffill().

    TUNABLE: the forward-fill aligns the fiscal-year total against the quarterly annualised
    GDP rate. This is a ratio of annual-period spending to an annual-rate denominator, so
    the units are compatible. If the fiscal year ends in September, the September quarter
    GDP is the natural matching denominator; forward-fill carries it through subsequent
    quarters until the next fiscal year.
    """
    fyoint = _load_raw_fred("FYOINT", data_dir)
    gdp = _load_raw_fred("GDP", data_dir).resample("QE").last().dropna()

    # Convert millions → billions
    fyoint_bn = fyoint / 1000.0

    # Resample to annual (last observation per calendar year), then forward-fill quarterly
    fyoint_annual = fyoint_bn.resample("YE").last().dropna()
    fyoint_q = fyoint_annual.reindex(gdp.index, method="ffill")

    ratio = fyoint_q.divide(gdp).dropna()
    return ratio


# ── Z-score computation ───────────────────────────────────────────────────────

def _rolling_z_quarterly(
    series: pd.Series,
    window: int,
    min_periods: int,
    shift: int = 1,
) -> pd.Series:
    """Rolling Z-score for a quarterly series with look-ahead protection.

    TUNABLE: window and min_periods come from config z_score.window_quarters /
             min_periods_quarters. shift comes from config z_score.look_back_shift
             and MUST remain ≥ 1 to prevent look-ahead bias.

    The shift(1) ensures that for period t, the rolling mean/std are computed
    from data up to and including t-1 only.
    """
    s = series.resample("QE").last().dropna()
    prior = s.shift(shift)
    mu = prior.rolling(window, min_periods=min_periods).mean()
    sigma = prior.rolling(window, min_periods=min_periods).std()
    return ((s - mu) / sigma).replace([np.inf, -np.inf], np.nan)


def _rolling_z_annual_then_ffill(
    series: pd.Series,
    window: int,
    min_periods: int,
    shift: int = 1,
    quarterly_index: pd.DatetimeIndex | None = None,
) -> pd.Series:
    """Rolling Z-score for an annual series, computed at annual frequency, then forward-filled.

    TUNABLE: window and min_periods come from config z_score.window_annual /
             min_periods_annual. shift comes from config z_score.look_back_shift.

    Carrying forward a single annual Z-score for 4 quarters avoids the look-ahead
    and multiple-counting problem that would arise from Z-scoring the quarterly
    forward-filled series directly.
    """
    annual = series.resample("YE").last().dropna()
    prior = annual.shift(shift)
    mu = prior.rolling(window, min_periods=min_periods).mean()
    sigma = prior.rolling(window, min_periods=min_periods).std()
    z_annual = ((annual - mu) / sigma).replace([np.inf, -np.inf], np.nan).dropna()

    if quarterly_index is None:
        return z_annual

    # Forward-fill the annual Z-score into the quarterly grid
    z_q = z_annual.reindex(quarterly_index, method="ffill")
    return z_q


# ── Main computation ──────────────────────────────────────────────────────────

def compute_debt_stress_history(
    conn,
    country: str,
    config: dict,
    data_dir: Path,
) -> list:
    """Compute the Long-Term Debt Stress Indicator for all available quarters.

    Returns list[DebtStressSnapshot] ready for store.upsert_debt_stress().

    Component Z-scores and raw values are stored alongside the aggregate score
    so the decomposition is auditable without re-running the computation.
    """
    from indicators.models import DebtStressSnapshot

    country_prefix = country.lower()
    z_cfg = config.get("z_score", {})
    cov_cfg = config.get("coverage", {})
    components_cfg = config.get("components", [])

    win_q = z_cfg.get("window_quarters", 40)
    min_q = z_cfg.get("min_periods_quarters", 20)
    win_a = z_cfg.get("window_annual", 10)
    min_a = z_cfg.get("min_periods_annual", 5)
    shift = z_cfg.get("look_back_shift", 1)
    min_weight = cov_cfg.get("min_retained_weight", 0.60)

    comp_map = {c["id"]: c for c in components_cfg}

    # ── Build raw level series for each component ─────────────────────────────

    raw_series: dict[str, pd.Series] = {}
    # Last observed date per component — used to flag stale carry-forward
    last_obs_dates: dict[str, Optional[pd.Timestamp]] = {}

    def _record_last(cid: str, s: pd.Series) -> None:
        last_obs_dates[cid] = s.index[-1] if not s.empty else None

    # Quarterly derived
    try:
        # Capture sub-component last dates before the merge so staleness is visible
        gov_raw = _load_signal_values(conn, f"{country_prefix}.credit.gov_debt_gdp")
        hh_raw  = _load_signal_values(conn, f"{country_prefix}.credit.household_debt_gdp")
        # Use the earlier of the two sub-components as the "last obs" for the combined series
        gov_last = gov_raw.index[-1] if not gov_raw.empty else None
        hh_last  = hh_raw.index[-1]  if not hh_raw.empty  else None
        if gov_last and hh_last:
            last_obs_dates["gov_household_debt_gdp"] = min(gov_last, hh_last)
        else:
            last_obs_dates["gov_household_debt_gdp"] = gov_last or hh_last
        raw_series["gov_household_debt_gdp"] = _build_gov_household_debt_gdp(conn, country_prefix)
    except Exception as exc:
        logger.warning("gov_household_debt_gdp: %s", exc)
        raw_series["gov_household_debt_gdp"] = pd.Series(dtype=float)
        last_obs_dates["gov_household_debt_gdp"] = None

    try:
        s = _build_corporate_debt_gdp(data_dir)
        raw_series["corporate_debt_gdp"] = s
        _record_last("corporate_debt_gdp", s)
    except Exception as exc:
        logger.warning("corporate_debt_gdp: %s", exc)
        raw_series["corporate_debt_gdp"] = pd.Series(dtype=float)
        last_obs_dates["corporate_debt_gdp"] = None

    # Quarterly signal — forward-fill up to 4 quarters to bridge publication lag
    try:
        s = _load_signal_values(conn, f"{country_prefix}.credit.debt_service_ratio")
        _record_last("household_debt_service", s)
        raw_series["household_debt_service"] = _extend_to_current_quarter(
            s.resample("QE").last(), limit=4
        )
    except Exception as exc:
        logger.warning("household_debt_service: %s", exc)
        raw_series["household_debt_service"] = pd.Series(dtype=float)
        last_obs_dates["household_debt_service"] = None

    # Annual derived (forward-fill to quarterly handled in Z step)
    try:
        s = _build_federal_interest_gdp(data_dir)
        raw_series["federal_interest_gdp"] = s
        _record_last("federal_interest_gdp", s)
    except Exception as exc:
        logger.warning("federal_interest_gdp: %s", exc)
        raw_series["federal_interest_gdp"] = pd.Series(dtype=float)
        last_obs_dates["federal_interest_gdp"] = None

    # Annual signals
    signal_id_map = {
        "primary_balance_gdp": f"{country_prefix}.fiscal.primary_balance_gdp",
        "structural_balance":  f"{country_prefix}.fiscal.structural_balance",
        "govt_revenue_gdp":    f"{country_prefix}.fiscal.govt_revenue_gdp",
    }
    for cid in ("primary_balance_gdp", "structural_balance", "govt_revenue_gdp"):
        try:
            s = _load_signal_values(conn, signal_id_map[cid])
            raw_series[cid] = s
            _record_last(cid, s)
        except Exception as exc:
            logger.warning("%s: %s", cid, exc)
            raw_series[cid] = pd.Series(dtype=float)
            last_obs_dates[cid] = None

    # ── Build the common quarterly index from available quarterly series ───────
    quarterly_ids = [
        cid for cid, cfg in comp_map.items()
        if cfg.get("frequency", "Q") == "Q" and not raw_series.get(cid, pd.Series()).empty
    ]
    if not quarterly_ids:
        logger.warning("No quarterly component data found for country=%s", country)
        return []

    q_index = raw_series[quarterly_ids[0]].index
    for cid in quarterly_ids[1:]:
        q_index = q_index.union(raw_series[cid].index)
    q_index = pd.DatetimeIndex(sorted(q_index)).to_period("Q").to_timestamp("Q")

    # ── Compute Z-scores ──────────────────────────────────────────────────────

    z_series: dict[str, pd.Series] = {}

    for comp in components_cfg:
        cid = comp["id"]
        freq = comp.get("frequency", "Q")
        raw = raw_series.get(cid, pd.Series(dtype=float))
        if raw.empty:
            z_series[cid] = pd.Series(dtype=float)
            continue

        if freq == "Q":
            z_series[cid] = _rolling_z_quarterly(raw, win_q, min_q, shift)
        else:
            # Annual: Z-score on annual series, then ffill to quarterly grid
            z_series[cid] = _rolling_z_annual_then_ffill(
                raw, win_a, min_a, shift, quarterly_index=q_index
            )

    # ── Assemble per-quarter snapshots ────────────────────────────────────────

    snapshots: list[DebtStressSnapshot] = []

    for qt in q_index:
        if qt.date() > date.today():
            continue

        component_z: dict[str, Optional[float]] = {}
        component_val: dict[str, Optional[float]] = {}

        for comp in components_cfg:
            cid = comp["id"]
            z_s = z_series.get(cid, pd.Series(dtype=float))
            raw_s = raw_series.get(cid, pd.Series(dtype=float))

            z_val = None
            if not z_s.empty and qt in z_s.index:
                v = z_s[qt]
                z_val = float(v) if pd.notna(v) else None

            raw_val = None
            if not raw_s.empty:
                # For the raw value: use the most recent observation at or before qt
                raw_idx = raw_s.index[raw_s.index <= qt]
                if len(raw_idx) > 0:
                    v = raw_s[raw_idx[-1]]
                    raw_val = float(v) if pd.notna(v) else None

            component_z[cid] = z_val
            component_val[cid] = raw_val

        # Coverage check and weight renormalisation
        total_config_weight = sum(c["weight"] for c in components_cfg)
        active_weight = sum(
            c["weight"] for c in components_cfg
            if component_z.get(c["id"]) is not None
        )
        n_active = sum(1 for c in components_cfg if component_z.get(c["id"]) is not None)
        retained = active_weight / total_config_weight if total_config_weight > 0 else 0.0
        low_cov = retained < min_weight

        # Aggregate stress score (renormalise active weights to 1.0)
        stress = None
        if not low_cov and active_weight > 0:
            weighted_sum = 0.0
            for comp in components_cfg:
                cid = comp["id"]
                z_val = component_z.get(cid)
                if z_val is None:
                    continue
                direction = comp.get("stress_direction", "positive")
                signed_z = -z_val if direction == "negative" else z_val
                # Renormalise: each active component's effective weight = config_weight / active_weight
                weighted_sum += signed_z * (comp["weight"] / active_weight)
            stress = round(weighted_sum, 4)

        # Detect which active components are carrying forward stale data
        stale_comps: list[str] = []
        qt_period_start = qt - pd.offsets.QuarterBegin(startingMonth=1)
        for comp in components_cfg:
            cid = comp["id"]
            if component_z.get(cid) is None:
                continue  # already excluded from active set
            last = last_obs_dates.get(cid)
            if last is not None and last < qt_period_start:
                stale_comps.append(cid)

        snapshots.append(DebtStressSnapshot(
            country=country,
            as_of=qt.date(),
            stress_score=stress,
            n_components=n_active,
            retained_weight=round(retained, 4),
            low_coverage=low_cov,
            stale_components=stale_comps,
            z_gov_household_debt_gdp=_r(component_z.get("gov_household_debt_gdp")),
            z_corporate_debt_gdp=_r(component_z.get("corporate_debt_gdp")),
            z_household_debt_service=_r(component_z.get("household_debt_service")),
            z_federal_interest_gdp=_r(component_z.get("federal_interest_gdp")),
            z_primary_balance_gdp=_r(component_z.get("primary_balance_gdp")),
            z_structural_balance=_r(component_z.get("structural_balance")),
            z_govt_revenue_gdp=_r(component_z.get("govt_revenue_gdp")),
            val_gov_household_debt_gdp=_r(component_val.get("gov_household_debt_gdp")),
            val_corporate_debt_gdp=_r(component_val.get("corporate_debt_gdp")),
            val_household_debt_service=_r(component_val.get("household_debt_service")),
            val_federal_interest_gdp=_r(component_val.get("federal_interest_gdp")),
            val_primary_balance_gdp=_r(component_val.get("primary_balance_gdp")),
            val_structural_balance=_r(component_val.get("structural_balance")),
            val_govt_revenue_gdp=_r(component_val.get("govt_revenue_gdp")),
        ))

    return snapshots


def _r(v: Optional[float], digits: int = 4) -> Optional[float]:
    return round(v, digits) if v is not None else None

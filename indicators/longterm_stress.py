"""
Long-Term Debt Stress Indicator computation.

Entry point: compute_debt_stress_history(conn, country, config, data_dir)
             → list[DebtStressSnapshot], ready for store.upsert_debt_stress().

All tunable parameters (weights, windows, coverage threshold, bands, staleness
decay) live in config/longterm_stress.yaml. Change them there; do not hardcode
values here.

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

# Expected publication lag per native frequency (in quarters).
# A component is NOT considered stale until it exceeds this lag.
# TUNABLE: these reflect standard provider release schedules.
_EXPECTED_LAG_BY_FREQ: dict[str, int] = {
    "Q": 1,   # quarterly series — one quarter publication lag is normal
    "A": 4,   # annual series — up to four quarters (one year) is normal
}


# ── Config loading ────────────────────────────────────────────────────────────

def load_longterm_stress_config(path: Path | None = None) -> dict:
    p = path or (_CONFIG_DIR / "longterm_stress.yaml")
    with open(p) as f:
        config = yaml.safe_load(f) or {}
    _validate_config(config)
    return config


def _validate_config(config: dict) -> None:
    """Fail fast when a model configuration would produce invalid output."""
    if not config.get("country"):
        raise ValueError("long-term stress config must declare its country")
    components = config.get("components", [])
    if not components:
        raise ValueError("long-term stress config must define components")

    ids = [component.get("id") for component in components]
    if any(not cid for cid in ids) or len(ids) != len(set(ids)):
        raise ValueError("component IDs must be present and unique")

    weights = [float(component.get("weight", 0)) for component in components]
    if any(weight <= 0 for weight in weights) or not np.isclose(sum(weights), 1.0):
        raise ValueError("component weights must be positive and sum to 1.0")

    shift = int(config.get("z_score", {}).get("look_back_shift", 1))
    if shift < 1:
        raise ValueError("z_score.look_back_shift must be at least 1")

    coverage = float(config.get("coverage", {}).get("min_retained_weight", 0.60))
    if not 0 < coverage <= 1:
        raise ValueError("coverage.min_retained_weight must be in (0, 1]")

    stale = config.get("staleness", {})
    expected_lags = stale.get("expected_lag_quarters", {})
    if any(int(expected_lags.get(freq, -1)) < 0 for freq in ("Q", "A")):
        raise ValueError("staleness.expected_lag_quarters must define non-negative Q and A values")
    if int(stale.get("max_carry_quarters", 0)) < 0:
        raise ValueError("staleness.max_carry_quarters cannot be negative")
    half_life = stale.get("stale_weight_halflife")
    if half_life is not None and float(half_life) <= 0:
        raise ValueError("staleness.stale_weight_halflife must be positive")
    min_fraction = float(stale.get("stale_min_weight_fraction", 0))
    if not 0 <= min_fraction <= 1:
        raise ValueError("staleness.stale_min_weight_fraction must be in [0, 1]")
    method = stale.get("extrapolation", {}).get("method", "rolling_mean")
    if method not in {"rolling_mean", "linear_trend"}:
        raise ValueError("unsupported staleness extrapolation method")

    bands = config.get("bands", {})
    thresholds = [
        bands.get("below_normal_upper"),
        bands.get("elevated_lower"),
        bands.get("high_lower"),
    ]
    if (
        any(value is None for value in thresholds)
        or not thresholds[0] < thresholds[1] < thresholds[2]
    ):
        raise ValueError("stress band thresholds must be present and increasing")


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


def build_debt_stress_formula_catalog(config: dict | None = None) -> list[dict]:
    """Return formula cards for the Debt Stress indicator, analogous to composites.build_formula_catalog().

    Parameter values are read live from the active config so the formula page
    stays in sync with longterm_stress.yaml without manual maintenance.
    """
    cfg = config or load_longterm_stress_config()
    z_cfg   = cfg.get("z_score", {})
    cov_cfg = cfg.get("coverage", {})
    stale   = cfg.get("staleness", {})
    bands   = cfg.get("bands", {})

    win_q  = int(z_cfg.get("window_quarters",     40))
    min_q  = int(z_cfg.get("min_periods_quarters", 20))
    win_a  = int(z_cfg.get("window_annual",        10))
    shift  = int(z_cfg.get("look_back_shift",       1))

    min_wt  = float(cov_cfg.get("min_retained_weight", 0.60))

    exp_lag = stale.get("expected_lag_quarters", {"Q": 1, "A": 4})
    hl      = stale.get("stale_weight_halflife",  4)
    min_frac = float(stale.get("stale_min_weight_fraction", 0.20))
    max_carry = int(stale.get("max_carry_quarters", 4))

    components = cfg.get("components", [])
    comp_rows  = [
        f"{c['label']}  w={c['weight']:.2f}, dir={c.get('stress_direction','positive')}"
        for c in components
    ]

    b_low  = float(bands.get("below_normal_upper", -0.5))
    b_norm = float(bands.get("elevated_lower",      0.5))
    b_high = float(bands.get("high_lower",          1.0))

    return [
        {
            "group": "Debt Stress",
            "title": "Rolling Z-score (quarterly components)",
            "equation": (
                r"Z_t = \frac{x_t - \mu_{t-1}^{W}}{\sigma_{t-1}^{W}}"
                r"\qquad W=" + str(win_q) + r"\text{ quarters}"
            ),
            "description": (
                f"Each quarterly component is Z-scored within a rolling {win_q}-quarter window.  "
                f"The window is shifted {shift} period(s) before computing μ and σ — "
                "any data from the scored period is excluded, preventing look-ahead bias.  "
                f"Minimum {min_q} non-null observations required before a Z-score is emitted."
            ),
            "parameters": [
                f"W (quarters) = {win_q}",
                f"min_periods  = {min_q}",
                f"look_back_shift = {shift}",
            ],
            "source": "indicators/longterm_stress.py::_rolling_z_quarterly",
        },
        {
            "group": "Debt Stress",
            "title": "Rolling Z-score (annual components → quarterly)",
            "equation": (
                r"Z_t^{A} = \frac{x_t^{A} - \mu_{t-1}^{W_A}}{\sigma_{t-1}^{W_A}}"
                r"\quad\xrightarrow{\text{ffill}}\quad Z_t^{Q}"
                r"\qquad W_A=" + str(win_a) + r"\text{ yr}"
            ),
            "description": (
                f"Annual components are Z-scored at annual frequency over a {win_a}-year rolling window "
                f"(shift={shift} for look-ahead protection), then the resulting annual Z-score is "
                f"forward-filled into the quarterly grid for up to {max_carry} quarters.  "
                "Z-scoring the raw annual series avoids artificially inflating the sample size "
                "that would result from Z-scoring after forward-filling."
            ),
            "parameters": [
                f"W_A (years) = {win_a}",
                f"max forward-fill quarters = {max_carry}",
            ],
            "source": "indicators/longterm_stress.py::_rolling_z_annual_then_ffill",
        },
        {
            "group": "Debt Stress",
            "title": "Staleness weight decay",
            "equation": (
                r"w_i^{eff} = w_i \cdot 0.5^{\,k_{excess}/h}"
                r"\qquad h=" + str(hl) + r"\text{ qtrs}"
            ),
            "description": (
                f"A component that has not updated within its expected publication lag "
                f"(Q: {exp_lag.get('Q', 1)} qtr, A: {exp_lag.get('A', 4)} qtrs) begins to lose weight.  "
                f"Effective weight halves every {hl} excess quarters.  "
                f"If effective weight falls below {min_frac:.0%} of its configured weight, "
                "the component is dropped from the score entirely.  "
                f"Components carried beyond {max_carry} quarters are also dropped (Gap 2)."
            ),
            "parameters": [
                f"h (half-life) = {hl} quarters",
                f"min_weight_fraction = {min_frac:.0%}",
                f"max_carry_quarters = {max_carry}",
            ],
            "source": "indicators/longterm_stress.py::staleness_weight_fraction",
        },
        {
            "group": "Debt Stress",
            "title": "Aggregate stress score",
            "equation": (
                r"S = \frac{\sum_i s_i\, Z_i\, w_i^{eff}}{\sum_i w_i^{eff}}"
                r"\quad\text{if } \frac{\sum w^{eff}}{\sum w} \geq "
                + f"{min_wt:.0%}"
            ),
            "description": (
                f"Signed, effective-weight-normalised sum of component Z-scores.  "
                "s_i = +1 for components where a higher value signals more stress "
                "(debt ratios, interest burden); s_i = −1 for components where a "
                "higher value signals less stress (fiscal surplus, revenue capacity).  "
                f"The score is null if retained weight falls below {min_wt:.0%} of "
                "the full basket, indicating insufficient data coverage."
            ),
            "parameters": [
                f"min_retained_weight = {min_wt:.0%}",
                "components: " + "; ".join(comp_rows),
            ],
            "source": "indicators/longterm_stress.py::compute_debt_stress_history",
        },
        {
            "group": "Debt Stress",
            "title": "Stress band labels",
            "equation": (
                r"S < " + f"{b_low:+g}" + r"\Rightarrow\text{Below-normal}"
                r"\quad " + f"{b_low:+g}" + r"\leq S < " + f"{b_norm:+g}"
                + r"\Rightarrow\text{Near norm}"
                r"\quad " + f"{b_norm:+g}" + r"\leq S < " + f"{b_high:+g}"
                + r"\Rightarrow\text{Elevated}"
                r"\quad S\geq " + f"{b_high:+g}" + r"\Rightarrow\text{High}"
            ),
            "description": (
                "Exploratory display bands only — NOT validated risk thresholds.  "
                "Thresholds should be calibrated against historical episodes "
                "(1994 bond rout, 2008 GFC, 2022 tightening) before operational use."
            ),
            "parameters": [
                f"below_normal_upper = {b_low:+g}",
                f"elevated_lower = {b_norm:+g}",
                f"high_lower = {b_high:+g}",
            ],
            "source": "indicators/longterm_stress.py::stress_band_label",
        },
    ]


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

    TUNABLE: `limit` (from config staleness.max_carry_quarters) controls how far
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


def _staleness_lag_q(
    last_obs: Optional[pd.Timestamp],
    qt: pd.Timestamp,
    frequency: str = "Q",
    expected_lags: Optional[dict[str, int]] = None,
) -> int:
    """Excess quarters of lag beyond the expected publication window.

    Returns 0 when the component is within its normal release schedule.
    Returns >0 when it is genuinely behind — this is the input to weight decay.

    Examples (with expected_lag Q=1, A=4):
      Q component, last_obs=Q4-2025, qt=Q1-2026 → total=1, expected=1, excess=0
      Q component, last_obs=Q3-2025, qt=Q1-2026 → total=2, expected=1, excess=1
      A component, last_obs=Dec-2024, qt=Q3-2025 → total=3, expected=4, excess=0
      A component, last_obs=Dec-2023, qt=Q3-2025 → total=7, expected=4, excess=3
    """
    if last_obs is None:
        return 999
    total_lag = max(0, qt.to_period("Q").ordinal - last_obs.to_period("Q").ordinal)
    expected = (expected_lags or _EXPECTED_LAG_BY_FREQ).get(frequency, 1)
    return max(0, total_lag - expected)


def _total_lag_q(last_obs: Optional[pd.Timestamp], qt: pd.Timestamp) -> int:
    """Total quarter distance from the last observation to a snapshot."""
    if last_obs is None:
        return 999
    return max(0, qt.to_period("Q").ordinal - last_obs.to_period("Q").ordinal)


def _latest_observation_date(
    source_indexes: list[pd.DatetimeIndex],
    qt: pd.Timestamp,
) -> Optional[pd.Timestamp]:
    """Return the restrictive latest source date known at ``qt``.

    Multi-source components use the earliest latest date because their combined
    value is only as current as the slower input. Future observations are never
    allowed to suppress historical staleness.
    """
    latest_dates: list[pd.Timestamp] = []
    for index in source_indexes:
        eligible = index[index <= qt]
        if len(eligible) == 0:
            return None
        latest_dates.append(pd.Timestamp(eligible[-1]))
    return min(latest_dates) if latest_dates else None


def staleness_weight_fraction(excess_lag_q: int, half_life_q: Optional[float]) -> float:
    """Exponential stale-weight multiplier with a true quarter half-life."""
    if half_life_q is None or half_life_q <= 0 or excess_lag_q <= 0:
        return 1.0
    return float(0.5 ** (excess_lag_q / half_life_q))


def _extrapolate_z_score(
    z_series: pd.Series,
    qt: pd.Timestamp,
    method: str,
    window: int,
) -> Optional[float]:
    """Estimate a missing Z-score at qt from the component's own historical Z-series.

    Used when a component is beyond its carry-forward horizon and extrapolation
    is enabled in config. The result is flagged in extrapolated_components.

    ⚠ Extrapolation introduces model risk. Keep disabled until back-tested.
    TUNABLE: method and window from config staleness.extrapolation.*
    """
    available = z_series[z_series.index < qt].dropna()
    if len(available) < 3:
        return None
    recent = available.tail(window)

    if method == "rolling_mean":
        return float(recent.mean())
    if method == "linear_trend":
        x = np.arange(len(recent), dtype=float)
        coeffs = np.polyfit(x, recent.values.astype(float), 1)
        # Extrapolate one step ahead from the fitted line
        return float(np.polyval(coeffs, len(recent)))
    return None


# ── Derived ratio construction ────────────────────────────────────────────────

def _build_gov_household_debt_gdp(
    conn,
    country_prefix: str,
    ffill_limit: int = 6,
) -> pd.Series:
    """Sum government debt/GDP and household debt/GDP at quarterly frequency.

    Forward-fills each component up to ffill_limit quarters (from config
    staleness.max_carry_quarters) before summing. This matches the typical BIS
    household-debt publication lag (~3–4 quarters) while still using the latest
    available data rather than producing NaN.
    The caller should check _component_last_dates to flag which components are stale.
    """
    gov = _load_signal_values(conn, f"{country_prefix}.credit.gov_debt_gdp")
    hh = _load_signal_values(conn, f"{country_prefix}.credit.household_debt_gdp")
    if gov.empty and hh.empty:
        return pd.Series(dtype=float)
    # Extend each sub-series to the current quarter before merging, so the
    # combined series covers the current quarter even when one sub-series lags.
    gov = _extend_to_current_quarter(gov.resample("QE").last(), limit=ffill_limit)
    hh  = _extend_to_current_quarter(hh.resample("QE").last(),  limit=ffill_limit)
    idx = gov.index.union(hh.index)
    gov_q = gov.reindex(idx).ffill(limit=ffill_limit)
    hh_q  = hh.reindex(idx).ffill(limit=ffill_limit)
    combined = gov_q.add(hh_q).dropna()
    return combined.resample("QE").last().dropna()


def _build_corporate_debt_gdp(
    data_dir: Path,
    ffill_limit: int = 4,
) -> pd.Series:
    """Construct corporate debt / GDP from raw FRED level series at quarterly frequency.

    BCNSDODNS: Nonfinancial corporate debt, millions $, quarterly.
    GDP: Nominal GDP, billions $ at annualised rate, quarterly.
    The numerator is converted to billions before division.
    """
    corp = _load_raw_fred("BCNSDODNS", data_dir).resample("QE").last().dropna()
    gdp = _load_raw_fred("GDP", data_dir).resample("QE").last().dropna()
    ratio = (corp / 1000.0).divide(gdp).dropna()
    return _extend_to_current_quarter(ratio, limit=ffill_limit)


def _build_federal_interest_gdp(data_dir: Path, ffill_limit: int = 4) -> pd.Series:
    """Construct federal interest outlays / GDP ratio.

    FYOINT: Federal interest outlays, millions $, annual (US fiscal year Oct–Sept).
    GDP: Nominal GDP, billions $, quarterly (annualised rate).

    Unit conversion: FYOINT millions → billions (÷ 1000).
    Frequency alignment: forward-fill the annual FYOINT to quarterly grid, up to
    ffill_limit quarters (from config staleness.max_carry_quarters).
    Z-score is computed AFTER this function returns, at annual frequency — see
    _rolling_z_annual_then_ffill().

    TUNABLE: the forward-fill aligns the fiscal-year total against the quarterly
    annualised GDP rate. The units are compatible (both annual-rate basis).
    """
    fyoint = _load_raw_fred("FYOINT", data_dir)
    gdp = _load_raw_fred("GDP", data_dir).resample("QE").last().dropna()

    # Convert millions → billions
    fyoint_bn = fyoint / 1000.0

    # Resample to annual (last observation per calendar year), then forward-fill quarterly
    fyoint_annual = fyoint_bn.resample("YE").last().dropna()
    fyoint_q = fyoint_annual.reindex(gdp.index, method="ffill", limit=ffill_limit)

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
    ffill_limit: int | None = None,
) -> pd.Series:
    """Rolling Z-score for an annual series, computed at annual frequency, then forward-filled.

    TUNABLE: window and min_periods come from config z_score.window_annual /
             min_periods_annual. shift comes from config z_score.look_back_shift.
             ffill_limit comes from config staleness.max_carry_quarters.

    Carrying forward a single annual Z-score for up to ffill_limit quarters avoids
    the look-ahead and multiple-counting problem that would arise from Z-scoring
    the quarterly forward-filled series directly.
    """
    annual = series.resample("YE").last().dropna()
    prior = annual.shift(shift)
    mu = prior.rolling(window, min_periods=min_periods).mean()
    sigma = prior.rolling(window, min_periods=min_periods).std()
    z_annual = ((annual - mu) / sigma).replace([np.inf, -np.inf], np.nan).dropna()

    if quarterly_index is None:
        return z_annual

    # Forward-fill the annual Z-score into the quarterly grid, limited to
    # max_carry_quarters so stale annual Z-scores age out properly.
    z_q = z_annual.reindex(quarterly_index, method="ffill", limit=ffill_limit)
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

    configured_country = str(config.get("country", "")).upper()
    if configured_country != country.upper():
        raise ValueError(
            f"long-term stress config is for {configured_country}, not {country.upper()}"
        )

    country_prefix = country.lower()
    z_cfg = config.get("z_score", {})
    cov_cfg = config.get("coverage", {})
    stale_cfg = config.get("staleness", {})
    components_cfg = config.get("components", [])

    win_q = z_cfg.get("window_quarters", 40)
    min_q = z_cfg.get("min_periods_quarters", 20)
    win_a = z_cfg.get("window_annual", 10)
    min_a = z_cfg.get("min_periods_annual", 5)
    shift = z_cfg.get("look_back_shift", 1)
    min_weight = cov_cfg.get("min_retained_weight", 0.60)

    # Staleness parameters (Gap 1 + Gap 2). Default to no-decay when section absent
    # (preserves backward compatibility with configs that predate this section).
    stale_halflife: Optional[float] = stale_cfg.get("stale_weight_halflife", None)
    stale_min_frac: float = stale_cfg.get("stale_min_weight_fraction", 0.0)
    max_carry_q: int = stale_cfg.get("max_carry_quarters", 6)
    expected_lags: dict[str, int] = stale_cfg.get(
        "expected_lag_quarters", _EXPECTED_LAG_BY_FREQ
    )

    extrap_cfg = stale_cfg.get("extrapolation", {})
    extrap_enabled: bool = extrap_cfg.get("enabled", False)
    extrap_method: str = extrap_cfg.get("method", "rolling_mean")
    extrap_window: int = extrap_cfg.get("window_quarters", 8)

    comp_map = {c["id"]: c for c in components_cfg}

    # ── Build raw level series for each component ─────────────────────────────

    raw_series: dict[str, pd.Series] = {}
    # Native source dates for point-in-time staleness. Keeping these separate
    # from forward-filled values prevents synthetic carry dates from appearing
    # to be fresh observations.
    observation_sources: dict[str, list[pd.DatetimeIndex]] = {}

    def _record_sources(cid: str, *series: pd.Series) -> None:
        observation_sources[cid] = [
            pd.DatetimeIndex(s.index).sort_values() for s in series if not s.empty
        ]

    # Quarterly derived
    try:
        # Capture sub-component last dates before the merge so staleness is visible
        gov_raw = _load_signal_values(conn, f"{country_prefix}.credit.gov_debt_gdp")
        hh_raw  = _load_signal_values(conn, f"{country_prefix}.credit.household_debt_gdp")
        _record_sources("gov_household_debt_gdp", gov_raw, hh_raw)
        raw_series["gov_household_debt_gdp"] = _build_gov_household_debt_gdp(
            conn, country_prefix, ffill_limit=max_carry_q
        )
    except Exception as exc:
        logger.warning("gov_household_debt_gdp: %s", exc)
        raw_series["gov_household_debt_gdp"] = pd.Series(dtype=float)
        observation_sources["gov_household_debt_gdp"] = []

    try:
        s = _build_corporate_debt_gdp(data_dir, ffill_limit=max_carry_q)
        raw_series["corporate_debt_gdp"] = s
        try:
            corp_obs = _load_raw_fred("BCNSDODNS", data_dir)
            gdp_obs = _load_raw_fred("GDP", data_dir)
            _record_sources("corporate_debt_gdp", corp_obs, gdp_obs)
        except Exception:
            _record_sources("corporate_debt_gdp", s)
    except Exception as exc:
        logger.warning("corporate_debt_gdp: %s", exc)
        raw_series["corporate_debt_gdp"] = pd.Series(dtype=float)
        observation_sources["corporate_debt_gdp"] = []

    # Quarterly signal — forward-fill up to max_carry_q quarters
    try:
        s = _load_signal_values(conn, f"{country_prefix}.credit.debt_service_ratio")
        _record_sources("household_debt_service", s)
        raw_series["household_debt_service"] = _extend_to_current_quarter(
            s.resample("QE").last(), limit=max_carry_q
        )
    except Exception as exc:
        logger.warning("household_debt_service: %s", exc)
        raw_series["household_debt_service"] = pd.Series(dtype=float)
        observation_sources["household_debt_service"] = []

    # Annual derived (Z-score forward-fill to quarterly handled in Z step)
    try:
        s = _build_federal_interest_gdp(data_dir, ffill_limit=max_carry_q)
        raw_series["federal_interest_gdp"] = s
        fyoint_obs = _load_signal_values(
            conn, f"{country_prefix}.fiscal.interest_payments"
        )
        _record_sources("federal_interest_gdp", fyoint_obs if not fyoint_obs.empty else s)
    except Exception as exc:
        logger.warning("federal_interest_gdp: %s", exc)
        raw_series["federal_interest_gdp"] = pd.Series(dtype=float)
        observation_sources["federal_interest_gdp"] = []

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
            _record_sources(cid, s)
        except Exception as exc:
            logger.warning("%s: %s", cid, exc)
            raw_series[cid] = pd.Series(dtype=float)
            observation_sources[cid] = []

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
            # Limited to max_carry_q so annual Z-scores don't carry indefinitely.
            z_series[cid] = _rolling_z_annual_then_ffill(
                raw, win_a, min_a, shift,
                quarterly_index=q_index,
                ffill_limit=max_carry_q,
            )

    # ── Assemble per-quarter snapshots ────────────────────────────────────────

    snapshots: list[DebtStressSnapshot] = []

    for qt in q_index:
        if qt.date() > date.today():
            continue

        # ── Gather raw Z and value for each component ─────────────────────────
        component_z: dict[str, Optional[float]] = {}
        component_val: dict[str, Optional[float]] = {}
        component_last_obs: dict[str, Optional[pd.Timestamp]] = {}

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
                raw_idx = raw_s.index[raw_s.index <= qt]
                if len(raw_idx) > 0:
                    v = raw_s[raw_idx[-1]]
                    raw_val = float(v) if pd.notna(v) else None

            component_z[cid] = z_val
            component_val[cid] = raw_val
            component_last_obs[cid] = _latest_observation_date(
                observation_sources.get(cid, []), qt
            )

        # ── Gap 2: extrapolation beyond carry horizon (when enabled) ──────────
        extrapolated_comps: list[str] = []
        if extrap_enabled:
            for comp in components_cfg:
                cid = comp["id"]
                if component_z.get(cid) is not None:
                    continue  # already has a real value
                freq = comp.get("frequency", "Q")
                last = component_last_obs.get(cid)
                excess = _staleness_lag_q(last, qt, freq, expected_lags)
                if _total_lag_q(last, qt) > max_carry_q:
                    z_extrap = _extrapolate_z_score(
                        z_series.get(cid, pd.Series(dtype=float)),
                        qt, extrap_method, extrap_window,
                    )
                    if z_extrap is not None:
                        component_z[cid] = z_extrap
                        extrapolated_comps.append(f"{cid}:{excess}")

        # ── Gap 1: weight decay proportional to staleness lag ─────────────────
        effective_weights: dict[str, float] = {}
        total_config_weight = sum(c["weight"] for c in components_cfg)

        for comp in components_cfg:
            cid = comp["id"]
            if component_z.get(cid) is None:
                effective_weights[cid] = 0.0
                continue

            freq = comp.get("frequency", "Q")
            last = component_last_obs.get(cid)
            excess = _staleness_lag_q(last, qt, freq, expected_lags)

            if stale_halflife is not None and stale_halflife > 0:
                decay = staleness_weight_fraction(excess, stale_halflife)
                eff_w = comp["weight"] * decay
                # Drop if effective weight falls below the minimum fraction
                if eff_w < stale_min_frac * comp["weight"] and comp["weight"] > 0:
                    component_z[cid] = None
                    eff_w = 0.0
            else:
                # No decay configured — binary present/missing
                eff_w = comp["weight"]

            effective_weights[cid] = eff_w

        active_weight = sum(effective_weights.values())
        n_active = sum(1 for w in effective_weights.values() if w > 0)
        retained = active_weight / total_config_weight if total_config_weight > 0 else 0.0
        low_cov = retained < min_weight

        # ── Aggregate stress score (renormalise effective weights to 1.0) ──────
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
                # Renormalise: each component's share = eff_weight / active_weight
                weighted_sum += signed_z * (effective_weights[cid] / active_weight)
            stress = round(weighted_sum, 4)

        # ── Gap 3: structured stale strings ("cid:lag_q") ────────────────────
        # Only components still active (weight > 0) with excess lag > 0 are stale.
        stale_comps: list[str] = []
        for comp in components_cfg:
            cid = comp["id"]
            if effective_weights.get(cid, 0.0) <= 0:
                continue  # excluded from score — not flagged as stale
            if cid in {e.split(":")[0] for e in extrapolated_comps}:
                continue  # extrapolated — flagged separately
            freq = comp.get("frequency", "Q")
            last = component_last_obs.get(cid)
            excess = _staleness_lag_q(last, qt, freq, expected_lags)
            if excess > 0:
                stale_comps.append(f"{cid}:{excess}")

        snapshots.append(DebtStressSnapshot(
            country=country,
            as_of=qt.date(),
            stress_score=stress,
            n_components=n_active,
            retained_weight=round(retained, 4),
            low_coverage=low_cov,
            stale_components=stale_comps,
            extrapolated_components=extrapolated_comps,
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

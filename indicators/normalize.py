"""Normalization: Z-scores, percentile ranks, direction, staleness, equilibrium distance."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from indicators.models import CountryBinding, Signal
from indicators.transform import compute_momentum

_LOW_HISTORY_THRESHOLD = 15  # fewer obs → set low_history=True

_STALE_THRESHOLDS: dict[str, timedelta] = {
    "D": timedelta(days=5),
    "W": timedelta(days=12),
    # Monthly: data is released ~60 days after period start; allow one full
    # extra release cycle (90 days) before flagging as stale.
    "M": timedelta(days=90),
    # Quarterly: obs_date is the START of the quarter. Advance estimates
    # arrive ~120 days later; revised estimates up to ~150 days later. The
    # next quarter's data is first available ~210 days from period start,
    # so flag stale only at 200 days.
    "Q": timedelta(days=200),
    # Annual: World Bank / IMF annual data is typically published 12–24
    # months after the reference year end, so allow 600 days before flagging.
    "A": timedelta(days=600),
}

_DIRECTION_THRESHOLD = 1e-9       # fallback when series_std is unavailable
_DIRECTION_STD_FRACTION = 0.10    # C1: change must exceed 10% of 1σ to be directional
_WINSORISE_SIGMA = 4.0            # C1: clip outliers beyond ±4σ before Z-scoring


def _zscore_series(s: pd.Series) -> pd.Series:
    """Z-score capped at ±4σ to prevent outlier distortion (C1).

    Computing mean/std first, then capping the resulting Z-score, guarantees the
    output is always in [-4, 4] regardless of the raw distribution shape.
    """
    mu, std = s.mean(), s.std(ddof=1)
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    z = (s - mu) / std
    return z.clip(lower=-_WINSORISE_SIGMA, upper=_WINSORISE_SIGMA)


def _percentile_series(s: pd.Series) -> pd.Series:
    """Fraction of all values strictly below each value (ties share the same rank)."""
    return s.rank(pct=True, method="average") - (0.5 / len(s))


def _direction(change_3m: Optional[float], series_std: Optional[float] = None) -> str:
    """Direction flag with variance-based significance threshold (E1).

    When series_std is provided, the 3-month change must exceed 10% of one
    historical standard deviation to be called rising/falling.  This avoids
    labelling near-zero drift on low-volatility series as directional.
    Falls back to the fixed 1e-9 epsilon when series_std is unavailable.
    """
    if change_3m is None or np.isnan(change_3m):
        return "flat"
    threshold = (
        series_std * _DIRECTION_STD_FRACTION
        if series_std is not None and series_std > 0
        else _DIRECTION_THRESHOLD
    )
    if change_3m > threshold:
        return "rising"
    if change_3m < -threshold:
        return "falling"
    return "flat"


def _is_stale(obs_date: date, frequency: str, is_latest: bool) -> bool:
    if not is_latest:
        return False
    threshold = _STALE_THRESHOLDS.get(frequency, timedelta(days=50))
    return (date.today() - obs_date) > threshold


def build_signals(
    transformed: pd.Series,
    binding: CountryBinding,
    raw: Optional[pd.Series] = None,
) -> list[Signal]:
    """
    Convert a fully-transformed series into a list of Signal objects.

    Z-scores and percentiles are computed against the *full* series history
    (not expanding).  This is appropriate for Phase 1A display.  Phase 3
    backtests will switch to expanding windows for look-ahead-free results.
    """
    clean = transformed.replace([np.inf, -np.inf], np.nan).dropna()
    if isinstance(clean.index, pd.DatetimeIndex):
        clean = clean[clean.index.normalize() <= pd.Timestamp(date.today())]
    if clean.empty:
        return []

    n = len(clean)
    low_history = n < _LOW_HISTORY_THRESHOLD

    zscores = _zscore_series(clean)
    percentiles = _percentile_series(clean)
    c1m, c3m, c12m = compute_momentum(clean, binding.frequency)
    series_std = float(clean.std(ddof=1)) if n > 1 else None

    country_namespace = binding.country.lower()
    signal_id = f"{country_namespace}.{binding.id}"
    source_label = (
        f"{binding.provider}:{binding.series_id}"
        if binding.series_id
        else f"{binding.provider}:{binding.id}"
    )

    signals: list[Signal] = []
    last_idx = len(clean) - 1

    for i, (obs_date, value) in enumerate(clean.items()):
        obs = obs_date.date() if hasattr(obs_date, "date") else obs_date
        is_latest = i == last_idx

        c3m_val = c3m.iloc[i]
        c3m_float = float(c3m_val) if pd.notna(c3m_val) else None

        def _f(v) -> Optional[float]:
            return float(v) if pd.notna(v) else None

        dist = (
            float(value) - binding.equilibrium
            if binding.equilibrium is not None and pd.notna(value)
            else None
        )

        signals.append(
            Signal(
                id=signal_id,
                country=binding.country,
                force=binding.force,
                lead_lag=binding.lead_lag,
                as_of=obs,
                value=_f(value),
                units=binding.units,
                zscore=_f(zscores.iloc[i]),
                level_percentile=_f(percentiles.iloc[i]),
                low_history=low_history,
                change_1m=_f(c1m.iloc[i]),
                change_3m=c3m_float,
                change_12m=_f(c12m.iloc[i]),
                direction=_direction(c3m_float, series_std),
                equilibrium_estimate=binding.equilibrium,
                distance_from_equilibrium=dist,
                is_proxy=binding.is_proxy,
                is_constructed=binding.is_constructed,
                is_stale=_is_stale(obs, binding.frequency, is_latest),
                provider=binding.provider,
                source_tier=binding.source_tier,
                vintage_available=binding.vintage_available,
                linkage=binding.linkage,
                source=source_label,
            )
        )

    return signals


def sanity_check(signal: Signal, binding: CountryBinding) -> list[str]:
    """
    Return a list of warning strings if the latest signal value is outside
    the declared sanity range.  Empty list = OK.
    """
    warnings: list[str] = []
    if signal.value is None:
        return warnings
    if binding.sanity_min is not None and signal.value < binding.sanity_min:
        warnings.append(
            f"{binding.id}: value {signal.value:.4f} below sanity_min {binding.sanity_min}"
        )
    if binding.sanity_max is not None and signal.value > binding.sanity_max:
        warnings.append(
            f"{binding.id}: value {signal.value:.4f} above sanity_max {binding.sanity_max}"
        )
    return warnings

"""Series transformation: YoY%, level pass-through, spread pass-through."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Number of native periods that constitute one year for each frequency
_YOY_PERIODS: dict[str, int] = {
    "D": 252,
    "W": 52,
    "M": 12,
    "Q": 4,
    "A": 1,
}

# Number of native periods per canonical momentum window
_MOMENTUM_PERIODS: dict[str, tuple[int, int, int]] = {
    #         1m   3m   12m
    "D":  (  21,  63, 252),
    "W":  (   4,  13,  52),
    "M":  (   1,   3,  12),
    "Q":  (   1,   1,   4),
    "A":  (   1,   1,   1),
}


def apply_yoy_pct(series: pd.Series, frequency: str) -> pd.Series:
    """Return year-over-year % change as a decimal (0.025 = 2.5 %)."""
    periods = _YOY_PERIODS.get(frequency, 12)
    result = series.pct_change(periods)
    return result.replace([np.inf, -np.inf], np.nan)


def apply_transformation(series: pd.Series, transformation: str, frequency: str) -> pd.Series:
    """
    Apply the declared transformation.

    yoy_pct → pct_change over one year of native periods (decimal)
    level   → pass-through (rates, ratios, diffusion indices)
    spread  → pass-through (already a difference/spread)
    derived → raises; derived series are computed by the pipeline directly
    """
    if transformation == "yoy_pct":
        return apply_yoy_pct(series, frequency)
    if transformation in ("level", "spread"):
        return series.copy()
    if transformation == "derived":
        raise ValueError(
            "Derived series must be computed by pipeline.compute_derived(), "
            "not by apply_transformation()."
        )
    raise ValueError(f"Unknown transformation '{transformation}'")


def compute_momentum(series: pd.Series, frequency: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Return (change_1m, change_3m, change_12m) as absolute differences
    over the canonical period counts for the given frequency.
    """
    p1m, p3m, p12m = _MOMENTUM_PERIODS.get(frequency, (1, 3, 12))
    return series.diff(p1m), series.diff(p3m), series.diff(p12m)


def momentum_periods(frequency: str) -> tuple[int, int, int]:
    return _MOMENTUM_PERIODS.get(frequency, (1, 3, 12))

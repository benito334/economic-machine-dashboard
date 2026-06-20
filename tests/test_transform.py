"""Unit tests for indicators/transform.py — deterministic math only, no I/O."""
import numpy as np
import pandas as pd
import pytest

from indicators.transform import apply_transformation, apply_yoy_pct, compute_momentum, _YOY_PERIODS, _MOMENTUM_PERIODS


def _monthly_series(start="2020-01", periods=36, values=None):
    idx = pd.date_range(start=start, periods=periods, freq="MS")
    if values is None:
        values = np.arange(1.0, periods + 1.0)
    return pd.Series(values, index=idx)


def _quarterly_series(start="2018Q1", periods=24, values=None):
    idx = pd.period_range(start=start, periods=periods, freq="Q").to_timestamp()
    if values is None:
        values = np.arange(100.0, 100.0 + periods)
    return pd.Series(values, index=idx)


class TestApplyYoyPct:
    def test_monthly_yoy_simple(self):
        # 12 months of value 100, then 12 months of 110 → YoY = 0.10
        vals = [100.0] * 12 + [110.0] * 12
        s = _monthly_series(periods=24, values=vals)
        result = apply_yoy_pct(s, "M")
        # First 12 rows should be NaN, next 12 should be ~0.10
        assert result.iloc[:12].isna().all()
        assert np.allclose(result.iloc[12:].dropna(), 0.10, atol=1e-9)

    def test_quarterly_yoy(self):
        vals = [100.0] * 4 + [105.0] * 4
        s = _quarterly_series(periods=8, values=vals)
        result = apply_yoy_pct(s, "Q")
        assert result.iloc[:4].isna().all()
        assert np.allclose(result.iloc[4:].dropna(), 0.05, atol=1e-9)

    def test_zero_base_produces_nan_not_infinity(self):
        s = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0])
        idx = pd.date_range("2020-01", periods=13, freq="MS")
        s.index = idx
        result = apply_yoy_pct(s, "M")
        assert np.isnan(result.iloc[-1])
        assert not np.isinf(result).any()

    def test_daily_uses_252_periods(self):
        # 252 daily values of 1.0 then 252 of 1.05 → YoY = 0.05
        n = 252 * 2
        vals = [1.0] * 252 + [1.05] * 252
        idx = pd.bdate_range("2020-01-01", periods=n)
        s = pd.Series(vals, index=idx)
        result = apply_yoy_pct(s, "D")
        assert np.allclose(result.dropna().iloc[-10:], 0.05, atol=1e-9)


class TestApplyTransformation:
    def test_yoy_pct_delegates(self):
        s = _monthly_series()
        r_direct = apply_yoy_pct(s, "M")
        r_via = apply_transformation(s, "yoy_pct", "M")
        pd.testing.assert_series_equal(r_direct, r_via)

    def test_level_passthrough(self):
        s = _monthly_series()
        r = apply_transformation(s, "level", "M")
        pd.testing.assert_series_equal(s, r)

    def test_spread_passthrough(self):
        s = _monthly_series()
        r = apply_transformation(s, "spread", "M")
        pd.testing.assert_series_equal(s, r)

    def test_derived_raises(self):
        s = _monthly_series()
        with pytest.raises(ValueError, match="derived"):
            apply_transformation(s, "derived", "M")

    def test_unknown_raises(self):
        s = _monthly_series()
        with pytest.raises(ValueError, match="Unknown"):
            apply_transformation(s, "banana", "M")


class TestComputeMomentum:
    def test_monthly_periods(self):
        vals = list(range(24))
        s = _monthly_series(periods=24, values=vals)
        c1m, c3m, c12m = compute_momentum(s, "M")
        # Each diff should be constant (linear series)
        assert np.allclose(c1m.dropna(), 1.0)
        assert np.allclose(c3m.dropna(), 3.0)
        assert np.allclose(c12m.dropna(), 12.0)

    def test_quarterly_periods(self):
        vals = list(range(8))
        s = _quarterly_series(periods=8, values=vals)
        c1m, c3m, c12m = compute_momentum(s, "Q")
        # Q: p1m=1, p3m=1, p12m=4
        assert np.allclose(c1m.dropna(), 1.0)
        assert np.allclose(c3m.dropna(), 1.0)
        assert np.allclose(c12m.dropna(), 4.0)

    def test_nan_where_insufficient_history(self):
        s = _monthly_series(periods=6)
        _, _, c12m = compute_momentum(s, "M")
        # Only 6 obs → first 12 are NaN; all 6 should be NaN
        assert c12m.isna().all()


# ── B1: Calendar-adjusted period constants audit ──────────────────────────────

class TestYoyPeriods:
    """B1: Assert correct calendar N for each native frequency."""

    def test_all_frequencies_present(self):
        for freq in ("D", "W", "M", "Q", "A"):
            assert freq in _YOY_PERIODS, f"Missing YoY period for frequency '{freq}'"

    def test_daily_252_trading_days(self):
        assert _YOY_PERIODS["D"] == 252

    def test_weekly_52_weeks(self):
        assert _YOY_PERIODS["W"] == 52

    def test_monthly_12_months(self):
        assert _YOY_PERIODS["M"] == 12

    def test_quarterly_4_quarters(self):
        assert _YOY_PERIODS["Q"] == 4

    def test_annual_1_year(self):
        assert _YOY_PERIODS["A"] == 1

    def test_weekly_yoy(self):
        # 52 weekly values at 1.0, then 52 at 1.05 → YoY = 0.05
        vals = [1.0] * 52 + [1.05] * 52
        idx = pd.date_range("2020-01-06", periods=104, freq="W-MON")
        s = pd.Series(vals, index=idx)
        result = apply_yoy_pct(s, "W")
        assert result.iloc[:52].isna().all()
        assert np.allclose(result.iloc[52:].dropna(), 0.05, atol=1e-9)

    def test_annual_yoy(self):
        vals = [100.0, 105.0, 110.0]
        idx = pd.date_range("2020", periods=3, freq="YS")
        s = pd.Series(vals, index=idx)
        result = apply_yoy_pct(s, "A")
        assert np.isnan(result.iloc[0])
        assert np.isclose(result.iloc[1], 0.05, atol=1e-9)
        assert np.isclose(result.iloc[2], 110 / 105 - 1, atol=1e-9)


class TestMomentumPeriods:
    """B1: Assert canonical 1m/3m/12m window counts for each frequency."""

    def test_all_frequencies_present(self):
        for freq in ("D", "W", "M", "Q", "A"):
            assert freq in _MOMENTUM_PERIODS

    def test_daily_periods(self):
        p1, p3, p12 = _MOMENTUM_PERIODS["D"]
        assert p1  == 21   # ~1 trading month
        assert p3  == 63   # ~3 trading months
        assert p12 == 252  # 1 trading year

    def test_weekly_periods(self):
        p1, p3, p12 = _MOMENTUM_PERIODS["W"]
        assert p1  == 4    # ~4 weeks per month
        assert p3  == 13   # ~13 weeks per quarter
        assert p12 == 52   # 52 weeks per year

    def test_monthly_periods(self):
        p1, p3, p12 = _MOMENTUM_PERIODS["M"]
        assert (p1, p3, p12) == (1, 3, 12)

    def test_quarterly_periods(self):
        # Q data has no intra-quarter resolution; 1q ≈ "1m" proxy, 4q = 1 year
        p1, p3, p12 = _MOMENTUM_PERIODS["Q"]
        assert p1  == 1
        assert p3  == 1    # no 3-month sub-quarter resolution
        assert p12 == 4

    def test_annual_periods(self):
        # Annual data: all windows collapse to 1 period
        assert _MOMENTUM_PERIODS["A"] == (1, 1, 1)

    def test_daily_momentum_correct_diffs(self):
        n = 252 * 2
        vals = list(range(n))
        idx = pd.bdate_range("2020-01-01", periods=n)
        s = pd.Series(vals, index=idx)
        c1m, c3m, c12m = compute_momentum(s, "D")
        assert np.allclose(c1m.dropna(),  21)
        assert np.allclose(c3m.dropna(),  63)
        assert np.allclose(c12m.dropna(), 252)

    def test_weekly_momentum_correct_diffs(self):
        n = 60
        vals = list(range(n))
        idx = pd.date_range("2020-01-06", periods=n, freq="W-MON")
        s = pd.Series(vals, index=idx)
        c1m, c3m, c12m = compute_momentum(s, "W")
        assert np.allclose(c1m.dropna(),  4)
        assert np.allclose(c3m.dropna(),  13)
        assert np.allclose(c12m.dropna(), 52)

    def test_annual_momentum_correct_diffs(self):
        vals = [10.0, 15.0, 20.0, 30.0]
        idx = pd.date_range("2020", periods=4, freq="YS")
        s = pd.Series(vals, index=idx)
        c1m, c3m, c12m = compute_momentum(s, "A")
        # All windows = 1 for annual freq
        assert np.allclose(c1m.dropna(),  [5.0, 5.0, 10.0])
        assert np.allclose(c3m.dropna(),  [5.0, 5.0, 10.0])
        assert np.allclose(c12m.dropna(), [5.0, 5.0, 10.0])

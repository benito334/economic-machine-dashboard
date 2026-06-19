"""Unit tests for indicators/normalize.py."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from indicators.models import CountryBinding
from indicators.normalize import _direction, _is_stale, _percentile_series, _zscore_series, build_signals, sanity_check


def _binding(**kwargs) -> CountryBinding:
    defaults = dict(
        id="growth.payrolls",
        series_id="PAYEMS",
        provider="FRED",
        frequency="M",
        force="growth",
        lead_lag="coincident",
        transformation="yoy_pct",
        units="yoy_pct",
        verified=True,
        equilibrium=0.015,
        linkage="test",
        sanity_min=-0.10,
        sanity_max=0.08,
    )
    defaults.update(kwargs)
    return CountryBinding(**defaults)


def _monthly_series(n=60):
    idx = pd.date_range("2019-01", periods=n, freq="MS")
    vals = np.linspace(0.01, 0.04, n) + np.random.default_rng(42).normal(0, 0.002, n)
    return pd.Series(vals, index=idx)


class TestZscoreSeries:
    def test_mean_zero(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        z = _zscore_series(s)
        assert abs(z.mean()) < 1e-10

    def test_unit_std(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        z = _zscore_series(s)
        assert abs(z.std(ddof=1) - 1.0) < 1e-10

    def test_constant_series_returns_zeros(self):
        s = pd.Series([3.0] * 10)
        z = _zscore_series(s)
        assert (z == 0).all()

    def test_middle_value_near_zero(self):
        s = pd.Series([0.0, 1.0, 2.0, 3.0, 4.0])
        z = _zscore_series(s)
        # Median value (2.0) should have Z ≈ 0
        assert abs(z.iloc[2]) < 0.01


class TestPercentileSeries:
    def test_range_zero_to_one(self):
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        p = _percentile_series(s)
        assert (p >= 0).all() and (p <= 1).all()

    def test_min_near_zero(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        p = _percentile_series(s)
        assert p.iloc[0] < 0.15

    def test_max_near_one(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        p = _percentile_series(s)
        assert p.iloc[-1] > 0.85

    def test_sorted_is_monotone(self):
        s = pd.Series(sorted([3.0, 1.0, 4.0, 1.5, 9.0, 2.6]))
        p = _percentile_series(s)
        assert (p.diff().dropna() > 0).all()


class TestDirection:
    def test_rising(self):
        assert _direction(0.005) == "rising"

    def test_falling(self):
        assert _direction(-0.005) == "falling"

    def test_flat_zero(self):
        assert _direction(0.0) == "flat"

    def test_none_is_flat(self):
        assert _direction(None) == "flat"

    def test_nan_is_flat(self):
        assert _direction(float("nan")) == "flat"


class TestIsStale:
    def test_non_latest_never_stale(self):
        old = date(2010, 1, 1)
        assert not _is_stale(old, "M", is_latest=False)

    def test_latest_recent_not_stale(self):
        recent = date.today() - timedelta(days=10)
        assert not _is_stale(recent, "M", is_latest=True)

    def test_latest_old_is_stale(self):
        old = date.today() - timedelta(days=200)
        assert _is_stale(old, "M", is_latest=True)

    def test_daily_stale_after_5_days(self):
        just_over = date.today() - timedelta(days=6)
        assert _is_stale(just_over, "D", is_latest=True)


class TestBuildSignals:
    def test_returns_correct_count(self):
        s = _monthly_series(24)
        b = _binding()
        signals = build_signals(s, b)
        assert len(signals) == 24

    def test_signal_id_prefix(self):
        s = _monthly_series(12)
        b = _binding()
        sigs = build_signals(s, b)
        assert all(sig.id == "us.growth.payrolls" for sig in sigs)

    def test_signal_id_uses_binding_country(self):
        s = _monthly_series(12)
        b = _binding(country="JP")
        sigs = build_signals(s, b)
        assert all(sig.id == "jp.growth.payrolls" for sig in sigs)

    def test_source_uses_binding_provider(self):
        s = _monthly_series(12)
        b = _binding(provider="WorldBank", series_id="TEST.ID")
        sigs = build_signals(s, b)
        assert all(sig.source == "WorldBank:TEST.ID" for sig in sigs)

    def test_non_finite_values_are_excluded(self):
        s = _monthly_series(20)
        s.iloc[5] = np.inf
        s.iloc[8] = -np.inf
        sigs = build_signals(s, _binding())
        assert len(sigs) == 18
        assert all(np.isfinite(sig.value) for sig in sigs)

    def test_future_dated_values_are_excluded(self):
        today = pd.Timestamp(date.today())
        s = pd.Series(
            [1.0, 2.0],
            index=[today - pd.Timedelta(days=1), today + pd.Timedelta(days=1)],
        )
        sigs = build_signals(s, _binding())
        assert len(sigs) == 1
        assert sigs[0].as_of < date.today()

    def test_zscore_and_percentile_populated(self):
        s = _monthly_series(30)
        b = _binding()
        sigs = build_signals(s, b)
        assert all(sig.zscore is not None for sig in sigs)
        assert all(sig.level_percentile is not None for sig in sigs)

    def test_low_history_flag(self):
        s = _monthly_series(10)  # below threshold of 15
        b = _binding()
        sigs = build_signals(s, b)
        assert all(sig.low_history for sig in sigs)

    def test_equilibrium_distance(self):
        vals = [0.025] * 20
        s = pd.Series(vals, index=pd.date_range("2020", periods=20, freq="MS"))
        b = _binding(equilibrium=0.015)
        sigs = build_signals(s, b)
        for sig in sigs:
            assert abs(sig.distance_from_equilibrium - 0.01) < 1e-9

    def test_empty_series_returns_empty(self):
        s = pd.Series([], dtype=float)
        b = _binding()
        assert build_signals(s, b) == []

    def test_only_latest_can_be_stale(self):
        # Old series — all but last are not stale
        s = _monthly_series(60)
        b = _binding()
        sigs = build_signals(s, b)
        non_latest_stale = [sig for sig in sigs[:-1] if sig.is_stale]
        assert non_latest_stale == []


class TestSanityCheck:
    def test_ok_within_range(self):
        s = _monthly_series(20)
        b = _binding(sanity_min=-0.10, sanity_max=0.08)
        sigs = build_signals(s, b)
        latest = sigs[-1]
        latest.value = 0.02
        assert sanity_check(latest, b) == []

    def test_warn_below_min(self):
        s = _monthly_series(20)
        b = _binding(sanity_min=0.0, sanity_max=1.0)
        sigs = build_signals(s, b)
        latest = sigs[-1]
        latest.value = -0.5
        warns = sanity_check(latest, b)
        assert len(warns) == 1
        assert "below sanity_min" in warns[0]

    def test_warn_above_max(self):
        s = _monthly_series(20)
        b = _binding(sanity_min=0.0, sanity_max=0.10)
        sigs = build_signals(s, b)
        latest = sigs[-1]
        latest.value = 0.50
        warns = sanity_check(latest, b)
        assert len(warns) == 1
        assert "above sanity_max" in warns[0]

    def test_none_value_ok(self):
        s = _monthly_series(20)
        b = _binding()
        sigs = build_signals(s, b)
        latest = sigs[-1]
        latest.value = None
        assert sanity_check(latest, b) == []

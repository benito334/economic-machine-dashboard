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

    def test_unit_std_without_outliers(self):
        """For a series within ±4σ no capping occurs, so std == 1."""
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        z = _zscore_series(s)
        # max raw Z for [1..5] is ±sqrt(2) ≈ 1.41 — well within ±4 cap
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


# ── C1: Winsorisation ─────────────────────────────────────────────────────────

class TestZscoreWinsorise:
    def test_extreme_spike_is_capped_at_4(self):
        """A massive spike must be capped at exactly ±4 in Z-score space."""
        base = pd.Series(np.linspace(0.0, 1.0, 100))
        spike = base.copy()
        spike.iloc[50] = 1000.0
        z = _zscore_series(spike)
        assert z.iloc[50] == 4.0  # capped, not beyond

    def test_negative_spike_is_capped_at_minus_4(self):
        base = pd.Series(np.linspace(0.0, 1.0, 100))
        spike = base.copy()
        spike.iloc[10] = -1000.0
        z = _zscore_series(spike)
        assert z.iloc[10] == -4.0

    def test_all_values_within_cap(self):
        """Z-scores must always be in [-4, 4]."""
        rng = np.random.default_rng(0)
        s = pd.Series(rng.normal(0, 1, 200))
        s.iloc[::20] = rng.choice([-100, 100], size=10)  # inject spikes
        z = _zscore_series(s)
        assert (z >= -4.0).all() and (z <= 4.0).all()

    def test_clean_series_mean_zero(self):
        """A clean symmetric series has mean Z ≈ 0."""
        s = pd.Series([-2.0, -1.0, 0.0, 1.0, 2.0])
        z = _zscore_series(s)
        assert abs(z.mean()) < 1e-10


# ── E1: Variance-based direction threshold ────────────────────────────────────

class TestDirectionWithStd:
    def test_tiny_change_vs_large_std_is_flat(self):
        """Change of 0.05 against std=10 is 0.5% of σ — below 10% threshold → flat."""
        assert _direction(0.05, series_std=10.0) == "flat"

    def test_significant_positive_change_is_rising(self):
        assert _direction(2.0, series_std=10.0) == "rising"

    def test_significant_negative_change_is_falling(self):
        assert _direction(-2.0, series_std=10.0) == "falling"

    def test_no_std_falls_back_to_epsilon(self):
        """When series_std is None, old 1e-9 epsilon applies — any non-zero change is directional."""
        assert _direction(0.001, series_std=None) == "rising"
        assert _direction(-0.001, series_std=None) == "falling"

    def test_zero_std_falls_back_to_epsilon(self):
        assert _direction(0.001, series_std=0.0) == "rising"

    def test_boundary_at_threshold(self):
        """Change exactly at 10% of σ is just above flat (> not >=)."""
        std = 10.0
        threshold = std * 0.10  # = 1.0
        assert _direction(threshold + 1e-10, series_std=std) == "rising"
        assert _direction(threshold, series_std=std) == "flat"


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

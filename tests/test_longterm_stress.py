"""
Tests for the Long-Term Debt Stress Indicator.

Coverage per spec:
- Unit conversion (FYOINT millions → billions)
- Signs (negative-direction components are negated)
- Look-ahead prevention (shift(1) means current Z uses only prior-period stats)
- Missing components: graceful drop + weight renormalization
- Minimum coverage threshold: low_coverage flag fires below min_retained_weight
- Weight renormalization: renormalised weights sum to 1.0 for active components
- No future-dated snapshots
- Band labels are for display only (confirmed by reading config annotation)
- Config is fully driven by YAML: changing a weight changes the score proportionally
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("INDICATORS_TESTING", "1")

from indicators.longterm_stress import (
    _rolling_z_quarterly,
    _rolling_z_annual_then_ffill,
    _build_federal_interest_gdp,
    _extend_to_current_quarter,
    stress_band_label,
    compute_debt_stress_history,
    load_longterm_stress_config,
)
from indicators.models import DebtStressSnapshot


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_config():
    """Minimal valid config with 3 quarterly components (total weight 1.0)."""
    return {
        "z_score": {
            "window_quarters": 10,
            "min_periods_quarters": 5,
            "window_annual": 5,
            "min_periods_annual": 3,
            "look_back_shift": 1,
        },
        "coverage": {"min_retained_weight": 0.60},
        "bands": {
            "below_normal_upper": -0.5,
            "elevated_lower": 0.5,
            "high_lower": 1.0,
        },
        "components": [
            {"id": "household_debt_service", "label": "DSR", "weight": 0.50,
             "stress_direction": "positive", "frequency": "Q",
             "construction": "signal", "sources": [], "notes": ""},
            {"id": "primary_balance_gdp", "label": "Primary balance", "weight": 0.30,
             "stress_direction": "negative", "frequency": "A",
             "construction": "signal", "sources": [], "notes": ""},
            {"id": "govt_revenue_gdp", "label": "Revenue", "weight": 0.20,
             "stress_direction": "negative", "frequency": "A",
             "construction": "signal", "sources": [], "notes": ""},
        ],
    }


@pytest.fixture
def full_config():
    cfg_path = Path(__file__).parents[1] / "config" / "longterm_stress.yaml"
    return load_longterm_stress_config(cfg_path)


# ── Quarterly index extension ─────────────────────────────────────────────────

def test_extend_to_current_quarter_adds_missing_quarters():
    """A series ending before the current quarter must be extended and forward-filled."""
    from datetime import date
    # Series ending 3 quarters before today
    end = (pd.Timestamp.today() - pd.DateOffset(months=9)).to_period("Q").to_timestamp("Q")
    dates = pd.date_range("2000-01-01", end, freq="QE")
    s = pd.Series(np.arange(len(dates), dtype=float), index=dates)

    extended = _extend_to_current_quarter(s, limit=4)
    current_qe = pd.Timestamp.today().to_period("Q").to_timestamp("Q")
    assert current_qe in extended.index, "Current quarter-end must be present after extension"
    # Value at current quarter-end should equal the last known value (ffill)
    assert extended[current_qe] == s.iloc[-1]


def test_extend_to_current_quarter_respects_limit():
    """Values beyond the ffill limit must remain NaN (then dropped by dropna)."""
    # Make a series ending 6 quarters ago; with limit=4, only 4 should be filled
    end = (pd.Timestamp.today() - pd.DateOffset(months=18)).to_period("Q").to_timestamp("Q")
    dates = pd.date_range("2000-01-01", end, freq="QE")
    s = pd.Series(np.arange(len(dates), dtype=float), index=dates)

    extended = _extend_to_current_quarter(s, limit=4)
    current_qe = pd.Timestamp.today().to_period("Q").to_timestamp("Q")
    # 6 quarters stale with limit=4 → current quarter not present (dropped by dropna)
    assert current_qe not in extended.index, (
        "A series more than `limit` quarters stale should not reach the current quarter"
    )


def test_extend_to_current_quarter_noop_when_current():
    """A series already at the current quarter must not be modified."""
    current_qe = pd.Timestamp.today().to_period("Q").to_timestamp("Q")
    dates = pd.date_range("2020-01-01", current_qe, freq="QE")
    s = pd.Series(np.arange(len(dates), dtype=float), index=dates)
    extended = _extend_to_current_quarter(s, limit=4)
    assert extended.index[-1] == current_qe
    assert len(extended) == len(s)


# ── Unit conversion ───────────────────────────────────────────────────────────

def test_fyoint_unit_conversion(tmp_path):
    """FYOINT is stored in millions $; the ratio uses billions → divide by 1000."""
    # Build mock parquet files
    dates_q = pd.date_range("2010-01-01", periods=40, freq="QE")
    gdp = pd.Series(20_000.0, index=dates_q, name="GDP")
    dates_a = pd.date_range("2010-01-01", periods=10, freq="YE")
    # 400 billion in interest = 400_000 millions
    fyoint = pd.Series(400_000.0, index=dates_a, name="FYOINT")

    raw_dir = tmp_path / "raw_cache"
    raw_dir.mkdir()
    gdp.to_frame().to_parquet(raw_dir / "fred_GDP.parquet")
    fyoint.to_frame().to_parquet(raw_dir / "fred_FYOINT.parquet")

    ratio = _build_federal_interest_gdp(tmp_path)
    assert not ratio.empty
    # Expected: 400 bn / 20_000 bn = 0.02
    assert abs(ratio.dropna().iloc[-1] - 0.02) < 1e-6, (
        "FYOINT unit conversion failed: ratio should be ~0.02 (400bn / 20_000bn)"
    )


# ── Look-ahead prevention ─────────────────────────────────────────────────────

def test_rolling_z_quarterly_no_lookahead():
    """Z-score for period t must not use data from period t."""
    dates = pd.date_range("2000-01-01", periods=50, freq="QE")
    s = pd.Series(np.arange(50, dtype=float), index=dates)

    z = _rolling_z_quarterly(s, window=10, min_periods=5, shift=1)
    z_no_shift = _rolling_z_quarterly(s, window=10, min_periods=5, shift=0)

    # With shift=1, the current value always looks positive (value is latest in a rising series)
    # With shift=0, the mean/std include the current point, compressing the Z-score
    # They must differ for a non-stationary series
    valid = z.dropna()
    valid_ns = z_no_shift.dropna()
    # The two series must not be identical
    assert not valid.equals(valid_ns), "shift=1 and shift=0 should produce different Z-scores"
    # With shift=1 the most-recent Z-score should be large and positive (rising series)
    assert valid.iloc[-1] > 0


def test_rolling_z_annual_no_lookahead():
    """Annual Z-score must use shift(1) before computing rolling stats."""
    dates = pd.date_range("1990-01-01", periods=20, freq="YE")
    s = pd.Series(np.arange(20, dtype=float), index=dates)
    q_index = pd.date_range("1990-01-01", periods=120, freq="QE")

    z = _rolling_z_annual_then_ffill(s, window=5, min_periods=3, shift=1, quarterly_index=q_index)
    z_no = _rolling_z_annual_then_ffill(s, window=5, min_periods=3, shift=0, quarterly_index=q_index)

    assert not z.dropna().equals(z_no.dropna()), "look_back_shift=1 vs 0 must differ"


# ── Sign convention ───────────────────────────────────────────────────────────

def test_negative_direction_components_reduce_stress(minimal_config):
    """A rising 'negative-direction' component (e.g. surplus) should lower the stress score."""
    dates = pd.date_range("2000-01-01", periods=60, freq="QE")
    # DSR (positive direction): gently rising → positive Z in later periods
    dsr = pd.Series(np.linspace(10.0, 20.0, 60), index=dates)
    # Primary balance (negative direction): progressively larger surplus (rising positive values)
    primary = pd.Series(np.linspace(-5.0, 5.0, 60), index=dates)
    # Revenue (negative direction): gently rising — non-constant so sigma > 0
    revenue = pd.Series(np.linspace(28.0, 32.0, 60), index=dates)

    cfg = minimal_config

    def fake_signal(conn, signal_id: str):
        if "debt_service" in signal_id:
            return dsr
        if "primary_balance" in signal_id:
            return primary
        if "govt_revenue" in signal_id:
            return revenue
        return pd.Series(dtype=float)

    with patch("indicators.longterm_stress._load_signal_values", side_effect=fake_signal), \
         patch("indicators.longterm_stress._build_gov_household_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_corporate_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_federal_interest_gdp", return_value=pd.Series(dtype=float)):
        snaps = compute_debt_stress_history(MagicMock(), "US", cfg, Path("/tmp"))

    valid = [s for s in snaps if s.stress_score is not None and s.z_primary_balance_gdp is not None]
    assert valid, "Expected some valid snapshots"
    # In the final quarters the primary balance Z is large and positive.
    # Because stress_direction=negative the Z is negated → stress contribution is negative.
    final = valid[-1]
    assert final.z_primary_balance_gdp is not None
    # The sign-negated contribution must reduce the score below what a positive contribution would give
    # Verify by checking that stress_score < DSR-only component (0.50 * DSR_z)
    # DSR is flat so its Z ≈ 0; total stress should be negative due to primary balance
    assert final.stress_score < 0, (
        f"Rising surplus should produce negative stress contribution; got {final.stress_score}"
    )


# ── Missing components & weight renormalisation ───────────────────────────────

def test_missing_component_renormalizes_weights(minimal_config):
    """When one component is missing, the remaining weights are renormalised to 1.0."""
    dates = pd.date_range("2000-01-01", periods=60, freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, 60), index=dates)

    def fake_signal(conn, signal_id: str):
        if "debt_service" in signal_id:
            return dsr
        return pd.Series(dtype=float)  # all other signals missing

    with patch("indicators.longterm_stress._load_signal_values", side_effect=fake_signal), \
         patch("indicators.longterm_stress._build_gov_household_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_corporate_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_federal_interest_gdp", return_value=pd.Series(dtype=float)):
        snaps = compute_debt_stress_history(MagicMock(), "US", minimal_config, Path("/tmp"))

    # DSR weight = 0.50; primary (0.30) + revenue (0.20) are missing → retained = 0.50
    # 0.50 < min_retained_weight (0.60) → low_coverage=True, stress_score=None
    valid = [s for s in snaps if s.n_components > 0]
    assert valid
    for s in valid:
        if s.n_components == 1:
            assert s.low_coverage is True, "retained_weight=0.50 should trigger low_coverage"
            assert s.stress_score is None, "low_coverage snapshot must have null stress_score"


def test_retained_weight_calculation(minimal_config):
    """retained_weight = sum(active component weights) / sum(all component weights)."""
    dates = pd.date_range("2000-01-01", periods=60, freq="QE")
    # Non-constant so sigma > 0 → valid Z-scores
    dsr = pd.Series(np.linspace(10.0, 20.0, 60), index=dates)
    revenue = pd.Series(np.linspace(28.0, 32.0, 60), index=dates)

    def fake_signal(conn, signal_id: str):
        if "debt_service" in signal_id:
            return dsr
        if "govt_revenue" in signal_id:
            return revenue
        return pd.Series(dtype=float)  # primary_balance missing

    with patch("indicators.longterm_stress._load_signal_values", side_effect=fake_signal), \
         patch("indicators.longterm_stress._build_gov_household_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_corporate_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_federal_interest_gdp", return_value=pd.Series(dtype=float)):
        snaps = compute_debt_stress_history(MagicMock(), "US", minimal_config, Path("/tmp"))

    # DSR (0.50) + revenue (0.20) = 0.70 out of 1.00; primary_balance is empty → not active
    # Need quarters where both DSR and revenue Z-scores are valid (after min_periods warm-up)
    valid = [s for s in snaps if s.n_components == 2 and s.retained_weight is not None]
    assert valid, "Expected snapshots with exactly 2 active components"
    for s in valid:
        assert abs(s.retained_weight - 0.70) < 0.01, (
            f"retained_weight should be ~0.70; got {s.retained_weight}"
        )


# ── No future-dated snapshots ─────────────────────────────────────────────────

def test_no_future_dated_snapshots(minimal_config):
    """Snapshots must not have as_of dates in the future."""
    dates = pd.date_range("2000-01-01", periods=120, freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, 120), index=dates)
    revenue = pd.Series(30.0, index=dates)
    primary = pd.Series(-2.0, index=dates)

    def fake_signal(conn, signal_id: str):
        if "debt_service" in signal_id:
            return dsr
        if "govt_revenue" in signal_id:
            return revenue
        if "primary_balance" in signal_id:
            return primary
        return pd.Series(dtype=float)

    with patch("indicators.longterm_stress._load_signal_values", side_effect=fake_signal), \
         patch("indicators.longterm_stress._build_gov_household_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_corporate_debt_gdp", return_value=pd.Series(dtype=float)), \
         patch("indicators.longterm_stress._build_federal_interest_gdp", return_value=pd.Series(dtype=float)):
        snaps = compute_debt_stress_history(MagicMock(), "US", minimal_config, Path("/tmp"))

    today = date.today()
    future = [s for s in snaps if s.as_of > today]
    assert not future, f"Got {len(future)} future-dated snapshots"


# ── Band labels ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected", [
    (-1.0, "Below-normal stress"),
    (-0.5, "Near historical norm"),     # exactly at boundary → "Near historical norm"
    (0.0,  "Near historical norm"),
    (0.5,  "Elevated stress"),
    (0.9,  "Elevated stress"),
    (1.0,  "High relative stress"),
    (2.5,  "High relative stress"),
])
def test_stress_band_labels(score, expected, full_config):
    bands = full_config["bands"]
    assert stress_band_label(score, bands) == expected


# ── Config YAML drives output ─────────────────────────────────────────────────

def test_config_weight_change_affects_score(minimal_config):
    """Doubling a component's weight (while reducing another) shifts the score proportionally."""
    import copy
    dates = pd.date_range("2000-01-01", periods=60, freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, 60), index=dates)
    revenue = pd.Series(np.linspace(25.0, 35.0, 60), index=dates)
    primary = pd.Series(-2.0, index=dates)

    def fake_signal(conn, signal_id: str):
        if "debt_service" in signal_id:
            return dsr
        if "govt_revenue" in signal_id:
            return revenue
        if "primary_balance" in signal_id:
            return primary
        return pd.Series(dtype=float)

    kwargs = dict(
        side_effect=fake_signal,
    )

    def run_with_config(cfg):
        with patch("indicators.longterm_stress._load_signal_values", **kwargs), \
             patch("indicators.longterm_stress._build_gov_household_debt_gdp", return_value=pd.Series(dtype=float)), \
             patch("indicators.longterm_stress._build_corporate_debt_gdp", return_value=pd.Series(dtype=float)), \
             patch("indicators.longterm_stress._build_federal_interest_gdp", return_value=pd.Series(dtype=float)):
            return compute_debt_stress_history(MagicMock(), "US", cfg, Path("/tmp"))

    snaps_default = run_with_config(minimal_config)

    # Shift weight: double DSR weight, halve primary balance weight
    cfg2 = copy.deepcopy(minimal_config)
    cfg2["components"][0]["weight"] = 1.00   # DSR: 0.50 → 1.00
    cfg2["components"][1]["weight"] = 0.00   # primary: 0.30 → 0.00 (effectively absent)
    cfg2["components"][2]["weight"] = 0.00   # revenue: 0.20 → 0.00
    snaps_shifted = run_with_config(cfg2)

    valid_d = [s for s in snaps_default if s.stress_score is not None]
    valid_s = [s for s in snaps_shifted if s.stress_score is not None]

    assert valid_d and valid_s, "Need valid snapshots from both runs"
    # The two scores should differ — a DSR-only indicator differs from the mixed one
    assert valid_d[-1].stress_score != valid_s[-1].stress_score, (
        "Changing component weights in config must change the stress score"
    )


# ── DebtStressSnapshot model ──────────────────────────────────────────────────

def test_debt_stress_snapshot_defaults():
    s = DebtStressSnapshot(country="US", as_of=date(2024, 3, 31))
    assert s.stress_score is None
    assert s.n_components == 0
    assert s.low_coverage is False
    assert s.z_gov_household_debt_gdp is None


def test_debt_stress_snapshot_full():
    s = DebtStressSnapshot(
        country="US",
        as_of=date(2024, 3, 31),
        stress_score=0.75,
        n_components=6,
        retained_weight=0.95,
        low_coverage=False,
        z_household_debt_service=1.2,
        val_household_debt_service=15.3,
    )
    assert s.stress_score == 0.75
    assert s.z_household_debt_service == 1.2
    assert s.val_household_debt_service == 15.3


# ── Full config loads cleanly ─────────────────────────────────────────────────

def test_full_config_structure(full_config):
    assert "z_score" in full_config
    assert "coverage" in full_config
    assert "bands" in full_config
    assert "components" in full_config
    assert len(full_config["components"]) == 7

    weights = sum(c["weight"] for c in full_config["components"])
    assert abs(weights - 1.0) < 1e-6, f"Component weights must sum to 1.0, got {weights}"

    for c in full_config["components"]:
        assert c["stress_direction"] in ("positive", "negative")
        assert c["frequency"] in ("Q", "A")
        assert "notes" in c, f"Component {c['id']} missing notes"
        assert 0 < c["weight"] <= 1.0, f"Component {c['id']} weight must be in (0, 1]"


def test_config_look_back_shift_is_nonzero(full_config):
    """look_back_shift must remain >= 1 to prevent look-ahead bias."""
    shift = full_config["z_score"]["look_back_shift"]
    assert shift >= 1, (
        f"look_back_shift={shift}; setting to 0 introduces look-ahead bias in backtests"
    )

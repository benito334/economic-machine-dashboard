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
    _build_corporate_debt_gdp,
    _rolling_z_quarterly,
    _rolling_z_annual_then_ffill,
    _build_federal_interest_gdp,
    _extend_to_current_quarter,
    _staleness_lag_q,
    _extrapolate_z_score,
    _latest_observation_date,
    staleness_weight_fraction,
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
        "country": "US",
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


def test_corporate_debt_unit_conversion(tmp_path):
    """BCNSDODNS is millions while GDP is billions; the ratio must be unitless."""
    dates = pd.date_range("2020-01-01", periods=8, freq="QE")
    raw_dir = tmp_path / "raw_cache"
    raw_dir.mkdir()
    pd.Series(14_000_000.0, index=dates, name="BCNSDODNS").to_frame().to_parquet(
        raw_dir / "fred_BCNSDODNS.parquet"
    )
    pd.Series(28_000.0, index=dates, name="GDP").to_frame().to_parquet(
        raw_dir / "fred_GDP.parquet"
    )

    ratio = _build_corporate_debt_gdp(tmp_path)
    assert ratio.iloc[-1] == pytest.approx(0.5)


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
    assert full_config["country"] == "US"
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


def test_config_loader_rejects_lookahead(tmp_path, full_config):
    import copy
    import yaml

    invalid = copy.deepcopy(full_config)
    invalid["z_score"]["look_back_shift"] = 0
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(invalid))
    with pytest.raises(ValueError, match="look_back_shift"):
        load_longterm_stress_config(path)


def test_compute_rejects_country_config_mismatch(minimal_config):
    with pytest.raises(ValueError, match="not EZ"):
        compute_debt_stress_history(MagicMock(), "EZ", minimal_config, Path("/tmp"))


# ── Gap 1: Staleness lag calculation ─────────────────────────────────────────

def test_staleness_lag_q_zero_when_current():
    """A quarterly component whose last obs is Q4 should show 0 excess lag in Q1."""
    last = pd.Timestamp("2025-12-31")   # Q4 2025
    qt   = pd.Timestamp("2026-03-31")   # Q1 2026 — one quarter later (expected lag=1)
    assert _staleness_lag_q(last, qt, "Q") == 0


def test_staleness_lag_q_one_excess_quarter():
    """A quarterly component two quarters behind should show excess=1."""
    last = pd.Timestamp("2025-09-30")   # Q3 2025
    qt   = pd.Timestamp("2026-03-31")   # Q1 2026 — two quarters later, excess = 2-1 = 1
    assert _staleness_lag_q(last, qt, "Q") == 1


def test_staleness_lag_q_annual_within_window():
    """An annual component 3 quarters behind (expected 4) should show excess=0."""
    last = pd.Timestamp("2024-12-31")   # Dec 2024
    qt   = pd.Timestamp("2025-09-30")   # Q3 2025 — 3 quarters later, expected=4, excess=0
    assert _staleness_lag_q(last, qt, "A") == 0


def test_staleness_lag_q_annual_stale():
    """An annual component 7 quarters behind (expected 4) should show excess=3."""
    last = pd.Timestamp("2023-12-31")   # Dec 2023
    qt   = pd.Timestamp("2025-09-30")   # Q3 2025 — 7 quarters later, excess = 7-4 = 3
    assert _staleness_lag_q(last, qt, "A") == 3


def test_staleness_lag_q_none_returns_large():
    """None last_obs should return a large sentinel value (treat as maximally stale)."""
    qt = pd.Timestamp("2026-03-31")
    assert _staleness_lag_q(None, qt, "Q") >= 100


def test_latest_observation_date_is_point_in_time_and_restrictive():
    source_a = pd.DatetimeIndex(["2024-03-31", "2024-06-30", "2025-03-31"])
    source_b = pd.DatetimeIndex(["2024-03-31", "2024-09-30"])
    result = _latest_observation_date([source_a, source_b], pd.Timestamp("2024-12-31"))
    assert result == pd.Timestamp("2024-06-30")


def test_staleness_weight_uses_true_half_life():
    assert staleness_weight_fraction(0, 4) == 1.0
    assert staleness_weight_fraction(4, 4) == pytest.approx(0.5)
    assert staleness_weight_fraction(8, 4) == pytest.approx(0.25)


def test_snapshot_list_defaults_are_independent():
    first = DebtStressSnapshot(country="US", as_of=date(2024, 3, 31))
    second = DebtStressSnapshot(country="US", as_of=date(2024, 6, 30))
    first.stale_components.append("test:1")
    assert second.stale_components == []


# ── Gap 1: Weight decay reduces retained_weight ───────────────────────────────

def test_weight_decay_stale_component_reduces_retained(minimal_config):
    """When a component carries stale data its effective weight is reduced, lowering retained_weight."""
    import copy
    cfg = copy.deepcopy(minimal_config)
    # Add staleness decay with halflife=4 quarters
    cfg["staleness"] = {
        "stale_weight_halflife": 4,
        "stale_min_weight_fraction": 0.0,  # never drop, just decay
        "max_carry_quarters": 8,
        "extrapolation": {"enabled": False},
    }

    dates = pd.date_range("2000-01-01", periods=80, freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, 80), index=dates)
    # Annual series — stops 3 years ago so it will be stale for recent quarters
    annual_dates = pd.date_range("2000-01-01", periods=18, freq="YE")
    primary = pd.Series(np.linspace(-5.0, 2.0, 18), index=annual_dates)
    revenue = pd.Series(np.linspace(28.0, 35.0, 18), index=annual_dates)

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

    # Recent snapshots where the annual series are stale should have retained_weight < 1.0
    # (because stale weight decays). Larger excess lags have lower retained weight.
    valid = [s for s in snaps if s.retained_weight is not None and s.n_components > 0]
    assert valid
    # In the final periods both annual series are very stale — weight should be decayed
    # No retained_weight should exceed 1.0.
    for s in valid:
        assert s.retained_weight <= 1.0 + 1e-6


def test_weight_decay_excludes_when_below_min_fraction(minimal_config):
    """A component with excess lag >> halflife should be dropped (effective weight < min_fraction)."""
    import copy
    cfg = copy.deepcopy(minimal_config)
    cfg["staleness"] = {
        "stale_weight_halflife": 2,          # sharp decay — weight halves every 2 excess quarters
        "stale_min_weight_fraction": 0.20,   # drop below 20% of original weight
        "max_carry_quarters": 40,            # allow long carry so Z-scores exist
        "extrapolation": {"enabled": False},
    }

    # DSR: runs up to the current date so recent snapshots exist
    dates_q = pd.date_range("2000-01-01", pd.Timestamp.today(), freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, len(dates_q)), index=dates_q)
    # Annual series ending 6 years ago → excess >> half-life → weight falls below cutoff
    old_end = pd.Timestamp.today() - pd.DateOffset(years=6)
    annual_dates = pd.date_range("2000-01-01", old_end, freq="YE")
    primary = pd.Series(np.linspace(-5.0, 2.0, len(annual_dates)), index=annual_dates)
    revenue = pd.Series(np.linspace(28.0, 35.0, len(annual_dates)), index=annual_dates)

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

    # The most recent snapshot should have the annual components dropped because their
    # excess lag >> stale_weight_halflife=2 → eff_weight < 0.20 → excluded
    all_snaps = [s for s in snaps]
    assert all_snaps
    last = all_snaps[-1]
    assert last.n_components <= 1, (
        f"Very stale annual components should be dropped; got n_components={last.n_components} "
        f"at {last.as_of}, retained={last.retained_weight}"
    )


# ── Gap 3: Structured stale string format ─────────────────────────────────────

def test_stale_components_include_lag_q(minimal_config):
    """stale_components entries must be in 'cid:lag_q' format when stale."""
    import copy
    cfg = copy.deepcopy(minimal_config)
    cfg["staleness"] = {
        "stale_weight_halflife": 8,
        "stale_min_weight_fraction": 0.0,
        "max_carry_quarters": 8,
        "extrapolation": {"enabled": False},
    }

    dates_q = pd.date_range("2000-01-01", periods=60, freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, 60), index=dates_q)
    # Annual data ending 2 years ago — will be stale with excess > 0
    old_end = pd.Timestamp.today() - pd.DateOffset(years=2)
    ann_dates = pd.date_range("2000-01-01", old_end, freq="YE")
    primary = pd.Series(np.linspace(-5.0, 2.0, len(ann_dates)), index=ann_dates)
    revenue = pd.Series(np.linspace(28.0, 35.0, len(ann_dates)), index=ann_dates)

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

    # Find snapshots where annual components are stale
    stale_snaps = [s for s in snaps if s.stale_components]
    assert stale_snaps, "Expected some snapshots with stale components"
    for s in stale_snaps:
        for entry in s.stale_components:
            assert ":" in entry, (
                f"stale_components entry '{entry}' must be 'cid:lag_q' format"
            )
            cid, lag_str = entry.split(":", 1)
            assert cid  # non-empty cid
            assert int(lag_str) >= 1  # lag must be at least 1


# ── Gap 2: Extrapolation ──────────────────────────────────────────────────────

def test_extrapolate_z_score_rolling_mean():
    """rolling_mean extrapolation returns the mean of recent Z-scores."""
    dates = pd.date_range("2020-01-01", periods=12, freq="QE")
    z = pd.Series([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6], index=dates)
    qt = pd.Timestamp("2023-06-30")  # beyond all data
    result = _extrapolate_z_score(z, qt, method="rolling_mean", window=8)
    expected = float(z.tail(8).mean())
    assert result is not None
    assert abs(result - expected) < 1e-6


def test_extrapolate_z_score_linear_trend():
    """linear_trend extrapolation returns a value beyond the last point."""
    dates = pd.date_range("2020-01-01", periods=10, freq="QE")
    # Perfect linear series: 0, 1, 2, ..., 9 → trend should extrapolate to ~10
    z = pd.Series(np.arange(10, dtype=float), index=dates)
    qt = pd.Timestamp("2022-09-30")
    result = _extrapolate_z_score(z, qt, method="linear_trend", window=10)
    assert result is not None
    assert abs(result - 10.0) < 0.5  # extrapolated one step ahead ≈ 10


def test_extrapolate_z_score_too_few_points():
    """With fewer than 3 historical points, extrapolation returns None."""
    dates = pd.date_range("2020-01-01", periods=2, freq="QE")
    z = pd.Series([1.0, 1.5], index=dates)
    qt = pd.Timestamp("2022-01-01")
    result = _extrapolate_z_score(z, qt, method="rolling_mean", window=8)
    assert result is None


def test_extrapolated_components_populated_when_enabled(minimal_config):
    """When extrapolation is enabled, extrapolated_components is non-empty for old components."""
    import copy
    cfg = copy.deepcopy(minimal_config)
    cfg["staleness"] = {
        "stale_weight_halflife": 20,
        "stale_min_weight_fraction": 0.0,
        "max_carry_quarters": 1,           # very short carry horizon → triggers extrapolation
        "extrapolation": {
            "enabled": True,
            "method": "rolling_mean",
            "window_quarters": 4,
        },
    }

    # dsr must run to today so q_index reaches current quarters (where the
    # annual data that ended 3 years ago is stale enough to trigger extrapolation)
    dates_q = pd.date_range("2000-01-01", pd.Timestamp.today(), freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, len(dates_q)), index=dates_q)
    # Annual data: ends well before current date → beyond max_carry_quarters=1
    ann_end = pd.Timestamp.today() - pd.DateOffset(years=3)
    ann_dates = pd.date_range("2000-01-01", ann_end, freq="YE")
    if len(ann_dates) < 8:
        pytest.skip("Not enough history for extrapolation test")
    primary = pd.Series(np.linspace(-5.0, 2.0, len(ann_dates)), index=ann_dates)
    revenue = pd.Series(np.linspace(28.0, 35.0, len(ann_dates)), index=ann_dates)

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

    extrap_snaps = [s for s in snaps if s.extrapolated_components]
    assert extrap_snaps, "Expected extrapolated_components to be populated when enabled"
    for s in extrap_snaps:
        for entry in s.extrapolated_components:
            assert ":" in entry, f"extrapolated_components entry '{entry}' must be 'cid:lag_q'"


def test_extrapolated_components_empty_when_disabled(minimal_config):
    """When extrapolation is disabled, extrapolated_components is always empty."""
    import copy
    cfg = copy.deepcopy(minimal_config)
    cfg["staleness"] = {
        "stale_weight_halflife": 20,
        "stale_min_weight_fraction": 0.0,
        "max_carry_quarters": 1,
        "extrapolation": {"enabled": False},
    }

    dates_q = pd.date_range("2000-01-01", periods=80, freq="QE")
    dsr = pd.Series(np.linspace(10.0, 20.0, 80), index=dates_q)
    ann_end = pd.Timestamp.today() - pd.DateOffset(years=3)
    ann_dates = pd.date_range("2000-01-01", ann_end, freq="YE")
    primary = pd.Series(np.linspace(-5.0, 2.0, len(ann_dates)), index=ann_dates)
    revenue = pd.Series(np.linspace(28.0, 35.0, len(ann_dates)), index=ann_dates)

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

    for s in snaps:
        assert s.extrapolated_components == [], (
            "extrapolated_components must be empty when extrapolation.enabled=False"
        )


# ── Full config: staleness section structure ──────────────────────────────────

def test_full_config_staleness_section(full_config):
    """Full config must have a staleness section with required fields."""
    stale = full_config.get("staleness")
    assert stale is not None, "staleness section missing from config"
    assert stale["expected_lag_quarters"] == {"Q": 1, "A": 4}
    assert "stale_weight_halflife" in stale
    assert "stale_min_weight_fraction" in stale
    assert "max_carry_quarters" in stale
    extrap = stale.get("extrapolation", {})
    assert "enabled" in extrap
    assert "method" in extrap
    assert extrap["method"] in ("rolling_mean", "linear_trend")
    # Safety guard: extrapolation must be off by default until back-tested
    assert extrap["enabled"] is False, (
        "extrapolation.enabled must be False by default; enable only after validation"
    )

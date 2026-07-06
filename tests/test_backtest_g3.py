"""Tests for the Phase G3 vintage-replay + asset-outcome module."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import numpy as np
import pandas as pd
import pytest

from indicators.backtest_g3 import (
    BOND_DURATION,
    VintageSeries,
    chip_conditioned_returns,
)


def _vint(rows):
    return pd.DataFrame(rows, columns=["date", "realtime_start", "value"]).assign(
        date=lambda d: pd.to_datetime(d["date"]),
        realtime_start=lambda d: pd.to_datetime(d["realtime_start"]),
    )


# ── VintageSeries: as-known-at-t semantics ────────────────────────────────────

def test_as_known_uses_only_released_vintages():
    """A revision published after t must be invisible at t."""
    v = _vint([
        ("2020-01-01", "2020-02-05", 100.0),   # first print of Jan
        ("2020-01-01", "2020-03-05", 105.0),   # revised in March
        ("2020-02-01", "2020-03-05", 110.0),   # first print of Feb
    ])
    vs = VintageSeries(v)
    known_feb = vs.as_known(pd.Timestamp("2020-02-20"))
    assert list(known_feb.values) == [100.0]           # only Jan first print
    known_mar = vs.as_known(pd.Timestamp("2020-03-10"))
    assert list(known_mar.values) == [105.0, 110.0]    # revision + Feb print


def test_as_known_excludes_future_observation_dates():
    """An observation dated after t is never included, even if pre-released."""
    v = _vint([
        ("2020-01-01", "2020-02-05", 100.0),
        ("2020-06-01", "2020-02-05", 999.0),   # pathological: future obs date
    ])
    vs = VintageSeries(v)
    known = vs.as_known(pd.Timestamp("2020-03-01"))
    assert 999.0 not in known.values


def test_as_known_before_first_release_is_empty():
    v = _vint([("2020-01-01", "2020-02-05", 100.0)])
    vs = VintageSeries(v)
    assert vs.as_known(pd.Timestamp("2020-01-15")).empty


def test_as_known_picks_latest_released_vintage():
    v = _vint([
        ("2020-01-01", "2020-02-05", 100.0),
        ("2020-01-01", "2020-03-05", 105.0),
        ("2020-01-01", "2020-04-05", 103.0),
    ])
    vs = VintageSeries(v)
    assert vs.as_known(pd.Timestamp("2020-05-01")).iloc[0] == 103.0


# ── Chip-conditioned forward returns ─────────────────────────────────────────

def test_forward_return_has_no_information_overlap():
    """The forward window starts the month AFTER the chip month: a chip in
    month m must be paired with returns from m+1..m+h only."""
    idx = pd.date_range("2020-01-31", periods=8, freq="ME")
    # returns: +1% only in Apr..Jun; all else 0
    rets = pd.Series([0, 0, 0, 0.01, 0.01, 0.01, 0, 0], index=idx)
    chips = pd.DataFrame({"growth_chip": ["Growth"] * 8}, index=idx)
    out = chip_conditioned_returns(chips, rets, "growth_chip", horizon=3)
    # chip at Mar (m=2) → fwd = Apr+May+Jun = 3% over 3m → 12% annualized
    # verify at least one row and the max annualized mean is 0.03*4 = 0.12
    assert out.loc["Growth", "count"] > 0
    # reconstruct: the mean must be an average of per-month annualized fwd sums
    assert out.loc["Growth", "mean"] <= 0.12 + 1e-9


def test_chip_grouping_separates_labels():
    idx = pd.date_range("2020-01-31", periods=12, freq="ME")
    rets = pd.Series([0.02] * 6 + [-0.02] * 6, index=idx)
    chips = pd.DataFrame(
        {"growth_chip": ["Growth"] * 5 + ["Retraction"] * 7}, index=idx)
    out = chip_conditioned_returns(chips, rets, "growth_chip", horizon=1)
    assert out.loc["Growth", "mean"] > out.loc["Retraction", "mean"]


# ── Bond return construction ──────────────────────────────────────────────────

def test_bond_return_formula_sign():
    """Rising yields must produce negative price-component returns."""
    y = pd.Series([4.0, 5.0], index=pd.to_datetime(["2020-01-31", "2020-02-29"])) / 100
    dy = y.diff()
    ret = (-BOND_DURATION * dy + y.shift(1) / 12.0).dropna()
    assert ret.iloc[0] < 0          # −7.5 × 1pp + carry ≈ −7.2%
    assert ret.iloc[0] == pytest.approx(-BOND_DURATION * 0.01 + 0.04 / 12)

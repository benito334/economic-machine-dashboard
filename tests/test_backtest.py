"""Tests for the Phase G point-in-time backtest engine (G1+G2)."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("INDICATORS_TESTING", "1")

from indicators.backtest import (
    Scenario,
    pit_composite,
    pit_zscore,
    score_scenario,
)


# ── G1: point-in-time Z-scores ────────────────────────────────────────────────

def test_pit_zscore_has_no_lookahead():
    """Changing FUTURE values must not change PAST Z-scores."""
    idx = pd.date_range("2000-01-31", periods=60, freq="ME")
    rng = np.random.default_rng(3)
    base = pd.Series(rng.normal(0, 1, 60), index=idx)

    z_a = pit_zscore(base, min_periods=12)
    tampered = base.copy()
    tampered.iloc[50:] += 100.0  # massive future shock
    z_b = pit_zscore(tampered, min_periods=12)

    pd.testing.assert_series_equal(z_a.iloc[:50], z_b.iloc[:50])


def test_pit_zscore_excludes_current_observation():
    """Value at t is scored against stats of strictly-prior observations."""
    idx = pd.date_range("2000-01-31", periods=6, freq="ME")
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 100.0], index=idx)
    z = pit_zscore(s, min_periods=3)
    prior = s.iloc[:5]  # obs before the last one
    expected = (100.0 - prior.mean()) / prior.std()
    expected = min(expected, 4.0)  # ZSCORE_CAP_SIGMA clip
    assert z.iloc[-1] == pytest.approx(expected)


def test_pit_zscore_clips_to_cap():
    idx = pd.date_range("2000-01-31", periods=40, freq="ME")
    s = pd.Series([1.0] * 39 + [1e9], index=idx)
    s.iloc[:39] = np.linspace(0.9, 1.1, 39)  # nonzero std
    z = pit_zscore(s, min_periods=12)
    assert z.iloc[-1] == pytest.approx(4.0)


# ── PIT composite ─────────────────────────────────────────────────────────────

def _z_panel():
    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    return pd.DataFrame({
        "us.growth.a": [1.0, 1.0, 1.0, np.nan],
        "us.growth.b": [1.0, -1.0, np.nan, np.nan],
        "us.growth.c": [0.0, 0.0, 0.0, 0.0],
        "us.growth.d": [2.0, 2.0, 2.0, 2.0],
    }, index=idx)


_CFG = [
    {"id": "growth.a", "base_share": 1.0, "importance": 1.0, "quality_factor": 1.0},
    {"id": "growth.b", "base_share": 1.0, "importance": 1.0, "quality_factor": 1.0,
     "invert": True},
    {"id": "growth.c", "base_share": 1.0, "importance": 1.0, "quality_factor": 1.0},
    {"id": "growth.d", "base_share": 1.0, "importance": 1.0, "quality_factor": 1.0},
]


def test_pit_composite_inverts_and_averages():
    score = pit_composite(_z_panel(), _CFG, "us", min_signals=3)
    # Month 1: equal weights, z = [1, -(1), 0, 2] → mean = 0.5
    assert score.iloc[0] == pytest.approx(0.5)
    # Month 2: z = [1, -(-1)=+1, 0, 2] → mean = 1.0
    assert score.iloc[1] == pytest.approx(1.0)


def test_pit_composite_renormalizes_on_missing():
    score = pit_composite(_z_panel(), _CFG, "us", min_signals=3)
    # Month 3: b missing → mean of [1, 0, 2] over 3 active weights = 1.0
    assert score.iloc[2] == pytest.approx(1.0)


def test_pit_composite_min_signals_gate():
    score = pit_composite(_z_panel(), _CFG, "us", min_signals=3)
    # Month 4: only c and d present (2 < 3) → NaN
    assert pd.isna(score.iloc[3])


# ── G2: scenario scoring ──────────────────────────────────────────────────────

def _chips(labels: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2020-01-31", periods=len(labels), freq="ME")
    return pd.DataFrame({"growth_chip": labels,
                         "inflation_chip": ["Transition"] * len(labels)}, index=idx)


def test_score_scenario_math():
    chips = _chips(["Retraction", "Retraction", "Transition", "Growth"])
    s = Scenario("test", "2020-01-01", "2020-04-30", "growth",
                 "Retraction", frozenset({"Retraction", "Transition"}))
    r = score_scenario(chips, s)
    assert r["months"] == 4
    assert r["strict_hit"] == pytest.approx(0.5)
    assert r["acceptable_hit"] == pytest.approx(0.75)
    assert r["wrong_direction"] == pytest.approx(0.25)


def test_score_scenario_window_bounds():
    chips = _chips(["Growth"] * 6)
    s = Scenario("test", "2020-02-01", "2020-04-30", "growth",
                 "Growth", frozenset({"Growth"}))
    assert score_scenario(chips, s)["months"] == 3  # Feb, Mar, Apr month-ends


def test_scenario_wrong_direction_property():
    s = Scenario("x", "2020-01-01", "2020-02-01", "inflation",
                 "Inflation", frozenset({"Inflation"}))
    assert s.wrong == "Disinflation"
    s2 = Scenario("y", "2020-01-01", "2020-02-01", "growth",
                  "Retraction", frozenset({"Retraction"}))
    assert s2.wrong == "Growth"

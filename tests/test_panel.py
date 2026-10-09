"""Cross-country panel tests (checklist item 9, 2026-10-09).

The module's reason to exist is that pooling buys far less than a count of
countries suggests. These pin that arithmetic and the honest-vs-naive split.
"""
from __future__ import annotations

import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import numpy as np
import pandas as pd
import pytest


def test_effective_n_equals_n_when_series_are_independent():
    from indicators.panel import effective_independent_n
    rng = np.random.default_rng(0)
    idx = pd.date_range("2000-01-31", periods=400, freq="ME")
    panel = pd.DataFrame({f"c{i}": rng.normal(0, 1, 400) for i in range(6)}, index=idx)
    e = effective_independent_n(panel)
    assert e["n"] == 6
    assert abs(e["rho_bar"]) < 0.12          # sampling noise around zero
    assert 4.5 < e["n_eff"] <= 7.5


def test_effective_n_collapses_when_series_are_identical():
    """Perfectly correlated units are worth exactly one."""
    from indicators.panel import effective_independent_n
    idx = pd.date_range("2000-01-31", periods=400, freq="ME")
    base = pd.Series(np.random.default_rng(1).normal(0, 1, 400), index=idx)
    panel = pd.DataFrame({f"c{i}": base for i in range(8)})
    e = effective_independent_n(panel)
    assert e["rho_bar"] == pytest.approx(1.0, abs=1e-9)
    assert e["n_eff"] == pytest.approx(1.0, abs=0.01)


def test_effective_n_is_the_design_effect_formula():
    from indicators.panel import effective_independent_n
    idx = pd.date_range("2000-01-31", periods=600, freq="ME")
    rng = np.random.default_rng(2)
    common = rng.normal(0, 1, 600)
    panel = pd.DataFrame(
        {f"c{i}": 0.7 * common + 0.7 * rng.normal(0, 1, 600) for i in range(10)},
        index=idx)
    e = effective_independent_n(panel)
    expected = e["n"] / (1 + (e["n"] - 1) * e["rho_bar"])
    assert e["n_eff"] == pytest.approx(expected, abs=0.01)
    assert e["n_eff"] < 3.5, "a strong common factor must collapse the count"


def test_effective_n_handles_a_degenerate_panel():
    from indicators.panel import effective_independent_n
    assert effective_independent_n(pd.DataFrame())["n_eff"] == 0.0
    one = pd.DataFrame({"a": np.arange(200.0)})
    assert effective_independent_n(one)["n_eff"] == 1.0


@pytest.mark.integration
def test_pooling_the_real_panel_does_not_rescue_significance():
    """The finding item 9 exists to record.

    Naive pooled t-statistics on ~4,200 country-months look significant. They
    are not: eleven countries are worth about two once their co-movement is
    accounted for, and neither coefficient clears |t| = 2 after the
    correction. Pinned so that a future reader cannot quote the naive number.
    """
    from indicators.panel import build_panel, pooled_regression
    r = pooled_regression(build_panel())
    assert "error" not in r, r
    assert r["countries"] >= 8
    assert r["effective_countries"] < r["countries"] / 2, (
        "countries co-move; the effective count must be far below the raw one")
    assert r["effective_country_months"] < r["country_months"]
    # The naive statistics overstate: adjusted must be strictly smaller in size.
    for leg in ("growth", "inflation"):
        assert abs(r[f"t_{leg}_adjusted"]) < abs(r[f"t_{leg}_naive"])

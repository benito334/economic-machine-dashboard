"""Tests for the cross-country relative-cycle view (roadmap Phase E)."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import numpy as np
import pandas as pd
import pytest
from dash import html

from dashboard import relative_view as rv


def _hist(dates, values, col="growth_score"):
    return pd.DataFrame({"as_of": pd.to_datetime(dates), col: values})


# ── Correlation math ──────────────────────────────────────────────────────────

def test_identical_series_correlate_at_one():
    dates = pd.date_range("2015-01-31", periods=60, freq="ME")
    vals = np.sin(np.arange(60) / 5)
    h = {"A": _hist(dates, vals), "B": _hist(dates, vals)}
    corr = rv.compute_score_correlations(h, "growth_score")
    assert corr.loc["A", "B"] == pytest.approx(1.0)


def test_inverted_series_correlate_at_minus_one():
    dates = pd.date_range("2015-01-31", periods=60, freq="ME")
    vals = np.sin(np.arange(60) / 5)
    h = {"A": _hist(dates, vals), "B": _hist(dates, -vals)}
    corr = rv.compute_score_correlations(h, "growth_score")
    assert corr.loc["A", "B"] == pytest.approx(-1.0)


def test_short_overlap_returns_nan():
    """Fewer than 24 common months → NaN, not a spurious correlation."""
    d1 = pd.date_range("2015-01-31", periods=60, freq="ME")
    d2 = pd.date_range("2019-10-31", periods=10, freq="ME")   # 10-month overlap
    h = {"A": _hist(d1, np.arange(60.0)), "B": _hist(d2, np.arange(10.0))}
    corr = rv.compute_score_correlations(h, "growth_score")
    assert np.isnan(corr.loc["A", "B"])


def test_start_filter_limits_window():
    dates = pd.date_range("2010-01-31", periods=120, freq="ME")
    rng = np.random.RandomState(7)
    a = rng.randn(120)
    b = a.copy()
    b[:60] = -a[:60]           # anti-correlated first half, identical second half
    h = {"A": _hist(dates, a), "B": _hist(dates, b)}
    recent = rv.compute_score_correlations(h, "growth_score", start=dates[60])
    assert recent.loc["A", "B"] == pytest.approx(1.0)


def test_misaligned_day_of_month_still_aligns():
    """US composites land on the 5th, KR on month-end — period alignment must join them."""
    d1 = pd.date_range("2015-01-31", periods=36, freq="ME")
    d2 = d1 - pd.Timedelta(days=26)     # same months, different days
    vals = np.cos(np.arange(36) / 3)
    h = {"A": _hist(d1, vals), "B": _hist(d2, vals)}
    corr = rv.compute_score_correlations(h, "growth_score")
    assert corr.loc["A", "B"] == pytest.approx(1.0)


# ── Rendering (integration against live DB) ───────────────────────────────────

def test_layout_returns_div():
    lay = rv.get_layout()
    assert isinstance(lay, html.Div)
    assert "relative-content" in str(lay)


def test_render_full_page():
    out = rv.render_relative_view({"page": "/relative"}, "carbon", None)
    s = str(out)
    for cc_name in ("United States", "Euro Area", "South Korea"):
        assert cc_name in s
    assert "Growth ·" in s and "Inflation ·" in s     # regime chips
    assert "diversification" in s                     # correlation section


def test_render_skips_other_pages():
    from dash import no_update
    assert rv.render_relative_view({"page": "/charts"}, "carbon", None) is no_update


def test_route_registered():
    import dashboard.charting as charting
    assert charting._PAGE_MAP["/relative"] is charting._page_relative_view

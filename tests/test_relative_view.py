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


# ── Relative ULC competitiveness table (Ray Dalio consult, 2026-08-19) ───────

def test_competitiveness_table_ranks_and_documents_gap():
    """Live regression: countries with a growth.relative_ulc signal appear,
    sorted most-improving (lowest Z) first, and CN/IN/BR/ID are explicitly
    called out as missing rather than silently dropped."""
    out = rv._competitiveness_table({})
    s = str(out)
    for cc_name in ("United States", "South Korea", "Germany"):
        assert cc_name in s
    assert "No free REER unit-labor-cost series" in s
    for missing in ("China", "India", "Brazil", "Indonesia"):
        assert missing in s


def test_render_full_page_includes_competitiveness_section():
    out = rv.render_relative_view({"page": "/relative"}, "carbon", None)
    s = str(out)
    assert "Relative competitiveness" in s
    # rendered lowercase, uppercased only via CSS textTransform
    assert "gaining" in s or "losing" in s or "flat" in s


# ── Clock-change notes (2026-07-30) ──────────────────────────────────────────

def test_label_run_start_detects_flip():
    import pandas as pd
    from dashboard.relative_view import _label_run_start
    ts = pd.Timestamp
    labels = [(ts("2026-04-30"), "Growth"), (ts("2026-05-31"), "Growth"),
              (ts("2026-06-30"), "Transition"), (ts("2026-07-18"), "Transition")]
    cur, prev, started = _label_run_start(labels)
    assert cur == "Transition" and prev == "Growth"
    assert started == ts("2026-06-30")   # first snapshot with the current label


def test_label_run_start_no_change_in_window():
    import pandas as pd
    from dashboard.relative_view import _label_run_start
    labels = [(pd.Timestamp("2026-05-31"), "Growth"), (pd.Timestamp("2026-06-30"), "Growth")]
    cur, prev, started = _label_run_start(labels)
    assert cur == "Growth" and prev is None


def test_recent_change_notes_windows():
    import pandas as pd
    from dashboard.relative_view import _recent_change_notes
    now = pd.Timestamp("2026-07-30")
    ts = pd.Timestamp
    fresh_flip = [(ts("2026-06-01"), "Growth"), (ts("2026-07-15"), "Retraction")]
    old_flip = [(ts("2026-03-01"), "Inflation"), (ts("2026-04-01"), "Disinflation"),
                (ts("2026-05-01"), "Disinflation")]
    stage_flip = [(ts("2026-03-31"), "reflation"), (ts("2026-06-30"), "squeeze")]
    notes = _recent_change_notes(fresh_flip, old_flip, stage_flip, now=now)
    # Growth flipped 15 days ago → shown; Inflation flipped ~3 months ago → hidden;
    # stage flipped 30 days ago → within the 45-day quarterly window → shown.
    assert len(notes) == 2
    assert any("Growth clock → Retraction (was Growth)" in n for n in notes)
    assert any("Stage clock → squeeze (was reflation)" in n for n in notes)


def test_recent_change_notes_empty_inputs():
    from dashboard.relative_view import _recent_change_notes
    assert _recent_change_notes([], [], []) == []

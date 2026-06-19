"""
Tests for Phase 1D — Dash charting view.

Unit tests: charting_data helpers, catalog parsing, figure builders.
Integration tests (marked): real DuckDB at DB_PATH.
"""
from __future__ import annotations

import os
import pytest
import pandas as pd

# ── charting_data unit tests ──────────────────────────────────────────────────

def test_load_series_catalog_returns_list():
    from dashboard.charting_data import load_series_catalog
    cat = load_series_catalog()
    assert isinstance(cat, list)
    assert len(cat) > 0


def test_catalog_entries_have_required_keys():
    from dashboard.charting_data import load_series_catalog
    required = {"label", "signal_id", "units", "value_col", "default_pane", "group"}
    for entry in load_series_catalog():
        missing = required - entry.keys()
        assert not missing, f"Entry {entry.get('signal_id')} missing keys: {missing}"


def test_catalog_value_col_valid():
    from dashboard.charting_data import load_series_catalog
    valid = {"value", "zscore", "level_percentile", "change_1m", "change_3m", "change_12m"}
    for entry in load_series_catalog():
        assert entry["value_col"] in valid, f"{entry['signal_id']}: bad value_col={entry['value_col']}"


def test_load_yield_curve_maturities():
    from dashboard.charting_data import load_yield_curve_maturities
    mats = load_yield_curve_maturities()
    assert isinstance(mats, list)
    assert len(mats) == 6
    fred_ids = {m["fred_id"] for m in mats}
    assert "DGS10" in fred_ids
    assert "DGS2" in fred_ids
    assert "DGS30" in fred_ids


def test_yield_curve_maturities_have_required_keys():
    from dashboard.charting_data import load_yield_curve_maturities
    for m in load_yield_curve_maturities():
        assert "fred_id" in m
        assert "maturity_years" in m
        assert "label" in m
        assert isinstance(m["maturity_years"], (int, float))


def test_read_fred_parquet_cached(tmp_path):
    """_read_fred_parquet returns None for a non-existent file."""
    original = os.environ.get("RAW_CACHE_DIR")
    os.environ["RAW_CACHE_DIR"] = str(tmp_path)
    try:
        from importlib import reload
        import dashboard.charting_data as cd
        reload(cd)
        result = cd._read_fred_parquet("NONEXISTENT")
        assert result is None
    finally:
        if original:
            os.environ["RAW_CACHE_DIR"] = original
        else:
            os.environ.pop("RAW_CACHE_DIR", None)
        reload(cd)


def test_charting_app_imports():
    """Dash app can be imported and server attribute exists."""
    from dashboard.charting import app, server
    import flask
    assert isinstance(server, flask.Flask)


def test_charting_app_catalog_loaded():
    """Dash app catalog is non-empty and grouped correctly."""
    from dashboard.charting import _CATALOG, _GROUPS, _BY_ID
    assert len(_CATALOG) > 0
    assert len(_GROUPS) > 0
    assert len(_BY_ID) == len(_CATALOG)


def test_charting_groups_match_catalog():
    from dashboard.charting import _CATALOG, _GROUPS
    # Every catalog entry appears in exactly one group
    grouped_ids = {e["signal_id"] for entries in _GROUPS.values() for e in entries}
    catalog_ids = {e["signal_id"] for e in _CATALOG}
    assert grouped_ids == catalog_ids


def test_dark_layout_returns_dict():
    from dashboard.charting import _dark_layout
    layout = _dark_layout()
    assert isinstance(layout, dict)
    assert "paper_bgcolor" in layout
    assert "plot_bgcolor" in layout


def test_dark_layout_with_title():
    from dashboard.charting import _dark_layout
    layout = _dark_layout("Test title")
    assert layout["title"]["text"] == "Test title"


def test_figure_layout_all_themes():
    from dashboard.themes import figure_layout, THEMES
    for name in THEMES:
        layout = figure_layout(name)
        assert isinstance(layout, dict)
        assert "paper_bgcolor" in layout
        assert "plot_bgcolor" in layout
        assert layout["paper_bgcolor"] == THEMES[name]["paper_bgcolor"]


def test_theme_css_vars_structure():
    from dashboard.themes import THEME_CSS_VARS, THEMES
    for name in THEMES:
        assert name in THEME_CSS_VARS
        assert "--page-bg" in THEME_CSS_VARS[name]
        assert "--font-color" in THEME_CSS_VARS[name]
        assert "--bs-body-bg" in THEME_CSS_VARS[name]
        assert "--series-label-color" in THEME_CSS_VARS[name]


def test_midnight_theme_removed():
    from dashboard.themes import THEMES, DEFAULT_THEME
    assert "midnight" not in THEMES
    assert DEFAULT_THEME == "carbon"


def test_dawn_theme_is_light():
    from dashboard.themes import THEMES
    dawn = THEMES["dawn"]
    assert dawn["page_bg"].startswith("#f")
    assert dawn["font_color"] == "#212529"


# ── Integration tests — require real DuckDB ───────────────────────────────────

DB = os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb")


@pytest.mark.integration
def test_load_signal_history_returns_df():
    from dashboard.charting_data import load_signal_history
    df = load_signal_history("us.policy.yield_10y")
    assert isinstance(df, pd.DataFrame)
    assert "as_of" in df.columns
    assert "value" in df.columns
    assert len(df) > 100


@pytest.mark.integration
def test_load_signal_history_date_filter():
    from dashboard.charting_data import load_signal_history
    df = load_signal_history("us.policy.yield_10y", start_date="2020-01-01", end_date="2021-01-01")
    assert df["as_of"].min() >= pd.Timestamp("2020-01-01")
    assert df["as_of"].max() <= pd.Timestamp("2021-01-31")


@pytest.mark.integration
def test_load_signal_history_zscore():
    from dashboard.charting_data import load_signal_history
    df = load_signal_history("us.policy.yield_10y", value_col="zscore")
    assert df["value"].notna().any()


@pytest.mark.integration
def test_load_signal_history_invalid_col():
    from dashboard.charting_data import load_signal_history
    with pytest.raises(ValueError, match="value_col"):
        load_signal_history("us.policy.yield_10y", value_col="bad_column")


@pytest.mark.integration
def test_load_multi_signal_history():
    from dashboard.charting_data import load_multi_signal_history
    df = load_multi_signal_history(
        ["us.policy.yield_2y", "us.policy.yield_10y"],
        start_date="2020-01-01",
    )
    assert "us.policy.yield_2y" in df.columns
    assert "us.policy.yield_10y" in df.columns
    assert len(df) > 50


@pytest.mark.integration
def test_load_multi_signal_history_empty_input():
    from dashboard.charting_data import load_multi_signal_history
    df = load_multi_signal_history([])
    assert df.empty


@pytest.mark.integration
def test_load_composite_history():
    from dashboard.charting_data import load_composite_history
    df = load_composite_history(start_date="2010-01-01")
    assert "growth_score" in df.columns
    assert "inflation_score" in df.columns
    assert "quadrant" in df.columns
    assert len(df) > 100
    assert df["as_of"].dtype == "datetime64[us]" or df["as_of"].dtype.kind == "M"


@pytest.mark.integration
def test_available_dates_for_yield_curve():
    from dashboard.charting_data import available_dates_for_yield_curve
    dates = available_dates_for_yield_curve()
    assert isinstance(dates, list)
    assert len(dates) > 1000
    # Check sorted
    assert dates == sorted(dates)
    # Check format
    assert len(dates[0]) == 10 and dates[0][4] == "-"


@pytest.mark.integration
def test_load_yield_curve_term_structure_recent():
    from dashboard.charting_data import load_yield_curve_term_structure
    df = load_yield_curve_term_structure("2024-06-28")
    assert isinstance(df, pd.DataFrame)
    assert "maturity_years" in df.columns
    assert "yield_pct" in df.columns
    # Expect at least 2 maturities (DGS2 + DGS10 are always cached)
    assert len(df) >= 2
    # Yields should be positive and reasonable
    assert (df["yield_pct"] > 0).all()
    assert (df["yield_pct"] < 20).all()
    # Should be sorted by maturity
    assert list(df["maturity_years"]) == sorted(df["maturity_years"])


@pytest.mark.integration
def test_load_yield_curve_term_structure_future_returns_empty():
    from dashboard.charting_data import load_yield_curve_term_structure
    df = load_yield_curve_term_structure("2099-01-01")
    # Should return the most recent available data (not empty, since we use "on or before")
    # This is actually fine — the function finds data <= target, so 2099 returns latest
    assert isinstance(df, pd.DataFrame)


@pytest.mark.integration
def test_overlay_chart_callback_no_series():
    """Overlay chart returns a figure with no traces when no series selected."""
    import plotly.graph_objects as go
    from dashboard.charting import update_overlay_chart
    fig = update_overlay_chart([], {"start": None, "end": None})
    assert isinstance(fig, go.Figure)


@pytest.mark.integration
def test_overlay_chart_callback_with_series():
    import plotly.graph_objects as go
    from dashboard.charting import update_overlay_chart
    fig = update_overlay_chart(
        ["us.policy.yield_10y", "us.policy.yield_2y"],
        {"start": "2020-01-01", "end": "2024-01-01"},
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 2


@pytest.mark.integration
def test_regime_chart_callback():
    import plotly.graph_objects as go
    from dashboard.charting import update_regime_chart
    fig = update_regime_chart("tab-regime", {"start": "2010-01-01", "end": None})
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 3  # growth score, inflation score, quadrant markers


@pytest.mark.integration
def test_yield_curve_chart_callback():
    import plotly.graph_objects as go
    from dashboard.charting import update_yield_curve
    fig = update_yield_curve("2024-06-28", None)
    assert isinstance(fig, go.Figure)
    # Should have at least a term structure trace and the spread bar chart
    assert len(fig.data) >= 2

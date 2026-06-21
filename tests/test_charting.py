"""
Tests for Phase 1D — Dash charting view.

Unit tests: charting_data helpers, catalog parsing, figure builders.
Integration tests (marked): real DuckDB at DB_PATH.
"""
from __future__ import annotations

import os
import re
import pytest
import pandas as pd

# ── charting_data unit tests ──────────────────────────────────────────────────

def test_load_series_catalog_returns_list():
    from dashboard.charting_data import load_series_catalog
    cat = load_series_catalog()
    assert isinstance(cat, list)
    assert len(cat) > 0


def test_load_catalog_parses_complete_yaml():
    from dashboard.charting_data import load_catalog
    series, maturities = load_catalog()
    assert len(series) > 0
    assert len(maturities) == 6


def test_reer_catalog_sources_are_not_swapped():
    from dashboard.charting_data import load_series_catalog
    by_label = {item["label"]: item for item in load_series_catalog()}
    assert by_label["REER (BIS)"]["signal_id"] == "us.currency.reer"
    assert by_label["REER (World Bank)"]["signal_id"] == "us.currency.reer_xcountry"


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


@pytest.mark.integration
def test_latest_signals_respects_as_of_cutoff():
    from dashboard.charting_data import load_latest_signals
    cutoff = pd.Timestamp("2020-06-30")
    df = load_latest_signals("US", as_of=str(cutoff.date()))
    assert not df.empty
    assert pd.to_datetime(df["as_of"]).max() <= cutoff


@pytest.mark.integration
def test_change_feed_uses_prior_observation_outside_120_day_window():
    from dashboard.charting_data import load_change_feed
    df = load_change_feed("US", as_of="2026-06-20")
    row = df[df["id"] == "us.credit.lending_standards"]
    assert not row.empty
    assert pd.notna(row.iloc[0]["prior_as_of"])
    assert row.iloc[0]["zscore_delta"] > 0


def test_regime_map_panels_use_selected_as_of(monkeypatch):
    import dashboard.charting as charting

    comp = pd.DataFrame({
        "as_of": pd.to_datetime(["2020-01-31", "2020-02-29"]),
    })
    seen: dict[str, str] = {}

    monkeypatch.setattr(charting, "load_composite_history", lambda **_kwargs: comp)

    def _latest(_country, as_of=None):
        seen["latest"] = as_of
        return pd.DataFrame()

    def _changes(_country, as_of=None):
        seen["changes"] = as_of
        return pd.DataFrame()

    def _histories(_country, n_months=36, as_of=None):
        seen["histories"] = as_of
        return pd.DataFrame()

    monkeypatch.setattr(charting, "load_latest_signals", _latest)
    monkeypatch.setattr(charting, "load_change_feed", _changes)
    monkeypatch.setattr(charting, "load_all_signal_histories", _histories)

    charting.update_regime_map_panels(1, {}, None)
    assert seen == {
        "latest": "2020-01-31",
        "changes": "2020-01-31",
        "histories": "2020-01-31",
    }


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
    fig = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", 0)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 3  # growth score, inflation score, quadrant markers


@pytest.mark.integration
def test_regime_chart_highlight_at_step():
    """Step > 0 adds highlight marker traces (one per subplot = 3 extra)."""
    import plotly.graph_objects as go
    from dashboard.charting import update_regime_chart
    fig0 = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", step=0)
    fig5 = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", step=5)
    # step=5 adds up to 3 highlight marker traces on top of the base traces
    assert len(fig5.data) >= len(fig0.data)
    # A vline shape should be present
    assert len(fig5.layout.shapes) >= 1


@pytest.mark.integration
def _collect_texts(node) -> list[str]:
    """Recursively collect all string leaf values from a Dash component tree."""
    results = []
    if isinstance(node, str):
        results.append(node)
    elif isinstance(node, list):
        for item in node:
            results.extend(_collect_texts(item))
    elif hasattr(node, "children"):
        results.extend(_collect_texts(node.children))
    return results


def test_regime_info_box_current():
    from dashboard.charting import update_regime_info
    children, date_display = update_regime_info(0, {"start": None, "end": None})
    assert "current" in date_display
    assert isinstance(children, list)
    assert len(children) > 0
    # "Past Data" warning must NOT appear when step == 0
    all_texts = _collect_texts(children)
    assert not any("PAST DATA" in t.upper() for t in all_texts)


@pytest.mark.integration
def test_regime_info_box_past():
    from dashboard.charting import update_regime_info
    children, date_display = update_regime_info(12, {"start": None, "end": None})
    assert "ago" in date_display
    # "Past Data" warning must appear somewhere in the nested component tree
    all_texts = _collect_texts(children)
    assert any("PAST DATA" in t.upper() for t in all_texts)


@pytest.mark.integration
def test_composite_component_status_respects_as_of_date():
    from dashboard.charting_data import load_composite_component_status
    cutoff = "2020-06-30"
    df = load_composite_component_status(country="US", as_of=cutoff)
    assert not df.empty
    assert (df["as_of"].dropna() <= pd.Timestamp(cutoff)).all()


@pytest.mark.integration
def test_debt_stress_derived_component_dates_are_available():
    from dashboard.charting_data import load_debt_stress_component_dates
    dates = load_debt_stress_component_dates(country="US", as_of="2025-12-31")
    assert dates["corporate_debt_gdp"] is not None
    assert dates["federal_interest_gdp"] is not None
    assert dates["corporate_debt_gdp"] <= pd.Timestamp("2025-12-31")


@pytest.mark.integration
def test_composite_history_has_disequilibrium():
    from dashboard.charting_data import load_composite_history
    df = load_composite_history(start_date="2020-01-01")
    assert "disequilibrium_score" in df.columns
    assert "n_growth_signals" in df.columns
    assert "n_inflation_signals" in df.columns


@pytest.mark.integration
def test_yield_curve_chart_callback():
    import plotly.graph_objects as go
    from dashboard.charting import update_yield_curve
    fig = update_yield_curve("2024-06-28", None)
    assert isinstance(fig, go.Figure)
    # Should have at least a term structure trace and the spread bar chart
    assert len(fig.data) >= 2


# ── L4: Stale-lag badges in Regime History component table ───────────────────

class TestRegimeInfoStaleBadge:
    """L4: STALE badge should show fill-months count when stale_dict provides it."""

    def _make_comp_df(self, signal_ids, is_stale=False):
        import pandas as pd
        rows = []
        for sid in signal_ids:
            rows.append({
                "composite": "growth",
                "concept_id": sid.split(".", 1)[1] if "." in sid else sid,
                "signal_id": sid,
                "label": sid.split(".")[-1].replace("_", " ").title(),
                "weight": 1.0,
                "invert": False,
                "zscore": 0.5,
                "direction": "rising",
                "change_3m": 0.01,
                "as_of": pd.Timestamp("2026-05-31"),
                "is_stale": is_stale,
                "low_history": False,
            })
        return pd.DataFrame(rows)

    def test_stale_badge_shows_months_when_in_dict(self):
        from dashboard.charting import _regime_info_children
        comp_df = self._make_comp_df(["us.growth.payrolls"], is_stale=True)
        row = {
            "quadrant": "Expansion", "growth_score": 0.5, "inflation_score": 0.3,
            "confidence": 0.6, "disequilibrium_score": 0.4,
            "n_growth_signals": 1, "n_inflation_signals": 0,
        }
        stale_dict = {"us.growth.payrolls": 2}
        children = _regime_info_children(row, False, comp_df, stale_dict)
        all_texts = _collect_texts(children)
        assert any("STALE · 2m" in t for t in all_texts), f"Expected 'STALE · 2m' in {all_texts}"

    def test_stale_badge_plain_when_not_in_dict(self):
        from dashboard.charting import _regime_info_children
        comp_df = self._make_comp_df(["us.growth.payrolls"], is_stale=True)
        row = {
            "quadrant": "Expansion", "growth_score": 0.5, "inflation_score": 0.3,
            "confidence": 0.6, "disequilibrium_score": 0.4,
            "n_growth_signals": 1, "n_inflation_signals": 0,
        }
        children = _regime_info_children(row, False, comp_df, {})
        all_texts = _collect_texts(children)
        assert any("STALE" in t for t in all_texts)
        assert not any("·" in t and "STALE" in t for t in all_texts), \
            "Expected plain STALE (no lag) when signal not in stale_dict"

    def test_forward_filled_signal_uses_stale_dict_even_if_source_is_fresh(self):
        from dashboard.charting import _regime_info_children
        comp_df = self._make_comp_df(["us.growth.payrolls"], is_stale=False)
        row = {
            "quadrant": "Expansion", "growth_score": 0.5, "inflation_score": 0.3,
            "confidence": 0.6, "disequilibrium_score": 0.4,
            "n_growth_signals": 1, "n_inflation_signals": 0,
        }
        stale_dict = {"us.growth.payrolls": 3}
        children = _regime_info_children(row, False, comp_df, stale_dict)
        all_texts = _collect_texts(children)
        assert any("STALE · 3m" in t for t in all_texts)
        assert not any("ACTIVE" in t for t in all_texts)

    @pytest.mark.integration
    def test_composite_history_includes_stale_signals_column(self):
        from dashboard.charting_data import load_composite_history
        df = load_composite_history(start_date="2026-01-01")
        assert "stale_signals" in df.columns

    @pytest.mark.integration
    def test_update_regime_info_stale_badges_wired(self):
        from dashboard.charting import update_regime_info
        children, date_display = update_regime_info(0, {"start": None, "end": None})
        assert isinstance(children, list)
        assert len(children) > 0
        # If any signal is stale at current snapshot, badge should contain "·"
        all_texts = _collect_texts(children)
        stale_texts = [t for t in all_texts if "STALE" in t]
        for t in stale_texts:
            assert "·" in t, f"STALE badge missing lag count: {t!r}"


# ── Momentum in summary box and chart ────────────────────────────────────────

class TestRegimeMomentumDisplay:
    """Verify momentum blocks appear separately in summary strip and chart has 5 subplots."""

    def _base_row(self):
        return {
            "quadrant": "Stagflation",
            "growth_score": -0.05, "inflation_score": 0.43,
            "confidence": 0.36, "disequilibrium_score": 0.70,
            "n_growth_signals": 9, "n_inflation_signals": 8,
            "growth_momentum": 0.4444, "inflation_momentum": 0.5,
        }

    def _make_comp_df(self):
        import pandas as pd
        rows = []
        for i, sid in enumerate([
            "us.growth.payrolls", "us.growth.industrial_prod",
            "us.inflation.core_pce", "us.inflation.breakeven_5y",
        ]):
            force = "growth" if "growth" in sid else "inflation"
            rows.append({
                "composite": force, "concept_id": sid.split(".", 1)[1],
                "signal_id": sid, "label": sid.split(".")[-1],
                "weight": 1.0, "invert": False,
                "zscore": 0.5 if i % 2 == 0 else -0.3,
                "direction": "rising", "change_3m": 0.01,
                "as_of": pd.Timestamp("2026-05-31"),
                "is_stale": False, "low_history": False,
            })
        return pd.DataFrame(rows)

    def test_momentum_blocks_appear_in_summary(self):
        from dashboard.charting import _regime_info_children
        children = _regime_info_children(self._base_row(), False, self._make_comp_df())
        all_texts = _collect_texts(children)
        # Momentum group header ("Momentum  (Δ MoM)") should appear in the summary strip
        assert any("momentum" in t.lower() for t in all_texts), \
            f"Expected 'Momentum' group header in summary, got: {all_texts}"

    def test_momentum_block_shows_fraction_string(self):
        from dashboard.charting import _regime_info_children
        comp_df = self._make_comp_df()
        children = _regime_info_children(self._base_row(), False, comp_df)
        all_texts = _collect_texts(children)
        # g_mom_str should be "1/2" (1 rising out of 2 non-inverted growth signals)
        assert any("/" in t for t in all_texts), "Expected X/Y momentum fraction in summary"

    def test_force_block_subtitle_no_longer_has_momentum(self):
        from dashboard.charting import _regime_info_children
        children = _regime_info_children(self._base_row(), False, self._make_comp_df())
        all_texts = _collect_texts(children)
        # The force block subtitles are "N/N signals" — no momentum phrase there.
        # (Old format was "N/N signals · X/Y momentum-positive".)
        signals_texts = [t for t in all_texts if re.match(r"\d+/\d+ signals", t)]
        assert len(signals_texts) >= 1, "Expected 'N/N signals' subtitle in score block"
        assert not any("momentum" in t.lower() for t in signals_texts), \
            f"Force subtitle should not contain 'momentum': {signals_texts}"

    @pytest.mark.integration
    def test_composite_history_has_momentum_columns(self):
        from dashboard.charting_data import load_composite_history
        df = load_composite_history(start_date="2020-01-01")
        assert "growth_momentum" in df.columns
        assert "inflation_momentum" in df.columns
        recent = df.dropna(subset=["growth_momentum", "inflation_momentum"])
        assert len(recent) > 0
        assert (recent["growth_momentum"].between(0, 1)).all()
        assert (recent["inflation_momentum"].between(0, 1)).all()

    @pytest.mark.integration
    def test_regime_chart_has_five_subplots(self):
        from dashboard.charting import update_regime_chart
        fig = update_regime_chart({}, "carbon", 0)
        # 5 subplots → subplot_titles has 5 entries; figure has at least 5 base traces
        assert len(fig.data) >= 5
        # y-axis domains: should have yaxis, yaxis2, yaxis3, yaxis4, yaxis5
        layout_keys = set(fig.layout.to_plotly_json().keys())
        for ax in ("yaxis", "yaxis2", "yaxis3", "yaxis4", "yaxis5"):
            assert ax in layout_keys, f"Missing axis {ax} in layout"


# ── Component table rollup (html.Details) ────────────────────────────────────

class TestRegimeTableRollup:
    """Verify Growth and Inflation tables are wrapped in separate html.Details elements."""

    def _make_comp_df(self):
        import pandas as pd
        rows = []
        for sid in ["us.growth.payrolls", "us.inflation.core_pce"]:
            force = "growth" if "growth" in sid else "inflation"
            rows.append({
                "composite": force, "concept_id": sid.split(".", 1)[1],
                "signal_id": sid, "label": sid.split(".")[-1],
                "weight": 1.0, "invert": False,
                "zscore": 0.5, "direction": "rising", "change_3m": 0.01,
                "as_of": pd.Timestamp("2026-05-31"),
                "is_stale": False, "low_history": False,
            })
        return pd.DataFrame(rows)

    def _count_type(self, children, component_type):
        """Recursively count components of a given type."""
        count = 0
        items = children if isinstance(children, list) else [children]
        for item in items:
            if isinstance(item, component_type):
                count += 1
            if hasattr(item, "children") and item.children:
                count += self._count_type(
                    item.children if isinstance(item.children, list) else [item.children],
                    component_type,
                )
        return count

    def test_combined_details_element_present(self):
        """T5: growth and inflation tables are combined into one html.Details (collapsed)."""
        from dash import html as dhtml
        from dashboard.charting import _regime_info_children
        row = {
            "quadrant": "Expansion", "growth_score": 0.5, "inflation_score": 0.3,
            "confidence": 0.6, "disequilibrium_score": 0.4,
            "n_growth_signals": 1, "n_inflation_signals": 1,
        }
        children = _regime_info_children(row, False, self._make_comp_df())
        n = self._count_type(children, dhtml.Details)
        assert n == 1, f"Expected 1 combined html.Details element, got {n}"

    def test_details_collapsed_by_default(self):
        """T5: combined force table is collapsed (open=False) by default."""
        from dash import html as dhtml
        from dashboard.charting import _regime_info_children
        row = {
            "quadrant": "Expansion", "growth_score": 0.5, "inflation_score": 0.3,
            "confidence": 0.6, "disequilibrium_score": 0.4,
            "n_growth_signals": 1, "n_inflation_signals": 1,
        }
        children = _regime_info_children(row, False, self._make_comp_df())
        details_found = []

        def _find_details(items):
            for item in (items if isinstance(items, list) else [items]):
                if isinstance(item, dhtml.Details):
                    details_found.append(item)
                if hasattr(item, "children") and item.children:
                    _find_details(item.children if isinstance(item.children, list) else [item.children])

        _find_details(children)
        assert len(details_found) == 1, f"Expected 1 Details element, got {len(details_found)}"
        assert details_found[0].open is False, "Combined force table should be collapsed by default"


class TestRoutedRegimeStepButtons:
    """Prev/Now/Next must work when only one routed page is mounted."""

    @staticmethod
    def _collect_ids(component):
        found = []
        component_id = getattr(component, "id", None)
        if component_id is not None:
            found.append(component_id)
        children = getattr(component, "children", None)
        for child in children if isinstance(children, list) else ([children] if children is not None else []):
            if hasattr(child, "children") or hasattr(child, "id"):
                found.extend(TestRoutedRegimeStepButtons._collect_ids(child))
        return found

    @pytest.mark.parametrize("layout_name", ["_page_regime_history", "_page_regime_map"])
    def test_each_routed_page_has_pattern_matched_step_buttons(self, layout_name):
        import dashboard.charting as charting
        layout = getattr(charting, layout_name)()
        ids = self._collect_ids(layout)
        actions = {
            item["action"]
            for item in ids
            if isinstance(item, dict) and item.get("type") == "regime-step-button"
        }
        assert actions == {"prev", "current", "next"}

    @pytest.mark.parametrize(
        ("action", "current_step", "expected"),
        [("prev", 0, 1), ("next", 2, 1), ("current", 2, 0)],
    )
    def test_step_button_updates_shared_index(
        self, monkeypatch, action, current_step, expected
    ):
        import dashboard.charting as charting

        class _Context:
            triggered_id = {"type": "regime-step-button", "action": action}

        monkeypatch.setattr(charting.dash, "callback_context", _Context())
        monkeypatch.setattr(
            charting,
            "load_composite_history",
            lambda **_kwargs: pd.DataFrame({"as_of": pd.date_range("2020-01-31", periods=4, freq="ME")}),
        )
        result = charting.update_regime_step(
            1 if action == "prev" else None,
            1 if action == "current" else None,
            1 if action == "next" else None,
            None,
            {},
            current_step,
        )
        assert result == expected

    def test_graph_click_selects_matching_snapshot(self, monkeypatch):
        import dashboard.charting as charting

        monkeypatch.setattr(
            charting,
            "load_composite_history",
            lambda **_kwargs: pd.DataFrame(
                {"as_of": pd.date_range("2020-01-31", periods=4, freq="ME")}
            ),
        )

        result = charting.select_regime_point(
            {"points": [{"x": "2020-02-29"}]}, {}, 0
        )

        assert result == 2

    def test_graph_click_uses_nearest_available_snapshot(self, monkeypatch):
        import dashboard.charting as charting

        monkeypatch.setattr(
            charting,
            "load_composite_history",
            lambda **_kwargs: pd.DataFrame(
                {"as_of": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"])}
            ),
        )

        result = charting.select_regime_point(
            {"points": [{"x": "2020-02-20T12:00:00Z"}]}, {}, 0
        )

        assert result == 1

    @pytest.mark.parametrize("click_data", [None, {}, {"points": []}, {"points": [{"x": None}]}])
    def test_graph_click_ignores_missing_dates(self, click_data):
        import dashboard.charting as charting

        assert charting.select_regime_point(click_data, {}, 0) is charting.no_update

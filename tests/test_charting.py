"""
Tests for Phase 1D — Dash charting view.

Unit tests: charting_data helpers, catalog parsing, figure builders.
Integration tests (marked): real DuckDB at DB_PATH.
"""
from __future__ import annotations

import os
import pathlib
import re
import pytest
import numpy as np
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


def test_formula_catalog_uses_live_composite_config():
    from indicators.composites import build_formula_catalog, load_composites_config

    config = load_composites_config()
    catalog = build_formula_catalog(config)
    by_title = {item["title"]: item for item in catalog}
    alpha = config["dynamic_weighting"]["momentum_alpha"]
    half_life = config["time_decay"]["half_life_months"]

    assert f"α = {alpha:g}" in by_title["Force/momentum weight tilt"]["parameters"]
    assert f"h = {half_life:g} months" in by_title["Observation-age decay"]["parameters"]
    assert "compute_composite_history" in by_title["Regime confidence"]["source"]


def test_overview_page_is_routed_and_renders_table():
    from dashboard.charting import _PAGE_MAP, route_page

    assert "/overview" in _PAGE_MAP
    layout, trigger = route_page("/overview")
    rendered = str(layout.to_plotly_json())
    assert "Global Overview" in rendered
    assert "ov-table" in rendered
    assert "Cycle Health" in rendered
    assert "Cycle Health Config" in rendered
    assert trigger == {"page": "/overview"}


def test_cycle_health_uses_real_growth_and_public_debt_drag():
    from dashboard.global_overview import _cycle_health

    country_data = {
        "master.gdp_real": (0.02, "2026-01"),
        "policy.fed_funds_target": (4.0, "2026-06"),
        "inflation.cpi_headline": (0.03, "2026-05"),
        "credit.gov_debt_gdp": (100.0, "2026-01"),
    }
    health = _cycle_health(country_data, {
        "threshold_mode": "fixed",
        "apply_freshness_decay": False,
    })

    assert health is not None
    assert health["growth_source"] == "real"
    assert health["simple"] == pytest.approx(-5.0)
    assert health["adjusted"] == pytest.approx(-4.5)
    assert health["debt_mode"] == "public-only"
    assert health["stage"] == "Late / Tight"


def test_cycle_health_uses_private_debt_when_available():
    from dashboard.global_overview import _cycle_health

    country_data = {
        "master.gdp_real": (0.02, "2026-01"),
        "policy.fed_funds_target": (4.0, "2026-06"),
        "inflation.cpi_headline": (0.03, "2026-05"),
        "credit.gov_debt_gdp": (70.0, "2026-01"),
        "credit.household_debt_gdp": (80.0, "2026-01"),
        "credit.corporate_debt_gdp": (120.0, "2026-01"),
    }
    health = _cycle_health(country_data, {
        "threshold_mode": "fixed",
        "apply_freshness_decay": False,
        "debt_targets": {"public": 70.0, "private": 90.0},
    })

    assert health is not None
    assert health["debt_mode"] == "public+private"
    assert health["private_debt_gap"] == pytest.approx(10.0)
    assert health["adjusted"] == pytest.approx(-2.0)


def test_conditional_chi_weights_tilts_toward_inflation_when_high():
    from dashboard.global_overview import _conditional_chi_weights, CYCLE_HEALTH_DEFAULT_CONFIG

    w = _conditional_chi_weights(CYCLE_HEALTH_DEFAULT_CONFIG["weights"], inflation_rate_ann=6.0, growth_rate_ann=2.0)
    assert w["inflation"] == pytest.approx(0.35)
    assert w["growth"] == pytest.approx(0.30)
    assert w["policy_rate"] == pytest.approx(0.30)


def test_conditional_chi_weights_tilts_toward_policy_rate_when_growth_low():
    from dashboard.global_overview import _conditional_chi_weights, CYCLE_HEALTH_DEFAULT_CONFIG

    w = _conditional_chi_weights(CYCLE_HEALTH_DEFAULT_CONFIG["weights"], inflation_rate_ann=2.0, growth_rate_ann=0.5)
    assert w["policy_rate"] == pytest.approx(0.35)
    assert w["inflation"] == pytest.approx(0.30)


def test_cycle_health_high_inflation_shifts_weight_onto_inflation_term():
    from dashboard.global_overview import _cycle_health

    country_data = {
        "master.gdp_real": (0.02, "2026-01"),
        "policy.fed_funds_target": (4.0, "2026-06"),
        "inflation.cpi_headline": (0.06, "2026-05"),  # 6% annual → triggers inflation tilt
        "credit.gov_debt_gdp": (70.0, "2026-01"),
    }
    health = _cycle_health(country_data, {
        "threshold_mode": "fixed",
        "apply_freshness_decay": False,
    })

    assert health is not None
    # adjusted = 0.30*2.0 - 0.30*4.0 - 0.35*6.0 - 0 (debt gap is 0 at target)
    assert health["adjusted"] == pytest.approx(0.30 * 2.0 - 0.30 * 4.0 - 0.35 * 6.0)


def test_cycle_health_real_policy_rate_toggle():
    from dashboard.global_overview import _cycle_health

    country_data = {
        "master.gdp_real": (0.02, "2026-01"),
        "policy.fed_funds_target": (4.0, "2026-06"),
        "inflation.cpi_headline": (0.03, "2026-05"),
        "credit.gov_debt_gdp": (70.0, "2026-01"),
    }
    health = _cycle_health(country_data, {
        "threshold_mode": "fixed",
        "apply_freshness_decay": False,
        "use_real_policy_rate": True,
    })

    assert health is not None
    # real policy rate = 4.0 - 3.0 = 1.0 → adjusted = 0.3*2.0 - 0.3*1.0 - 0.3*3.0 - 0
    assert health["adjusted"] == pytest.approx(0.3 * 2.0 - 0.3 * 1.0 - 0.3 * 3.0)


def test_cycle_health_clipboard_text_includes_configured_settings():
    from dashboard.global_overview import _cycle_config_clipboard_text

    text = _cycle_config_clipboard_text({
        "weights": {
            "growth": 0.4,
            "policy_rate": 0.2,
            "inflation": 0.3,
            "debt_gap": 0.1,
        },
        "debt_target_pct": 80.0,
        "positive_threshold": 0.75,
        "negative_threshold": -0.25,
    })

    assert "CHI_raw = Real GDP growth - Policy rate - Inflation" in text
    assert "Growth weight:      0.4" in text
    assert "Public debt target (% GDP):  80" in text
    assert "Fixed positive threshold: 0.75" in text
    assert "Fixed negative threshold: -0.25" in text


def test_methodology_page_documents_cycle_health_index():
    from dashboard.methodology import get_layout

    rendered = str(get_layout().to_plotly_json())
    assert "13 · Cycle Health Index" in rendered
    assert "CHI_raw = Real GDP growth - Policy rate - Inflation" in rendered
    assert "Debt-adjusted CHI" in rendered


def test_methodology_page_documents_2026_07_05_revisions():
    """Methodology page reflects the Ray Dalio review implementation and has a revision log."""
    from dashboard.methodology import get_layout

    rendered = str(get_layout().to_plotly_json())
    assert "15 · Revision Log" in rendered
    assert "dynamic-threshold algorithm" in rendered
    assert "Volatility basket" in rendered
    assert "Dynamic stock/flow weighting" in rendered
    assert "Conditional weighting & rate basis" in rendered
    assert "data_source_wishlist.md" in rendered
    assert "ray_dalio_review_log.md" in rendered


@pytest.mark.integration
def test_overview_drill_figure_builds_regular_metric_history():
    from dashboard.global_overview import _overview_drill_figure

    fig = _overview_drill_figure("us", "master.gdp_real")
    assert len(fig.data) == 1
    assert len(fig.data[0].x) > 0
    assert len(fig.data[0].y) > 0


@pytest.mark.integration
def test_overview_drill_figure_builds_cycle_health_history():
    from dashboard.global_overview import _overview_drill_figure

    fig = _overview_drill_figure("us", "chi_adjusted")
    assert len(fig.data) >= 1
    assert len(fig.data[0].x) > 0
    assert len(fig.data[0].y) > 0


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

DB = os.environ.get("DB_PATH", "/mnt/data/db/finance/indicators_machine/signals.duckdb")


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
    assert "weight_audit" in df.columns
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
# Regime History Phase 5 retrofit (2026-10-04): update_regime_chart now
# returns (band_fig, cards_children) — a compact categorical band figure
# plus a _section() of 6 _chart_cards (Growth Z/Momentum, Inflation
# Z/Momentum, Direction Agreement, Disequilibrium) — replacing the single
# 7-row make_subplots mega-figure, same pattern Phase 4 applied to the
# Signals force-detail pages. The cross-subplot shared-hover-line feature
# (tested below, pre-retrofit) is a deliberate, accepted tradeoff: each card
# now gets independent hover, consistent with every other chart-card page.
def test_regime_chart_callback():
    import plotly.graph_objects as go
    from dashboard.charting import update_regime_chart
    band_fig, cards = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", 0)
    assert isinstance(band_fig, go.Figure)
    assert len(band_fig.data) >= 2  # growth regime markers, inflation regime markers
    assert cards is not None


@pytest.mark.integration
def test_regime_chart_band_figure_is_compact_and_themed():
    from dashboard.charting import update_regime_chart

    band_fig, _ = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", 0)

    assert band_fig.layout.yaxis.range == (0, 1)
    assert band_fig.layout.yaxis.ticktext == ("Growth", "Inflation")


@pytest.mark.integration
def test_regime_chart_cards_cover_all_six_metrics():
    from dashboard.charting import update_regime_chart

    _, cards = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", 0)
    card_list = cards.children[2].children  # _section()'s card-row Div
    assert len(card_list) == 6


@pytest.mark.integration
def test_regime_chart_highlight_at_step():
    """Step > 0 moves the band figure's vline/highlight markers to a different
    date — same trace count either way (always 2 base + 2 highlight), but a
    vline shape must be present and its x position must track the step."""
    from dashboard.charting import update_regime_chart
    fig0, _ = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", step=0)
    fig5, _ = update_regime_chart({"start": "2010-01-01", "end": None}, "carbon", step=5)
    assert len(fig5.layout.shapes) >= 1
    assert len(fig0.data) == len(fig5.data)
    assert fig0.layout.shapes[0].x0 != fig5.layout.shapes[0].x0


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


def _walk(node):
    """Recursively yield every Dash component in a layout tree.

    Leaf components such as dcc.Graph declare no `children` prop, so the
    recursion is gated on Component-ness rather than on having children.
    """
    from dash.development.base_component import Component

    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    if not isinstance(node, Component):
        return
    yield node
    yield from _walk(getattr(node, "children", None))


@pytest.mark.integration
def test_term_structure_card_renders_the_curve():
    """The standalone Yield Curve page was retired 2026-10-06; its term-structure
    chart is now Fed Monitor's section-① card (latest observation, no date
    pickers). Guards the data path, which is what the old
    test_yield_curve_chart_callback actually covered."""
    from dashboard.fed_monitor import _term_structure_card

    card = _term_structure_card()
    graphs = [n for n in _walk(card) if type(n).__name__ == "Graph"]
    assert len(graphs) == 1
    fig = graphs[0].figure
    assert len(fig.data) == 1, "one trace: the maturity curve"
    # x is maturity, not a date — the whole reason this isn't a plain
    # _chart_card. Categorical (evenly spaced) so the short end, where
    # inversions show, isn't crushed into the left edge.
    assert fig.layout.xaxis.type == "category"
    xs = list(fig.data[0].x)
    assert xs[0].endswith("M") or xs[0].endswith("Y")
    assert xs[-1] == "30Y"
    assert len(xs) >= 4, "the curve needs enough points to have a shape"
    # A zero-anchored fill would flatten a 4-5% curve into a band — see the
    # comment in _term_structure_card.
    assert not fig.data[0].fill


@pytest.mark.integration
def test_retired_pages_still_route_to_fed_monitor():
    """/yield-curve and /central-bank were folded into Fed Monitor; both stay
    routed so existing links/bookmarks don't 404."""
    from dashboard.charting import _PAGE_MAP, _page_fed_monitor

    assert _PAGE_MAP["/yield-curve"] is _page_fed_monitor
    assert _PAGE_MAP["/central-bank"] is _page_fed_monitor


# ── L4: Stale-lag badges in Regime History component table ───────────────────

class TestRegimeInfoStaleBadge:
    """L4: only two badges — ACTIVE and STALE. STALE fires strictly off is_stale
    (past the expected update window); carry-forward age from stale_dict is
    informational "(#m)" text next to the decay %, shown under either badge."""

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
        assert any("STALE" in t for t in all_texts), f"Expected STALE badge in {all_texts}"
        assert any("(2m)" in t for t in all_texts), f"Expected carry-months detail in {all_texts}"

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

    def test_forward_filled_signal_within_window_reads_active_not_stale(self):
        """A signal that is NOT past its expected update window (is_stale=False)
        but is carried forward a few months (e.g. a quarterly release still
        inside its grace period) must badge ACTIVE, not STALE — the carry
        age is shown only as informational "(#m)" text, never as an alarm."""
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
        assert any("ACTIVE" in t for t in all_texts)
        assert any("(3m)" in t for t in all_texts), f"Expected carry-months detail in {all_texts}"
        assert not any("STALE" in t for t in all_texts)

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
            "growth_breadth": 0.4444, "inflation_breadth": 0.5,
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
        assert "growth_breadth" in df.columns
        assert "inflation_breadth" in df.columns
        recent = df.dropna(subset=["growth_breadth", "inflation_breadth"])
        assert len(recent) > 0
        assert (recent["growth_breadth"].between(0, 1)).all()
        assert (recent["inflation_breadth"].between(0, 1)).all()

    @pytest.mark.integration
    def test_regime_chart_returns_band_figure_and_six_cards(self):
        # Post Phase-5-retrofit shape: a compact band figure (no multi-row
        # subplot axes anymore) plus a _section() of 6 _chart_cards.
        from dashboard.charting import update_regime_chart
        band_fig, cards = update_regime_chart({}, "carbon", 0)
        layout_keys = set(band_fig.layout.to_plotly_json().keys())
        assert "yaxis2" not in layout_keys  # single-axis figure, not a 7-row subplot grid
        assert len(cards.children[2].children) == 6


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

    def test_details_can_be_rendered_open_after_date_change(self):
        from dash import html as dhtml
        from dashboard.charting import _regime_info_children

        row = {
            "quadrant": "Expansion", "growth_score": 0.5, "inflation_score": 0.3,
            "confidence": 0.6, "disequilibrium_score": 0.4,
            "n_growth_signals": 1, "n_inflation_signals": 1,
        }
        children = _regime_info_children(
            row, False, self._make_comp_df(), components_open=True
        )
        details_found = []

        def _find_details(items):
            for item in (items if isinstance(items, list) else [items]):
                if isinstance(item, dhtml.Details):
                    details_found.append(item)
                if hasattr(item, "children") and item.children:
                    _find_details(item.children if isinstance(item.children, list) else [item.children])

        _find_details(children)
        assert len(details_found) == 1
        assert details_found[0].id == "regime-components-details"
        assert details_found[0].open is True

    def test_details_open_state_has_clientside_persistence_callback(self):
        from dashboard.charting import app

        callbacks = [
            item for item in app._callback_list
            if item.get("output") == "regime-components-toggle-init.data"
        ]
        assert len(callbacks) == 1
        assert callbacks[0]["inputs"] == [
            {"id": "regime-info-box", "property": "children"}
        ]
        assert callbacks[0]["clientside_function"] is not None

    def test_force_table_mirrors_debt_stress_weight_audit_columns(self):
        from dashboard.charting import _regime_info_children

        row = {
            "quadrant": "Expansion", "growth_score": 0.5, "inflation_score": 0.3,
            "confidence": 0.6, "disequilibrium_score": 0.4,
            "n_growth_signals": 1, "n_inflation_signals": 1,
        }
        audit = {
            "growth": {
                "us.growth.payrolls": {
                    "importance": 0.9,
                    "config_weight": 0.1,
                    "effective_weight": 0.15,
                    "momentum_multiplier": 1.5,
                    "decay_fraction": 1.0,
                    "age_months": 0,
                    "missing": False,
                }
            }
        }
        children = _regime_info_children(
            row, False, self._make_comp_df(), weight_audit=audit
        )
        texts = _collect_texts(children)

        for header in ("Importance", "Config Wt", "Eff Wt", "Status / Detail"):
            assert header in texts
        assert "0.90" in texts
        assert "10.0%" in texts
        assert "15.0%" in texts
        assert "ACTIVE · BOOSTED" in texts
        assert any("momentum agreement 1.5×" in text for text in texts)


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
            # one ALL-wildcard input now, so the three buttons arrive as a list
            [1 if action == a else None for a in ("prev", "current", "next")],
            None,
            {},
            {},
            "US",
            current_step,
        )
        assert result == expected

    def test_step_button_bounds_use_selected_country_history(self, monkeypatch):
        import dashboard.charting as charting

        class _Context:
            triggered_id = {"type": "regime-step-button", "action": "prev"}

        def _history(**kwargs):
            periods = 2 if kwargs.get("country") == "KR" else 4
            return pd.DataFrame({
                "as_of": pd.date_range("2020-01-31", periods=periods, freq="ME")
            })

        monkeypatch.setattr(charting.dash, "callback_context", _Context())
        monkeypatch.setattr(charting, "load_composite_history", _history)

        result = charting.update_regime_step(
            [1, None, None],
            None,
            {},
            {},
            "KR",
            1,
        )

        assert result == 1

    @pytest.mark.parametrize("page,expected_reset", [
        ("/regime-map", True),
        ("/regime-history", True),
        ("/overview", False),
    ])
    def test_landing_on_regime_page_snaps_to_current(self, monkeypatch, page, expected_reset):
        # Navigation co-fires page-trigger with a phantom step-button re-mount; the page
        # reset must WIN so the walk features open on the most-current reading (step 0),
        # not a stale/leaked month. Regression for the "defaults to June" bug.
        import dashboard.charting as charting

        class _Context:
            triggered_id = {"type": "regime-step-button", "action": "prev"}  # phantom
            triggered = [
                {"prop_id": "page-trigger.data"},
                {"prop_id": '{"action":"prev","type":"regime-step-button"}.n_clicks'},
            ]

        monkeypatch.setattr(charting.dash, "callback_context", _Context())
        monkeypatch.setattr(
            charting, "load_composite_history",
            lambda **_k: pd.DataFrame({"as_of": pd.date_range("2020-01-31", periods=6, freq="ME")}),
        )
        result = charting.update_regime_step(
            [1, None, None], None, {}, {"page": page}, "US", 3,   # current_step=3 (walked back)
        )
        if expected_reset:
            assert result == 0            # snapped to current
        else:
            assert result != 0            # non-regime page → don't force-reset the index

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


# ── conc_adj capex-concentration multiplier (AI-capex panel 2026-10-04) ──────

class TestConcentrationMultiplier:
    """docs/ai_bubble_monitor_plan.md §6 — widens the GROWTH threshold only,
    off unless the caller supplies conc_share."""

    @staticmethod
    def _history(n=30):
        idx = pd.date_range("2020-01-31", periods=n, freq="ME")
        vals = [0.9, -0.9, 1.2, -1.2, 0.6] * (n // 5)
        return pd.DataFrame({
            "growth_score": vals, "inflation_score": vals,
            "credit_score": [0.0] * n,
        }, index=idx)

    @staticmethod
    def _share(index, pct):
        return pd.Series([pct] * len(index), index=index)

    def test_off_by_default(self):
        from dashboard.charting import compute_dynamic_thresholds

        comp = self._history()
        res = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5)
        assert (res["conc_adj"] == 1.0).all()

    def test_below_threshold_is_inert(self):
        from dashboard.charting import compute_dynamic_thresholds

        comp = self._history()
        res = compute_dynamic_thresholds(
            comp, base_gz=0.5, base_iz=0.5,
            conc_share=self._share(comp.index, 20.0))  # under the 25% cut-in
        assert (res["conc_adj"] == 1.0).all()

    def test_widens_growth_threshold_only(self):
        from dashboard.charting import compute_dynamic_thresholds

        comp = self._history()
        off = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5)
        on = compute_dynamic_thresholds(
            comp, base_gz=0.5, base_iz=0.5,
            conc_share=self._share(comp.index, 50.0))
        assert on["dyn_gz"].iloc[-1] > off["dyn_gz"].iloc[-1]
        # Inflation has no analogous concentration problem — must not move.
        assert on["dyn_iz"].iloc[-1] == pytest.approx(off["dyn_iz"].iloc[-1])

    def test_multiplier_magnitude_matches_the_documented_formula(self):
        from dashboard.charting import compute_dynamic_thresholds

        comp = self._history()
        # 34.2% share -> 1 + (0.342-0.25)/0.25*0.20 = 1.0736 (~7% widening,
        # the figure quoted in the plan and on the page).
        res = compute_dynamic_thresholds(
            comp, base_gz=0.5, base_iz=0.5,
            conc_share=self._share(comp.index, 34.2))
        assert res["conc_adj"].iloc[-1] == pytest.approx(1.0736, abs=1e-4)

    def test_aligns_on_as_of_column_not_positional_index(self):
        """_dyn_threshold_input keeps `as_of` as a COLUMN and leaves a
        RangeIndex behind. Reindexing a date-indexed share by that RangeIndex
        silently yields all-NaN and the multiplier dies quietly — a real bug
        caught by running it against live data, pinned here."""
        from dashboard.charting import compute_dynamic_thresholds

        comp = self._history().reset_index().rename(columns={"index": "as_of"})
        share = pd.Series([34.2] * 30,
                          index=pd.date_range("2020-01-31", periods=30, freq="ME"))
        res = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5,
                                         conc_share=share)
        assert res["conc_adj"].iloc[-1] == pytest.approx(1.0736, abs=1e-4)


# ── compute_dynamic_thresholds (Ray Dalio review 2026-07-05, #23) ─────────────

class TestComputeDynamicThresholds:
    @staticmethod
    def _flat_history(n=30, g=0.0, i=0.0, credit=0.0, freq="ME"):
        idx = pd.date_range("2020-01-31", periods=n, freq=freq)
        return pd.DataFrame({
            "growth_score": [g] * n,
            "inflation_score": [i] * n,
            "credit_score": [credit] * n,
        }, index=idx)

    def test_falls_back_to_base_thresholds_when_history_too_short(self):
        from dashboard.charting import compute_dynamic_thresholds

        comp = self._flat_history(n=4)  # well under the 8-period minimum
        result = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5)
        assert (result["dyn_gz"] == 0.5).all()
        assert (result["dyn_iz"] == 0.5).all()

    def test_credit_tightness_widens_inflation_threshold_only(self):
        from dashboard.charting import compute_dynamic_thresholds

        idx = pd.date_range("2020-01-31", periods=30, freq="ME")
        # Variability must be large enough that both thresholds clear the 0.15
        # floor added 2026-10-03 (Ray growth safeguard 2). With the old
        # near-flat series both cases floored to exactly 0.15 and the credit
        # multiplier was masked — see test_floor_masks_credit_multiplier below,
        # which pins that interaction deliberately.
        rng_vals = [0.9, -0.9, 1.2, -1.2, 0.6] * 6
        comp = pd.DataFrame({
            "growth_score": rng_vals,
            "inflation_score": rng_vals,
            "credit_score": [2.0] * 30,  # very healthy = very NOT tight (credit_z very negative)
        }, index=idx)
        loose = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5)

        comp_tight = comp.copy()
        comp_tight["credit_score"] = -2.0  # very unhealthy = tight (credit_z = 2.0 > hi=1.5)
        tight = compute_dynamic_thresholds(comp_tight, base_gz=0.5, base_iz=0.5)

        # Tight credit should raise the inflation threshold vs. loose credit,
        # and should NOT affect the growth threshold at all.
        assert tight["dyn_iz"].iloc[-1] > loose["dyn_iz"].iloc[-1]
        assert tight["dyn_gz"].iloc[-1] == pytest.approx(loose["dyn_gz"].iloc[-1])
        assert tight["credit_adj"].iloc[-1] > 1.0
        assert loose["credit_adj"].iloc[-1] == pytest.approx(1.0)

    def test_floor_masks_credit_multiplier_in_very_calm_regimes(self):
        """The 0.15 floor intentionally wins over the credit multiplier.

        Ray's safeguard exists precisely so an unusually calm stretch cannot
        shrink the effective threshold toward zero. When the floor binds, both
        the loose and tight cases clamp to it — that is the floor doing its job,
        not the credit term breaking.
        """
        from dashboard.charting import compute_dynamic_thresholds

        idx = pd.date_range("2020-01-31", periods=30, freq="ME")
        calm = [0.1, -0.1, 0.2, -0.2, 0.1] * 6
        comp = pd.DataFrame({
            "growth_score": calm, "inflation_score": calm,
            "credit_score": [2.0] * 30,
        }, index=idx)
        loose = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5)
        comp_tight = comp.copy()
        comp_tight["credit_score"] = -2.0
        tight = compute_dynamic_thresholds(comp_tight, base_gz=0.5, base_iz=0.5)

        assert loose["dyn_iz"].iloc[-1] == pytest.approx(0.15)
        assert tight["dyn_iz"].iloc[-1] == pytest.approx(0.15)
        assert (loose["dyn_gz"] >= 0.15 - 1e-9).all()

    def test_noisy_composite_widens_both_thresholds(self):
        from dashboard.charting import compute_dynamic_thresholds

        idx = pd.date_range("2020-01-31", periods=30, freq="ME")
        stable = compute_dynamic_thresholds(self._flat_history(n=30), base_gz=0.5, base_iz=0.5)

        noisy_vals = [3.0, -3.0] * 15  # highly erratic growth score
        comp_noisy = pd.DataFrame({
            "growth_score": noisy_vals,
            "inflation_score": [0.0] * 30,
            "credit_score": [0.0] * 30,
        }, index=idx)
        noisy = compute_dynamic_thresholds(comp_noisy, base_gz=0.5, base_iz=0.5)

        assert noisy["vol_adj"].iloc[-1] > stable["vol_adj"].iloc[-1]
        # vol_adj widens BOTH chips' thresholds (it's a max() of the two sides)
        assert noisy["dyn_gz"].iloc[-1] > 0 or noisy["dyn_iz"].iloc[-1] > 0

    def test_divergence_flag_fires_after_n_opposite_periods(self):
        from dashboard.charting import compute_dynamic_thresholds, _DIVERGENCE_LOOKBACK_N

        idx = pd.date_range("2020-01-31", periods=10, freq="ME")
        comp = pd.DataFrame({
            "growth_score": [0.5] * 10,
            "inflation_score": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, -0.5, -0.5, -0.5, -0.5],
            "credit_score": [0.0] * 10,
        }, index=idx)
        result = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5)

        # First N-1 opposite-sign rows should not yet trip the flag; by the
        # N-th consecutive opposite row it must be True.
        assert not result["divergence_flag"].iloc[6 + _DIVERGENCE_LOOKBACK_N - 2]
        assert result["divergence_flag"].iloc[6 + _DIVERGENCE_LOOKBACK_N - 1]
        assert not result["divergence_flag"].iloc[3]  # growth/inflation agree here

    def test_missing_credit_score_column_defaults_to_no_tightening(self):
        from dashboard.charting import compute_dynamic_thresholds

        idx = pd.date_range("2020-01-31", periods=30, freq="ME")
        comp = pd.DataFrame({
            "growth_score": [0.1] * 30,
            "inflation_score": [0.1] * 30,
        }, index=idx)  # no credit_score column at all
        result = compute_dynamic_thresholds(comp, base_gz=0.5, base_iz=0.5)
        assert (result["credit_adj"] - 1.0).abs().max() < 1e-6


def _stamped(**overrides) -> dict:
    """A store value as a real browser holds one: complete and version-stamped.

    Unstamped partial dicts are deliberately MIGRATED to the defaults now
    (resolve_thresholds), so a fixture that omits the stamp silently tests
    migration instead of whatever it meant to test.
    """
    import dashboard.charting as charting
    return {**charting._DEFAULT_THRESHOLDS, **overrides}


class TestDynamicToggleImmediateApply:
    """The dynamic-thresholds checkbox applies on click, not via the Apply button."""

    def test_toggle_on_writes_dynamic_true(self):
        from dashboard.charting import _apply_dynamic_toggle

        result = _apply_dynamic_toggle(["dynamic"], _stamped(gz=0.5, iz=0.5, dynamic=False))
        assert result["dynamic"] is True
        # other threshold values are preserved
        assert result["gz"] == 0.5 and result["iz"] == 0.5

    def test_toggle_off_writes_dynamic_false(self):
        from dashboard.charting import _apply_dynamic_toggle

        result = _apply_dynamic_toggle([], _stamped(gz=0.4, iz=0.4, dynamic=True))
        assert result["dynamic"] is False
        assert result["gz"] == 0.4  # preserved

    def test_no_op_when_value_matches_store(self):
        from dashboard.charting import _apply_dynamic_toggle
        from dash import no_update

        # This is what fires when the modal-open sync sets the checkbox to match
        # the store — must not rewrite the store (would cause a needless re-render).
        assert _apply_dynamic_toggle([], _stamped(dynamic=False)) is no_update
        assert _apply_dynamic_toggle(["dynamic"], _stamped(dynamic=True)) is no_update

    def test_toggling_an_unversioned_store_still_lands_on_current_defaults(self):
        # A returning browser's first click must not carry a retired rule
        # forward into the dict it writes back.
        from dashboard.charting import _apply_dynamic_toggle, _DEFAULT_THRESHOLDS

        # The stale dict still carries `im`, a key retired on 2026-10-08 —
        # exactly the shape a browser that has not been back since will send.
        result = _apply_dynamic_toggle([], {"gz": 0.5, "iz": 0.5, "gm": 0.0, "im": 0.0})
        assert result["dynamic"] is False            # the click is honored
        assert "im" not in result                    # the retired key is dropped
        assert result["gm"] == _DEFAULT_THRESHOLDS["gm"]  # the stale band is not kept
        assert result["v"] == _DEFAULT_THRESHOLDS["v"]


# ── compute_regime_confidence (coverage-audit Phase B, 2026-10-03) ────────────

class TestComputeRegimeConfidence:
    _T = {"gz": 0.5, "iz": 0.5, "gm": 0.05, "im": 0.05}

    @staticmethod
    def _comp(growth_vals, inflation_vals=None):
        n = len(growth_vals)
        idx = pd.date_range("2020-01-31", periods=n, freq="ME")
        return pd.DataFrame({
            "growth_score": growth_vals,
            "inflation_score": inflation_vals or [0.0] * n,
        }, index=idx)

    def test_persistently_growing_reading_has_high_confidence(self):
        from dashboard.charting import compute_regime_confidence

        # Steady +0.1/month climb starting well above threshold: every month
        # from the 2nd onward clears both the Z (>0.5) and momentum (>0.05)
        # legs, so every historical "Growth" month is followed by another one.
        vals = [round(1.0 + 0.1 * i, 2) for i in range(10)]
        comp = self._comp(vals)
        result = compute_regime_confidence(comp, dynamic=False, thresholds=self._T, force="growth")

        assert result["label"] == "Growth"
        assert result["confidence"] == pytest.approx(1.0)
        assert result["n"] > 0

    def test_flip_flopping_reading_has_low_confidence(self):
        from dashboard.charting import compute_regime_confidence

        # Alternates between a high Z/positive-momentum month (classifies
        # Growth) and a sharp drop back to zero (classifies Transition) —
        # every historical Growth month is immediately followed by Transition,
        # so Growth never actually "holds".
        vals = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
        comp = self._comp(vals)
        result = compute_regime_confidence(comp, dynamic=False, thresholds=self._T, force="growth")

        assert result["label"] == "Growth"  # today (last point) is a Growth month
        assert result["confidence"] == pytest.approx(0.0)
        assert result["n"] == 4  # idx 1,3,5,7 — idx9 (today) excluded from the precedent count

    def test_transition_today_returns_no_confidence_claim(self):
        from dashboard.charting import compute_regime_confidence

        # Flat near zero throughout -> Transition every month, including today.
        comp = self._comp([0.0] * 10)
        result = compute_regime_confidence(comp, dynamic=False, thresholds=self._T, force="growth")

        assert result["label"] == "Transition"
        assert result["confidence"] is None

    def test_too_short_history_returns_none(self):
        from dashboard.charting import compute_regime_confidence

        comp = self._comp([1.0])
        result = compute_regime_confidence(comp, dynamic=False, thresholds=self._T, force="growth")

        assert result == {"confidence": None, "label": None, "n": 0}

    def test_inflation_force_reads_the_anchored_gap(self):
        """The inflation leg is target-anchored as of 2026-10-08, so the replay
        is driven by the gap series, not by the inflation Z column."""
        from dashboard.charting import compute_regime_confidence

        comp = self._comp([0.0] * 10, inflation_vals=[0.0] * 10)
        gaps = pd.Series(1.0, index=pd.PeriodIndex(comp.index, freq="M"))
        result = compute_regime_confidence(comp, dynamic=False, thresholds=self._T,
                                           force="inflation", gaps=gaps)

        assert result["label"] == "Inflation"
        assert result["confidence"] == pytest.approx(1.0)

    def test_inflation_force_without_gaps_is_unavailable_not_wrong(self):
        """No gap series -> Transition everywhere -> no confidence number.
        Better than silently grading the retired relative-Z rule."""
        from dashboard.charting import compute_regime_confidence

        vals = [round(1.0 + 0.1 * i, 2) for i in range(10)]
        comp = self._comp([0.0] * 10, inflation_vals=vals)
        result = compute_regime_confidence(comp, dynamic=False, thresholds=self._T,
                                           force="inflation")
        assert result["label"] == "Transition"
        assert result["confidence"] is None


def test_chart_card_sync_hover_flag_marks_card_and_enables_spikes():
    import pandas as pd
    from dashboard.shared_components import _chart_card
    df = pd.DataFrame({"as_of": pd.to_datetime(["2024-01-01", "2024-02-01"]), "value": [1.0, 2.0]})
    on = _chart_card("t", df, 2.0, "z", "", sync_hover=True)
    off = _chart_card("t", df, 2.0, "z", "")
    assert on.className == "sync-hover-card" and off.className is None
    fig = on.children[-1].figure
    assert fig.layout.xaxis.showspikes and fig.layout.hovermode == "x"
    assert not off.children[-1].figure.layout.xaxis.showspikes


# ── Regime History header threshold readout ───────────────────────────────────
# The readout used to be wired to the threshold store alone, so with dynamic
# mode on it showed the sliders' base values (G·Z +0.50) while the classifier
# was using the country-vol-scaled ones (0.23 for the US in Oct 2026) — the
# number on screen was not the number doing the classifying.

def _chip_text(node) -> str:
    if isinstance(node, str):
        return node
    children = getattr(node, "children", None)
    if children is None:
        return ""
    if isinstance(children, list):
        return "".join(_chip_text(c) for c in children)
    return _chip_text(children)


def test_threshold_display_shows_effective_value_with_base_in_parens():
    import dashboard.charting as charting
    eff  = {"gz": 0.226, "iz": 0.150, "gm": 0.05, "im": 0.05, "dynamic": True}
    base = {"gz": 0.50,  "iz": 0.50,  "gm": 0.05, "im": 0.05, "dynamic": True}
    text = "".join(_chip_text(c) for c in charting._threshold_display_chips(eff, base))
    assert "+0.23" in text          # effective — what the classifier used
    assert "(0.50)" in text         # base — what the slider is set to
    assert "DYNAMIC" in text


def test_threshold_display_omits_base_when_dynamic_is_off():
    import dashboard.charting as charting
    static = {"gz": 0.5, "iz": 0.5, "gm": 0.05, "im": 0.05, "dynamic": False}
    text = "".join(_chip_text(c) for c in charting._threshold_display_chips(static))
    assert "+0.50" in text
    assert "(0.50)" not in text     # nothing to disambiguate
    assert "DYNAMIC" not in text


def test_threshold_display_omits_base_when_dynamic_did_not_move_it():
    # Same value either way → the parenthetical would be noise.
    import dashboard.charting as charting
    same = {"gz": 0.5, "iz": 0.5, "gm": 0.05, "im": 0.05, "dynamic": True}
    text = "".join(_chip_text(c) for c in charting._threshold_display_chips(same, same))
    assert "(0.50)" not in text     # the tooltip prose still mentions parentheses
    assert "DYNAMIC" in text


def test_resolve_row_thresholds_passes_momentum_gates_through_unscaled():
    # Ray's step 6: the dynamic algorithm scales the Z thresholds only.
    import dashboard.charting as charting
    comp = pd.DataFrame({
        "as_of": pd.date_range("2015-01-31", periods=60, freq="ME"),
        "growth_score": np.linspace(-1.0, 1.0, 60),
        "inflation_score": np.linspace(1.0, -1.0, 60),
    })
    base = _stamped(gz=0.5, iz=0.5, gm=0.05, im=0.05, dynamic=True)
    out = charting._resolve_row_thresholds(comp, 59, None, None, False, False, "US", base)
    assert out["gm"] == 0.05 and out["im"] == 0.05


def test_resolve_row_thresholds_is_a_noop_when_dynamic_is_off():
    import dashboard.charting as charting
    comp = pd.DataFrame({
        "as_of": pd.date_range("2015-01-31", periods=60, freq="ME"),
        "growth_score": np.linspace(-1.0, 1.0, 60),
        "inflation_score": np.linspace(1.0, -1.0, 60),
    })
    base = _stamped(gz=0.42, iz=0.37, gm=0.05, im=0.05, dynamic=False)
    assert charting._resolve_row_thresholds(comp, 59, None, None, False, False, "US", base) == base


def test_resolve_row_thresholds_survives_missing_columns_and_empty_input():
    import dashboard.charting as charting
    base = _stamped(gz=0.5, iz=0.5, gm=0.05, im=0.05, dynamic=True)
    assert charting._resolve_row_thresholds(
        pd.DataFrame(), 0, None, None, False, False, "US", base) == base
    bare = pd.DataFrame({"as_of": pd.date_range("2020-01-31", periods=3, freq="ME")})
    assert charting._resolve_row_thresholds(
        bare, 2, None, None, False, False, "US", base) == base


# ── Growth chip: level-gated, with momentum as a sub-state ────────────────────
# 2026-10-06. The growth chip used to require Z > gz AND dZ > gm; it now
# requires the level alone, and momentum moved to _growth_breadth_state().
# The inflation chip deliberately KEPT its momentum gate. Nothing pinned the
# old growth behaviour, so the whole asymmetry is pinned here instead.

_T = {"gz": 0.5, "iz": 0.5, "gm": 0.04, "im": 0.05, "dynamic": False}


def test_growth_chip_reads_growth_when_level_clears_but_momentum_is_flat():
    # The case that prompted the change: US 2026-10, Z well above threshold,
    # month-over-month change essentially zero. Used to read Transition.
    import dashboard.charting as charting
    g, _ = charting._classify_regime(0.9, 0.0, 0.001, 0.0, _T)
    assert g == "Growth"


def test_growth_chip_reads_growth_even_while_the_level_is_fading():
    # Still above the level gate but falling: NBER says these months are not
    # recessionary (0 of 65), so they stay inside the growth family.
    import dashboard.charting as charting
    g, _ = charting._classify_regime(0.9, 0.0, -0.30, 0.0, _T)
    assert g == "Growth"


def test_growth_chip_still_requires_the_level():
    import dashboard.charting as charting
    # below the gate, rising hard -> not Growth; the level is the primary gate
    assert charting._classify_regime(0.4, 0.0, 0.50, 0.0, _T)[0] == "Transition"
    # symmetric on the downside
    assert charting._classify_regime(-0.9, 0.0, 0.0, 0.0, _T)[0] == "Retraction"


def test_inflation_chip_is_gated_on_distance_from_target_not_momentum():
    """Replaces test_inflation_chip_keeps_its_momentum_gate (retired 2026-10-08).

    The momentum gate only ever existed as a stand-in for a level gate that did
    not work: dyn_iz was pinned at its 0.15 sigma floor for 10 of 14 countries
    while typical |inflation Z| ran 2.3-4.6x that, so the level cleared in 85%
    of months and momentum did all the gating -- 64 of the 82 percentage points
    of inflation Transition. With a functioning absolute gate it costs coverage
    for nothing. Ray 2026-10-03 Ruling 1; measurements in
    docs/Guidance/ray_consult_regime_frequency_2026-10-08.md.
    """
    import pandas as pd
    import dashboard.charting as charting
    held = pd.Series([1.0, 1.0])
    # Momentum is now irrelevant: a flat gap well above target still fires.
    _, i = charting._classify_regime(0.0, 0.9, 0.0, 0.000, _T,
                                     i_gap=1.0, i_gap_history=held)
    assert i == "Inflation"
    # And a big Z move inside the tolerance band does not.
    inside = pd.Series([0.1, 0.1])
    _, i = charting._classify_regime(0.0, 0.9, 0.0, 0.20, _T,
                                     i_gap=0.1, i_gap_history=inside)
    assert i == "Transition"


def test_growth_breadth_state_splits_a_growth_reading_three_ways():
    import dashboard.charting as charting
    assert charting._growth_breadth_state("Growth", 0.9,  0.20, _T) == "accelerating"
    assert charting._growth_breadth_state("Growth", 0.9,  0.001, _T) == "flat"
    assert charting._growth_breadth_state("Growth", 0.9, -0.001, _T) == "flat"
    assert charting._growth_breadth_state("Growth", 0.9, -0.20, _T) == "fading"
    # boundary sits at gm exactly: > gm accelerates, >= -gm is flat
    assert charting._growth_breadth_state("Growth", 0.9, 0.04, _T) == "flat"
    assert charting._growth_breadth_state("Growth", 0.9, 0.041, _T) == "accelerating"


def test_growth_breadth_state_is_none_outside_the_growth_regime():
    # Transition has no inside to describe, and the Retraction-side split does
    # not separate on forward GDP (+1.42 / +1.01 / +1.43), so it is not carried over.
    import dashboard.charting as charting
    assert charting._growth_breadth_state("Transition", 0.2, 0.9, _T) is None
    assert charting._growth_breadth_state("Retraction", -0.9, -0.9, _T) is None
    assert charting._growth_breadth_state("Growth", None, 0.9, _T) is None


def test_growth_breadth_state_has_a_plain_english_gloss_for_every_state():
    import dashboard.charting as charting
    for state in ("accelerating", "flat", "fading"):
        assert state in charting._GROWTH_MOMENTUM_STATE
        assert charting._GROWTH_MOMENTUM_STATE[state]


def test_default_growth_band_is_004_and_there_is_no_inflation_momentum_gate():
    """gm survives as the growth ANNOTATION band (it gates nothing, 2026-10-06).

    `im` was removed on 2026-10-08: the inflation chip is gated on distance
    from target, so there is no momentum gate left to default.
    """
    import dashboard.charting as charting
    assert charting._DEFAULT_THRESHOLDS["gm"] == 0.04
    assert "im" not in charting._DEFAULT_THRESHOLDS


def test_threshold_store_initial_data_references_the_module_defaults():
    # This pair drifted twice as two hand-maintained literals (the "dynamic"
    # default-ON change, then gm/im 0.0->0.05), silently giving new browsers
    # different thresholds from the ones the code documents. The Store now
    # REFERENCES the constant instead of restating it, so drift is impossible
    # -- pin that structure rather than comparing two literals.
    import re, pathlib
    import dashboard.charting as charting
    src = pathlib.Path(charting.__file__).read_text()
    m = re.search(r'dcc\.Store\(id="regime-threshold-store",.*?data=([^,\n]+),',
                  src, re.S)
    assert m, "could not locate the regime-threshold-store initial data"
    assert m.group(1).strip() == "dict(_DEFAULT_THRESHOLDS)", (
        "the threshold store must reference _DEFAULT_THRESHOLDS, not restate it")


# ── Threshold store: resolution + stale-value migration ──────────────────────
# Regression suite for 2026-10-07. Two persisted-state defects were in
# production: a pre-2026-10-03 store carries im=0.0 and degenerates the
# inflation chip's momentum gate into a sign test (US 2026-10 read Disinflation
# off a -0.0023 drift), and a pre-2026-07-09 store has no "dynamic" key while
# five files each guessed a different fallback for it. The store's initial data
# was already pinned by the test above -- which could not see either bug,
# because neither lives in the initial data. These do.

def _V():
    import dashboard.charting as charting
    return charting._THRESHOLD_STORE_VERSION


def test_resolve_thresholds_returns_defaults_for_a_fresh_browser():
    import dashboard.charting as charting
    assert charting.resolve_thresholds(None) == charting._DEFAULT_THRESHOLDS


@pytest.mark.parametrize("stale", [
    {"gz": 0.5, "iz": 0.5, "gm": 0.0, "im": 0.0},                    # pre-2026-07-09
    {"gz": 0.5, "iz": 0.5, "gm": 0.0, "im": 0.0, "dynamic": True},   # pre-2026-10-03
    {"gz": 0.5, "iz": 0.5, "gm": 0.0, "im": 0.0, "dynamic": False},
    {"gz": 0.5, "iz": 0.5, "v": 1},                                  # an older stamp
])
def test_stale_stores_are_migrated_to_current_defaults(stale):
    # The whole point: a browser cannot keep running a retired rule.
    import dashboard.charting as charting
    assert charting.resolve_thresholds(stale) == charting._DEFAULT_THRESHOLDS


@pytest.mark.parametrize("junk", ["not-a-dict", 42, [], {"v": "nonsense"}])
def test_resolve_thresholds_survives_junk(junk):
    import dashboard.charting as charting
    assert charting.resolve_thresholds(junk) == charting._DEFAULT_THRESHOLDS


def test_a_deliberate_current_version_choice_is_respected_exactly():
    # The flip side of migration: a choice made under TODAY's rules must stand,
    # including one that equals an old default (im=0.0 is a legal slider stop).
    import dashboard.charting as charting
    chosen = {**charting._DEFAULT_THRESHOLDS, "im": 0.0, "dynamic": False, "gz": 1.25}
    got = charting.resolve_thresholds(chosen)
    assert got["im"] == 0.0 and got["dynamic"] is False and got["gz"] == 1.25


def test_resolve_thresholds_fills_missing_keys_and_drops_nulls():
    # Callers read t["dynamic"] / t["gz"] directly, so the result must be
    # complete AND non-null: bool(None) is a silent False ("static"), and
    # float(None) raises.
    import dashboard.charting as charting
    got = charting.resolve_thresholds({"gz": None, "dynamic": None, "v": _V()})
    assert set(got) == set(charting._DEFAULT_THRESHOLDS)
    assert all(v is not None for v in got.values())
    assert got["dynamic"] is True


def test_dynamic_defaults_on_for_every_kind_of_absent_choice():
    # The user-facing contract: dynamic is ON until somebody turns it off here
    # and now.
    import dashboard.charting as charting
    for stored in (None, {}, {"gz": 0.5}, {"gz": 0.5, "iz": 0.5, "gm": 0.0, "im": 0.0}):
        assert charting.resolve_thresholds(stored)["dynamic"] is True


def test_no_module_reimplements_a_threshold_default():
    # The root cause was five files each hand-typing its own fallback, so
    # `dynamic` resolved True on the Regime Map and False on Command Center
    # from ONE stored value. Defaults live in _DEFAULT_THRESHOLDS; reads go
    # through resolve_thresholds()/thr(). Keep it that way.
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile(r'\.get\(\s*"(gz|iz|gm|im|dynamic|conc_adj)"\s*,')
    offenders = []
    for path in sorted((root / "dashboard").glob("*.py")) + \
                sorted((root / "indicators").glob("*.py")):
        for n, line in enumerate(path.read_text().split("\n"), 1):
            if pattern.search(line) and "_DEFAULT_THRESHOLDS[" not in line:
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, (
        "hand-typed threshold fallback(s) -- use thr(t, key) instead:\n"
        + "\n".join(offenders))


def test_version_bump_is_required_when_a_default_changes():
    # A default change without a version bump leaves every returning browser on
    # the old rule -- exactly the 2026-10-03 gm/im regression. This fingerprint
    # fails loudly on the next default change; bump _THRESHOLD_STORE_VERSION
    # and update the expected values together.
    import dashboard.charting as charting
    assert charting._THRESHOLD_STORE_VERSION == 3
    assert {k: v for k, v in charting._DEFAULT_THRESHOLDS.items() if k != "v"} == {
        "gz": 0.5, "iz": 0.5, "gm": 0.04,
        "dynamic": True, "conc_adj": False,
    }
    # `im` was removed on 2026-10-08 when the inflation chip became
    # target-anchored: its momentum gate was a stand-in for a level gate that
    # did not work, and a slider that no longer governs anything is a lie.
    assert "im" not in charting._DEFAULT_THRESHOLDS


def test_apply_stamps_the_version_so_a_choice_survives_the_next_bump():
    import dashboard.charting as charting
    from unittest.mock import patch
    with patch("dashboard.charting.ctx") as _c:
        pass
    # _save_thresholds reads dash.ctx, so exercise it through the registered
    # callback's python function with a patched ctx.triggered_id.
    import dash
    with patch.object(dash, "ctx") as mock_ctx:
        mock_ctx.triggered_id = "rh-threshold-apply"
        out = charting._save_thresholds(1, 0, 0.6, 0.7, 0.03, ["dynamic"], None)
    assert out["v"] == charting._THRESHOLD_STORE_VERSION
    assert (out["gz"], out["iz"], out["gm"]) == (0.6, 0.7, 0.03)
    assert out["dynamic"] is True
    # And it must round-trip unchanged through the resolver.
    assert charting.resolve_thresholds(out) == {**charting._DEFAULT_THRESHOLDS, **out}


def test_apply_keeps_a_deliberate_zero_on_the_momentum_slider():
    # `float(gm or 0.0)` would rewrite a deliberate 0.0; both sliders have a
    # 0.0 stop, so 0.0 has to survive Apply.
    import dashboard.charting as charting
    import dash
    from unittest.mock import patch
    with patch.object(dash, "ctx") as mock_ctx:
        mock_ctx.triggered_id = "rh-threshold-apply"
        out = charting._save_thresholds(1, 0, 0.5, 0.5, 0.0, [], None)
    assert out["gm"] == 0.0 and out["dynamic"] is False


def test_reset_writes_a_stamped_default_dict():
    import dashboard.charting as charting
    import dash
    from unittest.mock import patch
    with patch.object(dash, "ctx") as mock_ctx:
        mock_ctx.triggered_id = "rh-threshold-reset"
        out = charting._save_thresholds(0, 1, 0.5, 0.5, 0.0, [], None)
    assert out == charting._DEFAULT_THRESHOLDS
    assert charting.resolve_thresholds(out) == charting._DEFAULT_THRESHOLDS


def test_dynamic_toggle_initial_value_matches_the_default():
    # An unchecked box next to a default-ON store misreports the live rule for
    # the instant before the modal syncs from the store.
    import re, pathlib
    import dashboard.charting as charting
    src = pathlib.Path(charting.__file__).read_text()
    m = re.search(r'id="rh-dynamic-toggle".*?value=(\[[^\]]*\])', src, re.S)
    assert m, "could not locate the rh-dynamic-toggle initial value"
    checked = "dynamic" in m.group(1)
    assert checked is bool(charting._DEFAULT_THRESHOLDS["dynamic"])


def test_thr_falls_back_to_the_module_default_never_a_literal():
    import dashboard.charting as charting
    for key, default in charting._DEFAULT_THRESHOLDS.items():
        assert charting.thr(None, key) == default
        assert charting.thr({}, key) == default
        assert charting.thr({key: None}, key) == default
    # and a per-month dynamic override passes straight through
    assert charting.thr({"gz": 0.226}, "gz") == 0.226

# ── merge_asof datetime-precision regression (2026-10-07) ─────────────────────
#
# `update_chi_stress_scatter` raised `MergeError: incompatible merge keys` on
# every render for all 13 countries that have a debt-stress model: chi_hist is
# built on a pd.date_range (datetime64[ns]) while stress_hist comes straight
# from DuckDB (datetime64[us]), and pandas will not merge_asof across the two.
# EZ was the only country that passed, purely because it has no model and
# returns before the merge — which is why the original coverage missed this.

def test_align_as_of_normalises_duckdb_microsecond_dates():
    from dashboard.charting_data import align_as_of
    df = pd.DataFrame({
        "as_of": pd.to_datetime(["2020-01-01", "2020-02-01"]).astype("datetime64[us]"),
        "value": [1.0, 2.0],
    })
    assert df["as_of"].dtype == np.dtype("<M8[us]")
    assert align_as_of(df)["as_of"].dtype == np.dtype("<M8[ns]")


def test_align_as_of_leaves_nanosecond_dates_alone():
    from dashboard.charting_data import align_as_of
    df = pd.DataFrame({"as_of": pd.date_range("2020-01-01", periods=3, freq="MS")})
    assert align_as_of(df)["as_of"].dtype == np.dtype("<M8[ns]")


def test_align_as_of_handles_empty_and_missing_column():
    from dashboard.charting_data import align_as_of
    empty = pd.DataFrame(columns=["as_of", "value"])
    assert align_as_of(empty).empty
    other = pd.DataFrame({"raw_date": pd.date_range("2020-01-01", periods=2)})
    # no "as_of" column → handed back untouched rather than raising
    assert "raw_date" in align_as_of(other).columns


def test_align_as_of_makes_mixed_precision_frames_mergeable():
    """The exact ns-vs-us pairing that broke the chart, at the merge_asof level."""
    from dashboard.charting_data import align_as_of
    ns = pd.DataFrame({
        "as_of": pd.date_range("2020-01-01", periods=4, freq="MS"),
        "chi_z": [0.1, 0.2, 0.3, 0.4],
    })
    us = pd.DataFrame({
        "as_of": pd.to_datetime(["2020-01-01", "2020-03-01"]).astype("datetime64[us]"),
        "stress_score": [1.0, 2.0],
    })
    with pytest.raises(pd.errors.MergeError):
        pd.merge_asof(ns, us, on="as_of", direction="backward")
    merged = pd.merge_asof(align_as_of(ns), align_as_of(us),
                           on="as_of", direction="backward")
    assert len(merged) == 4
    assert merged["stress_score"].notna().all()


@pytest.mark.integration
def test_chi_stress_scatter_renders_for_country_with_a_model():
    """US HAS a debt-stress model, so this exercises the merge the old tests skipped."""
    from dashboard.charting import update_chi_stress_scatter
    fig, info = update_chi_stress_scatter({"start": None, "end": None}, "carbon", "US")
    # two traces: the 36-month trail and the latest marker
    assert len(fig.data) == 2
    assert len(fig.data[0].x) > 1
    assert len(fig.data[1].x) == 1
    # a real quadrant read, not the "—" placeholder
    assert "As of" in str(info[0].children)


@pytest.mark.integration
def test_chi_stress_scatter_renders_for_every_modelled_country():
    """Pins the whole set: the bug hit all 13 countries that have a model."""
    from dashboard.charting import update_chi_stress_scatter
    from dashboard.relative_view import COUNTRIES
    rendered = 0
    for cc in COUNTRIES:
        fig, _ = update_chi_stress_scatter({"start": None, "end": None}, "carbon", cc)
        if len(fig.data) == 2:
            rendered += 1
    # EZ has no debt-stress model and returns early; every other country must plot
    assert rendered == len(COUNTRIES) - 1


@pytest.mark.integration
def test_fed_monitor_ratio_survives_mixed_precision_inputs():
    """_ratio is DuckDB-on-both-sides today; pin that a parquet-sourced (ns) side works."""
    from dashboard.fed_monitor import _ratio
    num = pd.DataFrame({
        "as_of": pd.date_range("2020-01-01", periods=6, freq="MS"),
        "value": [10.0] * 6,
    })
    den = pd.DataFrame({
        "as_of": pd.to_datetime(["2020-01-01", "2020-04-01"]).astype("datetime64[us]"),
        "value": [100.0, 200.0],
    })
    out = _ratio(num, den)
    assert not out.empty
    assert set(out.columns) == {"as_of", "value"}


# ── 2026-10-08: the regime info card must honor the sustained-Z filter ────────
# The card is shared by Regime Map and Regime History. It was the only
# _classify_regime call site in the app that did not pass score history, so it
# silently ran the single-month rule and contradicted Command Center for
# 13-26% of months per country (GB/JP/ID disagreed live when this was found).

def _card_chips(children) -> list[str]:
    """The two chip labels, in order, out of a rendered regime info card."""
    out = []
    for t in _collect_texts(children):
        s = t.strip()
        if s in ("Growth", "Retraction", "Transition", "Inflation", "Disinflation"):
            out.append(s)
    return out[:2]


def _sustained_row() -> dict:
    return {
        "quadrant": "Expansion", "growth_score": 0.90, "inflation_score": 0.0,
        "confidence": 0.6, "disequilibrium_score": 0.4,
        "n_growth_signals": 1, "n_inflation_signals": 1,
        "as_of": pd.Timestamp("2026-10-31"),
    }


def test_regime_card_chip_blocks_growth_when_z_has_not_held():
    """Level clears the gate this month but not last month -> Transition."""
    from dashboard.charting import _regime_info_children
    thresholds = {"gz": 0.5, "iz": 0.5, "gm": 0.04, "im": 0.05, "dynamic": False}
    children = _regime_info_children(
        _sustained_row(), True, None, None, 0.9, 0.0,
        thresholds=thresholds,
        g_history=pd.Series([0.10, 0.90]),   # last month was INSIDE the band
        i_history=pd.Series([0.00, 0.00]),
    )
    assert _card_chips(children)[0] == "Transition"


def test_regime_card_chip_allows_growth_when_z_has_held():
    from dashboard.charting import _regime_info_children
    thresholds = {"gz": 0.5, "iz": 0.5, "gm": 0.04, "im": 0.05, "dynamic": False}
    children = _regime_info_children(
        _sustained_row(), True, None, None, 0.9, 0.0,
        thresholds=thresholds,
        g_history=pd.Series([0.80, 0.90]),   # held two consecutive months
        i_history=pd.Series([0.00, 0.00]),
    )
    assert _card_chips(children)[0] == "Growth"


def test_classify_regime_call_sites_in_charting_pass_history():
    """Guard: no _classify_regime call in charting.py may omit score history.

    compute_regime_confidence is the one documented exception — it runs a
    simplified replay on purpose and says so in its own docstring.
    """
    import re
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "dashboard" / "charting.py").read_text()
    # Drop the one sanctioned exception's body before scanning.
    src = re.sub(r"def compute_regime_confidence.*?\ndef ", "\ndef ", src, flags=re.S)
    calls = re.findall(r"_classify_regime\((?:[^()]|\([^()]*\))*\)", src)
    calls = [c for c in calls if not c.startswith("_classify_regime(\n    g_score")]
    offenders = [c for c in calls if "g_history" not in c]
    assert not offenders, (
        "_classify_regime called without history in charting.py:\n"
        + "\n---\n".join(offenders)
    )
    # Same contract for the anchored inflation gate (2026-10-08): a call that
    # omits i_gap silently reads Transition on the inflation leg forever.
    no_gap = [c for c in calls if "i_gap" not in c]
    assert not no_gap, (
        "_classify_regime called without i_gap in charting.py:\n"
        + "\n---\n".join(no_gap)
    )


@pytest.mark.integration
def test_regime_card_chip_matches_command_center_for_every_country():
    """The headline chip must not depend on which page you are looking at.

    This is the exact defect found 2026-10-08: same month, same country, same
    thresholds, two different chips. Runs every modelled country, because the
    US happened to agree while GB/JP/ID did not.
    """
    from dashboard.charting import (_classify_regime, compute_dynamic_thresholds,
                                    _dyn_threshold_input, resolve_thresholds,
                                    _conc_share_for, update_regime_info, gap_at)
    from dashboard.charting_data import load_composite_history
    from indicators.inflation_anchor import gap_series

    countries = ["US", "EZ", "GB", "JP", "KR", "CN", "IN",
                 "DE", "LU", "BR", "CA", "AU", "MX", "ID"]
    t0 = resolve_thresholds(None)
    mismatches = []
    for cc in countries:
        hist = load_composite_history(country=cc)
        if hist.empty:
            continue
        # Command Center's read (its own code path: full history, dynamic
        # threshold at the latest row, history passed).
        dyn = compute_dynamic_thresholds(
            _dyn_threshold_input(hist, "growth_score", "inflation_score"),
            base_gz=float(t0["gz"]), base_iz=float(t0["iz"]),
            conc_share=_conc_share_for(cc, t0),
        )
        t = dict(t0)
        if bool(t0["dynamic"]) and not dyn.empty:
            t["gz"] = float(dyn["dyn_gz"].iloc[-1])
            t["iz"] = float(dyn["dyn_iz"].iloc[-1])
        _ig, _igh = gap_at(gap_series(cc), hist["as_of"].iloc[-1])
        expected = _classify_regime(
            hist["growth_score"].iloc[-1], hist["inflation_score"].iloc[-1],
            hist["growth_score"].diff().iloc[-1], hist["inflation_score"].diff().iloc[-1],
            t, g_history=hist["growth_score"], i_history=hist["inflation_score"],
            i_gap=_ig, i_gap_history=_igh,
        )
        card, _ = update_regime_info(0, {}, 0, 0, 0, cc, None, None, False)
        got = tuple(_card_chips(card))
        if got != expected:
            mismatches.append(f"{cc}: card={got} command_center={expected}")
    assert not mismatches, "regime chip differs by page:\n" + "\n".join(mismatches)


# ── 1b: the map's inflation axis must be the chip's inflation gate ───────────
# The 2026-10-08 rule change moved the inflation chip to distance-from-target
# while the scatter still plotted the relative Z, reintroducing on one axis the
# map-vs-chip disagreement that 29331d2 fixed. These pin the repair.

def test_scatter_inflation_axis_plots_distance_from_target():
    from dashboard.charting import update_scatter_chart
    from indicators.inflation_anchor import anchor_read
    for cc in ("US", "JP", "CN"):
        fig = update_scatter_chart(0, {}, "Carbon", 0, 0, cc, None, None)
        assert "distance from target" in fig.layout.yaxis.title.text.lower()
        live = anchor_read(cc).gap_pp
        if live is None:
            continue
        sel_y = float(fig.data[-1].y[0])       # the big selected-month marker
        assert abs(sel_y - live) < 1e-2, f"{cc}: plotted {sel_y} vs anchor {live}"


def test_season_from_levels_gates_inflation_on_the_tolerance_not_the_z():
    """The TERRAIN function: background geography, gated on the two levels."""
    import dashboard.charting as charting
    tol = charting._inflation_tolerance_pp()
    t = {"gz": 0.5}
    assert charting._season_from_levels(0.9, tol + 0.5, t) == "Inflationary Boom"
    assert charting._season_from_levels(0.9, -(tol + 0.5), t) == "Expansion"
    # Gap inside the tolerance -> no season, however large the growth Z.
    assert charting._season_from_levels(3.0, tol / 2, t) == "Transition — no clear season"


def test_season_label_is_a_pure_function_of_the_two_chips():
    """The VERDICT function. Deriving the season from the chips is what makes
    it impossible for the map to name a season the chips do not support."""
    import dashboard.charting as charting
    assert charting._season_label("Growth", "Inflation") == "Inflationary Boom"
    assert charting._season_label("Growth", "Disinflation") == "Expansion"
    assert charting._season_label("Retraction", "Inflation") == "Stagflation"
    assert charting._season_label("Retraction", "Disinflation") == "Disinflationary Slowdown"
    for pair in (("Growth", "Transition"), ("Transition", "Inflation"),
                 ("Transition", "Transition")):
        assert charting._season_label(*pair) == "Transition — no clear season"
    assert charting._season_label(None, "Inflation") == "—"


def test_map_season_never_names_a_season_the_chips_do_not_support():
    """The invariant 1b exists to restore, checked on live data for every
    modelled country: if the map names a season, both chips must be decisive.
    """
    from dashboard.charting import (_season_label, _classify_regime, gap_at,
                                    resolve_thresholds, compute_dynamic_thresholds,
                                    _dyn_threshold_input, _conc_share_for)
    from dashboard.charting_data import load_composite_history
    from indicators.inflation_anchor import gap_series
    import pandas as pd

    t0 = resolve_thresholds(None)
    bad = []
    for cc in ("US", "EZ", "GB", "JP", "KR", "CN", "IN",
               "DE", "LU", "BR", "CA", "AU", "MX", "ID"):
        hist = load_composite_history(country=cc)
        if hist.empty:
            continue
        gaps = gap_series(cc)
        dyn = compute_dynamic_thresholds(
            _dyn_threshold_input(hist, "growth_score", "inflation_score"),
            base_gz=float(t0["gz"]), base_iz=float(t0["iz"]),
            conc_share=_conc_share_for(cc, t0),
        )
        t = dict(t0)
        if bool(t0["dynamic"]) and not dyn.empty:
            t["gz"] = float(dyn["dyn_gz"].iloc[-1])
        g = hist["growth_score"].iloc[-1]
        ig, igh = gap_at(gaps, hist["as_of"].iloc[-1])
        season = None  # filled from the chips below
        gc, ic = _classify_regime(
            g, hist["inflation_score"].iloc[-1],
            hist["growth_score"].diff().iloc[-1], hist["inflation_score"].diff().iloc[-1],
            t, g_history=hist["growth_score"], i_history=hist["inflation_score"],
            i_gap=ig, i_gap_history=igh,
        )
        season = _season_label(gc, ic)
        named = season not in ("—", "Transition — no clear season")
        if named and (gc == "Transition" or ic == "Transition"):
            bad.append(f"{cc}: map says {season!r} but chips are {gc}/{ic}")
    assert not bad, "map names a season the chips do not support:\n" + "\n".join(bad)


def test_the_environments_page_never_calls_an_environment_a_regime():
    """Checklist item 3, 2026-10-08. One word for two objects cost a session.

    `asset_environments.py` is the only surface in this repo that speaks about
    the All-Weather ENVIRONMENT (a deviation) rather than our regime STATE
    chip (a level). It used to call them regimes. The remaining allowed hits
    are the deliberate contrast between the two and references to the Regime
    Map's axis orientation — anything else is the ambiguity creeping back.
    """
    import pathlib, re
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "dashboard" / "asset_environments.py").read_text()
    allowed = ("regime **state**", 'call an environment a "regime"',
               "Regime-Map axis orientation", "Regime Map's axis orientation",
               "regime chip:")
    offenders = [
        ln.strip() for ln in src.splitlines()
        if re.search(r"\bregimes?\b", ln, re.I)
        and not any(a in ln for a in allowed)
    ]
    assert not offenders, (
        "asset_environments.py calls an environment a regime:\n  "
        + "\n  ".join(offenders)
    )

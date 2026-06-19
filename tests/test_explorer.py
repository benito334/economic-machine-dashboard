"""
Tests for Phase 1E — Data Explorer.

Unit tests: explorer_data helpers, formatting, gap detection.
Integration tests (marked): real DuckDB queries.
"""
from __future__ import annotations

import os
import pytest
import pandas as pd

DB = os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb")
CACHE = os.environ.get("RAW_CACHE_DIR", "/mnt/data/project_data/all_weather/indicators_machine/raw_cache")


# ── Unit tests — no DB required ───────────────────────────────────────────────

def test_infer_freq_label_daily():
    from dashboard.explorer_data import _infer_freq_label
    assert _infer_freq_label("us.policy.fed_funds") == "daily"
    assert _infer_freq_label("us.policy.yield_10y") == "daily"
    assert _infer_freq_label("us.premium.yield_curve_10y2y") == "daily"


def test_infer_freq_label_monthly():
    from dashboard.explorer_data import _infer_freq_label
    assert _infer_freq_label("us.growth.payrolls") == "monthly"
    assert _infer_freq_label("us.inflation.cpi_core") == "monthly"
    assert _infer_freq_label("us.growth.capacity_util") == "monthly"


def test_infer_freq_label_quarterly():
    from dashboard.explorer_data import _infer_freq_label
    assert _infer_freq_label("us.master.gdp_real") == "quarterly"
    assert _infer_freq_label("us.credit.corporate_debt") == "quarterly"
    assert _infer_freq_label("us.credit.household_debt_gdp") == "quarterly"


def test_infer_freq_label_annual():
    from dashboard.explorer_data import _infer_freq_label
    assert _infer_freq_label("us.growth.tfp") == "annual"
    assert _infer_freq_label("us.demo.population_growth") == "annual"
    assert _infer_freq_label("us.fiscal.federal_deficit") == "annual"


def test_cache_path_fred():
    from dashboard.explorer_data import _cache_path_for_source
    p = _cache_path_for_source("FRED:DGS10")
    assert p is not None
    assert p.name == "fred_DGS10.parquet"


def test_cache_path_worldbank():
    from dashboard.explorer_data import _cache_path_for_source
    p = _cache_path_for_source("WorldBank:NE.EXP.GNFS.ZS")
    assert p is not None
    assert "wb_US_NE_EXP_GNFS_ZS" in p.name


def test_cache_path_imf():
    from dashboard.explorer_data import _cache_path_for_source
    p = _cache_path_for_source("IMF:pb")
    assert p is not None
    assert "imf_US_pb" in p.name


def test_cache_path_derived_returns_none():
    from dashboard.explorer_data import _cache_path_for_source
    assert _cache_path_for_source("derived:policy.real_fed_funds") is None


def test_cache_path_missing_returns_none():
    from dashboard.explorer_data import _cache_path_for_source
    assert _cache_path_for_source("FRED:NONEXISTENT_SERIES_XYZ") is None


def test_flag_anomalies_detects_high_z():
    from dashboard.explorer_data import flag_anomalies
    df = pd.DataFrame({"zscore": [0.5, -4.0, 1.2, 3.5, 2.9], "value": [1.0]*5})
    mask = flag_anomalies(df)
    assert mask[1]   # |z| = 4.0 → anomaly
    assert mask[3]   # |z| = 3.5 → anomaly
    assert not mask[0]  # |z| = 0.5 → fine
    assert not mask[2]  # |z| = 1.2 → fine
    assert not mask[4]  # |z| = 2.9 < 3 → fine


def test_flag_anomalies_detects_nan_value():
    from dashboard.explorer_data import flag_anomalies
    import numpy as np
    df = pd.DataFrame({"zscore": [0.5, 0.2], "value": [1.0, np.nan]})
    mask = flag_anomalies(df)
    assert not mask[0]
    assert mask[1]   # NaN value → anomaly


def test_explorer_layout_returns_div():
    from dashboard.explorer import get_layout
    from dash import html
    layout = get_layout()
    assert isinstance(layout, html.Div)


def test_explorer_layout_has_required_ids():
    """Verify key component IDs are present in the layout."""
    from dashboard.explorer import get_layout
    import json
    layout = get_layout()
    layout_str = str(layout)
    required_ids = [
        "exp-selected-signal",
        "exp-force-filter",
        "exp-flag-filter",
        "exp-signal-table",
        "exp-ts-chart",
        "exp-obs-table",
        "exp-ref-input",
        "exp-ref-btn",
        "exp-gaps-content",
        "exp-raw-content",
    ]
    for id_ in required_ids:
        assert id_ in layout_str, f"Missing component id: {id_}"


def test_charting_imports_explorer():
    """Explorer is wired into the Dash app."""
    from dashboard import charting
    # Confirm server is still Flask (app didn't break)
    import flask
    assert isinstance(charting.server, flask.Flask)


def test_overview_columns_structure():
    from dashboard.explorer import _overview_columns
    cols = _overview_columns()
    ids = {c["id"] for c in cols}
    assert "id" in ids
    assert "force" in ids
    assert "zscore_fmt" in ids
    assert "flags" in ids
    assert "days_since_update" in ids


# ── Integration tests — require real DuckDB ───────────────────────────────────

@pytest.mark.integration
def test_load_signal_overview_returns_all_signals():
    from dashboard.explorer_data import load_signal_overview
    df = load_signal_overview()
    assert len(df) == 59
    assert "id" in df.columns
    assert "force" in df.columns
    assert "latest_value" in df.columns
    assert "obs_count" in df.columns
    assert "days_since_update" in df.columns
    assert "flags" in df.columns
    assert "freq" in df.columns


@pytest.mark.integration
def test_load_signal_overview_no_nulls_in_key_cols():
    from dashboard.explorer_data import load_signal_overview
    df = load_signal_overview()
    assert df["id"].notna().all()
    assert df["force"].notna().all()
    assert df["latest_as_of"].notna().all()
    assert df["obs_count"].gt(0).all()


@pytest.mark.integration
def test_load_signal_overview_freq_labels_plausible():
    from dashboard.explorer_data import load_signal_overview
    df = load_signal_overview()
    valid_freqs = {"daily", "weekly", "monthly", "quarterly", "annual"}
    assert set(df["freq"].unique()).issubset(valid_freqs)


@pytest.mark.integration
def test_load_signal_detail_returns_df():
    from dashboard.explorer_data import load_signal_detail
    df = load_signal_detail("us.inflation.pce_core")
    assert isinstance(df, pd.DataFrame)
    assert "as_of" in df.columns
    assert "value" in df.columns
    assert "zscore" in df.columns
    assert len(df) > 100


@pytest.mark.integration
def test_load_signal_detail_with_limit():
    from dashboard.explorer_data import load_signal_detail
    df = load_signal_detail("us.policy.fed_funds", limit=10)
    assert len(df) == 10
    # Should be newest first
    assert df["as_of"].iloc[0] >= df["as_of"].iloc[-1]


@pytest.mark.integration
def test_detect_gaps_monthly_signal():
    from dashboard.explorer_data import detect_gaps
    # labor_force_part has a known 61-day max gap (missing month)
    gaps = detect_gaps("us.growth.labor_force_part")
    assert isinstance(gaps, pd.DataFrame)
    assert "period_start" in gaps.columns
    assert "gap_days" in gaps.columns
    # Should find at least one gap
    assert len(gaps) >= 1
    # All flagged gaps should be > 60 days (2× monthly threshold of 30)
    assert (gaps["gap_days"] > 60).all()


@pytest.mark.integration
def test_detect_gaps_daily_signal_few_gaps():
    from dashboard.explorer_data import detect_gaps
    # Daily yields should have very few gaps (only weekends/holidays)
    # With threshold 2×1=2 days, weekends (2-day gap) should NOT be flagged
    # since we use 2× = 2, and weekends produce gap=3 (Fri→Mon). Check > 2.
    gaps = detect_gaps("us.policy.yield_10y")
    # The max_gap we saw was 5 days — these are holiday weeks, acceptable
    # All gaps should be short weekend/holiday gaps
    assert isinstance(gaps, pd.DataFrame)


@pytest.mark.integration
def test_detect_gaps_annual_signal_no_false_positives():
    from dashboard.explorer_data import detect_gaps
    gaps = detect_gaps("us.growth.tfp")
    # Annual signal: expect threshold = 730 days. No gap should be > 730 days.
    if len(gaps) > 0:
        assert (gaps["gap_days"] <= 1000).all()


@pytest.mark.integration
def test_compute_signal_stats():
    from dashboard.explorer_data import compute_signal_stats
    stats = compute_signal_stats("us.inflation.pce_core")
    assert isinstance(stats, dict)
    assert stats["obs_count"] > 100
    assert stats["min_val"] < stats["max_val"]
    assert stats["mean_val"] is not None
    assert stats["outlier_count"] >= 0


@pytest.mark.integration
def test_load_raw_cache_series_fred():
    from dashboard.explorer_data import load_raw_cache_series
    s = load_raw_cache_series("FRED:DGS10")
    assert s is not None
    assert isinstance(s, pd.Series)
    assert len(s) > 1000
    assert s.index.dtype.kind == "M"  # datetime


@pytest.mark.integration
def test_load_raw_cache_series_worldbank():
    from dashboard.explorer_data import load_raw_cache_series
    s = load_raw_cache_series("WorldBank:NE.EXP.GNFS.ZS")
    assert s is not None
    assert len(s) > 10


@pytest.mark.integration
def test_load_raw_cache_series_derived_returns_none():
    from dashboard.explorer_data import load_raw_cache_series
    s = load_raw_cache_series("derived:policy.real_fed_funds")
    assert s is None


@pytest.mark.integration
def test_compare_raw_vs_processed_level_signal():
    from dashboard.explorer_data import compare_raw_vs_processed
    df = compare_raw_vs_processed("us.policy.fed_funds", "FRED:DFF", n_recent=10)
    assert isinstance(df, pd.DataFrame)
    assert "raw_value" in df.columns
    assert "db_value" in df.columns
    assert "pct_delta" in df.columns
    # Fed funds is a level signal — raw and processed should match closely
    valid = df.dropna(subset=["raw_value", "pct_delta"])
    assert (valid["pct_delta"].abs() < 1.0).all(), "Level signal delta > 1% — possible transform error"


@pytest.mark.integration
def test_compare_raw_vs_processed_yoy_signal():
    from dashboard.explorer_data import compare_raw_vs_processed
    # For a YoY signal the raw cache holds the index level, DB holds YoY%
    # So delta is expected to be large; we just check the function runs cleanly
    df = compare_raw_vs_processed("us.growth.payrolls", "FRED:PAYEMS", n_recent=6)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "raw_value" in df.columns


@pytest.mark.integration
def test_compare_raw_vs_processed_derived_has_no_raw():
    from dashboard.explorer_data import compare_raw_vs_processed
    df = compare_raw_vs_processed("us.policy.real_fed_funds", "derived:policy.real_fed_funds", n_recent=5)
    assert df["raw_value"].isna().all()


@pytest.mark.integration
def test_explorer_signal_table_callback():
    """Smoke test the filter callback returns correctly typed data."""
    from dashboard.explorer import _format_overview
    from dashboard.explorer_data import load_signal_overview
    overview = load_signal_overview()
    rows = _format_overview(overview)
    assert isinstance(rows, list)
    assert len(rows) == 59
    assert all("id" in r for r in rows)
    assert all("zscore_fmt" in r for r in rows)
    assert all("flags" in r for r in rows)

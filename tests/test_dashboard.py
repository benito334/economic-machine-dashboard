"""Tests for Phase 1C dashboard helper functions and DB queries."""
from __future__ import annotations

import math
import os

import duckdb
import pandas as pd
import pytest

# Prevent Streamlit from executing main() on import
os.environ.setdefault("INDICATORS_TESTING", "1")

from dashboard.app import (
    _concept_label,
    _fmt_value,
    _pct_badge,
    _quality_badges,
    _sparkline_svg,
    _zscore_color,
)

# ── _fmt_value ──────────────────────────────────────────────────────────────

def test_fmt_value_yoy_pct():
    assert _fmt_value(0.0282, "yoy_pct") == "+2.82%"


def test_fmt_value_yoy_pct_negative():
    assert _fmt_value(-0.005, "yoy_pct") == "-0.50%"


def test_fmt_value_pct_level():
    assert _fmt_value(4.3, "pct_level") == "4.30%"


def test_fmt_value_pct_gdp():
    assert _fmt_value(122.77, "pct_gdp") == "122.77%"


def test_fmt_value_diffusion_index():
    assert _fmt_value(10.3, "diffusion_index") == "10.3"


def test_fmt_value_millions_usd_trillions():
    assert "T" in _fmt_value(-22_000_000.0, "millions_usd")


def test_fmt_value_millions_usd_billions():
    result = _fmt_value(-190_745.0, "millions_usd")
    assert "B" in result


def test_fmt_value_thousands():
    assert "M" in _fmt_value(8_500.0, "thousands")


def test_fmt_value_none():
    assert _fmt_value(None, "yoy_pct") == "—"


def test_fmt_value_nan():
    assert _fmt_value(float("nan"), "pct_level") == "—"


# ── _concept_label ──────────────────────────────────────────────────────────

def test_concept_label_standard():
    assert _concept_label("us.growth.payrolls") == "Payrolls"


def test_concept_label_underscored():
    label = _concept_label("us.inflation.core_pce")
    assert label == "Core Pce"


def test_concept_label_long_underscored():
    label = _concept_label("us.premium.yield_curve_10y2y")
    assert label == "Yield Curve 10Y2Y"


# ── _sparkline_svg ──────────────────────────────────────────────────────────

def test_sparkline_svg_returns_svg_tag():
    svg = _sparkline_svg([1.0, 2.0, 3.0, 2.5, 1.5])
    assert "<svg" in svg and "</svg>" in svg


def test_sparkline_svg_too_few_points():
    svg = _sparkline_svg([1.0])
    assert "<path" not in svg


def test_sparkline_svg_empty():
    svg = _sparkline_svg([])
    assert "<path" not in svg


def test_sparkline_svg_nans_filtered():
    svg = _sparkline_svg([float("nan"), 1.0, 2.0, float("nan"), 3.0])
    assert "<path" in svg


def test_sparkline_svg_constant():
    # All same value should not crash
    svg = _sparkline_svg([2.0, 2.0, 2.0])
    assert "<svg" in svg


# ── _pct_badge ──────────────────────────────────────────────────────────────

def test_pct_badge_elevated():
    badge = _pct_badge(0.90)
    assert "9b1c1c" in badge  # dark red
    assert "90%" in badge


def test_pct_badge_high():
    badge = _pct_badge(0.75)
    assert "c05a00" in badge  # orange


def test_pct_badge_depressed():
    badge = _pct_badge(0.05)
    assert "1a3a6e" in badge  # dark blue
    assert "5%" in badge


def test_pct_badge_low():
    badge = _pct_badge(0.25)
    assert "2155a0" in badge  # blue


def test_pct_badge_neutral():
    badge = _pct_badge(0.50)
    assert "444" in badge


def test_pct_badge_none():
    badge = _pct_badge(None)
    assert "—" in badge


def test_pct_badge_low_history():
    badge = _pct_badge(0.95, low_history=True)
    assert "555" in badge  # muted grey, not elevated red


# ── _zscore_color ───────────────────────────────────────────────────────────

def test_zscore_color_high():
    assert _zscore_color(2.0) == "#ff8888"


def test_zscore_color_low():
    assert _zscore_color(-2.0) == "#88aaff"


def test_zscore_color_neutral():
    assert _zscore_color(0.0) == "#cccccc"


def test_zscore_color_none():
    assert _zscore_color(None) == "#888"


# ── _quality_badges ─────────────────────────────────────────────────────────

def test_quality_badges_all_clean():
    row = pd.Series({
        "is_proxy": False,
        "is_stale": False,
        "vintage_available": True,
        "low_history": False,
    })
    assert _quality_badges(row) == ""


def test_quality_badges_proxy():
    row = pd.Series({"is_proxy": True, "is_stale": False, "vintage_available": True, "low_history": False})
    assert "proxy" in _quality_badges(row)


def test_quality_badges_stale():
    row = pd.Series({"is_proxy": False, "is_stale": True, "vintage_available": True, "low_history": False})
    assert "stale" in _quality_badges(row)


def test_quality_badges_no_vintage():
    row = pd.Series({"is_proxy": False, "is_stale": False, "vintage_available": False, "low_history": False})
    assert "vintage" in _quality_badges(row)


def test_quality_badges_low_history():
    row = pd.Series({"is_proxy": False, "is_stale": False, "vintage_available": True, "low_history": True})
    assert "hist" in _quality_badges(row)


def test_quality_badges_multiple():
    row = pd.Series({"is_proxy": True, "is_stale": True, "vintage_available": False, "low_history": True})
    html = _quality_badges(row)
    assert "proxy" in html
    assert "stale" in html
    assert "vintage" in html


# ── Integration: DB query correctness ───────────────────────────────────────

REAL_DB = "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"


@pytest.mark.integration
def test_real_db_latest_signals():
    conn = duckdb.connect(REAL_DB, read_only=True)
    df = conn.execute(
        """
        SELECT * FROM signals WHERE country = 'US'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
        ORDER BY force, id
        """
    ).df()
    conn.close()
    assert len(df) >= 50, "Expected at least 50 US signals"
    assert set(df["force"]).issuperset({"growth", "inflation", "policy", "credit"})
    assert df["level_percentile"].between(0, 1).all()
    assert df["is_stale"].dtype == bool


@pytest.mark.integration
def test_real_db_composite_history():
    conn = duckdb.connect(REAL_DB, read_only=True)
    df = conn.execute(
        "SELECT * FROM composites WHERE country = 'US' ORDER BY as_of"
    ).df()
    conn.close()
    assert len(df) >= 12, "Expected at least 12 monthly composite snapshots"
    valid_labels = set(
        ["Expansion", "Inflationary Boom", "Stagflation", "Disinflationary Slowdown"]
    )
    assert set(df["quadrant"].dropna()).issubset(valid_labels)
    # Early history may lack enough signals for some scores; require post-2010 to be fully populated
    recent = df[df["as_of"] >= "2010-01-01"]
    assert recent["growth_score"].notna().all()
    assert recent["inflation_score"].notna().all()
    # 2022 should be Inflationary Boom (not Stagflation — growth z-scores positive all year)
    boom_2022 = df[(df["as_of"] >= "2022-01-01") & (df["as_of"] <= "2022-12-31")]
    assert (boom_2022["quadrant"] == "Inflationary Boom").all(), (
        "2022 should be labeled Inflationary Boom (strong labour market)"
    )


@pytest.mark.integration
def test_real_db_change_feed():
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=120)).isoformat()
    conn = duckdb.connect(REAL_DB, read_only=True)
    df = conn.execute(
        """
        WITH ranked AS (
            SELECT id, force, lead_lag, as_of, zscore, direction,
                   ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) AS rn
            FROM signals WHERE country = 'US' AND as_of >= ?
        ),
        latest AS (SELECT * FROM ranked WHERE rn = 1),
        prior  AS (SELECT * FROM ranked WHERE rn = 2)
        SELECT
            l.id, l.force, l.zscore,
            ABS(l.zscore - COALESCE(p.zscore, l.zscore)) AS zscore_delta
        FROM latest l
        LEFT JOIN prior p ON l.id = p.id
        WHERE l.lead_lag IN ('leading', 'coincident')
        ORDER BY zscore_delta DESC
        """,
        [cutoff],
    ).df()
    conn.close()
    assert len(df) > 0, "Change feed should have rows"
    assert (df["zscore_delta"] >= 0).all(), "zscore_delta must be non-negative"
    # Top mover should have material z-score change
    assert df.iloc[0]["zscore_delta"] > 0.05


@pytest.mark.integration
def test_real_db_signal_history_bulk():
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=36 * 31)).isoformat()
    conn = duckdb.connect(REAL_DB, read_only=True)
    df = conn.execute(
        "SELECT id, as_of, value FROM signals WHERE country = 'US' AND as_of >= ? ORDER BY id, as_of",
        [cutoff],
    ).df()
    conn.close()
    assert df["id"].nunique() >= 50
    assert not df["value"].isna().all()
    # Build sparklines for every signal — should not raise
    for sid, grp in df.groupby("id"):
        vals = grp["value"].tolist()
        svg = _sparkline_svg(vals)
        assert "<svg" in svg

"""Tests for the Workbench (TV-style chart studio, /workbench)."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import json

import numpy as np
import pandas as pd
import pytest

from dashboard import workbench_data as wd


# ── Search index ──────────────────────────────────────────────────────────────

def test_index_covers_all_sources():
    idx = wd.build_search_index(force_refresh=True)
    sources = {r["source"] for r in idx}
    assert {"signal", "composite", "raw"}.issubset(sources)
    assert len([r for r in idx if r["source"] == "signal"]) >= 180


def test_search_tokens_all_must_match():
    hits = wd.search_index("cpi jp")
    assert hits and all("JP" in h["label"] or "jp." in h["key"] for h in hits)
    assert wd.search_index("zzz-no-such-thing") == []


def test_search_facets_filter():
    hits = wd.search_index("", countries=["GB"], groups=["policy"])
    assert hits and all(h["country"] == "GB" and h["group"] == "policy" for h in hits)


# ── Series loading + transforms ───────────────────────────────────────────────

def test_load_each_source():
    s, _ = wd.load_series("signal", "us.inflation.cpi_core")
    assert len(s) > 400
    c, _ = wd.load_series("composite", "US|growth_score")
    assert len(c) > 400
    r, _ = wd.load_series("raw", "DGS10")
    assert len(r) > 5000
    empty, _ = wd.load_series("signal", "xx.not.real")
    assert empty.empty


def test_transform_rebase_anchors_inside_window():
    idx = pd.date_range("2015-01-31", periods=60, freq="ME")
    s = pd.Series(np.linspace(50, 100, 60), index=idx)
    out, sfx = wd.apply_transform(s, "rebase", window_start=idx[30])
    # first value INSIDE the window is 100 after rebasing
    assert out[out.index >= idx[30]].iloc[0] == pytest.approx(100.0)
    assert "rebased" in sfx


def test_transform_pct_start():
    idx = pd.date_range("2020-01-31", periods=12, freq="ME")
    s = pd.Series(np.linspace(10, 12, 12), index=idx)
    out, _ = wd.apply_transform(s, "pct_start")
    assert out.iloc[0] == pytest.approx(0.0)
    assert out.iloc[-1] == pytest.approx(20.0)


def test_transform_yoy_monthly():
    idx = pd.date_range("2019-01-31", periods=36, freq="ME")
    s = pd.Series(np.arange(100.0, 136.0), index=idx)
    out, sfx = wd.apply_transform(s, "yoy")
    assert "YoY" in sfx
    # value at t vs t-12: (112-100)/100 = 12%
    assert out.iloc[0] == pytest.approx(12.0)


def test_transform_z_uses_stored_zscore():
    s, meta = wd.load_series("signal", "us.inflation.cpi_core")
    out, sfx = wd.apply_transform(s, "z", meta)
    assert "Z" in sfx and out.abs().max() < 10


# ── Saved views ───────────────────────────────────────────────────────────────

def test_view_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(wd, "SAVED_VIEWS_PATH", tmp_path / "views.json")
    spec = {"mode": "stacked", "timeframe": "5Y",
            "series": [{"source": "signal", "key": "us.inflation.cpi_core",
                        "transform": "yoy", "pane": 1}]}
    wd.save_view("my test view", spec)
    assert "my test view" in wd.list_views()
    assert wd.get_view("my test view") == spec
    wd.delete_view("my test view")
    assert "my test view" not in wd.list_views()


def test_presets_resolve_and_are_protected(tmp_path, monkeypatch):
    monkeypatch.setattr(wd, "SAVED_VIEWS_PATH", tmp_path / "views.json")
    for name in wd.PRESET_VIEWS:
        spec = wd.get_view(name)
        assert spec and spec["series"], name
        for s in spec["series"]:
            ts, _ = wd.load_series(s["source"], s["key"])
            assert not ts.empty, f"{name}: {s['key']} resolves to no data"
    with pytest.raises(ValueError):
        wd.save_view(list(wd.PRESET_VIEWS)[0], {"series": []})


# ── UI callbacks ──────────────────────────────────────────────────────────────

def test_chart_overlay_and_stacked_render():
    from dashboard.workbench import wb_chart
    series = [
        {"source": "signal", "key": "us.policy.yield_10y",
         "label": "Yield 10Y (US)", "transform": "raw", "pane": 1},
        {"source": "signal", "key": "jp.policy.yield_10y",
         "label": "Yield 10Y (JP)", "transform": "raw", "pane": 2},
    ]
    fig_o = wb_chart(series, {"mode": "overlay", "timeframe": "10Y"}, "carbon")
    assert len(fig_o.data) == 2
    fig_s = wb_chart(series, {"mode": "stacked", "timeframe": "10Y"}, "carbon")
    assert len(fig_s.data) == 2
    # stacked: two panes → second trace on a different y-axis
    assert fig_s.data[0].yaxis != fig_s.data[1].yaxis
    # empty state
    fig_e = wb_chart([], {}, "carbon")
    assert "Workbench" in (fig_e.layout.title.text or "")


def test_overlay_independent_axes():
    """Independent axis mode gives each series its own overlaying y-axis so a
    small-range series isn't flattened by a large-range one."""
    from dashboard.workbench import wb_chart
    series = [
        {"source": "signal", "key": "us.fiscal.interest_payments",
         "label": "Interest (US)", "transform": "raw", "pane": 1},
        {"source": "signal", "key": "us.growth.productivity",
         "label": "Productivity (US)", "transform": "raw", "pane": 2},
    ]
    shared = wb_chart(series, {"mode": "overlay", "axis": "shared",
                              "timeframe": "MAX"}, "carbon")
    indep = wb_chart(series, {"mode": "overlay", "axis": "independent",
                             "timeframe": "MAX"}, "carbon")
    # shared: both traces on the one y-axis
    assert {t.yaxis or "y" for t in shared.data} == {"y"}
    # independent: distinct axes, the second overlaying the base
    assert {t.yaxis or "y" for t in indep.data} == {"y", "y2"}
    assert indep.layout.yaxis2.overlaying == "y"
    # single series → independent is a no-op (no phantom second axis)
    one = wb_chart(series[:1], {"mode": "overlay", "axis": "independent",
                               "timeframe": "MAX"}, "carbon")
    assert "yaxis2" not in one.layout


def test_pills_render_with_pane_input_in_stacked():
    from dashboard.workbench import wb_pills
    series = [{"source": "signal", "key": "us.inflation.cpi_core",
               "label": "Cpi Core (US)", "transform": "raw", "pane": 1}]
    overlay = str(wb_pills(series, {"mode": "overlay"}))
    stacked = str(wb_pills(series, {"mode": "stacked"}))
    assert "wb-transform" in overlay and "wb-pane" not in overlay
    assert "wb-pane" in stacked


def test_search_results_callback():
    from dashboard.workbench import wb_search_results
    out = wb_search_results("cpi core us", None, None)
    assert out and "wb-add" in str(out)


def test_routes():
    import dashboard.charting as c
    assert c._PAGE_MAP["/workbench"] is c._page_workbench
    assert c._PAGE_MAP["/charts"] is c._page_workbench      # legacy redirect
    assert c._PAGE_MAP["/explorer"] is c._page_workbench    # legacy redirect

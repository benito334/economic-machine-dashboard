"""Tests for the target-anchored inflation read and Ray's growth safeguards.

Implements rulings from docs/Guidance/ray_dalio_review_log.md session 2026-10-03.
"""
from __future__ import annotations

import pandas as pd
import pytest
import yaml
from pathlib import Path

from indicators import inflation_anchor as ia

_CFG = Path(__file__).parents[1] / "config" / "inflation_anchor.yaml"


@pytest.fixture
def cfg():
    return yaml.safe_load(_CFG.read_text())


def _signals(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["id", "as_of", "value", "zscore", "is_stale"])
    df["as_of"] = pd.to_datetime(df["as_of"])
    df["concept"] = df["id"].str.rsplit(".", n=1).str[-1]
    return df


# ── Config integrity ─────────────────────────────────────────────────────────

def test_every_dashboard_country_has_a_target(cfg):
    countries = set(cfg["countries"])
    expected = {"US", "EZ", "DE", "LU", "GB", "JP", "KR", "CN",
                "IN", "BR", "CA", "AU", "MX", "ID"}
    assert expected <= countries, f"missing targets for {expected - countries}"


def test_targets_are_plausible(cfg):
    for cc, spec in cfg["countries"].items():
        assert 0.0 < float(spec["target_pct"]) <= 6.0, cc
        assert spec["gap_series"], cc
        assert spec.get("note"), f"{cc} must document its target's provenance"


def test_split_weights_sum_to_one(cfg):
    s = cfg["split"]
    assert s["impulse_weight"] + s["persistence_weight"] == pytest.approx(1.0)


def test_persistence_excludes_audit_benchmarks(cfg):
    """The documented departure from Ray: trimmed/median/sticky measures stay OUT.

    They are the audit skill's independent benchmarks. If they become inputs the
    audit is circular. This test is the enforcement.
    """
    from indicators import audit_benchmarks as ab
    bench_concepts = {b.key for b in ab.ALL_BENCHMARKS}
    members = set(cfg["split"]["impulse_members"]) | set(cfg["split"]["persistence_members"])
    assert not (members & bench_concepts), (
        f"basket members collide with audit benchmarks: {members & bench_concepts}"
    )
    for banned in ("trimmed", "median", "sticky"):
        assert not any(banned in m for m in members), (
            f"{banned!r} measures must stay validation-only"
        )


# ── Anchor classification ────────────────────────────────────────────────────

def test_above_target(cfg):
    sig = _signals([("us.inflation.pce_core", "2026-08-01", 0.030, 0.2, False)])
    r = ia.anchor_read("US", config=cfg, signals=sig)
    assert r.label == ia.ABOVE
    assert r.gap_pp == pytest.approx(1.0, abs=0.01)
    assert r.inflation_pct == pytest.approx(3.0, abs=0.01)


def test_below_target(cfg):
    sig = _signals([("cn.inflation.cpi_headline", "2026-08-01", -0.001, -1.0, False)])
    r = ia.anchor_read("CN", config=cfg, signals=sig)
    assert r.label == ia.BELOW
    assert r.gap_pp == pytest.approx(-3.1, abs=0.01)


def test_at_target_inside_tolerance(cfg):
    sig = _signals([("jp.inflation.cpi_headline", "2026-08-01", 0.0196, 0.0, False)])
    r = ia.anchor_read("JP", config=cfg, signals=sig)
    assert r.label == ia.AT


def test_tolerance_boundary_is_inclusive(cfg):
    """Exactly at the tolerance edge reads At Target, not Above."""
    sig = _signals([("us.inflation.pce_core", "2026-08-01", 0.025, 0.0, False)])
    assert ia.anchor_read("US", config=cfg, signals=sig).label == ia.AT


def test_country_target_is_respected_not_hardcoded_two_percent(cfg):
    """India's 4% target means 3% inflation is BELOW target, not above."""
    sig = _signals([("in.inflation.cpi_headline", "2026-08-01", 0.030, 0.0, False)])
    r = ia.anchor_read("IN", config=cfg, signals=sig)
    assert r.target_pct == 4.0
    assert r.label == ia.BELOW


def test_unknown_country_degrades_without_raising(cfg):
    r = ia.anchor_read("ZZ", config=cfg, signals=_signals([]))
    assert r.gap_pp is None
    assert "No inflation target" in r.note


def test_no_usable_series_reports_what_it_tried(cfg):
    r = ia.anchor_read("US", config=cfg, signals=_signals([]))
    assert r.gap_pp is None
    assert "pce_core" in r.note


def test_freshest_candidate_wins_over_config_order(cfg):
    """A dead monthly mirror must not anchor the read when a live bridge exists.

    GB/KR/CN/IN/MX/AU monthly CPI feeds are dead (data_source_wishlist.md); the
    read must fall through to the fresher series rather than quoting a print
    over a year old.
    """
    sig = _signals([
        ("gb.inflation.cpi_core", "2025-03-01", 0.042, 0.5, True),
        ("gb.inflation.cpi_headline", "2026-08-31", 0.031, 0.2, False),
    ])
    r = ia.anchor_read("GB", config=cfg, signals=sig)
    assert r.gap_series == "cpi_headline"
    assert r.as_of == "2026-08-31"


def test_staleness_is_surfaced(cfg):
    sig = _signals([("mx.inflation.cpi_headline", "2024-07-01", 0.055, 0.5, True)])
    r = ia.anchor_read("MX", config=cfg, signals=sig, as_of="2026-10-01")
    assert r.is_stale is True
    assert r.age_months is not None and r.age_months > 20


def test_as_of_filters_history(cfg):
    sig = _signals([
        ("us.inflation.pce_core", "2026-06-01", 0.050, 1.0, False),
        ("us.inflation.pce_core", "2026-08-01", 0.020, 0.0, False),
    ])
    assert ia.anchor_read("US", config=cfg, signals=sig).label == ia.AT
    assert ia.anchor_read("US", as_of="2026-07-01", config=cfg, signals=sig).label == ia.ABOVE


# ── Gap direction ────────────────────────────────────────────────────────────

def _gap_read(gap, chg):
    return ia.AnchorRead("US", "2026-08-01", ia.ABOVE, gap, None, 2.0, "x", chg,
                         False, None)


def test_direction_closing_and_widening():
    assert _gap_read(1.0, -0.4).direction == "closing"
    assert _gap_read(1.0, 0.4).direction == "widening"
    assert _gap_read(-1.0, -0.4).direction == "widening"
    assert _gap_read(-1.0, 0.4).direction == "closing"


def test_direction_handles_zero_crossing():
    """AU went +1.31pp -> -0.10pp: clearly closing, though both numbers are
    negative. A sign-based test calls that widening; comparing magnitudes does not."""
    assert _gap_read(-0.10, -1.41).direction == "closing"


def test_direction_flat_and_unknown():
    assert _gap_read(1.0, 0.01).direction == "flat"
    assert _gap_read(None, None).direction == "unknown"


# ── Impulse vs persistence ───────────────────────────────────────────────────

def test_impulse_and_persistence_split(cfg):
    sig = _signals([
        ("us.inflation.crude_oil", "2026-08-01", 0.5, 2.0, False),
        ("us.inflation.breakeven_avg", "2026-08-01", 0.02, 1.0, False),
        ("us.inflation.pce_core", "2026-08-01", 0.03, -0.5, False),
        ("us.inflation.cpi_core", "2026-08-01", 0.024, -0.5, False),
    ])
    out = ia.impulse_persistence("US", config=cfg, signals=sig)
    assert out["impulse"] == pytest.approx(1.5)
    assert out["persistence"] == pytest.approx(-0.5)
    # 0.30 * 1.5 + 0.70 * -0.5
    assert out["blended"] == pytest.approx(0.1)
    assert out["divergence"] == pytest.approx(2.0)
    assert "supply-side" in out["reading"]


def test_subindex_below_min_members_is_none(cfg):
    sig = _signals([("us.inflation.crude_oil", "2026-08-01", 0.5, 2.0, False)])
    out = ia.impulse_persistence("US", config=cfg, signals=sig)
    assert out["impulse"] is None
    assert out["persistence"] is None
    assert out["blended"] is None
    assert "insufficient" in out["reading"]


def test_embedded_inflation_reading(cfg):
    sig = _signals([
        ("us.inflation.crude_oil", "2026-08-01", 0.0, -1.0, False),
        ("us.inflation.ppi_broad", "2026-08-01", 0.0, -1.0, False),
        ("us.inflation.pce_core", "2026-08-01", 0.03, 1.0, False),
        ("us.inflation.cpi_core", "2026-08-01", 0.03, 1.0, False),
    ])
    out = ia.impulse_persistence("US", config=cfg, signals=sig)
    assert out["divergence"] == pytest.approx(-2.0)
    assert "embedded" in out["reading"]


def test_blended_falls_back_when_one_side_missing(cfg):
    sig = _signals([
        ("us.inflation.pce_core", "2026-08-01", 0.03, 0.4, False),
        ("us.inflation.cpi_core", "2026-08-01", 0.024, 0.6, False),
    ])
    out = ia.impulse_persistence("US", config=cfg, signals=sig)
    assert out["impulse"] is None
    assert out["blended"] == pytest.approx(0.5)
    assert out["divergence"] is None


# ── Growth safeguards ────────────────────────────────────────────────────────

def test_threshold_floor_applied():
    assert ia.apply_threshold_floor(0.09) == pytest.approx(0.15)
    assert ia.apply_threshold_floor(0.40) == pytest.approx(0.40)
    assert ia.apply_threshold_floor(None) == pytest.approx(0.15)
    assert ia.apply_threshold_floor(float("nan")) == pytest.approx(0.15)


def test_sustained_requires_consecutive_months():
    s = pd.Series([0.1, 0.9])
    assert ia.sustained(s, 0.5, "above") is False
    assert ia.sustained(pd.Series([0.8, 0.9]), 0.5, "above") is True


def test_sustained_below_direction():
    assert ia.sustained(pd.Series([-0.8, -0.9]), 0.5, "below") is True
    assert ia.sustained(pd.Series([-0.1, -0.9]), 0.5, "below") is False


def test_sustained_false_without_enough_history():
    assert ia.sustained(pd.Series([0.9]), 0.5, "above") is False


# ── Production classifier wiring ─────────────────────────────────────────────

def test_classifier_backcompat_without_history():
    """Callers that pass no history keep the original single-month rule."""
    from dashboard.charting import _classify_regime
    assert _classify_regime(0.9, 0.9, 0.1, 0.1) == ("Growth", "Inflation")


def test_classifier_sustained_filter_blocks_one_month_spike():
    from dashboard.charting import _classify_regime
    spike = pd.Series([0.0, 0.9])
    assert _classify_regime(0.9, 0.9, 0.1, 0.1,
                            g_history=spike, i_history=spike) == ("Transition", "Transition")


def test_classifier_sustained_filter_allows_held_move():
    from dashboard.charting import _classify_regime
    held = pd.Series([0.8, 0.9])
    assert _classify_regime(0.9, 0.9, 0.1, 0.1,
                            g_history=held, i_history=held) == ("Growth", "Inflation")


def test_short_history_does_not_block_a_new_country():
    """A country with one month of data must not be stuck at Transition."""
    from dashboard.charting import _classify_regime
    assert _classify_regime(0.9, 0.9, 0.1, 0.1,
                            g_history=pd.Series([0.9]),
                            i_history=pd.Series([0.9])) == ("Growth", "Inflation")


def test_dynamic_thresholds_respect_the_floor():
    """A very calm series would otherwise scale the threshold toward zero."""
    from dashboard.charting import compute_dynamic_thresholds
    idx = pd.date_range("2015-01-31", periods=80, freq="ME")
    calm = pd.DataFrame({
        "as_of": idx,
        "growth_score": [0.001 * (n % 3) for n in range(80)],
        "inflation_score": [0.001 * (n % 2) for n in range(80)],
    })
    out = compute_dynamic_thresholds(calm, base_gz=0.5, base_iz=0.5)
    assert (out["dyn_gz"] >= 0.15 - 1e-9).all()
    assert (out["dyn_iz"] >= 0.15 - 1e-9).all()

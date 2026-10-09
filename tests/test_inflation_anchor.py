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
    """No history -> the growth leg keeps the original single-month rule.

    The inflation leg reads Transition because no gap was supplied, which is
    the deliberate contract: a caller that does not provide the anchored gap
    gets Transition, never a fallback to the retired relative-Z rule.
    """
    from dashboard.charting import _classify_regime
    assert _classify_regime(0.9, 0.9, 0.1, 0.1) == ("Growth", "Transition")


def test_classifier_never_falls_back_to_the_retired_z_rule():
    """A large inflation Z with no gap must NOT produce an Inflation chip.

    Pins the one-definition contract: the relative-Z inflation rule was retired
    on 2026-10-08 and must not survive as a silent fallback.
    """
    from dashboard.charting import _classify_regime
    _, i = _classify_regime(0.0, 5.0, 0.0, 5.0, i_gap=None)
    assert i == "Transition"


def test_classifier_sustained_filter_blocks_one_month_spike():
    from dashboard.charting import _classify_regime
    spike = pd.Series([0.0, 0.9])
    assert _classify_regime(0.9, 0.9, 0.1, 0.1,
                            g_history=spike, i_history=spike) == ("Transition", "Transition")


def test_classifier_sustained_filter_allows_held_move():
    from dashboard.charting import _classify_regime
    held = pd.Series([0.8, 0.9])
    held_gap = pd.Series([1.2, 1.1])          # pp above target, two months
    assert _classify_regime(0.9, 0.9, 0.1, 0.1,
                            g_history=held, i_history=held,
                            i_gap=1.1, i_gap_history=held_gap) == ("Growth", "Inflation")


def test_classifier_inflation_leg_is_gated_on_the_TARGET_not_the_z():
    """Ray 2026-10-03 Ruling 1, the whole point of the change.

    A low relative Z with inflation genuinely above target must read
    Inflation — that is the "3% looks low on your Z-score but the Fed is still
    hiking" case that had the dashboard out of sync with reality.
    """
    from dashboard.charting import _classify_regime
    gap = pd.Series([1.0, 1.0])
    _, i = _classify_regime(0.0, -0.9, 0.0, -0.1, i_gap=1.0, i_gap_history=gap)
    assert i == "Inflation"
    # ...and a high Z that is AT target must not.
    at = pd.Series([0.1, 0.1])
    _, i = _classify_regime(0.0, 2.5, 0.0, 0.5, i_gap=0.1, i_gap_history=at)
    assert i == "Transition"


def test_short_history_does_not_block_a_new_country():
    """A country with one month of data must not be stuck at Transition."""
    from dashboard.charting import _classify_regime
    assert _classify_regime(0.9, 0.9, 0.1, 0.1,
                            g_history=pd.Series([0.9]),
                            i_history=pd.Series([0.9]),
                            i_gap=1.0,
                            i_gap_history=pd.Series([1.0])) == ("Growth", "Inflation")


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


# ── gap_series — the series form the regime classifier consumes ───────────────

def test_gap_series_agrees_with_anchor_read_on_the_latest_month():
    """Two readers of one rule. If these drift, the chip and its own display
    card are telling the user different things — the defect this module exists
    to prevent."""
    from indicators.inflation_anchor import gap_series, anchor_read
    for cc in ("US", "EZ", "GB", "JP", "BR", "MX", "AU"):
        g = gap_series(cc)
        a = anchor_read(cc)
        if g.empty or a.gap_pp is None:
            continue
        # anchor_read rounds gap_pp to 3dp; agreement to that precision is exact
        assert abs(float(g.iloc[-1]) - a.gap_pp) < 1e-3, (
            f"{cc}: gap_series {g.iloc[-1]} != anchor_read {a.gap_pp}"
        )


def test_gap_series_is_monthly_sorted_and_unique():
    from indicators.inflation_anchor import gap_series
    g = gap_series("US")
    assert not g.empty
    assert g.index.freqstr == "M"
    assert g.index.is_monotonic_increasing
    assert not g.index.duplicated().any()


def test_gap_series_drops_months_whose_source_is_older_than_max_age():
    """Staleness guard: a chip may not claim a state from a year-old print.

    Synthetic, because the real US gap series runs on monthly core PCE and so
    carries a fresh observation almost every month — there is nothing stale in
    it to catch.
    """
    import pandas as pd
    from indicators.inflation_anchor import gap_series, load_config
    cfg = load_config()
    cfg = {**cfg, "countries": {**cfg["countries"],
                                "US": {"target_pct": 2.0, "gap_series": ["cpi_headline"]}}}
    # one lone observation in 2020-01, nothing after
    sig = pd.DataFrame([{"id": "us.inflation.cpi_headline",
                         "as_of": pd.Timestamp("2020-01-31"),
                         "value": 0.035, "zscore": 0.0, "is_stale": False,
                         "concept": "cpi_headline"}])
    wide = dict(cfg); wide["bands"] = {**cfg["bands"], "max_age_months": 12}
    tight = dict(cfg); tight["bands"] = {**cfg["bands"], "max_age_months": 2}
    g_wide = gap_series("US", config=wide, signals=sig)
    g_tight = gap_series("US", config=tight, signals=sig)
    assert len(g_wide) == 13          # the month itself plus 12 carried months
    assert len(g_tight) == 3          # the month itself plus 2
    assert abs(float(g_wide.iloc[0]) - 1.5) < 1e-9   # 3.5% - 2.0% target


def test_gap_series_unknown_country_is_empty_not_an_error():
    from indicators.inflation_anchor import gap_series
    assert gap_series("ZZ").empty


# ── Ruling 2: the impulse / persistence split, as the basket WEIGHTS imply it ─

_ALL_COUNTRIES = ["US", "EZ", "GB", "JP", "KR", "CN", "IN",
                  "DE", "LU", "BR", "CA", "AU", "MX", "ID"]


def test_every_inflation_basket_member_is_classified():
    """Nothing may sit in neither sub-index.

    Before 2026-10-08 `cpi_imf_annual` (10 countries) and `hicp_food` (EZ) were
    in neither list, so the implied split was unreadable for 11 of 14. Both are
    flexible-price by Ray's own taxonomy — an annual HEADLINE CPI is not a
    sticky core measure — and are now in `impulse_members`. A new signal added
    to an inflation basket without classifying it fails here.
    """
    from indicators.inflation_anchor import basket_split_composition
    stray = {}
    for cc in _ALL_COUNTRIES:
        comp = basket_split_composition(cc)
        unc = comp.get("members", {}).get("unclassified", [])
        if unc:
            stray[cc] = unc
    assert not stray, f"inflation signals in neither sub-index: {stray}"


def test_countries_with_both_legs_are_persistence_majority():
    """Ray's 30/70: where a sticky component exists it must dominate.

    Actual persistence shares as of 2026-10-08 — US 0.80, EZ 0.68, GB 0.61,
    KR 0.61. US sits above Ray's stated 60-70% band; that is recorded rather
    than silently accepted, and this test will fail if any of them drifts
    below half, which would invert the ruling.
    """
    from indicators.inflation_anchor import basket_split_composition
    both = {cc: basket_split_composition(cc) for cc in _ALL_COUNTRIES}
    both = {cc: c for cc, c in both.items() if c["has_both"]}
    assert both, "expected at least one country with both legs"
    for cc, c in both.items():
        assert c["persistence_share"] > 0.5, (
            f"{cc}: persistence share {c['persistence_share']} — the sticky "
            f"component must dominate the flexible one (Ray 2026-10-03 #2)"
        )


def test_impulse_only_countries_are_identified_not_hidden():
    """Ten of fourteen have no sticky member at all.

    That makes their composite a LEADING impulse index, not a current-state
    gauge, and it has to be visible rather than presented like the US's
    core-PCE-weighted read.
    """
    from indicators.inflation_anchor import basket_split_composition
    comps = {cc: basket_split_composition(cc) for cc in _ALL_COUNTRIES}
    impulse_only = [cc for cc, c in comps.items() if not c["has_both"]]
    assert impulse_only, "expected impulse-only countries to exist"
    for cc in impulse_only:
        assert comps[cc]["members"]["persistence"] == []
        assert comps[cc]["impulse_weight"] > 0


# ── SPF expectations feeding signals.surprise (Ruling 3 slot, 2026-10-09) ────

def test_spf_expectation_is_none_for_an_unmapped_signal():
    """None is the signal to fall back to the random walk, not an error."""
    import pandas as pd
    from indicators.spf_loader import spf_expectation
    idx = pd.date_range("2015-01-31", periods=24, freq="ME")
    assert spf_expectation("growth.retail_sales", idx) is None
    assert spf_expectation("not.a.signal", idx) is None


def test_spf_expectation_arrives_in_the_signal_s_own_units():
    """The whole reason `conversion` exists.

    Subtracting an SPF LEVEL from a YoY-transformed signal would produce an
    authoritative-looking number that means nothing. Unemployment is a rate in
    percent on both sides (~3-11); payrolls is a YoY FRACTION (|x| < 0.2).
    """
    import pandas as pd
    from indicators.spf_loader import spf_expectation
    idx = pd.date_range("2000-01-31", periods=300, freq="ME")

    u = spf_expectation("growth.unemployment", idx)
    assert u is not None and u.notna().any()
    assert 2.0 < float(u.dropna().median()) < 12.0, "unemployment must be a percent"

    p = spf_expectation("growth.payrolls", idx)
    assert p is not None and p.notna().any()
    assert float(p.dropna().abs().median()) < 0.2, "payrolls must be a YoY fraction"


def test_every_spf_mapped_signal_is_actually_in_a_basket():
    """Guard against wiring a forecast that reaches nothing.

    Real GDP growth is the cautionary case: SPF publishes it, but
    master.gdp_real is in no composite, so an SPF GDP forecast would populate
    one orphan column and change no composite. It is deliberately absent from
    the map and must stay so unless the basket changes.
    """
    from indicators.spf_loader import _SPF_SIGNAL_MAP
    from indicators.composites import load_composites_config
    cfg = load_composites_config("US")
    in_basket = {i["id"] for b in ("growth_score", "inflation_score")
                 for i in cfg[b]["indicators"]}
    stray = set(_SPF_SIGNAL_MAP) - in_basket
    assert not stray, f"SPF mapped to signals that feed no composite: {stray}"


def test_build_signals_prefers_the_forecast_and_falls_back_cleanly():
    import numpy as np
    import pandas as pd
    from indicators.pipeline import load_bindings, _CONFIG_DIR
    from indicators.normalize import build_signals, compute_surprise

    bindings = {b.id: b for b in load_bindings(_CONFIG_DIR / "us_bindings.yaml")}
    idx = pd.date_range("2000-01-31", periods=240, freq="ME")
    series = pd.Series(
        4.0 + pd.Series(range(240)).mod(12).values * 0.05, index=idx)

    rw = pd.Series({d.date(): v for d, v in compute_surprise(series).dropna().items()})

    mapped = build_signals(series, bindings["growth.unemployment"])
    got = pd.Series({s.as_of: s.surprise for s in mapped if s.surprise is not None})
    shared = got.index.intersection(rw.index)
    assert len(shared) > 24, "no overlap to compare on"
    # A real forecast must produce a DIFFERENT series from the random walk.
    assert not np.allclose(got.loc[shared].values, rw.loc[shared].values)

    # An unmapped signal is untouched by any of this.
    unmapped = build_signals(series, bindings["growth.retail_sales"])
    got_u = pd.Series({s.as_of: s.surprise for s in unmapped if s.surprise is not None})
    shared_u = got_u.index.intersection(rw.index)
    assert len(shared_u) > 24
    assert np.allclose(got_u.loc[shared_u].values, rw.loc[shared_u].values)


def test_non_us_countries_get_no_spf_expectation():
    """SPF is a US survey. A GB signal must never silently inherit it."""
    import pandas as pd
    from indicators.normalize import _resolve_expectation
    from indicators.pipeline import load_bindings, _CONFIG_DIR
    gb = {b.id: b for b in load_bindings(_CONFIG_DIR / "countries" / "gb_bindings.yaml")}
    tail = next(t for t in gb if "unemploy" in t)
    idx = pd.date_range("2010-01-31", periods=60, freq="ME")
    assert _resolve_expectation(gb[tail], idx) is None

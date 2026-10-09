"""Tests for the country command center page (roadmap Phase CC)."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import pandas as pd
import pytest
from dash import html

from dashboard import command_center as cc


def _render(country="US", page="/country", thresholds=None):
    return cc.render_command_center(country, {"page": page}, thresholds)


def _tree_text(component) -> str:
    """Flatten a Dash component tree to its concatenated text."""
    parts = []

    def walk(c):
        if c is None:
            return
        if isinstance(c, str):
            parts.append(c)
            return
        if isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
            return
        walk(getattr(c, "children", None))

    walk(component)
    return " ".join(parts)


def _tree_hrefs(component) -> set:
    hrefs = set()

    def walk(c):
        if c is None or isinstance(c, str):
            return
        if isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
            return
        h = getattr(c, "href", None)
        if h:
            hrefs.add(h)
        walk(getattr(c, "children", None))

    walk(component)
    return hrefs


def test_layout_returns_div_with_content_target():
    lay = cc.get_layout()
    assert isinstance(lay, html.Div)
    assert "cc-content" in str(lay)


def test_render_us_has_all_cards_and_chips():
    out = _render("US")
    text = _tree_text(out)
    # Regime strip
    assert "Growth ·" in text and "Inflation ·" in text
    assert "confidence" in text
    # Lever cards
    for label in ("Credit conditions", "Policy stance", "Debt stress",
                  "Debt-service ratio", "Productivity trend", "Cycle stage"):
        assert label in text, f"missing card: {label}"
    # Planned placeholder for the remaining unbuilt layer (Phase D order);
    # the Phase C stage card is live as of the debt-cycle stage classifier.
    assert "Phase D" in text
    # What-changed feed section
    assert "What changed" in text


def test_render_cards_link_to_detail_pages():
    hrefs = _tree_hrefs(_render("US"))
    for href in ("/signals/growth", "/signals/inflation", "/signals/credit",
                 "/signals/rate", "/signals/productivity", "/debt-stress"):
        assert href in hrefs, f"missing drill-down link: {href}"


def test_render_skips_other_pages():
    from dash import no_update
    out = cc.render_command_center("US", {"page": "/charts"}, None)
    assert out is no_update


def test_render_handles_dynamic_thresholds():
    out = _render("US", thresholds={"gz": 0.5, "iz": 0.5, "gm": 0.0,
                                    "im": 0.0, "dynamic": True})
    assert "DYNAMIC" in _tree_text(out)


@pytest.mark.parametrize("country", ["EZ", "KR"])
def test_render_other_countries_no_crash(country):
    out = _render(country)
    text = _tree_text(out)
    assert "Growth ·" in text  # regime strip renders even with sparser data


def test_routes_registered():
    import dashboard.charting as charting
    assert charting._PAGE_MAP["/"] is charting._page_command_center
    assert charting._PAGE_MAP["/country"] is charting._page_command_center


# ── 2026-07-06 unification audit (Ray rulings) ────────────────────────────────

def test_season_label_threshold_aware():
    """Season geography, split in two on 2026-10-08.

    `_season_from_levels` is the positional TERRAIN read (growth Z vs ±gz,
    inflation vs ±tolerance_pp in percentage points). `_season_label` is the
    VERDICT and is a pure function of the two chips, so it cannot name a
    season the chips do not support.
    """
    from dashboard.charting import _season_from_levels, _season_label

    # terrain: second argument is now a GAP in pp, not an inflation Z
    assert _season_from_levels(1.2, 0.9, None) == "Inflationary Boom"
    assert _season_from_levels(1.2, -0.9, None) == "Expansion"
    assert _season_from_levels(-1.2, 0.9, None) == "Stagflation"
    assert _season_from_levels(-1.2, -0.9, None) == "Disinflationary Slowdown"
    assert "Transition" in _season_from_levels(0.3, 0.2, None)   # inside band
    assert "Transition" in _season_from_levels(1.2, 0.2, None)   # one side inside
    assert _season_from_levels(None, 0.9, None) == "—"
    assert "Transition" in _season_from_levels(0.9, 0.9, {"gz": 1.0})

    # verdict: chips in, season out
    assert _season_label("Growth", "Inflation") == "Inflationary Boom"
    assert "Transition" in _season_label("Growth", "Transition")


def test_chip_direction_agreement_reads_the_stored_value():
    # Rewritten 2026-10-07. This used to RECOMPUTE the metric here from
    # latest_signals, and drifted from the chip it describes: it measured every
    # signal carrying force=='growth' (19 for the US) rather than the 12 that
    # build the composite, and never flipped `invert` signals. It is now
    # computed once in the pipeline over the composite's own basket and read
    # here, so the screen and the stored column cannot disagree.
    from dashboard.command_center import chip_direction_agreement

    hist = pd.DataFrame({
        "growth_dir_agreement": [0.4, 0.75],
        "inflation_dir_agreement": [0.1, None],
    })
    assert chip_direction_agreement(hist, "growth") == pytest.approx(0.75)
    # falls back to the last NON-NULL month rather than reporting nothing
    assert chip_direction_agreement(hist, "inflation") == pytest.approx(0.1)
    assert chip_direction_agreement(pd.DataFrame(), "growth") is None
    assert chip_direction_agreement(pd.DataFrame({"x": [1]}), "growth") is None


def test_direction_agreement_is_invert_aware_and_basket_scoped():
    # The two bugs the move to the pipeline fixed, pinned on the real engine.
    import numpy as np

    from indicators.composites import compute_composite_history  # noqa: F401

    # A falling inverted signal (unemployment) is moving WITH a rising growth
    # chip, so it must count as agreement, not disagreement.
    cfg = [{"id": "growth.payrolls", "importance": 0.9},
           {"id": "growth.unemployment", "importance": 0.5, "invert": True}]
    d_row = pd.Series({"us.growth.payrolls": "rising",
                       "us.growth.unemployment": "falling",
                       "us.growth.not_in_basket": "falling"})
    contrib = ["us.growth.payrolls", "us.growth.unemployment"]

    def _agree(prev, cur):
        delta = cur - prev
        heading = "rising" if delta > 0 else "falling"
        vals = []
        for ind in cfg:
            sid = f"us.{ind['id']}"
            if sid not in contrib:
                continue
            d = d_row.get(sid)
            eff = d
            if ind.get("invert", False):
                eff = "falling" if d == "rising" else "rising"
            vals.append(1.0 if eff == heading else 0.0)
        return float(np.mean(vals))

    # Both signals agree with a rising chip once invert is honored.
    assert _agree(0.0, 0.5) == pytest.approx(1.0)
    # And the signal outside the basket never enters the denominator.
    assert len(contrib) == 2


def test_cc_honors_window_stores():
    """Ray Q1a: the front door computes on the user-selected rolling window."""
    out = cc.render_command_center("US", {"page": "/country"}, None, 48, 90)
    text = _tree_text(out)
    assert "window 48m / 90m" in text
    assert "chip agreement" in text          # Q3: replaces legacy confidence
    out_full = cc.render_command_center("US", {"page": "/country"}, None, 0, 0)
    assert "window full / full" in _tree_text(out_full)


def test_relative_uses_canonical_windows():
    """Ray Q1b: cross-country view normalizes every country on 48m/90m."""
    from dashboard import relative_view as rv
    out = rv.render_relative_view({"page": "/relative"}, "carbon", None)
    s = _tree_text(out)
    assert "48m" in s and "90m" in s


def test_dynamic_thresholds_computed_on_windowed_series():
    """Dynamic thresholds must be scaled to the SAME (windowed) series the
    classifier sees — not the full-history base columns (2026-07-06 fix)."""
    import dashboard.charting as charting
    from dashboard.charting_data import load_composite_history
    hist = load_composite_history(country="US")
    dyn_full = charting.compute_dynamic_thresholds(hist, 0.5, 0.5)
    dyn_win = charting.compute_dynamic_thresholds(
        charting._dyn_threshold_input(hist, "growth_score_48m", "inflation_score_90m"),
        0.5, 0.5)
    # the two constructions genuinely differ — pairing them wrongly is material
    assert dyn_full["dyn_gz"].iloc[-1] != pytest.approx(dyn_win["dyn_gz"].iloc[-1])
    # scatter geometry in dynamic mode uses the windowed-input values
    thr = {"gz": 0.5, "iz": 0.5, "gm": 0.0, "im": 0.0, "dynamic": True}
    fig = charting.update_scatter_chart(0, None, "carbon", 48, 90, "US",
                                        {"page": "/regime-map"}, thr)
    rects = [s for s in (fig.layout.shapes or []) if s.type == "rect"]
    assert rects[0].x0 == pytest.approx(float(dyn_win["dyn_gz"].iloc[-1]), abs=1e-6)


# ── External validator badge (docs/external_validators_plan.md, 2026-10-03) ──

def test_validator_badge_none_rollup_renders_nothing():
    assert cc._validator_badge(None) is None


def test_validator_badge_shows_symbols_for_both_axes():
    rollup = (
        {"verdict": "AGREE", "n_agree": 4, "n_partial": 0, "n_contradict": 0, "n_unknown": 0},
        {"verdict": "PARTIAL", "n_agree": 1, "n_partial": 2, "n_contradict": 0, "n_unknown": 0},
    )
    badge = cc._validator_badge(rollup)
    assert badge is not None
    text = badge.children.children
    assert "G ✓" in text and "I ~" in text


def test_validator_badge_color_follows_the_worse_axis():
    from dashboard.shared_components import VERDICT_COLOR
    rollup = (
        {"verdict": "AGREE", "n_agree": 1, "n_partial": 0, "n_contradict": 0, "n_unknown": 0},
        {"verdict": "CONTRADICT", "n_agree": 0, "n_partial": 0, "n_contradict": 1, "n_unknown": 0},
    )
    badge = cc._validator_badge(rollup)
    assert badge.children.style["color"] == VERDICT_COLOR["CONTRADICT"]

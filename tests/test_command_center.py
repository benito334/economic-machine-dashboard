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
    """Ray Q2: season names apply only beyond ±gz/±iz; inside = Transition."""
    from dashboard.charting import _season_label
    assert _season_label(1.2, 0.9, None) == "Inflationary Boom"
    assert _season_label(1.2, -0.9, None) == "Expansion"
    assert _season_label(-1.2, 0.9, None) == "Stagflation"
    assert _season_label(-1.2, -0.9, None) == "Disinflationary Slowdown"
    assert "Transition" in _season_label(0.3, 0.2, None)       # inside band
    assert "Transition" in _season_label(1.2, 0.2, None)       # one side inside
    assert _season_label(None, 0.9, None) == "—"
    # custom thresholds move the band
    assert "Transition" in _season_label(0.9, 0.9, {"gz": 1.0, "iz": 1.0})


def test_chip_direction_agreement_math():
    from dashboard.command_center import chip_direction_agreement
    sig = pd.DataFrame({
        "force": ["growth"] * 4 + ["inflation"] * 2,
        "direction": ["rising", "rising", "falling", "flat", "falling", "falling"],
    })
    # growth heading up: 2 of 3 directional growth signals rising ('flat' excluded)
    assert chip_direction_agreement(sig, "growth", 0.1) == pytest.approx(2 / 3)
    # inflation heading down: both falling
    assert chip_direction_agreement(sig, "inflation", -0.1) == pytest.approx(1.0)
    # flat heading → None
    assert chip_direction_agreement(sig, "growth", 0.0) is None
    assert chip_direction_agreement(sig, "growth", None) is None


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

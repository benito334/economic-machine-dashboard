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
                  "Debt-service ratio", "Productivity trend"):
        assert label in text, f"missing card: {label}"
    # Planned placeholders for the two unbuilt layers
    assert "Phase C" in text and "Phase D" in text
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

"""Tests for the User Guide training course (route /guide)."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import pytest
from dash import html, no_update

from dashboard import user_guide as ug


def _text(component) -> str:
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
        title = getattr(c, "title", None)      # dbc.AccordionItem stores it as a prop
        if isinstance(title, str):
            parts.append(title)
        walk(getattr(c, "children", None))

    walk(component)
    return " ".join(parts)


def test_layout_returns_div():
    lay = ug.get_layout()
    assert isinstance(lay, html.Div)
    assert "guide-content" in str(lay)


def test_all_lessons_present_in_ray_order():
    """Ray's pedagogy ruling: debt-cycle hook comes BEFORE the dial mechanics."""
    out = ug.render_guide("US", "carbon", {"page": "/guide"}, None, 48, 90)
    text = _text(out)
    order = ["machine in one picture", "long-term debt cycle in 60 seconds",
             "two dials", "Chips, thresholds, and windows", "Regime Map",
             "Debt Stress vs Stage", "Productivity and Order",
             "Diversification", "reading routine"]
    positions = [text.find(x) for x in order]
    assert all(p >= 0 for p in positions), f"missing lesson: {order[positions.index(-1)]}"
    assert positions == sorted(positions), "lessons out of Ray's teaching order"


def test_three_traps_taught():
    out = ug.render_guide("US", "carbon", {"page": "/guide"}, None, 48, 90)
    text = _text(out)
    assert "a Z-score is not a grade" in text
    assert "magnitude is not direction" in text
    assert "never trust the two dials alone" in text


def test_live_data_woven_in():
    out = ug.render_guide("US", "carbon", {"page": "/guide"}, None, 48, 90)
    text = _text(out)
    assert text.count("On your dashboard right now") >= 5
    assert "United States" in text


@pytest.mark.parametrize("country", ["EZ", "GB", "JP", "KR"])
def test_renders_for_sparse_countries(country):
    out = ug.render_guide(country, "carbon", {"page": "/guide"}, None, 48, 90)
    assert "machine in one picture" in _text(out)


def test_page_guard():
    assert ug.render_guide("US", "carbon", {"page": "/charts"}, None) is no_update


def test_route_and_nav_registered():
    import dashboard.charting as charting
    assert charting._PAGE_MAP["/guide"] is charting._page_user_guide

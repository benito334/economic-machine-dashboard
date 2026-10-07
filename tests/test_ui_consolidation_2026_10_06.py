"""UI consolidation pass, 2026-10-06.

Pins the decisions from that session so a later refactor doesn't silently
undo them:

  * every sidebar nav group is a click-to-roll <details>, not a fixed label
  * the Signals sub-pages are ordinary nav rows (icon + text), not the old
    smaller "↳ Growth" sub-links
  * Monitor pages lay their cards out two across
  * Fed Monitor absorbed the Yield Curve page (§①) and the Central Bank
    Monitor (§⑦, the one country-reactive section)
  * the Relative Cycles stage chip's ⚠ is hazard-colored, not stage-colored
  * the sidebar Feedback control is a solid amber button, not a link

These are deliberate UI choices, each from an explicit instruction — not
incidental styling. See docs/worklog.md 2026-10-06.
"""
import pytest
from dash import dcc
from dash import html as dhtml
from dash.development.base_component import Component


def _walk(node):
    """Recursively yield every Dash component in a layout tree."""
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    if not isinstance(node, Component):
        return
    yield node
    yield from _walk(getattr(node, "children", None))


def _texts(node) -> list[str]:
    out = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, (list, tuple)):
        for item in node:
            out.extend(_texts(item))
    elif isinstance(node, Component):
        out.extend(_texts(getattr(node, "children", None)))
    return out


# ── Sidebar nav ───────────────────────────────────────────────────────────────

_EXPECTED_GROUPS = {
    "Overviews", "Regime & Cycles", "Monitors", "Signals", "Tools",
    "Reference / Admin",
}


def _nav_groups(nav) -> dict[str, dhtml.Details]:
    """Group header text -> the <details> element, for every nav group."""
    out = {}
    for node in _walk(nav):
        if not isinstance(node, dhtml.Details):
            continue
        summary = next((c for c in _walk(node.children)
                        if isinstance(c, dhtml.Summary)), None)
        if summary is None:
            continue
        for txt in _texts(summary):
            if txt in _EXPECTED_GROUPS:
                out[txt] = node
                break
    return out


def test_every_nav_group_is_a_rollup():
    """Overviews / Regime & Cycles / Monitors used to be fixed `_label()`
    headings with an always-open dbc.Nav under them, so the sidebar had two
    different kinds of section. All six are <details> now."""
    from dashboard.charting import _left_nav

    groups = _nav_groups(_left_nav())
    assert set(groups) == _EXPECTED_GROUPS, f"nav groups drifted: {sorted(groups)}"


def test_no_fixed_section_labels_remain_in_the_nav():
    from dashboard.charting import _left_nav

    labels = [n for n in _walk(_left_nav())
              if getattr(n, "className", None) == "sidebar-section-label"]
    assert labels == [], "a nav group regressed to a non-collapsible label"


def test_signals_subpages_look_like_every_other_nav_row():
    """They were `_sub()` links — no icon, 0.78rem, a "↳ " text prefix. Now
    plain `_nl()` rows, so a row under Signals matches a row under Monitors."""
    import dash_bootstrap_components as dbc

    from dashboard.charting import _left_nav

    signals = _nav_groups(_left_nav())["Signals"]
    links = [n for n in _walk(signals.children) if isinstance(n, dbc.NavLink)]
    hrefs = {lk.href for lk in links}
    assert "/signals" in hrefs
    for force in ("growth", "inflation", "rate", "credit", "volatility",
                  "productivity"):
        assert f"/signals/{force}" in hrefs

    for lk in links:
        assert lk.className == "py-1 px-3 small sidebar-nav-link", (
            f"{lk.href} does not use the shared nav-row class")
        assert "sidebar-subnav" not in (lk.className or "")
        icons = [n for n in _walk(lk.children)
                 if getattr(n, "className", None) == "nav-icon"]
        assert len(icons) == 1, f"{lk.href} is missing its nav icon"
        assert not any(t.strip().startswith("↳") for t in _texts(lk)), (
            f"{lk.href} still carries the old sub-link arrow")


def test_every_nav_link_has_a_distinct_id():
    """dbc.NavLink rejects id=None, so a missing nav_id is a hard crash on
    import — this keeps the failure legible if a new row forgets one."""
    import dash_bootstrap_components as dbc

    from dashboard.charting import _left_nav

    ids = [lk.id for lk in _walk(_left_nav()) if isinstance(lk, dbc.NavLink)]
    assert all(isinstance(i, str) and i for i in ids)
    assert len(ids) == len(set(ids)), "duplicate nav link id"


def test_bubble_gauge_nav_icon_is_an_assigned_codepoint():
    """It rendered as a tofu box: U+1FAC7 is unassigned (the intended glyph,
    BUBBLES, is U+1FAE7)."""
    import unicodedata

    from dashboard.charting import _left_nav

    icons = [t for n in _walk(_left_nav())
             if getattr(n, "className", None) == "nav-icon"
             for t in _texts(n)]
    assert icons
    for glyph in icons:
        for ch in glyph.strip():
            if ord(ch) < 0x2000:         # plain ASCII/latin, nothing to check
                continue
            try:
                unicodedata.name(ch)
            except ValueError:
                pytest.fail(f"nav icon {glyph!r} contains unassigned U+{ord(ch):04X}")


def test_retired_pages_are_gone_from_the_nav_but_still_route():
    from dashboard.charting import _PAGE_MAP, _left_nav, _page_fed_monitor

    hrefs = {getattr(n, "href", None) for n in _walk(_left_nav())}
    assert "/yield-curve" not in hrefs
    assert "/central-bank" not in hrefs
    # ...but both still resolve, so old links and bookmarks don't 404.
    assert _PAGE_MAP["/yield-curve"] is _page_fed_monitor
    assert _PAGE_MAP["/central-bank"] is _page_fed_monitor


def test_renamed_pages_use_the_new_labels_in_the_nav():
    from dashboard.charting import _left_nav

    nav_text = " ".join(_texts(_left_nav()))
    assert "Debt Cycle Monitor" in nav_text
    assert "Case Study" not in nav_text
    assert "Regime Validator" in nav_text
    assert "Validator Audit" not in nav_text
    assert "Central Bank Monitor" not in nav_text


# ── Feedback button ───────────────────────────────────────────────────────────

def test_feedback_button_is_a_solid_amber_button(monkeypatch):
    """As a muted color="link" row it read as one more nav destination."""
    from dashboard import feedback

    monkeypatch.setattr(feedback, "ENDPOINT", "https://example.invalid/post")
    monkeypatch.setattr(feedback, "TOKEN", "t0ken")
    btn = next(n for n in _walk(feedback.nav_button())
               if getattr(n, "id", None) == "feedback-btn")
    assert btn.color == "warning"
    # size="sm" is what every neighbouring control uses; this one is bigger.
    assert getattr(btn, "size", None) is None
    assert float(btn.style["fontSize"].rstrip("rem")) > 0.875


def test_feedback_button_still_hidden_without_an_endpoint(monkeypatch):
    from dashboard import feedback

    monkeypatch.setattr(feedback, "ENDPOINT", "")
    monkeypatch.setattr(feedback, "TOKEN", "")
    assert feedback.nav_button() is None


# ── Two-across card grids ────────────────────────────────────────────────────

def _card_grids(layout) -> list[dhtml.Div]:
    """Every `_section(..., columns=N)` grid container in a layout."""
    return [n for n in _walk(layout)
            if getattr(n, "className", None) == "mon-grid"]


def test_section_columns_emits_a_responsive_grid():
    from dashboard.shared_components import _section

    sec = _section("t", "s", [dhtml.Div("a"), dhtml.Div("b")], columns=2)
    grid = _card_grids(sec)
    assert len(grid) == 1
    assert grid[0].style["gridTemplateColumns"] == "repeat(2, minmax(0, 1fr))"
    # `.mon-grid` carries the mobile collapse + the min-width override that
    # keeps a 280px card from forcing sideways scroll on a phone.
    assert grid[0].className == "mon-grid"


def test_section_without_columns_keeps_the_flex_row():
    from dashboard.shared_components import _section

    sec = _section("t", "s", [dhtml.Div("a")])
    assert _card_grids(sec) == []


@pytest.mark.integration
@pytest.mark.parametrize("module", [
    "dashboard.fed_monitor",
    "dashboard.case_study_monitor",
    "dashboard.bubble_gauge_monitor",
])
def test_monitor_pages_lay_out_two_across(module):
    import importlib

    try:
        layout = importlib.import_module(module).get_layout()
    except Exception:                       # DB-guarded, house convention
        pytest.skip(f"{module} layout could not be built (signals DB absent)")

    grids = _card_grids(layout)
    assert grids, f"{module} has no fixed-column card grid"
    for g in grids:
        assert g.style["gridTemplateColumns"] == "repeat(2, minmax(0, 1fr))"


# ── Fed Monitor absorbed two pages ───────────────────────────────────────────

@pytest.mark.integration
def test_fed_monitor_leads_with_the_yield_curve_section():
    from dashboard.fed_monitor import get_layout

    texts = _texts(get_layout())
    heads = [t for t in texts if t.startswith(("①", "②", "③", "④", "⑤", "⑥"))]
    assert heads, "Fed Monitor's numbered section headings disappeared"
    assert heads[0].startswith("① Yield curve")
    # The term structure is a maturity-axis chart, so it can't be a _chart_card.
    assert any("Treasury term structure" in t for t in texts)


@pytest.mark.integration
def test_fed_monitor_shows_the_10y2y_curve_exactly_once_in_section_one():
    """It used to appear in §1 as well; §① would have made that a visible
    duplicate of an adjacent card."""
    from dashboard.fed_monitor import get_layout

    titles = _texts(get_layout())
    assert titles.count("Yield curve (10y − 2y)") == 1


def test_fed_monitor_central_bank_section_is_country_reactive():
    """The merge must not quietly turn the cross-country read into a US-only
    one — Euro Area and Japan had no other home."""
    from dashboard.fed_monitor import _CB_COVERAGE, render_fed_central_bank_section

    assert set(_CB_COVERAGE) == {"US", "EZ", "JP"}
    for cc, bank in (("US", "Federal Reserve"),
                     ("EZ", "European Central Bank"),
                     ("JP", "Bank of Japan")):
        out = render_fed_central_bank_section({"page": "/fed"}, cc)
        assert any(bank in t for t in _texts(out)), f"{cc} lost its balance-sheet read"


def test_fed_monitor_central_bank_section_documents_the_gb_gap():
    """GB has no live FRED balance-sheet source at all (every BOE series is
    discontinued or years stale). Shown explicitly, never silently omitted."""
    from dashboard.fed_monitor import _central_bank_section

    txt = " ".join(_texts(_central_bank_section("GB")))
    assert "No live central-bank balance-sheet source for United Kingdom" in txt, (
        "the gap message must name the country, not print the bare code")
    assert "Bank of England" in txt


def test_central_bank_section_names_every_country_it_cannot_cover():
    """_CB_NAMES came over covering only US/EZ/JP, but it is what the
    not-covered message renders, so it needs the full selector list."""
    from dashboard.charting import _left_nav
    from dashboard.fed_monitor import _CB_NAMES

    selector = next(n for n in _walk(_left_nav())
                    if getattr(n, "id", None) == "country-selector")
    for opt in selector.options:
        assert opt["value"] in _CB_NAMES, f"{opt['value']} would render as a bare code"


def test_fed_monitor_central_bank_section_ignores_other_pages():
    from dash import no_update

    from dashboard.fed_monitor import render_fed_central_bank_section

    assert render_fed_central_bank_section({"page": "/relative"}, "US") is no_update


# ── Relative Cycles ──────────────────────────────────────────────────────────

def test_stage_warning_glyph_is_hazard_colored_not_stage_colored():
    """A green 'reflation' stage chip rendered its ⚠ in green, which is how a
    live sovereign-squeeze warning vanished into its own chip."""
    from dashboard.relative_view import HAZARD, _chip

    chip = _chip("Stage · reflation", "#2e9e5b", hazard="⚠")
    warn = next(n for n in _walk(chip.children)
                if isinstance(n, dhtml.Span) and "⚠" in " ".join(_texts(n)))
    assert warn.style["color"] == HAZARD
    assert HAZARD != "#2e9e5b"


def test_chip_without_a_hazard_is_unchanged():
    from dashboard.relative_view import _chip

    chip = _chip("Stage · reflation", "#2e9e5b")
    assert _texts(chip) == ["Stage · reflation"]


def test_relative_cycles_country_cards_are_two_across():
    from dashboard.relative_view import _CARD, _GRID_2

    assert _GRID_2["gridTemplateColumns"] == "repeat(2, minmax(0, 1fr))"
    # Grid items, so the old flex basis must not reimpose a 260px floor.
    assert _CARD["minWidth"] == "0"
    assert "flex" not in _CARD


def test_correlation_heatmaps_scale_with_the_country_count():
    """14x14 at the old fixed 260px was ~18px of vertical space per row, with
    the numbers unreadable. Height is derived from the matrix now, so adding
    a country grows the chart instead of shrinking its cells."""
    import pandas as pd

    from dashboard.relative_view import COUNTRIES, _CORR_MIN_HEIGHT, _corr_heatmap

    def _height(n):
        ccs = [f"C{i}" for i in range(n)]
        corr = pd.DataFrame(1.0, index=ccs, columns=ccs)
        graph = _corr_heatmap(corr, "t", "carbon")
        assert isinstance(graph, dcc.Graph)
        # Full page width, one per row — not a half-width flex item any more.
        assert graph.style["width"] == "100%"
        assert "flex" not in graph.style
        return graph.figure.layout.height

    small, live, bigger = _height(4), _height(len(COUNTRIES)), _height(len(COUNTRIES) + 4)
    assert small == _CORR_MIN_HEIGHT, "a tiny matrix should still clear the floor"
    assert live > 260, "the live 14-country matrix must be taller than the old fixed 260px"
    assert bigger > live, "height must grow with the matrix, not compress it"

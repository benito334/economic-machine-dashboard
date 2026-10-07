"""Tests for the productivity-vs-cyclical-growth divergence read
(Ray Dalio consult, 2026-08-19 session)."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import math

from dashboard.force_detail import _productivity_divergence


def test_rising_productivity_soft_growth_is_early_advantage():
    note = _productivity_divergence(prod_z=0.6, growth_z=0.1, thresh_gz=0.5)
    assert note is not None
    assert note["label"] == "Early-stage competitive advantage"


def test_falling_productivity_strong_growth_is_unsustainable_watch():
    note = _productivity_divergence(prod_z=-0.6, growth_z=0.8, thresh_gz=0.5)
    assert note is not None
    assert note["label"] == "Unsustainable-expansion watch"


def test_aligned_productivity_and_growth_has_no_note():
    # both positive and both above threshold — no divergence
    assert _productivity_divergence(prod_z=0.7, growth_z=0.7, thresh_gz=0.5) is None
    # both negative / below threshold — no divergence
    assert _productivity_divergence(prod_z=-0.2, growth_z=-0.2, thresh_gz=0.5) is None


def test_missing_inputs_return_none():
    assert _productivity_divergence(None, 0.5, 0.5) is None
    assert _productivity_divergence(0.5, None, 0.5) is None
    assert _productivity_divergence(float("nan"), 0.5, 0.5) is None
    assert _productivity_divergence(0.5, float("nan"), 0.5) is None


def test_threshold_is_reused_from_gz_not_hardcoded():
    """A growth_z that clears a looser threshold shouldn't trigger 'soft
    growth' — the same gz threshold the Growth chip itself uses."""
    assert _productivity_divergence(prod_z=0.4, growth_z=0.6, thresh_gz=0.5) is None
    assert _productivity_divergence(prod_z=0.4, growth_z=0.4, thresh_gz=0.5) is not None


# ── Banner / composite-card threshold readout ─────────────────────────────────
# The banner's THRESHOLD cell and the composite card's dashed bands used to be
# wired straight to `regime-threshold-store`, which only ever holds the
# sliders' BASE values. With dynamic mode on (the default) the classifier uses
# the country-vol-scaled value instead — US growth, Oct 2026: 0.226, not 0.50 —
# so /signals/growth drew the score (+0.374) comfortably below a band it had in
# fact cleared. Same bug class as commit ee3d3ed on the Regime History header,
# and it reuses that fix's helpers.

import pandas as pd

from dashboard.force_detail import (
    _build_banner,
    _build_force_cards,
    _threshold_text,
)


def _text(node) -> str:
    """Flatten a Dash component tree to its visible text."""
    if isinstance(node, str):
        return node
    children = getattr(node, "children", None)
    if children is None:
        return ""
    if isinstance(children, list):
        return "".join(_text(c) for c in children)
    return _text(children)


_BASE = {"gz": 0.50, "iz": 0.50, "gm": 0.05, "im": 0.05, "dynamic": True}
_EFF  = {"gz": 0.226, "iz": 0.150, "gm": 0.05, "im": 0.05, "dynamic": True}


def test_threshold_text_shows_effective_with_base_in_parens():
    val, s, sub, title = _threshold_text(_EFF, _BASE, "gz")
    assert val == 0.226
    assert s == "±0.23"          # effective — what the classifier used
    assert sub == "(±0.50)"      # base — what the slider is set to
    assert "0.23" in title and "0.50" in title


def test_threshold_text_omits_base_when_dynamic_is_off():
    static = {**_BASE, "dynamic": False}
    val, s, sub, title = _threshold_text(static, static, "gz")
    assert (val, s, sub, title) == (0.50, "±0.50", None, None)


def test_threshold_text_omits_base_when_scaling_did_not_move_it():
    same = dict(_BASE)
    _, s, sub, _t = _threshold_text(same, same, "gz")
    assert s == "±0.50" and sub is None


def test_banner_threshold_cell_reports_the_dynamic_value_not_the_base():
    """The regression this fix is for: with dynamic mode on the banner must
    read the value in force, with the slider base only as a parenthetical."""
    banner = _build_banner("growth", comp_z=0.3741, momentum=0.6,
                           n_active=8, n_total=9, n_agreement=5,
                           thresholds=_EFF, lookback_label="48m",
                           base_thresholds=_BASE)
    text = _text(banner)
    assert "±0.23" in text, text
    assert "(±0.50)" in text, text


def test_banner_inflation_page_uses_iz_not_gz():
    """/signals/inflation has its own threshold; it must not inherit growth's."""
    banner = _build_banner("inflation", comp_z=0.0325, momentum=0.5,
                           n_active=8, n_total=8, n_agreement=4,
                           thresholds=_EFF, lookback_label="90m",
                           base_thresholds=_BASE)
    text = _text(banner)
    assert "±0.15" in text, text        # iz, not gz's 0.23
    assert "±0.23" not in text, text


def test_banner_shows_plain_base_when_dynamic_is_off():
    static = {**_BASE, "dynamic": False}
    banner = _build_banner("growth", comp_z=0.37, momentum=0.6,
                           n_active=8, n_total=9, n_agreement=5,
                           thresholds=static, lookback_label="48m",
                           base_thresholds=static)
    text = _text(banner)
    assert "±0.50" in text
    assert "(±" not in text


def test_banner_threshold_is_na_for_forces_without_one():
    banner = _build_banner("credit", comp_z=0.1, momentum=0.5,
                           n_active=5, n_total=7, n_agreement=3,
                           thresholds=_EFF, lookback_label="Full",
                           base_thresholds=_BASE)
    assert "N/A" in _text(banner)


def _comp_hist() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=24, freq="MS")
    return pd.DataFrame({
        "as_of": dates,
        "growth_score": [0.30] * 24,
        "growth_momentum": [0.6] * 24,
    })


def _figures(node) -> list:
    """Every Plotly figure in a Dash component tree, in render order."""
    out = []
    fig = getattr(node, "figure", None)
    if fig is not None:
        out.append(fig)
    children = getattr(node, "children", None)
    if isinstance(children, list):
        for c in children:
            out.extend(_figures(c))
    elif children is not None:
        out.extend(_figures(children))
    return out


def _hlines(cards) -> list:
    """The dashed-threshold y-positions on the composite card's figure."""
    figs = [f for c in cards for f in _figures(c)]
    assert figs, "no chart card rendered"
    return sorted(round(float(sh.y0), 4) for sh in figs[0].layout.shapes
                  if getattr(sh, "y0", None) is not None and sh.y0 == sh.y1)


def test_composite_card_bands_are_drawn_at_the_dynamic_threshold():
    cards = _build_force_cards(
        "growth", [], {}, {}, _comp_hist(), pd.DataFrame(), pd.DataFrame(),
        thresholds=_EFF, base_thresholds=_BASE,
    )
    ys = _hlines(cards)
    assert -0.226 in ys and 0.226 in ys, ys
    assert 0.50 not in ys and -0.50 not in ys, ys


def test_composite_card_caption_names_both_the_dynamic_value_and_the_base():
    cards = _build_force_cards(
        "growth", [], {}, {}, _comp_hist(), pd.DataFrame(), pd.DataFrame(),
        thresholds=_EFF, base_thresholds=_BASE,
    )
    text = _text(cards[0])
    assert "±0.23" in text and "0.50" in text, text


def test_composite_card_bands_use_the_base_when_dynamic_is_off():
    static = {**_BASE, "dynamic": False}
    cards = _build_force_cards(
        "growth", [], {}, {}, _comp_hist(), pd.DataFrame(), pd.DataFrame(),
        thresholds=static, base_thresholds=static,
    )
    ys = _hlines(cards)
    assert -0.50 in ys and 0.50 in ys, ys

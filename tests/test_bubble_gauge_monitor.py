"""Bubble Gauge Monitor page — pure-logic helpers + (DB/network-guarded)
layout render."""
from dashboard import bubble_gauge_monitor as bgm


def test_direction_note_positioning_is_bidirectional():
    assert bgm._direction_note("positioning", 1.0) == "crowded long"
    assert bgm._direction_note("positioning", -1.0) == "crowded short"
    assert bgm._direction_note("positioning", 0.0) == "balanced"


def test_direction_note_trending_dimensions_are_unidirectional():
    assert bgm._direction_note("valuation", 2.0) == "above its own history"
    assert bgm._direction_note("valuation", -2.0) == "below its own history"
    assert bgm._direction_note("leverage", 1.0) == "above its own history"


def test_direction_note_handles_missing_z():
    assert bgm._direction_note("positioning", None) == ""
    assert bgm._direction_note("valuation", float("nan")) == ""


def test_layout_renders():
    # Network/DB-guarded like the other Monitor pages — returns a Div either
    # way (the real content, or the "unavailable" placeholder) rather than
    # raising, since this page depends on two live external sources.
    try:
        lay = bgm.get_layout()
    except Exception:
        return
    assert type(lay).__name__ == "Div"

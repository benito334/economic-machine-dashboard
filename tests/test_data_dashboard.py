"""Data Feed Monitor — status badge logic.

Locks in the 2026-08-16 fix: the badge column used to (1) recompute staleness
with its own hardcoded, override-blind heuristic that disagreed with the
pipeline's real is_stale flag, and (2) let informational metadata (PROXY /
DERIVED / NO VINTAGE) suppress the "OK" badge even when nothing was actually
wrong. Both collapsed the "89/90 OK" summary count against a table where
almost no row showed OK and a third showed a false "release overdue" alarm.
"""
import pandas as pd

from dashboard import data_dashboard as dd


def _row(**overrides) -> pd.Series:
    base = {
        "is_stale": False, "low_history": False, "is_proxy": False,
        "is_constructed": False, "vintage_available": True,
    }
    base.update(overrides)
    return pd.Series(base)


def _labels(badges) -> list[str]:
    def _text(node) -> str:
        c = node.children
        if isinstance(c, list):
            return "".join(_text(x) if hasattr(x, "children") else str(x) for x in c)
        return str(c) if c is not None else ""
    return [_text(b) for b in badges]


def test_clean_signal_is_ok_only():
    badges = dd._badges(_row(), "2026-07-01", "M", None)
    assert _labels(badges) == ["✓ OK"]


def test_in_window_carry_without_override_is_still_ok():
    """A monthly signal ~60 days old is well inside the 90-day generic
    window (indicators/normalize.py's _STALE_THRESHOLDS) even with no
    stale_after_days override — must not alarm."""
    as_of = (pd.Timestamp.today() - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    badges = dd._badges(_row(is_stale=False), as_of, "M", None)
    assert _labels(badges) == ["✓ OK"]


def test_stale_after_days_override_prevents_false_alarm():
    """A quarterly signal 220 days old blows the generic 200-day window but
    is fine under a real stale_after_days=260 override (e.g. the Z.1/BEA
    credit signals) — is_stale reflects the override already, so trust it."""
    as_of = (pd.Timestamp.today() - pd.Timedelta(days=220)).strftime("%Y-%m-%d")
    badges = dd._badges(_row(is_stale=False), as_of, "Q", 260)
    assert _labels(badges) == ["✓ OK"]


def test_genuinely_stale_signal_badges_stale_with_day_count():
    as_of = (pd.Timestamp.today() - pd.Timedelta(days=300)).strftime("%Y-%m-%d")
    badges = dd._badges(_row(is_stale=True), as_of, "Q", 200)
    labels = _labels(badges)
    assert len(labels) == 1
    assert labels[0].startswith("STALE +")


def test_metadata_badges_do_not_suppress_ok():
    """PROXY / DERIVED / NO VINTAGE are informational and must render
    alongside OK, never instead of it."""
    badges = dd._badges(
        _row(is_proxy=True, is_constructed=True, vintage_available=False),
        "2026-07-01", "M", None,
    )
    labels = _labels(badges)
    assert "✓ OK" in labels
    assert "PROXY" in labels
    assert "DERIVED" in labels
    assert "NO VINTAGE" not in labels  # suppressed when is_constructed (derived series never had vintage anyway)


def test_no_vintage_badge_alongside_ok_for_plain_fred_series():
    badges = dd._badges(_row(vintage_available=False), "2026-07-01", "M", None)
    labels = _labels(badges)
    assert "✓ OK" in labels
    assert "NO VINTAGE" in labels


def test_stale_and_low_history_both_render_no_ok():
    badges = dd._badges(_row(is_stale=True, low_history=True), "2020-01-01", "M", None)
    labels = _labels(badges)
    assert "✓ OK" not in labels
    assert any(l.startswith("STALE") for l in labels)
    assert "LOW HIST" in labels


def test_has_issue_matches_is_stale_or_low_history_only():
    assert dd._has_issue(_row(is_proxy=True, is_constructed=True, vintage_available=False)) is False
    assert dd._has_issue(_row(is_stale=True)) is True
    assert dd._has_issue(_row(low_history=True)) is True


def test_status_sort_key_ranks_alarms_above_metadata_above_ok():
    stale   = dd._status_sort_key(_row(is_stale=True))
    low     = dd._status_sort_key(_row(low_history=True))
    proxy   = dd._status_sort_key(_row(is_proxy=True))
    derived = dd._status_sort_key(_row(is_constructed=True))
    ok      = dd._status_sort_key(_row())
    assert stale < low < proxy < derived < ok


def test_overdue_days_uses_override_over_generic_default():
    as_of = (pd.Timestamp.today() - pd.Timedelta(days=250)).strftime("%Y-%m-%d")
    # Generic Q default is 200d -> would read +50d overdue; a 260d override
    # means this signal isn't overdue at all yet.
    assert dd._overdue_days(as_of, "Q", 260) < 0
    assert dd._overdue_days(as_of, "Q", None) == 50

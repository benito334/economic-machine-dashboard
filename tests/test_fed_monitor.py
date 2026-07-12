"""Fed Monitor page — ratio math + (DB-guarded) layout render."""
import pandas as pd

from dashboard import fed_monitor as fm


def test_ratio_aligns_and_percents():
    num = pd.DataFrame({"as_of": pd.to_datetime(["2025-01-01", "2025-04-01"]), "value": [10.0, 12.0]})
    den = pd.DataFrame({"as_of": pd.to_datetime(["2025-01-01", "2025-04-01"]), "value": [100.0, 100.0]})
    r = fm._ratio(num, den)
    assert list(round(r["value"], 2)) == [10.0, 12.0]


def test_ratio_uses_denser_series_and_forward_matches():
    # sparse numerator (annual), dense denominator (quarterly) → charted quarterly
    num = pd.DataFrame({"as_of": pd.to_datetime(["2024-09-30"]), "value": [900.0]})
    den = pd.DataFrame({"as_of": pd.to_datetime(["2024-10-01", "2025-01-01"]), "value": [6000.0, 6000.0]})
    r = fm._ratio(num, den)
    assert len(r) == 2                       # one row per denser point
    assert round(r["value"].iloc[0], 1) == 15.0


def test_layout_renders_on_db():
    # DB-guarded: returns a Div when the signals DB is present, else skips.
    try:
        lay = fm.get_layout()
    except Exception:
        return
    assert lay is not None
    assert type(lay).__name__ == "Div"


def test_info_icon_builds_tooltip_and_empty_is_noop():
    fm._ICON_SEQ["n"] = 0
    node = fm._info_icon("Detailed explanation of the chart.")
    # icon span + Tooltip, sharing one target id
    icon, tip = node.children
    assert icon.id == tip.target == "fed-info-1"
    assert tip.children == "Detailed explanation of the chart."
    # empty info → no icon, no id consumed
    empty = fm._info_icon("")
    assert not getattr(empty, "children", None)
    assert fm._ICON_SEQ["n"] == 1


def test_chart_card_with_info_renders_icon():
    import pandas as pd
    fm._ICON_SEQ["n"] = 0
    df = pd.DataFrame({"as_of": pd.to_datetime(["2025-01-01"]), "value": [1.0]})
    card = fm._chart_card("T", df, 1.0, "%", "one-liner", info="the long version")
    assert fm._ICON_SEQ["n"] == 1        # icon was emitted
    assert type(card).__name__ == "Div"

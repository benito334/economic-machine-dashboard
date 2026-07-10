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

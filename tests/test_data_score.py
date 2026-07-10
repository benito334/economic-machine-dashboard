"""Data Confidence scoring — grading, caveats, thin-basket caps."""
from datetime import date

from dashboard import data_score as ds


def test_grade_bands():
    assert ds.grade_of(95)["grade"] == "A"
    assert ds.grade_of(72)["grade"] == "B"
    assert ds.grade_of(60)["grade"] == "C"
    assert ds.grade_of(40)["grade"] == "D"
    # every band carries a colour hex
    assert ds.grade_of(95)["hex"].startswith("#")


def test_fresh_direct_deep_scores_high():
    ref = date(2026, 7, 1)
    # 5 fresh, native signals → A
    sigs = [(date(2026, 6, 1), False, False, False, False)] * 5
    out = ds._force_score(sigs, ref)
    assert out["grade"] == "A"
    assert out["n"] == 5 and out["stale"] == 0 and out["proxy"] == 0


def test_stale_and_proxy_drags_score_down():
    ref = date(2026, 7, 1)
    # 5 signals, 4 stale (2 of them ancient), 2 proxy → should not be A/B
    sigs = [
        (date(2026, 6, 1), False, False, False, False),  # fresh native
        (date(2026, 1, 1), True, True, False, False),     # stale proxy (~6mo)
        (date(2024, 1, 1), True, True, False, False),     # ancient proxy
        (date(2023, 1, 1), True, False, False, False),    # ancient
        (date(2025, 1, 1), True, False, False, False),    # stale (~18mo)
    ]
    out = ds._force_score(sigs, ref)
    assert out["grade"] in ("C", "D")
    assert out["stale"] == 4 and out["proxy"] == 2


def test_thin_basket_is_capped():
    ref = date(2026, 7, 1)
    # a single perfectly-fresh native signal still can't beat C
    one = ds._force_score([(date(2026, 6, 1), False, False, False, False)], ref)
    assert one["grade"] == "C"
    # two fresh natives capped at B, not A
    two = ds._force_score([(date(2026, 6, 1), False, False, False, False)] * 2, ref)
    assert two["grade"] in ("B", "C")


def test_force_caveat_wording():
    fi = {"n": 5, "stale": 4, "proxy": 2}
    assert ds.force_caveat(fi) == "5 signals · 4 stale, 2 proxy"
    assert ds.force_caveat({"n": 1, "stale": 0, "proxy": 0}) == "1 signal"
    assert ds.force_caveat(None) == "no data"


def test_compute_scores_shape_on_live_db():
    scores = ds.compute_scores()
    if not scores:            # DB not present in this env — skip gracefully
        return
    us = scores.get("us")
    assert us is not None
    assert us["overall"]["grade"] in ("A", "B", "C", "D")
    assert "growth" in us["forces"]
    assert us["forces"]["growth"]["n"] >= 1

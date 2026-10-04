"""Tests for dashboard.shared_components pure-logic helpers."""
from dashboard.shared_components import VERDICT_COLOR, summarize_validator_axis


def test_all_agree_rolls_up_to_agree():
    rows = [{"verdict": "AGREE"}, {"verdict": "AGREE"}]
    out = summarize_validator_axis(rows)
    assert out == {"verdict": "AGREE", "n_agree": 2, "n_partial": 0,
                   "n_contradict": 0, "n_unknown": 0}


def test_any_contradict_wins_over_everything():
    rows = [{"verdict": "AGREE"}, {"verdict": "AGREE"}, {"verdict": "CONTRADICT"},
            {"verdict": "PARTIAL"}]
    out = summarize_validator_axis(rows)
    assert out["verdict"] == "CONTRADICT"
    assert out["n_agree"] == 2 and out["n_partial"] == 1 and out["n_contradict"] == 1


def test_any_partial_wins_when_no_contradict():
    rows = [{"verdict": "AGREE"}, {"verdict": "PARTIAL"}]
    assert summarize_validator_axis(rows)["verdict"] == "PARTIAL"


def test_unknown_rows_are_ignored_not_counted_toward_verdict():
    rows = [{"verdict": "UNKNOWN"}, {"verdict": "UNKNOWN"}, {"verdict": "AGREE"}]
    out = summarize_validator_axis(rows)
    assert out["verdict"] == "AGREE"
    assert out["n_unknown"] == 2


def test_all_unknown_or_empty_has_no_verdict():
    assert summarize_validator_axis([{"verdict": "UNKNOWN"}])["verdict"] is None
    assert summarize_validator_axis([])["verdict"] is None


def test_verdict_color_covers_every_verdict_and_unknown_fallback():
    for v in ("AGREE", "PARTIAL", "CONTRADICT", "UNKNOWN"):
        assert v in VERDICT_COLOR

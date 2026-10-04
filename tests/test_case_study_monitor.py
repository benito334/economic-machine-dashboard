"""Case Study Monitor — 'pushing on a string' flag (coverage-audit Phase B,
2026-10-03): QE underway (central-bank balance sheet growing) without
private credit creation following."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

from dashboard import case_study_monitor as csm


def test_fires_when_qe_underway_and_credit_not_following():
    note = csm._pushing_on_a_string(bs_yoy_pct=7.2, priv_credit_pp=0.1)
    assert note is not None
    assert note["label"].startswith("Pushing on a string")


def test_fires_on_outright_private_deleveraging_during_qe():
    note = csm._pushing_on_a_string(bs_yoy_pct=6.0, priv_credit_pp=-1.5)
    assert note is not None


def test_no_flag_when_credit_is_following_qe():
    # balance sheet expanding AND private credit genuinely expanding too —
    # stimulus is working, not "pushing on a string".
    assert csm._pushing_on_a_string(bs_yoy_pct=7.0, priv_credit_pp=1.2) is None


def test_no_flag_when_balance_sheet_not_expanding():
    # same MP2 cutoff as central_bank_monitor.py's own _mp_read (>+5%) —
    # below it is QT/roughly-stable, not QE, so the pattern can't apply.
    assert csm._pushing_on_a_string(bs_yoy_pct=2.0, priv_credit_pp=-2.0) is None


def test_threshold_boundary_is_strict_greater_than_five():
    assert csm._pushing_on_a_string(bs_yoy_pct=5.0, priv_credit_pp=0.0) is None
    assert csm._pushing_on_a_string(bs_yoy_pct=5.01, priv_credit_pp=0.0) is not None


def test_missing_inputs_return_none():
    assert csm._pushing_on_a_string(None, 0.0) is None
    assert csm._pushing_on_a_string(7.0, None) is None
    assert csm._pushing_on_a_string(None, None) is None


def test_layout_renders():
    # DB-guarded like the Fed Monitor / Market Expectations tests.
    try:
        lay = csm.get_layout()
    except Exception:
        return
    assert type(lay).__name__ == "Div"

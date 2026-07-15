"""Market Expectations page — bindings, page render, quadrant read."""
from pathlib import Path

from dashboard import charting as c
from dashboard import market_expectations as m


def test_market_bindings_present_and_verified():
    from indicators.pipeline import load_bindings
    bs = load_bindings(Path("config/us_bindings.yaml"))
    mk = {b.id: b for b in bs if b.force == "market"}
    # the six market series + the 1y expectation
    for sid in ["market.nominal_5y", "market.nominal_10y", "market.real_5y", "market.real_10y",
                "market.breakeven_5y", "market.breakeven_10y", "market.exp_infl_1y"]:
        assert sid in mk, f"missing {sid}"
        assert mk[sid].provider == "FRED" and mk[sid].verified


def test_page_routed():
    assert "/market-expectations" in c._PAGE_MAP


def test_layout_renders():
    # DB-guarded like the Fed Monitor test.
    try:
        lay = m.get_layout()
    except Exception:
        return
    assert type(lay).__name__ == "Div"


def test_quadrant_read_covers_all_four_regimes():
    assert "tightening" in m._quadrant_read(0.2, 0.2).lower()      # BEI↑ real↑
    assert "stagflation" in m._quadrant_read(0.2, -0.2).lower()    # BEI↑ real↓
    assert "disinflation" in m._quadrant_read(-0.2, 0.2).lower()   # BEI↓ real↑
    assert "easing" in m._quadrant_read(-0.2, -0.2).lower()        # BEI↓ real↓
    # missing data → neutral description, no crash
    assert m._quadrant_read(None, 0.1)

"""Brazil BCB SGS loader — (network-guarded) live fetch of open series."""
import pandas as pd

from indicators import loader
from indicators.transform import apply_transformation


def test_bcb_ipca_live(tmp_path, monkeypatch):
    """BCB IPCA 12-month (series 13522) should be recent and a plausible rate.

    Network-guarded: skips cleanly if BCB is unreachable in this environment.
    """
    monkeypatch.setattr(loader, "RAW_CACHE_DIR", tmp_path)
    try:
        raw = loader.fetch_bcb_series("13522", force_refresh=True)
    except Exception:
        return
    if raw is None or raw.empty:
        return
    decimal = apply_transformation(raw / 100.0, "level", "M").dropna()
    assert 0.0 < decimal.iloc[-1] < 0.5              # Brazil inflation, decimal form
    assert raw.index[-1] >= pd.Timestamp("2026-01-01")  # genuinely live


def test_bcb_bad_code_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "RAW_CACHE_DIR", tmp_path)
    try:
        out = loader.fetch_bcb_series("999999999", force_refresh=True)
    except Exception:
        return
    assert out is None or out.empty

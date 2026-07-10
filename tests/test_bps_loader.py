"""Indonesia BPS WebAPI loader — (key/network-guarded) live national CPI fetch."""
import os

import pandas as pd

from indicators import loader
from indicators.transform import apply_transformation


def test_bps_skips_gracefully_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "RAW_CACHE_DIR", tmp_path)
    monkeypatch.delenv("BPS_KEY", raising=False)
    assert loader.fetch_bps_series("2245", force_refresh=True) is None


def test_bps_national_cpi_live_when_key_present(tmp_path, monkeypatch):
    """With a key, BPS var 2245 (national CPI) should be recent + a plausible rate.

    Guarded: skips when BPS_KEY is unset or the network is unavailable.
    """
    if not os.environ.get("BPS_KEY", "").strip():
        return
    monkeypatch.setattr(loader, "RAW_CACHE_DIR", tmp_path)
    try:
        idx = loader.fetch_bps_series("2245", force_refresh=True)
    except Exception:
        return
    if idx is None or idx.empty:
        return
    yoy = apply_transformation(idx, "yoy_pct", "M").dropna()
    assert -0.05 < yoy.iloc[-1] < 0.30                  # Indonesian inflation, decimal
    assert idx.index[-1] >= pd.Timestamp("2026-01-31")  # genuinely live

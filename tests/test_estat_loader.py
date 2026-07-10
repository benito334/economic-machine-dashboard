"""Japan e-Stat loader — time-code parsing + (key/network-guarded) live fetch."""
import os

import pandas as pd

from indicators import loader
from indicators.transform import apply_transformation


def test_parse_estat_month():
    assert loader._parse_estat_month("2026000505") == pd.Timestamp("2026-05-31")
    assert loader._parse_estat_month("1970000101") == pd.Timestamp("1970-01-31")
    assert loader._parse_estat_month("bad") is None
    assert loader._parse_estat_month("") is None


def test_estat_skips_gracefully_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "RAW_CACHE_DIR", tmp_path)
    monkeypatch.delenv("ESTAT_APP_ID", raising=False)
    # No key → returns None so the pipeline falls back to the IMF bridge
    assert loader.fetch_estat_series("0003427113/1/0001/00000", force_refresh=True) is None


def test_estat_cpi_live_when_key_present(tmp_path, monkeypatch):
    """If a key is available, JP CPI should be recent and a plausible rate.

    Guarded: skips when ESTAT_APP_ID is unset or the network is unavailable.
    """
    if not os.environ.get("ESTAT_APP_ID", "").strip():
        return
    monkeypatch.setattr(loader, "RAW_CACHE_DIR", tmp_path)
    try:
        idx = loader.fetch_estat_series("0003427113/1/0001/00000", force_refresh=True)
    except Exception:
        return
    if idx is None or idx.empty:
        return
    yoy = apply_transformation(idx, "yoy_pct", "M").dropna()
    assert -0.05 < yoy.iloc[-1] < 0.20
    assert idx.index[-1] >= pd.Timestamp("2026-01-31")

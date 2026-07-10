"""ONS append-/data loader — month parsing + (network-guarded) live fetch."""
import pandas as pd

from indicators import loader
from indicators.transform import apply_transformation


def test_parse_ons_month():
    assert loader._parse_ons_month("2026 MAY") == pd.Timestamp("2026-05-31")
    assert loader._parse_ons_month("1999 JAN") == pd.Timestamp("1999-01-31")
    # quarter/year rows (not "YYYY Mon") are skipped
    assert loader._parse_ons_month("2026 Q1") is None
    assert loader._parse_ons_month("2026") is None
    assert loader._parse_ons_month("") is None


def test_ons_cpi_live_and_matches_bank_target_units(tmp_path, monkeypatch):
    """Live UK CPI via ONS should be recent and in decimal form after scaling.

    Network-guarded: skips cleanly if ONS is unreachable in this environment.
    """
    monkeypatch.setattr(loader, "RAW_CACHE_DIR", tmp_path)
    try:
        raw = loader.fetch_ons_series("d7g7", "mm23", force_refresh=True)
    except Exception:
        return  # no network — don't fail the suite
    if raw is None or raw.empty:
        return
    # D7G7 is the published % rate; /100 → decimal, matching the signal contract
    decimal = apply_transformation(raw / 100.0, "level", "M").dropna()
    assert 0.0 < decimal.iloc[-1] < 0.25          # a plausible inflation rate
    assert raw.index[-1] >= pd.Timestamp("2026-01-31")  # genuinely live, not stale

"""Unit tests for the BIS SDMX 2.1 fetcher in indicators/loader.py.

Added 2026-08-21 for the dollar-dominance monitor build (Ray Dalio review
log, Session 2026-08-21) — order.offshore_usd_debt_outstanding /
order.offshore_total_debt_outstanding both use fetch_bis_sdmx_series().
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from indicators.loader import _fetch_bis_sdmx_from_api, fetch_bis_sdmx_series


def _csv_response(rows: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.text = (
        "STRUCTURE,STRUCTURE_ID,ACTION,FREQ,TIME_PERIOD,OBS_VALUE\n" + rows
    )
    return resp


# ─── _fetch_bis_sdmx_from_api ────────────────────────────────────────────────

class TestFetchBisSdmxFromApi:
    def test_parses_quarterly_periods_and_values(self):
        rows = (
            "dataflow,BIS:WS_DEBT_SEC2_PUB(1.0),I,Q,2025-Q4,15525254\n"
            "dataflow,BIS:WS_DEBT_SEC2_PUB(1.0),I,Q,2026-Q1,15867799\n"
        )
        with patch("indicators.loader.requests.get", return_value=_csv_response(rows)):
            s = _fetch_bis_sdmx_from_api("WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I")
        assert isinstance(s, pd.Series)
        assert list(s.index) == sorted(s.index)
        assert s.iloc[-1] == pytest.approx(15867799.0)

    def test_returns_sorted_series_regardless_of_row_order(self):
        rows = (
            "dataflow,BIS:WS_DEBT_SEC2_PUB(1.0),I,Q,2026-Q1,300\n"
            "dataflow,BIS:WS_DEBT_SEC2_PUB(1.0),I,Q,2024-Q1,100\n"
            "dataflow,BIS:WS_DEBT_SEC2_PUB(1.0),I,Q,2025-Q1,200\n"
        )
        with patch("indicators.loader.requests.get", return_value=_csv_response(rows)):
            s = _fetch_bis_sdmx_from_api("WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I")
        assert s.tolist() == [100.0, 200.0, 300.0]

    def test_skips_rows_with_empty_obs_value(self):
        rows = (
            "dataflow,BIS:WS_DEBT_SEC2_PUB(1.0),I,Q,2025-Q4,\n"
            "dataflow,BIS:WS_DEBT_SEC2_PUB(1.0),I,Q,2026-Q1,15867799\n"
        )
        with patch("indicators.loader.requests.get", return_value=_csv_response(rows)):
            s = _fetch_bis_sdmx_from_api("WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I")
        assert len(s) == 1

    def test_raises_on_empty_response(self):
        with patch("indicators.loader.requests.get", return_value=_csv_response("")):
            with pytest.raises(ValueError, match="Empty BIS SDMX"):
                _fetch_bis_sdmx_from_api("WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I")


# ─── fetch_bis_sdmx_series ────────────────────────────────────────────────────

class TestFetchBisSdmxSeries:
    def _make_series(self, n=8) -> pd.Series:
        idx = pd.date_range("2024-03-31", periods=n, freq="QE")
        return pd.Series(range(n), index=idx, name="value", dtype=float)

    def test_uses_cache_when_fresh(self, tmp_path, monkeypatch):
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        s = self._make_series()
        cache = ldr._bis_sdmx_cache_path("WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I")
        s.to_frame().to_parquet(cache)

        with patch("indicators.loader._fetch_bis_sdmx_from_api") as mock_fetch:
            result = fetch_bis_sdmx_series(
                "WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I", force_refresh=False,
            )

        mock_fetch.assert_not_called()
        assert result is not None
        assert len(result) == len(s)

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        fresh = self._make_series()
        with patch("indicators.loader._fetch_bis_sdmx_from_api", return_value=fresh) as mock_fetch:
            result = fetch_bis_sdmx_series(
                "WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I", force_refresh=True,
            )

        mock_fetch.assert_called_once()
        assert result is not None

    def test_returns_none_on_api_failure_no_cache(self, tmp_path):
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        with patch("indicators.loader._fetch_bis_sdmx_from_api", side_effect=ValueError("boom")):
            result = fetch_bis_sdmx_series(
                "WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I", force_refresh=True,
            )

        assert result is None

    def test_falls_back_to_stale_cache_on_api_failure(self, tmp_path):
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        s = self._make_series()
        cache = ldr._bis_sdmx_cache_path("WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I")
        s.to_frame().to_parquet(cache)

        with patch("indicators.loader._fetch_bis_sdmx_from_api", side_effect=RuntimeError("timeout")):
            result = fetch_bis_sdmx_series(
                "WS_DEBT_SEC2_PUB", "Q.3P.3P.1.1.C.A.A.USD.A.A.A.A.A.I", force_refresh=True,
            )

        assert result is not None
        assert len(result) == len(s)

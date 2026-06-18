"""Unit tests for the World Bank fetcher in indicators/loader.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from indicators.loader import _fetch_wb_from_api, fetch_wb_series


def _make_wb_response(records: list[tuple[str, float | None]]) -> list:
    """Build a minimal WB API response payload."""
    items = [{"date": d, "value": v} for d, v in records]
    return [{"page": 1, "pages": 1, "total": len(items)}, items]


# ─── _fetch_wb_from_api ──────────────────────────────────────────────────────

class TestFetchWbFromApi:
    def _mock_get(self, records):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = _make_wb_response(records)
        return resp

    def test_returns_sorted_series(self):
        records = [("2023", 11.2), ("2021", 10.8), ("2022", 11.0)]
        with patch("indicators.loader.requests.get", return_value=self._mock_get(records)):
            s = _fetch_wb_from_api("NE.EXP.GNFS.ZS", "US", 1990)
        assert isinstance(s, pd.Series)
        assert list(s.index) == sorted(s.index)

    def test_year_strings_become_year_end_timestamps(self):
        records = [("2023", 11.2), ("2022", 11.0)]
        with patch("indicators.loader.requests.get", return_value=self._mock_get(records)):
            s = _fetch_wb_from_api("NE.EXP.GNFS.ZS", "US", 1990)
        for ts in s.index:
            assert ts.month == 12
            assert ts.day == 31

    def test_null_values_excluded(self):
        records = [("2023", 11.2), ("2022", None), ("2021", 10.8)]
        with patch("indicators.loader.requests.get", return_value=self._mock_get(records)):
            s = _fetch_wb_from_api("NE.EXP.GNFS.ZS", "US", 1990)
        assert len(s) == 2

    def test_raises_on_empty_payload(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [{"page": 1, "pages": 1, "total": 0}, []]
        with patch("indicators.loader.requests.get", return_value=resp):
            with pytest.raises(ValueError, match="Empty or malformed"):
                _fetch_wb_from_api("BAD.SERIES", "US", 1990)

    def test_raises_when_all_null(self):
        records = [("2023", None), ("2022", None)]
        with patch("indicators.loader.requests.get", return_value=self._mock_get(records)):
            with pytest.raises(ValueError, match="All values null"):
                _fetch_wb_from_api("NE.EXP.GNFS.ZS", "US", 1990)


# ─── fetch_wb_series ─────────────────────────────────────────────────────────

class TestFetchWbSeries:
    def _make_series(self, n: int = 10) -> pd.Series:
        idx = pd.date_range("2010-12-31", periods=n, freq="YE")
        return pd.Series(range(n), index=idx, name="value", dtype=float)

    def test_returns_cached_series_when_fresh(self, tmp_path):
        s = self._make_series()
        cache = tmp_path / "wb_US_NE_EXP_GNFS_ZS.parquet"
        s.to_frame().to_parquet(cache)

        with patch("indicators.loader.RAW_CACHE_DIR", tmp_path), \
             patch("indicators.loader._is_fresh", return_value=True):
            result = fetch_wb_series("NE.EXP.GNFS.ZS", country_iso="US", frequency="A")

        pd.testing.assert_series_equal(result, s, check_freq=False)

    def test_fetches_from_api_when_cache_stale(self, tmp_path):
        s = self._make_series()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        records = [(str(ts.year), float(v)) for ts, v in zip(s.index, s.values)]
        resp.json.return_value = _make_wb_response(records)

        with patch("indicators.loader.RAW_CACHE_DIR", tmp_path), \
             patch("indicators.loader._is_fresh", return_value=False), \
             patch("indicators.loader.requests.get", return_value=resp):
            result = fetch_wb_series("NE.EXP.GNFS.ZS", country_iso="US", frequency="A")

        assert result is not None
        assert len(result) == len(s)

    def test_returns_none_and_logs_on_api_failure(self, tmp_path, caplog):
        import logging
        with patch("indicators.loader.RAW_CACHE_DIR", tmp_path), \
             patch("indicators.loader._is_fresh", return_value=False), \
             patch("indicators.loader._fetch_wb_from_api", side_effect=ValueError("bad")), \
             caplog.at_level(logging.ERROR):
            result = fetch_wb_series("BAD.SERIES", country_iso="US", frequency="A")

        assert result is None

    def test_falls_back_to_stale_cache_on_api_failure(self, tmp_path):
        s = self._make_series()
        cache = tmp_path / "wb_US_NE_EXP_GNFS_ZS.parquet"
        s.to_frame().to_parquet(cache)

        with patch("indicators.loader.RAW_CACHE_DIR", tmp_path), \
             patch("indicators.loader._is_fresh", return_value=False), \
             patch("indicators.loader._fetch_wb_from_api", side_effect=ValueError("timeout")):
            result = fetch_wb_series("NE.EXP.GNFS.ZS", country_iso="US", frequency="A")

        assert result is not None
        pd.testing.assert_series_equal(result, s, check_freq=False)

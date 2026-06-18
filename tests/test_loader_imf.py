"""Unit tests for the IMF Datamapper fetcher in indicators/loader.py."""
from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from indicators.loader import _fetch_imf_from_api, fetch_imf_series


def _make_imf_response(indicator: str, country_iso3: str, year_vals: dict) -> dict:
    """Build a minimal IMF Datamapper API response payload."""
    return {"values": {indicator: {country_iso3: year_vals}}}


# ─── _fetch_imf_from_api ─────────────────────────────────────────────────────

class TestFetchImfFromApi:
    def _mock_get(self, indicator: str, country: str, year_vals: dict):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = _make_imf_response(indicator, country, year_vals)
        return resp

    def test_returns_sorted_series(self):
        year_vals = {"2022": -3.1, "2020": -11.5, "2021": -8.7}
        with patch("indicators.loader.requests.get",
                   return_value=self._mock_get("pb", "USA", year_vals)):
            s = _fetch_imf_from_api("pb", "USA")
        assert isinstance(s, pd.Series)
        assert list(s.index) == sorted(s.index)

    def test_year_strings_become_year_end_timestamps(self):
        year_vals = {"2022": -3.1, "2021": -8.7}
        with patch("indicators.loader.requests.get",
                   return_value=self._mock_get("pb", "USA", year_vals)):
            s = _fetch_imf_from_api("pb", "USA")
        for ts in s.index:
            assert ts.month == 12
            assert ts.day == 31

    def test_null_values_excluded(self):
        year_vals = {"2022": -3.1, "2021": None, "2020": -11.5}
        with patch("indicators.loader.requests.get",
                   return_value=self._mock_get("pb", "USA", year_vals)):
            s = _fetch_imf_from_api("pb", "USA")
        assert len(s) == 2

    def test_future_years_excluded(self):
        current_year = datetime.date.today().year
        future_year = str(current_year + 1)
        year_vals = {"2022": -3.1, future_year: -2.5}
        with patch("indicators.loader.requests.get",
                   return_value=self._mock_get("pb", "USA", year_vals)):
            s = _fetch_imf_from_api("pb", "USA")
        years_in_result = [ts.year for ts in s.index]
        assert current_year + 1 not in years_in_result
        assert 2022 in years_in_result

    def test_current_year_included(self):
        current_year = datetime.date.today().year
        year_vals = {"2022": -3.1, str(current_year): -4.0}
        with patch("indicators.loader.requests.get",
                   return_value=self._mock_get("pb", "USA", year_vals)):
            s = _fetch_imf_from_api("pb", "USA")
        assert current_year in [ts.year for ts in s.index]

    def test_raises_on_empty_response(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"values": {}}
        with patch("indicators.loader.requests.get", return_value=resp):
            with pytest.raises(ValueError, match="Empty IMF"):
                _fetch_imf_from_api("pb", "USA")

    def test_raises_when_all_null(self):
        year_vals = {"2022": None, "2021": None}
        with patch("indicators.loader.requests.get",
                   return_value=self._mock_get("pb", "USA", year_vals)):
            with pytest.raises(ValueError, match="null or future"):
                _fetch_imf_from_api("pb", "USA")

    def test_values_are_float(self):
        year_vals = {"2022": "-3.1", "2021": "-8.7"}  # strings from JSON
        with patch("indicators.loader.requests.get",
                   return_value=self._mock_get("pb", "USA", year_vals)):
            s = _fetch_imf_from_api("pb", "USA")
        assert s.dtype == float


# ─── fetch_imf_series ────────────────────────────────────────────────────────

class TestFetchImfSeries:
    def _make_series(self, n=10) -> pd.Series:
        idx = pd.date_range("2014-12-31", periods=n, freq="YE")
        return pd.Series(range(n), index=idx, name="value", dtype=float)

    def test_returns_none_for_unknown_country(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_CACHE_DIR", str(tmp_path))
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path
        result = fetch_imf_series("pb", country_iso2="ZZ")
        assert result is None

    def test_uses_cache_when_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_CACHE_DIR", str(tmp_path))
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        s = self._make_series()
        cache = tmp_path / "imf_US_pb.parquet"
        s.to_frame().to_parquet(cache)

        with patch("indicators.loader._fetch_imf_from_api") as mock_fetch:
            result = fetch_imf_series("pb", country_iso2="US", force_refresh=False)

        mock_fetch.assert_not_called()
        assert result is not None

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_CACHE_DIR", str(tmp_path))
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        fresh = self._make_series()
        with patch("indicators.loader._fetch_imf_from_api", return_value=fresh) as mock_fetch:
            result = fetch_imf_series("pb", country_iso2="US", force_refresh=True)

        mock_fetch.assert_called_once()
        assert result is not None

    def test_returns_none_on_api_failure_no_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_CACHE_DIR", str(tmp_path))
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        with patch("indicators.loader._fetch_imf_from_api", side_effect=ValueError("boom")):
            result = fetch_imf_series("pb", country_iso2="US", force_refresh=True)

        assert result is None

    def test_falls_back_to_stale_cache_on_api_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_CACHE_DIR", str(tmp_path))
        import indicators.loader as ldr
        ldr.RAW_CACHE_DIR = tmp_path

        s = self._make_series()
        cache = tmp_path / "imf_US_pb.parquet"
        s.to_frame().to_parquet(cache)

        with patch("indicators.loader._fetch_imf_from_api", side_effect=RuntimeError("timeout")):
            result = fetch_imf_series("pb", country_iso2="US", force_refresh=True)

        assert result is not None
        assert len(result) == len(s)

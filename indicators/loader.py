"""FRED and World Bank data fetchers with parquet-based disk cache."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from fredapi import Fred
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

RAW_CACHE_DIR = Path(os.environ.get("RAW_CACHE_DIR", "/mnt/data/project_data/all_weather/indicators_machine/raw_cache"))

# Seconds before a cached file is considered stale and must be refreshed
_CACHE_TTL: dict[str, int] = {
    "D": 3600 * 20,        # 20 h — daily series
    "W": 3600 * 24 * 6,   # 6 days
    "M": 3600 * 24 * 25,  # 25 days
    "Q": 3600 * 24 * 80,  # 80 days
    "A": 3600 * 24 * 300, # 300 days
}

_FRED_START = "1980-01-01"  # default history start


def _get_fred_client() -> Fred:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "FRED_API_KEY is not set. Export it or add it to .env. "
            "Register for a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    return Fred(api_key=api_key)


def _cache_path(series_id: str) -> Path:
    return RAW_CACHE_DIR / f"fred_{series_id}.parquet"


def _is_fresh(path: Path, freq: str) -> bool:
    if not path.exists():
        return False
    ttl = _CACHE_TTL.get(freq, 3600 * 24)
    age = time.time() - path.stat().st_mtime
    return age < ttl


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_from_api(fred: Fred, series_id: str, start: str) -> pd.Series:
    return fred.get_series(series_id, observation_start=start)


def fetch_series(
    series_id: str,
    frequency: str,
    force_refresh: bool = False,
    start: str = _FRED_START,
) -> Optional[pd.Series]:
    """
    Return a pandas Series for the given FRED series_id.

    Checks the parquet cache first; fetches from the FRED API only when the
    cache is absent or stale (based on the series frequency).  Returns None
    and logs a warning if the result is empty.
    """
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(series_id)

    if not force_refresh and _is_fresh(cache, frequency):
        logger.debug("[cache hit] %s", series_id)
        df = pd.read_parquet(cache)
        return df["value"]

    logger.info("[FRED fetch] %s (start=%s)", series_id, start)
    fred = _get_fred_client()

    try:
        series = _fetch_from_api(fred, series_id, start)
    except Exception as exc:
        logger.error("[FRED] Failed to fetch %s: %s", series_id, exc)
        # Fall back to stale cache rather than hard-failing the whole pipeline
        if cache.exists():
            logger.warning("[cache fallback] Using stale cache for %s", series_id)
            df = pd.read_parquet(cache)
            return df["value"]
        return None

    if series is None or series.empty:
        logger.warning("[FRED] Empty result for %s — check series ID", series_id)
        return None

    series.name = "value"
    series.index.name = "date"
    series.to_frame().to_parquet(cache)
    logger.debug("[cached] %s → %s (%d obs)", series_id, cache.name, len(series))
    return series


# ─── World Bank fetcher ──────────────────────────────────────────────────────

_WB_BASE = "https://api.worldbank.org/v2"
_WB_START_YEAR = 1990


def _wb_cache_path(series_id: str, country_iso: str) -> Path:
    safe = series_id.replace(".", "_")
    return RAW_CACHE_DIR / f"wb_{country_iso}_{safe}.parquet"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_wb_from_api(series_id: str, country_iso: str, start_year: int) -> pd.Series:
    url = (
        f"{_WB_BASE}/country/{country_iso}/indicator/{series_id}"
        f"?format=json&per_page=500&date={start_year}:2030"
    )
    resp = requests.get(url, timeout=40)
    resp.raise_for_status()
    payload = resp.json()

    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise ValueError(f"Empty or malformed WB response for {series_id}")

    records = [
        (item["date"], item["value"])
        for item in payload[1]
        if item.get("value") is not None
    ]
    if not records:
        raise ValueError(f"All values null for {series_id}")

    # WB returns annual data as year strings; convert to year-end timestamps
    dates = pd.to_datetime([r[0] for r in records], format="%Y") + pd.offsets.YearEnd(0)
    values = [r[1] for r in records]
    series = pd.Series(values, index=dates, name="value", dtype=float)
    series.index.name = "date"
    return series.sort_index()


def fetch_wb_series(
    series_id: str,
    country_iso: str = "US",
    frequency: str = "A",
    force_refresh: bool = False,
    start_year: int = _WB_START_YEAR,
) -> Optional[pd.Series]:
    """
    Return a pandas Series for the given World Bank indicator.

    Uses the WB REST API directly (more reliable than wbgapi for this env).
    Annual data index is converted to year-end timestamps.
    Caches to parquet; TTL same as FRED annual series (300 days).
    Returns None and logs a warning if the result is empty.
    """
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _wb_cache_path(series_id, country_iso)

    if not force_refresh and _is_fresh(cache, frequency):
        logger.debug("[cache hit] WB %s/%s", country_iso, series_id)
        df = pd.read_parquet(cache)
        return df["value"]

    logger.info("[WB fetch] %s/%s (from %d)", country_iso, series_id, start_year)

    try:
        series = _fetch_wb_from_api(series_id, country_iso, start_year)
    except Exception as exc:
        logger.error("[WB] Failed to fetch %s/%s: %s", country_iso, series_id, exc)
        if cache.exists():
            logger.warning("[cache fallback] Using stale cache for WB %s/%s", country_iso, series_id)
            df = pd.read_parquet(cache)
            return df["value"]
        return None

    series.to_frame().to_parquet(cache)
    logger.debug("[cached] WB %s/%s → %s (%d obs)", country_iso, series_id, cache.name, len(series))
    return series

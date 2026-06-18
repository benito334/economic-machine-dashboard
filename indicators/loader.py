"""FRED data fetcher with parquet-based disk cache."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
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

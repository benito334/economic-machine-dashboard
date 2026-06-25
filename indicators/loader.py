"""FRED, World Bank, and IMF data fetchers with parquet-based disk cache."""
from __future__ import annotations

import datetime
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


def _meta_path(series_id: str) -> Path:
    return RAW_CACHE_DIR / f"fred_{series_id}_meta.json"


def get_fred_meta(series_id: str) -> dict:
    """Return FRED series metadata (title, units, seasonal adjustment).

    Reads from a sidecar JSON if present; otherwise fetches from the FRED API
    and writes the sidecar for future calls. TTL is 365 days.
    Returns an empty dict on failure so callers can degrade gracefully.
    """
    import json as _json
    meta_file = _meta_path(series_id)
    _year = 3600 * 24 * 365
    if meta_file.exists() and (time.time() - meta_file.stat().st_mtime) < _year:
        try:
            return _json.loads(meta_file.read_text())
        except Exception:
            pass
    try:
        fred = _get_fred_client()
        info = fred.get_series_info(series_id)
        meta = {
            "title":        str(info.get("title", "")),
            "units":        str(info.get("units", "")),
            "units_short":  str(info.get("units_short", "")),
            "seasonal_adjustment_short": str(info.get("seasonal_adjustment_short", "")),
            "frequency":    str(info.get("frequency", "")),
        }
        RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        meta_file.write_text(_json.dumps(meta))
        return meta
    except Exception as exc:
        logger.warning("[fred meta] %s: %s", series_id, exc)
        return {}


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

# Maps 2-letter binding country codes to World Bank API country codes.
# Individual countries (US, KR, JP, etc.) use their ISO2 code directly.
# Aggregate groups require special WB codes (e.g. EMU for Euro area).
_WB_COUNTRY_MAP: dict[str, str] = {
    "EZ": "EMU",   # Euro area aggregate (EZ = our internal code; WB uses EMU)
    "JP": "JPN",   # WB accepts ISO2 but ISO3 also works
    "GB": "GBR",
    "KR": "KOR",
    "CN": "CHN",
    "IN": "IND",
    "BR": "BRA",
    "SA": "SAU",
    "RU": "RUS",
}


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

    country_iso is the 2-letter binding code (e.g. "EA", "KR"). Mapped to the
    correct WB API code (e.g. "EMU", "KOR") via _WB_COUNTRY_MAP.
    """
    wb_code = _WB_COUNTRY_MAP.get(country_iso, country_iso)
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _wb_cache_path(series_id, wb_code)

    if not force_refresh and _is_fresh(cache, frequency):
        logger.debug("[cache hit] WB %s/%s", wb_code, series_id)
        df = pd.read_parquet(cache)
        return df["value"]

    logger.info("[WB fetch] %s/%s (from %d)", wb_code, series_id, start_year)

    try:
        series = _fetch_wb_from_api(series_id, wb_code, start_year)
    except Exception as exc:
        logger.error("[WB] Failed to fetch %s/%s: %s", wb_code, series_id, exc)
        if cache.exists():
            logger.warning("[cache fallback] Using stale cache for WB %s/%s", wb_code, series_id)
            df = pd.read_parquet(cache)
            return df["value"]
        return None

    series.to_frame().to_parquet(cache)
    logger.debug("[cached] WB %s/%s → %s (%d obs)", wb_code, series_id, cache.name, len(series))
    return series


# ─── IMF Datamapper fetcher ──────────────────────────────────────────────────

_IMF_BASE = "https://www.imf.org/external/datamapper/api/v1"

# Map 2-letter country codes (used in CountryBinding) to IMF Datamapper ISO-3 codes
_IMF_COUNTRY_MAP: dict[str, str] = {
    "US": "USA",
    "EZ": "EUR",   # Euro area — note: IMF Datamapper does NOT support EUR aggregate; kept for completeness
    "JP": "JPN",
    "GB": "GBR",
    "CN": "CHN",
    "KR": "KOR",
    "IN": "IND",
    "BR": "BRA",
    "SA": "SAU",
    "RU": "RUS",
}


def _imf_cache_path(indicator: str, country_iso2: str) -> Path:
    safe = indicator.replace(".", "_")
    return RAW_CACHE_DIR / f"imf_{country_iso2}_{safe}.parquet"


def _completed_imf_years(series: pd.Series) -> pd.Series:
    """Exclude Datamapper estimates for the current year and later."""
    last_completed_year = datetime.date.today().year - 1
    return series[series.index.year <= last_completed_year]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_imf_from_api(indicator: str, country_iso3: str) -> pd.Series:
    url = f"{_IMF_BASE}/{indicator}/{country_iso3}"
    resp = requests.get(url, timeout=40)
    resp.raise_for_status()
    payload = resp.json()

    vals: dict = (
        payload.get("values", {})
        .get(indicator, {})
        .get(country_iso3, {})
    )
    if not vals:
        raise ValueError(
            f"Empty IMF Datamapper response for {indicator}/{country_iso3}. "
            f"Top-level keys: {list(payload.keys())}"
        )

    # Datamapper's current-year annual values are WEO estimates, not completed
    # observations. Keep only completed calendar years in the signal store.
    last_completed_year = datetime.date.today().year - 1
    records = [
        (int(yr), float(v))
        for yr, v in vals.items()
        if v is not None and int(yr) <= last_completed_year
    ]
    if not records:
        raise ValueError(f"All values null or future-only for {indicator}/{country_iso3}")

    dates = pd.to_datetime([str(yr) for yr, _ in records], format="%Y") + pd.offsets.YearEnd(0)
    values = [v for _, v in records]
    series = pd.Series(values, index=dates, name="value", dtype=float)
    series.index.name = "date"
    return series.sort_index()


def fetch_imf_series(
    indicator: str,
    country_iso2: str = "US",
    frequency: str = "A",
    force_refresh: bool = False,
) -> Optional[pd.Series]:
    """
    Return a pandas Series for the given IMF Datamapper indicator.

    Calls https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3}.
    Current-year estimates and future forecast years are filtered out.
    Annual data index is converted to year-end timestamps.
    Caches to parquet; TTL same as annual series (300 days).
    Returns None and logs a warning if the result is empty.
    """
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _imf_cache_path(indicator, country_iso2)

    if not force_refresh and _is_fresh(cache, frequency):
        logger.debug("[cache hit] IMF %s/%s", country_iso2, indicator)
        df = pd.read_parquet(cache)
        return _completed_imf_years(df["value"])

    country_iso3 = _IMF_COUNTRY_MAP.get(country_iso2)
    if not country_iso3:
        logger.error("[IMF] No ISO-3 mapping for country '%s'", country_iso2)
        return None

    logger.info("[IMF fetch] %s/%s", country_iso2, indicator)

    try:
        series = _fetch_imf_from_api(indicator, country_iso3)
    except Exception as exc:
        logger.error("[IMF] Failed to fetch %s/%s: %s", country_iso2, indicator, exc)
        if cache.exists():
            logger.warning("[cache fallback] Using stale cache for IMF %s/%s", country_iso2, indicator)
            df = pd.read_parquet(cache)
            return _completed_imf_years(df["value"])
        return None

    series.to_frame().to_parquet(cache)
    logger.debug("[cached] IMF %s/%s → %s (%d obs)", country_iso2, indicator, cache.name, len(series))
    return series


# ─── Eurostat JSON stats API ──────────────────────────────────────────────────

_ESTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _estat_cache_path(dataset: str, params: dict) -> Path:
    import hashlib
    import json
    key = json.dumps(sorted(params.items()))
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return RAW_CACHE_DIR / f"estat_{dataset}_{h}.parquet"


def _parse_estat_periods(periods: list) -> pd.DatetimeIndex:
    """Convert Eurostat period strings to period-end DatetimeIndex."""
    first = periods[0]
    if "-Q" in first:
        return pd.PeriodIndex(periods, freq="Q").to_timestamp(how="end").normalize()
    elif len(first) == 7 and first[4] == "-":  # YYYY-MM
        return pd.to_datetime(periods, format="%Y-%m") + pd.offsets.MonthEnd(0)
    else:  # YYYY annual
        return pd.to_datetime(periods, format="%Y") + pd.offsets.YearEnd(0)


def _decode_eurostat_response(d: dict) -> pd.Series:
    """Decode Eurostat JSON stats API response to a dated pandas Series.

    Time is always the last dimension. If any non-time dimension has size > 1
    (caller failed to narrow filters), only the first combination is used.
    """
    ids = d.get("id", [])
    sizes = d.get("size", [])
    vals = d.get("value", {})

    if not ids or not vals:
        return pd.Series(dtype=float, name="value")

    n_time = sizes[-1]
    time_cats = d["dimension"][ids[-1]]["category"]["index"]  # period_str → pos
    time_by_pos = {v: k for k, v in time_cats.items()}        # pos → period_str

    non_time_product = 1
    for s in sizes[:-1]:
        non_time_product *= s
    if non_time_product > 1:
        logger.warning(
            "[Eurostat] %d non-time dimension combinations — using first combination only",
            non_time_product,
        )

    records: list[tuple[str, float]] = []
    for pos_str, val in vals.items():
        pos = int(pos_str)
        time_pos = pos % n_time
        if pos // n_time == 0:  # first combination of non-time dims
            period = time_by_pos.get(time_pos)
            if period is not None:
                records.append((period, float(val)))

    if not records:
        return pd.Series(dtype=float, name="value")

    periods, values = zip(*sorted(records))
    dates = _parse_estat_periods(list(periods))
    series = pd.Series(list(values), index=dates, name="value", dtype=float)
    series.index.name = "date"
    return series.sort_index()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_estat_from_api(dataset: str, params: dict) -> pd.Series:
    resp = requests.get(
        f"{_ESTAT_BASE}/{dataset}",
        params={**params, "lang": "en", "format": "JSON", "sinceTimePeriod": "1999-01"},
        timeout=40,
    )
    resp.raise_for_status()
    d = resp.json()
    if not d.get("value"):
        raise ValueError(
            f"Empty Eurostat response for {dataset} {params}. "
            f"Sizes: {dict(zip(d.get('id', []), d.get('size', [])))}"
        )
    series = _decode_eurostat_response(d)
    if series.empty:
        raise ValueError(f"Decoded empty series for {dataset} {params}")
    return series


def fetch_eurostat_series(
    dataset: str,
    params: dict,
    frequency: str = "M",
    force_refresh: bool = False,
) -> Optional[pd.Series]:
    """
    Return a pandas Series for the given Eurostat JSON stats dataset.

    dataset: dataset code (e.g. "une_rt_m", "sts_inpr_m")
    params: dimension filter dict (e.g. {"geo": "EA21", "s_adj": "SA", ...})
    Caches to parquet; TTL matches the series frequency.
    Returns None and logs a warning if the result is empty.
    """
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _estat_cache_path(dataset, params)

    if not force_refresh and _is_fresh(cache, frequency):
        logger.debug("[cache hit] Eurostat %s", dataset)
        df = pd.read_parquet(cache)
        return df["value"]

    logger.info("[Eurostat fetch] %s %s", dataset, params)

    try:
        series = _fetch_estat_from_api(dataset, params)
    except Exception as exc:
        logger.error("[Eurostat] Failed to fetch %s: %s", dataset, exc)
        if cache.exists():
            logger.warning("[cache fallback] Using stale cache for Eurostat %s", dataset)
            df = pd.read_parquet(cache)
            return df["value"]
        return None

    series.to_frame().to_parquet(cache)
    logger.debug("[cached] Eurostat %s → %s (%d obs)", dataset, cache.name, len(series))
    return series


# ── ECB Statistical Data Warehouse (SDMX-JSON 1.0) ───────────────────────────

_ECB_BASE = "https://data-api.ecb.europa.eu/service/data"


def _ecb_cache_path(flow: str, key: str) -> Path:
    import hashlib
    h = hashlib.md5(f"{flow}/{key}".encode()).hexdigest()[:10]
    return RAW_CACHE_DIR / f"ecb_{flow}_{h}.parquet"


def _decode_ecb_response(d: dict) -> pd.Series:
    """Decode ECB SDMX-JSON 1.0 response (single series) to a dated pandas Series."""
    struct = d.get("structure", {})
    obs_dims = struct.get("dimensions", {}).get("observation", [])
    if not obs_dims:
        return pd.Series(dtype=float, name="value")
    periods = [v["id"] for v in obs_dims[0].get("values", [])]

    dataset = d.get("dataSets", [{}])[0]
    series_dict = dataset.get("series", {})
    if not series_dict:
        return pd.Series(dtype=float, name="value")
    # Use the first series (single-country key returns exactly one)
    series_data = next(iter(series_dict.values()))
    obs = series_data.get("observations", {})

    records: list[tuple[str, float]] = []
    for pos_str, val_list in obs.items():
        pos = int(pos_str)
        if pos < len(periods) and val_list and val_list[0] is not None:
            records.append((periods[pos], float(val_list[0])))

    if not records:
        return pd.Series(dtype=float, name="value")

    periods_sorted, values = zip(*sorted(records))
    dates = _parse_estat_periods(list(periods_sorted))  # YYYY-MM → month-end works here
    return pd.Series(list(values), index=dates, name="value", dtype=float).sort_index()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_ecb_from_api(flow: str, key: str, start_period: str = "2000-01") -> pd.Series:
    resp = requests.get(
        f"{_ECB_BASE}/{flow}/{key}",
        params={"startPeriod": start_period, "format": "jsondata"},
        timeout=40,
    )
    resp.raise_for_status()
    d = resp.json()
    series = _decode_ecb_response(d)
    if series.empty:
        raise ValueError(f"Empty ECB response for {flow}/{key}")
    return series


def fetch_ecb_series(
    flow: str,
    key: str,
    start_period: str = "2000-01",
    frequency: str = "M",
    force_refresh: bool = False,
) -> Optional[pd.Series]:
    """
    Fetch a single time series from the ECB Statistical Data Warehouse SDMX-JSON API.

    flow: ECB data flow (e.g. "IRS")
    key: dimension key string (e.g. "M.DE.L.L40.CI.0000.EUR.N.Z")
    Caches to parquet; returns None and logs on failure.
    """
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _ecb_cache_path(flow, key)

    if not force_refresh and _is_fresh(cache, frequency):
        logger.debug("[cache hit] ECB %s/%s", flow, key)
        df = pd.read_parquet(cache)
        return df["value"]

    logger.info("[ECB fetch] %s/%s", flow, key)

    try:
        series = _fetch_ecb_from_api(flow, key, start_period)
    except Exception as exc:
        logger.error("[ECB] Failed to fetch %s/%s: %s", flow, key, exc)
        if cache.exists():
            logger.warning("[cache fallback] Using stale cache for ECB %s/%s", flow, key)
            df = pd.read_parquet(cache)
            return df["value"]
        return None

    series.to_frame().to_parquet(cache)
    logger.debug("[cached] ECB %s/%s → %s (%d obs)", flow, key, cache.name, len(series))
    return series

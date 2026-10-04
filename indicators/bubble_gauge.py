"""Late-stage-bubble gauge — Coverage-audit Phase C build-out, 2026-10-04.

The 2026-10-03 Phase C scoping pass (docs/worklog.md, "Coverage Audit Phase C")
checked all 6 of Dalio's late-stage-bubble dimensions live and found only 3
genuinely free-buildable:

  1. Valuation    — already built: indicators/valuations.py's Buffett
                     Indicator (market-cap/GDP). Reused here, not rebuilt.
  5. Leverage      — FINRA Margin Statistics (margin debt), NEW here.
  6. Positioning   — CFTC Traders in Financial Futures (TFF), leveraged-fund
                      net positioning in E-mini S&P 500 futures, NEW here.

The other 3 (sentiment, forward-earnings pricing, new-buyer participation)
were confirmed dead ends — no free live source exists for any of them. This
module does NOT attempt a 6-dimension composite; it reports the 3 buildable
dimensions as independent reads, each a full-history Z-score of its own
series. No combined "bubble score" is computed — Phase C's own scoping note
is explicit that a full 6-dimension gauge was never realistic on free data,
and averaging 3 partial dimensions into one number would manufacture false
precision this module doesn't try to claim.

Feeds no composite; isolated force, same convention as fed.*/market.*/order.*.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

RAW_CACHE_DIR = Path(os.environ.get(
    "RAW_CACHE_DIR", "/mnt/data/project_data/finance/indicators_machine/raw_cache"))

# ── FINRA Margin Statistics (leverage dimension) ───────────────────────────────
# Verified live 2026-10-03/04: direct Excel download, no login, no API — same
# shape of source as the SPF loader. The "2021-03" path segment is a CMS
# upload-date artifact, not a staleness signal (confirmed via last-modified
# header actively updating monthly).
_FINRA_URL = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
_FINRA_CACHE_TTL = 3600 * 24 * 7  # 7 days — FINRA updates ~3 weeks after month-end
_FINRA_DEBIT_COL = "Debit Balances in Customers' Securities Margin Accounts"

# ── CFTC Traders in Financial Futures (positioning dimension) ─────────────────
# Verified live 2026-10-03/04: official Socrata Open Data API, no auth.
# Dataset gpe5-46if = Traders in Financial Futures; E-MINI S&P 500 contract
# has weekly history back to 2006-06-13 (1060+ obs as of this writing).
_CFTC_TFF_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
_CFTC_CONTRACT = "E-MINI S&P 500"
_CFTC_CACHE_TTL = 3600 * 24 * 3  # 3 days — CFTC publishes weekly (Friday)


def _cache_path(name: str) -> Path:
    return RAW_CACHE_DIR / f"bubble_{name}"


def _is_fresh(path: Path, ttl: int) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < ttl


def _download_bytes(url: str, cache_name: str, ttl: int, force_refresh: bool) -> Optional[bytes]:
    cache = _cache_path(cache_name)
    if not force_refresh and _is_fresh(cache, ttl):
        return cache.read_bytes()
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        cache.write_bytes(data)
        return data
    except Exception as exc:
        logger.warning("[bubble_gauge] fetch failed for %s: %s", cache_name, exc)
        if cache.exists():
            logger.warning("[bubble_gauge] using stale cache for %s", cache_name)
            return cache.read_bytes()
        return None


def fetch_margin_debt(force_refresh: bool = False) -> pd.DataFrame:
    """{"as_of": month-end timestamp, "value": debit balances, $ millions}."""
    raw = _download_bytes(_FINRA_URL, "margin_debt.xlsx", _FINRA_CACHE_TTL, force_refresh)
    if raw is None:
        return pd.DataFrame(columns=["as_of", "value"])
    import io
    try:
        df = pd.read_excel(io.BytesIO(raw), sheet_name="Customer Margin Balances")
    except Exception as exc:
        logger.warning("[bubble_gauge] margin debt parse failed: %s", exc)
        return pd.DataFrame(columns=["as_of", "value"])
    if _FINRA_DEBIT_COL not in df.columns or "Year-Month" not in df.columns:
        logger.warning("[bubble_gauge] margin debt: expected columns not found")
        return pd.DataFrame(columns=["as_of", "value"])
    out = pd.DataFrame({
        "as_of": pd.to_datetime(df["Year-Month"], format="%Y-%m") + pd.offsets.MonthEnd(0),
        "value": pd.to_numeric(df[_FINRA_DEBIT_COL], errors="coerce"),
    }).dropna().sort_values("as_of").reset_index(drop=True)
    return out


def fetch_leveraged_fund_positioning(force_refresh: bool = False) -> pd.DataFrame:
    """{"as_of": report date, "value": leveraged-fund net longs as % of open
    interest} for E-mini S&P 500 futures. Positive = net long (crowded
    bullish); negative = net short (crowded bearish)."""
    params = {
        "$limit": "5000",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "contract_market_name": _CFTC_CONTRACT,
    }
    url = f"{_CFTC_TFF_URL}?{urllib.parse.urlencode(params)}"
    raw = _download_bytes(url, "cftc_tff_es.json", _CFTC_CACHE_TTL, force_refresh)
    if raw is None:
        return pd.DataFrame(columns=["as_of", "value"])
    try:
        rows = json.loads(raw)
    except Exception as exc:
        logger.warning("[bubble_gauge] CFTC TFF parse failed: %s", exc)
        return pd.DataFrame(columns=["as_of", "value"])

    recs = []
    for r in rows:
        try:
            oi = float(r["open_interest_all"])
            if oi <= 0:
                continue
            net = float(r["lev_money_positions_long"]) - float(r["lev_money_positions_short"])
            recs.append({
                "as_of": pd.Timestamp(r["report_date_as_yyyy_mm_dd"]),
                "value": net / oi * 100.0,
            })
        except (KeyError, ValueError, TypeError):
            continue
    if not recs:
        return pd.DataFrame(columns=["as_of", "value"])
    return pd.DataFrame(recs).sort_values("as_of").reset_index(drop=True)


def _full_history_z(series: pd.Series) -> pd.Series:
    """Z-score against the series' OWN full history — the Dalio bubble
    question is "elevated relative to all of history", not a recent window,
    so this deliberately doesn't use a rolling window the way the chip
    composites do."""
    mu, sd = series.mean(), series.std()
    if sd == 0 or pd.isna(sd):
        return series * float("nan")
    return (series - mu) / sd


_Z_MAGNITUDE_LABELS = [(1.5, "Extreme"), (0.5, "Elevated"), (0.0, "Normal")]


def _z_label(z: Optional[float]) -> str:
    """Magnitude-only label from |Z| — deliberately direction-agnostic.
    Valuation/leverage only really get "label-worthy" on the high side (low
    valuation isn't a bubble risk), but positioning is a mean-reverting
    oscillator where EITHER tail (crowded long or crowded short) is the
    noteworthy read — callers show the signed Z and their own directional
    text (e.g. "crowded short") alongside this magnitude label."""
    if z is None or (isinstance(z, float) and pd.isna(z)):
        return "—"
    az = abs(z)
    for cutoff, label in _Z_MAGNITUDE_LABELS:
        if az >= cutoff:
            return label
    return "Normal"


def _margin_debt_pct_gdp(force_refresh: bool = False) -> pd.DataFrame:
    """Margin debt as % of nominal GDP — the leverage-dimension series,
    GDP-normalized the same way the Buffett Indicator (dimension 1) is."""
    from indicators.loader import fetch_series
    debt = fetch_margin_debt(force_refresh=force_refresh)
    if debt.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    gdp = fetch_series("GDP", "Q", force_refresh=force_refresh)  # $ billions, quarterly
    if gdp is None or gdp.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    gdp_m = gdp.copy()
    gdp_m.index = pd.to_datetime(gdp_m.index)
    gdp_monthly = gdp_m.resample("ME").ffill().reindex(
        pd.date_range(gdp_m.index.min(), debt["as_of"].max(), freq="ME")
    ).ffill()

    merged = debt.set_index("as_of").join(
        gdp_monthly.rename("gdp_b"), how="inner"
    )
    merged = merged.dropna()
    if merged.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    # debt is $ millions, GDP is $ billions -> both to $ billions before the ratio
    pct = (merged["value"] / 1000.0) / merged["gdp_b"] * 100.0
    return pd.DataFrame({"as_of": pct.index, "value": pct.values})


def compute_bubble_gauge(force_refresh: bool = False) -> dict:
    """The three buildable dimensions, each as a full-history Z-score read.
    US-only (every underlying series is US-specific)."""
    from indicators.valuations import data_path

    dims: dict = {}

    # ── Dimension 1: Valuation (Buffett Indicator, reused not rebuilt) ────────
    try:
        buffett = json.loads(data_path().read_text())
        default_key = buffett.get("default", "z1")
        num = buffett["numerators"][default_key]
        series = pd.DataFrame(num["series"])
        series["as_of"] = pd.to_datetime(series["date"])
        s = series.set_index("as_of")["ratio"].astype(float)
        z = _full_history_z(s)
        dims["valuation"] = {
            "label": "Valuation — Buffett Indicator",
            "desc": num.get("label", ""),
            "unit": "% of GDP",
            "df": pd.DataFrame({"as_of": s.index, "value": s.values}),
            "current": float(s.iloc[-1]) if not s.empty else None,
            "z": float(z.iloc[-1]) if not z.empty and pd.notna(z.iloc[-1]) else None,
            "as_of": str(s.index[-1].date()) if not s.empty else None,
        }
    except Exception as exc:
        logger.warning("[bubble_gauge] valuation dimension unavailable: %s", exc)
        dims["valuation"] = None

    # ── Dimension 5: Leverage (FINRA margin debt / GDP) ───────────────────────
    try:
        df = _margin_debt_pct_gdp(force_refresh=force_refresh)
        if df.empty:
            dims["leverage"] = None
        else:
            s = df.set_index("as_of")["value"]
            z = _full_history_z(s)
            dims["leverage"] = {
                "label": "Leverage — Margin Debt / GDP",
                "desc": "FINRA customer margin debit balances as % of nominal GDP.",
                "unit": "% of GDP",
                "df": df,
                "current": float(s.iloc[-1]),
                "z": float(z.iloc[-1]) if pd.notna(z.iloc[-1]) else None,
                "as_of": str(s.index[-1].date()),
            }
    except Exception as exc:
        logger.warning("[bubble_gauge] leverage dimension unavailable: %s", exc)
        dims["leverage"] = None

    # ── Dimension 6: Positioning (CFTC leveraged-fund net % of OI) ────────────
    try:
        df = fetch_leveraged_fund_positioning(force_refresh=force_refresh)
        if df.empty:
            dims["positioning"] = None
        else:
            s = df.set_index("as_of")["value"]
            z = _full_history_z(s)
            dims["positioning"] = {
                "label": "Positioning — Leveraged-Fund Net Longs",
                "desc": "CFTC TFF leveraged-fund (hedge fund/CTA) net position in "
                        "E-mini S&P 500 futures, as % of open interest. "
                        "Positive = net long (crowded bullish).",
                "unit": "% of open interest",
                "df": df,
                "current": float(s.iloc[-1]),
                "z": float(z.iloc[-1]) if pd.notna(z.iloc[-1]) else None,
                "as_of": str(s.index[-1].date()),
            }
    except Exception as exc:
        logger.warning("[bubble_gauge] positioning dimension unavailable: %s", exc)
        dims["positioning"] = None

    for d in dims.values():
        if d is not None:
            d["z_label"] = _z_label(d["z"])

    return dims

"""Philadelphia Fed Survey of Professional Forecasters (SPF) loader
(docs/external_validators_plan.md item 2, 2026-10-03).

Not FRED-hosted — the Philly Fed publishes its own quarterly Excel workbooks
directly, so this is its own small loader rather than a reuse of
`indicators.loader.fetch_series`. Two files used here, URLs verified live
2026-10-03 (`curl -I` returned 200 with a fresh `last-modified`):

  Median_RGDP_Growth.xlsx — median QoQ-annualized real GDP growth forecast
  Median_CPI_Level.xlsx   — median QoQ-annualized headline CPI inflation
                            forecast. The file/sheet name says "Level" but
                            the variable itself is already rate-form — see
                            the SPF's own documentation PDF, section 1:
                            "...the headline and core CPI and PCE inflation
                            rates...enter the survey in growth-rate form."

Horizon convention (SPF documentation Table 1A + Section 2): each survey is
conducted in the middle month of a quarter, after that quarter's BEA/BLS
advance data is released. Column suffix 2 = the survey's OWN quarter (an
in-quarter nowcast using partial information); 3 = one quarter ahead; 4/5/6
= two/three/four quarters ahead. CPI additionally carries suffix 1 = the
PRIOR quarter (a backward estimate using the just-released advance data);
RGDP growth has no suffix-1 column (the growth rate for an already-realized
quarter is just that quarter's own already-known actual value — nothing to
forecast).

Surprise construction: a genuine ex-ante forecast error needs a forecast
MADE BEFORE the quarter it targets, not the in-quarter nowcast (suffix 2).
Survey Q-1's suffix-3 column ("one quarter ahead") targets quarter Q and was
recorded before Q began — shift it forward one quarter and compare against
Q's own realized actual once known. Growth's realized actual is FRED
A191RL1Q225SBEA (verified elsewhere in this codebase — indicators/
audit_benchmarks.py's own "real_gdp_growth" benchmark; same QoQ-annualized
convention SPF uses, zero unit mismatch). CPI has no ready-made FRED series
in that exact convention, so it's derived here from CPIAUCSL (the same
series already backing inflation.cpi_headline in config/us_bindings.yaml)
via the standard quarterly-average-then-annualize transformation: a derived
identity, not an invented series, same standard this project already
applies to debt_income_spread / FX reserve runway / etc.
"""
from __future__ import annotations

import logging
import time
import urllib.request
from pathlib import Path
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BASE = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/data-files/files"
_FILES = {
    "rgdp_growth": (f"{_BASE}/Median_RGDP_Growth.xlsx", "Median_Growth", "DRGDP"),
    "cpi":         (f"{_BASE}/Median_CPI_Level.xlsx",   "Median_Level",  "CPI"),
    # Added 2026-10-09 to give signals.surprise a REAL expectation rather than
    # a random walk (Ray 2026-10-07 Ruling 3). These three were chosen because
    # they are the SPF variables that actually map onto basket members:
    # unemployment, payrolls and industrial production are 33% of the US
    # growth basket between them. Real GDP growth, by contrast, reaches
    # nothing — master.gdp_real is not in any basket.
    "unemp":       (f"{_BASE}/Median_UNEMP_Level.xlsx",   "Median_Level", "UNEMP"),
    "empl":        (f"{_BASE}/Median_EMP_Level.xlsx",     "Median_Level", "EMP"),
    "indprod":     (f"{_BASE}/Median_INDPROD_Level.xlsx", "Median_Level", "INDPROD"),
}

import os
RAW_CACHE_DIR = Path(os.environ.get(
    "RAW_CACHE_DIR", "/mnt/data/project_data/finance/indicators_machine/raw_cache"))
_CACHE_TTL_SECONDS = 3600 * 24 * 7  # 7 days — SPF refreshes quarterly

_REALIZED_GROWTH_FRED_ID = "A191RL1Q225SBEA"  # QoQ-annualized real GDP growth
_REALIZED_CPI_FRED_ID = "CPIAUCSL"            # CPI index, derived to QoQ-annualized below


def _cache_path(key: str) -> Path:
    return RAW_CACHE_DIR / f"spf_{key}.xlsx"


def _is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < _CACHE_TTL_SECONDS


def _download(key: str, force_refresh: bool = False) -> Optional[Path]:
    url, _, _ = _FILES[key]
    cache = _cache_path(key)
    if not force_refresh and _is_fresh(cache):
        logger.debug("[spf cache hit] %s", key)
        return cache
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        cache.write_bytes(data)
        logger.info("[spf fetch] %s -> %s (%d bytes)", key, cache.name, len(data))
        return cache
    except Exception as exc:
        logger.warning("[spf fetch] %s failed: %s", key, exc)
        if cache.exists():
            logger.warning("[spf cache fallback] using stale cache for %s", key)
            return cache
        return None


def _survey_date(year: int, quarter: int) -> pd.Timestamp:
    """Quarter-end date for the survey's own quarter, matching this
    project's as_of convention (month-end timestamps)."""
    month = quarter * 3
    return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)


def _parse(key: str, force_refresh: bool = False) -> pd.DataFrame:
    """Long-form: index = survey quarter-end date, columns = h1..h6 (only the
    horizons actually present for this variable)."""
    path = _download(key, force_refresh=force_refresh)
    if path is None:
        return pd.DataFrame()
    _, sheet, prefix = _FILES[key]
    try:
        df = pd.read_excel(path, sheet_name=sheet)
    except Exception as exc:
        logger.warning("[spf parse] %s failed: %s", key, exc)
        return pd.DataFrame()

    df = df.dropna(subset=["YEAR", "QUARTER"])
    out = pd.DataFrame(index=[
        _survey_date(int(r.YEAR), int(r.QUARTER)) for r in df.itertuples()
    ])
    for h in range(1, 7):
        col = f"{prefix}{h}"
        if col in df.columns:
            out[f"h{h}"] = pd.to_numeric(df[col].values, errors="coerce")
    out.index.name = "as_of"
    return out.sort_index()


def _realized_growth(force_refresh: bool = False) -> pd.Series:
    from indicators.loader import fetch_series
    s = fetch_series(_REALIZED_GROWTH_FRED_ID, "Q", force_refresh=force_refresh)
    if s is None:
        return pd.Series(dtype=float)
    s.index = pd.to_datetime(s.index).to_period("Q").to_timestamp("Q")
    return s


def _realized_cpi_qoq_annualized(force_refresh: bool = False) -> pd.Series:
    """Quarterly-average CPI index, QoQ, annualized — the standard BEA/BLS
    transformation, matching the convention SPF's own CPI variable uses.

    CPI is released with roughly a one-month lag, so the most recent quarter
    is often only 1-2 months deep when this runs (e.g. September not out yet
    while Q3 is already "current"). Averaging a partial quarter and treating
    it as the real quarterly figure silently understates/overstates the rate
    — require all 3 months before a quarter counts as realized; an
    incomplete quarter is dropped (NaN), not guessed at."""
    from indicators.loader import fetch_series
    s = fetch_series(_REALIZED_CPI_FRED_ID, "M", force_refresh=force_refresh)
    if s is None:
        return pd.Series(dtype=float)
    s.index = pd.to_datetime(s.index)
    grouped = s.resample("QE")
    q = grouped.mean()
    complete = grouped.count() == 3
    q = q.where(complete)
    rate = (q / q.shift(1)) ** 4 - 1.0
    return rate * 100.0


def fetch_spf_panel(force_refresh: bool = False) -> dict[str, pd.DataFrame]:
    """{'rgdp_growth': df, 'cpi': df} — each indexed by survey date, columns h1..h6."""
    return {key: _parse(key, force_refresh=force_refresh) for key in _FILES}


def forecast_vs_realized(key: str, force_refresh: bool = False) -> tuple[pd.Series, pd.Series]:
    """Full-history (forecast-at-target-quarter, realized) pair for charting
    — the same h3-shifted-forward construction compute_spf_surprise() uses
    for its single latest reading, here as a complete time series."""
    panel = fetch_spf_panel(force_refresh=force_refresh)
    df = panel.get(key, pd.DataFrame())
    if df.empty or "h3" not in df.columns:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    fwd = df["h3"].dropna()
    target_index = [(d.to_period("Q") + 1).to_timestamp("Q") for d in fwd.index]
    forecast_at_target = pd.Series(fwd.values, index=target_index).sort_index()

    realized = (_realized_growth(force_refresh=force_refresh) if key == "rgdp_growth"
                else _realized_cpi_qoq_annualized(force_refresh=force_refresh))
    return forecast_at_target, realized


# ── Real expectations for signals.surprise (Ray 2026-10-07 Ruling 3) ─────────
# Ruling 3 specifies that a published forecast replaces the random-walk
# expectation "with no other pipeline change". These are the SPF variables that
# actually map onto a basket member. Real GDP growth is deliberately absent:
# master.gdp_real is in no basket, so an SPF GDP forecast would reach nothing.
#
# `conversion` exists because the expectation MUST arrive in the signal's own
# units. Subtracting an SPF level from a YoY-transformed signal would produce
# an authoritative-looking number that means nothing.
_SPF_SIGNAL_MAP: dict[str, tuple[str, str, str | None]] = {
    # signal id tail        (spf key,  conversion,     realized FRED id)
    "growth.unemployment":   ("unemp",   "direct",       None),
    "growth.payrolls":       ("empl",    "level_to_yoy", "PAYEMS"),
    "growth.industrial_prod":("indprod", "level_to_yoy_chained", "INDPRO"),
}


@lru_cache(maxsize=16)
def _forecast_at_target_cached(key: str) -> pd.Series:
    return _forecast_at_target(key)


def _forecast_at_target(key: str, force_refresh: bool = False) -> pd.Series:
    """The h3 (one-quarter-ahead) median, indexed by the quarter it describes.

    h3 is the first genuinely EX-ANTE horizon — suffix 2 is an in-quarter
    nowcast using partial information, which is not a forecast of anything
    unknown. Same construction forecast_vs_realized() uses.
    """
    df = _parse(key, force_refresh=force_refresh)
    if df.empty or "h3" not in df.columns:
        return pd.Series(dtype=float)
    fwd = df["h3"].dropna()
    idx = [(d.to_period("Q") + 1).to_timestamp("Q") for d in fwd.index]
    return pd.Series(fwd.values, index=idx).sort_index()


def spf_expectation(signal_tail: str, index: pd.DatetimeIndex,
                    force_refresh: bool = False) -> Optional[pd.Series]:
    """Monthly expectation for one signal, in that signal's own units.

    Returns None when SPF does not cover the signal, which is the signal to
    `build_signals` to fall back to the random walk.

    Point-in-time by construction: the h3 forecast for quarter Q comes from
    the survey taken in Q-1, and the realized level it is divided by is from
    Q-4. Both were known before Q began.
    """
    spec = _SPF_SIGNAL_MAP.get(signal_tail)
    if spec is None:
        return None
    key, conversion, realized_id = spec
    fc = (_forecast_at_target(key, force_refresh=True) if force_refresh
          else _forecast_at_target_cached(key))
    if fc.empty:
        return None

    if conversion == "level_to_yoy_chained":
        # INDPRO is an INDEX and gets rebased. The SPF forecast is on the base
        # current when the survey ran; today's realized series is on 2017=100.
        # Dividing one by the other compares different rulers — measured
        # 2026-10-09, the ratio of SPF level to realized level runs 2.08 in
        # 1985-95, 1.51 in 1995-05, 1.10 in 2005-15, 1.05 since. That produced
        # a surprise with a mean of -1.84 sigma instead of ~0.
        #
        # Growth RATES are base-invariant, so chain them instead: take the
        # quarterly growth the survey itself implies (h3/h2, both on the SAME
        # base, so the base cancels) and compound it onto three realized
        # quarterly growth rates.
        from indicators.loader import fetch_series
        df = _parse(key)
        if df.empty or "h2" not in df.columns or "h3" not in df.columns:
            return None
        pair = df[["h2", "h3"]].dropna()
        q_fc = (pair["h3"] / pair["h2"]) - 1.0          # base-invariant QoQ
        q_fc.index = [(d.to_period("Q") + 1).to_timestamp("Q") for d in pair.index]
        q_fc = q_fc.sort_index()
        lv = fetch_series(realized_id, "M", force_refresh=force_refresh)
        if lv is None or lv.empty:
            return None
        lv.index = pd.to_datetime(lv.index)
        q = lv.resample("QE").mean()
        g = q.pct_change()                               # realized QoQ, also base-invariant
        chained = {}
        for tgt, gf in q_fc.items():
            prior = g.reindex([tgt - pd.offsets.QuarterEnd(k) for k in (3, 2, 1)])
            if prior.isna().any() or pd.isna(gf):
                continue
            chained[tgt] = float(np.prod(1.0 + prior.values) * (1.0 + gf) - 1.0)
        fc = pd.Series(chained).sort_index()
        fc = fc.replace([np.inf, -np.inf], np.nan).dropna()
    elif conversion == "level_to_yoy":
        from indicators.loader import fetch_series
        lv = fetch_series(realized_id, "M", force_refresh=force_refresh)
        if lv is None or lv.empty:
            return None
        lv.index = pd.to_datetime(lv.index)
        q = lv.resample("QE").mean()
        base = q.shift(4).reindex(fc.index)          # realized level 4 quarters back
        fc = (fc / base) - 1.0                       # -> YoY fraction, the signal's unit
        fc = fc.replace([np.inf, -np.inf], np.nan).dropna()
    if fc.empty:
        return None

    # Broadcast each quarter's forecast across its months, then align.
    monthly = fc.resample("ME").ffill().reindex(
        pd.date_range(fc.index.min(), max(fc.index.max(), index.max()), freq="ME"),
        method="ffill", limit=2,                     # a quarter's value spans 3 months
    )
    out = monthly.reindex(pd.DatetimeIndex(index), method="ffill", limit=2)
    return out if out.notna().any() else None


def compute_spf_surprise(force_refresh: bool = False) -> dict:
    """Everything the dashboard's SPF card needs, in one dict.

    For each variable: the latest survey's own nowcast (h2) and one-quarter-
    ahead forecast (h3), plus the most recent resolved SURPRISE — the h3
    forecast made one survey ago for the quarter that has since become
    realized, minus that quarter's actual value. None fields when data
    isn't available yet (e.g. the target quarter hasn't been realized in
    FRED yet, or a fetch failed) — never silently zeroed.
    """
    panel = fetch_spf_panel(force_refresh=force_refresh)
    growth_df, cpi_df = panel["rgdp_growth"], panel["cpi"]

    out: dict = {"as_of": None, "variables": {}}
    if not growth_df.empty:
        out["as_of"] = str(growth_df.index[-1].date())
    elif not cpi_df.empty:
        out["as_of"] = str(cpi_df.index[-1].date())

    realized = {
        "rgdp_growth": _realized_growth(force_refresh=force_refresh),
        "cpi": _realized_cpi_qoq_annualized(force_refresh=force_refresh),
    }

    for key, df, label in (
        ("rgdp_growth", growth_df, "Real GDP growth"),
        ("cpi", cpi_df, "Headline CPI inflation"),
    ):
        if df.empty:
            out["variables"][key] = {"label": label, "nowcast": None, "next_q": None,
                                     "surprise": None, "surprise_target_quarter": None,
                                     "surprise_forecast_date": None}
            continue

        nowcast = df["h2"].dropna().iloc[-1] if "h2" in df.columns and df["h2"].notna().any() else None
        next_q = df["h3"].dropna().iloc[-1] if "h3" in df.columns and df["h3"].notna().any() else None

        surprise = None
        target_q = None
        forecast_date = None
        if "h3" in df.columns:
            # h3 recorded at survey date s targets quarter s+1
            fwd = df["h3"].dropna()
            if not fwd.empty:
                r = realized[key].dropna()
                for s_date in reversed(fwd.index):
                    tgt = (s_date.to_period("Q") + 1).to_timestamp("Q")
                    if tgt in r.index:
                        surprise = float(r.loc[tgt]) - float(fwd.loc[s_date])
                        target_q = str(tgt.date())
                        forecast_date = str(s_date.date())
                        break

        out["variables"][key] = {
            "label": label,
            "nowcast": None if nowcast is None else float(nowcast),
            "next_q": None if next_q is None else float(next_q),
            "surprise": surprise,
            "surprise_target_quarter": target_q,
            "surprise_forecast_date": forecast_date,
        }

    return out

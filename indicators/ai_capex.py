"""AI capex cycle monitor — Phase 1 trigger layer (docs/ai_bubble_monitor_plan.md §9).

Built off the 2026-10-04 six-expert panel (Digital Ray + credit / semis-equity /
power / forensic-accounting / macro-transmission research agents; Ray consult
logged in docs/Guidance/ray_dalio_review_log.md).

This module computes the Tier-1 metrics only — the ones that can TRIGGER a
stage. Tier-2 (SEC XBRL filings forensics) is Phase 2; the stage classifier
itself is Phase 3.

Two design rules carried over from the plan and enforced here:

  1. **No blended "AI bubble score".** Ray, asked directly: "I don't like
     blended scores for bubbles because they hide the real mechanics and
     create false confidence." Each metric is reported independently, same
     convention as indicators/bubble_gauge.py.

  2. **No Z-scores on the Census construction series.** The data-centre line
     has 12.7 years of history and ZERO prior downturns in it. "+2 sigma" on
     such a series means "higher than the only regime we have observed",
     which is not information. Report level, YoY and share — never a Z. This
     is a deliberate departure from the house `_full_history_z()` methodology
     and the page says so on its face.

Feeds no composite; isolated force, same convention as fed.*/market.*/order.*.
US-only by construction (every underlying series is US-specific).
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Census C30 Value of Private Construction Put in Place ─────────────────────
# Verified live 2026-10-04: direct xlsx, no key, no login. (api.census.gov now
# requires a free key; this file does not, which makes the key moot.)
# Layout verified, not assumed: sheet "Private SA", header on row index 3,
# data from row 4, dates DESCENDING in column 0 as "Aug-26p" / "Jul-26r".
_C30_URL = "https://www.census.gov/construction/c30/xlsx/privsatime.xlsx"
_C30_CACHE_TTL = 3600 * 24 * 7   # released monthly on the 1st business day
_C30_SHEET = "Private SA"
_C30_HEADER_ROW = 3
_C30_COLUMNS = {
    "data_center": "Data center",
    "chip_fab": "Computer/ electronic/ electrical",
    "nonresidential": "Nonresidential",
}

# ── EIA-930 hourly grid demand, subregion resolution ──────────────────────────
# Verified live 2026-10-04: key-free static CSV, ~1 DAY lag — the only
# metric in the whole roster that runs at better than monthly frequency.
#
# Why the overnight TROUGH and not the mean: data-centre load is flat 24/7, so
# it lifts the demand FLOOR far more than the peak, and the trough is nearly
# weather-insensitive, which kills the dominant confound.
#
# Why DOM/AEP net of PEP/BC: PEP (DC/Maryland) and BC (Baltimore) are
# physically adjacent to DOM (Dominion Virginia — "Data Center Alley"), share
# its weather, and carry no material data-centre load. Differencing against
# them is a built-in weather control that needs no degree-day model. This is
# the 2001 lesson — in the telecom bust, reported revenue was forgeable and
# lit traffic was not. A GPU that is not computing does not draw power.
_EIA930_URL = ("https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
               "EIA930_SUBREGION_{year}_{half}.csv")
_EIA930_CACHE_TTL = 3600 * 12
_EIA930_YEARS_BACK = 2          # bounded: each file is ~15 MB
# A month needs this fraction of its calendar days present to be usable; the
# current month is always partial because these files update daily.
_MONTH_COMPLETE_FRAC = 0.9
# Quarter-smoothing before the YoY comparison — see trough_excess().
_TROUGH_SMOOTH_MONTHS = 3
_DC_ZONES = ("DOM", "AEP")
_CONTROL_ZONES = ("PEP", "BC")

# ── FRED legs ─────────────────────────────────────────────────────────────────
# Every ID below was verified live 2026-10-04 (value + start date).
_FRED = {
    "abcp": ("RIFSPPAAAD30NB", "RIFSPPNAAD30NB"),   # 30d AA ABCP − nonfinancial CP
    "ndfi": "LNFACBW027SBOG",                        # bank loans to nondepository financials
    "ccc_bb": ("BAMLH0A3HYC", "BAMLH0A1HYBB"),       # CCC − BB OAS dispersion
    "it_equip": "Y034RY2Q224SBEA",                   # info-processing equipment, pp of GDP growth
    "it_soft": "B985RY2Q224SBEA",                    # software, pp of GDP growth
    "gdp_growth": "A191RL1Q225SBEA",                 # real GDP, % chg annualized
    "new_orders": "A34SNO",                          # computers & electronics new orders
}

# Thresholds — all from the plan's §3 roster, each anchored to a historical
# episode. TUNABLE, but do not move one without re-reading its anchor.
THRESHOLDS = {
    # ABCP spread: 2007-08-01 +0.09pp -> 08-10 +0.39 (the crack) -> 08-20 +0.68.
    "abcp_warn": 0.30, "abcp_crit": 0.75,
    # NDFI 13-week annualized growth; a STALL is the signal, a decline is already
    # the event (warehouse capacity is withdrawn by not renewing).
    "ndfi_warn": 5.0, "ndfi_crit": 0.0,
    # CCC-BB dispersion vs the available window's own distribution.
    "ccc_bb_warn": 8.0, "ccc_bb_crit": 10.0,
    # Data-centre construction, 6-month annualized.
    "dc_warn": 20.0, "dc_crit": 0.0,
    # Chip-fab vs data-centre divergence (the only genuine structural lead).
    "fab_warn": -20.0, "dc_diverge": 20.0,
    # IT share of all real GDP growth, 4q rolling.
    "conc_warn": 25.0,
    # Trough-load excess over the weather control, in pp.
    "load_warn": 5.0, "load_crit": 2.0,
}


# ── Census C30 ────────────────────────────────────────────────────────────────
def _parse_c30_date(raw: object, today: Optional[date] = None) -> pd.Timestamp:
    """"Aug-26p" -> 2026-08-31. The p/r suffixes are preliminary/revised flags.

    Two-digit years need a pivot: the file reaches back to 1993, so a naive
    "20" + yy turns Jan-99 into 2099. Anything more than one year ahead of
    today is 20th century.
    """
    m = re.match(r"^([A-Za-z]{3})-(\d{2})", str(raw).strip())
    if not m:
        return pd.NaT
    year = 2000 + int(m.group(2))
    cutoff = (today or date.today()).year + 1
    if year > cutoff:
        year -= 100
    try:
        return pd.Timestamp(f"{m.group(1)} {year}") + pd.offsets.MonthEnd(0)
    except ValueError:
        return pd.NaT


def fetch_census_c30(force_refresh: bool = False) -> pd.DataFrame:
    """Monthly private construction put in place, SAAR $ millions.

    Returns columns: as_of, data_center, chip_fab, nonresidential.
    Empty DataFrame (never an exception) when the source is unreachable.
    """
    from indicators.loader import fetch_url_cached

    cols = ["as_of", *_C30_COLUMNS]
    raw = fetch_url_cached(_C30_URL, "ai_census_c30.xlsx", _C30_CACHE_TTL,
                           force_refresh=force_refresh)
    if raw is None:
        return pd.DataFrame(columns=cols)
    try:
        sheet = pd.read_excel(io.BytesIO(raw), sheet_name=_C30_SHEET, header=None)
    except Exception as exc:
        logger.warning("[ai_capex] C30 parse failed: %s", exc)
        return pd.DataFrame(columns=cols)

    header = [str(h).replace("\n", " ").replace("_x000D_", "").strip()
              for h in sheet.iloc[_C30_HEADER_ROW].tolist()]
    idx = {}
    for key, label in _C30_COLUMNS.items():
        matches = [i for i, h in enumerate(header) if h.startswith(label)]
        if not matches:
            # An empty/missing column is a FAILURE, not a silent zero —
            # the Census occasionally renumbers footnote suffixes.
            logger.warning("[ai_capex] C30 column not found: %r", label)
            return pd.DataFrame(columns=cols)
        idx[key] = matches[0]

    body = sheet.iloc[_C30_HEADER_ROW + 1:].copy()
    out = pd.DataFrame({"as_of": body[0].map(_parse_c30_date)})
    for key, i in idx.items():
        out[key] = pd.to_numeric(body[i], errors="coerce")
    out = out.dropna(subset=["as_of"]).sort_values("as_of").reset_index(drop=True)
    return out


# ── EIA-930 ───────────────────────────────────────────────────────────────────
def fetch_eia930_trough(force_refresh: bool = False,
                        years_back: int = _EIA930_YEARS_BACK,
                        today: Optional[date] = None) -> pd.DataFrame:
    """Monthly mean of DAILY MINIMUM demand, by PJM subregion.

    Returns long-form columns: as_of, zone, trough_mw. Empty when unreachable.

    Bounded to `years_back` years because each six-month file is ~15 MB; that
    is enough for the year-over-year comparison the metric needs.
    """
    from indicators.loader import fetch_url_cached

    cols = ["as_of", "zone", "trough_mw"]
    this_year = (today or date.today()).year
    zones = set(_DC_ZONES) | set(_CONTROL_ZONES)
    frames = []

    for year in range(this_year - years_back, this_year + 1):
        for half in ("Jan_Jun", "Jul_Dec"):
            url = _EIA930_URL.format(year=year, half=half)
            raw = fetch_url_cached(url, f"ai_eia930_{year}_{half}.csv",
                                   _EIA930_CACHE_TTL, force_refresh=force_refresh)
            if raw is None:
                continue  # a half-year that doesn't exist yet is normal, not an error
            try:
                df = pd.read_csv(io.BytesIO(raw), low_memory=False)
            except Exception as exc:
                logger.warning("[ai_capex] EIA-930 %s %s parse failed: %s", year, half, exc)
                continue
            df.columns = [c.strip() for c in df.columns]
            if "Sub-Region" not in df.columns or "Demand (MW)" not in df.columns:
                logger.warning("[ai_capex] EIA-930 %s %s: unexpected columns", year, half)
                continue
            df = df[df["Sub-Region"].isin(zones)]
            if df.empty:
                continue
            df = df.assign(
                d=pd.to_datetime(df["Data Date"], format="%m/%d/%Y", errors="coerce"),
                mw=pd.to_numeric(df["Demand (MW)"], errors="coerce"),
            ).dropna(subset=["d", "mw"])
            frames.append(df[["d", "Sub-Region", "mw"]])

    if not frames:
        return pd.DataFrame(columns=cols)

    allrows = pd.concat(frames, ignore_index=True)
    daily_min = allrows.groupby(["Sub-Region", "d"])["mw"].min().reset_index()
    daily_min["as_of"] = daily_min["d"] + pd.offsets.MonthEnd(0)
    grouped = daily_min.groupby(["Sub-Region", "as_of"])["mw"]
    monthly = grouped.mean().reset_index().rename(
        columns={"Sub-Region": "zone", "mw": "trough_mw"})

    # Drop INCOMPLETE months. The current month is always partial — these
    # files are updated daily — and comparing four days of October against a
    # full October a year earlier produces a fabricated year-over-year move.
    # (Same failure mode as the SPF loader's incomplete-quarter CPI average,
    # docs/worklog.md 2026-10-03 entry 7; caught here the same way, by
    # actually running it rather than by inspection.)
    monthly["_days"] = grouped.size().values
    monthly["_in_month"] = monthly["as_of"].dt.day
    complete = monthly["_days"] >= (monthly["_in_month"] * _MONTH_COMPLETE_FRAC)
    dropped = monthly.loc[~complete, "as_of"].dt.strftime("%Y-%m").unique()
    if len(dropped):
        logger.info("[ai_capex] EIA-930: dropped %d incomplete month(s): %s",
                    len(dropped), ", ".join(dropped))
    monthly = monthly.loc[complete]
    return monthly[cols].sort_values(["zone", "as_of"]).reset_index(drop=True)


def trough_excess(trough: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year growth of the data-centre zones NET of the weather control.

    Returns columns: as_of, dc_yoy, control_yoy, excess_pp. The last is the
    headline: how much faster the overnight floor is rising in Data Center
    Alley than in its own weather-matched neighbours.
    """
    cols = ["as_of", "dc_yoy", "control_yoy", "excess_pp"]
    if trough.empty:
        return pd.DataFrame(columns=cols)

    wide = trough.pivot(index="as_of", columns="zone", values="trough_mw")
    have_dc = [z for z in _DC_ZONES if z in wide.columns]
    have_ctl = [z for z in _CONTROL_ZONES if z in wide.columns]
    if not have_dc or not have_ctl:
        logger.warning("[ai_capex] trough_excess: missing zones (dc=%s control=%s)",
                       have_dc, have_ctl)
        return pd.DataFrame(columns=cols)

    # Sum the zones before differencing so a zone with a reporting gap can't
    # swing the ratio the way averaging per-zone YoY would.
    dc = wide[have_dc].sum(axis=1, min_count=len(have_dc))
    ctl = wide[have_ctl].sum(axis=1, min_count=len(have_ctl))

    # Smooth over a quarter before the year-over-year comparison. The trough is
    # weather-insensitive relative to the peak, but it is not weather-PROOF: a
    # single month's storm or heatwave still lands differently in adjacent
    # zones, and the raw monthly excess swings between roughly +3pp and +14pp
    # on data whose underlying trend is steady. A 3-month mean is what makes
    # this a trend read rather than a noise read.
    dc = dc.rolling(_TROUGH_SMOOTH_MONTHS, min_periods=_TROUGH_SMOOTH_MONTHS).mean()
    ctl = ctl.rolling(_TROUGH_SMOOTH_MONTHS, min_periods=_TROUGH_SMOOTH_MONTHS).mean()

    out = pd.DataFrame({
        "as_of": wide.index,
        "dc_yoy": (dc / dc.shift(12) - 1.0).values * 100.0,
        "control_yoy": (ctl / ctl.shift(12) - 1.0).values * 100.0,
    })
    out["excess_pp"] = out["dc_yoy"] - out["control_yoy"]
    return out.dropna(subset=["excess_pp"]).reset_index(drop=True)


# ── FRED-derived legs ─────────────────────────────────────────────────────────
def _series(series_id: str, freq: str, force_refresh: bool = False) -> Optional[pd.Series]:
    from indicators.loader import fetch_series
    s = fetch_series(series_id, freq, force_refresh=force_refresh)
    if s is None or s.empty:
        logger.warning("[ai_capex] %s returned no data", series_id)
        return None
    s = s.copy()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _spread(a: str, b: str, freq: str, force_refresh: bool = False) -> pd.DataFrame:
    """a − b on their common dates, as {as_of, value}."""
    sa, sb = _series(a, freq, force_refresh), _series(b, freq, force_refresh)
    if sa is None or sb is None:
        return pd.DataFrame(columns=["as_of", "value"])
    joined = pd.concat([sa.rename("a"), sb.rename("b")], axis=1).dropna()
    if joined.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    return pd.DataFrame({"as_of": joined.index, "value": (joined["a"] - joined["b"]).values})


def it_growth_share(force_refresh: bool = False) -> pd.DataFrame:
    """IT equipment + software as a share of ALL real GDP growth, 4q rolling.

    Returns {as_of, value (percent), contribution_pp}. BOTH are returned
    deliberately: the share alone is dangerously misleading when GDP growth
    collapses — the denominator shrinks and the share spikes while the
    contribution itself is falling. Callers must display the pp level beside
    the share.
    """
    cols = ["as_of", "value", "contribution_pp"]
    eq = _series(_FRED["it_equip"], "Q", force_refresh)
    sw = _series(_FRED["it_soft"], "Q", force_refresh)
    gdp = _series(_FRED["gdp_growth"], "Q", force_refresh)
    if eq is None or sw is None or gdp is None:
        return pd.DataFrame(columns=cols)

    joined = pd.concat([eq.rename("eq"), sw.rename("sw"), gdp.rename("gdp")],
                       axis=1).dropna()
    if len(joined) < 4:
        return pd.DataFrame(columns=cols)
    it_4q = (joined["eq"] + joined["sw"]).rolling(4).sum()
    gdp_4q = joined["gdp"].rolling(4).sum()
    share = (it_4q / gdp_4q.where(gdp_4q.abs() > 1e-9)) * 100.0
    out = pd.DataFrame({
        "as_of": joined.index, "value": share.values, "contribution_pp": it_4q.values,
    }).dropna(subset=["value"]).reset_index(drop=True)
    return out


def _pct_change_annualized(s: pd.Series, periods: int, per_year: float) -> Optional[float]:
    """Annualized % growth over `periods` observations."""
    if s is None or len(s) <= periods:
        return None
    last, prior = s.iloc[-1], s.iloc[-1 - periods]
    if prior is None or prior <= 0 or pd.isna(prior) or pd.isna(last):
        return None
    return ((last / prior) ** (per_year / periods) - 1.0) * 100.0


def _yoy(df: pd.DataFrame, col: str, periods: int = 12) -> Optional[float]:
    s = df[col].dropna()
    if len(s) <= periods:
        return None
    prior = s.iloc[-1 - periods]
    if prior == 0 or pd.isna(prior):
        return None
    return (s.iloc[-1] / prior - 1.0) * 100.0


# ── Spread archive ────────────────────────────────────────────────────────────
# FRED cut every ICE BofA OAS series to a rolling 3-year window in April 2026
# (verified live: BAMLH0A0HYM2 now starts 2023-10-03). Our own DB and raw cache
# are ALREADY truncated — the long history is gone locally and is not
# recoverable. Every day not captured from here on is permanently lost, so this
# runs on every pipeline pass and only ever appends.
_ARCHIVE_SERIES = ("BAMLH0A0HYM2", "BAMLH0A3HYC", "BAMLH0A1HYBB",
                   "BAMLC0A0CM", "BAMLC0A4CBBB")
_ARCHIVE_NAME = "ai_spread_archive.parquet"


def archive_spreads(force_refresh: bool = False) -> pd.DataFrame:
    """Append today's ICE BofA observations to a monotonically-growing archive.

    Returns the full archive. Union-merges on (series_id, as_of) so re-running
    is idempotent and a provider outage can never shrink what we already hold.
    """
    from indicators.loader import RAW_CACHE_DIR

    path = RAW_CACHE_DIR / _ARCHIVE_NAME
    existing = pd.DataFrame(columns=["series_id", "as_of", "value"])
    if path.exists():
        try:
            existing = pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[ai_capex] spread archive unreadable, starting fresh: %s", exc)

    frames = [existing]
    for sid in _ARCHIVE_SERIES:
        s = _series(sid, "D", force_refresh)
        if s is None:
            continue
        frames.append(pd.DataFrame({
            "series_id": sid, "as_of": s.index, "value": s.values,
        }))

    # Drop empties before concat — an all-NA frame makes pandas warn about
    # (and eventually change) the resulting dtypes.
    frames = [f for f in frames if not f.empty]
    if not frames:
        return existing
    merged = (pd.concat(frames, ignore_index=True)
              .dropna(subset=["as_of", "value"])
              .drop_duplicates(subset=["series_id", "as_of"], keep="last")
              .sort_values(["series_id", "as_of"])
              .reset_index(drop=True))
    if len(merged) >= len(existing):
        RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(path, index=False)
        logger.info("[ai_capex] spread archive: %d rows (+%d)",
                    len(merged), len(merged) - len(existing))
    else:  # pragma: no cover - defensive; never shrink the archive
        logger.warning("[ai_capex] spread archive would shrink (%d -> %d); keeping existing",
                       len(existing), len(merged))
        return existing
    return merged


# ── Public entry point ────────────────────────────────────────────────────────
def _state(value: Optional[float], warn: float, crit: float, *,
           lower_is_worse: bool = False) -> str:
    """OK / WARNING / CRITICAL against two thresholds."""
    if value is None or pd.isna(value):
        return "—"
    if lower_is_worse:
        return "CRITICAL" if value <= crit else "WARNING" if value <= warn else "OK"
    return "CRITICAL" if value >= crit else "WARNING" if value >= warn else "OK"


def compute_ai_capex_metrics(force_refresh: bool = False) -> dict:
    """The Phase-1 Tier-1 roster. Each metric is independent — no composite.

    Every entry is {df, current, unit, state, read, ...} or None when the
    source was unreachable. A None is surfaced to the page as "unavailable",
    never silently treated as a benign zero.
    """
    t = THRESHOLDS
    out: dict = {}

    # 1. Census C30 — the divergence, and the data-centre second derivative.
    try:
        c30 = fetch_census_c30(force_refresh=force_refresh)
    except Exception as exc:
        logger.warning("[ai_capex] C30 unavailable: %s", exc)
        c30 = pd.DataFrame()

    if not c30.empty:
        dc = c30[["as_of", "data_center"]].rename(columns={"data_center": "value"}).dropna()
        fab = c30[["as_of", "chip_fab"]].rename(columns={"chip_fab": "value"}).dropna()
        dc_yoy, fab_yoy = _yoy(c30, "data_center"), _yoy(c30, "chip_fab")
        dc_6m = _pct_change_annualized(c30["data_center"].dropna(), 6, 12)
        fab_peak = fab["value"].max() if not fab.empty else None
        fab_from_peak = ((fab["value"].iloc[-1] / fab_peak - 1.0) * 100.0
                         if fab_peak else None)

        diverging = (fab_yoy is not None and dc_yoy is not None
                     and fab_yoy <= t["fab_warn"] and dc_yoy >= t["dc_diverge"])
        out["divergence"] = {
            "label": "Data-centre vs chip-fab construction",
            "df": dc, "df2": fab,
            "label_a": "Data centre", "label_b": "Chip fab",
            "current": dc_yoy, "unit": "% YoY",
            "fab_yoy": fab_yoy, "fab_from_peak": fab_from_peak,
            "state": "WARNING" if diverging else "OK",
            "read": (f"data centre {dc_yoy:+.1f}% YoY · chip fab {fab_yoy:+.1f}% YoY"
                     f" ({fab_from_peak:+.0f}% from peak)"
                     if dc_yoy is not None and fab_yoy is not None else "—"),
            "desc": ("The two legs of the BIS AI-investment measure. Facility-construction "
                     "decisions commit 2-3 years ahead, so this is the only metric in the "
                     "roster with a genuine structural lead. A sustained divergence is "
                     "either the telecom-1999 sequencing (upstream orders roll over before "
                     "downstream deployment) or CHIPS-Act expiry with no AI content — the "
                     "data cannot distinguish them."),
        }
        out["dc_construction"] = {
            "label": "Data-centre construction",
            "df": dc, "current": dc_6m, "unit": "% 6m ann.",
            "state": _state(dc_6m, t["dc_warn"], t["dc_crit"], lower_is_worse=True),
            "read": (f"{dc['value'].iloc[-1]:,.0f} $M SAAR · {dc_6m:+.0f}% 6m annualized"
                     if dc_6m is not None else "—"),
            "desc": ("Second derivative of the physical capex cycle. Note the base rate: "
                     "6-month annualized growth has gone negative 18 times in this series "
                     "and all 18 were false positives, so a trigger needs 3 consecutive "
                     "months. Reported as level/YoY/share and deliberately never as a "
                     "Z-score — 12.7 years with no prior downturn cannot support one."),
        }
    else:
        out["divergence"] = out["dc_construction"] = None

    # 2. ABCP tripwire — the 2007 seizure point, with its calibration in-sample.
    abcp = _spread(*_FRED["abcp"], "D", force_refresh)
    if not abcp.empty:
        cur = float(abcp["value"].iloc[-1])
        med = float(abcp["value"].median())
        out["abcp"] = {
            "label": "ABCP − nonfinancial CP spread",
            "df": abcp, "current": cur, "unit": "pp",
            "state": _state(cur, t["abcp_warn"], t["abcp_crit"]),
            "read": f"{cur:+.2f}pp vs a {med:+.2f}pp median over {len(abcp):,} days",
            "desc": ("Warehouse/conduit rollover price — the point that seized first in "
                     "2007, when this ran +0.09pp on 1 Aug, +0.39pp by 10 Aug and +0.68pp "
                     "by 20 Aug. Daily, 25 years of history, with the calibration event "
                     "inside the sample."),
        }
    else:
        out["abcp"] = None

    # 3. Bank loans to nondepository financials — warehouse capacity.
    ndfi = _series(_FRED["ndfi"], "W", force_refresh)
    if ndfi is not None:
        growth13 = _pct_change_annualized(ndfi, 13, 52)
        yoy = _pct_change_annualized(ndfi, 52, 52)
        out["ndfi"] = {
            "label": "Bank loans to nondepository financials",
            "df": pd.DataFrame({"as_of": ndfi.index, "value": ndfi.values}),
            "current": growth13, "unit": "% 13wk ann.",
            "state": _state(growth13, t["ndfi_warn"], t["ndfi_crit"], lower_is_worse=True),
            "read": (f"${ndfi.iloc[-1]:,.0f}bn · {growth13:+.1f}% 13wk ann. "
                     f"({yoy:+.1f}% YoY)" if growth13 is not None and yoy is not None else "—"),
            "desc": ("The bank-to-private-credit warehouse line. Capacity is withdrawn by "
                     "NOT renewing, so a stall is the signal and an outright decline is "
                     "already the event. History starts 2015 — no 2007 precedent, so this "
                     "is calibrated on its own distribution."),
        }
    else:
        out["ndfi"] = None

    # 4. CCC − BB dispersion.
    ccc = _spread(*_FRED["ccc_bb"], "D", force_refresh)
    if not ccc.empty:
        cur = float(ccc["value"].iloc[-1])
        pct = float((ccc["value"] <= cur).mean() * 100.0)
        out["ccc_bb"] = {
            "label": "CCC − BB spread dispersion",
            "df": ccc, "current": cur, "unit": "pp",
            "state": _state(cur, t["ccc_bb_warn"], t["ccc_bb_crit"]),
            "read": f"{cur:.2f}pp · {pct:.0f}th percentile of the available window",
            "desc": ("Tail-issuer repricing ahead of the index. Read with care: FRED cut "
                     "these series to a rolling 3-year window in April 2026, and there is "
                     "no US sector-level OAS at all — so the AI attribution of any move "
                     "here CANNOT be verified from free data. Needs corroboration from the "
                     "ABCP or NDFI legs before it means anything."),
        }
    else:
        out["ccc_bb"] = None

    # 5. Concentration — also the input to the growth-threshold multiplier.
    conc = it_growth_share(force_refresh)
    if not conc.empty:
        cur = float(conc["value"].iloc[-1])
        pp = float(conc["contribution_pp"].iloc[-1])
        pct = float((conc["value"] <= cur).mean() * 100.0)
        # Chart the pp CONTRIBUTION, not the share. The share is the threshold
        # variable (and what conc_adj consumes), but it is unplottable: when
        # 4-quarter GDP growth approaches zero the denominator collapses and
        # the share swings to several hundred percent in either direction,
        # which compresses today's 34% into an invisible line near the axis.
        # The contribution is the same information on a stable scale. The
        # share stays in the header value and the read line.
        out["concentration"] = {
            "label": "IT contribution to real GDP growth",
            "df": conc[["as_of", "contribution_pp"]].rename(
                columns={"contribution_pp": "value"}),
            "current": cur, "unit": "%",
            "contribution_pp": pp,
            "state": _state(cur, t["conc_warn"], 1e9),
            "read": f"{cur:.1f}% of growth ({pp:+.2f}pp) · {pct:.0f}th percentile",
            "desc": ("IT equipment + software, 4-quarter rolling. The CHART shows the "
                     "contribution in percentage points; the headline figure is that "
                     "contribution as a share of all real GDP growth. Both are given on "
                     "purpose — when GDP growth collapses the denominator shrinks and the "
                     "share spikes while the contribution is actually falling, so the "
                     "share alone is misleading and is also unplottable (it swings by "
                     "hundreds of percent near a zero denominator). The share is what "
                     "feeds the optional conc_adj growth-threshold multiplier."),
        }
    else:
        out["concentration"] = None

    # 6. New orders — the one clean mechanical trigger the 2000 analogue gave.
    orders = _series(_FRED["new_orders"], "M", force_refresh)
    if orders is not None:
        sm = orders.rolling(3).mean()
        yoy = None
        if len(sm.dropna()) > 12:
            prior = sm.dropna().iloc[-13]
            if prior and not pd.isna(prior):
                yoy = (sm.dropna().iloc[-1] / prior - 1.0) * 100.0
        out["new_orders"] = {
            "label": "Computers & electronics new orders",
            "df": pd.DataFrame({"as_of": orders.index, "value": orders.values}),
            "current": yoy, "unit": "% YoY (3m avg)",
            "state": _state(yoy, 5.0, 0.0, lower_is_worse=True),
            "read": (f"${orders.iloc[-1]:,.0f}M · {yoy:+.1f}% YoY on a 3-month average"
                     if yoy is not None else "—"),
            "desc": ("In 2000 this peaked at +15.7% in June, crossed zero in January 2001, "
                     "and the recession began that March. The peak was indistinguishable "
                     "from noise in real time; the ZERO-CROSS was the usable trigger, and "
                     "it gave about two months."),
        }
    else:
        out["new_orders"] = None

    # 7. Realized load — the only sub-monthly metric, and the demand validator.
    try:
        excess = trough_excess(fetch_eia930_trough(force_refresh=force_refresh))
    except Exception as exc:
        logger.warning("[ai_capex] EIA-930 unavailable: %s", exc)
        excess = pd.DataFrame()

    if not excess.empty:
        cur = float(excess["excess_pp"].iloc[-1])
        dcy = float(excess["dc_yoy"].iloc[-1])
        cty = float(excess["control_yoy"].iloc[-1])
        out["trough_load"] = {
            "label": "Data-centre-zone trough load, net of control",
            "df": excess.rename(columns={"excess_pp": "value"})[["as_of", "value"]],
            "current": cur, "unit": "pp excess",
            "state": _state(cur, t["load_warn"], t["load_crit"], lower_is_worse=True),
            "read": (f"{cur:+.1f}pp excess · DOM+AEP {dcy:+.1f}% YoY "
                     f"vs control {cty:+.1f}%"),
            "desc": ("Monthly mean of daily-minimum demand in Dominion Virginia and AEP, "
                     "differenced against adjacent same-weather zones (PEP, BC) that carry "
                     "no material data-centre load. Revenue can be booked, prepaid or "
                     "round-tripped; electricity draw cannot. The 2001 lesson was that lit "
                     "traffic told the truth when reported revenue did not. "
                     "Known weakness: behind-the-meter generation is invisible here."),
        }
    else:
        out["trough_load"] = None

    return out

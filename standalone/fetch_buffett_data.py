#!/usr/bin/env python3
"""Fetch the Buffett Indicator feed and write buffett_data.json with TWO numerators.

Denominator (both): FRED GDP — nominal Gross Domestic Product (quarterly, $ billions).

Numerator A — "Wilshire proxy (VTI)"  [dashboard default]
    US total market cap proxied by Vanguard Total Stock Market ETF (VTI, which
    tracks the CRSP US Total Market Index — the near-identical twin of the
    Wilshire 5000). VTI's price index is scaled to dollars via a single anchor:
    a published US total-market-cap level. Captures financials + nonfinancials,
    i.e. the same universe as the classic Buffett Indicator numerator.
    Data: Yahoo Finance chart API (free, no key). History starts 2001 (VTI inception).

Numerator B — "FRED Z.1 (nonfinancial)"
    FRED NCBEILQ027S — Nonfinancial Corporate Business; Corporate Equities;
    Liability, Level (Fed Z.1, quarterly, $ millions). Free, official, back to 1945.
    Reads a bit lower (excludes financial-sector equities).

    Buffett % = market_cap($T) / GDP($T) * 100

Re-run quarterly (after the Fed Z.1 release) to refresh. VTI updates daily, so
the proxy's latest quarter is always current.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

FRED = "https://api.stlouisfed.org/fred/series/observations"
NUMERATOR = "NCBEILQ027S"   # $ millions, quarterly
GDP = "GDP"                 # $ billions, quarterly
START = "1995-01-01"
YAHOO = "https://query2.finance.yahoo.com/v8/finance/chart/VTI?range=30y&interval=1mo"

# ── Anchor: one published US total-market-cap level, used to scale VTI → dollars.
# Source: ~US$62.2T total US equity market capitalisation at 2024-Q4 (Wilshire 5000 /
# SIFMA). Adjust this single pair when a better print is available; nothing else changes.
ANCHOR = {"year": 2024, "month": 12, "cap_tn": 62.2}

HERE = Path(__file__).resolve().parent
OUT = HERE / "buffett_data.json"


def _api_key() -> str:
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key.strip()
    env = HERE.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("FRED_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("FRED_API_KEY not set (env var or ../.env)")


def _fred(series_id: str, key: str) -> dict[str, float]:
    url = (f"{FRED}?series_id={series_id}&api_key={key}&file_type=json"
           f"&observation_start={START}&sort_order=asc")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    out = {o["date"]: float(o["value"]) for o in data.get("observations", [])
           if o.get("value") not in (None, "", ".")}
    if not out:
        sys.exit(f"No observations for {series_id}.")
    return out


def _vti_monthly() -> dict[tuple[int, int], float]:
    """Return {(year, month): month-end close} for VTI from Yahoo. {} on failure."""
    import datetime
    req = urllib.request.Request(YAHOO, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        res = d["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
    except Exception as e:                       # noqa: BLE001 — degrade gracefully
        print(f"  ! VTI fetch failed ({e}); emitting Z.1 numerator only.", file=sys.stderr)
        return {}
    out: dict[tuple[int, int], float] = {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        dt = datetime.date.fromtimestamp(t)
        out[(dt.year, dt.month)] = float(c)
    return out


def _q_endmonth(date: str) -> tuple[int, int]:
    """GDP obs date (quarter start, e.g. 2024-10-01) -> (year, quarter-end month)."""
    y, m, _ = (int(x) for x in date.split("-"))
    return y, m + 2                              # Q start month + 2 = quarter-end month


def _numerator(series, mean_key="mean"):
    ratios = [p["ratio"] for p in series]
    last = series[-1]
    return {
        "mean": round(sum(ratios) / len(ratios), 1),
        "current": {"ratio": last["ratio"], "cap_t": last["cap"], "gdp_t": last["gdp"]},
        "series": series,
    }


def main() -> None:
    key = _api_key()
    cap_m = _fred(NUMERATOR, key)                # $ millions
    gdp_b = _fred(GDP, key)                      # $ billions
    vti = _vti_monthly()                         # (y,m) -> close

    gdp_dates = sorted(gdp_b)                    # quarter-start dates, both series share GDP

    # ---- Numerator B: FRED Z.1 (nonfinancial) ----
    z1 = []
    for d in gdp_dates:
        if d not in cap_m or gdp_b[d] <= 0:
            continue
        gdp_t = gdp_b[d] / 1000.0
        cap_t = cap_m[d] / 1000.0 / 1000.0       # $M -> $B -> $T
        z1.append({"date": d, "cap": round(cap_t, 3), "gdp": round(gdp_t, 3),
                   "ratio": round(cap_t / gdp_t * 100.0, 2)})

    numerators = {}
    default = "z1"

    # ---- Numerator A: Wilshire proxy (VTI) ----
    if vti:
        anchor_close = vti.get((ANCHOR["year"], ANCHOR["month"]))
        if anchor_close:
            scale = ANCHOR["cap_tn"] / anchor_close     # $T per VTI point
            vt = []
            for d in gdp_dates:
                if gdp_b[d] <= 0:
                    continue
                close = vti.get(_q_endmonth(d))
                if close is None:                        # pre-VTI-inception quarter
                    continue
                gdp_t = gdp_b[d] / 1000.0
                cap_t = close * scale
                vt.append({"date": d, "cap": round(cap_t, 3), "gdp": round(gdp_t, 3),
                           "ratio": round(cap_t / gdp_t * 100.0, 2)})
            if vt:
                numerators["vti"] = {
                    "label": "Wilshire proxy (VTI)",
                    "desc": (f"VTI (CRSP US Total Market) scaled to ${ANCHOR['cap_tn']}T at "
                             f"{ANCHOR['year']}-{ANCHOR['month']:02d}; ÷ GDP. Total market, from 2001."),
                    **_numerator(vt),
                }
                default = "vti"

    numerators["z1"] = {
        "label": "FRED Z.1 (nonfinancial)",
        "desc": "FRED NCBEILQ027S (nonfinancial corporate equities) ÷ GDP. Official, from 1995.",
        **_numerator(z1),
    }

    payload = {
        "provider": "FRED + Yahoo Finance (VTI)",
        "updated": gdp_dates[-1],
        "default": default,
        "anchor": ANCHOR,
        "numerators": numerators,
    }
    OUT.write_text(json.dumps(payload, indent=1))

    def _fmt(nm):
        n = numerators[nm]
        s = n["series"]
        return (f"{n['label']}: {len(s)}q {s[0]['date']}→{s[-1]['date']}, "
                f"current {n['current']['ratio']:.1f}% (cap ${n['current']['cap_t']:.1f}T), "
                f"mean {n['mean']:.1f}%")
    print(f"Wrote {OUT.name}  (default: {default})")
    for nm in numerators:
        print("  " + _fmt(nm))


if __name__ == "__main__":
    main()

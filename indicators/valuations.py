"""Buffett Indicator valuation feed (operator-only dashboard page).

Produces ``buffett_data.json`` with TWO numerators over nominal GDP:

  * "Wilshire proxy (VTI)"  — US total market cap proxied by VTI (CRSP US Total
    Market, Yahoo), scaled to a published market-cap anchor. Financials + non-
    financials, from 2001. This is the dashboard default (closest to the classic
    Wilshire-5000 Buffett Indicator).
  * "FRED Z.1 (nonfinancial)" — FRED NCBEILQ027S ÷ GDP. Official, from 1995.

    Buffett % = market_cap($T) / GDP($T) * 100

This feeds the operator-only ``/valuations`` page (hidden in PUBLIC_MODE). It is
NOT a regime signal — it feeds no composite, the regime label, or the DB. The
pipeline calls :func:`refresh_buffett_data` best-effort each run; the dashboard
falls back to the repo-bundled ``standalone/buffett_data.json`` if it is missing.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

FRED = "https://api.stlouisfed.org/fred/series/observations"
NUMERATOR = "NCBEILQ027S"        # $ millions, quarterly
GDP = "GDP"                      # $ billions, quarterly
START = "1995-01-01"
YAHOO = "https://query2.finance.yahoo.com/v8/finance/chart/VTI?range=30y&interval=1mo"

# One published US total-market-cap level, used to scale VTI → dollars.
# Source: ~US$62.2T total US equity market cap at 2024-Q4 (Wilshire 5000 / SIFMA).
# Adjust this single pair when a better print is available; nothing else changes.
ANCHOR = {"year": 2024, "month": 12, "cap_tn": 62.2}

DATA_DIR = Path(os.environ.get(
    "DATA_DIR", "/mnt/data/project_data/all_weather/indicators_machine"))
_REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_JSON = _REPO_ROOT / "standalone" / "buffett_data.json"


def _api_key() -> str | None:
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key.strip()
    env = _REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("FRED_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _fred(series_id: str, key: str) -> dict[str, float]:
    url = (f"{FRED}?series_id={series_id}&api_key={key}&file_type=json"
           f"&observation_start={START}&sort_order=asc")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    return {o["date"]: float(o["value"]) for o in data.get("observations", [])
            if o.get("value") not in (None, "", ".")}


def _vti_monthly() -> dict[tuple[int, int], float]:
    """{(year, month): month-end close} for VTI from Yahoo; {} on failure."""
    import datetime
    req = urllib.request.Request(YAHOO, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
    out: dict[tuple[int, int], float] = {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        dt = datetime.date.fromtimestamp(t)
        out[(dt.year, dt.month)] = float(c)
    return out


def _q_endmonth(date: str) -> tuple[int, int]:
    y, m, _ = (int(x) for x in date.split("-"))
    return y, m + 2


def _numerator_block(series: list[dict]) -> dict:
    ratios = [p["ratio"] for p in series]
    last = series[-1]
    return {
        "mean": round(sum(ratios) / len(ratios), 1),
        "current": {"ratio": last["ratio"], "cap_t": last["cap"], "gdp_t": last["gdp"]},
        "series": series,
    }


def compute_buffett_data() -> dict:
    """Fetch both numerators + GDP and return the payload dict.

    Raises if the FRED key is missing or the Z.1 numerator can't be built (the
    minimum viable feed). VTI is best-effort: if Yahoo fails the payload simply
    ships the Z.1 numerator alone and defaults to it.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("FRED_API_KEY not set (env var or repo .env)")
    cap_m = _fred(NUMERATOR, key)
    gdp_b = _fred(GDP, key)
    if not cap_m or not gdp_b:
        raise RuntimeError("FRED returned no observations for NCBEILQ027S / GDP")

    gdp_dates = sorted(gdp_b)

    z1 = []
    for d in gdp_dates:
        if d not in cap_m or gdp_b[d] <= 0:
            continue
        gdp_t = gdp_b[d] / 1000.0
        cap_t = cap_m[d] / 1000.0 / 1000.0        # $M → $B → $T
        z1.append({"date": d, "cap": round(cap_t, 3), "gdp": round(gdp_t, 3),
                   "ratio": round(cap_t / gdp_t * 100.0, 2)})
    if not z1:
        raise RuntimeError("No overlapping quarters for the Z.1 numerator")

    numerators: dict[str, dict] = {}
    default = "z1"

    try:
        vti = _vti_monthly()
        anchor_close = vti.get((ANCHOR["year"], ANCHOR["month"]))
        if anchor_close:
            scale = ANCHOR["cap_tn"] / anchor_close
            vt = []
            for d in gdp_dates:
                if gdp_b[d] <= 0:
                    continue
                close = vti.get(_q_endmonth(d))
                if close is None:
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
                    **_numerator_block(vt),
                }
                default = "vti"
    except Exception as exc:                       # noqa: BLE001 — VTI is optional
        logger.warning("Buffett feed: VTI proxy unavailable (%s); Z.1 only.", exc)

    numerators["z1"] = {
        "label": "FRED Z.1 (nonfinancial)",
        "desc": "FRED NCBEILQ027S (nonfinancial corporate equities) ÷ GDP. Official, from 1995.",
        **_numerator_block(z1),
    }

    return {
        "provider": "FRED + Yahoo Finance (VTI)",
        "updated": gdp_dates[-1],
        "default": default,
        "anchor": ANCHOR,
        "numerators": numerators,
    }


def refresh_buffett_data(out_path: Path | None = None) -> Path | None:
    """Compute and write buffett_data.json. Returns the path, or None on failure."""
    out_path = out_path or (DATA_DIR / "buffett_data.json")
    try:
        payload = compute_buffett_data()
    except Exception as exc:                        # noqa: BLE001 — best-effort
        logger.warning("Buffett feed refresh skipped: %s", exc)
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1))
    return out_path


def data_path() -> Path:
    """The JSON the dashboard should serve: live DATA_DIR copy, else repo-bundled."""
    live = DATA_DIR / "buffett_data.json"
    return live if live.exists() else BUNDLED_JSON


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = refresh_buffett_data()
    print(f"wrote {p}" if p else "refresh failed (see log)")

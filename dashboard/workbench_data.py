"""Data layer for the Workbench (TV-style chart studio, route /workbench).

Three jobs:
  1. A unified SEARCH INDEX over everything plottable — all signals across
     all countries, the per-country composite scores, debt-stress, and the
     raw FRED parquet cache (with titles from the meta sidecars).
  2. Series resolution + per-series TRANSFORMS (raw / rebase=100 /
     % from start / YoY % / stored Z-score).
  3. SAVED VIEWS — named chart layouts persisted as JSON under DATA_DIR
     (deliberately NOT in signals.duckdb: the dashboard only holds read-only
     connections to the DB, and a writer would conflict with them).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

from dashboard.charting_data import DB_PATH, RAW_CACHE_DIR

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.environ.get("DATA_DIR", "/mnt/data/project_data/all_weather/indicators_machine"))
SAVED_VIEWS_PATH = _DATA_DIR / "saved_views.json"

_COUNTRY_FLAGS = {"US": "🇺🇸", "EZ": "🇪🇺", "GB": "🇬🇧", "JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳",
                  "IN": "🇮🇳", "DE": "🇩🇪", "LU": "🇱🇺", "BR": "🇧🇷", "CA": "🇨🇦",
                  "AU": "🇦🇺", "MX": "🇲🇽", "ID": "🇮🇩"}

TRANSFORMS = {
    "raw":       "Raw",
    "rebase":    "Rebase = 100",
    "pct_start": "% from start",
    "yoy":       "YoY %",
    "z":         "Z-score (stored)",
}

# ── Search index ──────────────────────────────────────────────────────────────

_INDEX_CACHE: dict = {"built": 0.0, "rows": []}
_INDEX_TTL_S = 600


def _label_from_id(signal_id: str) -> str:
    parts = signal_id.split(".")
    concept = parts[-1] if len(parts) >= 3 else signal_id
    return concept.replace("_", " ").title()


def build_search_index(force_refresh: bool = False) -> list[dict]:
    """Every plottable series as {key, source, label, country, group, freq,
    units, first, last}. Cached for 10 minutes."""
    if not force_refresh and _INDEX_CACHE["rows"] and time.time() - _INDEX_CACHE["built"] < _INDEX_TTL_S:
        return _INDEX_CACHE["rows"]

    rows: list[dict] = []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        # 1. Signals — one entry per id
        sig = con.execute("""
            SELECT id, any_value(country) AS country, any_value(force) AS force,
                   any_value(units) AS units, any_value(provider) AS provider,
                   min(as_of) AS first, max(as_of) AS last, count(*) AS n
            FROM signals GROUP BY id ORDER BY id
        """).df()
        for r in sig.itertuples(index=False):
            rows.append({
                "key": r.id, "source": "signal",
                "label": f"{_label_from_id(r.id)} ({r.country})",
                "country": r.country, "group": str(r.force),
                "units": str(r.units), "provider": str(r.provider),
                "first": str(r.first)[:7], "last": str(r.last)[:7], "n": int(r.n),
            })
        # 2. Composite scores per country
        comp_cols = ["growth_score", "inflation_score", "rate_score", "credit_score",
                     "volatility_score", "productivity_score", "disequilibrium_score"]
        countries = [r[0] for r in con.execute(
            "SELECT DISTINCT country FROM composites ORDER BY country").fetchall()]
        for cc in countries:
            spans = con.execute(
                f"SELECT {', '.join(f'min(as_of) FILTER (WHERE {c} IS NOT NULL)' for c in comp_cols)}, "
                f"{', '.join(f'max(as_of) FILTER (WHERE {c} IS NOT NULL)' for c in comp_cols)} "
                f"FROM composites WHERE country = ?", [cc]).fetchone()
            for i, col in enumerate(comp_cols):
                first, last = spans[i], spans[i + len(comp_cols)]
                if first is None:
                    continue
                nice = col.replace("_score", "").replace("_", " ").title()
                rows.append({
                    "key": f"{cc}|{col}", "source": "composite",
                    "label": f"{nice} Composite Z ({cc})",
                    "country": cc, "group": "composite", "units": "Z",
                    "provider": "engine", "first": str(first)[:7],
                    "last": str(last)[:7], "n": 0,
                })
        # 3. Debt stress
        for cc, first, last in con.execute(
                "SELECT country, min(as_of), max(as_of) FROM debt_stress_snapshots "
                "GROUP BY country").fetchall():
            rows.append({
                "key": f"{cc}|stress_score", "source": "debtstress",
                "label": f"Debt Stress Composite ({cc})",
                "country": cc, "group": "debt cycle", "units": "Z",
                "provider": "engine", "first": str(first)[:7],
                "last": str(last)[:7], "n": 0,
            })
    finally:
        con.close()

    # 4. Raw FRED parquet cache (titles from meta sidecars where present)
    for pq in sorted(RAW_CACHE_DIR.glob("fred_*.parquet")):
        fred_id = pq.stem[len("fred_"):]
        if fred_id.endswith("_meta"):
            continue
        title = fred_id
        meta = RAW_CACHE_DIR / f"fred_{fred_id}_meta.json"
        if meta.exists():
            try:
                title = json.loads(meta.read_text()).get("title", fred_id)[:70]
            except Exception:
                pass
        rows.append({
            "key": fred_id, "source": "raw",
            "label": f"{title} [RAW {fred_id}]",
            "country": "—", "group": "raw fred", "units": "level",
            "provider": "FRED", "first": "", "last": "", "n": 0,
        })

    _INDEX_CACHE.update(built=time.time(), rows=rows)
    return rows


def search_index(query: str, countries: Optional[list] = None,
                 groups: Optional[list] = None, limit: int = 30) -> list[dict]:
    """Fuzzy-ish search: every whitespace-separated token must appear in the
    label, key, group, or provider (case-insensitive). Facets filter first."""
    rows = build_search_index()
    if countries:
        rows = [r for r in rows if r["country"] in countries]
    if groups:
        rows = [r for r in rows if r["group"] in groups]
    tokens = [t for t in re.split(r"\s+", (query or "").lower()) if t]
    if tokens:
        def hit(r):
            hay = f"{r['label']} {r['key']} {r['group']} {r['provider']}".lower()
            return all(t in hay for t in tokens)
        rows = [r for r in rows if hit(r)]
    return rows[:limit]


# ── Series loading + transforms ───────────────────────────────────────────────

def load_series(source: str, key: str) -> tuple[pd.Series, dict]:
    """Resolve one search-index entry to a datetime-indexed value series."""
    meta = {"source": source, "key": key}
    if source == "signal":
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            df = con.execute(
                "SELECT as_of, value, zscore FROM signals WHERE id = ? "
                "AND value IS NOT NULL ORDER BY as_of", [key]).df()
        finally:
            con.close()
        if df.empty:
            return pd.Series(dtype=float), meta
        df["as_of"] = pd.to_datetime(df["as_of"])
        s = df.set_index("as_of")["value"]
        meta["zscore"] = df.set_index("as_of")["zscore"]
        return s, meta
    if source in ("composite", "debtstress"):
        cc, col = key.split("|", 1)
        table = "composites" if source == "composite" else "debt_stress_snapshots"
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            df = con.execute(
                f"SELECT as_of, {col} AS value FROM {table} WHERE country = ? "
                f"AND {col} IS NOT NULL ORDER BY as_of", [cc]).df()
        finally:
            con.close()
        if df.empty:
            return pd.Series(dtype=float), meta
        df["as_of"] = pd.to_datetime(df["as_of"])
        return df.set_index("as_of")["value"], meta
    if source == "raw":
        pq = RAW_CACHE_DIR / f"fred_{key}.parquet"
        if not pq.exists():
            return pd.Series(dtype=float), meta
        s = pd.read_parquet(pq).iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        return s.sort_index().dropna(), meta
    return pd.Series(dtype=float), meta


def _periods_per_year(s: pd.Series) -> int:
    if len(s) < 3:
        return 12
    med_days = np.median(np.diff(s.index.values).astype("timedelta64[D]").astype(float))
    if med_days <= 4:
        return 252
    if med_days <= 9:
        return 52
    if med_days <= 45:
        return 12
    if med_days <= 135:
        return 4
    return 1


def apply_transform(s: pd.Series, transform: str,
                    meta: Optional[dict] = None,
                    window_start: Optional[pd.Timestamp] = None) -> tuple[pd.Series, str]:
    """Apply one of TRANSFORMS. Returns (series, axis-label suffix).

    rebase / pct_start anchor at the first valid point INSIDE the visible
    window (TV 'compare' behavior) — pass window_start for that.
    """
    if s.empty or transform in (None, "raw"):
        return s, ""
    if transform == "z":
        z = (meta or {}).get("zscore")
        if z is not None and not z.dropna().empty:
            return z.dropna(), " (Z, stored)"
        # composites/debtstress are already Z; raw has no stored Z
        return s, " (Z)" if (meta or {}).get("source") in ("composite", "debtstress") else ""
    if transform == "yoy":
        ppy = _periods_per_year(s)
        if ppy >= 52:                       # daily/weekly → month-end first
            s = s.resample("ME").last()
            ppy = 12
        return (s.pct_change(ppy) * 100).dropna(), " (YoY %)"
    # window-anchored transforms
    win = s
    if window_start is not None:
        win = s[s.index >= window_start]
        if win.empty:
            win = s
    base = win.dropna()
    if base.empty:
        return s, ""
    anchor = base.iloc[0]
    if anchor == 0 or pd.isna(anchor):
        return s, ""
    if transform == "rebase":
        return (s / anchor) * 100.0, " (rebased=100)"
    if transform == "pct_start":
        return (s / anchor - 1.0) * 100.0, " (% from start)"
    return s, ""


# ── Saved views (JSON under DATA_DIR — see module docstring for why) ─────────

PRESET_VIEWS: dict[str, dict] = {
    "★ US Inflation Stack": {
        "mode": "stacked", "timeframe": "10Y",
        "series": [
            {"source": "signal", "key": "us.inflation.cpi_headline", "transform": "raw", "pane": 1},
            {"source": "signal", "key": "us.inflation.cpi_core", "transform": "raw", "pane": 1},
            {"source": "signal", "key": "us.inflation.wages", "transform": "raw", "pane": 2},
            {"source": "signal", "key": "us.inflation.breakeven_avg", "transform": "raw", "pane": 3},
        ],
    },
    "★ Policy Rates — 5 Countries": {
        "mode": "overlay", "timeframe": "10Y",
        "series": [
            {"source": "signal", "key": "us.policy.yield_10y", "transform": "raw"},
            {"source": "signal", "key": "ez.policy.yield_10y", "transform": "raw"},
            {"source": "signal", "key": "gb.policy.yield_10y", "transform": "raw"},
            {"source": "signal", "key": "jp.policy.yield_10y", "transform": "raw"},
            {"source": "signal", "key": "kr.policy.yield_10y", "transform": "raw"},
        ],
    },
    "★ US Credit Conditions": {
        "mode": "stacked", "timeframe": "10Y",
        "series": [
            {"source": "signal", "key": "us.credit.lending_standards", "transform": "raw", "pane": 1},
            {"source": "signal", "key": "us.credit.loan_demand", "transform": "raw", "pane": 1},
            {"source": "signal", "key": "us.premium.high_yield_spread", "transform": "raw", "pane": 2},
            {"source": "composite", "key": "US|credit_score", "transform": "raw", "pane": 3},
        ],
    },
    "★ The Two Dials (US)": {
        "mode": "overlay", "timeframe": "10Y",
        "series": [
            {"source": "composite", "key": "US|growth_score", "transform": "raw"},
            {"source": "composite", "key": "US|inflation_score", "transform": "raw"},
        ],
    },
}


def _read_views_file() -> dict:
    if SAVED_VIEWS_PATH.exists():
        try:
            return json.loads(SAVED_VIEWS_PATH.read_text())
        except Exception as exc:
            logger.warning("saved_views.json unreadable (%s) — starting empty", exc)
    return {}


def list_views() -> list[str]:
    return sorted(PRESET_VIEWS) + sorted(_read_views_file())


def get_view(name: str) -> Optional[dict]:
    if name in PRESET_VIEWS:
        return PRESET_VIEWS[name]
    return _read_views_file().get(name)


def save_view(name: str, spec: dict) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("View name is empty")
    if name in PRESET_VIEWS:
        raise ValueError("That name is a built-in preset — pick another")
    views = _read_views_file()
    views[name] = spec
    SAVED_VIEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SAVED_VIEWS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(views, indent=2))
    tmp.replace(SAVED_VIEWS_PATH)


def delete_view(name: str) -> None:
    views = _read_views_file()
    if name in views:
        del views[name]
        tmp = SAVED_VIEWS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(views, indent=2))
        tmp.replace(SAVED_VIEWS_PATH)

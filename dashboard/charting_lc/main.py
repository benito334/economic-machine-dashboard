"""
TradingView Lightweight Charts — FastAPI data API (ADR-007 Option B).

Run locally:
    uvicorn dashboard.charting_lc.main:app --host 0.0.0.0 --port 8000 --reload

In Docker, started via docker-compose service `lc_api`.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from dashboard.charting_data import (
    load_composite_history,
    load_series_catalog,
    load_signal_history,
    load_yield_curve_term_structure,
)

DB_PATH = Path(os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"))

app = FastAPI(title="Indicators Machine — Charting API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(v) -> Optional[float]:
    """Safely convert to float, returning None for nulls/NaN."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if pd.isna(f) else round(f, 6)
    except (TypeError, ValueError):
        return None


def _label_from_id(signal_id: str) -> str:
    parts = signal_id.split(".")
    concept = parts[2] if len(parts) >= 3 else signal_id
    return concept.replace("_", " ").title()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/catalog")
def get_catalog() -> list[dict]:
    """Return the full series catalog from chart_series.yaml."""
    return load_series_catalog()


@app.get("/series/{signal_id:path}")
def get_series(
    signal_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    col: str = Query("value", description="Column: value|zscore|change_1m|change_3m|change_12m"),
) -> list[dict]:
    """Return [{time, value}] for one signal."""
    allowed = {"value", "zscore", "level_percentile", "change_1m", "change_3m", "change_12m"}
    if col not in allowed:
        raise HTTPException(status_code=400, detail=f"col must be one of {allowed}")
    df = load_signal_history(signal_id, value_col=col, start_date=start, end_date=end)
    if df.empty:
        return []
    return [
        {"time": row["as_of"].strftime("%Y-%m-%d"), "value": _f(row["value"])}
        for _, row in df.iterrows()
        if _f(row["value"]) is not None
    ]


@app.get("/composite-history")
def get_composite_history(
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[dict]:
    """Return composite scores + momentum + quadrant history."""
    df = load_composite_history(start_date=start, end_date=end)
    if df.empty:
        return []
    result = []
    for _, row in df.iterrows():
        result.append({
            "time":               row["as_of"].strftime("%Y-%m-%d"),
            "growth_score":       _f(row.get("growth_score")),
            "inflation_score":    _f(row.get("inflation_score")),
            "growth_momentum":    _f(row.get("growth_momentum")),
            "inflation_momentum": _f(row.get("inflation_momentum")),
            "confidence":         _f(row.get("confidence")),
            "quadrant":           str(row.get("quadrant") or ""),
        })
    return result


@app.get("/signals/snapshot")
def get_signals_snapshot() -> list[dict]:
    """Latest snapshot for all US signals — powers the Macro Table."""
    # Load catalog for display labels and descriptions
    catalog = load_series_catalog()
    label_map = {s["signal_id"]: s["label"] for s in catalog}
    desc_map  = {s["signal_id"]: s.get("description", "") for s in catalog}

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute("""
            WITH latest AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) AS rn
                FROM signals WHERE country = 'US'
            )
            SELECT id, force, as_of, value, units, zscore, level_percentile,
                   momentum_percentile, direction,
                   change_1m, change_3m, change_12m,
                   is_stale, low_history, is_proxy, is_constructed, linkage
            FROM latest WHERE rn = 1
            ORDER BY force, id
        """).df()
    finally:
        con.close()

    df["as_of"] = pd.to_datetime(df["as_of"])
    records = []
    for _, row in df.iterrows():
        sid = row["id"]
        records.append({
            "id":                   sid,
            "force":                row["force"],
            "label":                label_map.get(sid, _label_from_id(sid)),
            "description":          desc_map.get(sid, ""),
            "as_of":                row["as_of"].strftime("%Y-%m-%d") if pd.notna(row["as_of"]) else None,
            "value":                _f(row.get("value")),
            "units":                row.get("units") or "",
            "zscore":               _f(row.get("zscore")),
            "level_percentile":     _f(row.get("level_percentile")),
            "momentum_percentile":  _f(row.get("momentum_percentile")),
            "direction":            row.get("direction") or "",
            "change_1m":            _f(row.get("change_1m")),
            "change_3m":            _f(row.get("change_3m")),
            "change_12m":           _f(row.get("change_12m")),
            "is_stale":             bool(row.get("is_stale", False)),
            "low_history":          bool(row.get("low_history", False)),
            "is_proxy":             bool(row.get("is_proxy", False)),
            "is_constructed":       bool(row.get("is_constructed", False)),
            "linkage":              row.get("linkage") or "",
        })
    return records


@app.get("/yield-curve/{date}")
def get_yield_curve(date: str) -> list[dict]:
    """Return [{maturity_years, label, yield_pct}] for the term structure at a date."""
    df = load_yield_curve_term_structure(date)
    return df.to_dict(orient="records")

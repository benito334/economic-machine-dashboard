"""
Option B skeleton — FastAPI data API for TradingView Lightweight Charts.
Deferred per ADR-007; activate when TradingView UX is required.

To run locally:
    pip install fastapi uvicorn
    uvicorn dashboard.charting_lc.main:app --port 8000 --reload
"""
from __future__ import annotations

# FastAPI is not in requirements.txt (deferred). Guard the import.
try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore

from dashboard.charting_data import load_signal_history, load_yield_curve_term_structure

if _FASTAPI_AVAILABLE:
    app = FastAPI(title="Indicators Machine — Charting API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/series/{signal_id}")
    def get_series(
        signal_id: str,
        start: str | None = None,
        end: str | None = None,
        value_col: str = "value",
    ) -> list[dict]:
        """Return [{time: ISO-date, value: float}] for a signal."""
        df = load_signal_history(signal_id, value_col=value_col, start_date=start, end_date=end)
        return [
            {"time": row["as_of"].strftime("%Y-%m-%d"), "value": row["value"]}
            for _, row in df.iterrows()
        ]

    @app.get("/yield-curve/{date}")
    def get_yield_curve(date: str) -> list[dict]:
        """Return [{maturity_years, label, yield_pct}] for the term structure on a date."""
        df = load_yield_curve_term_structure(date)
        return df.to_dict(orient="records")

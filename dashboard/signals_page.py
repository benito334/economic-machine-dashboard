"""Signals page — 5-force signal breakdown for the selected country.

Route: /signals
Shows Growth · Inflation · Interest Rate · Credit · Volatility.
Each section header displays the force composite Z-score and momentum direction.
Each section body mirrors the lens tables on the Regime Map page.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from dash import Input, Output, callback, html, no_update

from dashboard.charting_data import load_composite_history, load_latest_signals
from dashboard.shared_components import _DIR_ARROW, _zscore_color, build_force_table

# ── Rate section — policy-force concepts to exclude per country ───────────────
# US: balance-sheet series are QE/QT trackers, not rate signals
# EZ: fed_funds_target is a US series that was accidentally mapped to EZ;
#     central_bank_assets tracks ECB balance sheet (excluded here)
_RATE_EXCLUDE: dict[str, set] = {
    "US": {"fed_balance_sheet", "monetary_base_gdp"},
    "EZ": {"central_bank_assets", "fed_funds_target"},
    "KR": set(),
}

# Force accent colours (must not clash with the ones used in the existing lens tables)
_FORCE_ACCENT: dict[str, str] = {
    "Growth":        "#5CBA8A",   # green
    "Inflation":     "#E8734C",   # orange
    "Interest Rate": "#4C9BE8",   # blue
    "Credit":        "#B07FD4",   # purple
    "Volatility":    "#F4C842",   # gold
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _concept(signal_id: str) -> str:
    parts = signal_id.split(".")
    return parts[-1] if len(parts) >= 3 else signal_id


def _majority_arrow(directions: "pd.Series") -> str:
    rising  = (directions == "rising").sum()
    falling = (directions == "falling").sum()
    if rising > falling:
        return "↑"
    if falling > rising:
        return "↓"
    return "→"


def _mean_z(df: "pd.DataFrame") -> Optional[float]:
    if df.empty or "zscore" not in df.columns:
        return None
    vals = df["zscore"].dropna()
    return float(vals.mean()) if not vals.empty else None


def _vix_df(country: str) -> "pd.DataFrame":
    """Load VIX as a one-row synthetic signals DataFrame (US only)."""
    if country != "US":
        return pd.DataFrame()
    try:
        from indicators.regime_classifier import _load_vix

        vix = _load_vix()
        if vix is None or vix.empty:
            return pd.DataFrame()
        window     = 120
        roll       = vix.rolling(window, min_periods=24)
        z_series   = (vix - roll.mean()) / roll.std()
        last_val   = float(vix.iloc[-1])
        prev_val   = float(vix.iloc[-2]) if len(vix) > 1 else last_val
        direction  = "rising" if last_val > prev_val else "falling"
        pct_rank   = float((vix <= last_val).mean())
        z_val: Optional[float] = (
            float(z_series.iloc[-1]) if not z_series.empty and not math.isnan(z_series.iloc[-1])
            else None
        )
        return pd.DataFrame([{
            "id":                "us.volatility.vix",
            "force":             "volatility",
            "lead_lag":          "leading",
            "value":             last_val,
            "units":             "index",
            "direction":         direction,
            "level_percentile":  pct_rank,
            "zscore":            z_val,
            "is_proxy":          False,
            "is_stale":          False,
            "vintage_available": True,
            "low_history":       False,
            "source":            "FRED:VIXCLS",
            "linkage":           "Equity volatility index — rising VIX signals risk-off and credit stress",
        }])
    except Exception:
        return pd.DataFrame()


def _section_header(
    force_name: str,
    composite_z: Optional[float],
    momentum_arrow: str,
    accent: str,
    n_signals: int,
) -> html.Summary:
    z_str   = (
        f"{composite_z:+.2f}"
        if composite_z is not None and not math.isnan(composite_z)
        else "—"
    )
    z_color = _zscore_color(composite_z) if composite_z is not None else "#888"

    return html.Summary(
        html.Div([
            html.Span(force_name, style={
                "fontWeight": "700",
                "fontSize":   "0.95rem",
                "color":      accent,
                "minWidth":   "130px",
                "display":    "inline-block",
            }),
            html.Span("Z ", style={"color": "#666", "fontSize": "0.78em"}),
            html.Span(z_str, style={
                "fontFamily": "monospace", "color": z_color,
                "fontWeight": "600", "marginRight": "20px",
            }),
            html.Span("Mom ", style={"color": "#666", "fontSize": "0.78em"}),
            html.Span(momentum_arrow, style={"fontSize": "1.05em", "marginRight": "20px"}),
            html.Span(f"{n_signals} signal{'s' if n_signals != 1 else ''}",
                      style={"color": "#555", "fontSize": "0.75em"}),
        ], style={
            "display":    "flex",
            "alignItems": "center",
            "flexWrap":   "wrap",
            "gap":        "4px",
        }),
        style={
            "cursor":            "pointer",
            "padding":           "10px 14px",
            "background":        "#1a1d26",
            "listStyle":         "none",
            "WebkitAppearance":  "none",
            "outline":           "none",
            "userSelect":        "none",
        },
    )


def _build_section(
    force_name: str,
    force_df: "pd.DataFrame",
    composite_z: Optional[float],
) -> html.Details:
    accent   = _FORCE_ACCENT.get(force_name, "#aaa")
    arrow    = _majority_arrow(force_df["direction"]) if not force_df.empty else "→"
    n        = len(force_df)
    header   = _section_header(force_name, composite_z, arrow, accent, n)
    body_tbl = build_force_table(force_df)
    return html.Details(
        [
            header,
            html.Div(body_tbl, style={"padding": "0 0 4px 0"}),
        ],
        open=True,
        style={
            "marginBottom": "8px",
            "background":   "#12141c",
            "borderRadius": "8px",
            "border":       "1px solid #2a2d3a",
            "overflow":     "hidden",
        },
    )


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div(
        html.Div(id="signals-content"),
        style={"padding": "16px 20px"},
    )


# ── Callback ──────────────────────────────────────────────────────────────────

@callback(
    Output("signals-content", "children"),
    [Input("country-store", "data"),
     Input("page-trigger",  "data")],
    prevent_initial_call=False,
)
def render_signals(country_data, page_trigger):
    page    = (page_trigger or {}).get("page", "")
    if page and page != "/signals":
        return no_update

    country = (country_data or {}).get("country", "US").upper()

    # ── Load signals ──────────────────────────────────────────────────────────
    signals = load_latest_signals(country)

    # Latest Growth / Inflation composite Z-scores from the composites table
    g_z: Optional[float] = None
    i_z: Optional[float] = None
    try:
        comp = load_composite_history(country=country)
        if not comp.empty:
            row = comp.iloc[-1]
            g_z = float(row["growth_score"])   if pd.notna(row.get("growth_score"))    else None
            i_z = float(row["inflation_score"]) if pd.notna(row.get("inflation_score")) else None
    except Exception:
        pass

    # ── Slice by force ────────────────────────────────────────────────────────
    exc_rate = _RATE_EXCLUDE.get(country, set())

    growth_df    = signals[signals["force"] == "growth"].copy()
    inflation_df = signals[signals["force"] == "inflation"].copy()
    rate_df      = signals[
        (signals["force"] == "policy") &
        ~signals["id"].apply(_concept).isin(exc_rate)
    ].copy()
    credit_df    = signals[signals["force"].isin(["credit", "premium"])].copy()
    vol_df       = _vix_df(country)

    rate_z   = _mean_z(rate_df)
    credit_z = _mean_z(credit_df)
    vol_z    = _mean_z(vol_df)

    # ── Header ────────────────────────────────────────────────────────────────
    last_obs = signals["as_of"].max() if not signals.empty else "—"
    page_header = html.Div([
        html.H5(
            f"Signals — {country}",
            style={"color": "#ddd", "margin": "0 0 4px 0"},
        ),
        html.Div(
            f"Latest observation: {last_obs}",
            style={"color": "#555", "fontSize": "0.78em", "marginBottom": "16px"},
        ),
    ])

    # ── Sections ──────────────────────────────────────────────────────────────
    sections = [
        _build_section("Growth",        growth_df,    g_z),
        _build_section("Inflation",      inflation_df, i_z),
        _build_section("Interest Rate",  rate_df,      rate_z),
        _build_section("Credit",         credit_df,    credit_z),
        _build_section("Volatility",     vol_df,       vol_z),
    ]

    return html.Div([page_header] + sections)

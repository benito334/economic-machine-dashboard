"""
Phase 1D — Plotly Dash interactive charting view.

Served on port :8502 alongside the Streamlit regime dashboard (:8501).
Features:
  - Series selector sidebar grouped by lens
  - Multi-pane chart: each selected group gets its own subplot row with
    independent Y-axis; shared X-axis; hovermode="x unified"
  - Time-horizon presets (1Y / 3Y / 5Y / 10Y / MAX) + RangeSlider
  - Yield curve tab: term-structure at a selected date + historical spreads
  - Theme switcher: Midnight / Carbon / Slate / Dawn
"""
from __future__ import annotations

import datetime
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dash_table, dcc, html, no_update
from plotly.subplots import make_subplots

from dashboard.charting_data import (
    available_dates_for_yield_curve,
    load_all_signal_histories,
    load_change_feed,
    load_composite_component_status,
    load_composite_history,
    load_composite_signal_values,
    load_debt_stress_component_dates,
    load_debt_stress_history,
    load_latest_signals,
    load_series_catalog,
    load_signal_history,
    load_yield_curve_term_structure,
)
from dashboard.themes import DEFAULT_THEME, THEME_CSS_VARS, THEMES, figure_layout
from dashboard import data_dashboard as _data_dashboard
from dashboard import explorer as _explorer
from dashboard import global_overview as _global_overview
from dashboard import methodology as _methodology
from dashboard import weight_audit as _weight_audit

# ── App setup ─────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    title="Indicators Machine — Charts",
    update_title=None,          # prevent "Updating..." tab flicker from poll interval
    suppress_callback_exceptions=True,
)
server = app.server  # expose Flask for Gunicorn / production
_explorer.register_callbacks(app)       # Phase 1E Data Explorer callbacks
_data_dashboard.register_callbacks(app) # Data Feed Monitor sort + filter

# ── Palette ──────────────────────────────────────────────────────────────────

_COLORS = [
    "#4C9BE8",  # blue
    "#F4C842",  # yellow
    "#5CBA8A",  # green
    "#E8734C",  # orange
    "#B07FD4",  # purple
    "#E84C82",  # pink
    "#4CE8D4",  # teal
    "#E8C94C",  # gold
    "#8AB4F4",  # light blue
    "#F4A442",  # amber
]

_QUADRANT_COLOR = {
    "Expansion": "#5CBA8A",
    "Inflationary Boom": "#F4C842",
    "Stagflation": "#E8734C",
    "Disinflationary Slowdown": "#4C9BE8",
}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ── Rolling Z-score composite helpers ────────────────────────────────────────

def _load_composites_config_cached(country: str = "US") -> dict:
    """Load composites config once per process (config rarely changes)."""
    from indicators.composites import load_composites_config
    return load_composites_config(country)


def _compute_rolling_history(country: str, window: int) -> pd.DataFrame:
    """
    Recompute growth and inflation force scores across the full history using a
    rolling Z-score window.  Returns DataFrame with columns:
        as_of (datetime), rolling_growth, rolling_inflation.

    Used when the Settings panel selects a finite look-back window.
    Nominal weights from composites.yaml are applied; no momentum tilts
    (those depend on Z-sign which would be circular at this layer).
    """
    from indicators.normalize import zscore_rolling, ZSCORE_CAP_SIGMA

    cfg = _load_composites_config_cached(country)
    values_df = load_composite_signal_values(country)
    if values_df.empty:
        return pd.DataFrame()

    prefix = country.lower()

    def _force_series(indicators: list) -> pd.Series:
        weight_map: dict[str, float] = {}
        invert_map: dict[str, bool] = {}
        for ind in indicators:
            sig_id = f"{prefix}.{ind['id']}"
            w = (
                float(ind.get("base_share", 1.0))
                * float(ind.get("importance", 1.0))
                * float(ind.get("quality_factor", 1.0))
            )
            weight_map[sig_id] = w
            invert_map[sig_id] = bool(ind.get("invert", False))

        total = sum(weight_map.values())
        if total <= 0:
            return pd.Series(dtype=float)
        norm_w = {k: v / total for k, v in weight_map.items()}

        # Build rolling Z per signal on its native date index
        z_dict: dict[str, pd.Series] = {}
        for sig_id, w in norm_w.items():
            raw = (
                values_df[values_df["id"] == sig_id]
                .set_index("as_of")["value"]
                .sort_index()
                .dropna()
            )
            if raw.empty:
                continue
            z = zscore_rolling(raw, window)
            if invert_map[sig_id]:
                z = -z
            z_dict[sig_id] = z

        if not z_dict:
            return pd.Series(dtype=float)

        # Align to a monthly date range with ffill ≤ 95 days (covers one quarter)
        min_dt = min(s.index.min() for s in z_dict.values())
        max_dt = max(s.index.max() for s in z_dict.values())
        monthly_idx = pd.date_range(min_dt, max_dt, freq="MS")

        # Weighted numerator and denominator (re-normalise over available signals)
        num = pd.Series(0.0, index=monthly_idx)
        den = pd.Series(0.0, index=monthly_idx)
        for sig_id, z_s in z_dict.items():
            w = norm_w[sig_id]
            z_aligned = z_s.reindex(monthly_idx, method="ffill",
                                    tolerance=pd.Timedelta(days=95))
            mask = z_aligned.notna()
            num += z_aligned.fillna(0.0) * w
            den += mask.astype(float) * w

        score = (num / den.replace(0.0, float("nan"))).clip(
            lower=-ZSCORE_CAP_SIGMA, upper=ZSCORE_CAP_SIGMA
        )
        return score

    g = _force_series(cfg.get("growth_score", {}).get("indicators", []))
    i_s = _force_series(cfg.get("inflation_score", {}).get("indicators", []))

    if g.empty and i_s.empty:
        return pd.DataFrame()

    idx = g.index if not g.empty else i_s.index
    return pd.DataFrame({
        "as_of": idx,
        "rolling_growth": g.reindex(idx).values,
        "rolling_inflation": i_s.reindex(idx).values,
    })


def _momentum_z_at(comp: pd.DataFrame, idx: int, window: int = 12) -> tuple:
    """
    Return (g_mom_z, i_mom_z): Z-score of the current MoM force-score change
    against the preceding `window` monthly changes.

    comp must be sorted oldest-first (as returned by load_composite_history).
    idx is the integer position of the selected snapshot.
    """
    if comp.empty or idx < 1:
        return None, None

    def _z(series: pd.Series) -> "float | None":
        deltas = series.astype(float).diff()
        if idx >= len(deltas):
            return None
        current = deltas.iloc[idx]
        if pd.isna(current):
            return None
        start = max(1, idx - window + 1)
        window_vals = deltas.iloc[start: idx + 1].dropna()
        if len(window_vals) < 3:
            return None
        mu, sd = window_vals.mean(), window_vals.std(ddof=1)
        if sd == 0 or pd.isna(sd):
            return None
        return float(np.clip((current - mu) / sd, -4.0, 4.0))

    return _z(comp["growth_score"]), _z(comp["inflation_score"])


# ── Regime Map panel helpers (What Changed / Conflicts / Lens Drill-Downs) ────

import math as _math

_DIR_ARROW = {"rising": "↑", "falling": "↓", "flat": "→"}

_LENS_GROUPS: list[tuple[str, list[str]]] = [
    ("Nominal Spending Master Indicators", ["master"]),
    ("A · Growth Force",                   ["growth"]),
    ("B · Inflation Force",                ["inflation"]),
    ("C · Monetary Policy & Rates",        ["policy"]),
    ("D · Credit, Debt & Fiscal",          ["credit", "fiscal"]),
    ("E · Risk Premiums",                  ["premium"]),
    ("F · External & Trade",               ["external"]),
    ("G · Capital Flows & Currency",       ["capital", "currency"]),
    ("H · Governance & Political Risk",    ["governance"]),
    ("I · Demographics & Structural",      ["demographics"]),
]

_LENS_ABOUT: dict[str, str] = {
    "Nominal Spending Master Indicators": (
        "Top-level view of nominal economic activity. GDP (real, nominal, deflator) and "
        "derived spreads that summarise the pace of money flowing through the economy. "
        "These are lagging — they confirm what already happened."
    ),
    "A · Growth Force": (
        "Real economic output and labour-market strength. Composite signals are importance-weighted "
        "Z-scores (Unemployment is inverted — lower = stronger growth). "
        "A positive score means the economy is running above its long-run average."
    ),
    "B · Inflation Force": (
        "Price pressures across consumers, producers, and financial markets. Core measures "
        "(CPI/HICP ex-food-energy, Wages) carry higher importance weights; volatile components "
        "(energy, food, headline) carry lower weight to reduce short-term noise."
    ),
    "C · Monetary Policy & Rates": (
        "The price and quantity of money set by the central bank. "
        "The policy rate and real yields reveal how tight or loose conditions are; "
        "the balance sheet reflects QE/QT."
    ),
    "D · Credit, Debt & Fiscal": (
        "Leverage, debt sustainability, and the government's fiscal position. "
        "High debt/GDP or a widening deficit increases fragility; "
        "tightening lending standards are a leading warning of credit stress."
    ),
    "E · Risk Premiums": (
        "The extra return investors demand for holding risky or longer-duration assets. "
        "The yield curve slope is a leading recession indicator; "
        "credit spreads reflect market-priced default risk."
    ),
    "F · External & Trade": (
        "How the economy relates to the rest of the world via trade and capital flows. "
        "The current account balance shows whether the economy is a net borrower or lender "
        "with the rest of the world."
    ),
    "G · Capital Flows & Currency": (
        "Cross-border investment and the value of the currency in real terms. "
        "FDI inflows signal long-term foreign confidence; the Real Effective Exchange Rate (REER) "
        "shows competitiveness vs. trading partners."
    ),
    "H · Governance & Political Risk": (
        "Institutional quality, rule of law, and political stability (World Bank WGI scores). "
        "These structural indicators move slowly but matter for long-run capital allocation. "
        "Deferred — WB API unavailable."
    ),
    "I · Demographics & Structural": (
        "Slow-moving forces that set the economy's long-run speed limit: population growth, "
        "urbanisation, labour force participation, and age dependency."
    ),
}


def _concept_label(signal_id: str) -> str:
    parts = signal_id.split(".")
    concept = parts[-1] if len(parts) >= 3 else signal_id
    return concept.replace("_", " ").title()


def _zscore_color(z: Any) -> str:
    if z is None or (isinstance(z, float) and _math.isnan(z)):
        return "#888"
    z = float(z)
    if z > 2:  return "#ff6666"
    if z > 1:  return "#ffaa66"
    if z < -2: return "#6699ff"
    if z < -1: return "#88bbff"
    return "#cccccc"


def _fmt_value(val: Any, units: str) -> str:
    if val is None or (isinstance(val, float) and _math.isnan(val)):
        return "—"
    if units in ("yoy_pct", "yoy_pct_spread"):
        return f"{val*100:+.2f}%"
    if units in (
        "pct_level", "pct_gdp", "pct_pot_gdp",
        "pct_working_age", "pct_pop_15plus", "pct_annual",
        "pct_total_pop", "net_pct",
    ):
        return f"{val:.2f}%"
    if units in ("diffusion_index", "index", "index_2020eq100", "index_2010eq100"):
        return f"{val:.1f}"
    if units == "ratio":
        return f"{val:.3f}"
    if units == "thousands":
        return f"{val/1000:.1f}M" if abs(val) >= 1000 else f"{val:.0f}k"
    if units == "millions_usd":
        if abs(val) >= 1_000_000:
            return f"${val/1_000_000:.2f}T"
        if abs(val) >= 1_000:
            return f"${val/1_000:.1f}B"
        return f"${val:.0f}M"
    return f"{val:.4g}"


def _pct_badge_html(pct: Any, low_history: bool = False) -> str:
    if pct is None or (isinstance(pct, float) and _math.isnan(pct)):
        return '<span style="background:#3a3a3a;color:#888;padding:2px 5px;border-radius:3px;font-size:0.75em;">—</span>'
    if low_history:
        bg, title = "#555", ' title="low-history"'
    elif pct > 0.85:
        bg, title = "#9b1c1c", ""
    elif pct > 0.70:
        bg, title = "#c05a00", ""
    elif pct < 0.15:
        bg, title = "#1a3a6e", ""
    elif pct < 0.30:
        bg, title = "#2155a0", ""
    else:
        bg, title = "#444", ""
    return (
        f'<span{title} style="background:{bg};color:#eee;padding:2px 5px;'
        f'border-radius:3px;font-size:0.75em;font-family:monospace;">'
        f"{pct:.0%}</span>"
    )


def _quality_badges_html(row: "pd.Series") -> str:
    parts: list[str] = []
    if row.get("is_proxy"):
        parts.append(
            '<span title="proxy" style="background:#5a5a5a;color:#ddd;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">proxy</span>'
        )
    if row.get("is_stale"):
        parts.append(
            '<span title="stale" style="background:#7a4a00;color:#ffcc80;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">stale</span>'
        )
    if not row.get("vintage_available", True):
        parts.append(
            '<span title="no point-in-time vintage" style="background:#383838;color:#aaa;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">no&nbsp;vintage</span>'
        )
    if row.get("low_history"):
        parts.append(
            '<span title="low history" style="background:#4a5a5a;color:#cdd;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">low&nbsp;hist</span>'
        )
    return "&nbsp;".join(parts)


def _sparkline_svg_str(values: list, width: int = 72, height: int = 18) -> str:
    vals = [v for v in values if v is not None and not (isinstance(v, float) and _math.isnan(v))]
    if len(vals) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1.0
    step = width / (len(vals) - 1)
    pts = [f"{i*step:.1f},{height - (v - mn)/rng*(height-4) - 2:.1f}" for i, v in enumerate(vals)]
    return (
        f'<svg width="{width}" height="{height}" style="vertical-align:middle;">'
        f'<path d="M{" L".join(pts)}" fill="none" stroke="#5590cc" stroke-width="1.5"/>'
        f"</svg>"
    )


def _build_lens_table(lens_signals: "pd.DataFrame", histories_by_id: dict) -> html.Div:
    """Build a lens signal table as Dash html components (no raw HTML strings)."""
    if lens_signals.empty:
        return html.Div("No data for this lens.", style={"color": "#666", "fontSize": "0.85em", "padding": "8px"})

    _ll_color = {
        "leading": "#aaffaa", "coincident": "#aaaaff",
        "lagging": "#ffaaaa", "structural": "#ddddaa",
    }

    def _pct_badge(pct: Any, low_history: bool) -> html.Span:
        if pct is None or (isinstance(pct, float) and _math.isnan(pct)):
            bg = "#3a3a3a"; txt = "—"
        elif low_history:
            bg = "#555"; txt = f"{pct:.0%}"
        elif pct > 0.85:
            bg = "#9b1c1c"; txt = f"{pct:.0%}"
        elif pct > 0.70:
            bg = "#c05a00"; txt = f"{pct:.0%}"
        elif pct < 0.15:
            bg = "#1a3a6e"; txt = f"{pct:.0%}"
        elif pct < 0.30:
            bg = "#2155a0"; txt = f"{pct:.0%}"
        else:
            bg = "#444"; txt = f"{pct:.0%}"
        return html.Span(txt, style={
            "background": bg, "color": "#eee", "padding": "2px 5px",
            "borderRadius": "3px", "fontSize": "0.75em", "fontFamily": "monospace",
        })

    def _quality_badges(row: Any) -> list:
        parts = []
        _bs = lambda txt, bg, fg="#ddd", title="": html.Span(txt, title=title, style={
            "background": bg, "color": fg, "padding": "1px 4px",
            "borderRadius": "3px", "fontSize": "0.7em", "marginRight": "3px",
        })
        if row.get("is_proxy"):
            parts.append(_bs("proxy", "#5a5a5a", title="proxy series"))
        if row.get("is_stale"):
            parts.append(_bs("stale", "#7a4a00", fg="#ffcc80", title="not updated within release window"))
        if not row.get("vintage_available", True):
            parts.append(_bs("no vintage", "#383838", fg="#aaa", title="latest-revised only"))
        if row.get("low_history"):
            parts.append(_bs("low hist", "#4a5a5a", fg="#cdd", title="<15 observations"))
        return parts

    header_row = html.Tr([
        html.Th("Indicator",                    style={"padding": "4px 8px", "color": "#666", "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333"}),
        html.Th("Value",   style={"padding": "4px 8px", "textAlign": "right", "color": "#666", "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333"}),
        html.Th("Dir",     style={"padding": "4px 8px", "textAlign": "center", "color": "#666", "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333"}),
        html.Th("Pct",     style={"padding": "4px 8px", "textAlign": "center", "color": "#666", "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333"}),
        html.Th("Z",       style={"padding": "4px 8px", "textAlign": "center", "color": "#666", "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333"}),
        html.Th("Quality", style={"padding": "4px 8px", "color": "#666", "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333"}),
    ])

    data_rows = []
    for _, row in lens_signals.iterrows():
        sid  = str(row["id"])
        label = _concept_label(sid)
        linkage = str(row.get("linkage") or "")
        val_str = _fmt_value(row.get("value"), str(row.get("units", "")))
        arrow   = _DIR_ARROW.get(str(row.get("direction") or "flat"), "→")
        pct     = row.get("level_percentile")
        z       = row.get("zscore")
        z_val   = f"{z:+.2f}" if z is not None and not (isinstance(z, float) and _math.isnan(z)) else "—"
        z_color = _zscore_color(z)
        ll      = str(row.get("lead_lag", ""))
        ll_col  = _ll_color.get(ll, "#888")
        source  = str(row.get("source", ""))

        data_rows.append(html.Tr([
            html.Td([
                html.Span(label, title=linkage,
                          style={"cursor": "help", "color": "#ddd", "fontWeight": "600"}),
                html.Span(f" {ll}", style={"fontSize": "0.7em", "color": ll_col}),
                html.Br(),
                html.Span(source, style={"fontSize": "0.7em", "color": "#555"}),
            ], style={"padding": "5px 8px"}),
            html.Td(val_str, style={"padding": "5px 8px", "textAlign": "right",
                                     "fontFamily": "monospace", "color": "#ccc"}),
            html.Td(arrow, style={"padding": "5px 8px", "textAlign": "center", "fontSize": "1.1em"}),
            html.Td(_pct_badge(pct, bool(row.get("low_history"))),
                    style={"padding": "5px 8px", "textAlign": "center"}),
            html.Td(z_val, style={"padding": "5px 8px", "textAlign": "center",
                                   "fontFamily": "monospace", "color": z_color}),
            html.Td(_quality_badges(row), style={"padding": "5px 8px"}),
        ], style={"borderBottom": "1px solid #1e1e2e"}))

    return html.Table(
        [html.Thead(header_row), html.Tbody(data_rows)],
        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.88em"},
    )


def _what_changed_children(change_df: "pd.DataFrame") -> list:
    if change_df.empty:
        return [html.Span("No data.", style={"color": "#888", "fontSize": "0.85em"})]
    items = []
    for _, row in change_df.head(8).iterrows():
        label = _concept_label(str(row["id"]))
        z_now = float(row.get("zscore") or 0.0)
        z_prev = float(row.get("prior_zscore") or z_now)
        delta = z_now - z_prev
        d_str = f"{delta:+.2f}" if not _math.isnan(delta) else "—"
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        color = "#ff8888" if delta > 0.3 else ("#88aaff" if delta < -0.3 else "#aaa")
        prior_date = str(row.get("prior_as_of", ""))[:7]
        items.append(html.Div([
            html.Span(str(row["force"]), style={"color": "#888"}),
            html.Span(" · "),
            html.B(label, style={"color": "#ddd"}),
            html.Span(f" {arrow} {d_str}", style={"color": color, "fontSize": "1.1em"}),
            html.Span(f"  Δ Z vs {prior_date}", style={"color": "#666", "fontSize": "0.78em"}),
        ], style={"padding": "4px 0", "borderBottom": "1px solid #222", "fontSize": "0.88em"}))
    return items


def _conflicts_children(latest_signals: "pd.DataFrame") -> list:
    conflicts: list[str] = []
    for force in ["growth", "inflation"]:
        force_sigs = latest_signals[latest_signals["force"] == force]
        leading    = force_sigs[force_sigs["lead_lag"] == "leading"]["direction"].dropna()
        lagging    = force_sigs[force_sigs["lead_lag"] == "lagging"]["direction"].dropna()
        coincident = force_sigs[force_sigs["lead_lag"] == "coincident"]["direction"].dropna()
        if leading.empty or (lagging.empty and coincident.empty):
            continue
        lead_rising = (leading == "rising").mean()
        lag_ref = pd.concat([lagging, coincident])
        lag_rising = (lag_ref == "rising").mean() if not lag_ref.empty else None
        if lag_rising is not None:
            gap = abs(lead_rising - lag_rising)
            if gap > 0.4:
                if lead_rising < 0.4 and lag_rising > 0.6:
                    conflicts.append(
                        f"**{force.title()}**: Leading turning down ({lead_rising:.0%}) "
                        f"while lagging/coincident firm ({lag_rising:.0%})"
                    )
                elif lead_rising > 0.6 and lag_rising < 0.4:
                    conflicts.append(
                        f"**{force.title()}**: Leading strengthening ({lead_rising:.0%}) "
                        f"while lagging/coincident soft ({lag_rising:.0%})"
                    )
    pmi = latest_signals[latest_signals["id"].str.endswith("pmi_proxy")]
    pay = latest_signals[latest_signals["id"].str.endswith("payrolls")]
    if not pmi.empty and not pay.empty:
        pmi_d = pmi.iloc[0].get("direction")
        pay_d = pay.iloc[0].get("direction")
        if pmi_d and pay_d and pmi_d != pay_d:
            conflicts.append(
                f"**Leading vs Coincident**: PMI proxy {pmi_d} while Payrolls {pay_d}"
            )
    if conflicts:
        return [dcc.Markdown(c, style={"fontSize": "0.88em", "marginBottom": "4px"}) for c in conflicts]
    return [html.Span("No significant conflicts detected.",
                      style={"color": "#888", "fontSize": "0.88em"})]


# ── Series catalog ────────────────────────────────────────────────────────────

_CATALOG = load_series_catalog()

# Group → list of catalog entries
_GROUPS: dict[str, list[dict]] = defaultdict(list)
for _entry in _CATALOG:
    _GROUPS[_entry["group"]].append(_entry)

# signal_id → entry lookup
_BY_ID: dict[str, dict] = {e["signal_id"]: e for e in _CATALOG}

# ── Layout ────────────────────────────────────────────────────────────────────

def _series_selector() -> dbc.Card:
    """Build the left-sidebar shell; content is populated by update_series_selector callback."""
    return dbc.Card(
        dbc.CardBody([
            html.H6("Series", className="mb-0"),
            html.Hr(className="my-2"),
            html.Div(id="series-selector-body", children=[], style={"overflowY": "auto", "maxHeight": "78vh"}),
            html.Hr(className="my-2"),
            dbc.Button("Clear all", id="btn-clear-all", color="secondary", size="sm", className="w-100 mb-1"),
        ]),
        className="h-100",
        style={"minWidth": "220px", "maxWidth": "240px"},
    )


def _build_series_groups_us() -> list:
    """Static US series groups from the chart_series.yaml catalog."""
    groups = []
    for group_name, entries in _GROUPS.items():
        options = [
            {"label": e["label"], "value": e["signal_id"], "title": e.get("description", "")}
            for e in entries
        ]
        groups.append(html.Div([
            html.P(group_name, className="text-muted small mb-1 mt-2 fw-semibold"),
            dcc.Checklist(
                id={"type": "group-checklist", "group": group_name},
                options=options,
                value=[],
                inputStyle={"marginRight": "6px"},
                labelStyle={"display": "block", "fontSize": "0.82rem", "marginBottom": "3px"},
            ),
        ]))
    return groups


def _time_controls() -> html.Div:
    """Preset buttons + range slider row."""
    presets = ["1Y", "3Y", "5Y", "10Y", "MAX"]
    return html.Div([
        dbc.ButtonGroup(
            [dbc.Button(p, id=f"btn-{p}", color="secondary", size="sm", outline=True) for p in presets],
            className="me-3",
        ),
        html.Span("or drag the range slider below", className="text-muted small align-middle"),
    ], className="d-flex align-items-center mb-2")


def _theme_picker() -> dbc.RadioItems:
    return dbc.RadioItems(
        id="theme-picker",
        options=[{"label": t["name"], "value": k} for k, t in THEMES.items()],
        value=DEFAULT_THEME,
        inline=True,
        className="small py-2",
        inputStyle={"marginRight": "4px"},
        labelStyle={"marginRight": "12px", "fontSize": "0.82rem"},
    )


# Upcoming data release schedule — update when new releases are known.
_UPCOMING_RELEASES: list[tuple[datetime.date, str]] = [
    (datetime.date(2026, 6, 26), "BEA Q1 2026 current account / NIIP"),
    (datetime.date(2026, 7, 3),  "BLS June jobs report"),
    (datetime.date(2026, 7, 30), "BEA Q2 2026 GDP advance"),
    (datetime.date(2026, 8, 5),  "BLS July jobs report"),
]


def _sync_banner() -> html.Div | None:
    """Sync-status banner.
    Expanded: full text for both overdue and upcoming.
    Collapsed: ⚠ icon only for overdue; upcoming hidden entirely.
    """
    today = datetime.date.today()
    overdue = [(d, lbl) for d, lbl in _UPCOMING_RELEASES if d <= today]
    future  = [(d, lbl) for d, lbl in _UPCOMING_RELEASES if d > today]

    if overdue:
        _, lbl = overdue[0]
        return html.Div([
            html.Span("⚠", style={
                "color": "#F4C842", "fontWeight": "700", "fontSize": "0.9rem",
                "minWidth": "22px", "display": "inline-block", "textAlign": "center",
            }),
            html.Span(f" Update now · {lbl}", className="sidebar-text", style={
                "fontSize": "0.72rem", "color": "#F4C842", "fontWeight": "600",
            }),
        ], style={"padding": "4px 12px 6px 12px", "lineHeight": "1.3",
                  "display": "flex", "alignItems": "center"})
    if future:
        next_date, lbl = future[0]
        days_left = (next_date - today).days
        # Whole banner hidden when collapsed — no icon needed for a future event
        return html.Div(
            f"Next sync: {next_date.strftime('%b %d')} · {lbl} ({days_left}d)",
            className="sidebar-text",
            style={"fontSize": "0.70rem", "color": "#666",
                   "padding": "4px 12px 6px 12px", "lineHeight": "1.3"},
        )
    return None


# ── Per-page layout functions ─────────────────────────────────────────────────

def _left_nav() -> html.Div:
    """Collapsible vertical nav sidebar."""
    _sync = _sync_banner()

    def _label(txt: str) -> html.Div:
        return html.Div(txt, className="sidebar-section-label", style={
            "fontSize": "0.62rem", "textTransform": "uppercase", "letterSpacing": "0.1em",
            "color": "var(--muted-color)", "fontWeight": "700",
            "padding": "14px 12px 4px 12px",
        })

    _tooltips: list = []

    def _nl(icon: str, text: str, href: str, disabled: bool = False,
            nav_id: str | None = None) -> dbc.NavLink:
        link = dbc.NavLink(
            [
                html.Span(icon, className="nav-icon",
                          style={"minWidth": "22px", "display": "inline-block",
                                 "textAlign": "center"}),
                html.Span(f" {text}", className="sidebar-text"),
            ],
            href=href if not disabled else None,
            active="exact" if not disabled else False,
            disabled=disabled,
            id=nav_id,
            className="py-1 px-3 small sidebar-nav-link",
        )
        if nav_id:
            _tooltips.append(dbc.Tooltip(
                text, target=nav_id, placement="right",
                delay={"show": 300, "hide": 50},
            ))
        return link

    def _sm(v: int, lbl: str) -> dict:
        return {"label": lbl, "style": {"color": "var(--font-color)", "fontSize": "0.62rem"}}

    _country_options = [
        {"label": "🇺🇸 United States",          "value": "US"},
        {"label": "🇪🇺 Eurozone",               "value": "EZ"},
        {"label": "🇰🇷 South Korea",            "value": "KR"},
        {"label": "🇯🇵 Japan  (soon)",            "value": "JP", "disabled": True},
        {"label": "🇬🇧 United Kingdom  (soon)",   "value": "GB", "disabled": True},
    ]

    return html.Div([
        # ── Header: title + collapse toggle ──────────────────────────────────
        html.Div([
            html.Span("Indicators Machine", className="sidebar-text", style={
                "fontSize": "0.85rem", "fontWeight": "700",
                "color": "var(--font-color)", "flexGrow": "1",
            }),
            html.Button("‹", id="sidebar-toggle-btn", n_clicks=0, style={
                "background": "none", "border": "none", "cursor": "pointer",
                "color": "var(--muted-color)", "fontSize": "1.1rem",
                "padding": "0 4px", "lineHeight": "1", "flexShrink": "0",
            }),
        ], className="sidebar-header",
           style={"display": "flex", "alignItems": "center",
                  "padding": "14px 8px 6px 12px"}),

        # ── Country selector ──────────────────────────────────────────────────
        dbc.Select(
            id="country-selector",
            options=_country_options,
            value="US",
            size="sm",
            className="country-full",
            style={"fontSize": "0.78rem", "margin": "0 12px 10px 12px",
                   "width": "calc(100% - 24px)", "backgroundColor": "var(--card-bg)",
                   "color": "var(--font-color)", "borderColor": "var(--border-color)"},
        ),
        html.Div(id="country-flag-display", className="country-collapsed",
                 children="🇺🇸", title="United States",
                 style={"fontSize": "1.3rem", "textAlign": "center",
                        "padding": "4px 0 8px 0", "cursor": "default"}),

        html.Div(style={"borderBottom": "1px solid var(--border-color)",
                        "marginBottom": "2px"}),

        # ── Overviews (placeholder — Phase 2+) ───────────────────────────────
        _label("Overviews"),
        dbc.Nav([
            _nl("🌐", "Overview", "/overview", nav_id="navlnk-overview"),
        ], vertical=True, pills=True, className="mb-1"),

        # ── Indicators ────────────────────────────────────────────────────────
        _label("Indicators"),
        dbc.Nav([
            _nl("〰", "Yield Curve",    "/yield-curve",    nav_id="navlnk-yield-curve"),
            _nl("📍", "Regime Map",     "/regime-map",     nav_id="navlnk-regime-map"),
            _nl("📈", "Regime History", "/regime-history", nav_id="navlnk-regime-history"),
            _nl("⚖️", "Debt Stress",    "/debt-stress",    nav_id="navlnk-debt-stress"),
        ], vertical=True, pills=True, className="mb-1"),

        # ── Data ──────────────────────────────────────────────────────────────
        _label("Data"),
        dbc.Nav([
            _nl("📋", "Data Dashboard", "/data-dashboard", nav_id="navlnk-data-dashboard"),
            _nl("📊", "Chart Overlay",  "/charts",         nav_id="navlnk-charts"),
            _nl("🔬", "Data Explorer",  "/explorer",       nav_id="navlnk-explorer"),
        ], vertical=True, pills=True, className="mb-1"),

        # ── Reference ─────────────────────────────────────────────────────────
        _label("Reference"),
        dbc.Nav([
            _nl("📖", "Methodology",  "/methodology",  nav_id="navlnk-methodology"),
            _nl("🔍", "Weight Audit", "/weight-audit", nav_id="navlnk-weight-audit"),
        ], vertical=True, pills=True, className="mb-2"),

        html.Hr(style={"borderColor": "var(--border-color)", "margin": "6px 12px"}),

        # ── Window sliders (hidden when sidebar collapsed) ────────────────────
        html.Div([
            html.Div("Z-Score Window", className="sidebar-text", style={
                "fontSize": "0.62rem", "textTransform": "uppercase",
                "letterSpacing": "0.08em", "color": "var(--muted-color)",
                "fontWeight": "700", "padding": "0 4px 4px 4px",
            }),
            dcc.Slider(
                id="zscore-window-slider",
                min=0, max=60, step=None,
                marks={0: _sm(0,"Full"), 36: _sm(36,"36m"), 48: _sm(48,"48m"), 60: _sm(60,"60m")},
                value=0,
                tooltip={"always_visible": False, "style": {"display": "none"}},
                className="sidebar-slider",
            ),
            html.Div("Disequilibrium Window", className="sidebar-text", style={
                "fontSize": "0.62rem", "textTransform": "uppercase",
                "letterSpacing": "0.08em", "color": "var(--muted-color)",
                "fontWeight": "700", "padding": "10px 4px 4px 4px",
            }),
            dcc.Slider(
                id="diseq-window-slider",
                min=0, max=24, step=None,
                marks={0: _sm(0,"Full"), 12: _sm(12,"12m"), 18: _sm(18,"18m"), 24: _sm(24,"24m")},
                value=0,
                tooltip={"always_visible": False, "style": {"display": "none"}},
                className="sidebar-slider",
            ),
        ], className="sidebar-sliders", style={"padding": "0 8px 8px 8px"}),

        html.Hr(style={"borderColor": "var(--border-color)", "margin": "6px 12px"}),
        *([_sync] if _sync else []),

        # ── Settings ──────────────────────────────────────────────────────────
        html.Div(
            dbc.Button(
                [html.Span("⚙️", className="nav-icon",
                           style={"minWidth": "22px", "display": "inline-block",
                                  "textAlign": "center", "fontSize": "1.1em"}),
                 html.Span(" Settings", className="sidebar-text")],
                id="settings-btn",
                color="link",
                size="sm",
                className="sidebar-nav-link",
                style={"color": "var(--muted-color)", "fontSize": "0.875rem",
                       "padding": "4px 12px", "width": "100%", "textAlign": "left",
                       "display": "flex", "alignItems": "center"},
            ),
            style={"marginTop": "auto"},
        ),

        # ── Hover tooltips (shown on collapsed icon hover) ────────────────────
        dbc.Tooltip("Settings", target="settings-btn", placement="right",
                    delay={"show": 300, "hide": 50}),
        *_tooltips,
    ], id="sidebar-container", style={
        "width": "195px",
        "flexShrink": "0",
        "height": "100vh",
        "position": "sticky",
        "top": "0",
        "overflowY": "auto",
        "overflowX": "hidden",
        "backgroundColor": "var(--card-bg)",
        "borderRight": "1px solid var(--border-color)",
    })


def _page_chart_overlay() -> html.Div:
    presets = ["1Y", "3Y", "5Y", "10Y", "MAX"]
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.ButtonGroup(
                    [dbc.Button(p, id=f"btn-{p}", color="secondary", size="sm", outline=True)
                     for p in presets],
                    className="me-3",
                ),
                html.Span("or drag the range slider", className="text-muted small align-middle"),
            ], className="d-flex align-items-center mb-1 pt-2 pe-0", width=True),
        ]),
        dbc.Row([
            dbc.Col(
                dcc.RangeSlider(
                    id="range-slider", min=0, max=1, step=0.001, value=[0, 1], marks=None,
                    tooltip={"placement": "bottom", "always_visible": False},
                    className="mb-1",
                ),
            ),
        ]),
        dbc.Row([
            dbc.Col(
                dcc.Graph(
                    id="overlay-chart",
                    config={"displayModeBar": True, "scrollZoom": True},
                    style={"height": "76vh"},
                ),
            ),
            dbc.Col(_series_selector(), width="auto", className="ps-0"),
        ]),
    ], className="pe-2 pt-1", style={"maxWidth": "1600px", "margin": "0 auto"})


def _page_explorer() -> html.Div:
    return html.Div(_explorer.get_layout(), className="pe-2 pt-2", style={"maxWidth": "1600px", "margin": "0 auto"})


def _page_overview() -> html.Div:
    return _global_overview.get_layout()


def _page_data_dashboard() -> html.Div:
    return _data_dashboard.get_layout()


def _page_methodology() -> html.Div:
    return _methodology.get_layout()


def _page_weight_audit() -> html.Div:
    return _weight_audit.get_layout()


def _page_yield_curve() -> html.Div:
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Label("Date", className="small text-muted mb-1"),
                dcc.Dropdown(id="yc-date-picker", options=[], placeholder="Select a date…",
                             clearable=False, style={"color": "#000"}),
            ], width=3),
            dbc.Col([
                html.Label("Compare date (optional)", className="small text-muted mb-1"),
                dcc.Dropdown(id="yc-date-compare", options=[], placeholder="None",
                             clearable=True, style={"color": "#000"}),
            ], width=3),
        ], className="mb-3 pt-2"),
        dcc.Graph(id="yield-curve-chart", config={"displayModeBar": True}, style={"height": "72vh"}),
    ], className="pe-2", style={"maxWidth": "1600px", "margin": "0 auto"})


def _page_regime_map() -> html.Div:
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.ButtonGroup([
                    dbc.Button("← Prev", id={"type": "regime-step-button", "action": "prev"},
                               color="secondary", size="sm", outline=True, title="Previous data point"),
                    dbc.Button("◉ Now", id={"type": "regime-step-button", "action": "current"},
                               color="primary", size="sm", outline=True, title="Return to latest data point"),
                    dbc.Button("Next →", id={"type": "regime-step-button", "action": "next"},
                               color="secondary", size="sm", outline=True, title="Next data point"),
                ], className="me-3"),
                html.Span(id="scatter-date-display", className="text-muted small align-middle"),
            ], className="d-flex align-items-center pt-2 pb-1"),
        ]),
        dcc.Graph(id="scatter-chart",
                  responsive=True,
                  config={"displayModeBar": True, "scrollZoom": True},
                  style={"height": "55vh", "minHeight": "420px"}),
        html.Hr(style={"borderColor": "var(--border-color)", "margin": "10px 0"}),
        # ── Below-map panels ─────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                html.Div("What Changed", style={"fontWeight": "700", "fontSize": "0.9rem", "marginBottom": "6px"}),
                html.Div(id="what-changed"),
            ], width=4),
            dbc.Col([
                html.Div("Cross-Signal Conflicts", style={"fontWeight": "700", "fontSize": "0.9rem", "marginBottom": "6px"}),
                html.Div(id="conflicts-panel"),
            ], width=4),
            dbc.Col([
                html.Div("Geopolitical-Risk Overlay", style={"fontWeight": "700", "fontSize": "0.9rem", "marginBottom": "6px"}),
                html.Div(
                    "WGI governance scores deferred (WB v2 API unavailable). See session-checklist G-03 for resolution path.",
                    style={"color": "#666", "fontSize": "0.85em"},
                ),
            ], width=4),
        ], className="py-2"),
        html.Hr(style={"borderColor": "var(--border-color)", "margin": "10px 0"}),
        # ── Signal Drill-Downs ────────────────────────────────────────────────
        html.Div("Signal Drill-Downs", style={"fontWeight": "700", "fontSize": "0.95rem", "marginBottom": "4px"}),
        html.Div(
            "Percentile badge: 85%+ elevated · 15%− depressed · Hover indicator name for causal linkage.",
            style={"color": "#666", "fontSize": "0.78em", "marginBottom": "10px"},
        ),
        html.Div(id="lens-drilldowns"),
        html.Hr(style={"borderColor": "var(--border-color)", "margin": "10px 0"}),
        dbc.Accordion([
            dbc.AccordionItem(
                html.Div(id="data-quality-log"),
                title="Data-Quality Log",
                item_id="dql",
            ),
        ], start_collapsed=True, className="mb-3"),
    ], className="pe-2", style={"maxWidth": "1600px", "margin": "0 auto"})


_RH_HELP_PANEL_BASE_STYLE: dict = {
    "position": "fixed", "right": "0", "top": "0",
    "height": "100vh", "width": "310px", "overflowY": "auto",
    "zIndex": "500",
    "backgroundColor": "var(--card-bg)",
    "borderLeft": "1px solid var(--border-color)",
    "padding": "16px 16px 32px 16px",
    "transition": "transform 0.25s ease",
    "boxShadow": "-4px 0 20px rgba(0,0,0,0.4)",
}


def _build_rh_help_panel() -> html.Div:
    """Fixed right-side collapsible field guide for the Regime History page."""
    _H = {
        "fontSize": "0.6rem", "textTransform": "uppercase",
        "letterSpacing": "0.08em", "fontWeight": "700",
        "color": "var(--accent-color)", "marginBottom": "7px",
        "marginTop": "16px", "paddingBottom": "4px",
        "borderBottom": "1px solid var(--border-color)",
    }
    _TERM = {"fontWeight": "600", "fontSize": "0.78rem", "color": "var(--font-color)"}
    _DEF  = {"fontSize": "0.76rem", "color": "var(--muted-color)", "marginBottom": "6px", "marginTop": "1px"}

    def _row(term, defn):
        if term:
            return [html.Div(term, style=_TERM), html.Div(defn, style=_DEF)]
        return [html.Div(defn, style={**_DEF, "marginTop": "0"})]

    children = [
        html.Div([
            html.Span("Field Guide", style={"fontWeight": "700", "fontSize": "0.9rem"}),
            dbc.Button("×", id="rh-help-close", color="link", size="sm", n_clicks=0,
                       style={"padding": "0 2px", "fontSize": "1.3rem",
                              "lineHeight": "1", "opacity": "0.6"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "marginBottom": "2px"}),
        html.P("Regime History — all metrics explained.",
               style={"fontSize": "0.74rem", "color": "var(--muted-color)", "marginBottom": "0"}),

        html.Div("Regime Quadrant", style=_H),
        *_row(None, "The macro season, determined by the sign of both force Z-scores."),
        *_row("Expansion", "Growth ↑, Inflation ↓ — output recovering faster than prices."),
        *_row("Inflationary Boom", "Growth ↑, Inflation ↑ — both above long-run normal."),
        *_row("Stagflation", "Growth ↓, Inflation ↑ — weak output with elevated prices."),
        *_row("Disinflationary Slowdown", "Growth ↓, Inflation ↓ — both below normal."),

        html.Div("Force Z-Scores", style=_H),
        *_row("Growth  (blue)", ("Dynamically weighted composite of 9 growth signals, each standardised "
                                  "vs. its own history. Positive = above long-run average; negative = below.")),
        *_row("Inflation  (orange)", ("Same for 8 inflation signals. "
                                      "Positive = inflationary pressure above baseline.")),
        *_row(None, ("The zero reference line is the historical mean. "
                     "Magnitude shows how far conditions have deviated from 'normal'.")),

        html.Div("Dynamic Weighting", style=_H),
        *_row("Config Weight", ("Normalized base share × editable importance × data-quality factor. "
                                 "Importance defaults live in config/composites.yaml.")),
        *_row("Momentum Tilt", ("Force and momentum agreement boosts weight up to 1.5×; "
                                  "conflict reduces it to 0.5×; neutral leaves it unchanged.")),
        *_row("Time Decay", ("Observation weight halves every 3 months after its last data point. "
                               "Per-frequency carry caps still remove data that is too old.")),
        *_row("Effective Weight", "Config weight × momentum tilt × time-decay fraction."),

        html.Div("Momentum  Δ MoM  (info box)", style=_H),
        *_row(None, ("Month-over-month change in the force score: "
                     "this month's composite Z-score minus last month's. "
                     "↑ = score rose · ↓ = score fell · → = flat (|Δ| < 0.001).")),
        *_row(None, "Distinct from the signal fraction in chart rows 2 & 4 — see 'Chart Rows' below."),

        html.Div("Confidence", style=_H),
        *_row(None, ("Fraction of constituent signals whose 3-month direction "
                     "agrees with the assigned quadrant label.")),
        *_row(None, ("In Stagflation we expect growth signals falling AND inflation signals rising. "
                     "80% = 80% of all signals are moving in the expected direction.")),
        *_row(None, "Below 50% = mixed signals; low conviction in the quadrant label."),

        html.Div("Disequilibrium", style=_H),
        *_row(None, ("Mean absolute Z-score across five structural force groups: "
                     "Debt, External/Trade, Technology, Governance, Climate.")),
        *_row(None, ("Unlike the cyclical quadrant, Disequilibrium captures slow-moving "
                     "structural imbalances that build over years.")),
        *_row("0 – 0.5", "Low structural tension."),
        *_row("0.5 – 1.5", "Moderate tension."),
        *_row("> 1.5", "High — system stretched far from long-run equilibrium."),

        html.Div("Chart Rows", style=_H),
        *_row("Row 1 · Growth Force Z-Score",
              "Level of the growth composite over time. Fill shows magnitude above/below zero."),
        *_row("Row 2 · Growth Momentum  (signal fraction)",
              ("Fraction of the 9 growth signals whose 3-month direction is growth-positive. "
               "50% = neutral split. 70% = 7 of 9 signals trending growth-positive, "
               "independent of the absolute level. Note: 7/9 signals can be growth-positive "
               "even when the Z-score is negative if the score is rising from a low base.")),
        *_row("Row 3 · Inflation Force Z-Score",
              "Level of the inflation composite over time."),
        *_row("Row 4 · Inflation Momentum  (signal fraction)",
              "Fraction of the 8 inflation signals trending inflation-positive. 50% = neutral."),
        *_row("Row 5 · Regime Quadrant",
              ("Discrete step-function: 0 = Dis. Slowdown · 1 = Expansion "
               "· 2 = Inf. Boom · 3 = Stagflation.")),

        html.Div("Force Component Table", style=_H),
        *_row("Signal", "Constituent indicator name."),
        *_row("Importance", "Editable relevance judgement from 0 to 1; defaults come from the weighting guidance."),
        *_row("Config Wt", "Normalized nominal weight after base share, importance, and data quality."),
        *_row("Eff Wt", "Point-in-time weight after momentum agreement and age decay."),
        *_row("Last Data", "Date of the most-recent observation as of the selected date."),
        *_row("Force Z", "Signal-level Z-score at the selected date. Positive = above historical mean."),
        *_row("Momentum", "3-month change direction for this individual signal: ↑ ↓ →"),
        *_row("Status", ("ACTIVE = included in composite · "
                         "STALE = overdue per release schedule, excluded · "
                         "LOW HISTORY = < 15 obs, Z-score unreliable, excluded · "
                         "MISSING = no data at this date, excluded.")),
    ]

    return html.Div(
        id="rh-help-panel",
        style={**_RH_HELP_PANEL_BASE_STYLE, "transform": "translateX(100%)"},
        children=children,
    )


def _page_regime_history() -> html.Div:
    return html.Div([
        dcc.Store(id="rh-help-open", data=False),
        # ── Sticky header: controls + summary metrics box ─────────────────────
        html.Div([
            dbc.Row([
                dbc.Col([
                    dbc.ButtonGroup([
                        dbc.Button("← Prev", id={"type": "regime-step-button", "action": "prev"},
                                   color="secondary", size="sm", outline=True, title="Previous data point"),
                        dbc.Button("◉ Now", id={"type": "regime-step-button", "action": "current"},
                                   color="primary", size="sm", outline=True, title="Return to latest data point"),
                        dbc.Button("Next →", id={"type": "regime-step-button", "action": "next"},
                                   color="secondary", size="sm", outline=True, title="Next data point"),
                    ], className="me-3"),
                    html.Span(id="regime-date-display", className="text-muted small align-middle"),
                ], className="d-flex align-items-center pt-2 pb-1"),
                dbc.Col([
                    dbc.Button("ℹ", id="rh-help-toggle", color="link", size="sm", n_clicks=0,
                               title="Field Guide",
                               style={"fontSize": "1.0rem", "padding": "2px 8px", "opacity": "0.7"}),
                ], width="auto", className="d-flex align-items-center pt-2 pb-1 ms-auto"),
            ]),
            dbc.Row([
                dbc.Col(
                    dbc.Card(dbc.CardBody(html.Div(id="regime-info-box"), style={"padding": "14px 16px"})),
                    width=12,
                ),
            ], className="pb-1"),
        ], style={
            "position": "sticky", "top": "0", "zIndex": "200",
            "backgroundColor": "var(--page-bg)", "paddingBottom": "4px",
        }),
        # ── Chart (scrolls under sticky header) ───────────────────────────────
        dbc.Row([
            dbc.Col(
                dcc.Graph(id="regime-chart",
                          responsive=True,
                          config={"displayModeBar": True},
                          style={"height": "calc(100vh - 175px)", "minHeight": "700px"}),
                width=12,
            ),
        ]),
        # ── Help panel (fixed, off-screen right by default) ────────────────────
        _build_rh_help_panel(),
    ], className="pe-2", style={"maxWidth": "1600px", "margin": "0 auto"})


def _page_debt_stress() -> html.Div:
    return html.Div([
        dbc.Row([
            dbc.Col(
                dbc.Card(dbc.CardBody(html.Div(id="debt-stress-info-box"), style={"padding": "16px"})),
                width=12,
            ),
        ], className="pt-2 pb-2"),
        dbc.Row([
            dbc.Col(
                dcc.Graph(id="debt-stress-chart",
                          responsive=True,
                          config={"displayModeBar": True},
                          style={"height": "calc(100vh - 200px)", "minHeight": "500px"}),
                width=12,
            ),
        ]),
    ], className="pe-2", style={"maxWidth": "1600px", "margin": "0 auto"})


# ── App layout ────────────────────────────────────────────────────────────────

def _modal_mark(lbl: str) -> dict:
    return {"label": lbl, "style": {"color": "var(--font-color)", "fontSize": "0.78rem"}}


_SETTINGS_MODAL = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Settings", style={"fontSize": "1rem"})),
    dbc.ModalBody([
        # ── Theme ─────────────────────────────────────────────────────────────
        html.Label("Theme", style={"fontWeight": "700", "fontSize": "0.88rem"}),
        html.Div(_theme_picker(), style={"marginTop": "6px", "marginBottom": "4px"}),

        html.Hr(style={"borderColor": "var(--border-color)"}),

        # ── Force Z-Score window ──────────────────────────────────────────────
        html.Label("Force Z-Score Look-back Window",
                   style={"fontWeight": "700", "fontSize": "0.88rem"}),
        html.P(
            "Controls how much history is used to define 'normal' for each force indicator. "
            "Full History anchors to the entire available record (default). "
            "Rolling windows make regime scores more responsive to structural shifts — "
            "guidance recommends 36–60 months.",
            style={"fontSize": "0.78rem", "color": "var(--muted-color)",
                   "marginTop": "6px", "marginBottom": "16px"},
        ),
        html.Div(
            dcc.Slider(
                id="zscore-window-modal-slider",
                min=0, max=60, step=None,
                marks={0: _modal_mark("Full · default"), 36: _modal_mark("36m"),
                       48: _modal_mark("48m ★"), 60: _modal_mark("60m")},
                value=0,
                tooltip={"always_visible": False, "style": {"display": "none"}},
                className="sidebar-slider",
            ),
            style={"paddingBottom": "28px"},
        ),

        html.Hr(style={"borderColor": "var(--border-color)"}),

        # ── Disequilibrium window ─────────────────────────────────────────────
        html.Label("Disequilibrium Look-back Window",
                   style={"fontWeight": "700", "fontSize": "0.88rem", "marginTop": "4px"}),
        html.P(
            "Disequilibrium measures how far structural forces are from equilibrium. "
            "A longer window smooths short-term noise; guidance recommends 12–24 months. "
            "Confidence is short-window by design (3-month direction flags; no setting needed).",
            style={"fontSize": "0.78rem", "color": "var(--muted-color)",
                   "marginTop": "6px", "marginBottom": "16px"},
        ),
        html.Div(
            dcc.Slider(
                id="diseq-window-modal-slider",
                min=0, max=24, step=None,
                marks={0: _modal_mark("Full · default"), 12: _modal_mark("12m"),
                       18: _modal_mark("18m ★"), 24: _modal_mark("24m")},
                value=0,
                tooltip={"always_visible": False, "style": {"display": "none"}},
                className="sidebar-slider",
            ),
            style={"paddingBottom": "28px"},
        ),

        html.Hr(style={"borderColor": "var(--border-color)"}),
        html.P(
            "When a rolling window is active, regime panels read pre-computed DB columns — "
            "no additional computation at render time.  Re-run the pipeline to refresh.",
            style={"fontSize": "0.73rem", "color": "var(--muted-color)"},
        ),
    ]),
    dbc.ModalFooter(
        dbc.Button("Close", id="settings-close-btn", color="secondary",
                   size="sm", n_clicks=0, className="ms-auto"),
    ),
], id="settings-modal", is_open=False, size="md")


app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    # Top-level stores — persist across page navigations
    dcc.Store(id="selected-series",      data=[]),
    dcc.Store(id="date-range",           data={"start": None, "end": None}),
    dcc.Store(id="theme-store",          data=DEFAULT_THEME),
    dcc.Store(id="regime-step-index",    data=0),
    # Fired by routing callback so page callbacks wait until components exist in DOM
    dcc.Store(id="page-trigger",         data={"page": "/charts"}),
    # Keyboard navigation: interval polls the delta set by the key listener
    dcc.Store(id="nav-event",            data=None),
    dcc.Interval(id="key-interval",      interval=80, disabled=True, n_intervals=0),
    dcc.Store(id="hover-sync-init",      data=None),
    dcc.Store(id="regime-components-open",          data=False),
    dcc.Store(id="regime-components-toggle-init",   data=None),
    # Settings: force Z-score rolling window (0 = full history)
    dcc.Store(id="zscore-window-store",  data=0, storage_type="local"),
    # Settings: disequilibrium rolling window (0 = full history)
    dcc.Store(id="diseq-window-store",   data=0, storage_type="local"),
    # Active country (Phase 2 multi-country support)
    dcc.Store(id="country-store",        data="US", storage_type="local"),
    # Sidebar collapsed state — persisted in localStorage
    dcc.Store(id="sidebar-collapsed",    data=False, storage_type="local"),
    html.Div(id="theme-dummy",           style={"display": "none"}),

    _SETTINGS_MODAL,

    html.Div([
        _left_nav(),
        html.Div(id="page-content", style={"flex": "1", "minWidth": "0", "padding": "0 12px"}),
    ], style={"display": "flex", "alignItems": "flex-start", "minHeight": "100vh"}),
], style={"backgroundColor": "var(--page-bg)"})

# ── Theme callbacks ───────────────────────────────────────────────────────────

@callback(
    Output("theme-store", "data"),
    Input("theme-picker", "value"),
)
def update_theme_store(theme_name: str) -> str:
    return theme_name or DEFAULT_THEME


# ── Settings modal callbacks ──────────────────────────────────────────────────

@callback(
    Output("settings-modal", "is_open"),
    [Input("settings-btn",       "n_clicks"),
     Input("settings-close-btn", "n_clicks")],
    State("settings-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_settings_modal(n_open: int, n_close: int, is_open: bool) -> bool:
    return not is_open


@callback(
    Output("zscore-window-store", "data"),
    Input("zscore-window-slider",       "value"),
    Input("zscore-window-modal-slider", "value"),
    prevent_initial_call=True,
)
def update_zscore_window(sidebar_val: int, modal_val: int) -> int:
    from dash import ctx
    if ctx.triggered_id == "zscore-window-slider":
        return int(sidebar_val) if sidebar_val is not None else 0
    return int(modal_val) if modal_val is not None else 0


@callback(
    Output("diseq-window-store", "data"),
    Input("diseq-window-slider",       "value"),
    Input("diseq-window-modal-slider", "value"),
    prevent_initial_call=True,
)
def update_diseq_window(sidebar_val: int, modal_val: int) -> int:
    from dash import ctx
    if ctx.triggered_id == "diseq-window-slider":
        return int(sidebar_val) if sidebar_val is not None else 0
    return int(modal_val) if modal_val is not None else 0


@callback(
    Output("zscore-window-slider", "value"),
    Input("zscore-window-store", "data"),
    prevent_initial_call=False,
)
def sync_zscore_slider(stored: int) -> int:
    return int(stored) if stored is not None else 0


@callback(
    Output("diseq-window-slider", "value"),
    Input("diseq-window-store", "data"),
    prevent_initial_call=False,
)
def sync_diseq_slider(stored: int) -> int:
    return int(stored) if stored is not None else 0


@callback(
    Output("zscore-window-modal-slider", "value"),
    Input("zscore-window-store", "data"),
    prevent_initial_call=False,
)
def sync_zscore_modal_slider(stored: int) -> int:
    return int(stored) if stored is not None else 0


@callback(
    Output("diseq-window-modal-slider", "value"),
    Input("diseq-window-store", "data"),
    prevent_initial_call=False,
)
def sync_diseq_modal_slider(stored: int) -> int:
    return int(stored) if stored is not None else 0


@callback(
    Output("sidebar-collapsed", "data"),
    Input("sidebar-toggle-btn", "n_clicks"),
    State("sidebar-collapsed", "data"),
    prevent_initial_call=True,
)
def toggle_sidebar(n_clicks: int, is_collapsed: bool) -> bool:
    return not bool(is_collapsed)


@callback(
    Output("sidebar-container", "className"),
    Input("sidebar-collapsed", "data"),
    prevent_initial_call=False,
)
def update_sidebar_class(collapsed: bool) -> str:
    return "sidebar-collapsed" if bool(collapsed) else ""


@callback(
    Output("sidebar-toggle-btn", "children"),
    Input("sidebar-collapsed", "data"),
    prevent_initial_call=False,
)
def update_toggle_icon(collapsed: bool) -> str:
    return "›" if bool(collapsed) else "‹"


_COUNTRY_FLAGS = {"US": ("🇺🇸", "United States"), "EZ": ("🇪🇺", "Eurozone"),
                  "KR": ("🇰🇷", "South Korea"),    "JP": ("🇯🇵", "Japan"),
                  "GB": ("🇬🇧", "United Kingdom")}


@callback(
    Output("country-flag-display", "children"),
    Output("country-flag-display", "title"),
    Input("country-selector", "value"),
    prevent_initial_call=False,
)
def update_country_flag(value: str):
    flag, title = _COUNTRY_FLAGS.get(str(value or "US"), ("🌐", "Unknown"))
    return flag, title


@callback(
    Output("country-store", "data"),
    Input("country-selector", "value"),
    prevent_initial_call=True,
)
def update_country(value: str) -> str:
    return str(value) if value else "US"


# ── Keyboard navigation (arrow keys on Regime History page) ──────────────────
# CB1: enable/disable the poll interval and set up the key listener

app.clientside_callback(
    """
    function(pathname) {
        window._rhKeyDelta = 0;
        if (window._rhKeyListener) {
            document.removeEventListener('keydown', window._rhKeyListener);
            window._rhKeyListener = null;
        }
        if (pathname === '/regime-history') {
            window._rhKeyListener = function(e) {
                var t = e.target;
                if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
                if (e.key === 'ArrowLeft')  { e.preventDefault(); window._rhKeyDelta =  1; }
                if (e.key === 'ArrowRight') { e.preventDefault(); window._rhKeyDelta = -1; }
            };
            document.addEventListener('keydown', window._rhKeyListener);
            return false;   /* enable interval */
        }
        return true;        /* disable interval */
    }
    """,
    Output("key-interval", "disabled"),
    Input("url", "pathname"),
)

# CB2: drain the keyboard delta into the nav-event store

app.clientside_callback(
    """
    function(n) {
        var d = window._rhKeyDelta || 0;
        window._rhKeyDelta = 0;
        if (d !== 0) return {type: 'delta', value: d, t: n};
        return dash_clientside.no_update;
    }
    """,
    Output("nav-event", "data"),
    Input("key-interval", "n_intervals"),
)

# Plotly's native ``hoversubplots='axis'`` does not expand across the matched
# axes created by ``make_subplots(shared_xaxes=True)``. Mirror the hovered
# timestamp explicitly to every Cartesian subplot instead.
app.clientside_callback(
    """
    function(figure) {
        if (!figure) return dash_clientside.no_update;
        setTimeout(function() {
            var wrapper = document.getElementById('regime-chart');
            var gd = wrapper && wrapper.querySelector('.js-plotly-plot');
            if (!gd || typeof gd.on !== 'function' || gd._rhHoverSyncBound) return;

            gd._rhHoverSyncBound = true;
            function drawSharedHoverLine(rawX) {
                var layout = gd._fullLayout;
                var hoverLayer = gd.querySelector('.hoverlayer');
                var xAxis = layout && layout.xaxis;
                var yAxes = layout && layout._subplots ? layout._subplots.yaxis : null;
                if (!hoverLayer || !xAxis || !yAxes || !yAxes.length) return;

                var xPixel = xAxis._offset + xAxis.d2p(rawX);
                var top = Infinity;
                var bottom = -Infinity;
                yAxes.forEach(function(axisId) {
                    var key = axisId === 'y' ? 'yaxis' : 'yaxis' + axisId.slice(1);
                    var axis = layout[key];
                    if (!axis) return;
                    top = Math.min(top, axis._offset);
                    bottom = Math.max(bottom, axis._offset + axis._length);
                });
                if (!Number.isFinite(xPixel) || !Number.isFinite(top) || !Number.isFinite(bottom)) return;

                var line = hoverLayer.querySelector('.rh-shared-hover-line');
                if (!line) {
                    line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('class', 'rh-shared-hover-line');
                    line.setAttribute('stroke', 'rgba(210, 215, 225, 0.72)');
                    line.setAttribute('stroke-width', '1');
                    line.setAttribute('stroke-dasharray', '4,3');
                    line.setAttribute('pointer-events', 'none');
                    hoverLayer.insertBefore(line, hoverLayer.firstChild);
                }
                line.setAttribute('x1', xPixel);
                line.setAttribute('x2', xPixel);
                line.setAttribute('y1', top);
                line.setAttribute('y2', bottom);
            }

            gd.on('plotly_hover', function(eventData) {
                if (gd._rhHoverSyncing || !eventData || !eventData.points || !eventData.points.length) return;
                var rawX = eventData.points[0].x;
                var xValue = rawX instanceof Date ? rawX.getTime() : Date.parse(rawX);
                var subplots = gd._fullLayout && gd._fullLayout._subplots
                    ? gd._fullLayout._subplots.cartesian : null;
                if (!Number.isFinite(xValue) || !subplots || !subplots.length) return;

                gd._rhHoverSyncing = true;
                try {
                    Plotly.Fx.hover(gd, {xval: xValue}, subplots);
                    requestAnimationFrame(function() { drawSharedHoverLine(rawX); });
                } finally {
                    setTimeout(function() { gd._rhHoverSyncing = false; }, 0);
                }
            });
            gd.on('plotly_unhover', function() {
                var line = gd.querySelector('.rh-shared-hover-line');
                if (line) line.remove();
            });
        }, 0);
        return Date.now();
    }
    """,
    Output("hover-sync-init", "data"),
    Input("regime-chart", "figure"),
    prevent_initial_call=True,
)

# Native <details> toggle events are not exposed as Dash prop changes. Bind the
# disclosure directly and persist its state in the top-level store so replacing
# the date-specific info card does not collapse it.
app.clientside_callback(
    """
    function(children) {
        if (!children) return dash_clientside.no_update;
        setTimeout(function() {
            var details = document.getElementById('regime-components-details');
            if (!details || details._rhToggleBound) return;
            details._rhToggleBound = true;
            details.addEventListener('toggle', function() {
                dash_clientside.set_props('regime-components-open', {data: details.open});
            });
        }, 0);
        return Date.now();
    }
    """,
    Output("regime-components-toggle-init", "data"),
    Input("regime-info-box", "children"),
    prevent_initial_call=True,
)

# ── Routing callback ──────────────────────────────────────────────────────────

_PAGE_MAP = {
    "/":              _page_chart_overlay,
    "/charts":        _page_chart_overlay,
    "/overview":      _page_overview,
    "/data-dashboard":_page_data_dashboard,
    "/explorer":      _page_explorer,
    "/methodology":   _page_methodology,
    "/yield-curve":   _page_yield_curve,
    "/regime-map":    _page_regime_map,
    "/regime-history":_page_regime_history,
    "/debt-stress":   _page_debt_stress,
    "/weight-audit":  _page_weight_audit,
}


@callback(
    [Output("page-content", "children"),
     Output("page-trigger", "data")],
    Input("url", "pathname"),
    prevent_initial_call=False,
)
def route_page(pathname: str):
    pathname = pathname or "/charts"
    fn = _PAGE_MAP.get(pathname)
    layout = fn() if fn else html.Div(f"Page '{pathname}' not found", className="p-4 text-muted")
    return layout, {"page": pathname}


# Clientside: update CSS custom properties on documentElement when theme changes.
# Embeds the full THEME_CSS_VARS dict as JSON so all logic stays in Python.
app.clientside_callback(
    f"""
    function(theme) {{
        var themes = {json.dumps(THEME_CSS_VARS)};
        var t = themes[theme] || themes['carbon'];
        var r = document.documentElement;
        Object.entries(t).forEach(function(pair) {{
            r.style.setProperty(pair[0], pair[1]);
        }});
        return theme;
    }}
    """,
    Output("theme-dummy", "children"),
    Input("theme-store", "data"),
)

# ── Callbacks — aggregate selected series ─────────────────────────────────────

@callback(
    Output("series-selector-body", "children"),
    Input("country-store", "data"),
    prevent_initial_call=False,
)
def update_series_selector(country: str) -> list:
    """Populate the chart overlay series sidebar for the selected country."""
    from dashboard.data_dashboard import _SIGNAL_NAMES as _DN
    from dashboard.data_dashboard import _FORCE_LABELS as _FL
    country = (country or "US").upper()
    if country == "US":
        return _build_series_groups_us()
    # Dynamic: build groups from signals table for non-US country
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        df = con.execute(
            "SELECT id, force FROM signals WHERE country = ? "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1 "
            "ORDER BY force, id",
            [country],
        ).df()
        con.close()
    except Exception:
        return [html.Div("Could not load signals.", className="text-muted small")]
    if df.empty:
        return [html.Div(f"No signals found for {country}.", className="text-muted small")]
    groups = []
    for force in df["force"].unique():
        force_df = df[df["force"] == force]
        group_name = _FL.get(force, force.replace("_", " ").title())
        options = []
        for _, row in force_df.iterrows():
            concept = ".".join(row["id"].split(".")[1:])
            label = _DN.get(concept, concept.split(".")[-1].replace("_", " ").title())
            options.append({"label": label, "value": row["id"]})
        groups.append(html.Div([
            html.P(group_name, className="text-muted small mb-1 mt-2 fw-semibold"),
            dcc.Checklist(
                id={"type": "group-checklist", "group": group_name},
                options=options,
                value=[],
                inputStyle={"marginRight": "6px"},
                labelStyle={"display": "block", "fontSize": "0.82rem", "marginBottom": "3px"},
            ),
        ]))
    return groups


@callback(
    Output("selected-series", "data"),
    [Input({"type": "group-checklist", "group": dash.ALL}, "value"),
     Input("btn-clear-all", "n_clicks"),
     Input("country-store", "data")],
    prevent_initial_call=False,
)
def aggregate_selected(group_values: list[list[str]], _clear: Any, _country: Any) -> list[str]:
    triggered = dash.callback_context.triggered_id
    if triggered == "btn-clear-all" or triggered == "country-store":
        return []
    result = []
    for vals in (group_values or []):
        result.extend(vals or [])
    return result


# ── Callbacks — time range ────────────────────────────────────────────────────

@callback(
    Output("date-range", "data"),
    [Input("btn-1Y", "n_clicks"),
     Input("btn-3Y", "n_clicks"),
     Input("btn-5Y", "n_clicks"),
     Input("btn-10Y", "n_clicks"),
     Input("btn-MAX", "n_clicks"),
     Input("range-slider", "value")],
    State("date-range", "data"),
    prevent_initial_call=True,
)
def update_date_range(
    _1y: Any, _3y: Any, _5y: Any, _10y: Any, _max: Any,
    slider_val: list[float],
    current: dict,
) -> dict:
    today = datetime.date.today()
    ctx = dash.callback_context.triggered_id

    preset_map = {
        "btn-1Y": 365,
        "btn-3Y": 365 * 3,
        "btn-5Y": 365 * 5,
        "btn-10Y": 365 * 10,
    }
    if ctx in preset_map:
        start = (today - datetime.timedelta(days=preset_map[ctx])).isoformat()
        return {"start": start, "end": today.isoformat()}
    if ctx == "btn-MAX":
        return {"start": None, "end": None}

    # Slider: map [0,1] fractions onto full history (1980–today)
    epoch_start = datetime.date(1980, 1, 1)
    total_days = (today - epoch_start).days
    s_frac, e_frac = (slider_val or [0, 1])
    start = (epoch_start + datetime.timedelta(days=int(s_frac * total_days))).isoformat()
    end = (epoch_start + datetime.timedelta(days=int(e_frac * total_days))).isoformat()
    return {"start": start, "end": end}


# ── Callbacks — overlay chart ─────────────────────────────────────────────────

@callback(
    Output("overlay-chart", "figure"),
    [Input("selected-series", "data"),
     Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_overlay_chart(
    selected_ids: list[str],
    date_range: dict,
    theme_name: str = DEFAULT_THEME,
    _trigger: Any = None,
) -> go.Figure:
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    if not selected_ids:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "Select series from the left sidebar"))
        return fig

    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")

    from dashboard.data_dashboard import _SIGNAL_NAMES as _DN
    from dashboard.data_dashboard import _FORCE_LABELS as _FL

    def _entry_for(sid: str) -> dict:
        if sid in _BY_ID:
            return _BY_ID[sid]
        # Non-US signal not in the catalog: build a minimal entry on the fly
        parts = sid.split(".")
        concept = ".".join(parts[1:]) if len(parts) >= 2 else sid
        force = parts[1] if len(parts) >= 3 else "other"
        return {
            "label": _DN.get(concept, parts[-1].replace("_", " ").title()),
            "default_pane": _FL.get(force, force.title()),
            "units": "",
            "value_col": "value",
        }

    # Group selected series by their default_pane
    pane_series: dict[str, list[str]] = defaultdict(list)
    for sid in selected_ids:
        entry = _entry_for(sid)
        pane = entry.get("default_pane", "other")
        pane_series[pane].append(sid)

    panes = list(pane_series.keys())
    n_panes = len(panes)

    fig = make_subplots(
        rows=n_panes,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=panes,
    )

    color_idx = 0
    for row_idx, pane in enumerate(panes, start=1):
        for sid in pane_series[pane]:
            entry = _entry_for(sid)
            df = load_signal_history(
                sid,
                value_col=entry.get("value_col", "value"),
                start_date=start,
                end_date=end,
            )
            if df.empty:
                continue
            color = _COLORS[color_idx % len(_COLORS)]
            color_idx += 1
            fig.add_trace(
                go.Scatter(
                    x=df["as_of"],
                    y=df["value"],
                    name=entry.get("label", sid),
                    line={"color": color, "width": 1.5},
                    hovertemplate=f"<b>{entry.get('label', sid)}</b><br>%{{x|%Y-%m-%d}}<br>%{{y:.2f}} {entry.get('units', '')}<extra></extra>",
                ),
                row=row_idx,
                col=1,
            )
        # Y-axis label per pane
        units_in_pane = {_entry_for(s).get("units", "") for s in pane_series[pane]}
        y_title = " / ".join(u for u in units_in_pane if u) or ""
        fig.update_yaxes(title_text=y_title, row=row_idx, col=1)

    fig.update_layout(
        **figure_layout(theme_name),
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "xanchor": "left", "x": 0},
        height=max(300 * n_panes, 400),
        uirevision="chart-overlay",
    )
    fig.update_xaxes(showgrid=True, gridcolor=t["grid_color"], row=n_panes, col=1)
    return fig


# ── Callbacks — yield curve ───────────────────────────────────────────────────

@callback(
    [Output("yc-date-picker", "options"),
     Output("yc-date-picker", "value"),
     Output("yc-date-compare", "options")],
    Input("page-trigger", "data"),
    prevent_initial_call=False,
)
def populate_yc_dates(_trigger: Any) -> tuple[list[dict], str, list[dict]]:
    dates = available_dates_for_yield_curve()
    if not dates:
        return [], "", []
    # Downsample to month-end dates for the picker (fewer options)
    monthly = sorted({d[:7] for d in dates})
    # Map month string → last available daily date in that month
    month_to_date: dict[str, str] = {}
    for d in dates:
        m = d[:7]
        if m in monthly:
            month_to_date[m] = d  # last one wins (dates are sorted)
    options = [{"label": m, "value": month_to_date[m]} for m in monthly]
    latest = options[-1]["value"] if options else ""
    return options, latest, options


@callback(
    Output("yield-curve-chart", "figure"),
    [Input("yc-date-picker", "value"),
     Input("yc-date-compare", "value"),
     Input("theme-store", "data"),
     Input("country-store", "data")],
    prevent_initial_call=False,
)
def update_yield_curve(
    date_primary: str,
    date_compare: str,
    theme_name: str = DEFAULT_THEME,
    country: str = "US",
) -> go.Figure:
    country = (country or "US").upper()
    if country != "US":
        fig = go.Figure()
        fig.update_layout(**figure_layout(
            theme_name,
            f"Yield Curve — US Treasury data only  ·  {country} term structure not yet available",
        ))
        return fig
    if not date_primary:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "Select a date"))
        return fig

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=False,
        vertical_spacing=0.12,
        subplot_titles=["Term Structure", "Historical 10Y-2Y Spread"],
        row_heights=[0.6, 0.4],
    )

    # Primary curve
    df_primary = load_yield_curve_term_structure(date_primary)
    if not df_primary.empty:
        fig.add_trace(
            go.Scatter(
                x=df_primary["maturity_years"],
                y=df_primary["yield_pct"],
                mode="lines+markers",
                name=date_primary,
                line={"color": _COLORS[0], "width": 2},
                marker={"size": 7},
                hovertemplate="<b>%{customdata}</b><br>Yield: %{y:.2f}%<extra></extra>",
                customdata=df_primary["label"],
            ),
            row=1, col=1,
        )

    # Comparison curve
    if date_compare:
        df_compare = load_yield_curve_term_structure(date_compare)
        if not df_compare.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_compare["maturity_years"],
                    y=df_compare["yield_pct"],
                    mode="lines+markers",
                    name=date_compare,
                    line={"color": _COLORS[1], "width": 2, "dash": "dash"},
                    marker={"size": 7},
                    hovertemplate="<b>%{customdata}</b><br>Yield: %{y:.2f}%<extra></extra>",
                    customdata=df_compare["label"],
                ),
                row=1, col=1,
            )

    # Historical 10Y-2Y spread
    spread_df = load_signal_history("us.premium.yield_curve_10y2y")
    if not spread_df.empty:
        colors = [_COLORS[0] if v >= 0 else _COLORS[2] for v in spread_df["value"]]
        fig.add_trace(
            go.Bar(
                x=spread_df["as_of"],
                y=spread_df["value"],
                name="10Y-2Y Spread",
                marker_color=colors,
                hovertemplate="%{x|%Y-%m-%d}<br>Spread: %{y:.2f}%<extra></extra>",
                showlegend=False,
            ),
            row=2, col=1,
        )
        # Mark the selected date
        if date_primary:
            selected_ts = pd.Timestamp(date_primary)
            nearby = spread_df[spread_df["as_of"] <= selected_ts]
            if not nearby.empty:
                fig.add_vline(
                    x=selected_ts,
                    line_dash="dot",
                    line_color=_COLORS[0],
                    row=2, col=1,
                )

    # X-axis: maturity labels
    maturity_ticks = [0.25, 1, 2, 5, 10, 30]
    maturity_labels = ["3M", "1Y", "2Y", "5Y", "10Y", "30Y"]
    fig.update_xaxes(
        tickvals=maturity_ticks,
        ticktext=maturity_labels,
        title_text="Maturity",
        row=1, col=1,
    )
    fig.update_yaxes(title_text="Yield (%)", row=1, col=1)
    fig.update_yaxes(title_text="Spread (%)", row=2, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=2, col=1)

    fig.update_layout(**figure_layout(theme_name), height=650, uirevision="yield-curve")
    return fig


# ── Regime History — helpers + callbacks ─────────────────────────────────────

_GROWTH_COLOR    = "#4C9BE8"
_INFLATION_COLOR = "#E8734C"


def _regime_info_children(
    row: dict,
    is_current: bool,
    comp_df: "pd.DataFrame | None" = None,
    stale_dict: "dict[str, int] | None" = None,
    g_delta: "float | None" = None,
    i_delta: "float | None" = None,
    components_open: bool = False,
    weight_audit: "dict | None" = None,
    rolling: "dict | None" = None,
) -> list:
    """Build the full-width regime info card: summary strip + component table.

    rolling (optional): {
        "window": int,          # months in rolling window (0 = full history)
        "g_score": float|None,  # rolling growth force score
        "i_score": float|None,  # rolling inflation force score
        "g_delta": float|None,  # rolling MoM delta (growth)
        "i_delta": float|None,  # rolling MoM delta (inflation)
        "g_mom_z": float|None,  # Z-score of MoM changes (growth)
        "i_mom_z": float|None,  # Z-score of MoM changes (inflation)
    }
    """
    rolling = rolling or {}
    rw = int(rolling.get("window", 0))
    use_rolling = rw > 0

    # Use rolling scores if window is active, otherwise stored composite scores
    g_score    = rolling.get("g_score") if use_rolling else row.get("growth_score")
    i_score    = rolling.get("i_score") if use_rolling else row.get("inflation_score")

    # Derive quadrant from rolling scores when active; fall back to stored label
    _RQ = {
        (True,  True):  "Inflationary Boom",
        (True,  False): "Expansion",
        (False, True):  "Stagflation",
        (False, False): "Disinflationary Slowdown",
    }
    if use_rolling and g_score is not None and i_score is not None:
        try:
            quadrant = _RQ[(float(g_score) >= 0, float(i_score) >= 0)]
        except Exception:
            quadrant = row.get("quadrant") or "—"
    else:
        quadrant = row.get("quadrant") or "—"

    confidence = row.get("confidence")
    # Use rolling disequilibrium score when a diseq window is active
    use_rolling_diseq = rolling.get("diseq_window", 0) > 0
    diseq = (
        rolling.get("diseq_score", row.get("disequilibrium_score"))
        if use_rolling_diseq
        else row.get("disequilibrium_score")
    )
    n_g        = int(row.get("n_growth_signals", 0) or 0)
    n_i        = int(row.get("n_inflation_signals", 0) or 0)
    # Dynamic totals from the live composites config (not hardcoded US counts)
    if comp_df is not None and not comp_df.empty:
        n_g_total = len(comp_df[comp_df["composite"] == "growth"])
        n_i_total = len(comp_df[comp_df["composite"] == "inflation"])
    else:
        n_g_total, n_i_total = 9, 8
    q_color    = _QUADRANT_COLOR.get(quadrant, "#888")
    muted      = {"color": "var(--muted-color)"}

    def _fmt(v: Any, prec: int = 3) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        return f"{v:+.{prec}f}"

    def _arrow(v: Any) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "→"
        return "↑" if float(v) > 0.001 else ("↓" if float(v) < -0.001 else "→")

    def _score_color(v: Any, pos_color: str) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "#555"
        return pos_color if float(v) >= 0 else "#aaaaaa"

    # ── Reusable block builders ───────────────────────────────────────────────
    _SZ = "1.55rem"  # shared big-number font size

    def _val_block(label: str, value: Any, color: str, sub: str = "") -> html.Div:
        val_str = _fmt(value)
        c = _score_color(value, color)
        return html.Div([
            html.Div(label, style={"fontSize": "0.65rem", "color": "var(--muted-color)",
                                   "marginBottom": "3px", "whiteSpace": "nowrap"}),
            html.Div([
                html.Span(_arrow(value), style={"fontSize": "0.95rem", "color": c, "marginRight": "3px"}),
                html.Span(val_str, style={"fontSize": _SZ, "fontWeight": "700",
                                          "color": c, "fontFamily": "monospace"}),
            ], style={"lineHeight": "1.1", "marginBottom": "2px"}),
            html.Div(sub, style={"fontSize": "0.65rem", "color": "var(--muted-color)"}),
        ], style={"minWidth": "105px"})

    def _stat_block(label: str, val_str: str, color: str = "var(--font-color)") -> html.Div:
        """Confidence / Disequilibrium — same visual size as _val_block but no arrow."""
        return html.Div([
            html.Div(label, style={"fontSize": "0.65rem", "color": "var(--muted-color)",
                                   "marginBottom": "3px", "whiteSpace": "nowrap"}),
            html.Div(val_str, style={"fontSize": _SZ, "fontWeight": "700",
                                     "color": color, "fontFamily": "monospace",
                                     "lineHeight": "1.1", "marginBottom": "2px"}),
            html.Div(" ", style={"fontSize": "0.65rem"}),  # spacer to align baseline
        ], style={"minWidth": "105px"})

    def _group(header: str, blocks: list) -> html.Div:
        """Blocks under a single centered section header, left-separated."""
        return html.Div([
            html.Div(header, style={
                "fontSize": "0.6rem", "textTransform": "uppercase",
                "letterSpacing": "0.09em", "color": "var(--muted-color)",
                "fontWeight": "700", "textAlign": "center", "marginBottom": "8px",
            }),
            html.Div(blocks, style={"display": "flex", "gap": "18px"}),
        ], style={
            "borderLeft": "1px solid var(--border-color)",
            "paddingLeft": "20px",
        })

    past_badge = (
        html.Div("⚠ PAST DATA",
                 style={"fontSize": "0.68rem", "color": "#F4C842",
                        "textAlign": "center", "marginTop": "5px"})
        if not is_current else None
    )

    # ── Selected date block (shown for past and current) ─────────────────────
    try:
        _as_of = pd.Timestamp(row.get("as_of", ""))
        _today = pd.Timestamp.today()
        _mo_ago = (_today.year - _as_of.year) * 12 + (_today.month - _as_of.month)
        if is_current:
            _ago_str = "current"
        elif _mo_ago >= 24:
            _yrs = _mo_ago // 12
            _rem = _mo_ago % 12
            _ago_str = f"{_yrs} yr {_rem} mo ago" if _rem else f"{_yrs} yr ago"
        else:
            _ago_str = f"{_mo_ago} month{'s' if _mo_ago != 1 else ''} ago"
        _date_label = _as_of.strftime("%b %Y")
    except Exception:
        _date_label, _ago_str = "—", ""

    date_block = html.Div([
        html.Div(_date_label, style={
            "fontSize": "1.15rem", "fontWeight": "700",
            "color": "var(--font-color)", "textAlign": "center",
            "letterSpacing": "0.02em",
        }),
        html.Div(_ago_str, style={
            "fontSize": "0.72rem", "color": "var(--muted-color)",
            "textAlign": "center", "marginTop": "2px",
        }),
    ], style={"marginTop": "8px"})

    conf_str = (f"{confidence:.0%}" if confidence is not None and not pd.isna(confidence) else "—")
    diseq_str = _fmt(diseq)

    summary_strip = html.Div(
        style={
            "display": "flex", "alignItems": "flex-start",
            "gap": "0", "flexWrap": "wrap", "marginBottom": "16px",
        },
        children=[
            # ── Quadrant badge ────────────────────────────────────────────────
            html.Div([
                html.Div(
                    quadrant,
                    style={"backgroundColor": q_color, "color": "#111",
                           "textAlign": "center", "fontWeight": "bold",
                           "fontSize": "0.88rem", "padding": "8px 12px",
                           "borderRadius": "4px",
                           "width": "195px", "boxSizing": "border-box",
                           "whiteSpace": "nowrap"},
                ),
                *([past_badge] if past_badge is not None else []),
                date_block,
            ], style={"paddingRight": "20px", "width": "215px", "flexShrink": "0",
                      "display": "flex", "flexDirection": "column", "justifyContent": "flex-start"}),

            # ── Force Z-Scores ─────────────────────────────────────────────────
            _group(
                f"Force Z-Scores{'  ·  rolling ' + str(rw) + 'mo' if use_rolling else ''}",
                [
                    _val_block("Growth",    g_score, _GROWTH_COLOR,    f"{n_g}/{n_g_total} signals"),
                    _val_block("Inflation", i_score, _INFLATION_COLOR, f"{n_i}/{n_i_total} signals"),
                ],
            ),

            # ── Momentum (MoM Δ in force score) ───────────────────────────────
            _group("Momentum  (Δ MoM)", [
                _val_block("Growth",    rolling.get("g_delta", g_delta) if use_rolling else g_delta,
                           _GROWTH_COLOR),
                _val_block("Inflation", rolling.get("i_delta", i_delta) if use_rolling else i_delta,
                           _INFLATION_COLOR),
            ]),

            # ── Momentum Z (Z-score of recent MoM changes) ────────────────────
            _group("Momentum Z  (12mo)", [
                _val_block("Growth",    rolling.get("g_mom_z"), _GROWTH_COLOR,
                           "Z of Δ MoM"),
                _val_block("Inflation", rolling.get("i_mom_z"), _INFLATION_COLOR,
                           "Z of Δ MoM"),
            ]),

            # ── Confidence + Disequilibrium ────────────────────────────────────
            _group("Regime Quality", [
                _stat_block("Confidence",     conf_str),
                _stat_block("Disequilibrium", diseq_str),
            ]),
        ],
    )

    # ── Component breakdown table ─────────────────────────────────────────────
    if comp_df is None or comp_df.empty:
        table_section = html.Div("Component data unavailable — run pipeline.", style=muted)
    else:
        th_sty = {
            "textAlign": "left", "padding": "5px 10px",
            "fontSize": "0.68rem", "textTransform": "uppercase",
            "letterSpacing": "0.06em", "color": "var(--muted-color)",
            "borderBottom": "1px solid var(--border-color)",
            "whiteSpace": "nowrap",
        }
        td_sty = {
            "padding": "5px 10px", "fontSize": "0.82rem",
            "borderBottom": "1px solid var(--border-color)",
            "color": "var(--font-color)", "verticalAlign": "middle",
        }
        td_mono = {**td_sty, "fontFamily": "monospace"}

        _stale_months = stale_dict or {}
        _audit_by_signal: dict[str, dict] = {}
        for force_audit in (weight_audit or {}).values():
            if isinstance(force_audit, dict):
                _audit_by_signal.update(force_audit)

        def _section(force: str, total: int, color: str) -> list:
            df_f = comp_df[comp_df["composite"] == force].copy()
            rows = []
            for _, sr in df_f.iterrows():
                z = sr.get("zscore")
                direction = sr.get("direction") or ""
                change3m  = sr.get("change_3m")
                invert    = bool(sr.get("invert", False))
                is_stale  = bool(sr.get("is_stale", False))
                low_hist  = bool(sr.get("low_history", False))
                as_of     = sr.get("as_of")
                weight    = float(sr.get("weight", 1.0))
                z_missing = z is None or (isinstance(z, float) and pd.isna(z))

                # Last data
                if as_of is not None and not pd.isna(as_of):
                    last_str = pd.Timestamp(as_of).strftime("%b %Y")
                else:
                    last_str = "—"

                # Configured and point-in-time effective weights
                sig_id = sr.get("signal_id", "")
                audit = _audit_by_signal.get(sig_id, {})
                if bool(audit.get("missing", False)):
                    z_missing = True
                importance = float(audit.get("importance", sr.get("importance", 1.0)))
                config_wt = float(audit.get("config_weight", weight))
                eff_wt = float(audit.get("effective_weight", 0.0 if z_missing else config_wt))
                momentum_mult = float(audit.get("momentum_multiplier", 1.0))
                decay_fraction = float(audit.get("decay_fraction", 1.0))
                audit_age = int(round(float(audit.get("age_months", 0.0))))
                config_wt_str = f"{config_wt * 100:.1f}%"
                eff_wt_str = f"{eff_wt * 100:.1f}%"
                eff_wt_color = (
                    "#E8734C" if eff_wt <= 0
                    else (color if eff_wt > config_wt + 1e-9
                          else ("#F4C842" if eff_wt < config_wt - 1e-9
                                else "var(--font-color)"))
                )

                # Z-score bar cell
                if z_missing:
                    z_cell = html.Td("—", style={**td_mono, "color": "#555", "textAlign": "right"})
                else:
                    bar_w = min(abs(float(z)) / 2.5 * 80, 80)
                    z_cell = html.Td(
                        html.Div(
                            style={"display": "flex", "alignItems": "center",
                                   "justifyContent": "flex-end", "gap": "6px"},
                            children=[
                                html.Div(style={
                                    "width": f"{bar_w:.0f}px", "height": "6px",
                                    "backgroundColor": color, "borderRadius": "2px",
                                    "opacity": "0.6", "flexShrink": "0",
                                }),
                                html.Span(f"{float(z):+.2f}",
                                          style={"color": color, "fontFamily": "monospace",
                                                 "fontSize": "0.82rem"}),
                            ],
                        ),
                        style={**td_sty, "textAlign": "right"},
                    )

                # Direction / momentum cell
                if not direction:
                    dir_cell_content = html.Span("—", style={"color": "#555"})
                else:
                    # Growth-positive: rising (or falling if inverted). Inflation-positive: rising.
                    positive_dir = "falling" if (force == "growth" and invert) else "rising"
                    is_positive = (direction == positive_dir)
                    arrow = "↑" if direction == "rising" else "↓"
                    dir_color = color if is_positive else "#666"
                    invert_note = " (inv)" if invert else ""
                    dir_cell_content = html.Span(
                        f"{arrow} {direction}{invert_note}",
                        style={"color": dir_color, "fontSize": "0.80rem"},
                    )
                    if change3m is not None and not (isinstance(change3m, float) and pd.isna(change3m)):
                        dir_cell_content = html.Span([
                            html.Span(f"{arrow} {direction}{invert_note}   ",
                                      style={"color": dir_color}),
                            html.Span(f"{float(change3m):+.3f} 3m",
                                      style={"color": "var(--muted-color)",
                                             "fontSize": "0.72rem", "fontFamily": "monospace"}),
                        ])

                # Status cell
                fill_months = max(_stale_months.get(sig_id, 0), audit_age)
                # Composite carry age is point-in-time metadata.  It must drive
                # the badge even when the source observation's ingestion-time
                # is_stale flag is false (the usual case for forward fills).
                if not z_missing and (is_stale or fill_months > 0):
                    status = html.Span([
                        html.Span(
                            f"DECAYED · {fill_months}m",
                            style={"background": "#7a4a00", "color": "#ffcc80",
                                   "padding": "1px 5px", "borderRadius": "3px",
                                   "fontSize": "0.70rem"},
                        ),
                        html.Span(
                            f" · time {decay_fraction:.0%} · momentum {momentum_mult:.1f}×",
                            style={"color": "var(--muted-color)", "fontSize": "0.72rem"},
                        ),
                    ])
                elif low_hist:
                    status = html.Span("LOW HISTORY",
                                       style={"background": "#3a3a00", "color": "#cccc88",
                                              "padding": "1px 5px", "borderRadius": "3px",
                                              "fontSize": "0.70rem"})
                elif z_missing:
                    status = html.Span("BLANK",
                                       style={"background": "#3a2020", "color": "#cc7777",
                                              "padding": "1px 5px", "borderRadius": "3px",
                                              "fontSize": "0.70rem"})
                else:
                    if momentum_mult > 1.0 + 1e-9:
                        status_label = "ACTIVE · BOOSTED"
                        detail = f" · momentum agreement {momentum_mult:.1f}×"
                    elif momentum_mult < 1.0 - 1e-9:
                        status_label = "ACTIVE · CONFLICT"
                        detail = f" · momentum conflict {momentum_mult:.1f}×"
                    else:
                        status_label = "ACTIVE"
                        detail = ""
                    status = html.Span([
                        html.Span(
                            status_label,
                            style={"background": "#1a3a1a", "color": "#88cc88",
                                   "padding": "1px 5px", "borderRadius": "3px",
                                   "fontSize": "0.70rem"},
                        ),
                        html.Span(
                            detail,
                            style={"color": "var(--muted-color)", "fontSize": "0.72rem"},
                        ),
                    ])

                row_bg = (
                    "rgba(60,20,20,0.12)"
                    if z_missing or is_stale or fill_months > 0 or low_hist
                    else "transparent"
                )
                rows.append(html.Tr(
                    style={"backgroundColor": row_bg},
                    children=[
                        html.Td(sr["label"], style=td_sty),
                        html.Td(f"{importance:.2f}", style={**td_mono, "textAlign": "center"}),
                        html.Td(config_wt_str, style={**td_mono, "textAlign": "center"}),
                        html.Td(eff_wt_str, style={**td_mono, "textAlign": "center",
                                                  "color": eff_wt_color,
                                                  "fontWeight": "600" if eff_wt != config_wt else "400"}),
                        html.Td(last_str, style={**td_mono, "textAlign": "center",
                                                  "color": "var(--muted-color)",
                                                  "fontSize": "0.75rem"}),
                        z_cell,
                        html.Td(dir_cell_content, style=td_sty),
                        html.Td(status, style=td_sty),
                    ],
                ))
            return rows

        def _force_table(force: str, n_total: int, color: str) -> list:
            """Return [section_header_row, ...data_rows] for one force group."""
            rows = _section(force, n_total, color)
            df_f = comp_df[comp_df["composite"] == force]
            if _audit_by_signal:
                n_active = sum(
                    float(_audit_by_signal.get(sid, {}).get("effective_weight", 0.0)) > 0
                    for sid in df_f["signal_id"]
                )
            else:
                n_active = int(
                    (df_f["zscore"].notna()
                     & ~df_f["is_stale"]
                     & ~df_f["low_history"]).sum()
                )
            section_header = html.Tr([
                html.Td(
                    f"{force.upper()} FORCE  ·  {n_active}/{len(df_f)} active",
                    colSpan=8,
                    style={
                        "padding": "5px 10px",
                        "fontSize": "0.68rem", "fontWeight": "700",
                        "textTransform": "uppercase", "letterSpacing": "0.07em",
                        "color": color,
                        "backgroundColor": "rgba(0,0,0,0.18)",
                        "borderBottom": f"1px solid {color}",
                        "borderTop": "1px solid var(--border-color)",
                    },
                )
            ])
            return [section_header] + rows

        col_header = html.Tr([
            html.Th("Signal",    style=th_sty),
            html.Th("Importance", style={**th_sty, "textAlign": "center"}),
            html.Th("Config Wt", style={**th_sty, "textAlign": "center"}),
            html.Th("Eff Wt",    style={**th_sty, "textAlign": "center"}),
            html.Th("Last Data", style={**th_sty, "textAlign": "center"}),
            html.Th("Force Z",   style={**th_sty, "textAlign": "right"}),
            html.Th("Momentum",  style=th_sty),
            html.Th("Status / Detail", style=th_sty),
        ])

        all_rows = _force_table("growth", 9, _GROWTH_COLOR) + _force_table("inflation", 8, _INFLATION_COLOR)

        df_g = comp_df[comp_df["composite"] == "growth"]
        df_i = comp_df[comp_df["composite"] == "inflation"]
        if _audit_by_signal:
            n_active_g = sum(
                float(_audit_by_signal.get(sid, {}).get("effective_weight", 0.0)) > 0
                for sid in df_g["signal_id"]
            )
            n_active_i = sum(
                float(_audit_by_signal.get(sid, {}).get("effective_weight", 0.0)) > 0
                for sid in df_i["signal_id"]
            )
        else:
            n_active_g = int((df_g["zscore"].notna() & ~df_g["is_stale"] & ~df_g["low_history"]).sum())
            n_active_i = int((df_i["zscore"].notna() & ~df_i["is_stale"] & ~df_i["low_history"]).sum())
        combined_label = (
            f"Force Component Inputs  ·  "
            f"Growth {n_active_g}/{len(df_g)}  ·  "
            f"Inflation {n_active_i}/{len(df_i)}"
        )

        table_section = html.Details(
            id="regime-components-details",
            open=bool(components_open),
            children=[
                html.Summary(
                    combined_label,
                    style={
                        "cursor": "pointer",
                        "padding": "6px 10px",
                        "fontSize": "0.72rem", "fontWeight": "700",
                        "textTransform": "uppercase", "letterSpacing": "0.07em",
                        "color": "var(--slider-accent)",
                        "backgroundColor": "rgba(0,0,0,0.18)",
                        "borderBottom": "1px solid var(--border-color)",
                        "userSelect": "none",
                    },
                ),
                html.Div(
                    html.Table(
                        [html.Thead(col_header), html.Tbody(all_rows)],
                        style={"width": "100%", "minWidth": "1050px", "borderCollapse": "collapse"},
                    ),
                    style={"overflowX": "auto"},
                ),
            ],
            style={"marginBottom": "6px"},
        )

    footer = html.Div(
        "Config Wt = normalized base share × editable importance × data quality · "
        "Eff Wt = Config Wt × momentum agreement tilt × 3-month half-life decay · "
        "Force Z-Score = weighted average using effective weights · "
        "Confidence = direction-agreement fraction vs. expected quadrant · "
        "Provider-stale/low-history signals excluded; carried observations remain active with decay",
        style={"fontSize": "0.65rem", "color": "#555", "marginTop": "10px"},
    )

    return [summary_strip, table_section, footer]


@callback(
    Output("regime-step-index", "data"),
    [Input({"type": "regime-step-button", "action": "prev"}, "n_clicks"),
     Input({"type": "regime-step-button", "action": "current"}, "n_clicks"),
     Input({"type": "regime-step-button", "action": "next"}, "n_clicks"),
     Input("nav-event", "data"),
     Input("date-range", "data")],
    State("regime-step-index", "data"),
    prevent_initial_call=True,
)
def update_regime_step(
    _prev_clicks: Any, _current_clicks: Any, _next_clicks: Any,
    nav_event: dict,
    date_range: dict,
    current_step: int,
) -> int:
    triggered = dash.callback_context.triggered_id
    step = current_step or 0
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")

    if triggered == "date-range":
        return 0

    action = triggered.get("action") if isinstance(triggered, dict) else None

    if action == "current":
        return 0

    if triggered == "nav-event":
        ev = nav_event or {}
        ev_type = ev.get("type")
        val = ev.get("value")
        if val is None:
            return no_update
        comp = load_composite_history(start_date=start, end_date=end)
        n = len(comp)
        if ev_type == "delta":
            delta = int(val)
            if delta == 0:
                return no_update
            return max(0, min(step + delta, n - 1))
        return no_update

    comp = load_composite_history(start_date=start, end_date=end)
    max_step = max(0, len(comp) - 1)

    if action == "prev":
        return min(step + 1, max_step)
    if action == "next":
        return max(step - 1, 0)
    return step


@callback(
    Output("regime-step-index", "data", allow_duplicate=True),
    Input("regime-chart", "clickData"),
    State("date-range", "data"),
    State("regime-step-index", "data"),
    prevent_initial_call=True,
)
def select_regime_point(click_data: dict, date_range: dict, current_step: int) -> int:
    """Move the shared Regime History snapshot to the date clicked in any subplot."""
    points = (click_data or {}).get("points") or []
    raw_date = points[0].get("x") if points else None
    if raw_date is None:
        return no_update

    clicked_date = pd.to_datetime(raw_date, errors="coerce")
    if pd.isna(clicked_date):
        return no_update
    if getattr(clicked_date, "tzinfo", None) is not None:
        clicked_date = clicked_date.tz_convert(None)

    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp = load_composite_history(start_date=start, end_date=end)
    if comp.empty or "as_of" not in comp:
        return no_update

    dates = pd.to_datetime(comp["as_of"], errors="coerce")
    valid = dates.notna()
    if not valid.any():
        return no_update

    valid_positions = valid.to_numpy().nonzero()[0]
    deltas = (dates[valid] - clicked_date).abs().to_numpy()
    position = int(valid_positions[deltas.argmin()])
    new_step = len(comp) - 1 - position
    return new_step if new_step != (current_step or 0) else no_update


# Maps user-facing window month value → composites DB column suffix
_FORCE_WINDOW_COL = {36: "36m", 48: "48m", 60: "60m"}
_DISEQ_WINDOW_COL = {12: "12m", 18: "18m", 24: "24m"}

# Quadrant classification from (growth_positive, inflation_positive) booleans
_RQ_MAP = {
    (True,  True):  "Inflationary Boom",
    (True,  False): "Expansion",
    (False, True):  "Stagflation",
    (False, False): "Disinflationary Slowdown",
}


@callback(
    [Output("regime-info-box", "children"),
     Output("regime-date-display", "children")],
    [Input("regime-step-index",  "data"),
     Input("date-range",         "data"),
     Input("zscore-window-store","data"),
     Input("diseq-window-store", "data"),
     Input("country-store",      "data"),
     Input("page-trigger",       "data")],
    State("regime-components-open", "data"),
    prevent_initial_call=False,
)
def update_regime_info(
    step: int,
    date_range: dict,
    zscore_window: int = 0,
    diseq_window: int = 0,
    country: str = "US",
    _trigger: Any = None,
    components_open: bool = False,
) -> tuple:
    step = step or 0
    zscore_window = int(zscore_window or 0)
    diseq_window = int(diseq_window or 0)
    country = str(country or "US")
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp = load_composite_history(start_date=start, end_date=end, country=country)

    if comp.empty:
        return [], "No data"

    n = len(comp)
    idx = max(0, min(n - 1 - step, n - 1))
    selected = comp.iloc[idx].to_dict()
    all_comp = load_composite_history(country=country)
    is_current = (
        not all_comp.empty
        and pd.Timestamp(selected["as_of"]) == pd.Timestamp(all_comp.iloc[-1]["as_of"])
    )

    date_str = comp.iloc[idx]["as_of"].strftime("%b %Y")
    date_display = (
        f"{date_str} · current" if is_current
        else f"{date_str} · {step} month{'s' if step != 1 else ''} ago"
    )

    # ── Stored MoM delta (always computed from stored composite scores) ────────
    g_delta = i_delta = None
    if idx > 0:
        prev = comp.iloc[idx - 1]
        gs, pgs = selected.get("growth_score"), prev.get("growth_score")
        ins, pins = selected.get("inflation_score"), prev.get("inflation_score")
        if gs is not None and pgs is not None and not pd.isna(gs) and not pd.isna(pgs):
            g_delta = float(gs) - float(pgs)
        if ins is not None and pins is not None and not pd.isna(ins) and not pd.isna(pins):
            i_delta = float(ins) - float(pins)

    # ── Momentum Z — Z-score of recent MoM changes (always from stored scores) ─
    g_mom_z, i_mom_z = _momentum_z_at(comp, idx, window=12)

    # ── Rolling force scores (from pre-computed DB columns) ────────────────────
    rolling: dict = {
        "window": zscore_window,
        "diseq_window": diseq_window,
        "g_mom_z": g_mom_z,
        "i_mom_z": i_mom_z,
    }

    force_sfx = _FORCE_WINDOW_COL.get(zscore_window)
    if force_sfx:
        rg_col, ri_col = f"growth_score_{force_sfx}", f"inflation_score_{force_sfx}"
        # Only use rolling columns if this country has pre-computed data
        has_rolling = rg_col in comp.columns and comp[rg_col].notna().any()
        if has_rolling:
            rg = selected.get(rg_col)
            ri = selected.get(ri_col)
            rolling["g_score"] = float(rg) if rg is not None and not pd.isna(rg) else None
            rolling["i_score"] = float(ri) if ri is not None and not pd.isna(ri) else None
            if idx > 0:
                prev = comp.iloc[idx - 1]
                prev_rg = prev.get(rg_col)
                prev_ri = prev.get(ri_col)
                if rolling["g_score"] is not None and prev_rg is not None and not pd.isna(prev_rg):
                    rolling["g_delta"] = rolling["g_score"] - float(prev_rg)
                if rolling["i_score"] is not None and prev_ri is not None and not pd.isna(prev_ri):
                    rolling["i_delta"] = rolling["i_score"] - float(prev_ri)
        else:
            # Rolling pre-computation not available for this country; fall back to full history
            rolling["window"] = 0

    # ── Rolling disequilibrium (from pre-computed DB columns) ─────────────────
    diseq_sfx = _DISEQ_WINDOW_COL.get(diseq_window)
    if diseq_sfx:
        diseq_col = f"disequilibrium_{diseq_sfx}"
        has_diseq = diseq_col in comp.columns and comp[diseq_col].notna().any()
        if has_diseq:
            rd = selected.get(diseq_col)
            rolling["diseq_score"] = float(rd) if rd is not None and not pd.isna(rd) else None
        else:
            rolling["diseq_window"] = 0

    comp_df = load_composite_component_status(
        country=country, as_of=str(selected["as_of"])
    )
    stale_dict = _parse_stress_components(selected.get("stale_signals") or "")
    try:
        weight_audit = json.loads(selected.get("weight_audit") or "{}")
    except (TypeError, json.JSONDecodeError):
        weight_audit = {}
    return (
        _regime_info_children(
            selected,
            is_current,
            comp_df,
            stale_dict,
            g_delta,
            i_delta,
            components_open,
            weight_audit,
            rolling,
        ),
        date_display,
    )


@callback(
    Output("regime-chart", "figure"),
    [Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("regime-step-index", "data"),
     Input("zscore-window-store", "data"),
     Input("diseq-window-store",  "data"),
     Input("country-store",       "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_regime_chart(
    date_range: dict,
    theme_name: str = DEFAULT_THEME,
    step: int = 0,
    zscore_window: int = 0,
    diseq_window: int = 0,
    country: str = "US",
    _trigger: Any = None,
) -> go.Figure:
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    zscore_window = int(zscore_window or 0)
    diseq_window = int(diseq_window or 0)
    country = str(country or "US")

    comp = load_composite_history(start_date=start, end_date=end, country=country)
    if comp.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No composite data"))
        return fig

    # Resolve which columns to use based on rolling window settings.
    # For non-US countries the pre-computed rolling columns are all null —
    # fall back to the base column when the rolling column has no data.
    force_sfx = _FORCE_WINDOW_COL.get(zscore_window)
    diseq_sfx = _DISEQ_WINDOW_COL.get(diseq_window)
    def _has_data(df: pd.DataFrame, col: str) -> bool:
        return col in df.columns and df[col].notna().any()
    g_col = f"growth_score_{force_sfx}" if force_sfx and _has_data(comp, f"growth_score_{force_sfx}") else "growth_score"
    i_col = f"inflation_score_{force_sfx}" if force_sfx and _has_data(comp, f"inflation_score_{force_sfx}") else "inflation_score"
    d_col = f"disequilibrium_{diseq_sfx}" if diseq_sfx and _has_data(comp, f"disequilibrium_{diseq_sfx}") else "disequilibrium_score"

    # Derive quadrant from rolling scores when a force window is active
    if force_sfx and g_col != "growth_score":
        _RQ = {
            (True,  True):  "Inflationary Boom",
            (True,  False): "Expansion",
            (False, True):  "Stagflation",
            (False, False): "Disinflationary Slowdown",
        }
        def _roll_quadrant(row):
            g, i = row[g_col], row[i_col]
            if pd.isna(g) or pd.isna(i):
                return row.get("quadrant")
            return _RQ[(float(g) >= 0, float(i) >= 0)]
        quadrant_series = comp.apply(_roll_quadrant, axis=1)
    else:
        quadrant_series = comp["quadrant"]

    win_label = f" · rolling {zscore_window}mo" if (force_sfx and g_col != "growth_score") else ""
    diseq_label = f" · rolling {diseq_window}mo" if (diseq_sfx and d_col != "disequilibrium_score") else ""

    fig = make_subplots(
        rows=7, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.16, 0.18, 0.10, 0.18, 0.10, 0.14, 0.14],
        subplot_titles=[
            "Regime Quadrant",
            f"Growth Force Z-Score (composite{win_label})",
            "Growth Momentum (fraction of signals growth-positive)",
            f"Inflation Force Z-Score (composite{win_label})",
            "Inflation Momentum (fraction of signals inflation-positive)",
            "Confidence (direction-agreement across signals)",
            f"Disequilibrium Score (mean distance from equilibrium{diseq_label})",
        ],
    )

    # Row 1: Quadrant as colour-coded scatter
    quadrant_map = {
        "Expansion": 1,
        "Inflationary Boom": 2,
        "Stagflation": 3,
        "Disinflationary Slowdown": 0,
    }
    q_numeric = quadrant_series.map(quadrant_map).fillna(-1)
    fig.add_trace(
        go.Scatter(
            x=comp["as_of"],
            y=q_numeric,
            mode="markers",
            name="Quadrant",
            marker={
                "color": [_QUADRANT_COLOR.get(q, "#888") for q in quadrant_series],
                "size": 5,
            },
            hovertemplate="%{x|%Y-%m-%d}<br>%{customdata}<extra></extra>",
            customdata=quadrant_series,
            showlegend=False,
        ),
        row=1, col=1,
    )
    fig.update_yaxes(
        tickvals=[0, 1, 2, 3],
        ticktext=["Dis.Slow", "Expansion", "Inf.Boom", "Stagflation"],
        row=1, col=1,
    )

    # Row 2: Growth score (rolling or full-history)
    fig.add_trace(
        go.Scatter(
            x=comp["as_of"], y=comp[g_col],
            name="Growth Score",
            line={"color": _COLORS[0], "width": 1.5},
            hovertemplate="%{x|%Y-%m-%d}<br>Growth Force Z: %{y:.2f}<extra></extra>",
            fill="tozeroy",
            fillcolor="rgba(76, 155, 232, 0.15)",
        ),
        row=2, col=1,
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=2, col=1)

    # Row 3: Growth momentum
    if "growth_momentum" in comp.columns:
        fig.add_trace(
            go.Scatter(
                x=comp["as_of"], y=comp["growth_momentum"],
                name="Growth Momentum",
                line={"color": _COLORS[0], "width": 1.5, "dash": "dot"},
                hovertemplate="%{x|%Y-%m-%d}<br>Growth Momentum: %{y:.0%}<extra></extra>",
                fill="tozeroy",
                fillcolor="rgba(76, 155, 232, 0.10)",
            ),
            row=3, col=1,
        )
    fig.add_hline(y=0.5, line_dash="dot", line_color="#555", row=3, col=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1], row=3, col=1)

    # Row 4: Inflation score
    fig.add_trace(
        go.Scatter(
            x=comp["as_of"], y=comp[i_col],
            name="Inflation Score",
            line={"color": _INFLATION_COLOR, "width": 1.5},
            hovertemplate="%{x|%Y-%m-%d}<br>Inflation Force Z: %{y:.2f}<extra></extra>",
            fill="tozeroy",
            fillcolor="rgba(232, 115, 76, 0.15)",
        ),
        row=4, col=1,
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=4, col=1)

    # Row 5: Inflation momentum
    if "inflation_momentum" in comp.columns:
        fig.add_trace(
            go.Scatter(
                x=comp["as_of"], y=comp["inflation_momentum"],
                name="Inflation Momentum",
                line={"color": _INFLATION_COLOR, "width": 1.5, "dash": "dot"},
                hovertemplate="%{x|%Y-%m-%d}<br>Inflation Momentum: %{y:.0%}<extra></extra>",
                fill="tozeroy",
                fillcolor="rgba(232, 115, 76, 0.10)",
            ),
            row=5, col=1,
        )
    fig.add_hline(y=0.5, line_dash="dot", line_color="#555", row=5, col=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1], row=5, col=1)

    # Row 6: Confidence
    if "confidence" in comp.columns:
        fig.add_trace(
            go.Scatter(
                x=comp["as_of"], y=comp["confidence"],
                name="Confidence",
                line={"color": _COLORS[4], "width": 1.5},
                hovertemplate="%{x|%Y-%m-%d}<br>Confidence: %{y:.0%}<extra></extra>",
                fill="tozeroy",
                fillcolor="rgba(176, 127, 212, 0.15)",
            ),
            row=6, col=1,
        )
    fig.add_hline(y=0.5, line_dash="dot", line_color="#555", row=6, col=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1], row=6, col=1)

    # Row 7: Disequilibrium (rolling or full-history)
    if d_col in comp.columns:
        fig.add_trace(
            go.Scatter(
                x=comp["as_of"], y=comp[d_col],
                name="Disequilibrium",
                line={"color": _COLORS[1], "width": 1.5},
                hovertemplate="%{x|%Y-%m-%d}<br>Disequilibrium: %{y:.3f}<extra></extra>",
                fill="tozeroy",
                fillcolor="rgba(244, 200, 66, 0.12)",
            ),
            row=7, col=1,
        )

    fig.update_layout(
        **figure_layout(theme_name),
        hovermode="x",
        hoversubplots="axis",
        hoverlabel={
            "bgcolor": "#000000",
            "bordercolor": "#000000",
            "font": {"color": "#ffffff"},
        },
        showlegend=False,
        uirevision="regime-history",  # constant → Plotly.react() preserves user zoom
    )
    fig.update_layout(margin={"l": 55, "r": 20, "t": 30, "b": 40})
    fig.update_xaxes(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikethickness=1,
        spikecolor="rgba(180,180,180,0.6)",
    )

    # ── Step-selection highlight ──────────────────────────────────────────────
    step = step or 0
    n = len(comp)
    sel_idx = max(0, min(n - 1 - step, n - 1))
    sel = comp.iloc[sel_idx]
    sel_ts = sel["as_of"]

    # Vertical dashed guide line spanning all subplots
    fig.add_vline(
        x=sel_ts,
        line_dash="dot",
        line_color="rgba(255,255,255,0.35)",
        line_width=1.5,
    )

    # Highlighted marker — quadrant row (row 1), open circle in quadrant colour
    q_val = q_numeric.iloc[sel_idx] if sel_idx < len(q_numeric) else None
    q_label = sel.get("quadrant")
    if q_val is not None and not pd.isna(q_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[q_val],
                mode="markers",
                marker={
                    "size": 14, "symbol": "circle-open",
                    "color": _QUADRANT_COLOR.get(q_label, "#888"),
                    "line": {"width": 2.5},
                },
                showlegend=False, hoverinfo="skip",
            ),
            row=1, col=1,
        )

    # Highlighted marker — growth score (row 2, rolling-aware)
    g_val = sel.get(g_col)
    if g_val is not None and not pd.isna(g_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[g_val],
                mode="markers",
                marker={"size": 11, "color": _COLORS[0],
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=2, col=1,
        )

    # Highlighted marker — growth momentum (row 3)
    gm_val = sel.get("growth_momentum")
    if gm_val is not None and not pd.isna(gm_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[gm_val],
                mode="markers",
                marker={"size": 9, "color": _COLORS[0],
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=3, col=1,
        )

    # Highlighted marker — inflation score (row 4, rolling-aware)
    i_val = sel.get(i_col)
    if i_val is not None and not pd.isna(i_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[i_val],
                mode="markers",
                marker={"size": 11, "color": _INFLATION_COLOR,
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=4, col=1,
        )

    # Highlighted marker — inflation momentum (row 5)
    im_val = sel.get("inflation_momentum")
    if im_val is not None and not pd.isna(im_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[im_val],
                mode="markers",
                marker={"size": 9, "color": _INFLATION_COLOR,
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=5, col=1,
        )

    # Highlighted marker — confidence (row 6)
    conf_val = sel.get("confidence")
    if conf_val is not None and not pd.isna(conf_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[conf_val],
                mode="markers",
                marker={"size": 9, "color": _COLORS[4],
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=6, col=1,
        )

    # Highlighted marker — disequilibrium (row 7, rolling-aware)
    diseq_val = sel.get(d_col)
    if diseq_val is not None and not pd.isna(diseq_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[diseq_val],
                mode="markers",
                marker={"size": 9, "color": _COLORS[1],
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=7, col=1,
        )

    return fig


# ── Regime History help panel — callbacks ─────────────────────────────────────

@callback(
    Output("rh-help-open", "data"),
    [Input("rh-help-toggle", "n_clicks"),
     Input("rh-help-close", "n_clicks")],
    State("rh-help-open", "data"),
    prevent_initial_call=True,
)
def _toggle_rh_help(_n1: int, _n2: int, is_open: bool) -> bool:
    return not bool(is_open)


@callback(
    Output("rh-help-panel", "style"),
    Input("rh-help-open", "data"),
    prevent_initial_call=False,
)
def _update_rh_help_panel_style(is_open: bool) -> dict:
    return {
        **_RH_HELP_PANEL_BASE_STYLE,
        "transform": "translateX(0)" if is_open else "translateX(100%)",
    }


# ── Regime Map scatter — callbacks ────────────────────────────────────────────

@callback(
    Output("scatter-date-display", "children"),
    [Input("regime-step-index", "data"),
     Input("date-range", "data"),
     Input("country-store", "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_scatter_date(step: int, date_range: dict, country: str = "US", _trigger: Any = None) -> str:
    step = step or 0
    country = str(country or "US")
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp = load_composite_history(start_date=start, end_date=end, country=country)
    if comp.empty:
        return "No data"
    n = len(comp)
    idx = max(0, min(n - 1 - step, n - 1))
    sel_date = comp.iloc[idx]["as_of"]
    all_comp = load_composite_history(country=country)
    is_current = (
        not all_comp.empty
        and pd.Timestamp(sel_date) == pd.Timestamp(all_comp.iloc[-1]["as_of"])
    )
    date_str = sel_date.strftime("%b %Y")
    return f"{date_str} · current" if is_current else f"{date_str} · {step} month{'s' if step != 1 else ''} ago"


@callback(
    Output("scatter-chart", "figure"),
    [Input("regime-step-index", "data"),
     Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("zscore-window-store", "data"),
     Input("country-store",       "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_scatter_chart(
    step: int,
    date_range: dict,
    theme_name: str,
    zscore_window: int = 0,
    country: str = "US",
    _trigger: Any = None,
) -> go.Figure:
    step = step or 0
    theme_name = theme_name or DEFAULT_THEME
    zscore_window = int(zscore_window or 0)
    country = str(country or "US")
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])

    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp_filtered = load_composite_history(start_date=start, end_date=end, country=country)
    comp_all = load_composite_history(country=country)

    # Resolve rolling columns — fall back to base when pre-computed rolling cols
    # are all-null (non-US countries don't get rolling composite passes).
    force_sfx = _FORCE_WINDOW_COL.get(zscore_window)
    def _has_rolling(df: pd.DataFrame, col: str) -> bool:
        return col in df.columns and df[col].notna().any()
    g_col = f"growth_score_{force_sfx}" if force_sfx and _has_rolling(comp_all, f"growth_score_{force_sfx}") else "growth_score"
    i_col = f"inflation_score_{force_sfx}" if force_sfx and _has_rolling(comp_all, f"inflation_score_{force_sfx}") else "inflation_score"

    fig = go.Figure()

    if comp_all.empty or comp_filtered.empty:
        fig.update_layout(**figure_layout(theme_name, "No composite data"))
        return fig

    # ── Handle partial coverage (one axis all-null) ──────────────────────────
    # When growth or inflation signals are all stale/absent, substitute 0 so
    # the chart renders; add an annotation explaining the gap.
    gx_raw = comp_all[g_col]
    iy_raw = comp_all[i_col]
    g_missing = gx_raw.isna().all()
    i_missing = iy_raw.isna().all()

    coverage_annotations: list[dict] = []
    if g_missing:
        comp_all = comp_all.copy()
        comp_filtered = comp_filtered.copy()
        comp_all[g_col] = 0.0
        comp_filtered[g_col] = 0.0
        coverage_annotations.append(dict(
            text="⚠ Growth signals unavailable — X-axis fixed at 0",
            xref="paper", yref="paper", x=0.01, y=0.01,
            showarrow=False, font=dict(size=10, color="#E8734C"),
            align="left",
        ))
    if i_missing:
        comp_all = comp_all.copy()
        comp_filtered = comp_filtered.copy()
        comp_all[i_col] = 0.0
        comp_filtered[i_col] = 0.0
        coverage_annotations.append(dict(
            text="⚠ Inflation signals unavailable — Y-axis fixed at 0",
            xref="paper", yref="paper", x=0.01, y=0.05,
            showarrow=False, font=dict(size=10, color="#E8734C"),
            align="left",
        ))

    # ── Compute data-driven axis range with 15% buffer ───────────────────────
    gx = comp_all[g_col].dropna()
    iy = comp_all[i_col].dropna()
    if not gx.empty and not iy.empty:
        gx_span = (gx.max() - gx.min()) or 1.0
        iy_span = (iy.max() - iy.min()) or 1.0
        buf = 0.15
        x_range = [gx.min() - buf * gx_span, gx.max() + buf * gx_span]
        y_range = [iy.min() - buf * iy_span, iy.max() + buf * iy_span]
        # Give a visible spread on a fixed-zero axis
        if g_missing:
            x_range = [-1.0, 1.0]
        if i_missing:
            y_range = [-1.0, 1.0]
    else:
        x_range, y_range = [-3.0, 3.0], [-3.0, 3.0]

    # ── Quadrant background rectangles (±100 so they always fill the viewport)
    quad_bg = [
        (0,    100, 0,    100, "Inflationary Boom",        "#F4C842"),
        (0,    100, -100, 0,   "Expansion",                "#5CBA8A"),
        (-100, 0,   0,    100, "Stagflation",              "#E8734C"),
        (-100, 0,   -100, 0,   "Disinflationary Slowdown", "#4C9BE8"),
    ]
    shapes = [
        dict(type="rect", xref="x", yref="y",
             x0=x0, x1=x1, y0=y0, y1=y1,
             fillcolor=color, opacity=0.09, line=dict(width=0), layer="below")
        for x0, x1, y0, y1, _label, color in quad_bg
    ]
    # Axis centre lines
    shapes += [
        dict(type="line", xref="x", yref="paper", x0=0, x1=0, y0=0, y1=1,
             line=dict(color="#555", width=1, dash="dot")),
        dict(type="line", xref="paper", yref="y", x0=0, x1=1, y0=0, y1=0,
             line=dict(color="#555", width=1, dash="dot")),
    ]

    # ── Resolve selected index in all-history ────────────────────────────────
    n_filtered = len(comp_filtered)
    sel_idx_f = max(0, min(n_filtered - 1 - step, n_filtered - 1))
    sel_date = pd.Timestamp(comp_filtered.iloc[sel_idx_f]["as_of"])

    all_ts = [pd.Timestamp(d) for d in comp_all["as_of"]]
    try:
        sel_idx_all = next(i for i, d in enumerate(all_ts) if d == sel_date)
    except StopIteration:
        sel_idx_all = len(comp_all) - 1

    # ── Derive quadrant for rolling columns ───────────────────────────────────
    def _quadrant_for(row):
        g, i = row.get(g_col), row.get(i_col)
        if g is None or i is None or pd.isna(g) or pd.isna(i):
            return row.get("quadrant") or "—"
        return _RQ_MAP[(float(g) >= 0, float(i) >= 0)]

    eff_quadrant = comp_all.apply(_quadrant_for, axis=1)

    # ── All-history grey context dots ────────────────────────────────────────
    hist_dates = [str(d)[:7] for d in comp_all["as_of"]]
    fig.add_trace(go.Scatter(
        x=comp_all[g_col],
        y=comp_all[i_col],
        mode="markers",
        name="History",
        marker=dict(size=4, color=t["muted_color"], opacity=0.25),
        customdata=list(zip(hist_dates, eff_quadrant)),
        hovertemplate="%{customdata[0]}<br>Growth: %{x:.2f} · Inflation: %{y:.2f}<br>%{customdata[1]}<extra></extra>",
        showlegend=False,
    ))

    # ── 12-month trail up to and including the selected point ────────────────
    trail_start = max(0, sel_idx_all - 11)
    trail = comp_all.iloc[trail_start: sel_idx_all + 1]
    trail_q = eff_quadrant.iloc[trail_start: sel_idx_all + 1]
    n_trail = len(trail)

    if n_trail > 1:
        fig.add_trace(go.Scatter(
            x=trail[g_col],
            y=trail[i_col],
            mode="lines",
            line=dict(color="rgba(255,255,255,0.30)", width=1.5),
            showlegend=False,
            hoverinfo="skip",
        ))

    if n_trail > 0:
        trail_rgba = [
            _hex_to_rgba(_QUADRANT_COLOR.get(q, "#888"),
                         0.30 + (i + 1) / n_trail * 0.55)
            for i, q in enumerate(trail_q)
        ]
        trail_sizes = [5 + (i + 1) / n_trail * 5 for i in range(n_trail)]
        trail_dates = [str(d)[:7] for d in trail["as_of"]]
        fig.add_trace(go.Scatter(
            x=trail[g_col],
            y=trail[i_col],
            mode="markers",
            marker=dict(size=trail_sizes, color=trail_rgba),
            customdata=list(zip(trail_dates, trail_q)),
            hovertemplate="%{customdata[0]}<br>Growth: %{x:.2f} · Inflation: %{y:.2f}<br>%{customdata[1]}<extra></extra>",
            showlegend=False,
        ))

    # ── Selected point ────────────────────────────────────────────────────────
    sel = comp_all.iloc[sel_idx_all]
    sel_quadrant = eff_quadrant.iloc[sel_idx_all]
    sel_color = _QUADRANT_COLOR.get(sel_quadrant, "#888")
    sel_label = str(sel["as_of"])[:7]
    sel_g = sel.get(g_col)
    sel_i = sel.get(i_col)
    _g_str = f"{float(sel_g):.2f}" if sel_g is not None and not pd.isna(sel_g) else "—"
    _i_str = f"{float(sel_i):.2f}" if sel_i is not None and not pd.isna(sel_i) else "—"
    fig.add_trace(go.Scatter(
        x=[sel_g],
        y=[sel_i],
        mode="markers",
        marker=dict(size=18, color=sel_color, line=dict(width=2.5, color="#ffffff")),
        hovertemplate=f"{sel_label}<br>Growth: {_g_str}<br>Inflation: {_i_str}<br>{sel_quadrant}<extra></extra>",
        showlegend=False,
    ))

    # ── Quadrant corner labels (paper-coord: stay in corners at any zoom) ────
    q_annotations = [
        dict(text="Inflationary Boom",       x=0.98, y=0.98, xanchor="right",  yanchor="top"),
        dict(text="Expansion",               x=0.98, y=0.02, xanchor="right",  yanchor="bottom"),
        dict(text="Stagflation",             x=0.02, y=0.98, xanchor="left",   yanchor="top"),
        dict(text="Disinflationary Slowdown",x=0.02, y=0.02, xanchor="left",   yanchor="bottom"),
    ]
    q_colors = ["#F4C842", "#5CBA8A", "#E8734C", "#4C9BE8"]
    annotations = [
        dict(xref="paper", yref="paper", showarrow=False,
             font=dict(color=color, size=10, family="monospace"),
             bgcolor="rgba(0,0,0,0)", **ann)
        for ann, color in zip(q_annotations, q_colors)
    ]

    _win_sfx = f" ({zscore_window}mo)" if (force_sfx and g_col != "growth_score") else ""
    layout = figure_layout(theme_name)
    layout.update(dict(
        xaxis=dict(title=f"Growth Force Z-Score{_win_sfx}", range=x_range,
                   zeroline=False, gridcolor=t["grid_color"], showgrid=True),
        yaxis=dict(title=f"Inflation Force Z-Score{_win_sfx}", range=y_range,
                   zeroline=False, gridcolor=t["grid_color"], showgrid=True),
        shapes=shapes,
        annotations=annotations + coverage_annotations,
        hovermode="closest",
        showlegend=False,
        uirevision="scatter-map",  # constant → Plotly.react() preserves user zoom
        margin=dict(l=60, r=20, t=20, b=50),
    ))
    fig.update_layout(**layout)
    return fig


# ── Regime Map below-map panels callback ─────────────────────────────────────

@callback(
    [Output("what-changed",    "children"),
     Output("conflicts-panel", "children"),
     Output("lens-drilldowns", "children"),
     Output("data-quality-log","children")],
    [Input("regime-step-index", "data"),
     Input("date-range", "data"),
     Input("page-trigger", "data"),
     Input("country-store", "data")],
    prevent_initial_call=False,
)
def update_regime_map_panels(
    step: int,
    date_range: dict,
    _trigger: Any = None,
    country: str = "US",
) -> tuple:
    country = str(country or "US")
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp = load_composite_history(start_date=start, end_date=end, country=country)
    if comp.empty:
        selected_as_of = end
    else:
        idx = max(0, min(len(comp) - 1 - (step or 0), len(comp) - 1))
        selected_as_of = pd.Timestamp(comp.iloc[idx]["as_of"]).date().isoformat()

    latest_signals = load_latest_signals(country, as_of=selected_as_of)
    change_feed = load_change_feed(country, as_of=selected_as_of)

    # ── What Changed ─────────────────────────────────────────────────────────
    wc_children = _what_changed_children(change_feed)

    # ── Conflicts ─────────────────────────────────────────────────────────────
    cf_children = _conflicts_children(latest_signals) if not latest_signals.empty else [
        html.Span("No signal data.", style={"color": "#888", "fontSize": "0.85em"})
    ]

    # ── Lens Drill-Downs ──────────────────────────────────────────────────────
    histories_df = load_all_signal_histories(country, as_of=selected_as_of)
    histories_by_id: dict[str, list[float]] = {}
    if not histories_df.empty:
        for sid, grp in histories_df.groupby("id"):
            histories_by_id[str(sid)] = grp.sort_values("as_of")["value"].tolist()

    accordion_items = []
    for lens_label, forces in _LENS_GROUPS:
        if latest_signals.empty:
            lens_df = pd.DataFrame()
        else:
            lens_df = latest_signals[latest_signals["force"].isin(forces)].copy()
        n_sigs  = len(lens_df)
        n_stale = int(lens_df["is_stale"].sum()) if n_sigs else 0
        stale_txt = f"  ·  {n_stale} stale" if n_stale else ""
        title_str = f"{lens_label}  ({n_sigs} signals){stale_txt}"
        about = _LENS_ABOUT.get(lens_label, "")
        body_children: list = []
        if about:
            body_children.append(html.Div(about, style={
                "fontSize": "0.83em", "color": "#888",
                "padding": "4px 0 10px 0", "borderBottom": "1px solid #222",
                "marginBottom": "10px",
            }))
        body_children.append(_build_lens_table(lens_df, histories_by_id))
        accordion_items.append(
            dbc.AccordionItem(
                html.Div(body_children),
                title=title_str,
                item_id=f"lens-{lens_label[:8].strip()}",
            )
        )
    lens_children = [
        dbc.Accordion(
            accordion_items,
            start_collapsed=True,
            always_open=False,
        )
    ]

    # ── Data Quality Log ──────────────────────────────────────────────────────
    issues: list[dict] = []
    if not latest_signals.empty:
        for _, row in latest_signals.iterrows():
            sid = str(row["id"])
            if row.get("is_stale"):
                issues.append({"Signal": sid, "Issue": "stale",       "Note": "Not updated within expected release window"})
            if row.get("is_proxy"):
                issues.append({"Signal": sid, "Issue": "proxy",       "Note": "Not the primary statistical release"})
            if row.get("low_history"):
                issues.append({"Signal": sid, "Issue": "low history", "Note": "< 15 observations — Z-score unreliable"})
            if not row.get("vintage_available", True):
                issues.append({"Signal": sid, "Issue": "no vintage",  "Note": "Latest-revised only; no point-in-time data"})
    if issues:
        dql_children = [
            dash_table.DataTable(
                data=issues,
                columns=[{"name": c, "id": c} for c in ["Signal", "Issue", "Note"]],
                style_table={"overflowX": "auto"},
                style_cell={"fontSize": "0.85em", "textAlign": "left",
                             "backgroundColor": "var(--card-bg)", "color": "var(--font-color)"},
                style_header={"fontWeight": "600", "borderBottom": "1px solid #444"},
                page_size=20,
            )
        ]
    else:
        dql_children = [html.Span("No data-quality issues detected.",
                                  style={"color": "#5CBA8A", "fontSize": "0.88em"})]

    return wc_children, cf_children, lens_children, dql_children


# ── Debt Stress — helpers + callbacks ────────────────────────────────────────

_DEBT_STRESS_COMPONENTS = [
    ("z_gov_household_debt_gdp",   "Govt+HH Debt/GDP",      "positive"),
    ("z_corporate_debt_gdp",       "Corporate Debt/GDP",    "positive"),
    ("z_household_debt_service",   "HH Debt-Service Ratio", "positive"),
    ("z_federal_interest_gdp",     "Fed Interest/GDP",      "positive"),
    ("z_primary_balance_gdp",      "Primary Balance/GDP",   "negative"),
    ("z_structural_balance",       "Structural Balance",    "negative"),
    ("z_govt_revenue_gdp",         "Govt Revenue/GDP",      "negative"),
]

_STRESS_BAND_COLORS = {
    "Below-normal stress":  "#4C9BE8",
    "Near historical norm": "#aaaaaa",
    "Elevated stress":      "#F4C842",
    "High relative stress": "#E8734C",
}


def _stress_band(score: float) -> tuple[str, str]:
    """Return (label, color) for a stress score using spec-default thresholds."""
    try:
        from indicators.longterm_stress import load_longterm_stress_config, stress_band_label
        _cfg = load_longterm_stress_config()
        label = stress_band_label(score, _cfg["bands"])
    except Exception:
        if score < -0.5:
            label = "Below-normal stress"
        elif score < 0.5:
            label = "Near historical norm"
        elif score < 1.0:
            label = "Elevated stress"
        else:
            label = "High relative stress"
    return label, _STRESS_BAND_COLORS.get(label, "#888")


def _parse_stress_components(raw: str) -> dict[str, int]:
    """Parse 'cid:lag_q,cid2:lag_q2' → {cid: lag_q}. Back-compat with plain 'cid' (lag=1)."""
    result: dict[str, int] = {}
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            cid, lag = item.split(":", 1)
            result[cid.strip()] = int(lag)
        else:
            result[item] = 1
    return result


def _fmt_period(ts: pd.Timestamp, freq: str) -> str:
    """Format a timestamp as 'YYYY-Qn' (quarterly) or 'YYYY' (annual)."""
    if freq == "Q":
        q = (ts.month - 1) // 3 + 1
        return f"{ts.year}-Q{q}"
    return str(ts.year)


def _carry_expires(last_obs: pd.Timestamp, freq: str, max_carry_q: int) -> str:
    """Return a human label for the quarter when the carry-forward expires."""
    last_q = last_obs.to_period("Q")
    carry_end = last_q + max_carry_q
    return f"{carry_end.year}-Q{carry_end.quarter}"


def _build_debt_stress_info(
    ds_latest: pd.Series | None,
    theme_name: str,
    component_dates: dict[str, Any] | None = None,
) -> list:
    """Build the full-width top-panel children for the Debt Stress tab."""
    muted = {"color": "var(--muted-color)"}

    if ds_latest is None or ds_latest.empty:
        return [html.Div("No debt stress data — run pipeline.", style=muted)]

    # ── Load stress config for weights, frequencies, carry cap ────────────────
    try:
        from indicators.longterm_stress import load_longterm_stress_config
        stress_cfg = load_longterm_stress_config()
        comp_cfg_list = stress_cfg.get("components", [])
        stale_cfg     = stress_cfg.get("staleness", {})
        max_carry_q   = int(stale_cfg.get("max_carry_quarters", 4))
        halflife      = stale_cfg.get("stale_weight_halflife")
        min_frac      = float(stale_cfg.get("stale_min_weight_fraction", 0.20))
        expected_lags = stale_cfg.get("expected_lag_quarters", {"Q": 1, "A": 4})
        extrap_on     = bool(stale_cfg.get("extrapolation", {}).get("enabled", False))
    except Exception:
        comp_cfg_list, max_carry_q, halflife, min_frac, expected_lags, extrap_on = [], 4, None, 0.20, {"Q": 1, "A": 4}, False

    comp_cfg_by_id = {c["id"]: c for c in comp_cfg_list}

    score   = ds_latest.get("stress_score")
    n_comp  = int(ds_latest.get("n_components", 0))
    ret_wt  = ds_latest.get("retained_weight")
    low_cov = bool(ds_latest.get("low_coverage", False))
    stale_dict  = _parse_stress_components(ds_latest.get("stale_components") or "")
    extrap_dict = _parse_stress_components(ds_latest.get("extrapolated_components") or "")
    as_of_ts = ds_latest.get("as_of")
    try:
        as_of_ts_p = pd.Timestamp(as_of_ts)
        as_of_str  = as_of_ts_p.strftime("%b %Y")
    except Exception:
        as_of_ts_p = None
        as_of_str  = str(as_of_ts)[:7]

    if score is not None and not (isinstance(score, float) and pd.isna(score)):
        band_label, band_color = _stress_band(float(score))
        score_display = f"{score:+.2f}"
    else:
        band_label, band_color = ("⚠ low coverage" if low_cov else "No data"), "#888"
        score_display = "—"

    ret_str = f"{ret_wt * 100:.0f}%" if (ret_wt is not None and not pd.isna(ret_wt)) else "—"

    # ── Score summary strip ────────────────────────────────────────────────────
    summary_strip = html.Div(
        style={
            "display": "flex", "alignItems": "baseline", "gap": "20px",
            "marginBottom": "14px", "flexWrap": "wrap",
        },
        children=[
            html.Div([
                html.Span(
                    "DEBT STRESS",
                    style={"fontSize": "0.65rem", "color": "var(--muted-color)",
                           "textTransform": "uppercase", "letterSpacing": "0.08em",
                           "marginRight": "6px"},
                ),
                html.Span(
                    f"as of {as_of_str}",
                    style={"fontSize": "0.65rem", "color": "var(--muted-color)"},
                ),
            ]),
            html.Span(
                score_display,
                style={"fontSize": "2.2rem", "fontWeight": "700", "color": band_color,
                       "fontFamily": "monospace", "lineHeight": "1.0"},
            ),
            html.Span(
                band_label,
                style={"fontSize": "0.88rem", "color": band_color, "opacity": "0.85"},
            ),
            html.Span(
                f"{n_comp}/{len(comp_cfg_list) or len(_DEBT_STRESS_COMPONENTS)} components active",
                style={"fontSize": "0.75rem", "color": "var(--muted-color)"},
            ),
            html.Span(
                f"retained weight: {ret_str}",
                style={"fontSize": "0.75rem", "color": "var(--muted-color)"},
            ),
            *(
                [html.Span("⚠ LOW COVERAGE",
                           style={"fontSize": "0.75rem", "color": "#E8734C",
                                  "fontWeight": "600"})]
                if low_cov else []
            ),
        ],
    )

    # ── Component detail table ─────────────────────────────────────────────────
    th_sty = {
        "textAlign": "left", "padding": "5px 10px",
        "fontSize": "0.68rem", "textTransform": "uppercase",
        "letterSpacing": "0.06em", "color": "var(--muted-color)",
        "borderBottom": "1px solid var(--border-color)",
        "whiteSpace": "nowrap",
    }
    td_sty = {
        "padding": "6px 10px", "fontSize": "0.82rem",
        "borderBottom": "1px solid var(--border-color)",
        "color": "var(--font-color)", "verticalAlign": "middle",
    }
    td_mono = {**td_sty, "fontFamily": "monospace"}

    header_row = html.Tr([
        html.Th("Component",        style=th_sty),
        html.Th("Freq",             style={**th_sty, "textAlign": "center"}),
        html.Th("Config Wt",        style={**th_sty, "textAlign": "center"}),
        html.Th("Eff Wt",           style={**th_sty, "textAlign": "center"}),
        html.Th("Last Data",        style={**th_sty, "textAlign": "center"}),
        html.Th("Z-Score",          style={**th_sty, "textAlign": "right"}),
        html.Th("Status / Detail",  style=th_sty),
    ])

    rows = []
    for col, label, direction in _DEBT_STRESS_COMPONENTS:
        cid   = col.replace("z_", "")
        z     = ds_latest.get(col)
        val   = ds_latest.get(f"val_{cid}")
        cfg   = comp_cfg_by_id.get(cid, {})
        freq  = cfg.get("frequency", "Q")
        config_wt = float(cfg.get("weight", 0.0))
        lag_q    = stale_dict.get(cid, 0)
        extrap_q = extrap_dict.get(cid, 0)
        z_missing = z is None or (isinstance(z, float) and pd.isna(z))
        bar_color = "#E8734C" if direction == "positive" else "#4C9BE8"

        # ── Last data cell ───────────────────────────────────────────────────
        last_obs: pd.Timestamp | None = (component_dates or {}).get(cid)
        if last_obs is not None:
            last_data_str = _fmt_period(last_obs, freq)
        elif not z_missing:
            last_data_str = "active (derived)"
        else:
            last_data_str = "derived"

        # ── Effective weight ─────────────────────────────────────────────────
        if z_missing and extrap_q == 0:
            eff_wt = 0.0
        elif halflife and halflife > 0 and (lag_q > 0 or extrap_q > 0):
            from indicators.longterm_stress import staleness_weight_fraction
            decay = staleness_weight_fraction(max(lag_q, extrap_q), halflife)
            eff_wt = config_wt * decay
            if eff_wt < min_frac * config_wt:
                eff_wt = 0.0
        else:
            eff_wt = config_wt if not z_missing else 0.0

        config_wt_str = f"{config_wt * 100:.0f}%"
        eff_wt_str    = f"{eff_wt * 100:.0f}%"
        eff_wt_color  = (
            "var(--font-color)" if eff_wt == config_wt
            else ("#E8734C" if eff_wt == 0 else "#F4C842")
        )

        # ── Z-score cell ─────────────────────────────────────────────────────
        if z_missing:
            z_cell = html.Td("—", style={**td_mono, "color": "#555", "textAlign": "right"})
        else:
            bar_w = min(abs(float(z)) / 2.5 * 80, 80)
            z_cell = html.Td(
                html.Div(
                    style={"display": "flex", "alignItems": "center",
                           "justifyContent": "flex-end", "gap": "6px"},
                    children=[
                        html.Div(style={
                            "width": f"{bar_w:.0f}px", "height": "6px",
                            "backgroundColor": bar_color, "borderRadius": "2px",
                            "opacity": "0.65", "flexShrink": "0",
                        }),
                        html.Span(f"{float(z):+.2f}",
                                  style={"color": bar_color, "fontFamily": "monospace",
                                         "fontSize": "0.82rem"}),
                    ],
                ),
                style={**td_sty, "textAlign": "right"},
            )

        # ── Status / Detail cell ──────────────────────────────────────────────
        if extrap_q > 0:
            status_badge = html.Span(
                f"EXTRAPOLATED · {extrap_q}q stale",
                style={"background": "#2a3a5a", "color": "#88aadd",
                       "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.72rem"},
            )
            if last_obs is not None:
                detail_text = f" · last: {_fmt_period(last_obs, freq)}"
            else:
                detail_text = ""
            status_cell_children: list = [status_badge, html.Span(detail_text, style={"color": "var(--muted-color)", "fontSize": "0.75rem"})]

        elif lag_q > 0:
            status_badge = html.Span(
                f"STALE · {lag_q}q excess",
                style={"background": "#7a4a00", "color": "#ffcc80",
                       "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.72rem"},
            )
            if last_obs is not None:
                detail_text = f" · last: {_fmt_period(last_obs, freq)} · active with decay"
            else:
                detail_text = " · active with decay"
            status_cell_children = [status_badge, html.Span(detail_text, style={"color": "var(--muted-color)", "fontSize": "0.75rem"})]

        elif z_missing:
            # Blank — explain why
            if last_obs is not None and as_of_ts_p is not None:
                total_lag = max(0, as_of_ts_p.to_period("Q").ordinal - last_obs.to_period("Q").ordinal)
                expected  = int(expected_lags.get(freq, 1))
                excess    = max(0, total_lag - expected)
                carry_end = _carry_expires(last_obs, freq, max_carry_q)
                reason = (
                    f"carry expired · last data: {_fmt_period(last_obs, freq)} · "
                    f"carry cap {max_carry_q}q → covered to {carry_end}"
                )
                if extrap_on:
                    reason += f" · total lag {total_lag}q ≤ carry cap (no extrap trigger)"
                else:
                    reason += " · extrapolation disabled"
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    reason += f" · last known value: {float(val):.2f}"
            else:
                reason = "derived series · insufficient data for Z-score"
            status_badge = html.Span(
                "BLANK",
                style={"background": "#3a2020", "color": "#cc7777",
                       "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.72rem"},
            )
            status_cell_children = [
                status_badge,
                html.Span(f" {reason}", style={"color": "var(--muted-color)", "fontSize": "0.75rem"}),
            ]

        else:
            status_badge = html.Span(
                "ACTIVE",
                style={"background": "#1a3a1a", "color": "#88cc88",
                       "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.72rem"},
            )
            status_cell_children = [status_badge]

        row_bg = "rgba(60,20,20,0.15)" if z_missing else "transparent"
        rows.append(html.Tr(
            style={"backgroundColor": row_bg},
            children=[
                html.Td(label, style=td_sty),
                html.Td(
                    "Annual" if freq == "A" else "Quarterly",
                    style={**td_sty, "textAlign": "center",
                           "color": "var(--muted-color)", "fontSize": "0.75rem"},
                ),
                html.Td(config_wt_str, style={**td_mono, "textAlign": "center"}),
                html.Td(
                    eff_wt_str,
                    style={**td_mono, "textAlign": "center", "color": eff_wt_color,
                           "fontWeight": "600" if eff_wt < config_wt else "400"},
                ),
                html.Td(last_data_str, style={**td_mono, "textAlign": "center",
                                              "color": "var(--muted-color)", "fontSize": "0.75rem"}),
                z_cell,
                html.Td(status_cell_children, style=td_sty),
            ],
        ))

    table = html.Table(
        [html.Thead(header_row), html.Tbody(rows)],
        style={"width": "100%", "borderCollapse": "collapse"},
    )

    footer = html.Div(
        "⚠ Bands are NOT validated risk thresholds · Eff Wt applies exponential staleness decay (half-life "
        + (f"{int(halflife)}q" if halflife else "off") + f") · carry cap {max_carry_q}q",
        style={"fontSize": "0.65rem", "color": "#555", "marginTop": "10px"},
    )

    return [summary_strip, table, footer]


@callback(
    Output("debt-stress-info-box", "children"),
    [Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("country-store", "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_debt_stress_info(date_range: dict, theme_name: str, country: str = "US", _trigger: Any = None) -> list:
    country = (country or "US").upper()
    if country != "US":
        return [html.Div(
            f"Long-Term Debt Stress model is US-only — component series (household debt, "
            f"corporate debt, federal deficit, interest payments) are FRED-sourced US data. "
            f"A {country}-equivalent composite is pending research.",
            style={"color": "var(--muted-color)", "fontSize": "0.85rem", "padding": "20px 0"},
        )]
    end = (date_range or {}).get("end")
    df = load_debt_stress_history(country="US", end_date=end)
    latest = df.iloc[-1] if not df.empty else None
    comp_dates = load_debt_stress_component_dates(
        country="US", as_of=str(latest.get("as_of")) if latest is not None else end
    )
    return _build_debt_stress_info(latest, theme_name or DEFAULT_THEME, comp_dates)


@callback(
    Output("debt-stress-chart", "figure"),
    [Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("country-store", "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_debt_stress_chart(
    date_range: dict,
    theme_name: str = DEFAULT_THEME,
    country: str = "US",
    _trigger: Any = None,
) -> go.Figure:
    country = (country or "US").upper()
    theme_name = theme_name or DEFAULT_THEME
    if country != "US":
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, f"Debt Stress — US-only model  ·  {country} not yet available"))
        return fig
    start = (date_range or {}).get("start")
    end   = (date_range or {}).get("end")
    df = load_debt_stress_history(country="US", start_date=start, end_date=end)

    if df.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No debt stress data"))
        return fig

    comp_labels = [lbl for _, lbl, _ in _DEBT_STRESS_COMPONENTS]
    comp_cols   = [col for col, _, _ in _DEBT_STRESS_COMPONENTS]
    comp_dirs   = [d   for _, _, d   in _DEBT_STRESS_COMPONENTS]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.45, 0.55],
        subplot_titles=["Composite Stress Score", "Component Z-Scores"],
    )

    # ── Row 1: composite score + band shading ────────────────────────────────
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=1, col=1)
    fig.add_hrect(y0=0.5,  y1=3.5,  fillcolor="rgba(232,115,76,0.07)",  line_width=0, row=1, col=1)
    fig.add_hrect(y0=1.0,  y1=3.5,  fillcolor="rgba(232,115,76,0.07)",  line_width=0, row=1, col=1)
    fig.add_hrect(y0=-3.5, y1=-0.5, fillcolor="rgba(76,155,232,0.07)",  line_width=0, row=1, col=1)

    # Mask low-coverage points
    score_col = df["stress_score"].where(~df["low_coverage"].fillna(False))
    fig.add_trace(
        go.Scatter(
            x=df["as_of"], y=score_col,
            name="Stress Score",
            line={"color": "#E8734C", "width": 2},
            fill="tozeroy",
            fillcolor="rgba(232,115,76,0.12)",
            hovertemplate="%{x|%Y-Q%q}<br>Score: %{y:.2f}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Low-coverage gaps as grey dots
    low_cov = df[df["low_coverage"].fillna(False)]
    if not low_cov.empty:
        fig.add_trace(
            go.Scatter(
                x=low_cov["as_of"], y=[0] * len(low_cov),
                mode="markers",
                marker={"color": "#555", "size": 5, "symbol": "x"},
                name="Low coverage",
                hovertemplate="%{x|%Y-Q%q}<br>Low coverage<extra></extra>",
            ),
            row=1, col=1,
        )

    # ── Row 2: per-component Z-scores ────────────────────────────────────────
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=2, col=1)
    for i, (col, label, direction) in enumerate(zip(comp_cols, comp_labels, comp_dirs)):
        if col not in df.columns:
            continue
        color = _COLORS[i % len(_COLORS)]
        # Negate negative-direction components for visual: displayed as "stress contribution"
        z_series = df[col] if direction == "positive" else -df[col]
        fig.add_trace(
            go.Scatter(
                x=df["as_of"], y=z_series,
                name=label,
                line={"color": color, "width": 1.2},
                hovertemplate=f"%{{x|%Y-Q%q}}<br>{label}: %{{y:.2f}}<extra></extra>",
            ),
            row=2, col=1,
        )

    fig.update_yaxes(title_text="Z-Score", row=1, col=1)
    fig.update_yaxes(title_text="Z-Score (stress dir.)", row=2, col=1)
    fig.update_layout(**figure_layout(theme_name), hovermode="x unified", uirevision="debt-stress")
    fig.update_layout(
        margin={"l": 55, "r": 20, "t": 30, "b": 60},
        legend={"orientation": "h", "y": -0.15, "x": 0},
    )
    return fig


# ── Layout helper (kept for backward compatibility with tests) ─────────────────

def _dark_layout(title: str = "") -> dict:
    return figure_layout(DEFAULT_THEME, title)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("CHARTING_PORT", 8502))
    debug = os.environ.get("DASH_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

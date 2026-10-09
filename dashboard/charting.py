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
from dash import ALL, Input, Output, State, callback, ctx, dash_table, dcc, html, no_update
from dash.exceptions import PreventUpdate
from plotly.subplots import make_subplots

from dashboard.charting_data import (
    align_as_of,
    load_all_signal_histories,
    load_change_feed,
    load_composite_component_status,
    load_composite_history,
    load_composite_signal_values,
    load_debt_cycle_stage_history,
    load_debt_stress_component_dates,
    load_debt_stress_history,
    load_latest_signals,
    load_series_catalog,
)
from dashboard.themes import DEFAULT_THEME, THEME_CSS_VARS, THEMES, figure_layout
from dashboard import data_dashboard as _data_dashboard
from dashboard import global_overview as _global_overview
from dashboard import methodology as _methodology
from dashboard import weight_audit as _weight_audit
from dashboard import weight_history as _weight_history
from dashboard import signals_page as _signals_page
from dashboard import force_detail as _force_detail
from dashboard import command_center as _command_center
from dashboard import relative_view as _relative_view
from dashboard import workbench as _workbench
from dashboard import fed_monitor as _fed_monitor
from dashboard import case_study_monitor as _case_study_monitor
from dashboard import market_expectations as _market_exp
from dashboard import validator_monitor as _validator_monitor
from dashboard import bubble_gauge_monitor as _bubble_gauge_monitor
from dashboard import ai_capex_monitor as _ai_capex_monitor
from dashboard import feedback as _feedback
from dashboard import user_guide as _user_guide
from dashboard import asset_environments as _asset_env
from dashboard import traffic as _traffic
from dashboard.shared_components import (
    AMBER, GREEN, RED, _chart_card, _concept_label, _section, _signal_link, _zscore_color,
)
from dashboard.app_mode import PUBLIC_MODE, OPERATOR_ONLY_ROUTES
from indicators import schedule_config as sched_cfg

# ── App setup ─────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    title="Economic Machine Dashboard",
    update_title=None,          # prevent "Updating..." tab flicker from poll interval
    suppress_callback_exceptions=True,
    # Render at real device width on phones (without this, mobile browsers fake a
    # ~980px viewport and shrink everything). Enables the @media rules in theme.css.
    meta_tags=[{"name": "viewport",
                "content": "width=device-width, initial-scale=1"}],
)
server = app.server  # expose Flask for Gunicorn / production

# ── Valuations page (operator-only) — served as a self-contained static app via
# gated Flask routes so it never appears on the public/cloud deploy. The HTML is
# the same artifact as standalone/buffett_valuations_dashboard.html; its data
# comes from DATA_DIR/buffett_data.json (pipeline Pass 8), falling back to the
# repo-bundled copy. In PUBLIC_MODE both routes 404 (nav + /valuations also gated).
_VAL_HTML = Path(__file__).resolve().parent.parent / "standalone" / "buffett_valuations_dashboard.html"


@server.route("/valuations/app")
def _valuations_app():
    import flask
    if PUBLIC_MODE or not _VAL_HTML.exists():
        flask.abort(404)
    return flask.send_file(str(_VAL_HTML))


@server.route("/valuations/buffett_data.json")
def _valuations_data():
    import flask
    from indicators.valuations import data_path
    if PUBLIC_MODE:
        flask.abort(404)
    p = data_path()
    if not p.exists():
        flask.abort(404)
    return flask.send_file(str(p), mimetype="application/json")


_data_dashboard.register_callbacks(app) # Data Feed Monitor sort + filter
_global_overview.register_callbacks(app) # Global Overview Cycle Health config
for _fd_force in _force_detail._FORCES:  # Force detail sub-pages (/signals/{force})
    _force_detail.register_callbacks(app, _fd_force)

# Workbench clientside hooks: "/" hotkey focuses the omnibox; the shared
# crosshair spike (same JS as the force-detail pages) syncs stacked panes.
app.clientside_callback(
    _workbench.HOTKEY_JS,
    Output("wb-hover-dummy", "data"),
    Input("page-trigger", "data"),
    prevent_initial_call=False,
)
app.clientside_callback(
    _force_detail._hover_sync_js("wb-chart", "wb-hover-dummy"),
    Output("wb-hover-dummy", "data", allow_duplicate=True),
    Input("wb-chart", "figure"),
    prevent_initial_call=True,
)

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
    "Transition — no clear season": "#888888",   # Ray Q2: inside the threshold band
}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:                       # expand shorthand (#888 → #888888)
        h = "".join(ch * 2 for ch in h)
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
    Nominal weights from config/countries/{cc}_composites.yaml are applied; no momentum tilts
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


def _stress_z_color(z: Any, direction: str) -> str:
    """Semantic color for a debt-stress component Z-score.

    Signs the Z by its stress direction, then maps:
      signed > 0  → stress-increasing → red gradient
      signed < 0  → stress-reducing   → green gradient
      near zero   → grey
    """
    if z is None or (isinstance(z, float) and _math.isnan(z)):
        return "#666"
    from dashboard.shared_components import _CLR_GREEN_HI, _CLR_GREEN_LO, _CLR_RED_HI, _CLR_RED_LO, _lerp_rgb
    signed = float(z) if direction == "positive" else -float(z)
    mag = min(abs(signed) / 3.0, 1.0)
    if mag < 0.05:
        return "#888"
    return (
        _lerp_rgb(mag, _CLR_RED_LO,   _CLR_RED_HI)   if signed > 0
        else _lerp_rgb(mag, _CLR_GREEN_LO, _CLR_GREEN_HI)
    )


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
                _signal_link(label, sid),
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

# ── Regime classification thresholds ─────────────────────────────────────────
# Defined ABOVE the layout on purpose: the regime-threshold-store's initial
# data is `dict(_DEFAULT_THRESHOLDS)`, so the two cannot drift apart. They used
# to be a hand-retyped literal and a constant, which drifted twice.
# Ray's dynamic thresholds are ON by default (his 7-step algorithm; backtest
# G2 found dynamic ≥ fixed). Users can still turn them off in the Regime
# Thresholds modal; an explicit choice (stored) is respected.
#
# gm/im raised 0.0 -> 0.05 (coverage-audit follow-up, 2026-10-03): a pure
# sign test on momentum lets a single noisy one-month wiggle flip the
# Growth/Retraction (or Inflation/Disinflation) label -- exactly the
# false-positive mode flagged in the user's own notes. Backtested against
# the US direction-validation scenarios (indicators/backtest.py,
# US_SCENARIOS) before changing: wrong-direction rate was IDENTICAL at
# 0.9% (1/115 months) for gm=im in {0.0, 0.05, 0.1} -- raising the gate
# costs nothing on known episodes. Label-flip frequency over the full PIT
# history dropped from 37.9%->22.6% of months for inflation at 0.05 (growth
# flips were unaffected at 0.05, needing 0.1 to move -- 0.05 is the value
# actually cited in the source note, so that's what shipped; 0.1 tested
# cleanly too and is a candidate if 0.05 proves too weak in practice).
# gm 0.05 -> 0.04 (2026-10-06): gm no longer GATES the growth chip, it is the
# accelerating/flat boundary of _growth_breadth_state. 0.04 is the value Ray
# specified and the one our own acceptance test clears (accelerating-vs-flat
# separation +0.39pp on forward realized GDP, inside his stated 0.3-0.5pp band).
# im stays 0.05: the gate still gates the inflation chip, where it earns its keep.
#
# THRESHOLD_STORE_VERSION — bump this whenever a DEFAULT above changes.
#
# The thresholds live in a localStorage dcc.Store, so a browser keeps whatever
# it last persisted forever. Before 2026-10-07 every read site did
# `stored or _DEFAULT_THRESHOLDS` (a whole-dict swap) and then `.get(key,
# <literal>)`, which meant a key PRESENT in an old stored dict beat the new
# default outright -- the fallback literal never fired. Two concrete
# regressions came out of that:
#   * a store written between 2026-06-25 and 2026-10-03 carries im=0.0, which
#     degenerates the inflation chip's momentum gate into a bare sign test (US
#     2026-10 read Disinflation off a -0.0023 drift instead of Transition);
#   * a store written before 2026-07-09 has no "dynamic" key at all, and the
#     per-file fallback literals disagreed -- charting.py said True while
#     command_center/user_guide/audit_benchmarks said False and relative_view
#     said None -- so one browser rendered dynamic and static chips side by
#     side off one dataset (the flag alone changes a US chip in 25% of months).
# Both are fixed by routing EVERY read through resolve_thresholds() below and
# deleting the per-file fallbacks. A stored dict stamped with an older version
# is treated as "never an explicit choice under the current rules" and resets
# to the defaults, which is what keeps dynamic mode on by default for everyone
# who has not deliberately turned it off SINCE this version.
def _inflation_tolerance_pp() -> float:
    """Half-width of the "At Target" band, in percentage points.

    The inflation chip's level gate (Ray 2026-10-03 Ruling 1). Uniform across
    countries on purpose — official tolerance bands vary from +/-0.5pp to
    +/-2pp, and using each country's own would make "Above Target" mean
    something different in every column of a cross-country dashboard. The
    official bands are recorded per country in the config for reference only.
    TUNABLE in config/inflation_anchor.yaml::bands.tolerance_pp.
    """
    try:
        from indicators.inflation_anchor import load_config
        return float(load_config()["bands"]["tolerance_pp"])
    except Exception:  # pragma: no cover - defensive
        return 0.5


_THRESHOLD_STORE_VERSION = 3

_DEFAULT_THRESHOLDS = {"gz": 0.5, "iz": 0.5, "gm": 0.04, "dynamic": True,
                       "conc_adj": False, "v": _THRESHOLD_STORE_VERSION}


def resolve_thresholds(stored: "dict | None") -> dict:
    """The thresholds actually in force, from a persisted store value.

    THE one place that answers "what are the thresholds". Never read a
    threshold key off a raw store value with its own `.get(key, literal)`
    fallback -- that is the drift this function exists to end. Callers get a
    complete dict, so `t["dynamic"]` is always safe.

    Rules:
      * not a dict, or stamped with a different version -> the current
        defaults. An old store is NOT a deliberate choice under today's rules,
        and silently honoring half of it is how a browser ends up running a
        retired classifier (see the comment above).
      * current version -> defaults with the stored values overlaid, so a
        deliberate choice (im=0.0 included) is respected exactly.
    """
    if not isinstance(stored, dict):
        return dict(_DEFAULT_THRESHOLDS)
    try:
        version = int(stored.get("v", 0) or 0)
    except (TypeError, ValueError):
        return dict(_DEFAULT_THRESHOLDS)
    if version != _THRESHOLD_STORE_VERSION:
        return dict(_DEFAULT_THRESHOLDS)
    # Drop nulls before overlaying. A stored explicit null is not a choice, and
    # letting it through would break this function's whole contract: callers
    # read t["dynamic"] / t["gz"] directly, where None silently means "static"
    # (bool(None) is False) or raises in float(). Nulls do reach here -- a
    # Dash clientside write, or a hand-edited localStorage value.
    return {**_DEFAULT_THRESHOLDS,
            **{k: v for k, v in stored.items() if v is not None}}


def thr(t: "dict | None", key: str):
    """One threshold value out of an ALREADY-RESOLVED dict.

    The division of labour, and the rule for any new code that touches
    thresholds:
      * resolve_thresholds() exactly once, at the boundary where a raw
        localStorage value enters (a callback argument, a function's public
        `thresholds=` parameter);
      * thr() everywhere downstream.

    Downstream dicts legitimately carry per-month dynamic gz/iz overrides and
    are often partial (internal callers and tests pass {"gz": .., "iz": ..}),
    so they must NOT be re-resolved -- that would throw the dynamic value away.
    What they must not do is re-type a default: a hand-typed `0.5` fallback is
    a second, invisible home for a value that is supposed to live in exactly
    one place, and that is how gm/im/dynamic drifted. A None value (an old
    store with an explicit null) also falls back, not propagates.
    """
    val = (t or {}).get(key, _DEFAULT_THRESHOLDS[key])
    return _DEFAULT_THRESHOLDS[key] if val is None else val


# ── Layout ────────────────────────────────────────────────────────────────────

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
# When a listed date has passed, the sidebar shows an amber "Update now" flag
# as a reminder to re-run the pipeline; remove entries once their data is
# ingested so the flag clears. (Q1 2026 current account / NIIP + June jobs
# ingested 2026-07-09.)
_UPCOMING_RELEASES: list[tuple[datetime.date, str]] = [
    (datetime.date(2026, 7, 30), "BEA Q2 2026 GDP advance"),
    (datetime.date(2026, 8, 7),  "BLS July jobs report"),
    (datetime.date(2026, 9, 24), "BEA Q2 2026 current account / NIIP"),
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


def _data_freshness_str() -> str:
    """When the signals DB was last written — a proxy for the last data refresh."""
    import datetime
    import os
    try:
        from dashboard.charting_data import DB_PATH
        dt = datetime.datetime.fromtimestamp(os.path.getmtime(DB_PATH))
        return dt.strftime("%b %-d, %Y · %-I:%M %p")
    except Exception:
        return "—"


# ── Per-page layout functions ─────────────────────────────────────────────────

def _left_nav() -> html.Div:
    """Collapsible vertical nav sidebar."""
    _sync = _sync_banner()
    _fb_btn = _feedback.nav_button()   # None when FEEDBACK_ENDPOINT is unset

    def _nl(icon: str, text: str, href: str, disabled: bool = False,
            nav_id: str | None = None) -> dbc.NavLink:
        return dbc.NavLink(
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

    def _group(header: str, links: list, *, icon: str = "",
               open_default: bool = False) -> html.Details:
        """A click-to-roll collapsible nav section (native <details>).

        State persists across client-side navigation. In the icon-rail
        (collapsed sidebar) CSS force-shows every group's links and hides the
        headers, so pages stay reachable regardless of open/closed state.
        """
        head = []
        if icon:
            head.append(html.Span(icon, className="nav-icon",
                                  style={"minWidth": "22px", "display": "inline-block",
                                         "textAlign": "center"}))
        head.append(html.Span(header, className="sidebar-text"))
        return html.Details([
            html.Summary([
                html.Span(head, style={"display": "flex", "alignItems": "center"}),
                html.Span("▸", className="nav-group-chev"),
            ], className="nav-group-header"),
            html.Div(dbc.Nav(links, vertical=True, pills=True),
                     className="nav-group-body"),
        ], open=open_default, className="nav-group mb-1")

    def _sm(v: int, lbl: str) -> dict:
        return {"label": lbl, "style": {"color": "var(--font-color)", "fontSize": "0.62rem"}}

    _country_options = [
        {"label": "🇺🇸 United States",          "value": "US"},
        {"label": "🇪🇺 Eurozone",               "value": "EZ"},
        {"label": "🇬🇧 United Kingdom",         "value": "GB"},
        {"label": "🇯🇵 Japan",                  "value": "JP"},
        {"label": "🇰🇷 South Korea",            "value": "KR"},
        {"label": "🇨🇳 China",                  "value": "CN"},
        {"label": "🇮🇳 India",                  "value": "IN"},
        {"label": "🇩🇪 Germany",                "value": "DE"},
        {"label": "🇱🇺 Luxembourg",             "value": "LU"},
        {"label": "🇧🇷 Brazil",              "value": "BR"},
        {"label": "🇨🇦 Canada",              "value": "CA"},
        {"label": "🇦🇺 Australia",           "value": "AU"},
        {"label": "🇲🇽 Mexico",              "value": "MX"},
        {"label": "🇮🇩 Indonesia",           "value": "ID"},
    ]

    return html.Div([
        # ── Header: title + collapse toggle ──────────────────────────────────
        html.Div([
            html.Span("Economic Machine", className="sidebar-text", style={
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

        # ── Data-freshness stamp (last DB write ≈ last data refresh) ──────────
        html.Div([
            html.Div("🕐 Data updated", style={
                "fontSize": "0.56rem", "fontWeight": "800", "letterSpacing": "0.07em",
                "textTransform": "uppercase", "color": "var(--muted-color)"}),
            html.Div(id="data-freshness", children=_data_freshness_str(), style={
                "fontSize": "0.7rem", "fontWeight": "600", "color": "var(--font-color)",
                "marginTop": "1px"}),
        ], id="data-freshness-block", className="sidebar-text",
           style={"padding": "7px 12px 8px 12px"}),

        # ── Nav groups ────────────────────────────────────────────────────────
        # Every group is a click-to-roll `_group()` as of 2026-10-06. Three of
        # them (Overviews / Regime & Cycles / Monitors) used to be fixed
        # `_label()` headings with an always-open dbc.Nav under them, which
        # made the sidebar read as two different kinds of section. Group
        # placement rules: docs/Guidance/dashboard_ia_framework.md.
        #
        # Overviews and Monitors open by default — the landing page and the
        # most-visited curated reads live there.
        _group("Overviews", [
            _nl("🎛", "Command Center", "/country", nav_id="navlnk-command-center"),
            _nl("🌐", "Overview", "/overview", nav_id="navlnk-overview"),
            _nl("🌍", "Relative Cycles", "/relative", nav_id="navlnk-relative"),
        ], icon="🧭", open_default=True),

        # ── Regime & Cycles — the regime engine's own output ──────────────────
        # Yield Curve left this group on 2026-10-06: its two charts are now
        # Fed Monitor's section ①.
        _group("Regime & Cycles", [
            _nl("📍", "Regime Map",     "/regime-map",     nav_id="navlnk-regime-map"),
            _nl("📈", "Regime History", "/regime-history", nav_id="navlnk-regime-history"),
            _nl("⚖️", "Debt Stress",    "/debt-stress",    nav_id="navlnk-debt-stress"),
        ], icon="🔄", open_default=True),

        # ── Monitors — curated, single-topic pages that feed no composite ─────
        _group("Monitors", [
            _nl("🏛", "Fed Monitor",    "/fed",            nav_id="navlnk-fed"),
            _nl("🗂", "Debt Cycle Monitor", "/case-study", nav_id="navlnk-case-study"),
            _nl("📐", "Market Expectations", "/market-expectations", nav_id="navlnk-market-exp"),
            _nl("🧪", "Regime Validator", "/validator-audit", nav_id="navlnk-validator-audit"),
            # Operator-only. Valuations + Bubble Gauge are one page as of
            # 2026-10-06 — the Buffett app on top, the three bubble
            # dimensions below it — so this is also the old /valuations entry.
            *([] if PUBLIC_MODE else [
                _nl("\U0001fae7", "Valuations & Bubbles", "/bubble-gauge",
                    nav_id="navlnk-bubble-gauge"),
                _nl("⚡", "AI Capex Cycle", "/ai-capex-cycle", nav_id="navlnk-ai-capex"),
            ]),
        ], icon="🖥", open_default=True),

        # ── Signals — the per-force drill-down pages ──────────────────────────
        # These were `_sub()` links ("↳ Growth", no icon, 0.78rem) until
        # 2026-10-06; they are plain `_nl()` entries now so a row under
        # Signals looks exactly like a row under any other group.
        _group("Signals", [
            _nl("📡", "All signals",    "/signals",             nav_id="navlnk-signals"),
            _nl("🌱", "Growth",        "/signals/growth",
                nav_id="navlnk-signals-growth"),
            _nl("🔥", "Inflation",     "/signals/inflation",
                nav_id="navlnk-signals-inflation"),
            _nl("💵", "Interest Rate", "/signals/rate",
                nav_id="navlnk-signals-rate"),
            _nl("🏧", "Credit",        "/signals/credit",
                nav_id="navlnk-signals-credit"),
            _nl("⚡", "Volatility",    "/signals/volatility",
                nav_id="navlnk-signals-volatility"),
            _nl("🔧", "Productivity",  "/signals/productivity",
                nav_id="navlnk-signals-productivity"),
        ], icon="📡"),

        # ── Tools — power-user exploration + model-calibration surfaces ───────
        _group("Tools", [
            _nl("📈", "Workbench",      "/workbench",      nav_id="navlnk-workbench"),
            # Operator-only calibration tools — hidden in public mode (they write
            # shared model config + the DB).
            *([] if PUBLIC_MODE else [
                _nl("🔍", "Weight Audit",   "/weight-audit",   nav_id="navlnk-weight-audit"),
                _nl("📝", "Weight History", "/weight-history", nav_id="navlnk-weight-history"),
            ]),
        ], icon="🧰"),

        # ── Reference / Admin — docs + operator-only tooling ───────────────────
        _group("Reference / Admin", [
            _nl("🎓", "User Guide",     "/guide",          nav_id="navlnk-user-guide"),
            _nl("🧭", "Assets by Environment", "/asset-environments", nav_id="navlnk-asset-env"),
            _nl("📖", "Methodology",    "/methodology",    nav_id="navlnk-methodology"),
            _nl("📋", "Data Dashboard", "/data-dashboard", nav_id="navlnk-data-dashboard"),
            # Traffic metrics — linked only where openly viewable (local/no key).
            *([_nl("📊", "Traffic", "/traffic", nav_id="navlnk-traffic")]
              if _traffic.nav_visible() else []),
        ], icon="📚"),

        html.Hr(style={"borderColor": "var(--border-color)", "margin": "6px 12px"}),

        # ── Window sliders (hidden when sidebar collapsed) ────────────────────
        html.Div([
            html.Div("Growth Z-Score Window", className="sidebar-text", style={
                "fontSize": "0.62rem", "textTransform": "uppercase",
                "letterSpacing": "0.08em", "color": "var(--muted-color)",
                "fontWeight": "700", "padding": "0 4px 4px 4px",
            }),
            dcc.Slider(
                id="zscore-window-slider",
                min=0, max=60, step=None,
                marks={0: _sm(0,"Full"), 36: _sm(36,"36m"), 48: _sm(48,"48m"), 60: _sm(60,"60m")},
                value=48,   # canonical default per Ray audit ruling 2026-07-06 (Q1c)
                tooltip={"always_visible": False, "style": {"display": "none"}},
                className="sidebar-slider",
            ),
            html.Div("Inflation Z-Score Window", className="sidebar-text", style={
                "fontSize": "0.62rem", "textTransform": "uppercase",
                "letterSpacing": "0.08em", "color": "var(--muted-color)",
                "fontWeight": "700", "padding": "10px 4px 4px 4px",
            }),
            dcc.Slider(
                id="inflation-window-slider",
                min=0, max=120, step=None,
                marks={0: _sm(0,"Full"), 60: _sm(60,"60m"), 90: _sm(90,"90m"), 120: _sm(120,"120m")},
                value=90,   # canonical default per Ray ruling (his 96m → nearest 90m grid point)
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

        # ── Feedback (hidden entirely when no endpoint is configured) ─────────
        *([_fb_btn] if _fb_btn else []),

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


def _page_workbench() -> html.Div:
    return _workbench.get_layout()


def _page_command_center() -> html.Div:
    return _command_center.get_layout()


def _page_relative_view() -> html.Div:
    return _relative_view.get_layout()


def _page_user_guide() -> html.Div:
    return _user_guide.get_layout()


def _page_overview() -> html.Div:
    return _global_overview.get_layout()


def _page_data_dashboard() -> html.Div:
    return _data_dashboard.get_layout()


def _page_methodology() -> html.Div:
    return _methodology.get_layout()


def _page_weight_audit() -> html.Div:
    return _weight_audit.get_layout()


def _page_weight_history() -> html.Div:
    return _weight_history.get_layout()


def _page_signals() -> html.Div:
    return _signals_page.get_layout()


def _page_force(force: str) -> html.Div:
    return _force_detail.get_layout(force)


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
                # Hidden but present — still a valid Output target for
                # update_scatter_date; the richer regime-date-display (below,
                # shared with Regime History) carries the visible date+country.
                html.Span(id="scatter-date-display",
                         className="text-muted small align-middle d-none"),
                html.Span(id="regime-date-display",
                         className="text-muted small align-middle"),
            ], className="d-flex align-items-center pt-2 pb-1"),
        ]),
        # Regime chips + Z-score/momentum breakdown — the SAME component (and
        # the same update_regime_info callback) as Regime History, reused here
        # by id, so the map can never show a different chip from the one the
        # classifier produced. Added 2026-08-15 after a reported US growth-chip
        # disagreement between Command Center and this page: the map showed
        # only the dot's position against the threshold lines, with no chip
        # beside it. The specific 2026-08 symptom (a Z past the line with flat
        # momentum reading "obviously Growth" on the map while the chip said
        # Transition) no longer arises — the growth chip is level-gated as of
        # 2026-10-06, so position and chip now agree on the growth axis. The
        # card stays: the inflation chip still has a momentum gate the map
        # geometry cannot show, and _season_label still differs from the chips.
        dbc.Row([
            dbc.Col(
                dbc.Card(dbc.CardBody(html.Div(id="regime-info-box"), style={"padding": "14px 16px"})),
                width=12,
            ),
        ], className="mb-2"),
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

        html.Div("Regime Chips  (the classification)", style=_H),
        *_row(None, ("Two independent chips — Growth (Growth / Transition / Retraction) and "
                     "Inflation (Inflation / Transition / Disinflation). Both need the force "
                     "Z-score beyond its ±threshold, held two months. Beyond that they "
                     "differ: GROWTH is set by that level alone, with momentum shown as a "
                     "note (accelerating / flat / fading) under the chip; INFLATION also "
                     "requires its momentum to agree. Inside the band → Transition "
                     "(honesty, not indecision).")),
        *_row("Thresholds", ("±gz / ±iz — set in the Regime Thresholds modal. With dynamic mode "
                             "on (Ray's algorithm) they adapt per month: calm eras tighten the "
                             "band, chaotic eras widen it, tight credit raises the inflation bar.")),
        *_row("Windows", ("The sidebar sliders choose what counts as 'normal': growth vs the "
                          "last 48 months and inflation vs 90 by default (Ray's canonical "
                          "ruling — inflation regimes run longer).")),
        *_row("Seasons", ("The four season names (Expansion, Inflationary Boom, Stagflation, "
                          "Disinflationary Slowdown) survive only as map geography beyond the "
                          "threshold lines — display shorthand, not the decision rule.")),
        *_row(None, html.Span(["New to these tools? The ",
                               dcc.Link("User Guide", href="/guide",
                                        style={"color": "#E8A317"}),
                               " is a full 9-lesson walkthrough."])),

        html.Div("Force Z-Scores", style=_H),
        *_row("Growth  (blue)", ("Dynamically weighted composite of the growth basket, each signal "
                                  "standardised vs. its own history over the selected window. "
                                  "Positive = above that baseline; negative = below.")),
        *_row("Inflation  (orange)", ("Same for the inflation basket. "
                                      "Positive = inflationary pressure above baseline.")),
        *_row(None, ("The zero reference line is the window mean. "
                     "Magnitude shows how far conditions have deviated from 'normal'.")),

        html.Div("Dynamic Weighting", style=_H),
        *_row("Config Weight", ("Normalized base share × editable importance × data-quality factor. "
                                 "Importance defaults live in config/countries/{cc}_composites.yaml; "
                                 "methodology settings in config/composites_policy.yaml.")),
        *_row("Momentum Tilt", ("Force and momentum agreement boosts weight up to 1.5×; "
                                  "conflict reduces it to 0.5×; neutral leaves it unchanged.")),
        *_row("Time Decay", ("Observation weight decays on a per-signal half-life after its last "
                               "data point. Per-frequency carry caps still remove data that is too old.")),
        *_row("Effective Weight", "Config weight × momentum tilt × time-decay fraction."),

        html.Div("Momentum  Δ MoM  (info box)", style=_H),
        *_row(None, ("Month-over-month change in the force score: "
                     "this month's composite Z-score minus last month's. "
                     "↑ = score rose · ↓ = score fell · → = flat (|Δ| < 0.001).")),
        *_row(None, "Distinct from the signal fraction in the momentum chart rows — see 'Chart Rows' below."),

        html.Div("Chip Agreement", style=_H),
        *_row(None, ("Per force: the fraction of constituent signals whose 3-month direction "
                     "matches the chip's heading (the sign of the composite's MoM delta), "
                     "with inverted signals flipped. Shown as G / I sub-metrics.")),
        *_row(None, ("G 85% / I 55% = the growth call is broad-based, the inflation call is "
                     "contested — weight your conviction accordingly.")),
        *_row(None, ("The chart's bottom row plots the STORED direction-agreement series "
                     "(the legacy quadrant-based definition) for history; the live per-chip "
                     "numbers are in the card above.")),

        html.Div("Disequilibrium", style=_H),
        *_row(None, ("Mean absolute Z-score across five structural force groups: "
                     "Debt, External/Trade, Technology, Governance, Climate.")),
        *_row(None, ("Unlike the cyclical chips, Disequilibrium captures slow-moving "
                     "structural imbalances that build over years.")),
        *_row("0 – 0.5", "Low structural tension."),
        *_row("0.5 – 1.5", "Moderate tension."),
        *_row("> 1.5", "High — system stretched far from long-run equilibrium."),

        html.Div("Band Strip + Cards", style=_H),
        *_row("Regime  (Growth · Inflation)",
              ("Dual-band chip history: each month's Growth chip (lower band) and "
               "Inflation chip (upper band), colored by label. The dashed vertical "
               "line marks the currently stepped-to date — click any dot, or use "
               "Prev/Now/Next, to move it.")),
        *_row("Growth Z + Momentum cards",
              ("Level of the growth composite (amber dashed lines = the ±threshold), then the "
               "fraction of growth signals whose 3-month direction is growth-positive. "
               "50% = neutral split — the fraction can exceed 50% while the Z is still "
               "negative if the score is rising from a low base.")),
        *_row("Inflation Z + Momentum cards",
              "Same pair for the inflation composite."),
        *_row("Direction Agreement (legacy) card",
              ("The stored per-month direction-agreement series, kept for historical "
               "context. Its definition predates the chips — read trends, not the "
               "absolute level, and use the live Chip Agreement in the card for today.")),
        *_row("Disequilibrium Score card",
              "Mean absolute Z-score across the five structural force groups — see above."),

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
                    html.Div(id="rh-threshold-display",
                             style={"display": "flex", "alignItems": "center",
                                    "gap": "12px", "marginRight": "12px"}),
                    dbc.Button("Regime Thresholds",
                               id={"type": "rh-threshold-open", "idx": 0},
                               color="warning", size="sm", n_clicks=0,
                               style={"fontSize": "0.78rem", "fontWeight": "600",
                                      "padding": "4px 12px", "marginRight": "6px",
                                      "color": "#111"}),
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
        # Regime-history Phase 5 retrofit (2026-10-04): the old single 7-row
        # stacked make_subplots figure is now a compact band chart (the
        # regime-row markers, which are categorical and don't fit the
        # single-series card shape) plus a grid of shared _chart_cards for
        # the six genuinely single-series rows — same pattern Phase 4 applied
        # to the Signals force-detail pages.
        dbc.Row([
            dbc.Col(
                # Dressed as a _chart_card (same chrome, same left gutter) and
                # tagged sync-hover-card so it joins the page-wide shared
                # crosshair (assets/hover_sync.js) the six cards below already
                # use — hovering any chart in the stack marks the same month on
                # all seven, the way the old single stacked figure did.
                html.Div([
                    html.Div(
                        html.Span("Regime  (Growth · Inflation)",
                                  style={"fontSize": "0.78rem", "fontWeight": "700",
                                         "color": "var(--font-color)"}),
                    ),
                    dcc.Graph(id="regime-band-chart",
                              responsive=True,
                              config={"displayModeBar": False},
                              style={"height": "140px"}),
                ], className="sync-hover-card",
                    style={"background": "var(--card-bg)",
                           "border": "1px solid var(--border-color)",
                           "borderRadius": "8px", "padding": "10px 12px"}),
                width=12,
            ),
        ]),
        dbc.Row([
            dbc.Col(html.Div(id="regime-history-cards"), width=12),
        ]),
        # ── Help panel (fixed, off-screen right by default) ────────────────────
        _build_rh_help_panel(),
    ], className="pe-2", style={"maxWidth": "1600px", "margin": "0 auto"})


def _page_fed_monitor() -> html.Div:
    return _fed_monitor.get_layout()


def _page_case_study_monitor() -> html.Div:
    return _case_study_monitor.get_layout()


def _page_market_expectations() -> html.Div:
    return _market_exp.get_layout()


def _page_validator_audit() -> html.Div:
    return _validator_monitor.get_layout()


def _page_bubble_gauge() -> html.Div:
    # Operator-only. Since 2026-10-06 this is the merged Valuations + Bubble
    # Gauge page: it embeds the Buffett Indicator app (the gated Flask route
    # below) above its own three dimension cards, which is why /valuations
    # now resolves here too. PUBLIC_MODE is intercepted earlier in
    # route_page, so this only runs for the operator.
    return _bubble_gauge_monitor.get_layout()


def _page_ai_capex() -> html.Div:
    # Operator-only while the copy settles (plan doc §10 decision 2) —
    # PUBLIC_MODE is intercepted earlier in route_page, so this only runs
    # for the operator.
    return _ai_capex_monitor.get_layout()


def _page_asset_environments() -> html.Div:
    return _asset_env.get_layout()


def _page_debt_stress() -> html.Div:
    return html.Div([
        # ── Short-Term Health × Long-Term Stress — combined-quadrant read ─────
        # Zero new data: CHI (self-normalized to its own history's sigma) on one
        # axis, the existing Debt-Stress composite Z on the other. Quadrant
        # rules per the Obsidian "Indicators Machine" design note §6.
        dbc.Row([
            dbc.Col(
                dbc.Card(dbc.CardBody([
                    html.H6("Short-Term Health × Long-Term Stress", className="mb-1"),
                    html.Div(id="chi-stress-info", className="small mb-2"),
                    dcc.Graph(id="chi-stress-scatter",
                              responsive=True,
                              config={"displayModeBar": False},
                              style={"height": "360px"}),
                ], style={"padding": "16px"})),
                width=12,
            ),
        ], className="pt-2 pb-2"),
        dbc.Row([
            dbc.Col(
                dbc.Card(dbc.CardBody(html.Div(id="debt-stress-info-box"), style={"padding": "16px"})),
                width=12,
            ),
        ], className="pb-2"),
        # ── Long-term cycle STAGE (roadmap Phase C) ───────────────────────────
        dbc.Row([
            dbc.Col(
                dbc.Card(dbc.CardBody([
                    html.Div(id="debt-stage-info"),
                    dcc.Graph(id="debt-stage-timeline",
                              responsive=True,
                              config={"displayModeBar": False},
                              style={"height": "300px"}),
                ], style={"padding": "16px"})),
                width=12,
            ),
        ], className="pb-2"),
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


_LABEL_STYLE = {"fontWeight": "700", "fontSize": "0.88rem"}
_HELP_STYLE = {"fontSize": "0.78rem", "color": "var(--muted-color)",
               "marginTop": "6px", "marginBottom": "12px"}

# Data-updates controls (operator only) vs a read-only note (public viewers).
if PUBLIC_MODE:
    _data_updates_section = [
        html.Label("Data updates", style=_LABEL_STYLE),
        html.P("Data refreshes automatically on a daily schedule.", style=_HELP_STYLE),
    ]
else:
    _data_updates_section = [
        html.Label("Data updates", style=_LABEL_STYLE),
        html.P(
            "Automatically re-import all data on a daily schedule. At the set time "
            "the dashboard briefly goes offline while the import runs (~3 minutes), "
            "then comes back with fresh numbers — the same steps you'd run by hand.",
            style=_HELP_STYLE,
        ),
        dbc.Switch(id="sched-enabled", label="Enable daily automatic import",
                   value=False, style={"fontSize": "0.85rem"}),
        html.Div([
            html.Span("Run every day at ", style={"fontSize": "0.85rem"}),
            dcc.Input(id="sched-time", type="time", value="03:00", step=60,
                      style={"width": "110px", "marginLeft": "4px",
                             "background": "var(--card-bg)", "color": "var(--font-color)",
                             "border": "1px solid var(--border-color)",
                             "borderRadius": "4px", "padding": "2px 6px"}),
            html.Span(id="sched-tz", className="ms-2",
                      style={"fontSize": "0.78rem", "color": "var(--muted-color)"}),
        ], style={"display": "flex", "alignItems": "center", "margin": "8px 0 10px"}),
        html.Div([
            dbc.Button("Save schedule", id="sched-save-btn", color="warning",
                       size="sm", n_clicks=0),
            dbc.Button("Update now", id="sched-run-now-btn", color="secondary",
                       size="sm", n_clicks=0, className="ms-2",
                       title="Run the import immediately (needs the scheduler service running)"),
        ], style={"marginBottom": "8px"}),
        html.Div(id="sched-status", style={"fontSize": "0.76rem",
                 "color": "var(--muted-color)", "lineHeight": "1.5"}),
        html.P(
            "Requires the 'scheduler' service (starts automatically with docker "
            "compose up). Timezone is set by the TZ variable in your .env.",
            style={"fontSize": "0.72rem", "color": "var(--muted-color)", "marginTop": "8px"},
        ),
    ]

_SETTINGS_MODAL = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Settings", style={"fontSize": "1rem"})),
    dbc.ModalBody([
        # ── Data updates (daily auto-import) ──────────────────────────────────
        *_data_updates_section,

        html.Hr(style={"borderColor": "var(--border-color)"}),

        # ── Appearance ────────────────────────────────────────────────────────
        html.Label("Appearance", style=_LABEL_STYLE),
        html.Div(_theme_picker(), style={"marginTop": "6px", "marginBottom": "4px"}),

        html.P(
            "Analysis look-back windows (Growth / Inflation / Disequilibrium) live "
            "in the left sidebar.",
            style={"fontSize": "0.72rem", "color": "var(--muted-color)", "marginTop": "12px"},
        ),
    ]),
    dbc.ModalFooter(
        dbc.Button("Close", id="settings-close-btn", color="secondary",
                   size="sm", n_clicks=0, className="ms-auto"),
    ),
], id="settings-modal", is_open=False, size="md")

_FEEDBACK_MODAL = _feedback.modal()


_SIGNAL_INFO_MODAL = dbc.Modal(
    id="signal-info-modal",
    size="md",
    is_open=False,
    children=[
        dbc.ModalHeader(dbc.ModalTitle(id="signal-info-title"), close_button=True),
        dbc.ModalBody(
            html.Div(id="signal-info-content"),
            style={"padding": "12px 20px 20px"},
        ),
    ],
)

_THRESHOLD_MODAL = dbc.Modal(
    id="regime-threshold-modal",
    size="md",
    is_open=False,
    children=[
        dbc.ModalHeader(dbc.ModalTitle("Regime Thresholds", style={"fontSize": "1rem"})),
        dbc.ModalBody([
            html.P(
                "The two chips read momentum differently. The GROWTH chip needs only the "
                "Z-score beyond its ±threshold (sustained two months) — the momentum band "
                "below just annotates a Growth reading as accelerating / flat / fading. "
                "The INFLATION chip needs BOTH its Z-score and its momentum threshold "
                "crossed. Inside the band, either chip reads Transition.",
                style={"fontSize": "0.78rem", "color": "var(--muted-color)", "marginBottom": "18px"},
            ),
            dcc.Checklist(
                id="rh-dynamic-toggle",
                options=[{
                    "label": " Use dynamic thresholds (Ray Dalio algorithm)",
                    "value": "dynamic",
                }],
                # Matches the default-ON store. _sync_threshold_sliders
                # overwrites this from the store when the modal opens; the
                # static value only ever shows for the instant before that, and
                # an unchecked box there misreported the live default.
                value=["dynamic"],
                style={"fontSize": "0.85rem", "color": "var(--font-color)", "marginBottom": "6px"},
            ),
            html.P(
                "Scales the Z-score thresholds by each country's own rolling volatility, then "
                "widens them further when credit is tight or the composite has been noisy. "
                "The sliders below are used as a fallback only where there isn't yet enough "
                "history for a meaningful rolling calculation. See "
                "docs/Guidance/ray_dalio_review_log.md #23.",
                style={"fontSize": "0.72rem", "color": "var(--muted-color)", "marginBottom": "18px",
                       "fontStyle": "italic"},
            ),
            dcc.Checklist(
                id="rh-conc-toggle",
                options=[{
                    "label": " Widen the growth threshold when capex is concentrated",
                    "value": "conc_adj",
                }],
                value=[],
                style={"fontSize": "0.85rem", "color": "var(--font-color)", "marginBottom": "6px"},
            ),
            html.P(
                "US only. When IT investment supplies more than a quarter of all real GDP "
                "growth, a growth composite built from broad-economy signals is partly "
                "reading one sector's capex schedule — a lower-confidence read, so the "
                "growth threshold widens (never the score itself, and never the inflation "
                "chip). Today's 34% share widens it about 7%. See "
                "docs/ai_bubble_monitor_plan.md §6.",
                style={"fontSize": "0.72rem", "color": "var(--muted-color)", "marginBottom": "18px",
                       "fontStyle": "italic"},
            ),
            html.Label("Growth Z-Score threshold  (±)", style={"fontWeight": "700", "fontSize": "0.88rem", "color": "var(--font-color)"}),
            html.Div(
                dcc.Slider(id="rh-gz-slider", min=0.0, max=2.0, step=0.05, value=0.5,
                           marks={0: _modal_mark("0"), 0.5: _modal_mark("0.5"),
                                  1.0: _modal_mark("1.0"), 1.5: _modal_mark("1.5"), 2.0: _modal_mark("2.0")},
                           tooltip={"always_visible": False, "style": {"display": "none"}},
                           allow_direct_input=True,
                           className="sidebar-slider"),
                style={"paddingBottom": "28px"},
            ),

            html.Label("Inflation Z-Score threshold  (±)", style={"fontWeight": "700", "fontSize": "0.88rem", "color": "var(--font-color)"}),
            html.Div(
                dcc.Slider(id="rh-iz-slider", min=0.0, max=2.0, step=0.05, value=0.5,
                           marks={0: _modal_mark("0"), 0.5: _modal_mark("0.5"),
                                  1.0: _modal_mark("1.0"), 1.5: _modal_mark("1.5"), 2.0: _modal_mark("2.0")},
                           tooltip={"always_visible": False, "style": {"display": "none"}},
                           allow_direct_input=True,
                           className="sidebar-slider"),
                style={"paddingBottom": "28px"},
            ),

            html.Label("Growth Momentum band  (Δ MoM)", style={"fontWeight": "700", "fontSize": "0.88rem", "color": "var(--font-color)"}),
            html.P("Δ MoM of the composite growth score. This does NOT gate the Growth chip "
                   "(the level does, on its own) — it splits a Growth reading into "
                   "accelerating / flat / fading. Default 0.04 (2026-10-06): validated against "
                   "NBER recession dating, which puts every month above the level gate outside "
                   "a recession whether or not it is still accelerating.",
                   style={"fontSize": "0.75rem", "color": "var(--muted-color)", "marginBottom": "6px"}),
            html.Div(
                dcc.Slider(id="rh-gm-slider", min=-0.1, max=0.1, step=0.005, value=0.04,
                           marks={-0.1: _modal_mark("-0.10"), -0.05: _modal_mark("-0.05"),
                                  0: _modal_mark("0"), 0.05: _modal_mark("0.05"), 0.1: _modal_mark("0.10")},
                           tooltip={"always_visible": False, "style": {"display": "none"}},
                           allow_direct_input=True,
                           className="sidebar-slider"),
                style={"paddingBottom": "28px"},
            ),

            html.Label("Inflation chip gate  (distance from target)",
                       style={"fontWeight": "700", "fontSize": "0.88rem", "color": "var(--font-color)"}),
            html.P([
                "Not a slider, because the inflation chip no longer runs on a Z-score. "
                "As of 2026-10-08 it is gated on ",
                html.B("distance from the central bank's target"),
                f" \u2014 beyond \u00b1{_inflation_tolerance_pp():.2f}pp, "
                "held for the same number of months as growth. Growth has no natural "
                "\u201cright\u201d level so it is scored against its own history; inflation has "
                "a target, so it is not (Ray, 2026-10-03). The old momentum gate was a "
                "stand-in for a level gate that did not work and has been retired. "
                "Tune it in config/inflation_anchor.yaml::bands.tolerance_pp.",
            ], style={"fontSize": "0.75rem", "color": "var(--muted-color)", "marginBottom": "6px"}),
            html.Div(style={"paddingBottom": "10px"}),
        ], style={"padding": "12px 20px 4px"}),
        dbc.ModalFooter([
            dbc.Button("Reset Defaults", id="rh-threshold-reset", color="secondary",
                       size="sm", outline=True, n_clicks=0),
            dbc.Button("Apply", id="rh-threshold-apply", color="primary",
                       size="sm", n_clicks=0, className="ms-2"),
        ]),
    ],
)

_SIGNAL_DRILL_MODAL = dbc.Modal(
    id="signal-drill-modal",
    size="xl",
    is_open=False,
    children=[
        dbc.ModalHeader(
            dbc.ModalTitle(id="signal-drill-title"),
            close_button=True,
        ),
        dbc.ModalBody(
            dcc.Graph(
                id="signal-drill-chart",
                config={"displayModeBar": False},
                style={"height": "440px"},
            ),
            style={"padding": "8px 16px 16px"},
        ),
    ],
)


_REPO_URL = "https://github.com/benito334/economic-machine-dashboard"


def _static_data_through() -> str:
    """Latest composite date in the DB — for the static-snapshot banner. Safe."""
    try:
        import duckdb as _ddb
        from dashboard.charting_data import DB_PATH
        con = _ddb.connect(str(DB_PATH), read_only=True)
        try:
            d = con.execute("SELECT max(as_of) FROM composites").fetchone()[0]
        finally:
            con.close()
        if not d:
            return ""
        if hasattr(d, "strftime"):
            return d.strftime("%b %Y")
        # string fallback: "YYYY-MM-DD" → "Mon YYYY"
        from datetime import datetime as _dt
        return _dt.strptime(str(d)[:10], "%Y-%m-%d").strftime("%b %Y")
    except Exception:
        return ""


def _static_banner():
    """Thin provenance bar — public deploys only.

    There are two public deploys and they are NOT the same thing, so the text
    must not be: Cloud Run serves a FROZEN snapshot rebuilt from a GitHub
    release, while the Oracle VM runs the live system with a nightly import.
    Telling visitors of a live instance that they are looking at a static
    snapshot "not live" is simply false, so the wording follows DEPLOY_KIND.

    Defaults to "snapshot" so the existing Cloud Run deploy is unchanged if the
    variable is unset.
    """
    if not PUBLIC_MODE:
        return None
    through = _static_data_through()
    dated = f" · data through {through}" if through else ""
    live = os.environ.get("DEPLOY_KIND", "snapshot").strip().lower() == "live"
    label = (f"📊 Live instance{dated}, updated nightly — read-only. "
             if live else
             f"📊 Static demo snapshot{dated} — read-only, not live. ")
    return html.Div(
        [
            html.Span(label, style={"opacity": "0.9"}),
            html.A("View the source & run it yourself on GitHub →",
                   href=_REPO_URL, target="_blank",
                   style={"color": "inherit", "textDecoration": "underline",
                          "fontWeight": "600"}),
        ],
        style={
            "background": "var(--slider-accent, #E8A317)",
            "color": "#1a1a1a", "fontSize": "0.8rem",
            "padding": "6px 14px", "textAlign": "center",
            "borderBottom": "1px solid rgba(0,0,0,0.15)",
        },
    )


app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    # Top-level stores — persist across page navigations
    dcc.Store(id="date-range",           data={"start": None, "end": None}),
    dcc.Store(id="theme-store",          data=DEFAULT_THEME),
    dcc.Store(id="regime-step-index",    data=0),
    # Fired by routing callback so page callbacks wait until components exist in DOM
    dcc.Store(id="page-trigger",         data={"page": "/"}),
    # Keyboard navigation: interval polls the delta set by the key listener
    dcc.Store(id="nav-event",            data=None),
    dcc.Interval(id="key-interval",      interval=80, disabled=True, n_intervals=0),
    dcc.Store(id="regime-components-open",          data=False),
    dcc.Store(id="regime-components-toggle-init",   data=None),
    # Settings: growth Z-score rolling window (0 = full history)
    dcc.Store(id="zscore-window-store",     data=48, storage_type="local"),   # Ray Q1c canonical default
    # Settings: inflation Z-score rolling window (0 = full history; separate from growth)
    dcc.Store(id="inflation-window-store",  data=90, storage_type="local"),   # Ray ruled 96m; 90m is the existing grid point
    # Settings: disequilibrium rolling window (0 = full history)
    dcc.Store(id="diseq-window-store",      data=0, storage_type="local"),
    # Active country (Phase 2 multi-country support)
    dcc.Store(id="country-store",        data="US", storage_type="local"),
    # Regime classification thresholds (persisted per browser)
    dcc.Store(id="regime-threshold-store",
              # MUST stay in sync with _DEFAULT_THRESHOLDS above -- this has
              # drifted twice (the "dynamic" default-ON change, then gm/im
              # 0.0->0.05), so it is now pinned by a test. Latest: gm->0.04
              # (2026-10-06), where gm stopped gating the growth chip and
              # became the accelerating/flat band instead.
              #
              # Stale localStorage values ARE now migrated: the "v" stamp means
              # resolve_thresholds() resets any store written against older
              # defaults, so a returning browser can no longer keep running a
              # retired rule. Bump _THRESHOLD_STORE_VERSION on every default
              # change here.
              data=dict(_DEFAULT_THRESHOLDS),
              storage_type="local"),
    # Sidebar collapsed state — persisted in localStorage
    dcc.Store(id="sidebar-collapsed",    data=False, storage_type="local"),
    # Command Center "learn to read this" banner — dismissed flag (persisted)
    dcc.Store(id="cc-learn-dismissed",   data=False, storage_type="local"),
    # Per-tab session id for traffic metrics (unique-visitor proxy)
    dcc.Store(id="session-id",           storage_type="session"),
    # Browser timezone (coarse region for traffic metrics — no IP, no geolocation)
    dcc.Store(id="tz-region",            storage_type="local"),
    # Signal drill-down: stores the signal_id most recently clicked
    dcc.Store(id="signal-drill-id",         data=None),
    dcc.Store(id="signal-drill-hover-init", data=None),
    # Signal info popup
    dcc.Store(id="signal-info-id",          data=None),
    html.Div(id="theme-dummy",           style={"display": "none"}),

    _SETTINGS_MODAL,
    _FEEDBACK_MODAL,
    *_feedback.stores(),
    _THRESHOLD_MODAL,
    _SIGNAL_DRILL_MODAL,
    _SIGNAL_INFO_MODAL,

    _static_banner(),          # public cloud deploy only (None otherwise)

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
    Input("zscore-window-slider", "value"),
    prevent_initial_call=True,
)
def update_zscore_window(sidebar_val: int) -> int:
    return int(sidebar_val) if sidebar_val is not None else 0


@callback(
    Output("inflation-window-store", "data"),
    Input("inflation-window-slider", "value"),
    prevent_initial_call=True,
)
def update_inflation_window(sidebar_val: int) -> int:
    return int(sidebar_val) if sidebar_val is not None else 0


@callback(
    Output("diseq-window-store", "data"),
    Input("diseq-window-slider", "value"),
    prevent_initial_call=True,
)
def update_diseq_window(sidebar_val: int) -> int:
    return int(sidebar_val) if sidebar_val is not None else 0


@callback(
    Output("zscore-window-slider", "value"),
    Input("zscore-window-store", "data"),
    prevent_initial_call=False,
)
def sync_zscore_slider(stored: int) -> int:
    return int(stored) if stored is not None else 0


@callback(
    Output("inflation-window-slider", "value"),
    Input("inflation-window-store", "data"),
    prevent_initial_call=False,
)
def sync_inflation_slider(stored: int) -> int:
    return int(stored) if stored is not None else 0


@callback(
    Output("diseq-window-slider", "value"),
    Input("diseq-window-store", "data"),
    prevent_initial_call=False,
)
def sync_diseq_slider(stored: int) -> int:
    return int(stored) if stored is not None else 0


# ── Settings · daily auto-import schedule ─────────────────────────────────────

def _sched_status_text() -> str:
    """One-line human status from schedule_status.json + schedule.json."""
    st = sched_cfg.load_status()
    sc = sched_cfg.load_schedule()
    parts = []
    if sc.get("enabled"):
        nxt = st.get("next_run")
        parts.append(f"Next run: {nxt.replace('T', ' ')}" if nxt else "Enabled")
    else:
        parts.append("Auto-import is off")
    last = st.get("last_run")
    if last:
        outcome = st.get("last_status", "")
        parts.append(f"Last run: {last.replace('T', ' ')}"
                     + (f" ({outcome})" if outcome else ""))
    return "  ·  ".join(parts)


# These write shared server-side state, so they exist only for the operator —
# in PUBLIC_MODE the controls aren't rendered and the callbacks aren't registered.
if not PUBLIC_MODE:

    @callback(
        Output("sched-enabled", "value"),
        Output("sched-time", "value"),
        Output("sched-tz", "children"),
        Output("sched-status", "children"),
        Input("settings-modal", "is_open"),
        prevent_initial_call=False,
    )
    def load_schedule_into_settings(is_open):
        """Populate the schedule fields whenever the Settings modal opens."""
        sc = sched_cfg.load_schedule()
        return sc["enabled"], sc["time"], f"({sc['tz']})", _sched_status_text()

    @callback(
        Output("sched-status", "children", allow_duplicate=True),
        Input("sched-save-btn", "n_clicks"),
        State("sched-enabled", "value"),
        State("sched-time", "value"),
        prevent_initial_call=True,
    )
    def save_schedule_settings(n, enabled, time_str):
        if not n:
            raise PreventUpdate
        if not sched_cfg.valid_time(time_str or ""):
            return "⚠ Enter a valid time as HH:MM."
        sched_cfg.save_schedule(bool(enabled), time_str)
        state = "enabled" if enabled else "disabled"
        return f"✔ Saved — auto-import {state}.  {_sched_status_text()}"

    @callback(
        Output("sched-status", "children", allow_duplicate=True),
        Input("sched-run-now-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def trigger_run_now(n):
        if not n:
            raise PreventUpdate
        sched_cfg.request_run_now()
        return ("⏳ Import requested — the dashboard will briefly restart while it runs. "
                "Refresh in a few minutes.")


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
                  "GB": ("🇬🇧", "United Kingdom"), "CN": ("🇨🇳", "China"),
                  "IN": ("🇮🇳", "India"),           "DE": ("🇩🇪", "Germany"),
                  "LU": ("🇱🇺", "Luxembourg"),      "BR": ("🇧🇷", "Brazil"),
                  "CA": ("🇨🇦", "Canada"),          "AU": ("🇦🇺", "Australia"),
                  "MX": ("🇲🇽", "Mexico"),          "ID": ("🇮🇩", "Indonesia")}


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


# On load, sync the dropdown FROM the persisted store. Without this the store
# rehydrates from localStorage (e.g. "GB") while the dropdown renders its
# hardcoded "US" default — every page then shows GB data under a United States
# label (found 2026-08-03: the cloud Regime History appeared to have "lost" US
# feeds; it was showing the UK basket). One-directional: store is State here,
# so no dependency cycle with update_country above.
app.clientside_callback(
    """
    function(_trig, stored, current) {
        if (stored && current !== stored) { return stored; }
        return window.dash_clientside.no_update;
    }
    """,
    Output("country-selector", "value"),
    Input("page-trigger", "data"),
    State("country-store", "data"),
    State("country-selector", "value"),
)


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

# Same shared-hover-line treatment for the signal drill-down modal chart.
app.clientside_callback(
    """
    function(figure) {
        if (!figure) return dash_clientside.no_update;
        setTimeout(function() {
            var wrapper = document.getElementById('signal-drill-chart');
            var gd = wrapper && wrapper.querySelector('.js-plotly-plot');
            if (!gd || typeof gd.on !== 'function' || gd._sdHoverSyncBound) return;

            gd._sdHoverSyncBound = true;
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

                var line = hoverLayer.querySelector('.sd-shared-hover-line');
                if (!line) {
                    line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('class', 'sd-shared-hover-line');
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
                if (gd._sdHoverSyncing || !eventData || !eventData.points || !eventData.points.length) return;
                var rawX = eventData.points[0].x;
                var xValue = rawX instanceof Date ? rawX.getTime() : Date.parse(rawX);
                var subplots = gd._fullLayout && gd._fullLayout._subplots
                    ? gd._fullLayout._subplots.cartesian : null;
                if (!Number.isFinite(xValue) || !subplots || !subplots.length) return;

                gd._sdHoverSyncing = true;
                try {
                    Plotly.Fx.hover(gd, {xval: xValue}, subplots);
                    requestAnimationFrame(function() { drawSharedHoverLine(rawX); });
                } finally {
                    setTimeout(function() { gd._sdHoverSyncing = false; }, 0);
                }
            });
            gd.on('plotly_unhover', function() {
                var line = gd.querySelector('.sd-shared-hover-line');
                if (line) line.remove();
            });
        }, 0);
        return Date.now();
    }
    """,
    Output("signal-drill-hover-init", "data"),
    Input("signal-drill-chart", "figure"),
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
    "/":              _page_command_center,   # command center is the front door (roadmap Phase CC)
    "/country":       _page_command_center,
    "/relative":      _page_relative_view,
    "/fed":           _page_fed_monitor,
    "/case-study":    _page_case_study_monitor,
    # Retired 2026-10-06 — folded into Fed Monitor (§⑦ central bank balance
    # sheet, §① yield curve). Kept as aliases so existing links/bookmarks land
    # on the charts rather than a "not found".
    "/central-bank":  _page_fed_monitor,
    "/market-expectations": _page_market_expectations,
    "/validator-audit": _page_validator_audit,
    "/bubble-gauge": _page_bubble_gauge,
    "/ai-capex-cycle": _page_ai_capex,
    # Merged into the Bubble Gauge page 2026-10-06 (valuations on top, the
    # three bubble dimensions below) — kept as an alias for existing links.
    "/valuations":    _page_bubble_gauge,
    "/guide":         _page_user_guide,
    "/asset-environments": _page_asset_environments,
    "/workbench":     _page_workbench,
    "/charts":        _page_workbench,   # legacy route
    "/overview":      _page_overview,
    "/data-dashboard":_page_data_dashboard,
    "/explorer":      _page_workbench,   # legacy route
    "/methodology":   _page_methodology,
    "/yield-curve":   _page_fed_monitor,
    "/regime-map":    _page_regime_map,
    "/regime-history":_page_regime_history,
    "/debt-stress":   _page_debt_stress,
    "/weight-audit":        _page_weight_audit,
    "/weight-history":      _page_weight_history,
    "/signals":             _page_signals,
    "/signals/growth":     lambda: _page_force("growth"),
    "/signals/inflation":  lambda: _page_force("inflation"),
    "/signals/rate":       lambda: _page_force("rate"),
    "/signals/credit":     lambda: _page_force("credit"),
    "/signals/volatility": lambda: _page_force("volatility"),
    "/signals/productivity": lambda: _page_force("productivity"),
}


@callback(
    [Output("page-content", "children"),
     Output("page-trigger", "data")],
    Input("url", "pathname"),
    [State("url", "search"),
     State("session-id", "data"),
     State("tz-region", "data")],
    prevent_initial_call=False,
)
def route_page(pathname: str, search: str = "", session: str = None, tz: str = None):
    pathname = pathname or "/"
    _traffic.record_hit(pathname, session, tz)  # self-skips assets + /traffic
    if pathname == "/traffic":
        if _traffic.can_view(search or ""):
            return _traffic.get_layout(), {"page": pathname}
        return (html.Div("This is an operator page. Append ?key=… to view.",
                         className="p-4", style={"color": "var(--muted-color)"}),
                {"page": pathname})
    if PUBLIC_MODE and pathname in OPERATOR_ONLY_ROUTES:
        return (html.Div("This is an operator tool and isn't available in the public view.",
                         className="p-4", style={"color": "var(--muted-color)"}),
                {"page": pathname})
    fn = _PAGE_MAP.get(pathname)
    layout = fn() if fn else html.Div(f"Page '{pathname}' not found", className="p-4 text-muted")
    return layout, {"page": pathname}


# Generate a per-tab session id once (unique-visitor proxy for traffic metrics).
app.clientside_callback(
    "function(_p, sid){ return sid || (Math.random().toString(36).slice(2,10) "
    "+ Date.now().toString(36)); }",
    Output("session-id", "data"),
    Input("url", "pathname"),
    State("session-id", "data"),
)


# Capture the browser's IANA timezone (e.g. "Europe/London") once — a coarse
# region hint for traffic metrics. No IP, no geolocation, nothing leaves the box.
app.clientside_callback(
    "function(_p, tz){ if (tz) return tz; "
    "try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } "
    "catch(e){ return ''; } }",
    Output("tz-region", "data"),
    Input("url", "pathname"),
    State("tz-region", "data"),
)


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

# Clientside: keep the operator-only Valuations iframe on the site's active theme
# by re-pointing its src at /valuations/app?theme=…  (the embedded app reads the
# param and applies matching CSS vars). No-ops when the frame isn't on the page.
app.clientside_callback(
    """
    function(theme, _trig) {
        var f = document.getElementById('valuations-frame');
        if (!f) return window.dash_clientside.no_update;
        var want = '/valuations/app?theme=' + (theme || 'carbon');
        if (f.getAttribute('src') !== want) return want;
        return window.dash_clientside.no_update;
    }
    """,
    Output("valuations-frame", "src"),
    Input("theme-store", "data"),
    Input("page-trigger", "data"),
)


@callback(
    Output("data-freshness", "children"),
    Input("page-trigger", "data"),
    prevent_initial_call=False,
)
def _refresh_data_stamp(_trigger: Any) -> str:
    # Re-reads the DB write time on each navigation so the sidebar stamp stays
    # current after a data refresh (the pipeline bounces this container anyway).
    return _data_freshness_str()

# ── Callbacks — aggregate selected series ─────────────────────────────────────

# ── Regime History — helpers + callbacks ─────────────────────────────────────

_GROWTH_COLOR    = "#4C9BE8"
_INFLATION_COLOR = "#E8734C"

# Growth chip colors (positive = good)
_GROWTH_CHIP  = {"Growth": "#4C9BE8", "Transition": "#888888", "Retraction": "#E8734C"}
# Inflation chip colors (inflation = bad for macro, disinflation = good)
_INFLAT_CHIP  = {"Inflation": "#E8734C", "Transition": "#888888", "Disinflation": "#4C9BE8"}

# ── Dynamic regime thresholds (Ray Dalio review 2026-07-05, #23) ─────────────
# Full algorithm, as specified by Ray:
#   1. Country-vol-scaled baseline: base_gz = 0.6 * sigma_g (24-mo rolling
#      std of the growth composite's own Z-score, look-ahead safe).
#   2. (conditional weight shift — reused from the CHI weighting rule, not
#      applied here; see dashboard/global_overview.py::_conditional_chi_weights)
#   3. Credit-tightness multiplier, inflation threshold only: credit_adj =
#      1 + max(0, credit_z - 1.5) * 0.30, where credit_z is tightness
#      (= -credit_score, since our credit_score is positive=healthy).
#   4. Volatility multiplier, both chips: vol_adj = max(vol_adj_g, vol_adj_i),
#      vol_adj_x = 1 + max(0, sigma_x_12mo - 1.0) * 0.25 — "vol of the vol":
#      12-month rolling std of the growth/inflation composite's OWN Z-score
#      history (signal noisiness), distinct from the market-based Volatility
#      force.
#   5. Combine multiplicatively: final_gz = base_gz * vol_adj;
#      final_iz = base_iz * credit_adj * vol_adj.
#   6. Classify chips using final_gz/final_iz as the Z thresholds (momentum
#      thresholds gm/im are untouched).
#   7. Correlation-divergence overlay (diagnostic only, does not feed back
#      into the thresholds): flag when growth and inflation Z-scores have had
#      opposite signs for _DIVERGENCE_LOOKBACK_N consecutive periods.
# Supersedes punch items #4, #5, #6, #14.
_DYN_THRESH_BASE_COEF    = 0.6   # Ray's suggested vol-scaling coefficient
_DYN_THRESH_SIGMA_WINDOW = 24    # months — country-specific baseline scaling
_DYN_THRESH_VOL_WINDOW   = 12    # months — "vol of the vol" multiplier
_DYN_THRESH_MIN_PERIODS  = 8     # minimum history before dynamic scaling activates
_CREDIT_TIGHT_HI = 1.5
_CREDIT_TIGHT_C1 = 0.30
_VOL_MULT_HI = 1.0
_VOL_MULT_V1 = 0.25
_DIVERGENCE_LOOKBACK_N = 3
# Capex-concentration multiplier (AI-capex panel 2026-10-04). Kicks in above a
# 25% IT share of all real GDP growth; +0.20 per additional 25pp of share.
# At 34.2% (today) this widens the growth threshold ~7%; at the 41.3% cycle
# peak, ~13%. OFF by default — the caller must pass conc_share.
_CONC_ADJ_HI = 0.25
_CONC_ADJ_C2 = 0.20


_CONC_SHARE_CACHE: "dict[str, pd.Series]" = {}


def _it_concentration_series() -> "pd.Series | None":
    """IT share of all real GDP growth (percent), monthly-aligned, memoized.

    US-only by construction — the underlying BEA contribution series have no
    cross-country equivalent — so this returns None for every other country
    and conc_adj falls back to 1.0 there.
    """
    if "us" in _CONC_SHARE_CACHE:
        return _CONC_SHARE_CACHE["us"]
    try:
        from indicators.ai_capex import it_growth_share
        df = it_growth_share()
        if df.empty:
            return None
        s = pd.Series(df["value"].values,
                      index=pd.to_datetime(df["as_of"])).sort_index()
        # Quarterly -> month-end, forward-filled: a quarter's share stands
        # until the next one is published.
        s = s.resample("ME").ffill()
        _CONC_SHARE_CACHE["us"] = s
        return s
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[conc_adj] IT concentration unavailable: %s", exc)
        return None


def _conc_share_for(country: str, thresholds: "dict | None") -> "pd.Series | None":
    """The conc_share argument for compute_dynamic_thresholds, or None when the
    multiplier is switched off or the country isn't covered."""
    if not bool(thr(thresholds, "conc_adj")):
        return None
    if (country or "US").upper() != "US":
        return None
    return _it_concentration_series()


def _threshold_floor() -> float:
    """Minimum effective dynamic threshold, from config (Ray 2026-10-03).

    Imported lazily so a config problem can never stop the dashboard booting —
    the floor degrades to the documented default rather than taking the page
    down with it.
    """
    try:
        from indicators.inflation_anchor import load_config
        return float(load_config()["growth_safeguards"]["min_dynamic_threshold"])
    except Exception:  # pragma: no cover - defensive
        logger.warning("[thresholds] could not read threshold floor; using 0.15")
        return 0.15


def compute_dynamic_thresholds(
    comp: "pd.DataFrame",
    base_gz: float = 0.5,
    base_iz: float = 0.5,
    conc_share: "pd.Series | None" = None,
) -> "pd.DataFrame":
    """Country-vol-scaled, credit/volatility-adjusted regime thresholds.

    `comp` must have growth_score / inflation_score columns (credit_score
    optional — falls back to no credit adjustment if absent). Returns a
    DataFrame aligned to comp's index with columns:
      dyn_gz, dyn_iz      — adjusted thresholds, feed directly into
                             _classify_regime's `thresholds["gz"/"iz"]`
      credit_adj, vol_adj, conc_adj — the individual multipliers, for audit/display
      divergence_flag     — True when growth/inflation have moved in opposite
                             directions for _DIVERGENCE_LOOKBACK_N consecutive
                             periods (diagnostic only)

    Falls back to (base_gz, base_iz) wherever there isn't yet enough history
    for a meaningful rolling standard deviation (e.g. early in a country's
    history, or a newly-rolled-out country).
    """
    g = comp.get("growth_score", pd.Series(dtype=float, index=comp.index))
    i = comp.get("inflation_score", pd.Series(dtype=float, index=comp.index))
    credit = comp.get("credit_score", pd.Series(dtype=float, index=comp.index))

    # Step 1: country-specific volatility scaling (24-mo rolling sigma, lagged
    # by 1 period so period t's threshold never uses period t's own value).
    sigma_g_24 = g.shift(1).rolling(_DYN_THRESH_SIGMA_WINDOW, min_periods=_DYN_THRESH_MIN_PERIODS).std()
    sigma_i_24 = i.shift(1).rolling(_DYN_THRESH_SIGMA_WINDOW, min_periods=_DYN_THRESH_MIN_PERIODS).std()
    base_dyn_gz = _DYN_THRESH_BASE_COEF * sigma_g_24
    base_dyn_iz = _DYN_THRESH_BASE_COEF * sigma_i_24

    # Step 3: credit-tightness multiplier (inflation only).
    credit_z = (-credit).fillna(0.0)
    credit_adj = 1.0 + (credit_z - _CREDIT_TIGHT_HI).clip(lower=0.0) * _CREDIT_TIGHT_C1

    # Step 4: volatility multiplier (both sides) — signal noisiness, not the
    # market-based Volatility force.
    min_p_12 = max(3, _DYN_THRESH_VOL_WINDOW // 3)
    sigma_g_12 = g.shift(1).rolling(_DYN_THRESH_VOL_WINDOW, min_periods=min_p_12).std()
    sigma_i_12 = i.shift(1).rolling(_DYN_THRESH_VOL_WINDOW, min_periods=min_p_12).std()
    vol_adj_g = 1.0 + (sigma_g_12 - _VOL_MULT_HI).clip(lower=0.0) * _VOL_MULT_V1
    vol_adj_i = 1.0 + (sigma_i_12 - _VOL_MULT_HI).clip(lower=0.0) * _VOL_MULT_V1
    vol_adj = pd.concat([vol_adj_g, vol_adj_i], axis=1).max(axis=1)

    # Step 4b: capex-concentration multiplier (GROWTH ONLY) — AI-capex panel,
    # 2026-10-04, docs/ai_bubble_monitor_plan.md §6. Off unless the caller
    # supplies `conc_share` (the 4-quarter-rolling IT-investment share of all
    # real GDP growth, in percent, from indicators.ai_capex.it_growth_share).
    #
    # Rationale is statistical, not narrative: when a single investment
    # category supplies more than a quarter of all GDP growth, a growth
    # composite built from broad-economy signals is partly reading one
    # sector's capex schedule. That is a LOWER-CONFIDENCE growth read —
    # exactly what vol_adj already encodes for a different reason — so the
    # threshold widens. The score itself is untouched, which is what keeps
    # this consistent with the "curated narratives feed no composite" rule.
    #
    # Inflation is deliberately excluded: there is no analogous concentration
    # problem on that side.
    if conc_share is not None and not conc_share.empty:
        # Align on DATES, not on comp's index. _dyn_threshold_input keeps
        # `as_of` as a column and leaves a RangeIndex behind, so reindexing a
        # date-indexed series by comp.index silently yields all-NaN.
        if "as_of" in comp.columns:
            dates = pd.to_datetime(comp["as_of"])
        elif isinstance(comp.index, pd.DatetimeIndex):
            dates = pd.Series(comp.index, index=comp.index)
        else:
            dates = None

        if dates is None:
            conc_adj = pd.Series(1.0, index=comp.index)
        else:
            src = conc_share.sort_index()
            aligned = pd.Series(
                src.reindex(src.index.union(pd.DatetimeIndex(dates)))
                   .ffill()
                   .reindex(pd.DatetimeIndex(dates)).values,
                index=comp.index,
            )
            share = aligned / 100.0
            conc_adj = (1.0 + ((share - _CONC_ADJ_HI).clip(lower=0.0)
                               / _CONC_ADJ_HI * _CONC_ADJ_C2)).fillna(1.0)
    else:
        conc_adj = pd.Series(1.0, index=comp.index)

    # Step 5: combine multiplicatively.
    final_gz = base_dyn_gz * vol_adj * conc_adj
    final_iz = base_dyn_iz * credit_adj * vol_adj

    # Fall back to the static base threshold wherever there isn't enough
    # history yet for a meaningful sigma.
    dyn_gz = final_gz.where(sigma_g_24.notna(), base_gz)
    dyn_iz = final_iz.where(sigma_i_24.notna(), base_iz)

    # Step 6: threshold FLOOR (Ray ruling 2026-10-03, growth safeguard 2).
    # "consider a modest cap (e.g., never let the effective threshold fall
    #  below 0.15 sigma) so you don't become overly sensitive during unusually
    #  calm periods." Without it a long quiet stretch shrinks the
    #  volatility-scaled threshold until ordinary noise trips the chip.
    # Value is TUNABLE in config/inflation_anchor.yaml::growth_safeguards.
    _floor = _threshold_floor()
    dyn_gz = dyn_gz.clip(lower=_floor)
    dyn_iz = dyn_iz.clip(lower=_floor)

    # Step 7: correlation-divergence overlay (diagnostic only).
    g_sign = np.sign(g)
    i_sign = np.sign(i)
    valid = g_sign.notna() & i_sign.notna() & (g_sign != 0) & (i_sign != 0)
    opposite = (g_sign != i_sign) & valid
    divergence_flag = opposite.rolling(_DIVERGENCE_LOOKBACK_N).sum() >= _DIVERGENCE_LOOKBACK_N

    return pd.DataFrame({
        "dyn_gz": dyn_gz,
        "dyn_iz": dyn_iz,
        "credit_adj": credit_adj,
        "vol_adj": vol_adj,
        "conc_adj": conc_adj,
        "divergence_flag": divergence_flag.fillna(False),
    }, index=comp.index)


def _sustained_months() -> int:
    """How many consecutive months the Z condition must hold (Ray 2026-10-03).

    "Require the Z-score to be above the threshold for at least two consecutive
    months... This reduces noise without sacrificing much lead time."
    TUNABLE in config/inflation_anchor.yaml; 1 disables the filter.
    """
    try:
        from indicators.inflation_anchor import load_config
        return int(load_config()["growth_safeguards"]["sustained_months"])
    except Exception:  # pragma: no cover - defensive
        return 1


def _holds_for(history: "pd.Series | None", threshold: float, above: bool,
               n: int) -> bool:
    """Did the Z condition hold for n consecutive periods, latest included?

    Returns True when n <= 1 or no history was supplied, so callers without
    history keep the pre-existing single-month behaviour unchanged.
    """
    if n <= 1 or history is None:
        return True
    s = history.dropna() if hasattr(history, "dropna") else None
    if s is None or len(s) < n:
        # Not enough history to demonstrate persistence — do not block the call
        # on absence of evidence, or every newly-added country reads Transition
        # for its first n months.
        return True
    tail = s.iloc[-n:]
    return bool((tail > threshold).all() if above else (tail < -abs(threshold)).all())


# Growth-chip momentum sub-state. Momentum used to be a gate on the chip
# itself; the 2026-10-06 external validation moved it here instead — see
# _classify_regime's docstring for why. This is a SECONDARY annotation, not a
# label: it says what is happening inside the regime, and it is deliberately
# not part of the chip vocabulary.
#
# Deliberately growth-only, and deliberately not promoted to a headline label.
# Against NBER dating the three growth sub-states separate (0% in recession
# each, but ordered on forward GDP: accelerating +3.74%, fading +3.43%, flat
# +3.35%), while the equivalent split on the RETRACTION side does not separate
# at all (easing +1.42%, flat +1.01%, deepening +1.43% — no ordering), so there
# is no evidence to carry it over there. And rebuilding the same split on the
# Chicago Fed's independently-weighted CFNAI-MA3 reproduces only weakly (54%
# sub-state agreement, separation falling +0.39pp -> +0.21pp), which is why it
# annotates the chip rather than replacing it.
_GROWTH_MOMENTUM_STATE = {
    "accelerating": "building",
    "flat":         "holding",
    "fading":       "easing off",
}


def _growth_breadth_state(
    g_regime: str, g_score: "float | None", g_delta: "float | None",
    thresholds: "dict | None" = None,
) -> "str | None":
    """'accelerating' | 'flat' | 'fading' for a Growth chip, else None.

    Returns None whenever the chip is not reading Growth — Transition has no
    inside to describe, and the Retraction-side split is unsupported by the
    evidence (see the comment above).
    """
    if g_regime != "Growth":
        return None
    if g_score is None or (isinstance(g_score, float) and pd.isna(g_score)):
        return None
    t = thresholds or _DEFAULT_THRESHOLDS
    gm = float(thr(t, "gm"))
    gd = (float(g_delta)
          if (g_delta is not None and not (isinstance(g_delta, float) and pd.isna(g_delta)))
          else 0.0)
    if gd > gm:
        return "accelerating"
    if gd >= -gm:
        return "flat"
    return "fading"


def gap_at(gaps: "pd.Series | None", as_of) -> "tuple[float | None, pd.Series | None]":
    """(gap, gap history ending at `as_of`) from a `gap_series` result.

    The one place that aligns the anchored inflation read to a composite row,
    so no caller hand-rolls the slice. Returns (None, None) when the month has
    no usable gap — which makes `_classify_regime` read Transition, the honest
    answer when the anchor cannot be computed.
    """
    if gaps is None or len(gaps) == 0 or as_of is None:
        return None, None
    try:
        m = pd.Timestamp(as_of).to_period("M")
    except (ValueError, TypeError):  # pragma: no cover - defensive
        return None, None
    upto = gaps[gaps.index <= m]
    if upto.empty or m not in gaps.index:
        return None, None
    v = gaps.loc[m]
    if pd.isna(v):
        return None, None
    return float(v), upto


def _classify_regime(
    g_score: "float | None",
    i_score: "float | None",
    g_delta: "float | None",
    i_delta: "float | None",
    thresholds: "dict | None" = None,
    g_history: "pd.Series | None" = None,
    i_history: "pd.Series | None" = None,
    i_gap: "float | None" = None,
    i_gap_history: "pd.Series | None" = None,
) -> "tuple[str, str]":
    """Return (growth_regime, inflation_regime).

    The two chips do not share a framework, because growth and inflation are
    not the same kind of quantity (Ray, 2026-10-03: "different animals and
    must not share a framework").

    GROWTH is RELATIVE: Z beyond ±gz, sustained for `sustained_months`. Growth
    has no natural "right" level, so scoring it against its own history is
    correct. It does NOT require the month-over-month change to agree.

    INFLATION is ABSOLUTE: distance from the central bank's target beyond
    ±`bands.tolerance_pp`, sustained for the same N. Inflation HAS a target,
    and "the market, the central bank, and everyone else is always looking at
    inflation in terms of how far are we from the target" (Ray, 2026-10-03
    Ruling 1). `i_gap` is that distance in percentage points, from
    `inflation_anchor.gap_series`.

    `i_score` / `i_delta` no longer gate the inflation chip. They stay in the
    signature because callers still display the relative Z as the documented
    SECONDARY read, and because the growth leg's own delta travels the same
    path. The momentum gate is gone: it only ever existed as a stand-in for a
    level gate that did not work, and with a functioning absolute gate it costs
    coverage for nothing (measured: 18% -> 67% of months decisive, median
    episode 1.3 -> 9.8 months, flip rate 1.9 -> 1.4/yr).

    **A caller that supplies no `i_gap` gets Transition, never a fallback to
    the retired Z rule.** One definition, read everywhere — a silent fallback
    is how two rules stay alive, and this project has been bitten by that
    repeatedly. Missing gap is visible (everything reads Transition) rather
    than quietly wrong.

    That asymmetry is deliberate and evidence-backed (Ray consult + external
    validation 2026-10-06, both logged in docs/Guidance/ray_dalio_review_log.md):

      * Ray's ruling — "if the level is below the threshold, the regime is not
        Growth, regardless of momentum"; the level is the primary gate and
        momentum describes what is happening INSIDE the regime.
      * Against NBER recession dating — genuinely independent of every series
        we ingest — every month above the growth level gate is outside a
        recession (0 of 209), whether accelerating, flat or fading, and a
        high-but-flat month sits a median 77 months from the next recession
        onset. The old rule pushed those months into Transition, a bucket that
        is 23%-within-a-year of a recession. That was the defect.
      * The momentum gate measurably helped the INFLATION chip (flip rate 33%
        with it vs 9% without) and did nothing for growth (37.0% -> 37.0% in
        the 2026-10-03 calibration, which only ever compared gm 0.0/0.05/0.1
        and never tested removing it). So it stays on inflation and comes off
        growth, per Ray's "calibrate the momentum threshold for each chip".

    Momentum has NOT been discarded for growth — it moved to
    `_growth_breadth_state()`, which sub-classifies within the regime.

    When `g_history` / `i_history` are supplied, the Z leg additionally has to
    have held for `sustained_months` consecutive periods (Ray ruling
    2026-10-03, growth safeguard 1). Callers that pass no history keep the
    original single-month rule, so this is additive, never a silent change.
    """
    t = thresholds or _DEFAULT_THRESHOLDS
    _n = _sustained_months()
    gz  = float(thr(t, "gz"))
    tol = _inflation_tolerance_pp()

    # Growth regime — level only (see docstring).
    if g_score is not None and not (isinstance(g_score, float) and pd.isna(g_score)):
        gv = float(g_score)
        if gv > gz and _holds_for(g_history, gz, True, _n):
            g_regime = "Growth"
        elif gv < -gz and _holds_for(g_history, gz, False, _n):
            g_regime = "Retraction"
        else:
            g_regime = "Transition"
    else:
        g_regime = "Transition"

    # Inflation regime — distance from target, sustained. See the docstring for
    # why this is an absolute gate while growth's is relative.
    if i_gap is not None and not (isinstance(i_gap, float) and pd.isna(i_gap)):
        gv = float(i_gap)
        if gv > tol and _holds_for(i_gap_history, tol, True, _n):
            i_regime = "Inflation"
        elif gv < -tol and _holds_for(i_gap_history, tol, False, _n):
            i_regime = "Disinflation"
        else:
            i_regime = "Transition"
    else:
        i_regime = "Transition"

    return g_regime, i_regime


def compute_regime_confidence(comp_input: "pd.DataFrame", dynamic: bool,
                               thresholds: "dict | None", force: str,
                               gaps: "pd.Series | None" = None) -> dict:
    """Probabilistic regime confidence (coverage-audit Phase B, 2026-10-03):
    the empirical frequency that a historical reading carrying TODAY'S chip
    label actually held into the following month, rather than reversing to
    Transition or the opposite chip.

    A complement to — never a replacement for — the dynamic/fixed Z+momentum
    thresholds that decide the chip itself: this function never changes what
    _classify_regime returns, it only reports how often history-to-date has
    borne out a reading like today's. Callers display "uncertain" below the
    audit's suggested ~70% cutoff without altering the underlying label.

    Mirrors indicators/backtest.py's classify_history() replay loop (same
    production _classify_regime call; no sustained-months history arg,
    consistent with that module's own simplification) but runs against
    whatever comp_input the caller already has loaded — no DB connection, no
    point-in-time Z recompute — since an empirical hold-rate-so-far stat
    doesn't need the look-ahead discipline a backtest accuracy claim would.

    comp_input: a frame with "growth_score"/"inflation_score" columns (e.g.
    from _dyn_threshold_input(), so the SAME windowed series the live chip
    uses). force: "growth" or "inflation".

    gaps: the country's `inflation_anchor.gap_series`. REQUIRED for
    force="inflation" — without it every replayed month reads Transition and
    the stat is meaningless rather than merely approximate. Passed as data
    rather than looked up from a country code, so this stays a pure function
    and so a test can supply a synthetic series.
    """
    base = dict(_DEFAULT_THRESHOLDS)
    if thresholds:
        base.update(thresholds)
    comp = comp_input.dropna(subset=["growth_score", "inflation_score"], how="all")
    if len(comp) < 2:
        return {"confidence": None, "label": None, "n": 0}

    # conc_adj is deliberately NOT applied here. This function reports how often
    # a reading like today's has historically held, and it already runs a
    # simplified replay (no sustained-months history, no country argument). A
    # US-only multiplier threaded through a historical hold-rate would change
    # the stat's meaning for one country only, which is worse than leaving the
    # complement slightly conservative.
    dyn_df = compute_dynamic_thresholds(
        comp, base_gz=base["gz"], base_iz=base["iz"],
    ) if dynamic else None

    g_delta = comp["growth_score"].diff()
    i_delta = comp["inflation_score"].diff()
    labels = []
    for pos in range(len(comp)):
        t = dict(base)
        if dyn_df is not None:
            t["gz"] = float(dyn_df["dyn_gz"].iloc[pos])
            t["iz"] = float(dyn_df["dyn_iz"].iloc[pos])
        _when = comp["as_of"].iloc[pos] if "as_of" in comp.columns else comp.index[pos]
        _ig, _igh = gap_at(gaps, _when)
        g_chip, i_chip = _classify_regime(
            comp["growth_score"].iloc[pos], comp["inflation_score"].iloc[pos],
            g_delta.iloc[pos], i_delta.iloc[pos], t,
            i_gap=_ig, i_gap_history=_igh,
        )
        labels.append(g_chip if force == "growth" else i_chip)

    s = pd.Series(labels, index=comp.index)
    current = s.iloc[-1]
    if current is None or current == "Transition":
        return {"confidence": None, "label": current, "n": 0}

    hist_s = s.iloc[:-1]             # each has a known next-month outcome
    next_s = s.shift(-1).iloc[:-1]   # that outcome
    same_mask = hist_s == current
    n = int(same_mask.sum())
    if n == 0:
        return {"confidence": None, "label": current, "n": 0}
    held = next_s[same_mask] == current
    return {"confidence": float(held.mean()), "label": current, "n": n}


def _dyn_threshold_input(comp: "pd.DataFrame", g_col: str, i_col: str) -> "pd.DataFrame":
    """Frame for compute_dynamic_thresholds using the ACTIVE score columns.

    Ray's step 1 scales the baseline by the rolling σ of "the composite's own
    Z-score" — under the 2026-07-06 window unification that means the SAME
    windowed series the classifier sees, not the full-history base columns.
    Feeding mismatched series would scale thresholds to the wrong
    distribution's volatility.
    """
    cols = (["as_of"] if "as_of" in comp.columns else []) + [g_col, i_col]
    if "credit_score" in comp.columns:
        cols.append("credit_score")
    return comp[cols].rename(columns={g_col: "growth_score", i_col: "inflation_score"})


def _resolve_row_thresholds(
    comp: "pd.DataFrame", idx: int, g_sfx: "str | None", i_sfx: "str | None",
    use_g_rolling: bool, use_i_rolling: bool,
    country: str, base: "dict | None",
) -> dict:
    """Thresholds actually in force for one row of `comp`.

    Dynamic thresholds (Ray Dalio review 2026-07-05, #23) override the static
    gz/iz with the country-vol-scaled, credit/vol-adjusted values for that
    specific month. Computed on the ACTIVE (windowed or full) score columns per
    the 2026-07-06 window-unification audit. The momentum gates gm/im are NOT
    scaled (Ray's step 6), so they pass through untouched.

    One place, because two surfaces need the same answer: the regime info card
    (which classifies with it) and the header's threshold readout (which has to
    show the reader the same number the classifier used).
    """
    t = resolve_thresholds(base)
    if comp is None or comp.empty or not bool(t["dynamic"]):
        return dict(t)
    eff_g = f"growth_score_{g_sfx}" if (g_sfx and use_g_rolling) else "growth_score"
    eff_i = f"inflation_score_{i_sfx}" if (i_sfx and use_i_rolling) else "inflation_score"
    if eff_g not in comp.columns or eff_i not in comp.columns:
        return dict(t)
    dyn = compute_dynamic_thresholds(
        _dyn_threshold_input(comp, eff_g, eff_i),
        base_gz=float(t["gz"]), base_iz=float(t["iz"]),
        conc_share=_conc_share_for(country, t),
    )
    if dyn.empty:
        return dict(t)
    row = dyn.iloc[max(0, min(idx, len(dyn) - 1))]
    return {**t, "gz": float(row["dyn_gz"]), "iz": float(row["dyn_iz"])}


def _season_label(g_score, i_score, thresholds: "dict | None" = None) -> str:
    """Threshold-aware seasonal-archetype label (Ray audit ruling 2026-07-06, Q2).

    A season name applies only when BOTH scores sit beyond the ±gz/±iz
    threshold lines — inside the band the honest label is Transition. This is
    map geography / display shorthand; the chips are the decision rule.
    """
    t = thresholds or _DEFAULT_THRESHOLDS
    gz, iz = float(thr(t, "gz")), float(thr(t, "iz"))
    if (g_score is None or i_score is None
            or (isinstance(g_score, float) and pd.isna(g_score))
            or (isinstance(i_score, float) and pd.isna(i_score))):
        return "—"
    g, i = float(g_score), float(i_score)
    if abs(g) <= gz or abs(i) <= iz:
        return "Transition — no clear season"
    return {(True, True): "Inflationary Boom", (True, False): "Expansion",
            (False, True): "Stagflation", (False, False): "Disinflationary Slowdown"}[
        (g > 0, i > 0)]


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
    thresholds: "dict | None" = None,
    g_history: "pd.Series | None" = None,
    i_history: "pd.Series | None" = None,
    i_gap: "float | None" = None,
    i_gap_history: "pd.Series | None" = None,
) -> list:
    """Build the full-width regime info card: summary strip + component table.

    g_history / i_history: the ACTIVE (windowed or full) composite score series
    up to and INCLUDING the selected row, so the chip honors the sustained-Z
    filter. Without them _classify_regime falls back to its single-month rule
    and this card contradicts Command Center for 13-26% of months — the
    defect found 2026-10-08 (JP/GB/ID disagreed live). Every other call site
    in the app passes history; these two were the only ones that did not.

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
    # Each force window resolves independently
    g_use_rolling = int(rolling.get("window",           0)) > 0
    i_use_rolling = int(rolling.get("inflation_window", 0)) > 0
    use_rolling   = g_use_rolling or i_use_rolling

    # Use rolling scores if the respective window is active
    g_score = rolling.get("g_score") if g_use_rolling else row.get("growth_score")
    i_score = rolling.get("i_score") if i_use_rolling else row.get("inflation_score")

    # Active MoM deltas for threshold classification
    _g_delta_active = rolling.get("g_delta", g_delta) if g_use_rolling else g_delta
    _i_delta_active = rolling.get("i_delta", i_delta) if i_use_rolling else i_delta

    # Classify regimes using configurable thresholds
    _t = resolve_thresholds(thresholds)
    g_regime, i_regime = _classify_regime(g_score, i_score, _g_delta_active, _i_delta_active, _t,
                                          g_history=g_history, i_history=i_history,
                                          i_gap=i_gap, i_gap_history=i_gap_history)

    # Threshold-aware seasonal-archetype label (Ray audit ruling 2026-07-06,
    # Q2) — used for the color accent only; the chips are the decision rule.
    quadrant = _season_label(g_score, i_score, _t)

    # ── Chip Direction Agreement (Ray audit ruling 2026-07-06, Q3) ────────────
    # Replaces the legacy quadrant-based confidence. Per force: the fraction of
    # signals whose direction matches the chip's heading (the sign of the
    # composite's MoM delta), with inverted signals flipped. Shown as G/I
    # sub-metrics; the averaged number keeps the old display slot.
    confidence = row.get("confidence")   # stored legacy value = fallback
    g_agree_frac: "float | None" = None
    i_agree_frac: "float | None" = None
    if comp_df is not None and not comp_df.empty:
        try:
            def _heading(delta) -> "str | None":
                if delta is None or (isinstance(delta, float) and pd.isna(delta)):
                    return None
                return "rising" if float(delta) > 0 else ("falling" if float(delta) < 0 else None)

            def _agree(direction: str, exp: str, invert: bool) -> float:
                if not direction:
                    return 0.5
                if invert:
                    exp = "falling" if exp == "rising" else "rising"
                return 1.0 if direction == exp else 0.0

            def _frac(df_part, exp) -> "float | None":
                if exp is None:
                    return None
                vals = [_agree(str(r.direction or ""), exp, bool(r.invert))
                        for r in df_part.itertuples(index=False)
                        if r.zscore is not None and not (isinstance(r.zscore, float) and pd.isna(r.zscore))]
                return sum(vals) / len(vals) if vals else None

            g_agree_frac = _frac(comp_df[comp_df["composite"] == "growth"],
                                 _heading(_g_delta_active))
            i_agree_frac = _frac(comp_df[comp_df["composite"] == "inflation"],
                                 _heading(_i_delta_active))
            known = [v for v in (g_agree_frac, i_agree_frac) if v is not None]
            if known:
                confidence = sum(known) / len(known)
        except Exception:
            pass  # fall back to stored legacy confidence
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

    def _stat_block(label: str, val_str: str, color: str = "var(--font-color)",
                    sub: str = " ") -> html.Div:
        """Chip Agreement / Disequilibrium — same visual size as _val_block but no arrow."""
        return html.Div([
            html.Div(label, style={"fontSize": "0.65rem", "color": "var(--muted-color)",
                                   "marginBottom": "3px", "whiteSpace": "nowrap"}),
            html.Div(val_str, style={"fontSize": _SZ, "fontWeight": "700",
                                     "color": color, "fontFamily": "monospace",
                                     "lineHeight": "1.1", "marginBottom": "2px"}),
            html.Div(sub, style={"fontSize": "0.65rem", "color": "var(--muted-color)"}),
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
    _cda_bits = []
    if g_agree_frac is not None:
        _cda_bits.append(f"G {g_agree_frac:.0%}")
    if i_agree_frac is not None:
        _cda_bits.append(f"I {i_agree_frac:.0%}")
    cda_sub = " · ".join(_cda_bits) if _cda_bits else "vs chip headings"
    diseq_str = _fmt(diseq)

    _g_mom_state = _growth_breadth_state(g_regime, g_score, _g_delta_active, _t)

    # Window label for the Force Z-Scores group header
    _gw = int(rolling.get("window", 0))
    _iw = int(rolling.get("inflation_window", 0))
    _win_parts = ([f"G:{_gw}mo"] if _gw else []) + ([f"I:{_iw}mo"] if _iw else [])
    _win_label = ("  ·  rolling " + " / ".join(_win_parts)) if _win_parts else ""

    summary_strip = html.Div(
        style={
            "display": "flex", "alignItems": "flex-start",
            "gap": "0", "flexWrap": "wrap", "marginBottom": "16px",
        },
        children=[
            # ── Regime chips (Growth · Inflation) ─────────────────────────────
            html.Div([
                html.Div([
                    html.Div(
                        [html.Span("G · ", style={"opacity": "0.65", "fontWeight": "400"}),
                         html.Span(g_regime, style={"fontWeight": "700"})],
                        style={
                            "backgroundColor": _GROWTH_CHIP.get(g_regime, "#888"),
                            "color": "#111", "textAlign": "center",
                            "fontSize": "0.82rem", "padding": "6px 10px",
                            "borderRadius": "4px", "flex": "1",
                            "whiteSpace": "nowrap",
                        },
                    ),
                    html.Div(
                        [html.Span("I · ", style={"opacity": "0.65", "fontWeight": "400"}),
                         html.Span(i_regime, style={"fontWeight": "700"})],
                        style={
                            "backgroundColor": _INFLAT_CHIP.get(i_regime, "#888"),
                            "color": "#111", "textAlign": "center",
                            "fontSize": "0.82rem", "padding": "6px 10px",
                            "borderRadius": "4px", "flex": "1",
                            "whiteSpace": "nowrap",
                        },
                    ),
                ], style={"display": "flex", "gap": "6px"}),
                # Growth momentum sub-state — a note UNDER the chip, never part
                # of it. The chip answers "is growth strong?" (level); this
                # answers "and is it still building?" (2026-10-06).
                *([html.Div(
                    f"growth {_g_mom_state} ({_GROWTH_MOMENTUM_STATE[_g_mom_state]})",
                    style={"fontSize": "0.66rem", "color": "var(--muted-color)",
                           "marginTop": "4px", "letterSpacing": "0.02em"},
                )] if _g_mom_state else []),
                *([past_badge] if past_badge is not None else []),
                date_block,
            ], style={"paddingRight": "20px", "width": "215px", "flexShrink": "0",
                      "display": "flex", "flexDirection": "column", "justifyContent": "flex-start"}),

            # ── Force Z-Scores ─────────────────────────────────────────────────
            _group(
                f"Force Z-Scores{_win_label}",
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

            # ── Chip Direction Agreement + Disequilibrium (Ray Q3: agreement
            # is measured against the chips' headings, not the old quadrant) ──
            _group("Regime Quality", [
                _stat_block("Chip Agreement", conf_str, sub=cda_sub),
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

        _thresh_z = float(thr(_t, "gz"))

        def _sem_z_color(z_val, f: str, inv: bool = False) -> str:
            """Green = economically good for the force, red = bad, grey = neutral zone."""
            from dashboard.shared_components import _CLR_GREEN_HI, _CLR_GREEN_LO, _CLR_RED_HI, _CLR_RED_LO, _lerp_rgb
            if z_val is None or (isinstance(z_val, float) and pd.isna(z_val)):
                return "#666"
            adj = -float(z_val) if inv else float(z_val)
            if f == "inflation":
                adj = -adj
            # Neutral zone width = threshold; magnitude scales above it
            if abs(adj) < _thresh_z:
                return "#888"
            mag = min((abs(adj) - _thresh_z) / max(2.0 * _thresh_z, 0.01), 1.0)
            mag = 0.35 + 0.65 * mag  # floor at 35% intensity so colour is visible
            return (_lerp_rgb(mag, _CLR_GREEN_LO, _CLR_GREEN_HI) if adj > 0
                    else _lerp_rgb(mag, _CLR_RED_LO, _CLR_RED_HI))

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
                    z_clr = _sem_z_color(z, force, invert)
                    bar_w = min(abs(float(z)) / 2.5 * 80, 80)
                    z_cell = html.Td(
                        html.Div(
                            style={"display": "flex", "alignItems": "center",
                                   "justifyContent": "flex-end", "gap": "6px"},
                            children=[
                                html.Div(style={
                                    "width": f"{bar_w:.0f}px", "height": "6px",
                                    "backgroundColor": z_clr, "borderRadius": "2px",
                                    "opacity": "0.7", "flexShrink": "0",
                                }),
                                html.Span(f"{float(z):+.2f}",
                                          style={"color": z_clr, "fontFamily": "monospace",
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
                    # Semantic: good direction=green for growth, red for inflation; bad=opposite
                    if force == "growth":
                        dir_color = "#5CBA8A" if is_positive else "#E8734C"
                    elif force == "inflation":
                        dir_color = "#E8734C" if is_positive else "#5CBA8A"
                    else:
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

                # Status cell — only two badges: ACTIVE (fresh, or carried
                # forward within its expected release window) and STALE
                # (genuinely past that window, per is_stale / stale_after_days).
                # Carry age/decay is informational and shown as "(#m)" next to
                # the decay % regardless of badge — it used to only surface
                # under the old "DECAYED" badge, hiding it on in-window carries.
                fill_months = max(_stale_months.get(sig_id, 0), audit_age)
                decay_detail = f" · time {decay_fraction:.0%} ({fill_months}m)" if fill_months > 0 else ""
                if not z_missing and is_stale:
                    status = html.Span([
                        html.Span(
                            "STALE",
                            style={"background": "#7a4a00", "color": "#ffcc80",
                                   "padding": "1px 5px", "borderRadius": "3px",
                                   "fontSize": "0.70rem"},
                        ),
                        html.Span(
                            f"{decay_detail} · momentum {momentum_mult:.1f}×",
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
                            decay_detail + detail,
                            style={"color": "var(--muted-color)", "fontSize": "0.72rem"},
                        ),
                    ])

                row_bg = (
                    "rgba(60,20,20,0.12)"
                    if z_missing or is_stale or low_hist
                    else "transparent"
                )
                rows.append(html.Tr(
                    style={"backgroundColor": row_bg},
                    children=[
                        html.Td(_signal_link(str(sr["label"]), str(sig_id)), style=td_sty),
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
        "Chip Agreement = % of each force's signals moving with its chip's heading (Ray audit 2026-07-06) · "
        "Provider-stale/low-history signals excluded; carried observations remain active with decay",
        style={"fontSize": "0.65rem", "color": "#555", "marginTop": "10px"},
    )

    return [summary_strip, table_section, footer]


@callback(
    Output("regime-step-index", "data"),
    # ALL, not three exact {"action": "prev"|"current"|"next"} ids: the walk
    # buttons only exist on /regime-map + /regime-history, and an exact id that
    # isn't in the current layout makes the Dash renderer log "A nonexistent
    # object was used in an `Input`" on every OTHER page's load (page-trigger
    # below is global, so this callback resolves everywhere). A wildcard input
    # matching zero components is legal and silent. triggered_id still carries
    # the concrete {"type", "action"} dict, so the action dispatch is unchanged.
    [Input({"type": "regime-step-button", "action": ALL}, "n_clicks"),
     Input("nav-event", "data"),
     Input("date-range", "data"),
     Input("page-trigger", "data"),
     Input("country-store", "data")],
    State("regime-step-index", "data"),
    prevent_initial_call=True,
)
def update_regime_step(
    _step_clicks: list,
    nav_event: dict,
    date_range: dict,
    page_trigger: dict,
    country: str,
    current_step: int,
) -> int:
    ctx = dash.callback_context
    triggered = ctx.triggered_id
    step = current_step or 0
    country = str(country or "US")
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")

    # The step index is SHARED by the Regime Map + Regime History walk controls.
    # On navigation, page-trigger CO-FIRES with a spurious step-button re-mount (its
    # n_clicks resets), and that phantom "prev" would otherwise win via triggered_id —
    # leaking a stale/incremented month between the two pages ("defaults to June" bug).
    # So: if page-trigger is anywhere in the trigger batch, landing on a walkable regime
    # page snaps back to the most-current reading (step 0) and takes priority.
    _trig_props = [t.get("prop_id", "") for t in (getattr(ctx, "triggered", None) or [])]
    if any(p.startswith("page-trigger") for p in _trig_props):
        if (page_trigger or {}).get("page") in ("/regime-history", "/regime-map"):
            return 0
        return no_update

    if triggered == "date-range":
        return 0
    if triggered == "country-store":
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
        comp = load_composite_history(start_date=start, end_date=end, country=country)
        n = len(comp)
        if ev_type == "delta":
            delta = int(val)
            if delta == 0:
                return no_update
            return max(0, min(step + delta, n - 1))
        return no_update

    comp = load_composite_history(start_date=start, end_date=end, country=country)
    max_step = max(0, len(comp) - 1)

    if action == "prev":
        return min(step + 1, max_step)
    if action == "next":
        return max(step - 1, 0)
    return step


@callback(
    Output("regime-step-index", "data", allow_duplicate=True),
    Input("regime-band-chart", "clickData"),
    State("date-range", "data"),
    State("regime-step-index", "data"),
    prevent_initial_call=True,
)
def select_regime_point(click_data: dict, date_range: dict, current_step: int) -> int:
    """Move the shared Regime History snapshot to the date clicked on the band
    chart. Pre-Phase-5-retrofit this listened across all 7 subplots of one
    shared figure; the individual _chart_cards below don't carry a stable
    component id to wire the same click-anywhere behavior onto (dcc.Graph
    inside _chart_card is anonymous by design), so click-to-jump is now
    scoped to the band chart — the Prev/Now/Next buttons remain the way to
    step from anywhere on the page."""
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
_FORCE_WINDOW_COL     = {36: "36m", 48: "48m", 60: "60m"}           # growth window → col suffix
_INFLATION_WINDOW_COL = {60: "60m", 90: "90m", 120: "120m"}          # inflation window → col suffix
_DISEQ_WINDOW_COL     = {12: "12m", 18: "18m", 24: "24m"}


@callback(
    [Output("regime-info-box", "children"),
     Output("regime-date-display", "children")],
    [Input("regime-step-index",        "data"),
     Input("date-range",               "data"),
     Input("zscore-window-store",      "data"),
     Input("inflation-window-store",   "data"),
     Input("diseq-window-store",       "data"),
     Input("country-store",            "data"),
     Input("page-trigger",             "data"),
     Input("regime-threshold-store",   "data")],
    State("regime-components-open", "data"),
    prevent_initial_call=False,
)
def update_regime_info(
    step: int,
    date_range: dict,
    zscore_window: int = 0,
    inflation_window: int = 0,
    diseq_window: int = 0,
    country: str = "US",
    _trigger: Any = None,
    thresholds: "dict | None" = None,
    components_open: bool = False,
) -> tuple:
    thresholds = resolve_thresholds(thresholds)
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

    # Position of the selected month inside FULL history. Both the dynamic
    # threshold (a 24-mo rolling sigma) and the sustained-Z filter have to read
    # real preceding data, not data the viewer's date-range preset happens to
    # include — otherwise a 1Y range silently truncates the lookback and this
    # card drifts from the scatter, which computes on full history (the frame
    # mismatch found 2026-10-08: JP gz 0.169 full vs 0.152 at the 1Y preset).
    idx_all = idx
    if not all_comp.empty:
        _sel_ts = pd.Timestamp(selected["as_of"])
        _match = all_comp.index[pd.to_datetime(all_comp["as_of"]) == _sel_ts]
        if len(_match):
            idx_all = int(all_comp.index.get_loc(_match[0]))

    date_str = comp.iloc[idx]["as_of"].strftime("%b %Y")
    # Country is spelled out in the strip — this page had NO country label, so a
    # selector/store desync (or a mis-click on the adjacent dropdown entry)
    # rendered another country's basket with nothing on screen to reveal it
    # (2026-08-03: "missing US feeds" was the GB, then EZ, basket).
    _cname = {"US": "United States", "EZ": "Euro Area", "GB": "United Kingdom",
              "JP": "Japan", "KR": "South Korea", "CN": "China", "IN": "India",
              "DE": "Germany", "LU": "Luxembourg", "BR": "Brazil", "CA": "Canada",
              "AU": "Australia", "MX": "Mexico", "ID": "Indonesia"}.get(country, country)
    date_display = (
        f"{_cname} · {date_str} · current" if is_current
        else f"{_cname} · {date_str} · {step} month{'s' if step != 1 else ''} ago"
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
        "inflation_window": inflation_window,
        "diseq_window": diseq_window,
        "g_mom_z": g_mom_z,
        "i_mom_z": i_mom_z,
    }

    # Growth and Inflation resolve their windows independently
    inflation_window = int(inflation_window or 0)
    g_sfx = _FORCE_WINDOW_COL.get(zscore_window)
    i_sfx = _INFLATION_WINDOW_COL.get(inflation_window)

    if g_sfx:
        rg_col = f"growth_score_{g_sfx}"
        if rg_col in comp.columns and comp[rg_col].notna().any():
            rg = selected.get(rg_col)
            rolling["g_score"] = float(rg) if rg is not None and not pd.isna(rg) else None
            if idx > 0:
                prev_rg = comp.iloc[idx - 1].get(rg_col)
                if rolling["g_score"] is not None and prev_rg is not None and not pd.isna(prev_rg):
                    rolling["g_delta"] = rolling["g_score"] - float(prev_rg)
        else:
            rolling["window"] = 0  # fall back — rolling not pre-computed for this country

    if i_sfx:
        ri_col = f"inflation_score_{i_sfx}"
        if ri_col in comp.columns and comp[ri_col].notna().any():
            ri = selected.get(ri_col)
            rolling["i_score"] = float(ri) if ri is not None and not pd.isna(ri) else None
            if idx > 0:
                prev_ri = comp.iloc[idx - 1].get(ri_col)
                if rolling["i_score"] is not None and prev_ri is not None and not pd.isna(prev_ri):
                    rolling["i_delta"] = rolling["i_score"] - float(prev_ri)
        else:
            rolling["inflation_window"] = 0  # fall back

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

    # Per-signal Z-score col: use rolling col when window is active
    _g_zcol = f"zscore_{g_sfx}" if g_sfx else "zscore"
    _i_zcol = f"zscore_{i_sfx}" if i_sfx else "zscore"
    comp_df = load_composite_component_status(
        country=country, as_of=str(selected["as_of"]),
        g_zscore_col=_g_zcol, i_zscore_col=_i_zcol,
    )
    stale_dict = _parse_stress_components(selected.get("stale_signals") or "")
    try:
        weight_audit = json.loads(selected.get("weight_audit") or "{}")
    except (TypeError, json.JSONDecodeError):
        weight_audit = {}

    _dyn_frame = all_comp if not all_comp.empty else comp
    _dyn_idx   = idx_all  if not all_comp.empty else idx
    thresholds_for_row = _resolve_row_thresholds(
        _dyn_frame, _dyn_idx, g_sfx, i_sfx,
        bool(rolling.get("window")), bool(rolling.get("inflation_window")),
        country, thresholds,
    )

    # Sustained-Z history on the SAME columns the card classifies with, sliced
    # to end at the selected month so stepping back in time never reads a
    # month that had not happened yet.
    def _hist(sfx: "str | None", use_rolling: bool, base_col: str) -> "pd.Series | None":
        if _dyn_frame.empty:
            return None
        col = f"{base_col}_{sfx}" if (sfx and use_rolling) else base_col
        if col not in _dyn_frame.columns:
            return None
        return _dyn_frame[col].iloc[:_dyn_idx + 1]

    g_history = _hist(g_sfx, bool(rolling.get("window")),           "growth_score")
    i_history = _hist(i_sfx, bool(rolling.get("inflation_window")), "inflation_score")

    # Target-anchored inflation gate (Ray 2026-10-03 Ruling 1).
    from indicators.inflation_anchor import gap_series as _gap_series
    _i_gap, _i_gap_hist = gap_at(_gap_series(country), selected["as_of"])

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
            thresholds=thresholds_for_row,
            g_history=g_history,
            i_history=i_history,
            i_gap=_i_gap,
            i_gap_history=_i_gap_hist,
        ),
        date_display,
    )


def _threshold_display_chips(effective: "dict | None",
                             base: "dict | None" = None) -> list:
    """The Regime History header's threshold readout.

    Shows the thresholds ACTUALLY IN FORCE for the selected month. In dynamic
    mode those are the country-vol-scaled values, not the sliders' base values
    — the two can differ a lot (US 2026-10: base 0.50, effective 0.226), and
    showing the base next to a lit DYNAMIC badge misread as "the chip needs
    +0.50" when the real bar was less than half that. The base is kept in
    parentheses so the slider setting is still visible.
    """
    t = effective or _DEFAULT_THRESHOLDS
    b = base or t
    dynamic = bool(thr(b, "dynamic"))
    gz, iz = float(thr(t, "gz")), float(thr(t, "iz"))
    gm = float(thr(t, "gm"))
    base_gz, base_iz = float(thr(b, "gz")), float(thr(b, "iz"))

    def _chip(label: str, val: float, prec: int = 2,
              base_val: "float | None" = None) -> html.Span:
        parts = [
            html.Span(label, style={"color": "var(--muted-color)", "fontSize": "0.65rem",
                                    "textTransform": "uppercase", "letterSpacing": "0.05em",
                                    "marginRight": "3px"}),
            html.Span(f"{val:+.{prec}f}" if prec > 1 else f"{val:.{prec}f}",
                      style={"color": "#E8A317", "fontFamily": "monospace", "fontSize": "0.75rem",
                             "fontWeight": "600"}),
        ]
        # Only worth the ink when the dynamic value actually moved off the base.
        if base_val is not None and abs(base_val - val) >= 0.005:
            parts.append(html.Span(f"({base_val:.2f})",
                                   style={"color": "var(--muted-color)", "fontSize": "0.62rem",
                                          "fontFamily": "monospace", "marginLeft": "3px",
                                          "opacity": "0.75"}))
        return html.Span(parts, style={"whiteSpace": "nowrap"})

    def _dot() -> html.Span:
        return html.Span("·", style={"color": "var(--border-color)", "fontSize": "0.65rem"})

    chips = [
        _chip("G·Z", gz, 2, base_gz if dynamic else None), _dot(),
        _chip("I·Z", iz, 2, base_iz if dynamic else None), _dot(),
        # gm is untouched by the dynamic algorithm (step 6) — no base shown.
        # There is no I·Δ chip: the inflation leg is target-anchored as of
        # 2026-10-08 and no longer has a momentum gate to display.
        _chip("G·Δ", gm, 3),
    ]
    if dynamic:
        chips += [_dot(), html.Span(
            "DYNAMIC", id="rh-dynamic-badge",
            style={"color": "#E8A317", "fontSize": "0.65rem",
                   "fontWeight": "700", "letterSpacing": "0.05em", "cursor": "help"})]
        chips.append(dbc.Tooltip(
            "Z thresholds shown are the values in force for the selected month "
            "(country-vol-scaled, credit/volatility-adjusted). The slider's base "
            "value is in parentheses. Momentum gates are not scaled.",
            target="rh-dynamic-badge", placement="bottom"))
    return chips


# Left gutter shared by every chart on the Regime History page. Wide enough for
# the band chart's "Inflation"/"Growth" row labels; pinned (not auto-sized to
# each figure's own tick labels) so all seven plot areas start at the same pixel.
_RH_MARGIN_L = 55


def _build_regime_band_chart(
    comp: pd.DataFrame, g_regimes: list, i_regimes: list,
    theme_name: str, sel_ts, sel_idx: int,
) -> go.Figure:
    """The regime-history page's dual-band chip-label strip (Growth @ y=0.25,
    Inflation @ y=0.75) — categorical, not a numeric series, so it stays a
    small standalone figure rather than becoming a _chart_card."""
    g_colors = [_GROWTH_CHIP.get(r, "#888") for r in g_regimes]
    i_colors = [_INFLAT_CHIP.get(r, "#888") for r in i_regimes]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=comp["as_of"], y=[0.25] * len(comp), mode="markers", name="Growth Regime",
        marker={"color": g_colors, "size": 7, "symbol": "square"},
        customdata=g_regimes,
        hovertemplate="%{x|%Y-%m-%d}<br>Growth: %{customdata}<extra></extra>",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=comp["as_of"], y=[0.75] * len(comp), mode="markers", name="Inflation Regime",
        marker={"color": i_colors, "size": 7, "symbol": "square"},
        customdata=i_regimes,
        hovertemplate="%{x|%Y-%m-%d}<br>Inflation: %{customdata}<extra></extra>",
        showlegend=False,
    ))
    fig.update_yaxes(tickvals=[0.25, 0.75], ticktext=["Growth", "Inflation"], range=[0, 1])

    fig.add_vline(x=sel_ts, line_dash="dot", line_color="rgba(255,255,255,0.35)", line_width=1.5)
    _sel_g = g_regimes[sel_idx] if sel_idx < len(g_regimes) else "Transition"
    _sel_i = i_regimes[sel_idx] if sel_idx < len(i_regimes) else "Transition"
    for _y, _regime, _chip in [(0.25, _sel_g, _GROWTH_CHIP), (0.75, _sel_i, _INFLAT_CHIP)]:
        fig.add_trace(go.Scatter(
            x=[sel_ts], y=[_y], mode="markers",
            marker={"size": 14, "symbol": "circle-open",
                   "color": _chip.get(_regime, "#888"), "line": {"width": 2.5}},
            showlegend=False, hoverinfo="skip",
        ))

    layout = figure_layout(theme_name)
    # Same gutters and spike styling as the _chart_cards stacked below it
    # (_RH_MARGIN_L on all seven), so the shared crosshair is one continuous
    # vertical line down the page rather than seven lines a few pixels apart.
    layout.update(height=140, margin={"l": _RH_MARGIN_L, "r": 8, "t": 6, "b": 18},
                  showlegend=False, hovermode="x")
    fig.update_layout(**layout)
    fig.update_xaxes(
        showgrid=False,
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikedash="dot", spikethickness=1, spikecolor="rgba(210,215,225,0.72)",
    )
    return fig


@callback(
    [Output("regime-band-chart",   "figure"),
     Output("regime-history-cards", "children")],
    [Input("date-range",               "data"),
     Input("theme-store",              "data"),
     Input("regime-step-index",        "data"),
     Input("zscore-window-store",      "data"),
     Input("inflation-window-store",   "data"),
     Input("diseq-window-store",       "data"),
     Input("country-store",            "data"),
     Input("page-trigger",             "data"),
     Input("regime-threshold-store",   "data")],
    prevent_initial_call=False,
)
def update_regime_chart(
    date_range: dict,
    theme_name: str = DEFAULT_THEME,
    step: int = 0,
    zscore_window: int = 0,
    inflation_window: int = 0,
    diseq_window: int = 0,
    country: str = "US",
    _trigger: Any = None,
    thresholds: "dict | None" = None,
) -> go.Figure:
    thresholds = resolve_thresholds(thresholds)
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    zscore_window = int(zscore_window or 0)
    inflation_window = int(inflation_window or 0)
    diseq_window = int(diseq_window or 0)
    country = str(country or "US")

    comp = load_composite_history(start_date=start, end_date=end, country=country)
    if comp.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No composite data"))
        return fig, []

    # Resolve which columns to use — Growth and Inflation have independent windows.
    # Rolling columns exist for every country as of the 2026-07-06 audit;
    # the base-column fallback remains for freshly-added countries whose
    # rolling passes haven't run yet.
    g_sfx = _FORCE_WINDOW_COL.get(zscore_window)
    i_sfx = _INFLATION_WINDOW_COL.get(inflation_window)
    diseq_sfx = _DISEQ_WINDOW_COL.get(diseq_window)
    def _has_data(df: pd.DataFrame, col: str) -> bool:
        return col in df.columns and df[col].notna().any()
    g_col = f"growth_score_{g_sfx}" if g_sfx and _has_data(comp, f"growth_score_{g_sfx}") else "growth_score"
    i_col = f"inflation_score_{i_sfx}" if i_sfx and _has_data(comp, f"inflation_score_{i_sfx}") else "inflation_score"
    d_col = f"disequilibrium_{diseq_sfx}" if diseq_sfx and _has_data(comp, f"disequilibrium_{diseq_sfx}") else "disequilibrium_score"

    # Threshold-aware seasonal-archetype label (Ray audit ruling 2026-07-06,
    # Q2): a season name applies only beyond the ±gz/±iz lines; inside the
    # band the label is Transition. Uses the active (rolling or full) columns.
    quadrant_series = comp.apply(
        lambda row: _season_label(row.get(g_col), row.get(i_col), thresholds), axis=1)

    win_label_g = f"G:{zscore_window}mo" if (g_sfx and g_col != "growth_score") else ""
    win_label_i = f"I:{inflation_window}mo" if (i_sfx and i_col != "inflation_score") else ""
    parts = [p for p in [win_label_g, win_label_i] if p]
    win_label = f" · rolling {' / '.join(parts)}" if parts else ""
    diseq_label = f" · rolling {diseq_window}mo" if (diseq_sfx and d_col != "disequilibrium_score") else ""

    # ── Per-row regime classification using configurable thresholds ────────────
    _t = thresholds
    _gz = float(thr(_t, "gz"))
    _iz = float(thr(_t, "iz"))
    _th_line = dict(color="rgba(232,163,23,0.40)", width=1, dash="dash")

    # Dynamic thresholds (Ray Dalio review 2026-07-05, #23) — per-row gz/iz
    # computed from each country's own rolling volatility + credit tightness,
    # rather than one flat value for the whole history. Computed on the
    # ACTIVE (windowed or full) score columns per the 2026-07-06 audit.
    # Both the rolling-sigma threshold and the sustained-Z filter must read
    # real preceding months, so they are computed on FULL history and then
    # looked up by date for the rows this (possibly date-filtered) view shows.
    # Computing either on the filtered frame truncates the lookback and makes
    # this chart disagree with its own regime info card.
    _full = comp
    try:
        _cand = load_composite_history(country=country)
        if (not _cand.empty and g_col in _cand.columns and i_col in _cand.columns):
            _full = _cand
    except Exception:
        pass
    _full_pos = {pd.Timestamp(d): p for p, d in enumerate(_full["as_of"])}

    _dynamic = bool(thr(_t, "dynamic"))
    _dyn_df = compute_dynamic_thresholds(
        _dyn_threshold_input(_full, g_col, i_col), base_gz=_gz, base_iz=_iz,
        conc_share=_conc_share_for(country, _t),
    ) if _dynamic else None
    if _dynamic and not _dyn_df.empty:
        # Use the latest VISIBLE row's dynamic threshold as the reference hline
        # — a single static line can't represent a time-varying threshold.
        # Indexed into full history (where _dyn_df now lives), but still the
        # last month this view shows, not the last month that exists.
        _ref = _full_pos.get(pd.Timestamp(comp.iloc[-1]["as_of"]), len(_dyn_df) - 1)
        _gz = float(_dyn_df["dyn_gz"].iloc[_ref])
        _iz = float(_dyn_df["dyn_iz"].iloc[_ref])

    # Deltas off full history too: on the filtered frame the first visible row
    # has a NaN delta, which _classify_regime reads as 0.0 and so fails the
    # inflation momentum gate for a month that may well have cleared it.
    _full_g = _full[g_col]
    _full_i = _full[i_col]
    g_delta_s = _full_g.diff()
    i_delta_s = _full_i.diff()
    from indicators.inflation_anchor import gap_series as _gap_series
    _gaps = _gap_series(country)
    g_regimes, i_regimes = [], []
    for pos in range(len(comp)):
        row_s = comp.iloc[pos]
        _fp = _full_pos.get(pd.Timestamp(row_s["as_of"]))
        if _dynamic and _dyn_df is not None and not _dyn_df.empty and _fp is not None:
            row_t = {
                "gz": float(_dyn_df["dyn_gz"].iloc[_fp]),
                "iz": float(_dyn_df["dyn_iz"].iloc[_fp]),
                "gm": thr(_t, "gm"),
            }
        else:
            row_t = _t
        gr, ir = _classify_regime(
            row_s.get(g_col), row_s.get(i_col),
            None if _fp is None else g_delta_s.iloc[_fp],
            None if _fp is None else i_delta_s.iloc[_fp],
            row_t,
            g_history=None if _fp is None else _full_g.iloc[:_fp + 1],
            i_history=None if _fp is None else _full_i.iloc[:_fp + 1],
            **dict(zip(("i_gap", "i_gap_history"), gap_at(_gaps, row_s["as_of"]))),
        )
        g_regimes.append(gr)
        i_regimes.append(ir)

    # ── Step selection (used by both the band chart and every card below) ─────
    step = step or 0
    n = len(comp)
    sel_idx = max(0, min(n - 1 - step, n - 1))
    sel = comp.iloc[sel_idx]
    sel_ts = sel["as_of"]

    # ── Band chart — the regime-row markers are categorical (a chip label per
    # month, not a numeric series), so they stay their own compact figure
    # rather than becoming a _chart_card. Everything else below is a genuine
    # single series and converts cleanly.
    band_fig = _build_regime_band_chart(comp, g_regimes, i_regimes, theme_name, sel_ts, sel_idx)

    # ── Cards — Growth Z, Growth Momentum, Inflation Z, Inflation Momentum,
    # Direction Agreement, Disequilibrium (the old Rows 2-7) ──────────────────
    def _series_df(col: str) -> pd.DataFrame:
        if col not in comp.columns:
            return pd.DataFrame(columns=["as_of", "value"])
        return comp[["as_of", col]].dropna().rename(columns={col: "value"})

    def _cur(col: str, fmt: str) -> tuple[Optional[float], Optional[str]]:
        v = sel.get(col)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None, None
        v = float(v)
        return v, format(v, fmt)

    g_cur, g_fmt = _cur(g_col, "+.2f")
    gm_cur, gm_fmt = _cur("growth_breadth", ".0%")
    i_cur, i_fmt = _cur(i_col, "+.2f")
    im_cur, im_fmt = _cur("inflation_breadth", ".0%")
    conf_cur, conf_fmt = _cur("confidence", ".0%")
    d_cur, d_fmt = _cur(d_col, ".3f")

    cards = [
        _chart_card(
            f"Growth Force Z-Score (composite{win_label})", _series_df(g_col), g_cur, "z", "",
            zero_line=True, hline=_gz, hline_txt=f"+{_gz:.2f}", hline2=-_gz, hline2_txt=f"-{_gz:.2f}",
            color=_COLORS[0], fill=True, vline_x=sel_ts, sync_hover=True, fmt_override=g_fmt,
            margin_l=_RH_MARGIN_L,
        ),
        _chart_card(
            "Growth Momentum (fraction of signals growth-positive)", _series_df("growth_breadth"),
            gm_cur, "pct", "", hline=0.5, hline_txt="50%",
            color=_COLORS[0], vline_x=sel_ts, sync_hover=True, fmt_override=gm_fmt,
            margin_l=_RH_MARGIN_L,
        ),
        _chart_card(
            f"Inflation Force Z-Score (composite{win_label})", _series_df(i_col), i_cur, "z", "",
            zero_line=True, hline=_iz, hline_txt=f"+{_iz:.2f}", hline2=-_iz, hline2_txt=f"-{_iz:.2f}",
            color=_INFLATION_COLOR, fill=True, vline_x=sel_ts, sync_hover=True, fmt_override=i_fmt,
            margin_l=_RH_MARGIN_L,
        ),
        _chart_card(
            "Inflation Momentum (fraction of signals inflation-positive)", _series_df("inflation_breadth"),
            im_cur, "pct", "", hline=0.5, hline_txt="50%",
            color=_INFLATION_COLOR, vline_x=sel_ts, sync_hover=True, fmt_override=im_fmt,
            margin_l=_RH_MARGIN_L,
        ),
        _chart_card(
            "Direction Agreement (legacy)", _series_df("confidence"), conf_cur, "pct",
            "Stored series — legacy definition; live Chip Agreement is in the card above.",
            hline=0.5, hline_txt="50%", color=_COLORS[4], vline_x=sel_ts, sync_hover=True,
            fmt_override=conf_fmt, margin_l=_RH_MARGIN_L,
        ),
        _chart_card(
            f"Disequilibrium Score{diseq_label}", _series_df(d_col), d_cur, "", "",
            color=_COLORS[1], fill=True, vline_x=sel_ts, sync_hover=True, fmt_override=d_fmt,
            margin_l=_RH_MARGIN_L,
        ),
    ]

    # columns=1: one chart per row, full width, stacked — same shape as the
    # Signals force pages' composite cards, so the shared crosshair reads as a
    # single vertical line down the page instead of jumping between columns.
    return band_fig, _section("", "", cards, columns=1)


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


# ── Regime Threshold modal — callbacks ───────────────────────────────────────

@callback(
    Output("regime-threshold-modal", "is_open"),
    # The opener button lives on /regime-history only, while the modal itself,
    # Apply/Reset and page-trigger are all global — so this callback resolves on
    # every page, and an exact id absent from the current layout made the Dash
    # renderer log "A nonexistent object was used in an `Input`" on every other
    # page's load. A wildcard input matching zero components is legal and silent.
    [Input({"type": "rh-threshold-open", "idx": ALL}, "n_clicks"),
     Input("rh-threshold-apply", "n_clicks"),
     Input("rh-threshold-reset", "n_clicks"),
     Input("page-trigger",       "data")],
    State("regime-threshold-modal", "is_open"),
    prevent_initial_call=False,  # fire on load to guarantee is_open=False
)
def _toggle_threshold_modal(
    n_open: list, n_apply: int, n_reset: int,
    page_trigger: dict, is_open: bool,
) -> bool:
    from dash import ctx
    trig = ctx.triggered_id
    # Guard on n_clicks > 0: initial load fires with n_clicks=0 which must not open
    if isinstance(trig, dict) and trig.get("type") == "rh-threshold-open":
        if any((n or 0) > 0 for n in (n_open or [])):
            return True
    return False  # initial load, Apply, Reset, or page navigation all close


@callback(
    Output("rh-threshold-display", "children"),
    [Input("regime-threshold-store", "data"),
     Input("regime-step-index",      "data"),
     Input("zscore-window-store",    "data"),
     Input("inflation-window-store", "data"),
     Input("country-store",          "data"),
     Input("date-range",             "data"),
     Input("page-trigger",           "data")],
    prevent_initial_call=False,
)
def _update_threshold_display(
    thresholds: "dict | None", step: int = 0,
    zscore_window: int = 0, inflation_window: int = 0,
    country: str = "US", date_range: "dict | None" = None, _trigger: Any = None,
) -> list:
    """Header readout of the thresholds in force for the SELECTED month.

    Takes the same selection inputs the regime info card does, because in
    dynamic mode the thresholds move month to month — a readout wired to the
    threshold store alone could only ever show the sliders' base values, which
    is what made the header say "G·Z +0.50" while the classifier was using
    0.226 (US, Oct 2026).
    """
    country = str(country or "US")
    base = resolve_thresholds(thresholds)
    if not bool(base["dynamic"]):
        return _threshold_display_chips(base)
    try:
        comp = load_composite_history(
            start_date=(date_range or {}).get("start"),
            end_date=(date_range or {}).get("end"),
            country=country,
        )
    except Exception:
        return _threshold_display_chips(base)
    if comp.empty:
        return _threshold_display_chips(base)
    idx = max(0, min(len(comp) - 1 - int(step or 0), len(comp) - 1))
    # The date range picks WHICH month is selected; the dynamic threshold for
    # that month is then computed on FULL history, the same frame the scatter
    # and the regime info card use. Resolving it on the filtered frame made
    # this readout disagree with both whenever a short preset was active.
    _sel_ts = pd.Timestamp(comp.iloc[idx]["as_of"])
    try:
        _all = load_composite_history(country=country)
    except Exception:
        _all = comp
    if not _all.empty:
        _m = _all.index[pd.to_datetime(_all["as_of"]) == _sel_ts]
        if len(_m):
            comp, idx = _all, int(_all.index.get_loc(_m[0]))
    g_sfx = _FORCE_WINDOW_COL.get(int(zscore_window or 0))
    i_sfx = _INFLATION_WINDOW_COL.get(int(inflation_window or 0))

    def _has(col: "str | None") -> bool:
        return bool(col) and col in comp.columns and comp[col].notna().any()

    eff = _resolve_row_thresholds(
        comp, idx, g_sfx, i_sfx,
        _has(f"growth_score_{g_sfx}" if g_sfx else None),
        _has(f"inflation_score_{i_sfx}" if i_sfx else None),
        country, base,
    )
    return _threshold_display_chips(eff, base)


@callback(
    [Output("rh-gz-slider", "value"),
     Output("rh-iz-slider", "value"),
     Output("rh-gm-slider", "value"),
     Output("rh-dynamic-toggle", "value"),
     Output("rh-conc-toggle", "value")],
    Input("regime-threshold-modal", "is_open"),
    State("regime-threshold-store", "data"),
    prevent_initial_call=True,
)
def _sync_threshold_sliders(is_open: bool, stored: "dict | None") -> tuple:
    """Populate slider values from store when modal opens."""
    if not is_open:
        from dash import no_update
        return (no_update,) * 5
    t = resolve_thresholds(stored)
    return (
        float(t["gz"]),
        float(t["iz"]),
        float(t["gm"]),
        ["dynamic"] if bool(t["dynamic"]) else [],
        ["conc_adj"] if bool(t["conc_adj"]) else [],
    )


@callback(
    Output("regime-threshold-store", "data"),
    [Input("rh-threshold-apply", "n_clicks"),
     Input("rh-threshold-reset", "n_clicks")],
    [State("rh-gz-slider", "value"),
     State("rh-iz-slider", "value"),
     State("rh-gm-slider", "value"),
     State("rh-dynamic-toggle", "value"),
     State("regime-threshold-store", "data")],
    prevent_initial_call=True,
)
def _save_thresholds(
    n_apply: int, n_reset: int,
    gz: float, iz: float, gm: float,
    dynamic_val: "list | None",
    current: "dict | None",
) -> dict:
    from dash import ctx, no_update
    if ctx.triggered_id == "rh-threshold-reset":
        return dict(_DEFAULT_THRESHOLDS)
    if ctx.triggered_id == "rh-threshold-apply":
        # Stamp the version: this IS a deliberate choice, so it must survive
        # future default changes -- and an unstamped write would be reset by
        # resolve_thresholds() on the very next page load.
        #
        # `x if x is not None else default` rather than `x or default`: a
        # slider legitimately sits at 0.0 (gm/im both have a 0.0 stop), and
        # `or` would silently rewrite a deliberate zero.
        _cur = resolve_thresholds(current)
        def _val(v, key):
            return float(v) if v is not None else float(_cur[key])
        return {"gz": _val(gz, "gz"), "iz": _val(iz, "iz"),
                "gm": _val(gm, "gm"),
                "dynamic": bool(dynamic_val),
                "conc_adj": bool(_cur["conc_adj"]),
                "v": _THRESHOLD_STORE_VERSION}
    return no_update


@callback(
    Output("regime-threshold-store", "data", allow_duplicate=True),
    Input("rh-dynamic-toggle", "value"),
    State("regime-threshold-store", "data"),
    prevent_initial_call=True,
)
def _apply_dynamic_toggle(dynamic_val: "list | None", current: "dict | None") -> dict:
    """Dynamic-thresholds is a mode switch, not a value to confirm — apply it the
    moment the checkbox changes rather than waiting for the Apply button (which
    users don't expect to press for a checkbox).  Slider values still require Apply.
    """
    from dash import no_update
    t = resolve_thresholds(current)
    new_val = bool(dynamic_val)
    if bool(t["dynamic"]) == new_val:
        # No real change (e.g. this fired because the modal-open sync callback
        # set the checkbox to match the store) — don't rewrite the store.
        return no_update
    t["dynamic"] = new_val
    return t


@callback(
    Output("regime-threshold-store", "data", allow_duplicate=True),
    Input("rh-conc-toggle", "value"),
    State("regime-threshold-store", "data"),
    prevent_initial_call=True,
)
def _apply_conc_toggle(conc_val: "list | None", current: "dict | None") -> dict:
    """Same mode-switch treatment as the dynamic toggle — apply on change, not
    on Apply."""
    from dash import no_update
    t = resolve_thresholds(current)
    new_val = bool(conc_val)
    if bool(t["conc_adj"]) == new_val:
        return no_update
    t["conc_adj"] = new_val
    return t


# ── Feedback dialog ───────────────────────────────────────────────────────────
# The SUBMIT is clientside on purpose: the POST must leave the visitor's
# browser, never this server, so the deployment keeps writing nothing. Opening
# and closing the modal is ordinary server-side state.
if _feedback.enabled():

    @callback(
        Output("feedback-modal", "is_open"),
        Output("feedback-message", "value"),
        Output("feedback-email", "value"),
        Output("feedback-status", "children", allow_duplicate=True),
        [Input("feedback-btn", "n_clicks"),
         Input("feedback-cancel", "n_clicks"),
         Input("feedback-sent", "data")],
        State("feedback-modal", "is_open"),
        prevent_initial_call=True,
    )
    def _toggle_feedback(open_n, cancel_n, sent, is_open):
        """Open on the sidebar button; clear and close on cancel or a send.

        Clearing the fields on close matters: a stale draft reappearing the
        next time someone opens the dialog reads as if it failed to send.
        """
        from dash import ctx
        trig = ctx.triggered_id
        if trig == "feedback-btn":
            return True, "", "", ""
        if trig == "feedback-cancel":
            return False, "", "", ""
        if trig == "feedback-sent" and sent:
            return False, "", "", ""
        return is_open, no_update, no_update, no_update

    app.clientside_callback(
        _feedback.SUBMIT_JS,
        Output("feedback-status", "children"),
        Output("feedback-status", "style"),
        Output("feedback-sent", "data"),
        Input("feedback-send", "n_clicks"),
        [State("feedback-message", "value"),
         State("feedback-email", "value"),
         State("feedback-config", "data"),
         State("url", "pathname"),
         State("country-store", "data"),
         State("zscore-window-store", "data"),
         State("inflation-window-store", "data"),
         State("diseq-window-store", "data"),
         State("theme-store", "data"),
         State("session-id", "data")],
        prevent_initial_call=True,
    )


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
    [Input("regime-step-index",        "data"),
     Input("date-range",               "data"),
     Input("theme-store",              "data"),
     Input("zscore-window-store",      "data"),
     Input("inflation-window-store",   "data"),
     Input("country-store",            "data"),
     Input("page-trigger",             "data"),
     Input("regime-threshold-store",   "data")],
    prevent_initial_call=False,
)
def update_scatter_chart(
    step: int,
    date_range: dict,
    theme_name: str,
    zscore_window: int = 0,
    inflation_window: int = 0,
    country: str = "US",
    _trigger: Any = None,
    thresholds: "dict | None" = None,
) -> go.Figure:
    step = step or 0
    theme_name = theme_name or DEFAULT_THEME
    zscore_window = int(zscore_window or 0)
    inflation_window = int(inflation_window or 0)
    country = str(country or "US")
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])

    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp_filtered = load_composite_history(start_date=start, end_date=end, country=country)
    comp_all = load_composite_history(country=country)

    # Resolve rolling columns independently for Growth and Inflation —
    # fall back to base when pre-computed rolling cols are all-null.
    g_sfx = _FORCE_WINDOW_COL.get(zscore_window)
    i_sfx = _INFLATION_WINDOW_COL.get(inflation_window)
    def _has_rolling(df: pd.DataFrame, col: str) -> bool:
        return col in df.columns and df[col].notna().any()
    g_col = f"growth_score_{g_sfx}" if g_sfx and _has_rolling(comp_all, f"growth_score_{g_sfx}") else "growth_score"
    i_col = f"inflation_score_{i_sfx}" if i_sfx and _has_rolling(comp_all, f"inflation_score_{i_sfx}") else "inflation_score"

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

    # ── Resolve selected index in all-history (needed before the shading so
    # dynamic-mode geometry can follow the SELECTED month when stepping back) ─
    n_filtered = len(comp_filtered)
    sel_idx_f = max(0, min(n_filtered - 1 - step, n_filtered - 1))
    sel_date = pd.Timestamp(comp_filtered.iloc[sel_idx_f]["as_of"])

    all_ts = [pd.Timestamp(d) for d in comp_all["as_of"]]
    try:
        sel_idx_all = next(i for i, d in enumerate(all_ts) if d == sel_date)
    except StopIteration:
        sel_idx_all = len(comp_all) - 1

    # ── Seasonal-archetype background shading (Ray audit ruling 2026-07-06,
    # Q2): the four season colors shade ONLY the outer corner regions beyond
    # the ±gz/±iz threshold lines — the operative classifier's Transition band
    # between the lines stays neutral. Season names are map geography ("modes
    # of behavior"), not the decision rule; the chips are the decision rule.
    # In dynamic mode the geometry is positioned by the SELECTED month's
    # dynamic thresholds (computed on the ACTIVE score columns) — walking back
    # in time moves the band to what the classifier used that month, matching
    # the regime info card's per-row values.
    _bg_th = resolve_thresholds(thresholds)
    _dyn_bg = None
    if bool(_bg_th["dynamic"]):
        _dyn_bg = compute_dynamic_thresholds(
            _dyn_threshold_input(comp_all, g_col, i_col),
            base_gz=float(_bg_th["gz"]), base_iz=float(_bg_th["iz"]),
            conc_share=_conc_share_for(country, _bg_th),
        )
        if not _dyn_bg.empty:
            _bg_th["gz"] = float(_dyn_bg["dyn_gz"].iloc[sel_idx_all])
            _bg_th["iz"] = float(_dyn_bg["dyn_iz"].iloc[sel_idx_all])
    _bgz = float(thr(_bg_th, "gz"))
    _biz = float(thr(_bg_th, "iz"))
    quad_bg = [
        (_bgz,  100,  _biz,  100, "Inflationary Boom",        "#F4C842"),
        (_bgz,  100,  -100, -_biz, "Expansion",                "#5CBA8A"),
        (-100, -_bgz, _biz,  100, "Stagflation",              "#E8734C"),
        (-100, -_bgz, -100, -_biz, "Disinflationary Slowdown", "#4C9BE8"),
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
    # Configurable threshold lines — same effective (static or selected-month
    # dynamic) values as the corner shading above, so geometry and lines agree.
    _gz, _iz = _bgz, _biz
    _th_line = dict(color="rgba(255,255,255,0.22)", width=1, dash="dash")
    shapes += [
        dict(type="line", xref="x", yref="paper", x0=_gz,  x1=_gz,  y0=0, y1=1, line=_th_line),
        dict(type="line", xref="x", yref="paper", x0=-_gz, x1=-_gz, y0=0, y1=1, line=_th_line),
        dict(type="line", xref="paper", yref="y", x0=0, x1=1, y0=_iz,  y1=_iz,  line=_th_line),
        dict(type="line", xref="paper", yref="y", x0=0, x1=1, y0=-_iz, y1=-_iz, line=_th_line),
    ]

    # ── Threshold-aware season label for hovers (Ray Q2: Transition inside
    # the band; season names only beyond the lines). In dynamic mode each
    # history dot is labeled against ITS OWN month's thresholds — the honest
    # per-row read, matching how the classifier judged that month. ───────────
    if _dyn_bg is not None and not _dyn_bg.empty:
        eff_quadrant = pd.Series([
            _season_label(
                comp_all.iloc[pos].get(g_col), comp_all.iloc[pos].get(i_col),
                {"gz": float(_dyn_bg["dyn_gz"].iloc[pos]),
                 "iz": float(_dyn_bg["dyn_iz"].iloc[pos])},
            )
            for pos in range(len(comp_all))
        ], index=comp_all.index)
    else:
        eff_quadrant = comp_all.apply(
            lambda row: _season_label(row.get(g_col), row.get(i_col), _bg_th), axis=1)

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

    # ── Season corner labels + explicit Transition band label (Ray Q2) ───────
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
    annotations.append(dict(
        text="Transition — no clear season", x=0, y=0, xref="x", yref="y",
        showarrow=False, font=dict(color="#777", size=9, family="monospace"),
        bgcolor="rgba(0,0,0,0)",
    ))

    _g_win_sfx = f" ({zscore_window}mo)" if (g_sfx and g_col != "growth_score") else ""
    _i_win_sfx = f" ({inflation_window}mo)" if (i_sfx and i_col != "inflation_score") else ""
    layout = figure_layout(theme_name)
    layout.update(dict(
        xaxis=dict(title=f"Growth Force Z-Score{_g_win_sfx}", range=x_range,
                   zeroline=False, gridcolor=t["grid_color"], showgrid=True),
        yaxis=dict(title=f"Inflation Force Z-Score{_i_win_sfx}", range=y_range,
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
    country: str = "US",
) -> list:
    """Build the full-width top-panel children for the Debt Stress tab."""
    muted = {"color": "var(--muted-color)"}

    if ds_latest is None or ds_latest.empty:
        return [html.Div("No debt stress data — run pipeline.", style=muted)]

    # ── Load stress config for weights, frequencies, carry cap ────────────────
    # US runs the original 7-component model; every other rolled-out country
    # (2026-10 coverage-audit, High item #3) has its own reduced-subset file.
    try:
        from indicators.longterm_stress import _CONFIG_DIR as _STRESS_CFG_DIR
        from indicators.longterm_stress import load_longterm_stress_config
        if country.upper() == "US":
            stress_cfg = load_longterm_stress_config()
        else:
            cc_path = _STRESS_CFG_DIR / "countries" / f"{country.lower()}_longterm_stress.yaml"
            stress_cfg = load_longterm_stress_config(cc_path) if cc_path.exists() else {"components": []}
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
            z_clr = _stress_z_color(z, direction)
            bar_w = min(abs(float(z)) / 2.5 * 80, 80)
            z_cell = html.Td(
                html.Div(
                    style={"display": "flex", "alignItems": "center",
                           "justifyContent": "flex-end", "gap": "6px"},
                    children=[
                        html.Div(style={
                            "width": f"{bar_w:.0f}px", "height": "6px",
                            "backgroundColor": z_clr, "borderRadius": "2px",
                            "opacity": "0.8", "flexShrink": "0",
                        }),
                        html.Span(f"{float(z):+.2f}",
                                  style={"color": z_clr, "fontFamily": "monospace",
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
                html.Td(
                    _signal_link(label, _DEBT_STRESS_DRILL_SIGNAL[cid])
                    if _DEBT_STRESS_DRILL_SIGNAL.get(cid) else html.Span(label),
                    style=td_sty,
                ),
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
    end = (date_range or {}).get("end")
    df = load_debt_stress_history(country=country, end_date=end)
    latest = df.iloc[-1] if not df.empty else None
    if latest is None:
        return [html.Div(
            f"No Debt-Stress model for {country} yet.",
            style={"color": "var(--muted-color)", "fontSize": "0.85rem", "padding": "20px 0"},
        )]
    comp_dates = load_debt_stress_component_dates(
        country=country, as_of=str(latest.get("as_of")) if latest is not None else end
    )
    return _build_debt_stress_info(latest, theme_name or DEFAULT_THEME, comp_dates, country)


# ── Long-term debt-cycle STAGE section (roadmap Phase C) ─────────────────────

_STAGE_FEATURE_LABELS = [
    ("feat_debt_pct",         "Debt/GDP percentile", "{:.0%} of own history"),
    ("feat_debt_traj",        "Debt/GDP trajectory", "{:+.1f} pp/yr"),
    ("feat_dsr_trend",        "Debt-service trend",  "{:+.2f} pp / 2y"),
    ("feat_r_minus_g",        "Real rate − growth",  "{:+.2f} pp"),
    ("feat_ngdp_minus_yield", "NGDP − yield",        "{:+.2f} pp"),
    ("feat_gov_interest_z",   "Gov interest Z",       "{:+.2f}"),
    ("feat_refi_gap",         "Refinancing gap",      "{:+.2f} pp"),
    ("feat_spread_household", "Spread · household",  "{:+.2f}pp"),
    ("feat_spread_corporate", "Spread · corporate",  "{:+.2f}pp"),
    ("feat_spread_government", "Spread · government", "{:+.2f}pp"),
]


@callback(
    [Output("debt-stage-info", "children"),
     Output("debt-stage-timeline", "figure")],
    [Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("country-store", "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_debt_stage_section(date_range: dict, theme_name: str,
                              country: str = "US", _trigger: Any = None):
    country = (country or "US").upper()
    theme_name = theme_name or DEFAULT_THEME
    stage_colors = _command_center.STAGE_COLORS

    df = load_debt_cycle_stage_history(country=country)
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No stage data — run the pipeline"))
        return [html.Div("Long-Term Cycle Stage — no data yet.",
                         style={"color": "var(--muted-color)"})], fig

    start = (date_range or {}).get("start")
    plot_df = df[df["as_of"] >= pd.Timestamp(start)] if start else df

    labeled = df[df["stage"].notna()]
    latest = labeled.iloc[-1] if not labeled.empty else None

    # ── Info strip: current stage chip + driving features ────────────────────
    children: list = [html.Span("Long-Term Cycle Stage",
                                style={"fontWeight": "700", "fontSize": "0.9rem",
                                       "marginRight": "14px"})]
    if latest is not None:
        stage = str(latest["stage"])
        color = stage_colors.get(stage, "#888")
        conf = latest.get("confidence")
        children.append(html.Span(stage.upper(), style={
            "background": f"{color}26", "border": f"1px solid {color}", "color": color,
            "borderRadius": "4px", "padding": "2px 10px", "fontWeight": "700",
            "fontSize": "0.8rem", "marginRight": "12px"}))
        # Private/sovereign votes (Ray ruling 2026-07-06): headline = worse of
        # the two; show both when they diverge, plus the early-warning flag.
        priv, sov = latest.get("stage_private"), latest.get("stage_sovereign")
        if priv and sov and priv != sov:
            children.append(html.Span(f"private: {priv} · sovereign: {sov}",
                                      style={"color": "var(--muted-color)",
                                             "fontSize": "0.72rem", "marginRight": "12px"}))
        if bool(latest.get("sovereign_squeeze")):
            children.append(html.Span(
                "SOVEREIGN SQUEEZE",
                title="Refinancing gap, government interest/GDP, or government "
                      "debt-service has crossed its threshold — an early-warning "
                      "signal independent of the stage vote (Ray Dalio ruling, "
                      "2026-07-06).",
                style={"color": "#E8A317", "fontSize": "0.68rem", "fontWeight": "800",
                       "letterSpacing": "0.04em", "border": "1px solid #E8A317",
                       "borderRadius": "4px", "padding": "1px 8px", "marginRight": "12px"}))
        spread_flag = latest.get("debt_income_spread_flag")
        if spread_flag in ("warning", "critical"):
            sf_color = "#E8A317" if spread_flag == "warning" else RED
            children.append(html.Span(
                f"DEBT-INCOME SPREAD: {spread_flag.upper()}",
                title="Debt is growing faster than the income available to service it "
                      "in at least one sector — Spread = DebtGrowthRate − "
                      "IncomeGrowthRate (both YoY %), computed per sector from the "
                      "existing debt/GDP ratios. Independent of Sovereign Squeeze "
                      "(Ray Dalio consult, 2026-08-19); see the per-sector values below.",
                style={"color": sf_color, "fontSize": "0.68rem", "fontWeight": "800",
                       "letterSpacing": "0.04em", "border": f"1px solid {sf_color}",
                       "borderRadius": "4px", "padding": "1px 8px", "marginRight": "12px"}))
        as_of_ts = pd.Timestamp(latest["as_of"])
        meta = f"{as_of_ts.year}-Q{as_of_ts.quarter} · {int(latest['n_features'])}/5 features"
        if conf is not None and not pd.isna(conf):
            meta += f" · margin {float(conf):.2f}"
        children.append(html.Span(meta, style={"color": "var(--muted-color)",
                                               "fontSize": "0.75rem"}))
        feat_bits = []
        for col, lbl, fmt in _STAGE_FEATURE_LABELS:
            v = latest.get(col)
            if v is not None and not pd.isna(v):
                feat_bits.append(f"{lbl}: {fmt.format(float(v))}")
        children.append(html.Div("  ·  ".join(feat_bits),
                                 style={"color": "var(--muted-color)",
                                        "fontSize": "0.72rem", "marginTop": "4px"}))
    else:
        children.append(html.Span("no current label — insufficient features",
                                  style={"color": "var(--muted-color)",
                                         "fontSize": "0.8rem"}))

    # ── Timeline: colored quarterly band (row 1) + stage scores (row 2) ──────
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.10, row_heights=[0.28, 0.72])
    seen_stages: set = set()
    band = plot_df[plot_df["stage"].notna()]
    for stage in ("leveraging", "squeeze", "deleveraging", "reflation", "neutral"):
        seg = band[band["stage"] == stage]
        if seg.empty:
            continue
        seen_stages.add(stage)
        fig.add_trace(go.Bar(
            x=seg["as_of"], y=[1.0] * len(seg),
            width=86400000 * 88,                        # ~one quarter in ms
            marker={"color": stage_colors[stage], "line": {"width": 0}},
            name=stage,
            hovertemplate="%{x|%Y-Q%q}<br>" + stage + "<extra></extra>",
        ), row=1, col=1)
    score_traces = [
        ("score_leveraging", "leveraging"), ("score_squeeze", "squeeze"),
        ("score_deleveraging", "deleveraging"), ("score_reflation", "reflation"),
    ]
    for col, stage in score_traces:
        if col in plot_df.columns:
            fig.add_trace(go.Scatter(
                x=plot_df["as_of"], y=plot_df[col],
                name=f"{stage} score", line={"color": stage_colors[stage], "width": 1.3},
                showlegend=False,
                hovertemplate="%{x|%Y-Q%q}<br>" + stage + ": %{y:.2f}<extra></extra>",
            ), row=2, col=1)
    layout = figure_layout(theme_name, "")
    layout["barmode"] = "overlay"
    layout["bargap"] = 0
    layout["margin"] = {"l": 40, "r": 20, "t": 10, "b": 30}
    layout["legend"] = {"orientation": "h", "y": 1.18, "font": {"size": 10}}
    fig.update_layout(**layout)
    fig.update_yaxes(visible=False, range=[0, 1], row=1, col=1)
    fig.update_yaxes(title_text="stage scores", range=[0, 1.05],
                     tickfont={"size": 9}, row=2, col=1)
    return children, fig


def _chi_stress_quadrant(st: float, lt: float) -> str:
    """Combined-quadrant read per the "Indicators Machine" design note §6.

    st = Short-Term Health (CHI, self-normalized Z); lt = Long-Term Stress
    (the existing Debt-Stress composite Z). The note names four cells —
    anything outside those four gets an honest "no sharp read" fallback
    rather than being forced into the nearest one.
    """
    if st > 0.5 and lt < 0:
        return "Late-expansion of the short cycle — long-term debt still manageable."
    if st < 0 and lt > 0:
        return "Entering late-deleveraging — even a mild slowdown gets amplified by the debt squeeze."
    if st > 0 and lt > 0:
        return "Short cycle strong but debt burden building — watch for the stress gauge rising sharply."
    if st < 0 and lt < 0:
        return "Deep contraction, likely driven by the long-term debt crisis."
    return "Near-neutral short cycle — no sharp combined read from this position yet."


@callback(
    Output("chi-stress-scatter", "figure"),
    Output("chi-stress-info", "children"),
    [Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("country-store", "data"),
     Input("page-trigger", "data")],
    prevent_initial_call=False,
)
def update_chi_stress_scatter(
    date_range: dict,
    theme_name: str = DEFAULT_THEME,
    country: str = "US",
    _trigger: Any = None,
) -> tuple[go.Figure, list]:
    country = (country or "US").upper()
    theme_name = theme_name or DEFAULT_THEME

    chi_hist = _global_overview._cycle_health_history(country.lower(), None)
    stress_hist = load_debt_stress_history(country=country)
    if stress_hist.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, f"No Debt-Stress model for {country} yet"))
        return fig, [html.Span(
            f"The Debt-Stress composite (the long-term axis) has no model for {country} yet.",
            style={"color": "var(--muted-color)"})]
    if chi_hist.empty or "chi_adjusted" not in chi_hist:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "Not enough CHI history yet"))
        return fig, [html.Span("—", style={"color": "var(--muted-color)"})]

    sigma = float(chi_hist["chi_adjusted"].dropna().std())
    if not pd.notna(sigma) or sigma <= 0:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "Not enough CHI variance yet"))
        return fig, [html.Span("—", style={"color": "var(--muted-color)"})]
    chi_hist = chi_hist.sort_values("as_of").copy()
    chi_hist["chi_z"] = chi_hist["chi_adjusted"] / sigma
    stress_hist = stress_hist.sort_values("as_of")[["as_of", "stress_score"]]

    # Both sides must carry the same datetime precision: chi_hist is built on a
    # pd.date_range (ns) while stress_hist comes straight from DuckDB (us), and
    # merge_asof rejects the pair outright. See charting_data.align_as_of.
    merged = pd.merge_asof(align_as_of(chi_hist[["as_of", "chi_z"]]),
                            align_as_of(stress_hist),
                            on="as_of", direction="backward")
    merged = merged.dropna(subset=["chi_z", "stress_score"])
    start = (date_range or {}).get("start")
    end   = (date_range or {}).get("end")
    if start:
        merged = merged[merged["as_of"] >= pd.Timestamp(start)]
    if end:
        merged = merged[merged["as_of"] <= pd.Timestamp(end)]
    if merged.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No overlapping history in range"))
        return fig, [html.Span("—", style={"color": "var(--muted-color)"})]

    trail = merged.tail(36)   # ~3yr trail at monthly cadence, matches the old 4-quadrant convention
    latest = merged.iloc[-1]

    fig = go.Figure()
    fig.add_vline(x=0, line_dash="dot", line_color="#888", opacity=0.6)
    fig.add_hline(y=0, line_dash="dot", line_color="#888", opacity=0.6)
    fig.add_hline(y=0.5, line_dash="dot", line_color=AMBER, opacity=0.35)
    fig.add_trace(go.Scatter(
        x=trail["stress_score"], y=trail["chi_z"],
        mode="lines+markers",
        line={"color": "#9AA4B2", "width": 1.2},
        marker={"size": 5, "color": "#9AA4B2", "opacity": 0.55},
        hovertemplate="%{customdata|%Y-%m}<br>Stress Z: %{x:.2f}<br>CHI Z: %{y:.2f}<extra></extra>",
        customdata=trail["as_of"],
        name="Trail (last 36mo)",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[latest["stress_score"]], y=[latest["chi_z"]],
        mode="markers",
        marker={"size": 13, "color": AMBER, "line": {"width": 1.5, "color": "#fff"}},
        hovertemplate="Latest · %{customdata|%Y-%m}<br>Stress Z: %{x:.2f}<br>CHI Z: %{y:.2f}<extra></extra>",
        customdata=[latest["as_of"]],
        name="Latest",
        showlegend=False,
    ))
    fig.update_layout(**figure_layout(theme_name))
    fig.update_layout(
        height=360,
        margin={"l": 48, "r": 20, "t": 10, "b": 40},
        uirevision=f"chi-stress-{country}",
        xaxis_title="Long-Term Stress (Debt-Stress composite Z)",
        yaxis_title="Short-Term Health (CHI, self-normalized Z)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.18)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.18)")

    label = _chi_stress_quadrant(float(latest["chi_z"]), float(latest["stress_score"]))
    info = [
        html.Span(f"As of {latest['as_of']:%Y-%m}: ", style={"fontWeight": "700"}),
        html.Span(label),
    ]
    return fig, info


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
    start = (date_range or {}).get("start")
    end   = (date_range or {}).get("end")
    df = load_debt_stress_history(country=country, start_date=start, end_date=end)

    if df.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, f"No Debt-Stress model for {country} yet"))
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


# ── Signal drill-down modal ───────────────────────────────────────────────────

# Map debt-stress component IDs → the closest signal_id in the signals table
_DEBT_STRESS_DRILL_SIGNAL: dict[str, str | None] = {
    "gov_household_debt_gdp":  "us.credit.gov_debt_gdp",
    "corporate_debt_gdp":      None,   # pure derived ratio; no single signal
    "household_debt_service":  "us.credit.debt_service_ratio",
    "federal_interest_gdp":    "us.fiscal.interest_payments",
    "primary_balance_gdp":     "us.fiscal.primary_balance_gdp",
    "structural_balance":      "us.fiscal.structural_balance",
    "govt_revenue_gdp":        "us.fiscal.govt_receipts_qtr",
}


def _load_signal_binding(signal_id: str) -> dict | None:
    """Return the YAML binding dict for a signal_id, or None if not found."""
    import yaml as _yaml
    parts = signal_id.split(".")
    if len(parts) < 2:
        return None
    country = parts[0].upper()
    binding_suffix = ".".join(parts[1:])

    config_dir = Path(__file__).parent.parent / "config"
    fpath = (
        config_dir / "us_bindings.yaml"
        if country == "US"
        else config_dir / "countries" / f"{country.lower()}_bindings.yaml"
    )
    if not fpath.exists():
        return None
    try:
        with open(fpath) as f:
            data = _yaml.safe_load(f)
    except Exception:
        return None
    for b in data.get("bindings", []):
        if b.get("id") == binding_suffix:
            b["_country"] = country
            return b
    return None


def _load_raw_cache_series(binding: dict) -> tuple[pd.Series | None, str]:
    """Load the raw pre-transformation FRED series for a yoy_pct binding.

    Returns (series, series_id_label) or (None, "") when not applicable.
    Covers FRED yoy_pct signals only — WB/Eurostat/ECB use hash-based filenames.
    """
    from indicators.loader import RAW_CACHE_DIR
    if (str(binding.get("provider", "")).upper() != "FRED"
            or str(binding.get("transformation", "")) != "yoy_pct"):
        return None, ""
    series_id = str(binding.get("series_id", ""))
    if not series_id:
        return None, ""
    cache_path = RAW_CACHE_DIR / f"fred_{series_id}.parquet"
    if not cache_path.exists():
        return None, ""
    try:
        df = pd.read_parquet(cache_path)
        raw = df.iloc[:, 0].dropna() if isinstance(df, pd.DataFrame) else df.dropna()
        return raw, series_id
    except Exception:
        return None, ""


def _build_drill_chart(signal_id: str, window_months: int, theme_name: str) -> go.Figure:
    """Drill-down chart: computed value + Z-score + optional raw underlying level."""
    import duckdb as _ddb
    from dashboard.charting_data import DB_PATH

    con = _ddb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            "SELECT as_of, value, units FROM signals "
            "WHERE id = ? AND value IS NOT NULL ORDER BY as_of",
            [signal_id],
        ).df()
        meta = con.execute(
            "SELECT units, linkage FROM signals WHERE id = ? LIMIT 1",
            [signal_id],
        ).df()
    finally:
        con.close()

    if df.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No data"))
        return fig

    df["as_of"] = pd.to_datetime(df["as_of"])
    units = str(meta["units"].iloc[0]) if not meta.empty else ""

    # ── Rolling Z-score ────────────────────────────────────────────────────────
    if len(df) > 1:
        median_gap_days = float(df["as_of"].diff().dt.days.median())
    else:
        median_gap_days = 30.0
    obs_per_month = 30.44 / max(median_gap_days, 1.0)

    if window_months > 0:
        window_n = max(int(round(window_months * obs_per_month)), 5)
        min_p    = max(window_n // 2, 5)
        win_label = f"{window_months}m rolling"
    else:
        window_n  = len(df)
        min_p     = max(min(window_n, 24), 5)
        win_label = "full-history"

    mu    = df["value"].rolling(window_n, min_periods=min_p).mean()
    sigma = df["value"].rolling(window_n, min_periods=min_p).std()
    df["z"] = ((df["value"] - mu) / sigma).replace([float("inf"), float("-inf")], float("nan"))

    # ── Raw underlying level (FRED yoy_pct signals) ────────────────────────────
    binding = _load_signal_binding(signal_id)
    raw_series, raw_label = _load_raw_cache_series(binding) if binding else (None, "")

    # ── Subplot layout ─────────────────────────────────────────────────────────
    force = signal_id.split(".")[1] if signal_id.count(".") >= 2 else ""
    n_rows = 3 if raw_series is not None else 2

    def _z_fill_color(pos: bool) -> str:
        if force == "inflation":
            return "rgba(92,186,138,0.12)" if pos else "rgba(232,115,76,0.12)"
        return "rgba(232,115,76,0.12)" if pos else "rgba(92,186,138,0.12)"

    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=[0.36, 0.32, 0.32] if n_rows == 3 else [0.55, 0.45],
        vertical_spacing=0.05,
    )

    # ── Row 1: computed value (YoY% or level pass-through) ────────────────────
    fig.add_trace(go.Scatter(
        x=df["as_of"], y=df["value"],
        mode="lines",
        line={"color": "rgba(180,200,255,0.85)", "width": 1.6},
        name=units or "value",
        hovertemplate="%{x|%b %Y}: %{y:.4g}<extra></extra>",
    ), row=1, col=1)

    # ── Row 2: Z-score with ±1σ / ±2σ bands ──────────────────────────────────
    z_valid = df["z"].dropna()
    if not z_valid.empty:
        fig.add_hrect(y0=1,  y1=4,  fillcolor=_z_fill_color(True),  line_width=0, row=2, col=1)
        fig.add_hrect(y0=-4, y1=-1, fillcolor=_z_fill_color(False), line_width=0, row=2, col=1)

    for lvl, dash in [(1, "dot"), (2, "dash"), (-1, "dot"), (-2, "dash")]:
        fig.add_hline(y=lvl, line_dash=dash, line_color="rgba(150,150,150,0.35)",
                      line_width=1, row=2, col=1)
    fig.add_hline(y=0, line_color="rgba(150,150,150,0.5)", line_width=1, row=2, col=1)

    fig.add_trace(go.Scatter(
        x=df["as_of"], y=df["z"],
        mode="lines",
        line={"color": "rgba(200,180,255,0.9)", "width": 1.5},
        name=f"Z ({win_label})",
        hovertemplate="%{x|%b %Y}: Z=%{y:+.2f}<extra></extra>",
    ), row=2, col=1)

    # ── Row 3: raw underlying level ────────────────────────────────────────────
    if raw_series is not None:
        fig.add_trace(go.Scatter(
            x=raw_series.index, y=raw_series.values,
            mode="lines",
            line={"color": "rgba(255,210,100,0.75)", "width": 1.4},
            name=f"Raw: {raw_label}",
            hovertemplate="%{x|%b %Y}: %{y:.4g}<extra></extra>",
        ), row=3, col=1)

    # ── Layout: spike crosshair spanning all panels (mirrors regime history) ───
    layout = figure_layout(theme_name)
    layout.update({
        "margin": {"l": 55, "r": 20, "t": 10, "b": 30},
        "hovermode": "x",
        "hoversubplots": "axis",
        "showlegend": False,
        "uirevision": signal_id,
    })
    fig.update_layout(**layout)
    fig.update_xaxes(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikethickness=1,
        spikecolor="rgba(180,180,180,0.6)",
    )
    fig.update_yaxes(title_text=units or "value", title_font_size=10, row=1, col=1)
    fig.update_yaxes(title_text="Z-score", title_font_size=10, zeroline=False, row=2, col=1)
    if raw_series is not None:
        fig.update_yaxes(title_text=raw_label, title_font_size=10, row=3, col=1)

    return fig


@app.callback(
    Output("signal-drill-id", "data"),
    Input({"type": "signal-link", "index": ALL}, "n_clicks"),
    State({"type": "signal-link", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def _on_signal_link_click(n_clicks_list: list, id_list: list) -> str | None:
    """Store the clicked signal_id whenever any signal link is clicked."""
    if not ctx.triggered or not any(n for n in (n_clicks_list or []) if n):
        raise PreventUpdate
    raw_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
    try:
        import json as _json
        clicked = _json.loads(raw_id)["index"]
    except Exception:
        raise PreventUpdate
    return clicked


@app.callback(
    Output("signal-drill-modal", "is_open"),
    Output("signal-drill-title", "children"),
    Output("signal-drill-chart", "figure"),
    Input("signal-drill-id", "data"),
    State("zscore-window-store",    "data"),
    State("inflation-window-store", "data"),
    State("theme-store",            "data"),
    prevent_initial_call=True,
)
def _open_signal_drill(signal_id: str | None,
                       zscore_window: int,
                       inflation_window: int,
                       theme_name: str) -> tuple:
    """Open the drill-down modal and render the dual-panel chart."""
    if not signal_id:
        raise PreventUpdate

    force = signal_id.split(".")[1] if signal_id.count(".") >= 2 else ""
    window = inflation_window if force == "inflation" else zscore_window

    label = _concept_label(signal_id)
    sid_display = signal_id.replace(".", " · ")
    title = [
        html.Span(label, style={"fontWeight": "700"}),
        html.Span(f"  ·  {sid_display}",
                  style={"fontSize": "0.78rem", "color": "var(--muted-color)",
                         "fontWeight": "400"}),
    ]

    fig = _build_drill_chart(signal_id, int(window or 0), theme_name or DEFAULT_THEME)
    return True, title, fig


# ── Signal info popup callbacks ───────────────────────────────────────────────

_UNITS_LABEL: dict[str, str] = {
    "yoy_pct":          "Year-over-year % change (decimal)",
    "yoy_pct_spread":   "YoY % spread between two series",
    "pct_level":        "Percent level",
    "pct_gdp":          "% of GDP",
    "pct_pot_gdp":      "% of potential GDP",
    "pct_working_age":  "% of working-age population",
    "pct_pop_15plus":   "% of population aged 15+",
    "pct_annual":       "% (annual rate)",
    "pct_total_pop":    "% of total population",
    "net_pct":          "Net % (diffusion / balance-of-opinion)",
    "diffusion_index":  "Diffusion index",
    "index":            "Index",
    "index_2020eq100":  "Index (2020 = 100)",
    "index_2010eq100":  "Index (2010 = 100)",
    "ratio":            "Ratio",
    "thousands":        "Thousands",
    "millions_usd":     "USD millions",
    "billions_usd":     "USD billions",
}
_FREQ_LABEL: dict[str, str] = {
    "M": "Monthly", "Q": "Quarterly", "A": "Annual",
    "W": "Weekly",  "D": "Daily",
}
_FORCE_COLOR: dict[str, str] = {
    "growth":        "#5CBA8A",
    "inflation":     "#E8734C",
    "interest_rate": "#4C9EEB",
    "credit":        "#E8C84C",
    "volatility":    "#B07FE8",
    "master":        "#888",
    "fiscal":        "#9EA8B8",
    "external":      "#78C4C4",
    "demographic":   "#B8A08C",
}


@app.callback(
    Output("signal-info-id", "data"),
    Input({"type": "info-icon", "index": ALL}, "n_clicks"),
    State({"type": "info-icon", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def _on_info_icon_click(n_clicks_list: list, id_list: list) -> str | None:
    if not ctx.triggered or not any(n for n in (n_clicks_list or []) if n):
        raise PreventUpdate
    raw_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
    try:
        import json as _json
        clicked = _json.loads(raw_id)["index"]
    except Exception:
        raise PreventUpdate
    return clicked


@app.callback(
    Output("signal-info-modal", "is_open"),
    Output("signal-info-title", "children"),
    Output("signal-info-content", "children"),
    Input("signal-info-id", "data"),
    prevent_initial_call=True,
)
def _open_signal_info(signal_id: str | None) -> tuple:
    if not signal_id:
        raise PreventUpdate

    import duckdb as _ddb
    from dashboard.charting_data import DB_PATH

    con = _ddb.connect(str(DB_PATH), read_only=True)
    try:
        row = con.execute(
            "SELECT units, linkage, provider, source, is_stale, is_proxy, "
            "       low_history, vintage_available, as_of "
            "FROM signals WHERE id = ? "
            "ORDER BY as_of DESC LIMIT 1",
            [signal_id],
        ).fetchone()
    finally:
        con.close()

    binding = _load_signal_binding(signal_id)

    units_code  = (row[0] if row else None) or (binding or {}).get("units", "")
    linkage     = (row[1] if row else None) or ""
    provider    = (row[2] if row else None) or (binding or {}).get("provider", "")
    source      = (row[3] if row else None) or (binding or {}).get("series_id", "")
    is_stale    = bool(row[4]) if row else False
    is_proxy    = bool(row[5]) if row else False
    low_hist    = bool(row[6]) if row else False
    as_of       = row[8] if row else None

    freq_code   = (binding or {}).get("frequency", "")
    lead_lag    = (binding or {}).get("lead_lag", "")
    force       = signal_id.split(".")[1] if signal_id.count(".") >= 2 else ""

    label = _concept_label(signal_id)
    sid_parts = signal_id.split(".")
    country_badge = sid_parts[0].upper() if len(sid_parts) >= 1 else ""
    force_color = _FORCE_COLOR.get(force, "#888")

    # ── Title ─────────────────────────────────────────────────────────────────
    title_children = [
        html.Span(label, style={"fontWeight": "700"}),
        html.Span(f"  {country_badge}", style={
            "fontSize": "0.72rem", "color": "#888",
            "fontWeight": "400", "marginLeft": "6px",
        }),
    ]

    # ── Badge row ─────────────────────────────────────────────────────────────
    def _badge(text: str, bg: str, fg: str = "#eee") -> html.Span:
        return html.Span(text, style={
            "background": bg, "color": fg,
            "padding": "2px 7px", "borderRadius": "4px",
            "fontSize": "0.72rem", "marginRight": "6px",
            "fontWeight": "600",
        })

    badges = [_badge(force.replace("_", " ").title(), force_color, "#111")]
    if lead_lag:
        ll_colors = {"leading": "#2a5a3a", "coincident": "#2a3a5a",
                     "lagging": "#5a2a2a", "structural": "#3a3a2a"}
        badges.append(_badge(lead_lag.title(), ll_colors.get(lead_lag, "#333")))
    if is_stale:
        badges.append(_badge("stale", "#7a4a00", "#ffcc80"))
    if is_proxy:
        badges.append(_badge("proxy", "#4a4a4a"))
    if low_hist:
        badges.append(_badge("low history", "#3a4a4a"))

    # ── Metadata grid ─────────────────────────────────────────────────────────
    units_display = _UNITS_LABEL.get(str(units_code), str(units_code) if units_code else "—")
    freq_display  = _FREQ_LABEL.get(freq_code, freq_code or "—")
    as_of_display = (
        pd.Timestamp(as_of).strftime("%B %Y") if as_of else "—"
    )

    # Raw units from FRED sidecar — only shown when different from transformed units
    raw_units_display = None
    fred_title = None
    if str((binding or {}).get("provider", "")).upper() == "FRED":
        series_id_for_meta = str((binding or {}).get("series_id", ""))
        if series_id_for_meta:
            from indicators.loader import get_fred_meta
            meta = get_fred_meta(series_id_for_meta)
            fred_title = meta.get("title") or None
            raw_units_short = meta.get("units_short", "")
            sa_short = meta.get("seasonal_adjustment_short", "")
            if raw_units_short:
                raw_label = raw_units_short
                if sa_short and sa_short not in ("Not Seasonally Adjusted", "NSA"):
                    raw_label += f", {sa_short}"
                # Only show if it adds information beyond the transformed units label
                if raw_label.lower() not in units_display.lower():
                    raw_units_display = raw_label

    def _meta_row(label_txt: str, value_content) -> html.Tr:
        return html.Tr([
            html.Td(label_txt, style={
                "color": "var(--muted-color)", "fontSize": "0.78rem",
                "padding": "4px 12px 4px 0", "whiteSpace": "nowrap",
                "fontWeight": "500", "verticalAlign": "top",
            }),
            html.Td(value_content, style={
                "fontSize": "0.82rem", "padding": "4px 0",
                "color": "var(--font-color)", "wordBreak": "break-all",
            }),
        ])

    units_cell = html.Span([
        html.Span(units_display),
        *(
            [html.Span(
                f"  (raw: {raw_units_display})",
                style={"color": "var(--muted-color)", "fontSize": "0.78rem"},
            )]
            if raw_units_display else []
        ),
    ])

    meta_rows = [
        _meta_row("Units",        units_cell),
        _meta_row("Frequency",    freq_display),
        _meta_row("Provider",     provider or "—"),
        _meta_row("Series ID",    source or "—"),
        _meta_row("Last updated", as_of_display),
    ]
    if fred_title:
        meta_rows.insert(0, _meta_row("Series title", fred_title))

    meta_table = html.Table(
        meta_rows,
        style={"width": "100%", "borderCollapse": "collapse", "marginTop": "10px"},
    )

    content = html.Div([
        html.Div(badges, style={"marginBottom": "12px"}),
        html.P(
            linkage or "No description available.",
            style={
                "fontSize": "0.85rem", "color": "var(--font-color)",
                "lineHeight": "1.55", "margin": "0 0 4px 0",
                "borderLeft": f"3px solid {force_color}",
                "paddingLeft": "10px",
            },
        ),
        meta_table,
    ])

    return True, title_children, content


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("CHARTING_PORT", 8502))
    debug = os.environ.get("DASH_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

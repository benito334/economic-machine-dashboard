"""Weight Audit page for the Dash dashboard.

Three panels surfacing the outputs of the weight calibration system:
  1. Force Balance   — G_mass vs I_mass per country; flags ratio outside 0.75–1.33
  2. Correlations    — Heatmap of Z-score correlations within each basket + flagged pairs table
  3. Monte Carlo     — 500-trial importance perturbation → regime outcome distribution

All component IDs are prefixed with "wa-" to avoid collisions.
Callbacks register against the global `dash.get_app()` so this module
must be imported AFTER `dash.Dash()` is instantiated in charting.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from dashboard.themes import DEFAULT_THEME, THEMES, figure_layout
from indicators.composites import (
    compute_force_balance,
    compute_signal_correlation_matrix,
    load_composites_config,
    monte_carlo_regime_sensitivity,
)
from store.store import get_connection

# ── Constants ─────────────────────────────────────────────────────────────────

_Q_COLORS: dict[str, str] = {
    "Expansion":                "#5CBA8A",
    "Inflationary Boom":        "#F4C842",
    "Stagflation":              "#E8734C",
    "Disinflationary Slowdown": "#4C9BE8",
}
_BALANCE_OK_COLOR   = "#5CBA8A"
_BALANCE_WARN_COLOR = "#E8734C"
_BALANCE_LO, _BALANCE_HI = 0.75, 1.33

_PROJECT_ROOT = Path(__file__).parents[1]
_COUNTRIES_DIR = _PROJECT_ROOT / "config" / "countries"


# ── Data helpers ──────────────────────────────────────────────────────────────

def _available_countries() -> list[str]:
    """Return uppercase country codes that have a *_composites.yaml file."""
    codes = []
    for p in sorted(_COUNTRIES_DIR.glob("*_composites.yaml")):
        cc = p.stem.replace("_composites", "").upper()
        codes.append(cc)
    return codes


def _short_label(signal_id: str) -> str:
    """Strip country.force prefix: 'us.inflation.cpi_core' → 'cpi_core'."""
    parts = signal_id.split(".")
    return parts[-1] if len(parts) >= 3 else signal_id


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div([
        # ── Header ───────────────────────────────────────────────────────────
        html.Div([
            html.H4("Weight Audit", style={
                "fontSize": "1.05rem", "fontWeight": "700",
                "color": "var(--font-color)", "margin": "0 0 4px 0",
            }),
            html.Span(
                "Force balance, cross-signal correlations, and Monte Carlo sensitivity "
                "for the selected country's composite weights.",
                style={"fontSize": "0.80rem", "color": "var(--muted-color)"},
            ),
        ], style={"marginBottom": "18px"}),

        # ── Section 1: Force Balance ──────────────────────────────────────────
        _section_header("1 — Force Balance", "All countries; ratio of pre-normalization weight mass (Growth / Inflation). "
                        "Target: 0.75 – 1.33."),
        dcc.Graph(id="wa-force-balance-chart", config={"displayModeBar": False},
                  style={"height": "180px", "marginBottom": "24px"}),

        # ── Section 2: Correlations ───────────────────────────────────────────
        _section_header("2 — Signal Correlations",
                        "Pearson r of monthly Z-score histories. Pairs above |r| = 0.80 in the same basket "
                        "are candidates for importance reduction (anti-redundancy rule)."),
        dbc.Row([
            dbc.Col(dcc.Graph(id="wa-corr-growth",    config={"displayModeBar": False}), width=6),
            dbc.Col(dcc.Graph(id="wa-corr-inflation",  config={"displayModeBar": False}), width=6),
        ], className="mb-2"),
        html.Div(id="wa-flagged-pairs", style={"marginBottom": "24px"}),

        # ── Section 3: Monte Carlo ────────────────────────────────────────────
        _section_header("3 — Monte Carlo Weight Sensitivity",
                        "500 trials: each signal's importance perturbed by ±15% (1σ). "
                        "Scatter shows the cloud of (growth score, inflation score) outcomes. "
                        "Donut shows how often each regime is returned."),
        html.Div(id="wa-mc-caption",
                 style={"fontSize": "0.80rem", "color": "var(--muted-color)", "marginBottom": "10px"}),
        dbc.Row([
            dbc.Col(dcc.Graph(id="wa-mc-scatter",  config={"displayModeBar": False}), width=7),
            dbc.Col(dcc.Graph(id="wa-mc-donut",    config={"displayModeBar": False}), width=5),
        ]),

    ], style={"padding": "16px 20px", "maxWidth": "1400px", "margin": "0 auto"})


def _section_header(title: str, subtitle: str) -> html.Div:
    return html.Div([
        html.H5(title, style={
            "fontSize": "0.88rem", "fontWeight": "700",
            "color": "var(--slider-accent, #E8A317)",
            "margin": "0 0 2px 0", "letterSpacing": "0.03em",
        }),
        html.P(subtitle, style={
            "fontSize": "0.76rem", "color": "var(--muted-color)",
            "margin": "0 0 10px 0", "lineHeight": "1.5",
        }),
    ])


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("wa-force-balance-chart", "figure"),
    [Input("page-trigger", "data"),
     Input("theme-store",  "data")],
    prevent_initial_call=False,
)
def update_force_balance(_, theme_name: str):
    theme_name = theme_name or DEFAULT_THEME
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])

    countries = _available_countries()
    rows = []
    for cc in countries:
        try:
            cfg = load_composites_config(cc)
            g, i, ratio = compute_force_balance(cfg)
            balanced = _BALANCE_LO <= ratio <= _BALANCE_HI
            rows.append({"country": cc, "g_mass": g, "i_mass": i,
                         "ratio": ratio, "balanced": balanced})
        except Exception:
            continue

    if not rows:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No country configs found"))
        return fig

    df = pd.DataFrame(rows)

    fig = go.Figure()
    bar_w = 0.35

    for idx, row in df.iterrows():
        color = _BALANCE_OK_COLOR if row["balanced"] else _BALANCE_WARN_COLOR
        x_offset = idx * 1.2
        ratio_label = f"ratio {row['ratio']:.2f}"
        status = "OK" if row["balanced"] else "WARN"

        fig.add_trace(go.Bar(
            x=[x_offset - bar_w / 2], y=[row["g_mass"]],
            width=[bar_w],
            name="Growth mass" if idx == 0 else None,
            showlegend=(idx == 0),
            marker_color="#5CBA8A",
            text=[f"G {row['g_mass']:.2f}"],
            textposition="outside",
            textfont={"size": 9, "color": t["font_color"]},
        ))
        fig.add_trace(go.Bar(
            x=[x_offset + bar_w / 2], y=[row["i_mass"]],
            width=[bar_w],
            name="Inflation mass" if idx == 0 else None,
            showlegend=(idx == 0),
            marker_color="#E8734C",
            text=[f"I {row['i_mass']:.2f}"],
            textposition="outside",
            textfont={"size": 9, "color": t["font_color"]},
        ))
        # Country label + ratio badge below x-axis handled via annotations
        fig.add_annotation(
            x=x_offset, y=-0.55, xref="x", yref="paper",
            text=f"<b>{row['country']}</b><br><span style='color:{color}'>{ratio_label} {status}</span>",
            showarrow=False,
            font={"size": 9, "color": t["font_color"]},
            align="center",
        )

    # Balance band reference lines
    max_mass = max(max(r["g_mass"], r["i_mass"]) for r in rows)
    fig.update_layout(
        **figure_layout(theme_name),
        height=180,
        barmode="overlay",
        bargap=0,
        showlegend=True,
        legend={"orientation": "h", "y": 1.15, "x": 0, "font": {"size": 9}},
        margin={"l": 40, "r": 20, "t": 20, "b": 55},
        xaxis={
            "showticklabels": False, "showgrid": False,
            "range": [-0.7, len(rows) * 1.2 - 0.5],
            "gridcolor": t["grid_color"],
        },
        yaxis={
            "title": "Mass", "titlefont": {"size": 9},
            "gridcolor": t["grid_color"],
            "range": [0, max_mass * 1.35],
        },
    )
    return fig


@callback(
    [Output("wa-corr-growth",    "figure"),
     Output("wa-corr-inflation", "figure"),
     Output("wa-flagged-pairs",  "children")],
    [Input("country-store", "data"),
     Input("page-trigger",  "data"),
     Input("theme-store",   "data")],
    prevent_initial_call=False,
)
def update_correlations(country: str, _, theme_name: str):
    country = (country or "US").upper()
    theme_name = theme_name or DEFAULT_THEME

    try:
        cfg = load_composites_config(country)
    except FileNotFoundError:
        empty = _empty_fig(theme_name, f"No composites config for {country}")
        return empty, empty, _no_data_msg("No composites config")

    try:
        with get_connection() as conn:
            corr, growth_ids, inflation_ids = compute_signal_correlation_matrix(
                conn, country, cfg, min_periods=24
            )
    except Exception as exc:
        empty = _empty_fig(theme_name, str(exc))
        return empty, empty, _no_data_msg(str(exc))

    if corr.empty:
        empty = _empty_fig(theme_name, "No Z-score data in DB")
        return empty, empty, _no_data_msg("No Z-score data")

    g_fig = _heatmap(corr, growth_ids, "Growth Basket", theme_name)
    i_fig = _heatmap(corr, inflation_ids, "Inflation Basket", theme_name)
    pairs_div = _flagged_pairs_table(corr, growth_ids, inflation_ids, theme_name)
    return g_fig, i_fig, pairs_div


@callback(
    [Output("wa-mc-scatter",  "figure"),
     Output("wa-mc-donut",    "figure"),
     Output("wa-mc-caption",  "children")],
    [Input("country-store", "data"),
     Input("page-trigger",  "data"),
     Input("theme-store",   "data")],
    prevent_initial_call=False,
)
def update_monte_carlo(country: str, _, theme_name: str):
    country = (country or "US").upper()
    theme_name = theme_name or DEFAULT_THEME

    try:
        cfg = load_composites_config(country)
    except FileNotFoundError:
        e = _empty_fig(theme_name, f"No composites config for {country}")
        return e, e, ""

    try:
        with get_connection() as conn:
            result = monte_carlo_regime_sensitivity(conn, country, cfg, n_trials=500, sigma=0.15)
    except Exception as exc:
        e = _empty_fig(theme_name, str(exc))
        return e, e, f"Error: {exc}"

    if not result["outcomes"]:
        e = _empty_fig(theme_name, "No signal data in DB")
        return e, e, "No data"

    outcomes_df = pd.DataFrame(result["outcomes"])
    q_counts = result["quadrant_counts"]
    n_total = len(result["outcomes"])
    base_g = result["base_growth"]
    base_i = result["base_inflation"]

    # Identify base quadrant
    if base_g >= 0 and base_i >= 0:
        base_q = "Inflationary Boom"
    elif base_g >= 0 and base_i < 0:
        base_q = "Expansion"
    elif base_g < 0 and base_i >= 0:
        base_q = "Stagflation"
    else:
        base_q = "Disinflationary Slowdown"

    pct_same = round(q_counts.get(base_q, 0) / n_total * 100, 1)

    scatter_fig = _mc_scatter(outcomes_df, base_g, base_i, base_q, theme_name)
    donut_fig   = _mc_donut(q_counts, n_total, theme_name)
    caption = (
        f"{pct_same}% of trials confirm current {base_q} reading "
        f"(±15% importance perturbation, 500 trials). "
        f"Unperturbed: Growth={base_g:+.3f}, Inflation={base_i:+.3f}."
    )
    return scatter_fig, donut_fig, caption


# ── Figure builders ───────────────────────────────────────────────────────────

def _heatmap(corr: pd.DataFrame, ids: list[str], title: str, theme_name: str) -> go.Figure:
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    sub = corr.reindex(index=ids, columns=ids)
    labels = [_short_label(s) for s in ids]
    z = sub.values.tolist()

    # Build annotation text matrix
    text = []
    for row in sub.values:
        row_text = []
        for val in row:
            row_text.append(f"{val:.2f}" if not np.isnan(val) else "")
        text.append(row_text)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=labels,
        y=labels,
        text=text,
        texttemplate="%{text}",
        textfont={"size": 8},
        colorscale="RdBu",
        zmid=0,
        zmin=-1, zmax=1,
        showscale=True,
        colorbar={"thickness": 10, "len": 0.8, "tickfont": {"size": 8},
                  "title": {"text": "r", "font": {"size": 9}}},
    ))

    # Red outlines on high-correlation off-diagonal cells
    n = len(ids)
    for i in range(n):
        for j in range(n):
            if i != j:
                val = sub.iloc[i, j]
                if not np.isnan(val) and abs(val) >= 0.80:
                    fig.add_shape(
                        type="rect",
                        x0=j - 0.5, x1=j + 0.5,
                        y0=i - 0.5, y1=i + 0.5,
                        line={"color": "#E8734C", "width": 2},
                        fillcolor="rgba(0,0,0,0)",
                    )

    h = max(220, n * 38 + 60)
    fig.update_layout(
        **figure_layout(theme_name, title),
        height=h,
        margin={"l": 80, "r": 10, "t": 36, "b": 60},
        xaxis={"tickfont": {"size": 8}, "tickangle": -35, "showgrid": False},
        yaxis={"tickfont": {"size": 8}, "showgrid": False, "autorange": "reversed"},
    )
    return fig


def _flagged_pairs_table(
    corr: pd.DataFrame,
    growth_ids: list[str],
    inflation_ids: list[str],
    theme_name: str,
) -> html.Div:
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    growth_set = set(growth_ids)
    inflation_set = set(inflation_ids)
    all_ids = list(dict.fromkeys(growth_ids + inflation_ids))

    pairs = []
    for i, id_a in enumerate(all_ids):
        for id_b in all_ids[i + 1:]:
            if id_a not in corr.index or id_b not in corr.index:
                continue
            r = corr.loc[id_a, id_b]
            if pd.isna(r) or abs(r) < 0.70:
                continue
            same = (
                (id_a in growth_set and id_b in growth_set)
                or (id_a in inflation_set and id_b in inflation_set)
            )
            pairs.append({
                "Signal A": _short_label(id_a),
                "Signal B": _short_label(id_b),
                "r": round(float(r), 3),
                "Basket": "SAME" if same else "cross",
                "Flag": "redundant" if same and abs(r) >= 0.80 else ("watch" if abs(r) >= 0.80 else ""),
            })

    pairs.sort(key=lambda x: abs(x["r"]), reverse=True)

    if not pairs:
        return html.P("No pairs above |r| = 0.70 found.", style={
            "fontSize": "0.78rem", "color": "var(--muted-color)"
        })

    th_sty = {
        "padding": "5px 10px", "fontSize": "0.72rem",
        "textTransform": "uppercase", "letterSpacing": "0.05em",
        "color": "var(--muted-color)", "borderBottom": "1px solid var(--border-color)",
        "whiteSpace": "nowrap",
    }
    def _td(val: Any, flag: str, col: str) -> html.Td:
        bg = "transparent"
        color = t["font_color"]
        if flag == "redundant" and col in ("r", "Flag", "Basket"):
            color = _BALANCE_WARN_COLOR
        elif flag == "watch":
            color = "#F4C842"
        sty = {"padding": "4px 10px", "fontSize": "0.80rem",
               "borderBottom": "1px solid var(--border-color)",
               "color": color, "background": bg}
        return html.Td(str(val), style=sty)

    headers = ["Signal A", "Signal B", "r", "Basket", "Flag"]
    rows_html = []
    for p in pairs:
        rows_html.append(html.Tr([_td(p[h], p["Flag"], h) for h in headers]))

    return html.Div([
        html.P("High-correlation pairs (|r| ≥ 0.70):", style={
            "fontSize": "0.76rem", "color": "var(--muted-color)", "marginBottom": "6px"
        }),
        html.Table([
            html.Thead(html.Tr([html.Th(h, style=th_sty) for h in headers])),
            html.Tbody(rows_html),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.80rem"}),
    ])


def _mc_scatter(
    df: pd.DataFrame, base_g: float, base_i: float, base_q: str, theme_name: str
) -> go.Figure:
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    fig = go.Figure()

    # Quadrant background shading
    for (g_pos, i_pos), q_label in [
        ((True, True),   "Inflationary Boom"),
        ((True, False),  "Expansion"),
        ((False, True),  "Stagflation"),
        ((False, False), "Disinflationary Slowdown"),
    ]:
        x0 = 0 if g_pos else -10
        x1 = 10 if g_pos else 0
        y0 = 0 if i_pos else -10
        y1 = 10 if i_pos else 0
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=_Q_COLORS[q_label] + "18",
                      line={"width": 0}, layer="below")
        fig.add_annotation(
            x=(x0 + x1) / 2, y=(y0 + y1) / 2,
            text=q_label, showarrow=False,
            font={"size": 8, "color": _Q_COLORS[q_label]},
            opacity=0.6,
        )

    # Trial scatter points
    for q, color in _Q_COLORS.items():
        sub = df[df["quadrant"] == q]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["growth_score"], y=sub["inflation_score"],
            mode="markers",
            name=q,
            marker={"color": color, "size": 4, "opacity": 0.55},
        ))

    # Base reading (large cross marker)
    fig.add_trace(go.Scatter(
        x=[base_g], y=[base_i],
        mode="markers",
        name="Base (unperturbed)",
        marker={"color": "#ffffff", "size": 14, "symbol": "cross",
                "line": {"color": _Q_COLORS.get(base_q, "#888"), "width": 2}},
        showlegend=True,
    ))

    # Axis lines
    fig.add_hline(y=0, line={"color": t["font_color"], "width": 0.8, "dash": "dot"})
    fig.add_vline(x=0, line={"color": t["font_color"], "width": 0.8, "dash": "dot"})

    # Auto-range with padding
    x_vals = df["growth_score"].tolist() + [base_g]
    y_vals = df["inflation_score"].tolist() + [base_i]
    pad = 0.15
    xr = [min(x_vals) - pad, max(x_vals) + pad]
    yr = [min(y_vals) - pad, max(y_vals) + pad]
    xr = [min(xr[0], -0.1), max(xr[1], 0.1)]
    yr = [min(yr[0], -0.1), max(yr[1], 0.1)]

    fig.update_layout(
        **figure_layout(theme_name, "Monte Carlo Trials"),
        height=340,
        xaxis={"title": "Growth Score", "range": xr, "zeroline": False,
               "gridcolor": t["grid_color"], "titlefont": {"size": 9}},
        yaxis={"title": "Inflation Score", "range": yr, "zeroline": False,
               "gridcolor": t["grid_color"], "titlefont": {"size": 9}},
        legend={"font": {"size": 8}, "y": 1.1, "orientation": "h"},
        margin={"l": 55, "r": 15, "t": 40, "b": 40},
        hovermode="closest",
    )
    return fig


def _mc_donut(q_counts: dict, n_total: int, theme_name: str) -> go.Figure:
    labels = [q for q in _Q_COLORS if q_counts.get(q, 0) > 0]
    values = [q_counts.get(q, 0) for q in labels]
    colors = [_Q_COLORS[q] for q in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker={"colors": colors, "line": {"color": "var(--page-bg)", "width": 2}},
        textinfo="percent",
        textfont={"size": 9},
        hovertemplate="%{label}<br>%{value} trials (%{percent})<extra></extra>",
    ))
    fig.add_annotation(
        text=f"<b>{n_total}</b><br><span style='font-size:9px'>trials</span>",
        x=0.5, y=0.5, showarrow=False,
        font={"size": 12, "color": THEMES.get(theme_name, THEMES[DEFAULT_THEME])["font_color"]},
    )
    fig.update_layout(
        **figure_layout(theme_name, "Regime Distribution"),
        height=340,
        showlegend=True,
        legend={"font": {"size": 8}, "orientation": "v", "x": 1.0},
        margin={"l": 10, "r": 10, "t": 40, "b": 20},
    )
    return fig


def _empty_fig(theme_name: str, msg: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**figure_layout(theme_name, msg), height=260)
    return fig


def _no_data_msg(msg: str) -> html.P:
    return html.P(msg, style={"fontSize": "0.78rem", "color": "var(--muted-color)"})

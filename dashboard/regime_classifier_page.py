"""Threshold-Based Regime Classifier page.

Standalone analysis page that runs the threshold-based classifier
(indicators/regime_classifier.py) and visualises:
  1. Dimension flag timeline heatmap (Growth · Inflation · Rate · Credit · Volatility)
  2. Threshold-classifier quadrant step chart over time
  3. Comparison vs composites-engine labels
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.themes import DEFAULT_THEME, THEMES, figure_layout
from indicators.regime_classifier import (
    CREDIT_SIGNAL_LABELS,
    classify_regimes_threshold,
)
from store.store import get_connection

logger = logging.getLogger(__name__)

_Q_COLORS = {
    "Expansion":               "#5CBA8A",
    "Inflationary Boom":       "#E8734C",
    "Stagflation":             "#F4C842",
    "Disinflationary Slowdown":"#4C9BE8",
    "Transitional":            "#8b97a8",
    "Insufficient Data":       "#444c5a",
}

_Q_Y = {
    "Expansion":               0,
    "Disinflationary Slowdown":1,
    "Inflationary Boom":       2,
    "Stagflation":             3,
}

_DIM_LABELS = {
    "growth":    "Growth",
    "inflation": "Inflation",
    "rate":      "Rate",
    "credit":    "Credit",
    "volatility":"Volatility",
}

_DIMS = ["growth", "inflation", "rate", "credit", "volatility"]

_HEATMAP_CS = [
    [0.00, "#E8734C"],   # -1  red/orange
    [0.50, "#2a2d35"],   # 0   dark grey
    [1.00, "#5CBA8A"],   # +1  green
]


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    credit_options = [{"label": v, "value": k} for k, v in CREDIT_SIGNAL_LABELS.items()]

    return html.Div([
        dcc.Store(id="rc-results-store"),

        # ── Header ──────────────────────────────────────────────────────────
        html.Div([
            html.H4("Threshold-Based Regime Classifier", style={
                "fontSize": "1.05rem", "fontWeight": "700",
                "color": "var(--font-color)", "margin": "0 0 4px 0",
            }),
            html.Span(
                "Classifies each month independently using hard rolling Z-score thresholds "
                "per macro dimension. Results are compared against the composites-engine labels. "
                "Useful as an objective cross-check and as ground truth for Phase 3 calibration.",
                style={"fontSize": "0.80rem", "color": "var(--muted-color)"},
            ),
        ], style={"marginBottom": "18px"}),

        # ── Config panel ─────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Label("Lookback window", style=_lbl_style()),
                dcc.Dropdown(
                    id="rc-lookback",
                    options=[
                        {"label": "5 yr  (60 m)",  "value": 5},
                        {"label": "10 yr (120 m)", "value": 10},
                        {"label": "20 yr (240 m)", "value": 20},
                    ],
                    value=10, clearable=False,
                    style={"fontSize": "0.80rem", "width": "140px"},
                ),
            ], style=_cfg_col()),

            html.Div([
                html.Label("Upper threshold (Z)", style=_lbl_style()),
                dbc.Input(id="rc-upper-thresh", type="number", value=0.5, step=0.1, min=0.0, max=2.0,
                          style=_num_input()),
            ], style=_cfg_col()),

            html.Div([
                html.Label("Lower threshold (Z)", style=_lbl_style()),
                dbc.Input(id="rc-lower-thresh", type="number", value=-0.5, step=0.1, min=-2.0, max=0.0,
                          style=_num_input()),
            ], style=_cfg_col()),

            html.Div([
                html.Label("GDP fill method", style=_lbl_style()),
                dcc.RadioItems(
                    id="rc-fill-method",
                    options=[
                        {"label": "Forward-fill", "value": "ffill"},
                        {"label": "Decay-weighted", "value": "decay"},
                    ],
                    value="ffill",
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"marginRight": "12px", "fontSize": "0.80rem",
                                "color": "var(--font-color)"},
                ),
            ], style=_cfg_col()),

            # Halflife slider — only visible in decay mode
            html.Div([
                html.Label("Decay half-life (months)", style=_lbl_style()),
                dcc.Slider(
                    id="rc-decay-halflife",
                    min=1, max=6, step=0.5, value=2,
                    marks={i: str(i) for i in range(1, 7)},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
            ], id="rc-halflife-div",
               style={**_cfg_col(), "display": "none", "minWidth": "180px"}),

            html.Div([
                html.Label("Credit signal", style=_lbl_style()),
                dcc.Dropdown(
                    id="rc-credit-signal",
                    options=credit_options,
                    value="baa_spread", clearable=False,
                    style={"fontSize": "0.80rem", "width": "200px"},
                ),
            ], style=_cfg_col()),

            html.Div([
                html.Label(" ", style=_lbl_style()),
                html.Button(
                    "▶ Run Classifier",
                    id="rc-run-btn",
                    n_clicks=0,
                    style={
                        "fontSize": "0.82rem", "padding": "5px 16px",
                        "background": "var(--slider-accent, #E8A317)",
                        "color": "#14171e", "border": "none",
                        "borderRadius": "4px", "cursor": "pointer",
                        "fontWeight": "700",
                    },
                ),
            ], style=_cfg_col()),

        ], style={
            "display": "flex", "flexWrap": "wrap", "gap": "18px",
            "alignItems": "flex-end",
            "background": "var(--card-bg)", "borderRadius": "6px",
            "padding": "14px 18px", "marginBottom": "20px",
            "border": "1px solid var(--border-color)",
        }),

        # ── Status / error ───────────────────────────────────────────────────
        html.Div(id="rc-status-msg", style={
            "fontSize": "0.78rem", "color": "var(--muted-color)",
            "marginBottom": "12px", "minHeight": "18px",
        }),

        # ── Results ──────────────────────────────────────────────────────────
        dcc.Loading(id="rc-loading", type="circle", children=[

            # Section 1: Flag Timeline
            _section_hdr("1 — Dimension Flag Timeline",
                "Green (+1) = above upper threshold · Grey (0) = neutral "
                "· Red (−1) = below lower threshold · Blank = insufficient history. "
                "Credit and spread signals are inverted so that +1 always means "
                "favourable / expanding conditions."),
            dcc.Graph(id="rc-flag-heatmap", config={"displayModeBar": False},
                      style={"marginBottom": "24px"}),

            # Section 2: Threshold Quadrant
            _section_hdr("2 — Regime Classification (Threshold)",
                "Quadrant derived from Growth × Inflation flags only, matching the "
                "composites engine's 4-season taxonomy. Transitional = either flag is 0."),
            dcc.Graph(id="rc-quadrant-chart", config={"displayModeBar": False},
                      style={"marginBottom": "24px"}),

            # Section 3: Comparison
            _section_hdr("3 — Comparison: Threshold vs Composites Engine",
                "Both classifiers plotted on the same scale. Months where they disagree "
                "are flagged below the chart. Agreement rate is computed over the "
                "overlapping period where both have a definitive label."),
            dcc.Graph(id="rc-comparison-chart", config={"displayModeBar": False},
                      style={"marginBottom": "12px"}),
            html.Div(id="rc-agreement-summary", style={
                "fontSize": "0.82rem", "color": "var(--muted-color)",
                "marginBottom": "24px",
            }),

        ]),

    ], style={"padding": "16px 20px", "maxWidth": "1400px", "margin": "0 auto"})


# ── Style helpers ─────────────────────────────────────────────────────────────

def _lbl_style() -> dict:
    return {"fontSize": "0.70rem", "fontWeight": "700", "textTransform": "uppercase",
            "letterSpacing": "0.05em", "color": "var(--muted-color)",
            "display": "block", "marginBottom": "4px"}

def _cfg_col() -> dict:
    return {"display": "flex", "flexDirection": "column"}

def _num_input() -> dict:
    return {"width": "90px", "fontSize": "0.80rem",
            "background": "var(--page-bg)", "color": "var(--font-color)",
            "border": "1px solid var(--border-color)", "borderRadius": "4px",
            "padding": "4px 8px"}

def _section_hdr(title: str, subtitle: str) -> html.Div:
    return html.Div([
        html.H5(title, style={
            "fontSize": "0.88rem", "fontWeight": "700",
            "color": "var(--slider-accent, #E8A317)",
            "margin": "0 0 2px 0",
        }),
        html.P(subtitle, style={
            "fontSize": "0.75rem", "color": "var(--muted-color)",
            "margin": "0 0 10px 0", "lineHeight": "1.5",
        }),
    ])


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("rc-halflife-div", "style"),
    Input("rc-fill-method", "value"),
    prevent_initial_call=False,
)
def toggle_halflife_div(fill_method: str):
    base = {**_cfg_col(), "minWidth": "180px"}
    if fill_method == "decay":
        return {**base, "display": "flex"}
    return {**base, "display": "none"}


@callback(
    [Output("rc-results-store", "data"),
     Output("rc-status-msg",   "children")],
    Input("rc-run-btn",         "n_clicks"),
    [State("country-store",     "data"),
     State("rc-lookback",       "value"),
     State("rc-upper-thresh",   "value"),
     State("rc-lower-thresh",   "value"),
     State("rc-fill-method",    "value"),
     State("rc-decay-halflife", "value"),
     State("rc-credit-signal",  "value")],
    prevent_initial_call=True,
)
def run_classifier(n_clicks, country, lookback, upper, lower,
                   fill_method, decay_halflife, credit_signal):
    if not n_clicks:
        raise PreventUpdate

    country = (country or "US").upper()
    upper   = float(upper   or  0.5)
    lower   = float(lower   or -0.5)
    lookback = int(lookback or 10)
    decay_halflife = float(decay_halflife or 2.0)

    try:
        with get_connection() as conn:
            df = classify_regimes_threshold(
                country=country,
                conn=conn,
                lookback_years=lookback,
                upper_threshold=upper,
                lower_threshold=lower,
                quarterly_fill=fill_method,
                decay_halflife=decay_halflife,
                credit_signal=credit_signal,
            )
    except Exception as exc:
        logger.error("run_classifier error: %s", exc, exc_info=True)
        return no_update, html.Span(f"Error: {exc}", style={"color": "#E8734C"})

    if df.empty:
        return no_update, "No data returned — check that the pipeline has been run."

    result = {
        "records": df.to_dict("records"),
        "meta": {
            "country":        country,
            "lookback_years": lookback,
            "upper_threshold": upper,
            "lower_threshold": lower,
            "fill_method":    fill_method,
            "decay_halflife": decay_halflife,
            "credit_signal":  credit_signal,
            "n_months":       len(df),
            "run_time":       datetime.utcnow().isoformat(),
        },
    }

    credit_lbl = CREDIT_SIGNAL_LABELS.get(credit_signal, credit_signal)
    fill_lbl   = f"decay (½-life {decay_halflife}m)" if fill_method == "decay" else "forward-fill"
    msg = (f"Ran {len(df)} months for {country} | "
           f"lookback={lookback}yr | thresholds [{lower:+.1f}, {upper:+.1f}] | "
           f"GDP fill: {fill_lbl} | credit: {credit_lbl}")
    return result, msg


@callback(
    Output("rc-flag-heatmap", "figure"),
    [Input("rc-results-store", "data"),
     Input("theme-store",      "data")],
    prevent_initial_call=True,
)
def update_flag_heatmap(results, theme_name):
    if not results:
        raise PreventUpdate
    theme_name = theme_name or DEFAULT_THEME
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    df = pd.DataFrame(results["records"])
    df["as_of"] = pd.to_datetime(df["as_of"])

    dim_labels = [_DIM_LABELS[d] for d in _DIMS]
    z = []
    for dim in _DIMS:
        col = f"{dim}_flag"
        if col in df.columns:
            z.append(df[col].tolist())
        else:
            z.append([np.nan] * len(df))

    customdata = []
    for dim in _DIMS:
        z_col = f"{dim}_z"
        if z_col in df.columns:
            customdata.append(df[z_col].round(3).tolist())
        else:
            customdata.append([np.nan] * len(df))

    # Build hover text matrix
    hover = []
    for i, dim in enumerate(_DIMS):
        row_hover = []
        for j in range(len(df)):
            flag_val = z[i][j]
            z_val    = customdata[i][j]
            flag_str = f"{int(flag_val):+d}" if not np.isnan(flag_val) else "N/A"
            z_str    = f"{z_val:.3f}" if not np.isnan(z_val) else "N/A"
            row_hover.append(
                f"<b>{_DIM_LABELS[dim]}</b><br>"
                f"Date: {df['as_of'].iloc[j].strftime('%Y-%m')}<br>"
                f"Flag: {flag_str} | Z: {z_str}"
            )
        hover.append(row_hover)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=df["as_of"].dt.strftime("%Y-%m").tolist(),
        y=dim_labels,
        colorscale=_HEATMAP_CS,
        zmin=-1.5, zmax=1.5,
        showscale=True,
        colorbar={
            "tickvals": [-1, 0, 1],
            "ticktext": ["−1", "0", "+1"],
            "thickness": 10, "len": 0.7,
            "tickfont": {"size": 8},
            "title": {"text": "Flag", "font": {"size": 9}},
        },
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover,
    ))

    fig.update_layout(**figure_layout(theme_name, "Dimension Flags"))
    fig.update_layout(
        height=260,
        margin={"l": 80, "r": 20, "t": 40, "b": 40},
        xaxis={
            "type": "category",
            "tickangle": -45,
            "tickfont": {"size": 8},
            "nticks": 24,
            "gridcolor": t["grid_color"],
        },
        yaxis={
            "tickfont": {"size": 9},
            "gridcolor": t["grid_color"],
        },
    )
    return fig


@callback(
    Output("rc-quadrant-chart", "figure"),
    [Input("rc-results-store", "data"),
     Input("theme-store",      "data")],
    prevent_initial_call=True,
)
def update_quadrant_chart(results, theme_name):
    if not results:
        raise PreventUpdate
    theme_name = theme_name or DEFAULT_THEME
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    df = pd.DataFrame(results["records"])
    df["as_of"] = pd.to_datetime(df["as_of"])

    fig = go.Figure()

    for q_label, y_val in _Q_Y.items():
        sub = df[df["quadrant_label"] == q_label]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["as_of"],
            y=[y_val] * len(sub),
            mode="markers",
            name=q_label,
            marker={
                "color": _Q_COLORS.get(q_label, "#888"),
                "size": 7,
                "symbol": "square",
                "opacity": 0.85,
            },
            hovertemplate=f"<b>{q_label}</b><br>%{{x|%Y-%m}}<extra></extra>",
        ))

    # Transitional dots
    trans = df[~df["quadrant_label"].isin(_Q_Y)]
    if not trans.empty:
        fig.add_trace(go.Scatter(
            x=trans["as_of"], y=[1.5] * len(trans),
            mode="markers", name="Transitional / No data",
            marker={"color": "#555e6d", "size": 5, "symbol": "circle-open"},
            hovertemplate="<b>%{customdata}</b><br>%{x|%Y-%m}<extra></extra>",
            customdata=trans["quadrant_label"].tolist(),
        ))

    fig.update_layout(**figure_layout(theme_name, "Threshold Classifier — Quadrant over Time"))
    fig.update_layout(
        height=280,
        margin={"l": 155, "r": 20, "t": 40, "b": 40},
        xaxis={"gridcolor": t["grid_color"]},
        yaxis={
            "tickvals": list(_Q_Y.values()),
            "ticktext": list(_Q_Y.keys()),
            "gridcolor": t["grid_color"],
            "tickfont": {"size": 9},
        },
        legend={"font": {"size": 8}, "orientation": "h", "y": -0.2},
    )
    return fig


@callback(
    [Output("rc-comparison-chart",   "figure"),
     Output("rc-agreement-summary",  "children")],
    [Input("rc-results-store", "data"),
     Input("theme-store",      "data")],
    State("country-store",     "data"),
    prevent_initial_call=True,
)
def update_comparison(results, theme_name, country):
    if not results:
        raise PreventUpdate
    theme_name = theme_name or DEFAULT_THEME
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    country = (country or "US").upper()

    thresh_df = pd.DataFrame(results["records"])
    thresh_df["as_of"] = pd.to_datetime(thresh_df["as_of"])

    # Load composites labels from DB
    try:
        with get_connection() as conn:
            comp_df = conn.execute(
                "SELECT as_of, quadrant FROM composites WHERE country = ? "
                "AND quadrant IS NOT NULL ORDER BY as_of",
                [country],
            ).df()
    except Exception as exc:
        empty_fig = go.Figure()
        empty_fig.update_layout(**figure_layout(theme_name, f"DB error: {exc}"))
        return empty_fig, f"Could not load composites: {exc}"

    comp_df["as_of"] = pd.to_datetime(comp_df["as_of"])

    fig = go.Figure()

    # ── Threshold trace ───────────────────────────────────────────────────────
    for q_label, y_val in _Q_Y.items():
        sub = thresh_df[thresh_df["quadrant_label"] == q_label]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["as_of"], y=[y_val + 0.15] * len(sub),
            mode="markers", name=f"{q_label} (Threshold)",
            marker={"color": _Q_COLORS.get(q_label, "#888"),
                    "size": 7, "symbol": "square", "opacity": 0.85},
            legendgroup=q_label,
            hovertemplate=f"<b>Threshold: {q_label}</b><br>%{{x|%Y-%m}}<extra></extra>",
        ))

    # ── Composites trace ──────────────────────────────────────────────────────
    for q_label, y_val in _Q_Y.items():
        sub = comp_df[comp_df["quadrant"] == q_label]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["as_of"], y=[y_val - 0.15] * len(sub),
            mode="markers", name=f"{q_label} (Composites)",
            marker={"color": _Q_COLORS.get(q_label, "#888"),
                    "size": 7, "symbol": "diamond", "opacity": 0.55},
            legendgroup=q_label, showlegend=False,
            hovertemplate=f"<b>Composites: {q_label}</b><br>%{{x|%Y-%m}}<extra></extra>",
        ))

    # Row labels
    fig.add_annotation(x=thresh_df["as_of"].min(), y=3.5,
                       text="▪ squares = Threshold  ◆ diamonds = Composites",
                       showarrow=False, xanchor="left",
                       font={"size": 8, "color": t["font_color"]}, opacity=0.6)

    fig.update_layout(**figure_layout(theme_name, f"Threshold vs Composites — {country}"))
    fig.update_layout(
        height=310,
        margin={"l": 155, "r": 20, "t": 40, "b": 50},
        xaxis={"gridcolor": t["grid_color"]},
        yaxis={
            "tickvals": list(_Q_Y.values()),
            "ticktext": list(_Q_Y.keys()),
            "gridcolor": t["grid_color"],
            "tickfont": {"size": 9},
        },
        legend={"font": {"size": 8}, "orientation": "h", "y": -0.25},
    )

    # ── Agreement summary ────────────────────────────────────────────────────
    merged = pd.merge(
        thresh_df[["as_of", "quadrant_label"]].rename(columns={"quadrant_label": "thresh_q"}),
        comp_df[["as_of", "quadrant"]].rename(columns={"quadrant": "comp_q"}),
        on="as_of", how="inner",
    )
    definitive = merged[
        merged["thresh_q"].isin(_Q_Y) & merged["comp_q"].isin(_Q_Y)
    ]
    if definitive.empty:
        summary = "No overlapping months with definitive labels in both classifiers."
    else:
        agree = (definitive["thresh_q"] == definitive["comp_q"]).sum()
        total = len(definitive)
        pct   = round(agree / total * 100, 1)
        disagree_months = definitive[definitive["thresh_q"] != definitive["comp_q"]]
        n_disagree = len(disagree_months)
        summary = (
            f"Agreement: {agree}/{total} months ({pct}%) over overlapping definitive period. "
            f"{n_disagree} divergence month(s)."
        )
        if n_disagree and n_disagree <= 10:
            dates = ", ".join(disagree_months["as_of"].dt.strftime("%Y-%m").tolist())
            summary += f"  Divergences: {dates}."

    return fig, summary

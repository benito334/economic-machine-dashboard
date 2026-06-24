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
import re

from dash import ALL, Input, Output, State, callback, dash_table, dcc, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.themes import DEFAULT_THEME, THEMES, figure_layout
from indicators.composites import (
    compute_force_balance,
    compute_signal_correlation_matrix,
    load_composites_config,
    monte_carlo_regime_sensitivity,
)
from indicators.calibrate import calibrate_growth_weights
from store.store import get_connection, log_weight_changes

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


def _hex_alpha(hex_color: str, alpha_hex: str = "18") -> str:
    """Convert '#RRGGBB' + 2-digit alpha hex string to 'rgba(r,g,b,a)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = round(int(alpha_hex, 16) / 255, 3)
    return f"rgba({r},{g},{b},{a})"


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


def _importance_tier(imp: float) -> str:
    if imp >= 0.85: return "PRIMARY"
    if imp >= 0.60: return "STRONG"
    if imp >= 0.30: return "CONTEXT"
    return "VOLATILE"


def _load_editor_rows(cc: str) -> list[dict]:
    """Flatten composites config into table rows for the importance editor."""
    cfg = load_composites_config(cc)
    rows = []
    for basket, key in [("Growth", "growth_score"), ("Inflation", "inflation_score")]:
        for ind in cfg[key]["indicators"]:
            imp = round(float(ind.get("importance", 1.0)), 2)
            bs  = float(ind.get("base_share",    1.0))
            qf  = float(ind.get("quality_factor", 1.0))
            rows.append({
                "yaml_id":       ind["id"],          # key used in YAML (no country prefix)
                "label":         ind["id"].split(".")[-1],
                "basket":        basket,
                "base_share":    round(bs, 2),
                "importance":    imp,
                "tier":          _importance_tier(imp),
                "quality_factor": round(qf, 2),
                "raw_weight":    round(bs * imp * qf, 3),
            })
    return rows


def _replace_importance_in_yaml(text: str, signal_id: str, new_val: float) -> str:
    """Replace importance value for signal_id in YAML text, preserving inline comments."""
    lines = text.split("\n")
    in_block = False
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.endswith(f"id: {signal_id}") or stripped == f"- id: {signal_id}":
            in_block = True
        elif in_block and stripped.startswith("- id:"):
            in_block = False
        if in_block and re.match(r"\s+importance:", line):
            comment_m = re.search(r"(#.*)", line)
            comment = "  " + comment_m.group(1) if comment_m else ""
            indent = len(line) - len(line.lstrip())
            line = f"{' ' * indent}importance: {new_val:.2f}{comment}"
        result.append(line)
    return "\n".join(result)


def _write_importance_updates(cc: str, updates: dict[str, float]) -> tuple[bool, str]:
    """Write importance updates to {cc}_composites.yaml, preserving comments."""
    yaml_path = _COUNTRIES_DIR / f"{cc.lower()}_composites.yaml"
    if not yaml_path.exists():
        return False, f"File not found: {yaml_path.name}"
    text = yaml_path.read_text()
    for sid, val in updates.items():
        val = round(max(0.10, min(1.00, float(val))), 2)
        text = _replace_importance_in_yaml(text, sid, val)
    yaml_path.write_text(text)
    return True, f"Saved {len(updates)} value(s) to {cc.lower()}_composites.yaml — audit panels updated."


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div([
        dcc.Store(id="wa-run-store",      data=0),
        dcc.Store(id="wa-editor-original", data=[]),

        # ── Header ───────────────────────────────────────────────────────────
        html.Div([
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
            ]),
            html.Button(
                "↺ Re-run",
                id="wa-rerun-btn",
                n_clicks=0,
                style={
                    "fontSize": "0.78rem", "padding": "4px 12px",
                    "background": "var(--card-bg)", "color": "var(--slider-accent, #E8A317)",
                    "border": "1px solid var(--slider-accent, #E8A317)",
                    "borderRadius": "4px", "cursor": "pointer",
                    "whiteSpace": "nowrap", "alignSelf": "flex-start",
                },
            ),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "marginBottom": "18px"}),

        # ── Section 1: Force Balance ──────────────────────────────────────────
        _section_header("1 — Force Balance",
                        "All countries; ratio of pre-normalization weight mass (Growth / Inflation). "
                        "Target: 0.75 – 1.33. Run automatically on every pipeline Pass 5."),
        dcc.Graph(id="wa-force-balance-chart", config={"displayModeBar": False},
                  style={"height": "180px", "marginBottom": "24px"}),

        # ── Section 2: Correlations ───────────────────────────────────────────
        _section_header("2 — Signal Correlations",
                        "Pearson r of monthly Z-score histories. Pairs above |r| = 0.80 in the same basket "
                        "are flagged by the anti-redundancy rule. Correlation audit also runs on pipeline Pass 5."),
        dbc.Row([
            dbc.Col(dcc.Graph(id="wa-corr-growth",    config={"displayModeBar": False}), width=6),
            dbc.Col(dcc.Graph(id="wa-corr-inflation",  config={"displayModeBar": False}), width=6),
        ], className="mb-2"),
        html.Div(id="wa-flagged-pairs", style={"marginBottom": "24px"}),

        # ── Section 3: Monte Carlo ────────────────────────────────────────────
        _section_header("3 — Monte Carlo Weight Sensitivity",
                        "500 trials: each signal's importance perturbed by ±15% (1σ). "
                        "Scatter shows the cloud of (growth score, inflation score) outcomes. "
                        "Donut shows how often each regime is returned. On-demand only — not run in pipeline."),
        html.Div(id="wa-mc-caption",
                 style={"fontSize": "0.80rem", "color": "var(--muted-color)", "marginBottom": "10px"}),
        dbc.Row([
            dbc.Col(dcc.Graph(id="wa-mc-scatter",  config={"displayModeBar": False}), width=7),
            dbc.Col(dcc.Graph(id="wa-mc-donut",    config={"displayModeBar": False}), width=5),
        ]),

        html.Hr(style={"borderColor": "var(--border-color)", "margin": "28px 0 20px 0"}),

        # ── Section 4: Importance Editor ─────────────────────────────────────
        html.Div([
            _section_header("4 — Importance Editor",
                            "Edit signal importance values for the selected country. "
                            "Importance is clamped to 0.10 – 1.00. "
                            "Tier and Raw Weight update as you type. "
                            "Save writes back to config/{cc}_composites.yaml (preserving comments) "
                            "and re-runs all audit panels above. "
                            "Run the pipeline separately to apply changes to composite history."),
            dcc.Clipboard(
                id="wa-editor-copy-btn",
                content="",
                title="Copy table as TSV",
                style={
                    "position": "absolute", "top": "0", "right": "0",
                    "fontSize": "0.75rem", "padding": "3px 9px",
                    "background": "var(--card-bg)",
                    "color": "var(--muted-color)",
                    "border": "1px solid var(--border-color)",
                    "borderRadius": "4px", "cursor": "pointer",
                },
            ),
        ], style={"position": "relative"}),

        dash_table.DataTable(
            id="wa-editor-table",
            columns=[
                {"name": "Signal",         "id": "label",         "editable": False},
                {"name": "Basket",         "id": "basket",        "editable": False},
                {"name": "base_share",     "id": "base_share",    "editable": False, "type": "numeric"},
                {"name": "importance",     "id": "importance",    "editable": True,  "type": "numeric",
                 "format": {"specifier": ".2f"}},
                {"name": "Tier",           "id": "tier",          "editable": False},
                {"name": "quality_factor", "id": "quality_factor","editable": False, "type": "numeric"},
                {"name": "Raw Weight",     "id": "raw_weight",    "editable": False, "type": "numeric",
                 "format": {"specifier": ".3f"}},
            ],
            data=[],
            editable=True,
            row_selectable=False,
            cell_selectable=True,
            style_table={"overflowX": "auto", "marginBottom": "12px"},
            style_header={
                "backgroundColor": "var(--card-bg, #1e2128)",
                "color": "var(--muted-color, #8b97a8)",
                "fontSize": "0.70rem", "fontWeight": "700",
                "textTransform": "uppercase", "letterSpacing": "0.05em",
                "borderBottom": "1px solid var(--border-color, #2a2d35)",
                "padding": "6px 10px",
            },
            style_cell={
                "backgroundColor": "var(--page-bg, #14171e)",
                "color": "var(--font-color, #d4dae4)",
                "fontSize": "0.82rem",
                "border": "none",
                "borderBottom": "1px solid var(--border-color, #2a2d35)",
                "padding": "5px 10px",
                "fontFamily": "inherit",
            },
            style_cell_conditional=[
                {"if": {"column_id": "importance"},
                 "backgroundColor": "var(--card-bg, #1e2128)",
                 "fontWeight": "600", "color": "var(--slider-accent, #E8A317)"},
            ],
            style_data_conditional=[
                {"if": {"filter_query": '{tier} = "PRIMARY"',  "column_id": "tier"},
                 "color": "#5CBA8A", "fontWeight": "700"},
                {"if": {"filter_query": '{tier} = "STRONG"',   "column_id": "tier"},
                 "color": "#4C9BE8"},
                {"if": {"filter_query": '{tier} = "CONTEXT"',  "column_id": "tier"},
                 "color": "#F4C842"},
                {"if": {"filter_query": '{tier} = "VOLATILE"', "column_id": "tier"},
                 "color": "#8b97a8"},
                {"if": {"filter_query": '{basket} = "Growth"', "column_id": "basket"},
                 "color": "#5CBA8A"},
                {"if": {"filter_query": '{basket} = "Inflation"', "column_id": "basket"},
                 "color": "#E8734C"},
            ],
            style_as_list_view=True,
        ),

        # Live G/I ratio preview
        html.Div(id="wa-editor-ratio-preview",
                 style={"fontSize": "0.80rem", "color": "var(--muted-color)",
                        "marginBottom": "12px"}),

        # Reason input + action buttons
        html.Div([
            dbc.Input(
                id="wa-editor-reason",
                placeholder="Reason for change (recorded in change log)…",
                type="text",
                style={
                    "fontSize": "0.80rem", "flex": "1",
                    "background": "var(--card-bg)", "color": "var(--font-color)",
                    "border": "1px solid var(--border-color)", "borderRadius": "4px",
                    "padding": "4px 10px", "marginRight": "10px",
                },
            ),
        ], style={"display": "flex", "marginBottom": "8px"}),
        html.Div([
            html.Button(
                "↺ Reset",
                id="wa-editor-reset-btn",
                n_clicks=0,
                style={
                    "fontSize": "0.78rem", "padding": "4px 12px",
                    "background": "transparent",
                    "color": "var(--muted-color)", "border": "1px solid var(--border-color)",
                    "borderRadius": "4px", "cursor": "pointer", "marginRight": "8px",
                },
            ),
            html.Button(
                "💾 Save to config",
                id="wa-editor-save-btn",
                n_clicks=0,
                style={
                    "fontSize": "0.78rem", "padding": "4px 14px",
                    "background": "var(--slider-accent, #E8A317)",
                    "color": "#14171e", "border": "none",
                    "borderRadius": "4px", "cursor": "pointer", "fontWeight": "700",
                },
            ),
            html.Span(id="wa-editor-save-msg", style={
                "fontSize": "0.78rem", "marginLeft": "14px",
                "color": "var(--muted-color)",
            }),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),

        html.P(
            "Changes take effect in audit panels immediately after save. "
            "To apply to composite history (Regime Map page), re-run the pipeline: "
            "python3 -m indicators.pipeline",
            style={"fontSize": "0.72rem", "color": "var(--muted-color)",
                   "marginTop": "6px", "fontStyle": "italic"},
        ),

        html.Hr(style={"borderColor": "var(--border-color)", "margin": "28px 0 20px 0"}),

        # ── Section 5: GDP Regression Calibration ────────────────────────────
        dcc.Store(id="wa-calib-store", data=None),
        _section_header("5 — GDP-Regression Calibration (Growth)",
                        "OLS regression of each growth signal's Z-score against real GDP Z-score "
                        "(quarterly, full history). β > 0 → contribution to GDP explained variance. "
                        "Recommended importance scales the highest-β signal to 0.95; others proportionally, floor 0.10. "
                        "Signals with β ≤ 0 receive no recommendation — keep current importance (Option B). "
                        "On-demand only."),
        html.Div([
            html.Button(
                "▶ Run Regression",
                id="wa-calib-run-btn",
                n_clicks=0,
                style={
                    "fontSize": "0.78rem", "padding": "4px 14px",
                    "background": "var(--card-bg)",
                    "color": "var(--slider-accent, #E8A317)",
                    "border": "1px solid var(--slider-accent, #E8A317)",
                    "borderRadius": "4px", "cursor": "pointer", "marginRight": "10px",
                },
            ),
            html.Span(id="wa-calib-status",
                      style={"fontSize": "0.78rem", "color": "var(--muted-color)"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),

        html.Div(id="wa-calib-table-container", style={"marginBottom": "10px"}),

        html.Div([
            html.Button(
                "↓ Apply selected to Editor",
                id="wa-calib-apply-btn",
                n_clicks=0,
                disabled=True,
                style={
                    "fontSize": "0.78rem", "padding": "4px 14px",
                    "background": "transparent",
                    "color": "var(--muted-color)", "border": "1px solid var(--border-color)",
                    "borderRadius": "4px", "cursor": "pointer",
                },
            ),
            html.Span(
                "Applies recommended importance for checked rows into the editor above. "
                "Review and save from there.",
                style={"fontSize": "0.72rem", "color": "var(--muted-color)",
                       "marginLeft": "10px"},
            ),
        ], style={"display": "flex", "alignItems": "center"}),

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
    Output("wa-run-store", "data"),
    Input("wa-rerun-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _rerun(n_clicks: int) -> int:
    return n_clicks or 0


@callback(
    Output("wa-force-balance-chart", "figure"),
    [Input("page-trigger", "data"),
     Input("theme-store",  "data"),
     Input("wa-run-store", "data")],
    prevent_initial_call=False,
)
def update_force_balance(_, theme_name: str, _run=None):
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
    fig.update_layout(**figure_layout(theme_name))
    fig.update_layout(
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
            "title": {"text": "Mass", "font": {"size": 9}},
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
     Input("theme-store",   "data"),
     Input("wa-run-store",  "data")],
    prevent_initial_call=False,
)
def update_correlations(country: str, _, theme_name: str, _run=None):
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
     Input("theme-store",   "data"),
     Input("wa-run-store",  "data")],
    prevent_initial_call=False,
)
def update_monte_carlo(country: str, _, theme_name: str, _run=None):
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
    fig.update_layout(**figure_layout(theme_name, title))
    fig.update_layout(
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
                      fillcolor=_hex_alpha(_Q_COLORS[q_label]),
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

    fig.update_layout(**figure_layout(theme_name, "Monte Carlo Trials"))
    fig.update_layout(
        height=340,
        xaxis={"title": {"text": "Growth Score", "font": {"size": 9}},
               "range": xr, "zeroline": False, "gridcolor": t["grid_color"]},
        yaxis={"title": {"text": "Inflation Score", "font": {"size": 9}},
               "range": yr, "zeroline": False, "gridcolor": t["grid_color"]},
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
    fig.update_layout(**figure_layout(theme_name, "Regime Distribution"))
    fig.update_layout(
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


# ── Editor callbacks ──────────────────────────────────────────────────────────

_EDITOR_COLS = [
    ("Signal",         "label"),
    ("Basket",         "basket"),
    ("base_share",     "base_share"),
    ("importance",     "importance"),
    ("Tier",           "tier"),
    ("quality_factor", "quality_factor"),
    ("Raw Weight",     "raw_weight"),
]


@callback(
    Output("wa-editor-copy-btn", "content"),
    Input("wa-editor-table", "data"),
    prevent_initial_call=False,
)
def _update_editor_clipboard(rows):
    if not rows:
        return ""
    header = "\t".join(h for h, _ in _EDITOR_COLS)
    lines = [header]
    for row in rows:
        lines.append("\t".join(str(row.get(k, "")) for _, k in _EDITOR_COLS))
    return "\n".join(lines)


@callback(
    [Output("wa-editor-table",    "data"),
     Output("wa-editor-original", "data")],
    [Input("country-store",  "data"),
     Input("page-trigger",   "data")],
    prevent_initial_call=False,
)
def populate_editor_table(country: str, _):
    country = (country or "US").upper()
    try:
        rows = _load_editor_rows(country)
    except Exception:
        return [], []
    return rows, rows


@callback(
    [Output("wa-editor-table",        "data",   allow_duplicate=True),
     Output("wa-editor-ratio-preview","children")],
    Input("wa-editor-table", "data"),
    prevent_initial_call=True,
)
def update_derived_columns(rows):
    if not rows:
        return no_update, ""
    g_mass = i_mass = 0.0
    updated = []
    for r in rows:
        try:
            imp = float(r.get("importance") or 0.10)
        except (TypeError, ValueError):
            imp = 0.10
        imp = round(max(0.10, min(1.00, imp)), 2)
        bs  = float(r.get("base_share",    1.0))
        qf  = float(r.get("quality_factor", 1.0))
        rw  = round(bs * imp * qf, 3)
        tier = _importance_tier(imp)
        r = {**r, "importance": imp, "tier": tier, "raw_weight": rw}
        updated.append(r)
        if r["basket"] == "Growth":
            g_mass += rw
        else:
            i_mass += rw

    ratio = g_mass / i_mass if i_mass > 0 else 0.0
    ok = _BALANCE_LO <= ratio <= _BALANCE_HI
    color = _BALANCE_OK_COLOR if ok else _BALANCE_WARN_COLOR
    status = "OK" if ok else "OUT OF RANGE — adjust base_share or importance"
    preview = html.Span([
        "Live G/I ratio: ",
        html.Strong(f"{ratio:.2f}", style={"color": color}),
        f"  (G mass {g_mass:.3f} / I mass {i_mass:.3f})  ",
        html.Span(status, style={"color": color, "fontSize": "0.76rem"}),
    ])
    return updated, preview


@callback(
    Output("wa-editor-table", "data", allow_duplicate=True),
    Input("wa-editor-reset-btn", "n_clicks"),
    State("wa-editor-original",  "data"),
    prevent_initial_call=True,
)
def reset_editor_table(n_clicks, original):
    if not n_clicks or not original:
        raise PreventUpdate
    return original


@callback(
    [Output("wa-editor-save-msg", "children"),
     Output("wa-run-store",       "data",     allow_duplicate=True)],
    Input("wa-editor-save-btn", "n_clicks"),
    [State("wa-editor-table",    "data"),
     State("wa-editor-original", "data"),
     State("wa-editor-reason",   "value"),
     State("country-store",      "data"),
     State("wa-run-store",       "data")],
    prevent_initial_call=True,
)
def save_importance(n_clicks, rows, original_rows, reason, country, run_count):
    if not n_clicks or not rows:
        raise PreventUpdate
    country = (country or "US").upper()

    # Build old-importance lookup from original snapshot
    orig_map = {r["yaml_id"]: float(r["importance"]) for r in (original_rows or []) if r.get("yaml_id")}
    basket_map = {r["yaml_id"]: r.get("basket", "") for r in (original_rows or []) if r.get("yaml_id")}

    updates = {
        r["yaml_id"]: float(r["importance"])
        for r in rows
        if r.get("yaml_id") and r.get("importance") is not None
    }
    ok, msg = _write_importance_updates(country, updates)
    if not ok:
        return html.Span(msg, style={"color": _BALANCE_WARN_COLOR}), run_count

    # Log changes to DuckDB
    change_records = [
        {
            "country":        country,
            "signal_id":      yaml_id,
            "basket":         basket_map.get(yaml_id, ""),
            "old_importance": orig_map.get(yaml_id, new_val),
            "new_importance": new_val,
        }
        for yaml_id, new_val in updates.items()
    ]
    try:
        with get_connection() as conn:
            logged = log_weight_changes(
                conn, change_records,
                reason=reason or "",
                source="manual",
            )
        if logged:
            msg += f" {logged} change(s) logged."
    except Exception as exc:
        msg += f" (log error: {exc})"

    color = _BALANCE_OK_COLOR if ok else _BALANCE_WARN_COLOR
    return html.Span(msg, style={"color": color}), (run_count or 0) + 1


# ── Section 5 — calibration callbacks ────────────────────────────────────────

@callback(
    [Output("wa-calib-store",          "data"),
     Output("wa-calib-table-container","children"),
     Output("wa-calib-status",         "children"),
     Output("wa-calib-apply-btn",      "disabled")],
    Input("wa-calib-run-btn", "n_clicks"),
    [State("country-store",   "data"),
     State("theme-store",     "data")],
    prevent_initial_call=True,
)
def run_calibration(n_clicks, country, theme_name):
    if not n_clicks:
        raise PreventUpdate
    country = (country or "US").upper()
    t = THEMES.get(theme_name or DEFAULT_THEME, THEMES[DEFAULT_THEME])

    try:
        cfg = load_composites_config(country)
        with get_connection() as conn:
            df = calibrate_growth_weights(country, conn, cfg)
    except Exception as exc:
        return None, _no_data_msg(f"Calibration error: {exc}"), f"Error: {exc}", True

    if df.empty:
        return None, _no_data_msg("No results returned."), "No data", True

    # ── Build results table ───────────────────────────────────────────────────
    th_sty = {
        "padding": "5px 10px", "fontSize": "0.70rem",
        "textTransform": "uppercase", "letterSpacing": "0.05em",
        "color": "var(--muted-color)", "borderBottom": "1px solid var(--border-color)",
        "whiteSpace": "nowrap", "textAlign": "right",
    }
    th_sty_l = {**th_sty, "textAlign": "left"}

    def _td(val, align="right", color=None, bold=False):
        sty = {
            "padding": "4px 10px", "fontSize": "0.80rem",
            "borderBottom": "1px solid var(--border-color)",
            "color": color or t["font_color"],
            "fontWeight": "700" if bold else "normal",
            "textAlign": align,
        }
        return html.Td(val, style=sty)

    def _fit_color(r2, pval):
        if r2 is None:
            return "#8b97a8"
        if r2 >= 0.30 and pval is not None and pval < 0.05:
            return "#5CBA8A"
        if r2 >= 0.10:
            return "#F4C842"
        return "#8b97a8"

    headers = ["", "Signal", "n_obs", "β", "R²", "p-value",
               "Contribution Share", "Recommended", "Current", "Δ", "Note"]
    head_aligns = ["left", "left", "right", "right", "right", "right",
                   "right", "right", "right", "right", "left"]

    body_rows = []
    store_data = []
    for _, row in df.iterrows():
        fit_c = _fit_color(row.get("r_squared"), row.get("p_value"))
        has_rec = row.get("recommended_imp") is not None

        delta_val = row.get("delta")
        if delta_val is not None:
            delta_str = f"{delta_val:+.2f}"
            delta_color = "#5CBA8A" if delta_val > 0 else _BALANCE_WARN_COLOR
        else:
            delta_str, delta_color = "—", "#8b97a8"

        rec_str = f"{row['recommended_imp']:.2f}" if has_rec else "—"

        chk = dcc.Checklist(
            id={"type": "wa-calib-chk", "index": str(row["signal_id"])},
            options=[{"label": "", "value": "on"}],
            value=["on"] if has_rec else [],
            style={"display": "inline"},
            inputStyle={"accentColor": "var(--slider-accent, #E8A317)"},
        ) if has_rec else html.Span("—", style={"color": "#8b97a8", "fontSize": "0.75rem"})

        body_rows.append(html.Tr([
            html.Td(chk, style={"padding": "4px 10px", "borderBottom": "1px solid var(--border-color)"}),
            _td(row["label"], align="left", bold=True),
            _td(str(row["n_obs"])),
            _td(f"{row['beta']:.3f}" if row.get("beta") is not None else "—", color=fit_c),
            _td(f"{row['r_squared']:.3f}" if row.get("r_squared") is not None else "—", color=fit_c),
            _td(f"{row['p_value']:.4f}" if row.get("p_value") is not None else "—", color=fit_c),
            _td(f"{row['contribution_share']:.3f}" if row.get("contribution_share") is not None else "—"),
            _td(rec_str, color="#E8A317" if has_rec else "#8b97a8", bold=has_rec),
            _td(f"{row['current_importance']:.2f}"),
            _td(delta_str, color=delta_color, bold=delta_val is not None),
            _td(row.get("note") or "", align="left"),
        ]))

        store_data.append({
            "signal_id":      str(row["signal_id"]),
            "recommended_imp": float(row["recommended_imp"]) if has_rec else None,
        })

    legend = html.Div([
        html.Span("● ", style={"color": "#5CBA8A"}),
        html.Span("R²≥0.30 p<0.05  ", style={"fontSize": "0.72rem", "color": "var(--muted-color)"}),
        html.Span("● ", style={"color": "#F4C842"}),
        html.Span("R²≥0.10  ", style={"fontSize": "0.72rem", "color": "var(--muted-color)"}),
        html.Span("● ", style={"color": "#8b97a8"}),
        html.Span("weak / no recommendation", style={"fontSize": "0.72rem", "color": "var(--muted-color)"}),
    ], style={"marginBottom": "8px"})

    table = html.Table([
        html.Thead(html.Tr([
            html.Th(h, style={**th_sty, "textAlign": a})
            for h, a in zip(headers, head_aligns)
        ])),
        html.Tbody(body_rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    n_rec = sum(1 for r in store_data if r["recommended_imp"] is not None)
    status = f"Growth basket — {len(df)} signals, {n_rec} with positive β (recommendations available)"

    return store_data, html.Div([legend, table]), status, False


@callback(
    Output("wa-editor-table", "data", allow_duplicate=True),
    Input("wa-calib-apply-btn", "n_clicks"),
    [State("wa-calib-store",                          "data"),
     State("wa-editor-table",                         "data"),
     State({"type": "wa-calib-chk", "index": ALL},   "value"),
     State({"type": "wa-calib-chk", "index": ALL},   "id")],
    prevent_initial_call=True,
)
def apply_calibration_to_editor(n_clicks, calib_data, editor_rows, chk_values, chk_ids):
    if not n_clicks or not calib_data or not editor_rows:
        raise PreventUpdate

    checked_ids: set[str] = set()
    for vals, cid in zip(chk_values or [], chk_ids or []):
        if vals and "on" in vals:
            checked_ids.add(cid["index"])

    rec_map = {
        r["signal_id"]: r["recommended_imp"]
        for r in calib_data
        if r.get("recommended_imp") is not None and r["signal_id"] in checked_ids
    }
    if not rec_map:
        raise PreventUpdate

    updated = []
    for r in editor_rows:
        yaml_id = r.get("yaml_id", "")
        short = yaml_id.split(".")[-1] if "." in yaml_id else yaml_id
        if short in rec_map or yaml_id in rec_map:
            new_imp = rec_map.get(short) or rec_map.get(yaml_id)
            r = {**r, "importance": new_imp,
                 "tier": _importance_tier(new_imp),
                 "raw_weight": round(
                     float(r.get("base_share", 1.0)) * new_imp * float(r.get("quality_factor", 1.0)),
                     3)}
        updated.append(r)
    return updated

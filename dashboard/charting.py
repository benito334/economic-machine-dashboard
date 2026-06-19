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
from typing import Any

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html
from plotly.subplots import make_subplots

from dashboard.charting_data import (
    available_dates_for_yield_curve,
    load_composite_history,
    load_series_catalog,
    load_signal_history,
    load_yield_curve_term_structure,
)
from dashboard.themes import THEME_CSS_VARS, THEMES, figure_layout
from dashboard import explorer as _explorer

# ── App setup ─────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    title="Indicators Machine — Charts",
    suppress_callback_exceptions=True,
)
server = app.server  # expose Flask for Gunicorn / production
_explorer.register_callbacks(app)  # Phase 1E Data Explorer callbacks

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
    """Build the left-sidebar series checklist grouped by lens."""
    groups = []
    for group_name, entries in _GROUPS.items():
        options = [
            {"label": e["label"], "value": e["signal_id"], "title": e.get("description", "")}
            for e in entries
        ]
        groups.append(
            html.Div([
                html.P(group_name, className="text-muted small mb-1 mt-2 fw-semibold"),
                dcc.Checklist(
                    id={"type": "group-checklist", "group": group_name},
                    options=options,
                    value=[],
                    inputStyle={"marginRight": "6px"},
                    labelStyle={"display": "block", "fontSize": "0.82rem", "marginBottom": "3px"},
                ),
            ])
        )

    return dbc.Card(
        dbc.CardBody([
            html.H6("Series", className="mb-0"),
            html.Hr(className="my-2"),
            html.Div(id="series-selector-body", children=groups, style={"overflowY": "auto", "maxHeight": "78vh"}),
            html.Hr(className="my-2"),
            dbc.Button("Clear all", id="btn-clear-all", color="secondary", size="sm", className="w-100 mb-1"),
        ]),
        className="h-100",
        style={"minWidth": "220px", "maxWidth": "240px"},
    )


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
        value="midnight",
        inline=True,
        className="small py-2",
        inputStyle={"marginRight": "4px"},
        labelStyle={"marginRight": "12px", "fontSize": "0.82rem"},
    )


app.layout = dbc.Container(
    fluid=True,
    children=[
        # Hidden stores and theme helpers
        dcc.Store(id="selected-series", data=[]),
        dcc.Store(id="date-range", data={"start": None, "end": None}),
        dcc.Store(id="theme-store", data="midnight"),
        html.Div(id="theme-dummy", style={"display": "none"}),

        # Header
        dbc.Row([
            dbc.Col(html.H4("Indicators Machine — Charting", className="mb-0 py-2"), width="auto"),
            dbc.Col(_theme_picker(), width="auto", className="ms-auto"),
            dbc.Col(
                dbc.Button("← Regime Dashboard", href="http://localhost:8501",
                           external_link=True, color="secondary", size="sm", outline=True,
                           className="mt-1"),
                width="auto",
                className="ms-2",
            ),
        ], className="border-bottom mb-3"),

        # ── Shared time controls (above tabs, apply to Overlay + Regime) ────
        dbc.Row([
            dbc.Col(_time_controls(), className="ps-3 pt-1"),
        ]),
        dbc.Row([
            dbc.Col(
                dcc.RangeSlider(
                    id="range-slider",
                    min=0, max=1, step=0.001,
                    value=[0, 1],
                    marks=None,
                    tooltip={"placement": "bottom", "always_visible": False},
                    className="mb-2",
                ),
            ),
        ]),

        dbc.Row([
            # ── Sidebar ───────────────────────────────────────────────────
            dbc.Col(_series_selector(), width="auto", className="pe-0"),

            # ── Main content ──────────────────────────────────────────────
            dbc.Col([
                dbc.Tabs(id="main-tabs", active_tab="tab-overlay", children=[

                    dbc.Tab(label="Chart Overlay", tab_id="tab-overlay", children=[
                        dcc.Graph(
                            id="overlay-chart",
                            config={"displayModeBar": True, "scrollZoom": True},
                            style={"height": "65vh"},
                        ),
                    ]),

                    dbc.Tab(label="Yield Curve", tab_id="tab-yield-curve", children=[
                        html.Div([
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Date", className="small text-muted mb-1"),
                                    dcc.Dropdown(
                                        id="yc-date-picker",
                                        options=[],  # populated on load
                                        placeholder="Select a date…",
                                        clearable=False,
                                        style={"color": "#000"},
                                    ),
                                ], width=3),
                                dbc.Col([
                                    html.Label("Compare date (optional)", className="small text-muted mb-1"),
                                    dcc.Dropdown(
                                        id="yc-date-compare",
                                        options=[],
                                        placeholder="None",
                                        clearable=True,
                                        style={"color": "#000"},
                                    ),
                                ], width=3),
                            ], className="mb-3 pt-2"),
                            dcc.Graph(
                                id="yield-curve-chart",
                                config={"displayModeBar": True},
                                style={"height": "55vh"},
                            ),
                        ]),
                    ]),

                    dbc.Tab(label="Regime History", tab_id="tab-regime", children=[
                        dcc.Graph(
                            id="regime-chart",
                            config={"displayModeBar": True},
                            style={"height": "65vh"},
                        ),
                    ]),

                    dbc.Tab(label="🔬 Data Explorer", tab_id="tab-explorer", children=[
                        _explorer.get_layout(),
                    ]),
                ]),
            ]),
        ]),
    ],
    style={"backgroundColor": "var(--page-bg)", "minHeight": "100vh"},
)

# ── Theme callbacks ───────────────────────────────────────────────────────────

@callback(
    Output("theme-store", "data"),
    Input("theme-picker", "value"),
)
def update_theme_store(theme_name: str) -> str:
    return theme_name or "midnight"


# Clientside: update CSS custom properties on documentElement when theme changes.
# Embeds the full THEME_CSS_VARS dict as JSON so all logic stays in Python.
app.clientside_callback(
    f"""
    function(theme) {{
        var themes = {json.dumps(THEME_CSS_VARS)};
        var t = themes[theme] || themes['midnight'];
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
    Output("selected-series", "data"),
    [Input({"type": "group-checklist", "group": dash.ALL}, "value"),
     Input("btn-clear-all", "n_clicks")],
    prevent_initial_call=False,
)
def aggregate_selected(group_values: list[list[str]], _clear: Any) -> list[str]:
    triggered = dash.callback_context.triggered_id
    if triggered == "btn-clear-all":
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
    prevent_initial_call=False,
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
     Input("theme-store", "data")],
    prevent_initial_call=False,
)
def update_overlay_chart(
    selected_ids: list[str],
    date_range: dict,
    theme_name: str = "midnight",
) -> go.Figure:
    t = THEMES.get(theme_name, THEMES["midnight"])
    if not selected_ids:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "Select series from the left sidebar"))
        return fig

    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")

    # Group selected series by their default_pane
    pane_series: dict[str, list[str]] = defaultdict(list)
    for sid in selected_ids:
        entry = _BY_ID.get(sid, {})
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
            entry = _BY_ID.get(sid, {})
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
        units_in_pane = {_BY_ID.get(s, {}).get("units", "") for s in pane_series[pane]}
        y_title = " / ".join(u for u in units_in_pane if u) or ""
        fig.update_yaxes(title_text=y_title, row=row_idx, col=1)

    fig.update_layout(
        **figure_layout(theme_name),
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "xanchor": "left", "x": 0},
        height=max(300 * n_panes, 400),
    )
    fig.update_xaxes(showgrid=True, gridcolor=t["grid_color"], row=n_panes, col=1)
    return fig


# ── Callbacks — yield curve ───────────────────────────────────────────────────

@callback(
    [Output("yc-date-picker", "options"),
     Output("yc-date-picker", "value"),
     Output("yc-date-compare", "options")],
    Input("main-tabs", "active_tab"),
    prevent_initial_call=False,
)
def populate_yc_dates(active_tab: str) -> tuple[list[dict], str, list[dict]]:
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
     Input("theme-store", "data")],
    prevent_initial_call=False,
)
def update_yield_curve(
    date_primary: str,
    date_compare: str,
    theme_name: str = "midnight",
) -> go.Figure:
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

    fig.update_layout(**figure_layout(theme_name), height=650)
    return fig


# ── Callbacks — regime history ────────────────────────────────────────────────

@callback(
    Output("regime-chart", "figure"),
    [Input("main-tabs", "active_tab"),
     Input("date-range", "data"),
     Input("theme-store", "data")],
    prevent_initial_call=False,
)
def update_regime_chart(
    active_tab: str,
    date_range: dict,
    theme_name: str = "midnight",
) -> go.Figure:
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")

    comp = load_composite_history(start_date=start, end_date=end)
    if comp.empty:
        fig = go.Figure()
        fig.update_layout(**figure_layout(theme_name, "No composite data"))
        return fig

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=["Growth Score (Z)", "Inflation Score (Z)", "Regime Quadrant"],
    )

    # Growth score
    fig.add_trace(
        go.Scatter(
            x=comp["as_of"], y=comp["growth_score"],
            name="Growth Score",
            line={"color": _COLORS[0], "width": 1.5},
            hovertemplate="%{x|%Y-%m-%d}<br>Growth Z: %{y:.2f}<extra></extra>",
            fill="tozeroy",
            fillcolor="rgba(76, 155, 232, 0.15)",
        ),
        row=1, col=1,
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=1, col=1)

    # Inflation score
    fig.add_trace(
        go.Scatter(
            x=comp["as_of"], y=comp["inflation_score"],
            name="Inflation Score",
            line={"color": _COLORS[2], "width": 1.5},
            hovertemplate="%{x|%Y-%m-%d}<br>Inflation Z: %{y:.2f}<extra></extra>",
            fill="tozeroy",
            fillcolor="rgba(228, 115, 76, 0.15)",
        ),
        row=2, col=1,
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=2, col=1)

    # Quadrant as numeric bands
    quadrant_map = {
        "Expansion": 1,
        "Inflationary Boom": 2,
        "Stagflation": 3,
        "Disinflationary Slowdown": 0,
    }
    q_numeric = comp["quadrant"].map(quadrant_map).fillna(-1)
    fig.add_trace(
        go.Scatter(
            x=comp["as_of"],
            y=q_numeric,
            mode="markers",
            name="Quadrant",
            marker={
                "color": [_QUADRANT_COLOR.get(q, "#888") for q in comp["quadrant"]],
                "size": 5,
            },
            hovertemplate="%{x|%Y-%m-%d}<br>%{customdata}<extra></extra>",
            customdata=comp["quadrant"],
            showlegend=False,
        ),
        row=3, col=1,
    )
    fig.update_yaxes(
        tickvals=[0, 1, 2, 3],
        ticktext=["Dis.Slow", "Expansion", "Inf.Boom", "Stagflation"],
        row=3, col=1,
    )

    fig.update_layout(**figure_layout(theme_name), hovermode="x unified", height=700)
    return fig


# ── Layout helper (kept for backward compatibility with tests) ─────────────────

def _dark_layout(title: str = "") -> dict:
    return figure_layout("midnight", title)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("CHARTING_PORT", 8502))
    debug = os.environ.get("DASH_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

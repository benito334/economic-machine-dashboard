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
    load_debt_stress_component_dates,
    load_debt_stress_history,
    load_series_catalog,
    load_signal_history,
    load_yield_curve_term_structure,
)
from dashboard.themes import DEFAULT_THEME, THEME_CSS_VARS, THEMES, figure_layout
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


def _sync_banner() -> dbc.Col:
    """Return a header Col showing the next scheduled data sync date, or an overdue warning."""
    today = datetime.date.today()
    overdue = [(d, lbl) for d, lbl in _UPCOMING_RELEASES if d <= today]
    future  = [(d, lbl) for d, lbl in _UPCOMING_RELEASES if d > today]

    if overdue:
        _, lbl = overdue[0]
        content = html.Span(
            f"⚠  Update data now  ·  {lbl}",
            style={"color": "#F4C842", "fontSize": "0.82rem", "fontWeight": "600", "whiteSpace": "nowrap"},
        )
    elif future:
        next_date, lbl = future[0]
        days_left = (next_date - today).days
        content = html.Span(
            f"Next sync: {next_date.strftime('%b %d, %Y')}  ·  {lbl}  ({days_left}d)",
            style={"color": "#888", "fontSize": "0.82rem", "whiteSpace": "nowrap"},
        )
    else:
        return dbc.Col(width=0)

    return dbc.Col(content, width="auto", className="ms-3 align-self-center")


app.layout = dbc.Container(
    fluid=True,
    children=[
        # Hidden stores and theme helpers
        dcc.Store(id="selected-series", data=[]),
        dcc.Store(id="date-range", data={"start": None, "end": None}),
        dcc.Store(id="theme-store", data=DEFAULT_THEME),
        dcc.Store(id="regime-step-index", data=0),
        html.Div(id="theme-dummy", style={"display": "none"}),

        # Header
        dbc.Row([
            dbc.Col(html.H4("Indicators Machine — Charting", className="mb-0 py-2"), width="auto"),
            _sync_banner(),
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
                        # Navigation bar
                        dbc.Row([
                            dbc.Col([
                                dbc.ButtonGroup([
                                    dbc.Button(
                                        "←", id="btn-regime-prev",
                                        color="secondary", size="sm", outline=True,
                                        title="Step back in time",
                                    ),
                                    dbc.Button(
                                        "→", id="btn-regime-next",
                                        color="secondary", size="sm", outline=True,
                                        title="Step forward in time",
                                    ),
                                ], className="me-3"),
                                html.Span(
                                    id="regime-date-display",
                                    className="text-muted small align-middle",
                                ),
                            ], className="d-flex align-items-center pt-2 pb-1"),
                        ]),
                        # Info box (left) + chart (right)
                        dbc.Row([
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        html.Div(id="regime-info-box"),
                                        style={"padding": "12px"},
                                    ),
                                    style={"position": "relative"},
                                ),
                                width=3,
                            ),
                            dbc.Col(
                                dcc.Graph(
                                    id="regime-chart",
                                    config={"displayModeBar": True},
                                    style={"height": "70vh"},
                                ),
                                width=9,
                            ),
                        ]),
                    ]),

                    dbc.Tab(label="📉 Debt Stress", tab_id="tab-debt-stress", children=[
                        dbc.Row([
                            dbc.Col(
                                dbc.Card(dbc.CardBody(
                                    html.Div(id="debt-stress-info-box"),
                                    style={"padding": "16px"},
                                )),
                                width=12,
                            ),
                        ], className="pt-2"),
                        dbc.Row([
                            dbc.Col(
                                dcc.Graph(
                                    id="debt-stress-chart",
                                    config={"displayModeBar": True},
                                    style={"height": "65vh"},
                                ),
                                width=12,
                            ),
                        ], className="pt-2"),
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
    return theme_name or DEFAULT_THEME


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
    theme_name: str = DEFAULT_THEME,
) -> go.Figure:
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
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
    theme_name: str = DEFAULT_THEME,
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


# ── Regime History — helpers + callbacks ─────────────────────────────────────

def _regime_info_children(row: dict, is_current: bool) -> list:
    """Build children for the regime-info-box Div from one CompositeSnapshot row."""
    quadrant = row.get("quadrant") or "—"
    g_score = row.get("growth_score")
    i_score = row.get("inflation_score")
    confidence = row.get("confidence")
    diseq = row.get("disequilibrium_score")

    q_color = _QUADRANT_COLOR.get(quadrant, "#888")

    row_style = {
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "padding": "5px 0", "borderBottom": "1px solid var(--border-color)",
        "fontSize": "0.83rem",
    }
    muted = {"color": "var(--muted-color)"}
    val_s = {"color": "var(--font-color)", "fontWeight": "500"}

    def _arrow(v: Any) -> str:
        return "↑" if (v is not None and not pd.isna(v) and v >= 0) else "↓"

    def _fmt(v: Any, prec: int = 3) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        return f"{v:+.{prec}f}"

    children: list = [
        html.Div(
            quadrant,
            style={
                "backgroundColor": q_color, "color": "#111",
                "textAlign": "center", "fontWeight": "bold",
                "fontSize": "0.9rem", "padding": "8px 4px",
                "borderRadius": "4px", "marginBottom": "10px",
            },
        ),
        html.Div([
            html.Span("Growth", style=muted),
            html.Span(f"{_arrow(g_score)} {_fmt(g_score)}", style=val_s),
        ], style=row_style),
        html.Div([
            html.Span("Inflation", style=muted),
            html.Span(f"{_arrow(i_score)} {_fmt(i_score)}", style=val_s),
        ], style=row_style),
        html.Div([
            html.Span("Confidence", style=muted),
            html.Span(
                f"{int(confidence * 100)}%" if (confidence is not None and not pd.isna(confidence)) else "—",
                style=val_s,
            ),
        ], style=row_style),
        html.Div([
            html.Span("Disequilibrium", style=muted),
            html.Span(_fmt(diseq), style=val_s),
        ], style={**row_style, "borderBottom": "none"}),
    ]

    if not is_current:
        children.append(
            html.Div(
                "⚠ Past Data",
                style={
                    "position": "absolute", "bottom": "8px", "right": "10px",
                    "fontSize": "0.72rem", "color": "#F4C842", "fontWeight": "500",
                },
            )
        )

    return children


@callback(
    Output("regime-step-index", "data"),
    [Input("btn-regime-prev", "n_clicks"),
     Input("btn-regime-next", "n_clicks"),
     Input("date-range", "data")],
    State("regime-step-index", "data"),
    prevent_initial_call=True,
)
def update_regime_step(
    _prev: Any,
    _next: Any,
    date_range: dict,
    current_step: int,
) -> int:
    triggered = dash.callback_context.triggered_id
    if triggered == "date-range":
        return 0  # reset to latest on range change

    step = current_step or 0
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp = load_composite_history(start_date=start, end_date=end)
    max_step = max(0, len(comp) - 1)

    if triggered == "btn-regime-prev":
        return min(step + 1, max_step)
    if triggered == "btn-regime-next":
        return max(step - 1, 0)
    return step


@callback(
    [Output("regime-info-box", "children"),
     Output("regime-date-display", "children")],
    [Input("regime-step-index", "data"),
     Input("date-range", "data")],
    prevent_initial_call=False,
)
def update_regime_info(step: int, date_range: dict) -> tuple:
    step = step or 0
    start = (date_range or {}).get("start")
    end = (date_range or {}).get("end")
    comp = load_composite_history(start_date=start, end_date=end)

    if comp.empty:
        return [], "No data"

    n = len(comp)
    idx = max(0, min(n - 1 - step, n - 1))
    selected = comp.iloc[idx].to_dict()
    is_current = (step == 0)

    date_str = comp.iloc[idx]["as_of"].strftime("%b %Y")
    date_display = f"{date_str} · current" if is_current else f"{date_str} · {step} month{'s' if step != 1 else ''} ago"

    return _regime_info_children(selected, is_current), date_display


@callback(
    Output("regime-chart", "figure"),
    [Input("main-tabs", "active_tab"),
     Input("date-range", "data"),
     Input("theme-store", "data"),
     Input("regime-step-index", "data")],
    prevent_initial_call=False,
)
def update_regime_chart(
    active_tab: str,
    date_range: dict,
    theme_name: str = DEFAULT_THEME,
    step: int = 0,
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

    # Highlighted marker — growth score (row 1)
    g_val = sel.get("growth_score")
    if g_val is not None and not pd.isna(g_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[g_val],
                mode="markers",
                marker={"size": 11, "color": _COLORS[0],
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=1, col=1,
        )

    # Highlighted marker — inflation score (row 2)
    i_val = sel.get("inflation_score")
    if i_val is not None and not pd.isna(i_val):
        fig.add_trace(
            go.Scatter(
                x=[sel_ts], y=[i_val],
                mode="markers",
                marker={"size": 11, "color": _COLORS[2],
                        "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ),
            row=2, col=1,
        )

    # Highlighted marker — quadrant row (row 3), open circle in quadrant colour
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
            row=3, col=1,
        )

    return fig


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
        extrap_on     = bool(stale_cfg.get("extrapolation", {}).get("enabled", False))
    except Exception:
        comp_cfg_list, max_carry_q, halflife, min_frac, extrap_on = [], 4, None, 0.20, False

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
                f"{n_comp}/7 components active",
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
        elif halflife and halflife > 0 and lag_q > 0:
            decay = max(0.0, 1.0 - lag_q / halflife)
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
                expected  = 4 if freq == "A" else 1
                excess    = max(0, total_lag - expected)
                carry_end = _carry_expires(last_obs, freq, max_carry_q)
                reason = (
                    f"carry expired · last data: {_fmt_period(last_obs, freq)} · "
                    f"carry cap {max_carry_q}q → covered to {carry_end}"
                )
                if extrap_on:
                    reason += f" · excess lag {excess}q ≤ carry cap (no extrap trigger)"
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
        "⚠ Bands are NOT validated risk thresholds · Eff Wt applies staleness decay (halflife "
        + (f"{int(halflife)}q" if halflife else "off") + f") · carry cap {max_carry_q}q",
        style={"fontSize": "0.65rem", "color": "#555", "marginTop": "10px"},
    )

    return [summary_strip, table, footer]


@callback(
    Output("debt-stress-info-box", "children"),
    [Input("main-tabs", "active_tab"),
     Input("date-range", "data"),
     Input("theme-store", "data")],
    prevent_initial_call=False,
)
def update_debt_stress_info(active_tab: str, date_range: dict, theme_name: str) -> list:
    end = (date_range or {}).get("end")
    df = load_debt_stress_history(country="US", end_date=end)
    latest = df.iloc[-1] if not df.empty else None
    comp_dates = load_debt_stress_component_dates(country="US")
    return _build_debt_stress_info(latest, theme_name or DEFAULT_THEME, comp_dates)


@callback(
    Output("debt-stress-chart", "figure"),
    [Input("main-tabs", "active_tab"),
     Input("date-range", "data"),
     Input("theme-store", "data")],
    prevent_initial_call=False,
)
def update_debt_stress_chart(
    active_tab: str,
    date_range: dict,
    theme_name: str = DEFAULT_THEME,
) -> go.Figure:
    start = (date_range or {}).get("start")
    end   = (date_range or {}).get("end")
    df = load_debt_stress_history(country="US", start_date=start, end_date=end)

    theme_name = theme_name or DEFAULT_THEME

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
    fig.update_layout(
        **figure_layout(theme_name),
        hovermode="x unified",
        height=700,
        legend={"orientation": "h", "y": -0.12, "x": 0},
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

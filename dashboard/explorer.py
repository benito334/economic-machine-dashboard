"""
Phase 1E — Data Explorer tab for the Dash charting app.

Registers its own layout and callbacks; imported by charting.py.
All component IDs are prefixed with "exp-" to avoid collisions.
"""
from __future__ import annotations

from typing import Any, Optional

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dash_table, dcc, html
from plotly.subplots import make_subplots

from dashboard.explorer_data import (
    compare_raw_vs_processed,
    compute_pca,
    compute_signal_stats,
    detect_gaps,
    flag_anomalies,
    load_composite_zscore_matrix,
    load_raw_cache_series,
    load_signal_detail,
    load_signal_overview,
)
from dashboard.themes import DEFAULT_THEME, THEMES, figure_layout

# ── Constants ─────────────────────────────────────────────────────────────────

_DIR_ARROW = {"rising": "↑", "falling": "↓", "flat": "→"}

_FORCE_COLORS = {
    "growth": "#4C9BE8",
    "inflation": "#E8734C",
    "policy": "#B07FD4",
    "premium": "#F4C842",
    "credit": "#E84C82",
    "fiscal": "#5CBA8A",
    "external": "#4CE8D4",
    "capital": "#8AB4F4",
    "currency": "#F4A442",
    "master": "#aaaaaa",
    "demographics": "#cccccc",
}

_DARK = {
    "paper_bgcolor": "#1a1a2e",
    "plot_bgcolor": "#16213e",
    "font": {"color": "#e0e0e0", "size": 12},
    "margin": {"l": 55, "r": 20, "t": 35, "b": 30},
}

# Shared DataTable style dicts — use CSS custom properties so they update
# automatically when the clientside theme callback changes the CSS vars.
_TABLE_HEADER = {
    "backgroundColor": "var(--header-bg)",
    "color": "var(--muted-color)",
    "fontWeight": "bold",
    "border": "1px solid var(--border-color)",
    "padding": "4px 6px",
}
_TABLE_CELL = {
    "backgroundColor": "var(--cell-bg)",
    "color": "var(--font-color)",
    "border": "1px solid var(--border-color)",
    "padding": "4px 6px",
    "whiteSpace": "nowrap",
}


# ── Overview table helpers ────────────────────────────────────────────────────

def _overview_columns() -> list[dict]:
    return [
        {"name": "Signal", "id": "id", "type": "text"},
        {"name": "Force", "id": "force", "type": "text"},
        {"name": "Latest", "id": "latest_value_fmt", "type": "text"},
        {"name": "Z-Score", "id": "zscore_fmt", "type": "text"},
        {"name": "Pct", "id": "pct_fmt", "type": "text"},
        {"name": "Dir", "id": "direction_fmt", "type": "text"},
        {"name": "Last Updated", "id": "latest_as_of_str", "type": "text"},
        {"name": "Δ days", "id": "days_since_update", "type": "numeric"},
        {"name": "Obs", "id": "obs_count", "type": "numeric"},
        {"name": "Freq", "id": "freq", "type": "text"},
        {"name": "Flags", "id": "flags", "type": "text"},
    ]


def _format_overview(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        val = r["latest_value"]
        units = r.get("units", "")
        if units in ("yoy_pct", "pct_level", "pct_gdp", "pct_pot_gdp", "net_pct", "pct_annual",
                     "pct_working_age", "pct_pop_15plus", "pct_total_pop"):
            val_fmt = f"{val*100:.2f}%" if abs(val) < 1 else f"{val:.2f}%"
        elif units in ("millions_usd",):
            val_fmt = f"${val/1e6:.1f}T" if abs(val) >= 1e6 else f"${val/1e3:.0f}B"
        else:
            val_fmt = f"{val:.3f}"

        z = r["zscore"]
        z_fmt = f"{z:+.2f}" if pd.notna(z) else "—"

        rows.append({
            "id": r["id"].replace("us.", ""),
            "_signal_id": r["id"],
            "force": r["force"],
            "latest_value_fmt": val_fmt,
            "zscore_fmt": z_fmt,
            "pct_fmt": f"{r['level_percentile']*100:.0f}%" if pd.notna(r['level_percentile']) else "—",
            "direction_fmt": _DIR_ARROW.get(r.get("direction", ""), ""),
            "latest_as_of_str": r["latest_as_of"].strftime("%Y-%m-%d"),
            "days_since_update": int(r["days_since_update"]),
            "obs_count": int(r["obs_count"]),
            "freq": r["freq"],
            "flags": r["flags"],
        })
    return rows


def _zscore_style_conditions() -> list[dict]:
    """Conditional styles for Z-score column in overview table."""
    return [
        {"if": {"filter_query": "{zscore_fmt} contains '+'", "column_id": "zscore_fmt"},
         "color": "#E8734C"},
        {"if": {"filter_query": "{flags} contains 'STALE'"},
         "backgroundColor": "rgba(255, 200, 0, 0.08)"},
        {"if": {"filter_query": "{days_since_update} > 365"},
         "color": "#888"},
        {"if": {"state": "selected"}, "backgroundColor": "#2a4070", "color": "white"},
    ]


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div([
        dcc.Store(id="exp-selected-signal", data=None),

        dbc.Row([
            # ── Left: Signal browser ──────────────────────────────────────
            dbc.Col([
                # Filters
                dbc.Row([
                    dbc.Col(
                        dcc.Dropdown(
                            id="exp-force-filter",
                            options=[{"label": "All forces", "value": "all"}] + [
                                {"label": f, "value": f}
                                for f in ["capital", "credit", "currency", "demographics",
                                          "external", "fiscal", "growth", "inflation",
                                          "master", "policy", "premium"]
                            ],
                            value="all",
                            clearable=False,
                            style={"color": "#000", "fontSize": "0.82rem"},
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        dcc.Dropdown(
                            id="exp-flag-filter",
                            options=[
                                {"label": "Any flags", "value": "any"},
                                {"label": "Stale", "value": "stale"},
                                {"label": "Proxy", "value": "proxy"},
                                {"label": "Low history", "value": "low_history"},
                                {"label": "High |Z| (>2)", "value": "high_z"},
                                {"label": "No issues", "value": "clean"},
                            ],
                            value="any",
                            clearable=False,
                            style={"color": "#000", "fontSize": "0.82rem"},
                        ),
                        width=6,
                    ),
                ], className="mb-2"),

                dash_table.DataTable(
                    id="exp-signal-table",
                    columns=_overview_columns(),
                    data=[],
                    row_selectable="single",
                    selected_rows=[],
                    sort_action="native",
                    filter_action="native",
                    page_action="native",
                    page_size=20,
                    style_table={"overflowX": "auto", "fontSize": "0.78rem"},
                    style_header={**_TABLE_HEADER},
                    style_cell={
                        **_TABLE_CELL,
                        "maxWidth": "180px",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                    style_data_conditional=_zscore_style_conditions(),
                    tooltip_delay=0,
                    tooltip_duration=None,
                ),
            ], width=5, className="pe-2"),

            # ── Right: Detail panel ────────────────────────────────────────
            dbc.Col([
                html.Div(id="exp-detail-header",
                         children=_placeholder_header(),
                         className="mb-2"),
                dbc.Tabs(id="exp-detail-tabs", active_tab="exp-tab-ts", children=[

                    dbc.Tab(label="📈 Time Series", tab_id="exp-tab-ts", children=[
                        dbc.Row([
                            dbc.Col(_stat_card("exp-stat-latest", "Latest", "—"), width=2),
                            dbc.Col(_stat_card("exp-stat-mean",   "Mean",   "—"), width=2),
                            dbc.Col(_stat_card("exp-stat-min",    "Min",    "—"), width=2),
                            dbc.Col(_stat_card("exp-stat-max",    "Max",    "—"), width=2),
                            dbc.Col(_stat_card("exp-stat-std",    "Std Dev","—"), width=2),
                            dbc.Col(_stat_card("exp-stat-obs",    "Obs",    "—"), width=2),
                        ], className="my-2 g-1"),
                        dcc.Graph(id="exp-ts-chart",
                                  config={"displayModeBar": True, "scrollZoom": True},
                                  style={"height": "52vh"}),
                        # Reference spot-check
                        dbc.Card(dbc.CardBody([
                            html.Small("Reference spot-check — enter expected value from provider (e.g. FRED website):",
                                       className="text-muted"),
                            dbc.InputGroup([
                                dbc.Input(id="exp-ref-input", type="number",
                                          placeholder="Reference value…",
                                          debounce=True, size="sm"),
                                dbc.Button("Check", id="exp-ref-btn", color="primary",
                                           size="sm", n_clicks=0),
                            ], className="mt-1", size="sm"),
                            html.Div(id="exp-ref-result", className="mt-1 small"),
                        ]), className="mt-2", style={"backgroundColor": "var(--card-bg)"}),
                    ]),

                    dbc.Tab(label="📋 Observations", tab_id="exp-tab-obs", children=[
                        html.Div([
                            dbc.Row([
                                dbc.Col(
                                    html.Small(id="exp-obs-subtitle", className="text-muted"),
                                    width="auto",
                                ),
                                dbc.Col(
                                    dbc.Button("⬇ Download CSV", id="exp-dl-btn",
                                               color="secondary", size="sm", outline=True),
                                    width="auto", className="ms-auto",
                                ),
                            ], className="mb-2 align-items-center"),
                            dcc.Download(id="exp-dl-csv"),
                            dash_table.DataTable(
                                id="exp-obs-table",
                                columns=[
                                    {"name": "Date", "id": "as_of_str"},
                                    {"name": "Value", "id": "value_fmt"},
                                    {"name": "Z-Score", "id": "zscore_fmt"},
                                    {"name": "Percentile", "id": "pct_fmt"},
                                    {"name": "Direction", "id": "dir_fmt"},
                                    {"name": "Δ 1M", "id": "change_1m_fmt"},
                                    {"name": "Δ 3M", "id": "change_3m_fmt"},
                                    {"name": "Δ 12M", "id": "change_12m_fmt"},
                                    {"name": "Δ Equil.", "id": "dist_eq_fmt"},
                                    {"name": "Stale?", "id": "stale_fmt"},
                                ],
                                data=[],
                                sort_action="native",
                                filter_action="native",
                                page_action="native",
                                page_size=25,
                                style_table={"overflowX": "auto", "fontSize": "0.8rem"},
                                style_header={**_TABLE_HEADER, "padding": "4px 8px"},
                                style_cell={**_TABLE_CELL, "padding": "4px 8px"},
                                style_data_conditional=[
                                    # Outlier rows (|Z| > 3)
                                    {"if": {"filter_query": "{anomaly} = 1"},
                                     "backgroundColor": "rgba(232, 115, 76, 0.15)",
                                     "color": "#E8734C"},
                                    # Stale rows
                                    {"if": {"filter_query": '{stale_fmt} = "✓"'},
                                     "backgroundColor": "rgba(255, 200, 0, 0.07)"},
                                    {"if": {"state": "selected"},
                                     "backgroundColor": "#2a4070", "color": "white"},
                                ],
                            ),
                        ], className="pt-2"),
                    ]),

                    dbc.Tab(label="🔍 Quality & Gaps", tab_id="exp-tab-quality", children=[
                        dbc.Row([
                            dbc.Col([
                                html.H6("Metadata", className="text-muted small mb-2 mt-2"),
                                html.Div(id="exp-metadata-card"),
                            ], width=6),
                            dbc.Col([
                                html.H6("Quality Flags", className="text-muted small mb-2 mt-2"),
                                html.Div(id="exp-flags-card"),
                            ], width=6),
                        ]),
                        html.Hr(style={"borderColor": "var(--border-color)"}),
                        html.H6("Time Gaps (> 2× expected release cycle)",
                                className="text-muted small mb-2"),
                        html.Div(id="exp-gaps-content"),
                    ]),

                    dbc.Tab(label="🔄 Raw vs Processed", tab_id="exp-tab-raw", children=[
                        html.Div([
                            html.Small(
                                "Compares the raw value from the API parquet cache with the "
                                "processed value stored in DuckDB. For YoY-transformed signals "
                                "the raw value is the index level; delta is only meaningful for "
                                "level/spread signals.",
                                className="text-muted d-block mb-2",
                            ),
                            html.Div(id="exp-raw-content"),
                        ], className="pt-2"),
                    ]),

                    dbc.Tab(label="📊 Composite Analysis", tab_id="exp-tab-analysis", children=[
                        html.Div([
                            html.Small(
                                "Pearson correlation matrix and PCA for the 17 composite "
                                "regime signals (9 growth + 8 inflation). "
                                "Computed on monthly Z-score history. "
                                "Highly correlated signals (|r| > 0.8) may warrant weight review.",
                                className="text-muted d-block mb-2",
                            ),
                            dcc.Graph(
                                id="exp-corr-chart",
                                config={"displayModeBar": True},
                                style={"height": "52vh"},
                            ),
                            dcc.Graph(
                                id="exp-pca-chart",
                                config={"displayModeBar": True},
                                style={"height": "32vh"},
                            ),
                        ], className="pt-2"),
                    ]),
                ]),
            ], width=7),
        ], className="pt-2"),
    ])


def _placeholder_header() -> list:
    return [html.P("← Select a signal from the table to begin.",
                   className="text-muted small pt-3")]


def _stat_card(card_id: str, label: str, value: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.P(label, className="text-muted mb-0", style={"fontSize": "0.7rem"}),
            html.H6(value, id=card_id, className="mb-0", style={"fontSize": "0.85rem"}),
        ], className="p-2"),
        style={"backgroundColor": "var(--card-bg)"},
    )


# ── Callbacks ─────────────────────────────────────────────────────────────────

def register_callbacks(app: dash.Dash) -> None:

    # 1. Populate + filter overview table
    @app.callback(
        Output("exp-signal-table", "data"),
        [Input("exp-force-filter", "value"),
         Input("exp-flag-filter", "value")],
    )
    def update_signal_table(force_filter: str, flag_filter: str) -> list[dict]:
        df = load_signal_overview()
        if force_filter and force_filter != "all":
            df = df[df["force"] == force_filter]
        if flag_filter == "stale":
            df = df[df["is_stale"]]
        elif flag_filter == "proxy":
            df = df[df["is_proxy"]]
        elif flag_filter == "low_history":
            df = df[df["low_history"]]
        elif flag_filter == "high_z":
            df = df[df["abs_zscore"] > 2]
        elif flag_filter == "clean":
            df = df[~df["is_stale"] & ~df["is_proxy"] & ~df["low_history"] & (df["abs_zscore"] <= 2)]
        return _format_overview(df)

    # 2. Track selected signal
    @app.callback(
        Output("exp-selected-signal", "data"),
        [Input("exp-signal-table", "selected_rows"),
         Input("exp-signal-table", "data")],
        prevent_initial_call=True,
    )
    def store_selected(selected_rows: list[int], table_data: list[dict]) -> Optional[str]:
        if not selected_rows or not table_data:
            return None
        row = table_data[selected_rows[0]]
        return row.get("_signal_id") or ("us." + row["id"])

    # 3. Detail header
    @app.callback(
        Output("exp-detail-header", "children"),
        Input("exp-selected-signal", "data"),
    )
    def update_header(signal_id: Optional[str]) -> list:
        if not signal_id:
            return _placeholder_header()
        overview = load_signal_overview()
        row = overview[overview["id"] == signal_id]
        if row.empty:
            return _placeholder_header()
        r = row.iloc[0]
        force_color = _FORCE_COLORS.get(r["force"], "#888")
        return [
            dbc.Row([
                dbc.Col(
                    html.H6(signal_id, className="mb-0", style={"fontFamily": "monospace"}),
                    width="auto",
                ),
                dbc.Col(
                    dbc.Badge(r["force"].upper(), color="secondary",
                              style={"backgroundColor": force_color, "fontSize": "0.7rem"}),
                    width="auto",
                ),
                dbc.Col(
                    dbc.Badge(r["freq"], color="dark", style={"fontSize": "0.7rem"}),
                    width="auto",
                ),
                dbc.Col(
                    html.Small(r["source"], className="text-muted"),
                    width="auto",
                ),
                dbc.Col(
                    html.Small(f"{r['units']}", className="text-muted"),
                    width="auto",
                ),
            ], className="g-2 align-items-center"),
            html.Small(r["linkage"], className="text-muted d-block mt-1",
                       style={"fontSize": "0.75rem", "fontStyle": "italic"}),
        ]

    # 4. Time series chart + summary stats
    @app.callback(
        [Output("exp-ts-chart", "figure"),
         Output("exp-stat-latest", "children"),
         Output("exp-stat-mean", "children"),
         Output("exp-stat-min", "children"),
         Output("exp-stat-max", "children"),
         Output("exp-stat-std", "children"),
         Output("exp-stat-obs", "children")],
        [Input("exp-selected-signal", "data"),
         Input("theme-store", "data")],
    )
    def update_ts(signal_id: Optional[str], theme_name: str = DEFAULT_THEME) -> tuple:
        fl = {**figure_layout(theme_name), "margin": {"l": 55, "r": 20, "t": 35, "b": 30}}
        empty_fig = go.Figure()
        empty_fig.update_layout(**fl, title={"text": "Select a signal", "x": 0.5})
        blank = ("—",) * 6
        if not signal_id:
            return (empty_fig,) + blank

        detail = load_signal_detail(signal_id)
        if detail.empty:
            return (empty_fig,) + blank

        detail = detail.sort_values("as_of")
        stats = compute_signal_stats(signal_id)
        overview = load_signal_overview()
        r = overview[overview["id"] == signal_id]
        equil = float(r["equilibrium_estimate"].iloc[0]) if not r.empty else None
        units = r["units"].iloc[0] if not r.empty else ""
        force = r["force"].iloc[0] if not r.empty else "growth"
        color = _FORCE_COLORS.get(force, "#4C9BE8")
        t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=["Raw Value", "Z-Score"],
            row_heights=[0.6, 0.4],
        )

        # Raw value trace
        fig.add_trace(
            go.Scatter(
                x=detail["as_of"], y=detail["value"],
                name="Value",
                line={"color": color, "width": 1.5},
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.4f}<extra></extra>",
            ),
            row=1, col=1,
        )

        # Equilibrium reference line
        if equil is not None and pd.notna(equil):
            fig.add_hline(
                y=equil, line_dash="dot", line_color="#888",
                annotation_text=f"Equil. {equil:.3f}",
                annotation_font_size=10,
                row=1, col=1,
            )

        # Stale points highlighted
        stale = detail[detail["is_stale"]]
        if not stale.empty:
            fig.add_trace(
                go.Scatter(
                    x=stale["as_of"], y=stale["value"],
                    mode="markers", name="Stale",
                    marker={"color": "#F4C842", "size": 6, "symbol": "circle-open"},
                    hovertemplate="STALE<br>%{x|%Y-%m-%d}<br>%{y:.4f}<extra></extra>",
                ),
                row=1, col=1,
            )

        # Z-score trace
        z = detail.dropna(subset=["zscore"])
        fig.add_trace(
            go.Scatter(
                x=z["as_of"], y=z["zscore"],
                name="Z-Score",
                line={"color": "#aaaaaa", "width": 1.2},
                hovertemplate="%{x|%Y-%m-%d}<br>Z=%{y:.2f}<extra></extra>",
                fill="tozeroy",
                fillcolor="rgba(170,170,170,0.08)",
            ),
            row=2, col=1,
        )
        # ±2 and ±3 bands
        for level, dash, col_ in [(2, "dot", "#5CBA8A"), (3, "dash", "#E8734C"),
                                   (-2, "dot", "#5CBA8A"), (-3, "dash", "#E8734C")]:
            fig.add_hline(y=level, line_dash=dash, line_color=col_,
                          line_width=0.8, row=2, col=1)
        fig.add_hline(y=0, line_dash="solid", line_color="#555", line_width=0.5, row=2, col=1)

        fig.update_yaxes(title_text=units, row=1, col=1)
        fig.update_yaxes(title_text="σ", row=2, col=1)
        fig.update_layout(**fl, hovermode="x unified", showlegend=False)

        # Summary stats
        def _fmt(v: Any, pct: bool = False) -> str:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "—"
            if pct and abs(v) < 1:
                return f"{v*100:.2f}%"
            return f"{v:.4f}"

        return (
            fig,
            _fmt(detail["value"].iloc[-1]),
            _fmt(stats.get("mean_val")),
            _fmt(stats.get("min_val")),
            _fmt(stats.get("max_val")),
            _fmt(stats.get("std_val")),
            str(int(stats.get("obs_count", 0))),
        )

    # 5. Observations table
    @app.callback(
        [Output("exp-obs-table", "data"),
         Output("exp-obs-subtitle", "children")],
        Input("exp-selected-signal", "data"),
    )
    def update_obs_table(signal_id: Optional[str]) -> tuple[list[dict], str]:
        if not signal_id:
            return [], ""
        detail = load_signal_detail(signal_id)
        if detail.empty:
            return [], "No data"

        anomaly_mask = flag_anomalies(detail)

        rows = []
        for i, (_, r) in enumerate(detail.iterrows()):
            def _fmt(v: Any, scale: float = 1.0) -> str:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return "—"
                return f"{v * scale:.4f}"

            rows.append({
                "as_of_str": r["as_of"].strftime("%Y-%m-%d"),
                "value_fmt": _fmt(r["value"]),
                "zscore_fmt": f"{r['zscore']:+.2f}" if pd.notna(r.get("zscore")) else "—",
                "pct_fmt": f"{r['level_percentile']*100:.0f}%" if pd.notna(r.get("level_percentile")) else "—",
                "dir_fmt": _DIR_ARROW.get(r.get("direction", ""), ""),
                "change_1m_fmt": _fmt(r.get("change_1m")),
                "change_3m_fmt": _fmt(r.get("change_3m")),
                "change_12m_fmt": _fmt(r.get("change_12m")),
                "dist_eq_fmt": _fmt(r.get("distance_from_equilibrium")),
                "stale_fmt": "✓" if r.get("is_stale") else "",
                "anomaly": 1 if anomaly_mask.iloc[i] else 0,
            })

        n_anomalies = int(anomaly_mask.sum())
        n_stale = int(detail["is_stale"].sum())
        subtitle = (
            f"{len(detail):,} observations · "
            f"{n_anomalies} outliers (|Z|>3) · "
            f"{n_stale} stale rows"
        )
        return rows, subtitle

    # 5b. CSV download
    @app.callback(
        Output("exp-dl-csv", "data"),
        Input("exp-dl-btn", "n_clicks"),
        State("exp-selected-signal", "data"),
        prevent_initial_call=True,
    )
    def download_csv(n_clicks: int, signal_id: Optional[str]) -> Any:
        if not signal_id or not n_clicks:
            return dash.no_update
        detail = load_signal_detail(signal_id)
        safe_name = signal_id.replace(".", "_")
        return dcc.send_data_frame(detail.to_csv, f"{safe_name}.csv", index=False)

    # 6. Quality & Gaps tab
    @app.callback(
        [Output("exp-metadata-card", "children"),
         Output("exp-flags-card", "children"),
         Output("exp-gaps-content", "children")],
        Input("exp-selected-signal", "data"),
    )
    def update_quality(signal_id: Optional[str]) -> tuple:
        if not signal_id:
            return html.P("Select a signal.", className="text-muted small"), html.Div(), html.Div()

        overview = load_signal_overview()
        r_df = overview[overview["id"] == signal_id]
        if r_df.empty:
            return html.P("Not found.", className="text-muted small"), html.Div(), html.Div()
        r = r_df.iloc[0]

        metadata = dbc.ListGroup([
            _meta_item("Source", r["source"]),
            _meta_item("Provider", r["provider"]),
            _meta_item("Source tier", r["source_tier"]),
            _meta_item("Lead/Lag", r["lead_lag"]),
            _meta_item("Units", r["units"]),
            _meta_item("Equilibrium est.", f"{r['equilibrium_estimate']:.4f}" if pd.notna(r.get('equilibrium_estimate')) else "—"),
            _meta_item("Dist. from equilibrium", f"{r['distance_from_equilibrium']:.4f}" if pd.notna(r.get('distance_from_equilibrium')) else "—"),
            _meta_item("First obs", r["first_obs"].strftime("%Y-%m-%d")),
            _meta_item("Last obs", r["latest_as_of"].strftime("%Y-%m-%d")),
            _meta_item("Days since update", str(int(r["days_since_update"]))),
            _meta_item("Linkage", r.get("linkage", "") or "—"),
        ], flush=True, style={"fontSize": "0.78rem", "backgroundColor": "transparent"})

        def _flag_badge(label: str, active: bool, good_when: bool = False) -> dbc.Badge:
            is_good = active == good_when
            color = "#5CBA8A" if is_good else "#E8734C"
            return dbc.Badge(
                f"{'✓' if active else '✗'} {label}",
                style={"backgroundColor": color, "marginRight": "4px", "marginBottom": "4px",
                       "fontSize": "0.75rem"},
            )

        flags_div = html.Div([
            _flag_badge("Stale", bool(r["is_stale"]), good_when=False),
            _flag_badge("Proxy", bool(r["is_proxy"]), good_when=False),
            _flag_badge("Low history", bool(r["low_history"]), good_when=False),
            _flag_badge("Vintage available", bool(r["vintage_available"]), good_when=True),
            _flag_badge("Constructed", bool(r["is_constructed"]), good_when=False),
        ])

        # Gaps
        gaps_df = detect_gaps(signal_id)
        if gaps_df.empty:
            gaps_content = html.P("✓ No unexpected gaps detected.",
                                  className="text-success small")
        else:
            gaps_df["period_start"] = pd.to_datetime(gaps_df["period_start"]).dt.strftime("%Y-%m-%d")
            gaps_df["period_end"] = pd.to_datetime(gaps_df["period_end"]).dt.strftime("%Y-%m-%d")
            gaps_content = html.Div([
                html.Small(f"{len(gaps_df)} gap(s) found:", className="text-warning d-block mb-1"),
                dash_table.DataTable(
                    data=gaps_df.to_dict("records"),
                    columns=[
                        {"name": "Period Start", "id": "period_start"},
                        {"name": "Period End", "id": "period_end"},
                        {"name": "Gap (days)", "id": "gap_days"},
                        {"name": "Expected (days)", "id": "expected_days"},
                    ],
                    style_table={"fontSize": "0.78rem"},
                    style_header={**_TABLE_HEADER, "padding": "3px 6px"},
                    style_cell={**_TABLE_CELL, "padding": "3px 6px"},
                    style_data_conditional=[
                        {"if": {"filter_query": "{gap_days} > 500"},
                         "backgroundColor": "rgba(232, 115, 76, 0.15)"},
                    ],
                    page_size=10,
                ),
            ])

        return metadata, flags_div, gaps_content

    # 7. Raw vs Processed tab
    @app.callback(
        Output("exp-raw-content", "children"),
        Input("exp-selected-signal", "data"),
    )
    def update_raw_compare(signal_id: Optional[str]) -> Any:
        if not signal_id:
            return html.P("Select a signal.", className="text-muted small")

        overview = load_signal_overview()
        r_df = overview[overview["id"] == signal_id]
        if r_df.empty:
            return html.P("Signal not found.", className="text-muted small")

        source = r_df["source"].iloc[0]
        units = r_df["units"].iloc[0]

        if source.startswith("derived:"):
            return html.P(
                "Derived signal — no raw cache (computed from other signals).",
                className="text-muted small",
            )

        df = compare_raw_vs_processed(signal_id, source, n_recent=36)

        if df["raw_value"].isna().all():
            return html.P(
                f"No parquet cache found for source: {source}",
                className="text-warning small",
            )

        is_level = units in ("pct_level", "index_2020eq100", "index_2010eq100",
                             "diffusion_index", "net_pct", "ratio")
        delta_note = (
            "Delta is meaningful for level signals — shows transform rounding."
            if is_level
            else f"Delta is the arithmetic difference (raw level → {units} transform)."
        )

        df_display = df.copy()
        df_display["as_of"] = pd.to_datetime(df_display["as_of"]).dt.strftime("%Y-%m-%d")
        df_display["raw_value"] = df_display["raw_value"].round(6)
        df_display["db_value"] = df_display["db_value"].round(6)
        df_display["delta"] = df_display["delta"].round(6)
        df_display["pct_delta"] = df_display["pct_delta"].round(3)

        return html.Div([
            html.Small(delta_note, className="text-muted d-block mb-2"),
            dash_table.DataTable(
                data=df_display.fillna("—").to_dict("records"),
                columns=[
                    {"name": "Date", "id": "as_of"},
                    {"name": "Raw Cache Value", "id": "raw_value"},
                    {"name": "DB Processed Value", "id": "db_value"},
                    {"name": "Delta (DB − Raw)", "id": "delta"},
                    {"name": "Δ %", "id": "pct_delta"},
                ],
                sort_action="native",
                page_action="native",
                page_size=20,
                style_table={"fontSize": "0.8rem"},
                style_header={**_TABLE_HEADER, "padding": "4px 8px"},
                style_cell={**_TABLE_CELL, "padding": "4px 8px"},
                style_data_conditional=[
                    {"if": {"filter_query": "{pct_delta} > 5 or {pct_delta} < -5"},
                     "backgroundColor": "rgba(232, 115, 76, 0.15)", "color": "#E8734C"},
                ],
            ),
        ])

    # 8. Reference spot-check
    @app.callback(
        Output("exp-ref-result", "children"),
        [Input("exp-ref-btn", "n_clicks"),
         Input("exp-ref-input", "value")],
        State("exp-selected-signal", "data"),
        prevent_initial_call=True,
    )
    def ref_spotcheck(n_clicks: int, ref_val: Optional[float], signal_id: Optional[str]) -> Any:
        if ref_val is None or not signal_id:
            return ""
        detail = load_signal_detail(signal_id, limit=1)
        if detail.empty:
            return html.Small("No data.", className="text-muted")
        db_val = float(detail["value"].iloc[0])
        delta = db_val - ref_val
        pct = (delta / abs(ref_val) * 100) if ref_val != 0 else 0
        color = "#5CBA8A" if abs(pct) < 1 else ("#F4C842" if abs(pct) < 5 else "#E8734C")
        icon = "✅" if abs(pct) < 1 else ("⚠️" if abs(pct) < 5 else "❌")
        return html.Span(
            f"{icon}  DB: {db_val:.6f}  |  Reference: {ref_val:.6f}  |  "
            f"Δ {delta:+.6f}  ({pct:+.2f}%)",
            style={"color": color, "fontFamily": "monospace"},
        )

    # 9. Composite Analysis (A2/I2)
    _register_analysis_callbacks(app)


def _meta_item(label: str, value: str) -> dbc.ListGroupItem:
    return dbc.ListGroupItem(
        [html.Strong(label + ": ", style={"color": "var(--muted-color)"}), html.Span(value)],
        style={"backgroundColor": "transparent", "border": "none",
               "borderBottom": "1px solid var(--border-color)", "padding": "3px 0"},
    )


# ── A2/I2: Composite Analysis callbacks ───────────────────────────────────────

def _register_analysis_callbacks(app: dash.Dash) -> None:
    import numpy as np
    from plotly.subplots import make_subplots

    _FORCE_BORDER = {"growth": "#4C9BE8", "inflation": "#E8734C"}

    @app.callback(
        [Output("exp-corr-chart", "figure"),
         Output("exp-pca-chart",  "figure")],
        [Input("exp-detail-tabs", "active_tab"),
         Input("theme-store",     "data")],
        prevent_initial_call=False,
    )
    def update_composite_analysis(active_tab: str, theme_name: str):
        _empty = go.Figure()
        _empty.update_layout(**figure_layout(theme_name or DEFAULT_THEME))
        if active_tab != "exp-tab-analysis":
            return _empty, _empty

        matrix, signal_meta = load_composite_zscore_matrix()
        if matrix.empty:
            _empty.update_layout(**figure_layout(theme_name or DEFAULT_THEME, "No data"))
            return _empty, _empty

        short_labels  = [m["label"]  for m in signal_meta]
        forces        = [m["force"]  for m in signal_meta]
        border_colors = [_FORCE_BORDER.get(f, "#888") for f in forces]

        # ── Correlation heatmap ───────────────────────────────────────────────
        filled = matrix.copy()
        for col in filled.columns:
            mean = filled[col].mean()
            filled[col] = filled[col].fillna(0.0 if pd.isna(mean) else mean)
        corr   = filled.corr().values

        corr_fig = go.Figure(go.Heatmap(
            z=corr,
            x=short_labels,
            y=short_labels,
            colorscale="RdBu_r",
            zmid=0, zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in corr],
            texttemplate="%{text}",
            textfont={"size": 8},
            hovertemplate="%{y} × %{x}: %{z:.2f}<extra></extra>",
            colorbar={"len": 0.9, "thickness": 12},
        ))
        # Divider line between growth (9) and inflation (8) signals
        n_growth = sum(1 for m in signal_meta if m["force"] == "growth")
        corr_fig.add_shape(type="line",
            x0=n_growth - 0.5, x1=n_growth - 0.5, y0=-0.5, y1=len(signal_meta) - 0.5,
            line={"color": "#ffffff", "width": 1.5, "dash": "dot"},
        )
        corr_fig.add_shape(type="line",
            x0=-0.5, x1=len(signal_meta) - 0.5, y0=n_growth - 0.5, y1=n_growth - 0.5,
            line={"color": "#ffffff", "width": 1.5, "dash": "dot"},
        )
        corr_fig.update_layout(
            **figure_layout(theme_name or DEFAULT_THEME,
                            f"Composite Signal Correlation Matrix  ·  {len(matrix)} months"),
            height=520,
            margin={"l": 130, "r": 80, "t": 50, "b": 120},
        )

        # ── PCA ───────────────────────────────────────────────────────────────
        try:
            pca = compute_pca(matrix)
        except ValueError as exc:
            pca_fig = go.Figure()
            pca_fig.update_layout(
                **figure_layout(theme_name or DEFAULT_THEME, "PCA unavailable"),
                height=320,
            )
            pca_fig.add_annotation(
                text=str(exc), x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False,
            )
            return corr_fig, pca_fig
        var_r   = pca["explained_variance_ratio"]
        loadings = pca["loadings"]
        n_obs   = pca["n_obs"]
        n_show  = min(10, len(var_r))

        pca_fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=[
                "Explained Variance by PC",
                "PC1 & PC2 Loadings per Signal",
            ],
            column_widths=[0.30, 0.70],
        )

        # Scree bar + cumulative line
        pca_fig.add_trace(go.Bar(
            x=[f"PC{i+1}" for i in range(n_show)],
            y=var_r[:n_show] * 100,
            marker_color="#4C9BE8",
            showlegend=False,
            hovertemplate="PC%{x}: %{y:.1f}%<extra></extra>",
        ), row=1, col=1)
        pca_fig.add_trace(go.Scatter(
            x=[f"PC{i+1}" for i in range(n_show)],
            y=np.cumsum(var_r[:n_show]) * 100,
            mode="lines+markers",
            line={"color": "#E8734C", "width": 1.5},
            marker={"size": 5},
            name="Cumulative",
            hovertemplate="Cumulative: %{y:.1f}%<extra></extra>",
        ), row=1, col=1)
        pca_fig.update_yaxes(title_text="% variance", range=[0, 110], row=1, col=1)

        # Loadings heatmap (PC1 + PC2 × all 17 signals)
        pca_fig.add_trace(go.Heatmap(
            z=loadings[:2],
            x=short_labels,
            y=["PC1", "PC2"],
            colorscale="RdBu_r",
            zmid=0,
            text=[[f"{v:.2f}" for v in row] for row in loadings[:2]],
            texttemplate="%{text}",
            textfont={"size": 8},
            hovertemplate="%{y} · %{x}: %{z:.2f}<extra></extra>",
            showscale=False,
        ), row=1, col=2)

        pca_fig.update_layout(
            **figure_layout(theme_name or DEFAULT_THEME,
                            f"PCA  ·  {n_obs} observations  ·  "
                            f"PC1+PC2 = {(var_r[0]+var_r[1])*100:.1f}% variance"),
            height=320,
            margin={"l": 55, "r": 20, "t": 50, "b": 90},
        )

        return corr_fig, pca_fig

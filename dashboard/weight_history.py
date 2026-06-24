"""Weight Change History page.

Displays a log of all importance changes made via the Weight Audit editor,
with an editable Reason column so the user can record or update their
rationale at any time.
"""
from __future__ import annotations

import pandas as pd
from dash import Input, Output, State, callback, dash_table, dcc, html, no_update
from dash.exceptions import PreventUpdate

from store.store import get_connection, query_weight_change_log, update_weight_change_reason

_SOURCE_LABELS = {"manual": "Manual", "regression": "Regression"}
_DELTA_POS = "#5CBA8A"
_DELTA_NEG = "#E8734C"
_MUTED = "#8b97a8"


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div([
        dcc.Store(id="wh-country-filter", data="ALL"),

        # Header
        html.Div([
            html.Div([
                html.H4("Weight Change History", style={
                    "fontSize": "1.05rem", "fontWeight": "700",
                    "color": "var(--font-color)", "margin": "0 0 4px 0",
                }),
                html.Span(
                    "Log of all importance changes made via the Weight Audit editor. "
                    "Edit the Reason column to record or update your rationale — "
                    "click Save Notes to persist.",
                    style={"fontSize": "0.80rem", "color": "var(--muted-color)"},
                ),
            ]),
            html.Button(
                "↺ Refresh",
                id="wh-refresh-btn",
                n_clicks=0,
                style={
                    "fontSize": "0.78rem", "padding": "4px 12px",
                    "background": "var(--card-bg)",
                    "color": "var(--slider-accent, #E8A317)",
                    "border": "1px solid var(--slider-accent, #E8A317)",
                    "borderRadius": "4px", "cursor": "pointer",
                    "alignSelf": "flex-start",
                },
            ),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "marginBottom": "16px"}),

        # Filter bar
        html.Div([
            html.Span("Country:", style={
                "fontSize": "0.78rem", "color": "var(--muted-color)",
                "marginRight": "8px", "alignSelf": "center",
            }),
            dcc.Dropdown(
                id="wh-country-dropdown",
                options=[{"label": "All countries", "value": "ALL"}],
                value="ALL",
                clearable=False,
                style={
                    "width": "160px", "fontSize": "0.80rem",
                    "backgroundColor": "var(--card-bg)", "color": "var(--font-color)",
                },
            ),
            html.Span(id="wh-row-count", style={
                "fontSize": "0.78rem", "color": "var(--muted-color)",
                "marginLeft": "16px", "alignSelf": "center",
            }),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),

        # Table
        dash_table.DataTable(
            id="wh-table",
            columns=[
                {"name": "log_id",     "id": "log_id",     "editable": False, "type": "numeric"},
                {"name": "Date",       "id": "changed_at", "editable": False},
                {"name": "Country",    "id": "country",    "editable": False},
                {"name": "Signal",     "id": "signal_id",  "editable": False},
                {"name": "Basket",     "id": "basket",     "editable": False},
                {"name": "Old",        "id": "old_importance", "editable": False,
                 "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "New",        "id": "new_importance", "editable": False,
                 "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "Δ",          "id": "delta",      "editable": False,
                 "type": "numeric", "format": {"specifier": "+.2f"}},
                {"name": "Source",     "id": "source",     "editable": False},
                {"name": "Reason",     "id": "reason",     "editable": True},
            ],
            data=[],
            editable=True,
            row_selectable=False,
            page_action="native",
            page_size=25,
            sort_action="native",
            sort_by=[{"column_id": "changed_at", "direction": "desc"}],
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": "var(--card-bg, #1e2128)",
                "color": "var(--muted-color, #8b97a8)",
                "fontSize": "0.70rem", "fontWeight": "700",
                "textTransform": "uppercase", "letterSpacing": "0.05em",
                "borderBottom": "1px solid var(--border-color, #2a2d35)",
                "padding": "6px 10px", "whiteSpace": "nowrap",
            },
            style_cell={
                "backgroundColor": "var(--page-bg, #14171e)",
                "color": "var(--font-color, #d4dae4)",
                "fontSize": "0.82rem",
                "border": "none",
                "borderBottom": "1px solid var(--border-color, #2a2d35)",
                "padding": "5px 10px",
                "fontFamily": "inherit",
                "whiteSpace": "normal",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_cell_conditional=[
                {"if": {"column_id": "reason"},
                 "backgroundColor": "var(--card-bg, #1e2128)",
                 "minWidth": "220px", "maxWidth": "400px"},
                {"if": {"column_id": "log_id"},   "width": "50px",  "textAlign": "right"},
                {"if": {"column_id": "changed_at"}, "minWidth": "140px"},
                {"if": {"column_id": "signal_id"}, "fontWeight": "600"},
            ],
            style_data_conditional=[
                {"if": {"filter_query": "{delta} > 0", "column_id": "delta"},
                 "color": _DELTA_POS, "fontWeight": "700"},
                {"if": {"filter_query": "{delta} < 0", "column_id": "delta"},
                 "color": _DELTA_NEG, "fontWeight": "700"},
                {"if": {"filter_query": '{basket} = "Growth"', "column_id": "basket"},
                 "color": _DELTA_POS},
                {"if": {"filter_query": '{basket} = "Inflation"', "column_id": "basket"},
                 "color": _DELTA_NEG},
                {"if": {"filter_query": '{source} = "regression"', "column_id": "source"},
                 "color": "#4C9BE8"},
                {"if": {"column_id": "reason"},
                 "color": "var(--font-color)", "fontStyle": "normal"},
            ],
            style_as_list_view=True,
            tooltip_delay=0,
            tooltip_duration=None,
            tooltip_data=[],
        ),

        # Save notes bar
        html.Div([
            html.Button(
                "💾 Save Notes",
                id="wh-save-btn",
                n_clicks=0,
                style={
                    "fontSize": "0.78rem", "padding": "4px 14px",
                    "background": "var(--slider-accent, #E8A317)",
                    "color": "#14171e", "border": "none",
                    "borderRadius": "4px", "cursor": "pointer", "fontWeight": "700",
                    "marginRight": "12px",
                },
            ),
            html.Span(id="wh-save-msg", style={
                "fontSize": "0.78rem", "color": "var(--muted-color)",
            }),
        ], style={"display": "flex", "alignItems": "center", "marginTop": "12px"}),

    ], style={"padding": "16px 20px", "maxWidth": "1400px", "margin": "0 auto"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_row(row: dict) -> dict:
    ts = str(row.get("changed_at", ""))[:19].replace("T", " ")
    return {
        "log_id":         int(row.get("log_id", 0)),
        "changed_at":     ts,
        "country":        str(row.get("country", "")),
        "signal_id":      str(row.get("signal_id", "")),
        "basket":         str(row.get("basket", "")),
        "old_importance": float(row.get("old_importance", 0)),
        "new_importance": float(row.get("new_importance", 0)),
        "delta":          float(row.get("delta", 0)),
        "source":         _SOURCE_LABELS.get(str(row.get("source", "")), str(row.get("source", ""))),
        "reason":         str(row.get("reason", "") or ""),
    }


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    [Output("wh-table",           "data"),
     Output("wh-country-dropdown","options"),
     Output("wh-row-count",       "children")],
    [Input("page-trigger",        "data"),
     Input("wh-refresh-btn",      "n_clicks"),
     Input("wh-country-dropdown", "value")],
    prevent_initial_call=False,
)
def load_history(_, _refresh, country_filter):
    try:
        with get_connection() as conn:
            df = query_weight_change_log(conn)
    except Exception as exc:
        return [], [{"label": "All countries", "value": "ALL"}], f"Error: {exc}"

    if df.empty:
        return [], [{"label": "All countries", "value": "ALL"}], "No changes logged yet."

    # Country filter options
    countries = sorted(df["country"].unique().tolist())
    options = [{"label": "All countries", "value": "ALL"}] + [
        {"label": c, "value": c} for c in countries
    ]

    if country_filter and country_filter != "ALL":
        df = df[df["country"] == country_filter]

    rows = [_fmt_row(r) for r in df.to_dict("records")]
    count_msg = f"{len(rows)} change(s)"
    return rows, options, count_msg


@callback(
    [Output("wh-save-msg",  "children"),
     Output("wh-table",     "data",    allow_duplicate=True)],
    Input("wh-save-btn",    "n_clicks"),
    [State("wh-table",      "data"),
     State("wh-country-dropdown", "value")],
    prevent_initial_call=True,
)
def save_notes(n_clicks, table_data, country_filter):
    if not n_clicks or not table_data:
        raise PreventUpdate

    updated = 0
    errors = 0
    try:
        with get_connection() as conn:
            for row in table_data:
                log_id = row.get("log_id")
                reason = row.get("reason", "") or ""
                if log_id is not None:
                    try:
                        update_weight_change_reason(conn, int(log_id), reason)
                        updated += 1
                    except Exception:
                        errors += 1
    except Exception as exc:
        return html.Span(f"Save error: {exc}", style={"color": _DELTA_NEG}), no_update

    msg = f"Saved {updated} note(s)."
    if errors:
        msg += f" ({errors} error(s))"

    # Reload to confirm
    try:
        with get_connection() as conn:
            df = query_weight_change_log(
                conn, country=country_filter if country_filter != "ALL" else None
            )
        rows = [_fmt_row(r) for r in df.to_dict("records")]
    except Exception:
        rows = table_data

    return html.Span(msg, style={"color": _DELTA_POS}), rows

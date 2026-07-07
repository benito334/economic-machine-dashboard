"""Workbench — TradingView-style chart studio (route /workbench).

Replaces both Chart Overlay and Data Explorer (2026-07-06 redesign):
  * omnibox symbol search ("/" to focus) over every plottable series —
    signals, composite scores, debt stress, raw FRED cache
  * overlay mode (one pane, per-series transforms solve mixed units) and
    stacked mode (grouped panes, shared X, synced crosshair)
  * per-series transform: Raw · Rebase=100 · % from start · YoY % · Z (stored)
  * inspector drawer per series (metadata, stats, observations + CSV,
    gaps, raw-vs-processed audit) — the old Data Explorer, docked
  * saved views (JSON under DATA_DIR) + URL deep links (?view=name) +
    built-in presets

Old routes /charts and /explorer land here.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash_bootstrap_components as dbc
from dash import (ALL, Input, Output, State, callback, ctx, dash_table, dcc,
                  html, no_update)
from dash.exceptions import PreventUpdate

from dashboard import workbench_data as wd
from dashboard.themes import DEFAULT_THEME, THEMES, figure_layout

logger = logging.getLogger(__name__)

_PALETTE = ["#4C9BE8", "#E8734C", "#5CBA8A", "#F4C842", "#B07FD4",
            "#4CE8D4", "#E84C82", "#8AB4F4", "#E8C94C", "#3FBFB0"]

_TIMEFRAMES = ["1Y", "3Y", "5Y", "10Y", "MAX"]

_FLAGS = {"US": "🇺🇸", "EZ": "🇪🇺", "GB": "🇬🇧", "JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳",
          "IN": "🇮🇳", "DE": "🇩🇪", "LU": "🇱🇺", "—": "🌐"}


def _tf_start(tf: str) -> Optional[pd.Timestamp]:
    years = {"1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10}.get(tf)
    return pd.Timestamp.today() - pd.DateOffset(years=years) if years else None


def _series_color(i: int) -> str:
    return _PALETTE[i % len(_PALETTE)]


def _label_for(source: str, key: str) -> str:
    for r in wd.build_search_index():
        if r["source"] == source and r["key"] == key:
            return r["label"]
    return key


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    view_opts = [{"label": v, "value": v} for v in wd.list_views()]
    return html.Div([
        dcc.Store(id="wb-series", data=[], storage_type="session"),
        dcc.Store(id="wb-config", data={"mode": "overlay", "timeframe": "10Y"},
                  storage_type="session"),
        dcc.Store(id="wb-hover-dummy"),

        # ── Top bar: search + facets ──────────────────────────────────────────
        html.Div([
            html.Div([
                dcc.Input(id="wb-search", type="text", debounce=False,
                          placeholder='Search anything plottable —  "/" to focus  ·  e.g. "cpi jp", "yield 10y", "growth composite"',
                          autoComplete="off",
                          style={"width": "100%", "background": "var(--card-bg)",
                                 "border": "1px solid var(--border-color)",
                                 "borderRadius": "6px", "color": "var(--font-color)",
                                 "padding": "7px 12px", "fontSize": "0.85rem"}),
                html.Div(id="wb-search-results", style={
                    "position": "absolute", "top": "40px", "left": 0, "right": 0,
                    "zIndex": 1200, "background": "var(--card-bg)",
                    "border": "1px solid var(--border-color)", "borderRadius": "6px",
                    "maxHeight": "420px", "overflowY": "auto",
                    "boxShadow": "0 8px 22px rgba(0,0,0,0.45)"}),
            ], style={"position": "relative", "flex": "1 1 420px"}),
            dcc.Dropdown(id="wb-facet-country", multi=True, placeholder="country",
                         options=[{"label": f"{_FLAGS[c]} {c}", "value": c}
                                  for c in ["US", "EZ", "GB", "JP", "KR", "CN", "IN", "DE", "LU"]],
                         style={"minWidth": "150px", "fontSize": "0.78rem"}),
            dcc.Dropdown(id="wb-facet-group", multi=True, placeholder="force / group",
                         options=[{"label": g, "value": g} for g in
                                  ["growth", "inflation", "policy", "credit", "premium",
                                   "volatility", "master", "fiscal", "external", "capital",
                                   "currency", "demographics", "order", "composite",
                                   "debt cycle", "raw fred"]],
                         style={"minWidth": "170px", "fontSize": "0.78rem"}),
        ], style={"display": "flex", "gap": "8px", "alignItems": "flex-start",
                  "marginBottom": "6px"}),

        # ── Second bar: timeframe · mode · views ──────────────────────────────
        html.Div([
            dbc.ButtonGroup([
                dbc.Button(tf, id={"type": "wb-tf", "tf": tf}, size="sm",
                           outline=True, color="secondary") for tf in _TIMEFRAMES
            ]),
            dbc.RadioItems(
                id="wb-mode", value="overlay", inline=True,
                options=[{"label": "Overlay", "value": "overlay"},
                         {"label": "Stacked", "value": "stacked"}],
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "12px", "fontSize": "0.8rem"},
                style={"marginLeft": "14px"}),
            html.Div([
                html.Span("axis:", style={"fontSize": "0.72rem",
                                          "color": "var(--muted-color)",
                                          "marginRight": "6px"}),
                dbc.RadioItems(
                    id="wb-axis", value="shared", inline=True,
                    options=[{"label": "Shared", "value": "shared"},
                             {"label": "Independent", "value": "independent"}],
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"marginRight": "10px", "fontSize": "0.78rem"}),
            ], id="wb-axis-wrap",
                title="Overlay only — Independent gives every series its own "
                      "auto-scaled y-axis (values read from the crosshair), so a "
                      "small-range series isn't flattened by a large-range one.",
                style={"display": "flex", "alignItems": "center"}),
            dbc.Button("Clear", id="wb-clear", size="sm", outline=True,
                       color="secondary", style={"marginLeft": "auto"}),
            dcc.Dropdown(id="wb-view-select", placeholder="Saved views…",
                         options=view_opts, clearable=True,
                         style={"minWidth": "230px", "fontSize": "0.78rem"}),
            dcc.Input(id="wb-view-name", type="text", placeholder="name…",
                      autoComplete="off",
                      style={"width": "130px", "background": "var(--card-bg)",
                             "border": "1px solid var(--border-color)",
                             "borderRadius": "6px", "color": "var(--font-color)",
                             "padding": "4px 8px", "fontSize": "0.78rem"}),
            dbc.Button("★ Save", id="wb-view-save", size="sm", color="warning",
                       outline=True),
            dbc.Button("🗑", id="wb-view-delete", size="sm", color="secondary",
                       outline=True, title="Delete the selected saved view"),
            html.Span(id="wb-view-status",
                      style={"fontSize": "0.72rem", "color": "var(--muted-color)"}),
        ], style={"display": "flex", "gap": "8px", "alignItems": "center",
                  "marginBottom": "6px", "flexWrap": "wrap"}),

        # ── Legend pills ──────────────────────────────────────────────────────
        html.Div(id="wb-pills", style={"display": "flex", "gap": "6px",
                                       "flexWrap": "wrap", "marginBottom": "4px"}),

        # ── Chart ─────────────────────────────────────────────────────────────
        html.Div(
            dcc.Graph(id="wb-chart", responsive=True,
                      config={"displayModeBar": True, "scrollZoom": True,
                              "modeBarButtonsToRemove": ["select2d", "lasso2d"]},
                      style={"height": "calc(100vh - 210px)", "minHeight": "480px"}),
            id="wb-chart-wrap"),

        # ── Inspector drawer ──────────────────────────────────────────────────
        dbc.Offcanvas(id="wb-inspector", title="Inspector", placement="end",
                      is_open=False, scrollable=True,
                      style={"width": "480px", "background": "var(--page-bg)"},
                      children=html.Div(id="wb-inspector-body")),
    ], className="pe-2 pt-2", style={"maxWidth": "1600px", "margin": "0 auto"})


# ── Search results ────────────────────────────────────────────────────────────

@callback(
    Output("wb-search-results", "children"),
    [Input("wb-search", "value"),
     Input("wb-facet-country", "value"),
     Input("wb-facet-group", "value")],
    prevent_initial_call=True,
)
def wb_search_results(query, countries, groups):
    if not (query or countries or groups):
        return []
    rows = wd.search_index(query or "", countries, groups, limit=14)
    if not rows:
        return html.Div("no matches", style={"padding": "8px 12px",
                                             "color": "var(--muted-color)",
                                             "fontSize": "0.8rem"})
    out = []
    for r in rows:
        out.append(html.Div([
            html.Span(_FLAGS.get(r["country"], "🌐"),
                      style={"marginRight": "8px"}),
            html.Span(r["label"], style={"fontWeight": "600", "flex": "1",
                                         "fontSize": "0.8rem"}),
            html.Span(r["group"], style={"fontSize": "0.66rem", "color": "#888",
                                         "border": "1px solid var(--border-color)",
                                         "borderRadius": "3px", "padding": "1px 5px",
                                         "marginRight": "8px"}),
            html.Span(f"{r['first']}→{r['last']}" if r["first"] else "cache",
                      style={"fontSize": "0.66rem", "color": "var(--muted-color)"}),
        ],
            id={"type": "wb-add", "source": r["source"], "key": r["key"]},
            n_clicks=0,
            style={"display": "flex", "alignItems": "center", "padding": "7px 12px",
                   "cursor": "pointer",
                   "borderBottom": "1px solid var(--border-color)"},
            className="wb-result-row"))
    return out


# ── Series-list mutations (single owner of wb-series) ────────────────────────

@callback(
    [Output("wb-series", "data"),
     Output("wb-config", "data", allow_duplicate=True),
     Output("wb-search", "value"),
     Output("wb-view-select", "value")],
    [Input({"type": "wb-add", "source": ALL, "key": ALL}, "n_clicks"),
     Input({"type": "wb-remove", "idx": ALL}, "n_clicks"),
     Input({"type": "wb-transform", "idx": ALL}, "value"),
     Input({"type": "wb-pane", "idx": ALL}, "value"),
     Input("wb-clear", "n_clicks"),
     Input("wb-view-select", "value"),
     Input("url", "search")],
    [State("wb-series", "data"),
     State("wb-config", "data"),
     State("page-trigger", "data")],
    prevent_initial_call=True,
)
def wb_mutate(add_clicks, rm_clicks, transforms, panes, clear, view_name,
              url_search, series, config, page_trigger):
    page = (page_trigger or {}).get("page", "")
    if page not in ("/workbench", "/charts", "/explorer"):
        raise PreventUpdate
    series = list(series or [])
    config = dict(config or {"mode": "overlay", "timeframe": "10Y"})
    trig = ctx.triggered_id
    if trig is None:
        raise PreventUpdate

    # Deep link ?view=name (fires on page load via url.search)
    if trig == "url":
        params = urllib.parse.parse_qs((url_search or "").lstrip("?"))
        name = (params.get("view") or [None])[0]
        if not name:
            raise PreventUpdate
        spec = wd.get_view(name)
        if not spec:
            raise PreventUpdate
        return _spec_to_series(spec), {"mode": spec.get("mode", "overlay"),
                                       "axis": spec.get("axis", "shared"),
                                       "timeframe": spec.get("timeframe", "10Y")}, "", name

    if trig == "wb-view-select":
        if not view_name:
            raise PreventUpdate
        spec = wd.get_view(view_name)
        if not spec:
            raise PreventUpdate
        return _spec_to_series(spec), {"mode": spec.get("mode", "overlay"),
                                       "axis": spec.get("axis", "shared"),
                                       "timeframe": spec.get("timeframe", "10Y")}, "", view_name

    if trig == "wb-clear":
        return [], no_update, "", None

    if isinstance(trig, dict) and trig.get("type") == "wb-add":
        if not any(add_clicks or []):
            raise PreventUpdate
        src, key = trig["source"], trig["key"]
        if any(s["source"] == src and s["key"] == key for s in series):
            return series, no_update, "", no_update       # already plotted
        series.append({"source": src, "key": key,
                       "label": _label_for(src, key),
                       "transform": "raw",
                       "pane": max([s.get("pane", 1) for s in series], default=0) + 1})
        return series, no_update, "", no_update           # clear search box

    if isinstance(trig, dict) and trig.get("type") == "wb-remove":
        if not any(rm_clicks or []):
            raise PreventUpdate
        i = trig["idx"]
        if 0 <= i < len(series):
            series.pop(i)
        return series, no_update, no_update, no_update

    if isinstance(trig, dict) and trig.get("type") == "wb-transform":
        i = trig["idx"]
        if 0 <= i < len(series) and transforms and i < len(transforms):
            series[i]["transform"] = transforms[i] or "raw"
        return series, no_update, no_update, no_update

    if isinstance(trig, dict) and trig.get("type") == "wb-pane":
        i = trig["idx"]
        if 0 <= i < len(series) and panes and i < len(panes):
            try:
                series[i]["pane"] = max(1, int(panes[i]))
            except (TypeError, ValueError):
                pass
        return series, no_update, no_update, no_update

    raise PreventUpdate


def _spec_to_series(spec: dict) -> list[dict]:
    out = []
    for i, s in enumerate(spec.get("series", [])):
        out.append({"source": s["source"], "key": s["key"],
                    "label": _label_for(s["source"], s["key"]),
                    "transform": s.get("transform", "raw"),
                    "pane": int(s.get("pane", i + 1))})
    return out


# ── Config (mode + timeframe) ────────────────────────────────────────────────

@callback(
    Output("wb-config", "data"),
    [Input("wb-mode", "value"),
     Input("wb-axis", "value"),
     Input({"type": "wb-tf", "tf": ALL}, "n_clicks")],
    State("wb-config", "data"),
    prevent_initial_call=True,
)
def wb_config(mode, axis, tf_clicks, config):
    config = dict(config or {"mode": "overlay", "timeframe": "10Y"})
    trig = ctx.triggered_id
    if trig == "wb-mode":
        config["mode"] = mode or "overlay"
    elif trig == "wb-axis":
        config["axis"] = axis or "shared"
    elif isinstance(trig, dict) and trig.get("type") == "wb-tf":
        if not any(tf_clicks or []):
            raise PreventUpdate
        config["timeframe"] = trig["tf"]
    return config


@callback(Output("wb-mode", "value"), Input("wb-config", "data"))
def wb_mode_sync(config):
    return (config or {}).get("mode", "overlay")


@callback(
    [Output("wb-axis", "value"),
     Output("wb-axis-wrap", "style")],
    Input("wb-config", "data"),
)
def wb_axis_sync(config):
    config = config or {}
    # The independent-axis toggle is meaningful only in overlay mode.
    visible = {"display": "flex", "alignItems": "center"}
    hidden = {"display": "none"}
    style = visible if config.get("mode", "overlay") == "overlay" else hidden
    return config.get("axis", "shared"), style


# ── Legend pills ──────────────────────────────────────────────────────────────

@callback(
    Output("wb-pills", "children"),
    [Input("wb-series", "data"), Input("wb-config", "data")],
)
def wb_pills(series, config):
    mode = (config or {}).get("mode", "overlay")
    pills = []
    for i, s in enumerate(series or []):
        color = _series_color(i)
        bits = [
            html.Span("●", style={"color": color, "marginRight": "6px"}),
            html.Span(s["label"], style={"fontSize": "0.75rem", "fontWeight": "600",
                                         "marginRight": "6px"}),
            dcc.Dropdown(
                id={"type": "wb-transform", "idx": i},
                value=s.get("transform", "raw"), clearable=False,
                options=[{"label": v, "value": k} for k, v in wd.TRANSFORMS.items()],
                style={"width": "128px", "fontSize": "0.7rem",
                       "display": "inline-block", "verticalAlign": "middle"}),
        ]
        if mode == "stacked":
            bits.append(dcc.Input(
                id={"type": "wb-pane", "idx": i}, type="number",
                value=s.get("pane", i + 1), min=1, max=8, step=1,
                placeholder="pane",
                style={"width": "52px", "marginLeft": "6px",
                       "background": "var(--card-bg)", "color": "var(--font-color)",
                       "border": "1px solid var(--border-color)",
                       "borderRadius": "4px", "fontSize": "0.72rem",
                       "padding": "2px 5px"}))
        bits += [
            html.Span("🔍", id={"type": "wb-inspect", "idx": i}, n_clicks=0,
                      title="Inspect this series (metadata, observations, quality)",
                      style={"cursor": "pointer", "marginLeft": "7px"}),
            html.Span("✕", id={"type": "wb-remove", "idx": i}, n_clicks=0,
                      title="Remove", style={"cursor": "pointer", "marginLeft": "6px",
                                             "color": "var(--muted-color)"}),
        ]
        pills.append(html.Div(bits, style={
            "display": "flex", "alignItems": "center",
            "border": f"1px solid {color}55", "borderRadius": "6px",
            "padding": "3px 9px", "background": "var(--card-bg)"}))
    if not pills:
        pills = [html.Span("Search above to add series — try a preset from Saved views.",
                           style={"fontSize": "0.78rem", "color": "var(--muted-color)"})]
    return pills


# ── Chart ─────────────────────────────────────────────────────────────────────

@callback(
    Output("wb-chart", "figure"),
    [Input("wb-series", "data"),
     Input("wb-config", "data"),
     Input("theme-store", "data")],
)
def wb_chart(series, config, theme_name):
    theme_name = theme_name or DEFAULT_THEME
    config = config or {}
    mode = config.get("mode", "overlay")
    tf = config.get("timeframe", "10Y")
    start = _tf_start(tf)

    if not series:
        fig = go.Figure()
        fig.update_layout(**figure_layout(
            theme_name, "Workbench — search for a series or load a saved view"))
        return fig

    loaded = []
    for i, s in enumerate(series):
        raw, meta = wd.load_series(s["source"], s["key"])
        ts, sfx = wd.apply_transform(raw, s.get("transform", "raw"), meta,
                                     window_start=start)
        if start is not None:
            ts = ts[ts.index >= start]
        loaded.append({**s, "ts": ts, "sfx": sfx, "color": _series_color(i)})

    if mode == "overlay":
        plottable = [it for it in loaded if not it["ts"].empty]
        # Independent axes (TV multiple-price-scales): each series on its own
        # auto-scaled y-axis so a small-range series isn't flattened by a
        # large-range one. Only meaningful with 2+ series.
        independent = config.get("axis") == "independent" and len(plottable) > 1
        fig = go.Figure()
        layout = figure_layout(theme_name, "")
        for n, item in enumerate(plottable, start=1):
            yaxis_id = "y" if (not independent or n == 1) else f"y{n}"
            fig.add_trace(go.Scatter(
                x=item["ts"].index, y=item["ts"].values, mode="lines",
                name=item["label"] + item["sfx"], yaxis=yaxis_id,
                line={"color": item["color"], "width": 1.6},
                hovertemplate="%{x|%Y-%m-%d} · %{y:.3f}<extra>"
                              + item["label"] + item["sfx"] + "</extra>"))
            if independent and n > 1:
                # overlay this axis on the base; hidden ticks (N scales can't
                # share one label column — the crosshair carries each value)
                layout[f"yaxis{n}"] = dict(overlaying="y", side="right",
                                           showgrid=False, zeroline=False,
                                           showticklabels=False)
        layout.update(hovermode="x unified" if independent else "x",
                      dragmode="pan",
                      legend=dict(orientation="h", y=1.06, font=dict(size=10)),
                      margin=dict(l=10, r=55, t=30, b=20))
        fig.update_layout(**layout)
        if independent:
            # hide the base axis ticks too, and drop grid (overlapping scales)
            fig.update_layout(yaxis=dict(showticklabels=False, showgrid=False,
                                         zeroline=False))
        else:
            fig.update_yaxes(side="right")
        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor",
                         spikedash="dot", spikethickness=1,
                         spikecolor="rgba(180,180,180,0.6)",
                         rangeslider=dict(visible=True, thickness=0.05))
        return fig

    # ── stacked ───────────────────────────────────────────────────────────────
    panes = sorted({item.get("pane", 1) for item in loaded})
    pane_row = {p: i + 1 for i, p in enumerate(panes)}
    fig = make_subplots(rows=len(panes), cols=1, shared_xaxes=True,
                        vertical_spacing=min(0.03, 0.24 / max(1, len(panes))))
    for item in loaded:
        if item["ts"].empty:
            continue
        fig.add_trace(go.Scatter(
            x=item["ts"].index, y=item["ts"].values, mode="lines",
            name=item["label"] + item["sfx"],
            line={"color": item["color"], "width": 1.5},
            hovertemplate="%{x|%Y-%m-%d} · %{y:.3f}<extra>"
                          + item["label"] + "</extra>"),
            row=pane_row.get(item.get("pane", 1), 1), col=1)
    layout = figure_layout(theme_name, "")
    layout.update(hovermode="x", hoversubplots="axis", dragmode="pan",
                  legend=dict(orientation="h", y=1.04, font=dict(size=10)),
                  margin=dict(l=10, r=55, t=30, b=20),
                  uirevision=f"wb-{len(panes)}")
    fig.update_layout(**layout)
    fig.update_yaxes(side="right")
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor",
                     spikedash="dot", spikethickness=1,
                     spikecolor="rgba(180,180,180,0.6)")
    return fig


# ── Saved views ───────────────────────────────────────────────────────────────

@callback(
    [Output("wb-view-select", "options"),
     Output("wb-view-status", "children")],
    [Input("wb-view-save", "n_clicks"),
     Input("wb-view-delete", "n_clicks")],
    [State("wb-view-name", "value"),
     State("wb-view-select", "value"),
     State("wb-series", "data"),
     State("wb-config", "data")],
    prevent_initial_call=True,
)
def wb_views(save_n, del_n, name, selected, series, config):
    trig = ctx.triggered_id
    msg = ""
    try:
        if trig == "wb-view-save":
            if not save_n:
                raise PreventUpdate
            if not series:
                msg = "nothing to save"
            else:
                spec = {"mode": (config or {}).get("mode", "overlay"),
                        "axis": (config or {}).get("axis", "shared"),
                        "timeframe": (config or {}).get("timeframe", "10Y"),
                        "series": [{k: s[k] for k in ("source", "key", "transform", "pane")
                                    if k in s} for s in series]}
                wd.save_view(name or "", spec)
                msg = f"saved '{name}' — deep link: /workbench?view={urllib.parse.quote(name or '')}"
        elif trig == "wb-view-delete":
            if not del_n:
                raise PreventUpdate
            if selected and selected not in wd.PRESET_VIEWS:
                wd.delete_view(selected)
                msg = f"deleted '{selected}'"
            else:
                msg = "select a non-preset view first"
    except ValueError as exc:
        msg = str(exc)
    opts = [{"label": v, "value": v} for v in wd.list_views()]
    return opts, msg


# ── Inspector ─────────────────────────────────────────────────────────────────

@callback(
    [Output("wb-inspector", "is_open"),
     Output("wb-inspector-body", "children")],
    Input({"type": "wb-inspect", "idx": ALL}, "n_clicks"),
    State("wb-series", "data"),
    prevent_initial_call=True,
)
def wb_inspector(clicks, series):
    if not any(clicks or []):
        raise PreventUpdate
    trig = ctx.triggered_id
    i = trig["idx"] if isinstance(trig, dict) else None
    if i is None or not series or i >= len(series):
        raise PreventUpdate
    s = series[i]
    return True, _inspector_body(s)


def _inspector_body(s: dict) -> list:
    from dashboard.explorer_data import (compare_raw_vs_processed,
                                         compute_signal_stats, detect_gaps,
                                         load_signal_detail)
    head = [html.Div(s["label"], style={"fontWeight": "700", "fontSize": "0.95rem",
                                        "marginBottom": "2px"}),
            html.Div(f"{s['source']} · {s['key']}",
                     style={"fontSize": "0.72rem", "color": "var(--muted-color)",
                            "fontFamily": "monospace", "marginBottom": "10px"})]

    if s["source"] != "signal":
        ts, _meta = wd.load_series(s["source"], s["key"])
        if ts.empty:
            return head + [html.Div("No data.", style={"color": "var(--muted-color)"})]
        stats = html.Div([
            _kv("observations", f"{len(ts):,}"),
            _kv("span", f"{ts.index[0].date()} → {ts.index[-1].date()}"),
            _kv("latest", f"{ts.iloc[-1]:,.4f}"),
            _kv("mean / std", f"{ts.mean():,.4f} / {ts.std():,.4f}"),
            _kv("min / max", f"{ts.min():,.4f} / {ts.max():,.4f}"),
        ])
        note = html.Div("Engine-computed or raw-cache series — the full quality "
                        "audit applies to signals; see Methodology for how this "
                        "series is constructed.",
                        style={"fontSize": "0.72rem", "color": "var(--muted-color)",
                               "marginTop": "10px"})
        return head + [stats, note]

    # Full Data-Explorer treatment for signals
    sid = s["key"]
    try:
        stats = compute_signal_stats(sid)
    except Exception:
        stats = {}
    idx_row = next((r for r in wd.build_search_index()
                    if r["source"] == "signal" and r["key"] == sid), {})
    meta_block = html.Div([
        _kv("provider", idx_row.get("provider", "—")),
        _kv("force", idx_row.get("group", "—")),
        _kv("units", idx_row.get("units", "—")),
        _kv("span", f"{idx_row.get('first', '?')} → {idx_row.get('last', '?')}"),
        *[_kv(k.replace("_", " "), f"{v:,.4f}" if isinstance(v, float) else str(v))
          for k, v in (stats or {}).items() if v is not None][:6],
    ])

    detail = load_signal_detail(sid, limit=400)
    obs_cols = [c for c in ("as_of", "value", "zscore", "is_stale") if c in detail.columns]
    obs_tbl = dash_table.DataTable(
        data=detail[obs_cols].sort_values("as_of", ascending=False)
        .assign(as_of=lambda d: d["as_of"].astype(str).str[:10]).to_dict("records"),
        columns=[{"name": c, "id": c} for c in obs_cols],
        page_size=12, export_format="csv",
        style_table={"overflowX": "auto"},
        style_cell={"backgroundColor": "transparent", "color": "var(--font-color)",
                    "fontSize": "0.72rem", "fontFamily": "monospace",
                    "border": "1px solid var(--border-color)", "padding": "3px 8px"},
        style_header={"fontWeight": "700", "backgroundColor": "var(--card-bg)"},
    )

    gaps = detect_gaps(sid)
    gaps_block = (html.Div("No gaps beyond 2× the expected release cycle. ✓",
                           style={"fontSize": "0.76rem", "color": "#5CBA8A"})
                  if gaps.empty else dash_table.DataTable(
        data=gaps.astype(str).to_dict("records"),
        columns=[{"name": c, "id": c} for c in gaps.columns],
        page_size=6,
        style_cell={"backgroundColor": "transparent", "color": "var(--font-color)",
                    "fontSize": "0.7rem", "border": "1px solid var(--border-color)"},
        style_header={"fontWeight": "700", "backgroundColor": "var(--card-bg)"}))

    rvp_block = html.Div("Raw-cache comparison not available for this signal.",
                         style={"fontSize": "0.74rem", "color": "var(--muted-color)"})
    try:
        con_src = None
        import duckdb as _duck
        con = _duck.connect(str(wd.DB_PATH), read_only=True)
        try:
            row = con.execute("SELECT any_value(source) FROM signals WHERE id = ?",
                              [sid]).fetchone()
            con_src = row[0] if row else None
        finally:
            con.close()
        if con_src:
            rvp = compare_raw_vs_processed(sid, con_src, n_recent=24)
            if not rvp.empty and rvp["raw_value"].notna().any():
                rvp_block = dash_table.DataTable(
                    data=rvp.assign(
                        as_of=lambda d: d["as_of"].astype(str).str[:10]).round(4)
                    .to_dict("records"),
                    columns=[{"name": c, "id": c} for c in rvp.columns],
                    page_size=8,
                    style_cell={"backgroundColor": "transparent",
                                "color": "var(--font-color)", "fontSize": "0.7rem",
                                "fontFamily": "monospace",
                                "border": "1px solid var(--border-color)"},
                    style_header={"fontWeight": "700",
                                  "backgroundColor": "var(--card-bg)"},
                    style_data_conditional=[{
                        "if": {"filter_query": "{pct_delta} > 5 || {pct_delta} < -5"},
                        "color": "#E8734C"}])
    except Exception as exc:
        logger.warning("raw-vs-processed failed for %s: %s", sid, exc)

    return head + [
        meta_block,
        dbc.Tabs([
            dbc.Tab(html.Div(obs_tbl, style={"paddingTop": "8px"}),
                    label="Observations", tab_style={"fontSize": "0.78rem"}),
            dbc.Tab(html.Div(gaps_block, style={"paddingTop": "8px"}),
                    label="Quality & Gaps", tab_style={"fontSize": "0.78rem"}),
            dbc.Tab(html.Div(rvp_block, style={"paddingTop": "8px"}),
                    label="Raw vs Processed", tab_style={"fontSize": "0.78rem"}),
        ], style={"marginTop": "10px"}),
    ]


def _kv(k: str, v: str) -> html.Div:
    return html.Div([
        html.Span(k, style={"color": "var(--muted-color)", "fontSize": "0.72rem",
                            "display": "inline-block", "width": "125px"}),
        html.Span(v, style={"fontSize": "0.76rem", "fontFamily": "monospace"}),
    ], style={"padding": "1px 0"})


# ── "/" hotkey (clientside, registered by charting.py at import) ─────────────

HOTKEY_JS = """
function(trigger) {
    if (window._wbHotkeyBound) return window.dash_clientside.no_update;
    window._wbHotkeyBound = true;
    document.addEventListener('keydown', function(e) {
        if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
            var el = document.getElementById('wb-search');
            if (el) { e.preventDefault(); el.focus(); }
        }
        if (e.key === 'Escape') {
            var res = document.getElementById('wb-search-results');
            if (res) res.innerHTML = '';
        }
    });
    return window.dash_clientside.no_update;
}
"""

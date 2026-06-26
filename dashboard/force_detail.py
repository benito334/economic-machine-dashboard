"""Force detail sub-pages — /signals/{force}.

Layout per page:
  1. Banner strip  — Force Z, Momentum, Active signals, In agreement, Threshold, Lookback
  2. Collapsible 8-column signal table  (same as /signals, one force only)
  3. Stacked time-series chart  — composite Z on top, then per-signal dual panels
     (raw value + Z-score), shared spike hover across all subplots.

Routes: /signals/growth  /signals/inflation  /signals/rate  /signals/credit  /signals/volatility
"""
from __future__ import annotations

import json
import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html, no_update

from dashboard.charting_data import (
    load_composite_component_status,
    load_composite_history,
    load_multi_signal_history,
    load_signal_units,
)
from dashboard.signals_page import (
    _GROWTH_COLOR,
    _INFLATION_COLOR,
    _RATE_COLOR,
    _CREDIT_COLOR,
    _VOLATILITY_COLOR,
    _RATE_EXCLUDE,
    _build_section,
    _composite_rows,
    _comp_arrow,
    _direction_fraction,
    _majority_arrow,
    _mean_z,
    _momentum_score_color,
    _semantic_z_color,
    _signal_rows,
    _vix_df,
)
from dashboard.themes import figure_layout
from indicators.composites import load_composites_config

# ── Force config ───────────────────────────────────────────────────────────────

_FORCES = ["growth", "inflation", "rate", "credit", "volatility"]

_FORCE_CFG: dict[str, dict] = {
    "growth":    {"label": "Growth",       "color": _GROWTH_COLOR,     "score_col": "growth_score",    "mom_col": "growth_momentum",    "thresh_key": "gz", "is_composite": True},
    "inflation": {"label": "Inflation",    "color": _INFLATION_COLOR,  "score_col": "inflation_score", "mom_col": "inflation_momentum", "thresh_key": "iz", "is_composite": True},
    "rate":      {"label": "Interest Rate","color": _RATE_COLOR,       "score_col": "rate_score",      "mom_col": "rate_momentum",      "thresh_key": None, "is_composite": True},
    "credit":    {"label": "Credit",       "color": _CREDIT_COLOR,     "score_col": "credit_score",    "mom_col": "credit_momentum",    "thresh_key": None, "is_composite": True},
    "volatility":{"label": "Volatility",   "color": _VOLATILITY_COLOR, "score_col": None,              "mom_col": None,                 "thresh_key": None, "is_composite": False},
}

_GROWTH_WINDOW_COL   = {36: "36m", 48: "48m", 60: "60m"}
_INFLATION_WINDOW_COL = {60: "60m", 90: "90m", 120: "120m"}


# ── Layout factory ─────────────────────────────────────────────────────────────

def get_layout(force: str) -> html.Div:
    fc = _FORCE_CFG[force]
    return html.Div(
        [
            html.Div(id=f"fd-banner-{force}"),
            html.Div(id=f"fd-table-{force}", style={"marginTop": "10px"}),
            html.Div(
                dcc.Graph(
                    id=f"fd-chart-{force}",
                    config={"displayModeBar": False},
                    style={"width": "100%"},
                ),
                style={"marginTop": "18px"},
            ),
            dcc.Store(id=f"fd-hover-init-{force}", data=0),
        ],
        className="pe-2",
        style={"maxWidth": "1600px", "margin": "0 auto"},
    )


# ── Banner builder ─────────────────────────────────────────────────────────────

def _chip(label: str, value: str, color: str = "var(--font-color)") -> html.Div:
    return html.Div(
        [
            html.Span(label, style={
                "fontSize": "0.60rem", "textTransform": "uppercase",
                "letterSpacing": "0.08em", "color": "var(--muted-color)",
                "display": "block", "marginBottom": "2px",
            }),
            html.Span(value, style={
                "fontSize": "0.92rem", "fontFamily": "monospace",
                "fontWeight": "700", "color": color,
            }),
        ],
        style={
            "background": "rgba(0,0,0,0.20)", "border": "1px solid var(--border-color)",
            "borderRadius": "5px", "padding": "6px 14px", "textAlign": "center",
            "minWidth": "90px",
        },
    )


def _build_banner(
    force: str,
    comp_z: Optional[float],
    momentum: Optional[float],
    n_active: int,
    n_total: int,
    n_agreement: int,
    thresholds: dict,
    lookback_label: str,
) -> html.Div:
    fc = _FORCE_CFG[force]
    color = fc["color"]
    thresh_key = fc["thresh_key"]

    z_str   = f"{comp_z:+.3f}" if comp_z is not None and not math.isnan(comp_z) else "—"
    z_color = _semantic_z_color(comp_z, force) if comp_z is not None else "#888"
    mom_str = f"{momentum:.0%}" if momentum is not None else "—"
    mom_color = _momentum_score_color(momentum, force)

    if thresh_key:
        thresh_val = float((thresholds or {}).get(thresh_key, 0.5))
        thresh_str = f"±{thresh_val:.2f}"
    else:
        thresh_str = "N/A"

    title = html.Div(
        fc["label"].upper() + " FORCE",
        style={
            "color": color, "fontWeight": "800", "fontSize": "0.78rem",
            "letterSpacing": "0.10em", "textTransform": "uppercase",
            "marginBottom": "10px",
        },
    )

    chips = html.Div(
        [
            _chip("Force Z",      z_str,                       z_color),
            _chip("Momentum",     mom_str,                     mom_color),
            _chip("Active",       f"{n_active}/{n_total}",     "var(--font-color)"),
            _chip("In Agreement", f"{n_agreement}/{n_active}" if n_active else "—", "var(--font-color)"),
            _chip("Threshold",    thresh_str,                  "#E8A317"),
            _chip("Lookback",     lookback_label,              "var(--muted-color)"),
        ],
        style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
    )

    return html.Div(
        [title, chips],
        style={
            "background": "var(--card-bg)", "border": "1px solid var(--border-color)",
            "borderRadius": "6px", "padding": "12px 16px",
        },
    )


# ── Chart builder ──────────────────────────────────────────────────────────────

_COMPOSITE_H = 160   # px — composite Z panel
_MOMENTUM_H  = 110   # px — composite momentum panel
_SIGNAL_PH   = 100   # px — each raw/Z sub-panel

# Per-force fill colours for the composite Z area (matches force brand colour)
_FORCE_FILL: dict[str, str] = {
    "growth":    "rgba(92, 186, 138, 0.15)",
    "inflation": "rgba(232, 115, 76, 0.15)",
    "rate":      "rgba(76, 155, 232, 0.15)",
    "credit":    "rgba(176, 127, 212, 0.15)",
    "volatility":"rgba(244, 200, 66, 0.12)",
}
_MOM_COLOR = "#E8A317"          # amber — distinct from all force colours
_MOM_FILL  = "rgba(232, 163, 23, 0.12)"
_TH_LINE   = dict(color="rgba(232, 163, 23, 0.40)", width=1, dash="dash")


def _build_force_chart(
    force: str,
    country: str,
    signal_ids: list[str],
    labels: dict[str, str],
    units_map: dict[str, str],
    comp_hist: pd.DataFrame,
    raw_wide: pd.DataFrame,
    z_wide: pd.DataFrame,
    theme_name: str = "carbon",
    score_col: Optional[str] = None,
    thresholds: Optional[dict] = None,
) -> go.Figure:
    fc = _FORCE_CFG[force]
    color = fc["color"]
    score_col = score_col or fc["score_col"]
    mom_col   = fc["mom_col"]
    thresholds = thresholds or {}

    has_composite = bool(score_col and not comp_hist.empty and score_col in comp_hist.columns)
    has_momentum  = bool(
        has_composite and mom_col
        and not comp_hist.empty and mom_col in comp_hist.columns
        and not comp_hist[mom_col].dropna().empty
    )

    n_signals       = len(signal_ids)
    momentum_offset = 1 if has_momentum else 0
    n_rows          = 1 + momentum_offset + n_signals * 2

    composite_h = _COMPOSITE_H
    momentum_h  = _MOMENTUM_H if has_momentum else 0
    signal_ph   = _SIGNAL_PH
    total_h     = composite_h + momentum_h + n_signals * 2 * signal_ph

    row_heights = [composite_h / total_h]
    if has_momentum:
        row_heights.append(momentum_h / total_h)
    row_heights += [signal_ph / total_h] * (n_signals * 2)

    subplot_titles: list[str] = [f"{fc['label']} Composite Z-score"]
    if has_momentum:
        subplot_titles.append(f"{fc['label']} Momentum (signal agreement %)")
    for sid in signal_ids:
        lbl = labels.get(sid, sid.split(".")[-1].replace("_", " ").title())
        subplot_titles += [lbl, f"{lbl}  ·  Z-score"]

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.012,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )

    # ── Normalize signal dates to month-start to align with monthly composites ─
    # Only resample when a composite row exists; skip for volatility (daily VIX).
    if has_composite:
        if not raw_wide.empty:
            raw_wide = raw_wide.copy()
            raw_wide.index = pd.to_datetime(raw_wide.index).to_period("M").to_timestamp()
            raw_wide = raw_wide.groupby(raw_wide.index).last()
        if not z_wide.empty:
            z_wide = z_wide.copy()
            z_wide.index = pd.to_datetime(z_wide.index).to_period("M").to_timestamp()
            z_wide = z_wide.groupby(z_wide.index).last()

    # ── Row 1: Composite Z — filled area + threshold lines ────────────────────
    if has_composite:
        ser = comp_hist[["as_of", score_col]].dropna().copy()
        ser["as_of"] = pd.to_datetime(ser["as_of"]).dt.to_period("M").dt.to_timestamp()
        fig.add_trace(go.Scatter(
            x=ser["as_of"], y=ser[score_col],
            name="Composite Z",
            line=dict(color=color, width=1.5),
            fill="tozeroy",
            fillcolor=_FORCE_FILL.get(force, "rgba(128,128,128,0.15)"),
            hovertemplate="%{x|%b %Y}: %{y:.3f}<extra></extra>",
            showlegend=False,
        ), row=1, col=1)
        fig.add_hline(y=0, line_dash="dot", line_color="#555", row=1, col=1)
        thresh_key = fc["thresh_key"]
        if thresh_key:
            tv = float(thresholds.get(thresh_key, 0.5))
            fig.add_hline(y= tv, line=_TH_LINE, row=1, col=1)
            fig.add_hline(y=-tv, line=_TH_LINE, row=1, col=1)

    # ── Row 2 (optional): Composite Momentum — amber fill ─────────────────────
    if has_momentum:
        mom_ser = comp_hist[["as_of", mom_col]].dropna().copy()
        mom_ser["as_of"] = pd.to_datetime(mom_ser["as_of"]).dt.to_period("M").dt.to_timestamp()
        fig.add_trace(go.Scatter(
            x=mom_ser["as_of"], y=mom_ser[mom_col],
            name="Momentum",
            line=dict(color=_MOM_COLOR, width=1.5),
            fill="tozeroy",
            fillcolor=_MOM_FILL,
            hovertemplate="%{x|%b %Y}: %{y:.0%}<extra></extra>",
            showlegend=False,
        ), row=2, col=1)
        fig.add_hline(y=0.5, line_dash="dot", line_color="#555", row=2, col=1)
        fig.update_yaxes(tickformat=".0%", range=[0, 1],
                         title_text="%", title_font_size=9, row=2, col=1)

    # ── Rows 3+ : per-signal dual panels ──────────────────────────────────────
    for i, sid in enumerate(signal_ids):
        row_raw = 2 + momentum_offset + i * 2
        row_z   = 3 + momentum_offset + i * 2
        lbl     = labels.get(sid, sid.split(".")[-1].replace("_", " ").title())
        units   = units_map.get(sid, "value")

        if sid in raw_wide.columns:
            raw_s = raw_wide[sid].dropna()
            if not raw_s.empty:
                fig.add_trace(go.Scatter(
                    x=raw_s.index, y=raw_s.values,
                    name=lbl,
                    line=dict(color=color, width=1.4),
                    hovertemplate=f"%{{x|%b %Y}}: %{{y:.4g}} ({units})<extra></extra>",
                    showlegend=False,
                ), row=row_raw, col=1)

        if sid in z_wide.columns:
            z_s = z_wide[sid].dropna()
            if not z_s.empty:
                fig.add_trace(go.Scatter(
                    x=z_s.index, y=z_s.values,
                    name=f"{lbl} Z",
                    mode="lines",
                    line=dict(color=color, width=1.2),
                    hovertemplate=f"%{{x|%b %Y}}  Z=%{{y:+.2f}}<extra></extra>",
                    showlegend=False,
                ), row=row_z, col=1)
                fig.add_hline(y=0, line_dash="dot",
                              line_color="rgba(130,130,130,0.35)", line_width=1,
                              row=row_z, col=1)

        fig.update_yaxes(title_text=units, title_font_size=9, row=row_raw, col=1)
        fig.update_yaxes(title_text="Z", title_font_size=9, zeroline=False,
                         row=row_z, col=1)

    # ── Global layout ─────────────────────────────────────────────────────────
    layout = figure_layout(theme_name)
    layout.update({
        "height":        max(400, total_h),
        "margin":        {"l": 55, "r": 20, "t": 28, "b": 30},
        "hovermode":     "x",
        "hoversubplots": "axis",
        "showlegend":    False,
        "uirevision":    f"force-{force}-{country}",
    })
    fig.update_yaxes(title_text="Z", title_font_size=9, zeroline=False, row=1, col=1)
    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikedash="dot", spikethickness=1, spikecolor="rgba(180,180,180,0.6)",
    )
    for ann in fig.layout.annotations:
        ann.update(font=dict(size=9), xanchor="left", x=0.01)

    fig.update_layout(**layout)
    return fig


# ── Shared-hover clientside callback JS (parameterised by element ID) ─────────

def _hover_sync_js(element_id: str, store_id: str) -> str:
    return f"""
    function(figure) {{
        if (!figure) return dash_clientside.no_update;
        setTimeout(function() {{
            var wrapper = document.getElementById('{element_id}');
            var gd = wrapper && wrapper.querySelector('.js-plotly-plot');
            if (!gd || typeof gd.on !== 'function' || gd._fdHoverSyncBound) return;

            gd._fdHoverSyncBound = true;
            function drawLine(rawX) {{
                var layout = gd._fullLayout;
                var hoverLayer = gd.querySelector('.hoverlayer');
                var xAxis = layout && layout.xaxis;
                var yAxes = layout && layout._subplots ? layout._subplots.yaxis : null;
                if (!hoverLayer || !xAxis || !yAxes || !yAxes.length) return;

                var xPixel = xAxis._offset + xAxis.d2p(rawX);
                var top = Infinity, bottom = -Infinity;
                yAxes.forEach(function(axisId) {{
                    var key = axisId === 'y' ? 'yaxis' : 'yaxis' + axisId.slice(1);
                    var axis = layout[key];
                    if (!axis) return;
                    top = Math.min(top, axis._offset);
                    bottom = Math.max(bottom, axis._offset + axis._length);
                }});
                if (!Number.isFinite(xPixel) || !Number.isFinite(top) || !Number.isFinite(bottom)) return;

                var line = hoverLayer.querySelector('.fd-shared-hover-line');
                if (!line) {{
                    line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('class', 'fd-shared-hover-line');
                    line.setAttribute('stroke', 'rgba(210,215,225,0.72)');
                    line.setAttribute('stroke-width', '1');
                    line.setAttribute('stroke-dasharray', '4,3');
                    line.setAttribute('pointer-events', 'none');
                    hoverLayer.insertBefore(line, hoverLayer.firstChild);
                }}
                line.setAttribute('x1', xPixel); line.setAttribute('x2', xPixel);
                line.setAttribute('y1', top);     line.setAttribute('y2', bottom);
            }}

            gd.on('plotly_hover', function(eventData) {{
                if (gd._fdSyncing || !eventData || !eventData.points || !eventData.points.length) return;
                var rawX = eventData.points[0].x;
                var xVal = rawX instanceof Date ? rawX.getTime() : Date.parse(rawX);
                var subplots = gd._fullLayout && gd._fullLayout._subplots
                    ? gd._fullLayout._subplots.cartesian : null;
                if (!Number.isFinite(xVal) || !subplots || !subplots.length) return;
                gd._fdSyncing = true;
                try {{
                    Plotly.Fx.hover(gd, {{xval: xVal}}, subplots);
                    requestAnimationFrame(function() {{ drawLine(rawX); }});
                }} finally {{
                    setTimeout(function() {{ gd._fdSyncing = false; }}, 0);
                }}
            }});
            gd.on('plotly_unhover', function() {{
                var line = gd.querySelector('.fd-shared-hover-line');
                if (line) line.remove();
            }});
        }}, 0);
        return Date.now();
    }}
    """


# ── Callback registration ──────────────────────────────────────────────────────

def register_callbacks(app, force: str) -> None:  # noqa: C901
    """Register main content + hover-sync callbacks for one force page."""

    route = f"/signals/{force}"
    fc    = _FORCE_CFG[force]

    @app.callback(
        [
            Output(f"fd-banner-{force}", "children"),
            Output(f"fd-table-{force}",  "children"),
            Output(f"fd-chart-{force}",  "figure"),
        ],
        [
            Input("country-store",          "data"),
            Input("page-trigger",           "data"),
            Input("zscore-window-store",    "data"),
            Input("inflation-window-store", "data"),
            Input("regime-threshold-store", "data"),
            Input("theme-store",            "data"),
        ],
        prevent_initial_call=False,
    )
    def _render(country_data, page_trigger, zscore_window, inflation_window,
                thresholds, theme):
        if (page_trigger or {}).get("page") != route:
            return no_update, no_update, no_update

        country      = str(country_data or "US").upper()
        theme_name   = theme or "carbon"
        thresholds   = thresholds or {}
        zscore_window    = int(zscore_window    or 0)
        inflation_window = int(inflation_window or 0)

        # ── Z-score column selection ──────────────────────────────────────────
        g_sfx = _GROWTH_WINDOW_COL.get(zscore_window)
        i_sfx = _INFLATION_WINDOW_COL.get(inflation_window)
        g_zcol = f"zscore_{g_sfx}" if g_sfx else "zscore"
        i_zcol = f"zscore_{i_sfx}" if i_sfx else "zscore"
        lookback_label = (
            f"{g_sfx}" if force == "growth"    and g_sfx else
            f"{i_sfx}" if force == "inflation" and i_sfx else "Full"
        )

        # ── Composite history ─────────────────────────────────────────────────
        comp_hist = load_composite_history(country=country)

        # ── Composite component status (for table + banner stats) ─────────────
        comp_df = load_composite_component_status(
            country, g_zscore_col=g_zcol, i_zscore_col=i_zcol,
        )

        # ── Latest composite row for banner values ────────────────────────────
        comp_z:   Optional[float] = None
        momentum: Optional[float] = None
        audit_by_signal: dict = {}

        if not comp_hist.empty:
            row = comp_hist.iloc[-1]
            score_col = fc["score_col"]
            mom_col   = fc["mom_col"]

            if score_col:
                # Use rolling column for growth/inflation if selected
                if force == "growth" and g_sfx:
                    rc = f"growth_score_{g_sfx}"
                    comp_z = float(row[rc]) if rc in comp_hist.columns and pd.notna(row.get(rc)) else None
                elif force == "inflation" and i_sfx:
                    rc = f"inflation_score_{i_sfx}"
                    comp_z = float(row[rc]) if rc in comp_hist.columns and pd.notna(row.get(rc)) else None
                if comp_z is None and score_col in comp_hist.columns:
                    comp_z = float(row[score_col]) if pd.notna(row.get(score_col)) else None

            if mom_col and mom_col in comp_hist.columns and pd.notna(row.get(mom_col)):
                momentum = float(row[mom_col])

            wa_raw = row.get("weight_audit")
            if wa_raw:
                raw = json.loads(wa_raw) if isinstance(wa_raw, str) else wa_raw
                for force_dict in raw.values():
                    if isinstance(force_dict, dict):
                        audit_by_signal.update(force_dict)

        # ── Volatility special case ───────────────────────────────────────────
        if force == "volatility":
            vol_df   = _vix_df(country)
            comp_z   = _mean_z(vol_df)
            momentum = _direction_fraction(vol_df)

            n_total  = len(vol_df)
            n_active = sum(1 for _, r in vol_df.iterrows() if pd.notna(r.get("zscore")))
            n_agree  = 0  # VIX: rising = bad, no clear agreement metric for 1 signal

            thresh_z = float(thresholds.get("gz", 0.5))
            v_rows, v_active = _signal_rows(vol_df, _VOLATILITY_COLOR)
            table_section = _build_section(
                "Volatility", _VOLATILITY_COLOR, "volatility",
                comp_z, momentum,
                _majority_arrow(vol_df["direction"].dropna().tolist() if not vol_df.empty else []),
                v_active, n_total, v_rows,
            )
            banner = _build_banner(force, comp_z, momentum, n_active, n_total,
                                   n_agree, thresholds, lookback_label)

            # Chart: VIX raw + Z, no composite row from DB
            vix_ids = ["us.volatility.vix"]
            raw_wide_v = pd.DataFrame()
            z_wide_v   = pd.DataFrame()
            try:
                # VIX raw data from regime_classifier helper
                from indicators.regime_classifier import _load_vix
                vix_raw = _load_vix()
                if vix_raw is not None and not vix_raw.empty:
                    raw_wide_v = vix_raw.to_frame(name="us.volatility.vix")
                    window = 120
                    roll = vix_raw.rolling(window, min_periods=24)
                    z_series = (vix_raw - roll.mean()) / roll.std()
                    z_wide_v = z_series.to_frame(name="us.volatility.vix")
            except Exception:
                pass

            vix_labels   = {"us.volatility.vix": "VIX"}
            vix_units    = {"us.volatility.vix": "index level"}
            empty_hist   = pd.DataFrame(columns=["as_of"])
            chart = _build_force_chart(
                force, country, vix_ids, vix_labels, vix_units,
                empty_hist, raw_wide_v, z_wide_v, theme_name,
                thresholds=thresholds,
            )
            return banner, table_section, chart

        # ── Composite forces (growth, inflation, rate, credit) ────────────────
        comp_key = {"growth": "growth_score", "inflation": "inflation_score",
                    "rate": "rate_score", "credit": "credit_score"}[force]
        cfg = load_composites_config(country)
        country_prefix = country.lower()
        indicators = cfg.get(comp_key, {}).get("indicators", [])
        signal_ids = [f"{country_prefix}.{ind['id']}" for ind in indicators]

        # Exclude country-specific rate signals
        if force == "rate":
            exc = _RATE_EXCLUDE.get(country, set())
            signal_ids = [s for s in signal_ids
                          if s.split(".")[-1] not in exc]

        # ── Banner stats ──────────────────────────────────────────────────────
        force_df = comp_df[comp_df["composite"] == force]
        n_total  = len(force_df)
        n_active = 0
        n_agree  = 0
        for _, sr in force_df.iterrows():
            z_val = sr.get("zscore")
            if z_val is None or (isinstance(z_val, float) and math.isnan(z_val)):
                continue
            n_active += 1
            direction = str(sr.get("direction") or "")
            invert    = bool(sr.get("invert", False))
            positive_dir = "falling" if invert else "rising"
            if comp_z is not None:
                if comp_z >= 0 and direction == positive_dir:
                    n_agree += 1
                elif comp_z < 0 and direction != positive_dir and direction:
                    n_agree += 1

        if momentum is None:
            momentum = float(force_df["direction"].eq("rising").sum()) / max(1, n_active)

        # ── Table ─────────────────────────────────────────────────────────────
        thresh_z = float(thresholds.get("gz", 0.5))
        rows, active_cnt = _composite_rows(comp_df, force, fc["color"],
                                           audit_by_signal, thresh=thresh_z)
        table_section = _build_section(
            fc["label"], fc["color"], force,
            comp_z, momentum, _comp_arrow(comp_df, force),
            active_cnt, n_total, rows,
        )

        # ── Chart data ────────────────────────────────────────────────────────
        labels_map   = {r["signal_id"]: r["label"]
                        for _, r in comp_df[comp_df["composite"] == force].iterrows()}
        units_map    = load_signal_units(signal_ids)
        raw_wide_df  = load_multi_signal_history(signal_ids, value_col="value")
        # Use the rolling Z column matching the selected window so per-signal
        # Z panels update when the lookback slider changes.
        z_val_col = g_zcol if force == "growth" else i_zcol if force == "inflation" else "zscore"
        z_wide_df    = load_multi_signal_history(signal_ids, value_col=z_val_col)

        # Use the same rolling-window column the banner uses, so chart matches
        chart_score_col = fc["score_col"]
        if force == "growth" and g_sfx:
            rc = f"growth_score_{g_sfx}"
            if not comp_hist.empty and rc in comp_hist.columns:
                chart_score_col = rc
        elif force == "inflation" and i_sfx:
            rc = f"inflation_score_{i_sfx}"
            if not comp_hist.empty and rc in comp_hist.columns:
                chart_score_col = rc

        chart = _build_force_chart(
            force, country, signal_ids, labels_map, units_map,
            comp_hist, raw_wide_df, z_wide_df, theme_name,
            score_col=chart_score_col, thresholds=thresholds,
        )

        banner = _build_banner(force, comp_z, momentum, n_active, n_total,
                               n_agree, thresholds, lookback_label)
        return banner, table_section, chart

    # ── Shared spike hover (mirrors Regime History clientside callback) ────────
    app.clientside_callback(
        _hover_sync_js(f"fd-chart-{force}", f"fd-hover-init-{force}"),
        Output(f"fd-hover-init-{force}", "data"),
        Input(f"fd-chart-{force}", "figure"),
        prevent_initial_call=True,
    )

"""Force detail sub-pages — /signals/{force}.

Layout per page:
  1. Banner strip  — Force Z, Momentum, Active signals, In agreement, Threshold, Lookback
  2. Collapsible 8-column signal table  (same as /signals, one force only)
  3. Chart cards — the shared Monitor-card style (`dashboard.shared_components.
     _chart_card`/`_section`, 2026-10 IA cleanup Phase 4): a Composite Z card
     (+ Momentum card where the force has one), then one raw-value + one
     Z-score card per basket signal. Replaces the previous single stacked
     make_subplots mega-chart with per-card hover, consistent with every
     other chart surface on the dashboard.

Routes: /signals/growth  /signals/inflation  /signals/rate  /signals/credit  /signals/volatility
"""
from __future__ import annotations

import json
import math
from typing import Optional

import pandas as pd

from dash import Input, Output, html, no_update

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
    _PRODUCTIVITY_COLOR,
    _RATE_EXCLUDE,
    _build_section,
    _composite_rows,
    _comp_arrow,
    _momentum_score_color,
    _semantic_z_color,
)
from dashboard.shared_components import _chart_card, _fmt_value, _section
from indicators.composites import load_composites_config

# ── Force config ───────────────────────────────────────────────────────────────

_FORCES = ["growth", "inflation", "rate", "credit", "volatility", "productivity"]

_FORCE_CFG: dict[str, dict] = {
    "growth":    {"label": "Growth",       "color": _GROWTH_COLOR,     "score_col": "growth_score",    "mom_col": "growth_momentum",    "thresh_key": "gz", "is_composite": True},
    "inflation": {"label": "Inflation",    "color": _INFLATION_COLOR,  "score_col": "inflation_score", "mom_col": "inflation_momentum", "thresh_key": "iz", "is_composite": True},
    "rate":      {"label": "Interest Rate","color": _RATE_COLOR,       "score_col": "rate_score",      "mom_col": "rate_momentum",      "thresh_key": None, "is_composite": True},
    "credit":    {"label": "Credit",       "color": _CREDIT_COLOR,     "score_col": "credit_score",    "mom_col": "credit_momentum",    "thresh_key": None, "is_composite": True},
    "volatility":{"label": "Volatility",   "color": _VOLATILITY_COLOR, "score_col": "volatility_score", "mom_col": "volatility_momentum", "thresh_key": None, "is_composite": True},
    "productivity":{"label": "Productivity Trend", "color": _PRODUCTIVITY_COLOR, "score_col": "productivity_score", "mom_col": "productivity_momentum", "thresh_key": None, "is_composite": True},
}

_GROWTH_WINDOW_COL   = {36: "36m", 48: "48m", 60: "60m"}
_INFLATION_WINDOW_COL = {60: "60m", 90: "90m", 120: "120m"}


# ── Layout factory ─────────────────────────────────────────────────────────────

def get_layout(force: str) -> html.Div:
    return html.Div(
        [
            html.Div(id=f"fd-banner-{force}"),
            html.Div(id=f"fd-table-{force}", style={"marginTop": "10px"}),
            html.Div(id=f"fd-chart-{force}", style={"marginTop": "6px"}),
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


# Ray Dalio consult, 2026-08-19: the diagnostic pairing he described for
# reading the productivity trend against the cyclical Growth Z-score — a
# labeled interpretation layer on top of the overlay chart that already
# exists (force_detail.py:278). Thresholds reuse the same `gz` regime
# threshold the Growth chip itself uses, so "strong" here means the same
# thing it means everywhere else on the dashboard.
def _productivity_divergence(prod_z: Optional[float], growth_z: Optional[float],
                             thresh_gz: float) -> Optional[dict]:
    if prod_z is None or growth_z is None or math.isnan(prod_z) or math.isnan(growth_z):
        return None
    if prod_z > 0 and growth_z <= thresh_gz:
        return {
            "label": "Early-stage competitive advantage",
            "detail": ("Productivity trend rising while cyclical growth is soft/neutral — "
                      "efficiency gains ahead of demand, a bullish long-term-competitiveness "
                      "signal (Ray Dalio consult, 2026-08-19)."),
            "color": "#3FBFB0",
        }
    if prod_z < 0 and growth_z > thresh_gz:
        return {
            "label": "Unsustainable-expansion watch",
            "detail": ("Cyclical growth is strong while the productivity trend is falling — "
                      "the expansion may be leaning on diminishing returns rather than "
                      "capacity gains (Ray Dalio consult, 2026-08-19)."),
            "color": "#E8A317",
        }
    return None


def _build_banner(
    force: str,
    comp_z: Optional[float],
    momentum: Optional[float],
    n_active: int,
    n_total: int,
    n_agreement: int,
    thresholds: dict,
    lookback_label: str,
    divergence: Optional[dict] = None,
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

    children = [title, chips]
    if divergence:
        children.append(html.Div(
            [html.Span(divergence["label"], style={"fontWeight": "700"}),
             html.Span(" — " + divergence["detail"], style={"fontWeight": "400"})],
            style={
                "color": divergence["color"], "fontSize": "0.72rem", "marginTop": "10px",
                "borderLeft": f"2px solid {divergence['color']}", "paddingLeft": "8px",
                "background": f"{divergence['color']}14", "borderRadius": "0 4px 4px 0",
                "padding": "5px 8px",
            },
        ))

    return html.Div(
        children,
        style={
            "background": "var(--card-bg)", "border": "1px solid var(--border-color)",
            "borderRadius": "6px", "padding": "12px 16px",
        },
    )


# ── Chart builder — shared Monitor-card style ───────────────────────────────

def _series_df(wide: pd.DataFrame, sid: str) -> pd.DataFrame:
    """One signal's column from a load_multi_signal_history() wide frame,
    reshaped to the {"as_of", "value"} long form _chart_card expects."""
    if wide.empty or sid not in wide.columns:
        return pd.DataFrame(columns=["as_of", "value"])
    s = wide[sid].dropna()
    return pd.DataFrame({"as_of": s.index, "value": s.values})


def _build_force_cards(
    force: str,
    signal_ids: list[str],
    labels: dict[str, str],
    units_map: dict[str, str],
    comp_hist: pd.DataFrame,
    raw_wide: pd.DataFrame,
    z_wide: pd.DataFrame,
    score_col: Optional[str] = None,
    thresholds: Optional[dict] = None,
) -> list[html.Div]:
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

    # Normalize signal dates to month-start to align with monthly composites —
    # daily signals like VIX/realized_vol/fed_funds take their month-end last
    # value, same convention the composite engine itself uses.
    if has_composite:
        if not raw_wide.empty:
            raw_wide = raw_wide.copy()
            raw_wide.index = pd.to_datetime(raw_wide.index).to_period("M").to_timestamp()
            raw_wide = raw_wide.groupby(raw_wide.index).last()
        if not z_wide.empty:
            z_wide = z_wide.copy()
            z_wide.index = pd.to_datetime(z_wide.index).to_period("M").to_timestamp()
            z_wide = z_wide.groupby(z_wide.index).last()

    composite_cards: list[html.Div] = []

    if has_composite:
        ser = comp_hist[["as_of", score_col]].dropna().rename(columns={score_col: "value"})
        ser = ser.copy()
        ser["as_of"] = pd.to_datetime(ser["as_of"]).dt.to_period("M").dt.to_timestamp()
        cur = float(ser["value"].iloc[-1]) if not ser.empty else None

        thresh_key = fc["thresh_key"]
        hline = hline2 = None
        hline_txt = hline2_txt = ""
        if thresh_key:
            tv = float(thresholds.get(thresh_key, 0.5))
            hline,  hline_txt  = tv,  f"+{tv:.2f}"
            hline2, hline2_txt = -tv, f"-{tv:.2f}"

        df2 = label2 = None
        color2 = _GROWTH_COLOR
        # Productivity page: overlay cyclical growth so "cyclically strong but
        # trend-decelerating" (or the reverse) is visible at a glance — Ray's
        # framing of the trend line vs. the short-term cycle (roadmap Phase B).
        if force == "productivity" and "growth_score" in comp_hist.columns:
            g = comp_hist[["as_of", "growth_score"]].dropna().rename(columns={"growth_score": "value"})
            if not g.empty:
                g = g.copy()
                g["as_of"] = pd.to_datetime(g["as_of"]).dt.to_period("M").dt.to_timestamp()
                df2, label2 = g, "Cyclical growth Z"

        composite_cards.append(_chart_card(
            f"{fc['label']} Composite Z-score", ser, cur, "z",
            f"Weighted Z-score across the {fc['label'].lower()} basket."
            + (f" Dashed lines = ±{hline:.2f} regime threshold." if hline is not None else ""),
            hline=hline, hline_txt=hline_txt, hline2=hline2, hline2_txt=hline2_txt,
            zero_line=True, color=color, fill=True,
            info="The composite score this force's chip/basket is built from.",
            df2=df2, color2=color2, label2=label2,
            fmt_override=f"{cur:+.3f}" if cur is not None else None,
            sync_hover=True,
        ))

    if has_momentum:
        mom_ser = comp_hist[["as_of", mom_col]].dropna().rename(columns={mom_col: "value"})
        mom_ser = mom_ser.copy()
        mom_ser["as_of"] = pd.to_datetime(mom_ser["as_of"]).dt.to_period("M").dt.to_timestamp()
        mcur = float(mom_ser["value"].iloc[-1]) if not mom_ser.empty else None
        composite_cards.append(_chart_card(
            f"{fc['label']} Momentum", mom_ser, mcur, "pct",
            "Share of basket signals moving in their 'good' direction. "
            "50% = no net agreement either way.",
            hline=0.5, hline_txt="50%",
            color="#E8A317",
            info="Momentum agreement fraction feeding this force's composite.",
            fmt_override=f"{mcur:.0%}" if mcur is not None else None,
            sync_hover=True,
        ))

    signal_cards: list[html.Div] = []
    for sid in signal_ids:
        lbl   = labels.get(sid, sid.split(".")[-1].replace("_", " ").title())
        units = units_map.get(sid, "value")

        raw_df = _series_df(raw_wide, sid)
        raw_cur = float(raw_df["value"].iloc[-1]) if not raw_df.empty else None
        signal_cards.append(_chart_card(
            lbl, raw_df, raw_cur, "", f"Units: {units}",
            color=color,
            fmt_override=_fmt_value(raw_cur, units),
            sync_hover=True,
        ))

        z_df = _series_df(z_wide, sid)
        z_cur = float(z_df["value"].iloc[-1]) if not z_df.empty else None
        signal_cards.append(_chart_card(
            f"{lbl} · Z-score", z_df, z_cur, "z", "Standardized within this basket.",
            zero_line=True, color=color,
            fmt_override=f"{z_cur:+.2f}" if z_cur is not None else None,
            sync_hover=True,
        ))

    # Composite Z/Momentum run full-width, one per row; basket signal cards
    # (raw + Z pairs) sit two per row.
    comp_cols, sig_cols = 1, 2
    sections: list[html.Div] = []
    if composite_cards:
        sections.append(_section(f"{fc['label']} composite", "", composite_cards, columns=comp_cols))
    if signal_cards:
        sections.append(_section("Basket signals", "", signal_cards, columns=sig_cols))
    return sections


# ── Callback registration ──────────────────────────────────────────────────────

# ── Shared-hover clientside callback JS (parameterised by element ID) ─────────
#
# No longer used by this module's own pages (Phase 4 IA cleanup replaced the
# single stacked multi-panel figure with independent chart cards, each with
# its own hover). Kept here and still exported: dashboard/charting.py wires
# this same JS onto the Workbench page's stacked chart ("wb-chart"), which is
# a genuinely separate multi-panel figure that still needs a synced crosshair
# across its panes — do not remove without updating that caller too.

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
    """Register main content callbacks for one force page."""

    route = f"/signals/{force}"
    fc    = _FORCE_CFG[force]

    @app.callback(
        [
            Output(f"fd-banner-{force}", "children"),
            Output(f"fd-table-{force}",  "children"),
            Output(f"fd-chart-{force}",  "children"),
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

        # ── Composite forces (growth, inflation, rate, credit, volatility) ─────
        # Volatility became a real basket composite 2026-07-05 (Ray Dalio review
        # #13) — it now uses this same generic path instead of a raw-VIX special case.
        comp_key = {"growth": "growth_score", "inflation": "inflation_score",
                    "rate": "rate_score", "credit": "credit_score",
                    "volatility": "volatility_score",
                    "productivity": "productivity_score"}[force]
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

        chart_cards = _build_force_cards(
            force, signal_ids, labels_map, units_map,
            comp_hist, raw_wide_df, z_wide_df,
            score_col=chart_score_col, thresholds=thresholds,
        )

        divergence = None
        if force == "productivity" and not comp_hist.empty and "growth_score" in comp_hist.columns:
            g_latest = comp_hist["growth_score"].dropna()
            growth_z = float(g_latest.iloc[-1]) if not g_latest.empty else None
            divergence = _productivity_divergence(comp_z, growth_z, float(thresholds.get("gz", 0.5)))

        banner = _build_banner(force, comp_z, momentum, n_active, n_total,
                               n_agree, thresholds, lookback_label, divergence)
        return banner, table_section, chart_cards

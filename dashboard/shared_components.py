"""Shared Dash component builders reused across dashboard pages.

Extracted from charting.py so that signals_page.py and future pages
can build the same force-signal table without duplicating the logic.

_chart_card/_section/_chip/_info_icon/_fmt (dashboard IA cleanup, Phase 3,
2026-10-03) were promoted here from fed_monitor.py, where they originated —
that page is still the one that defines "the standard" visually, this is
just the one place they're defined now so every page draws from it instead
of importing through fed_monitor as an indirection. fed_monitor.py,
case_study_monitor.py, market_expectations.py, and central_bank_monitor.py
all import these directly from here.
"""
from __future__ import annotations

import hashlib as _hashlib
import math as _math
from typing import Any

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from dashboard.themes import DEFAULT_THEME, figure_layout

_DIR_ARROW: dict[str, str] = {"rising": "↑", "falling": "↓", "flat": "→"}

# ── Canonical semantic palette ────────────────────────────────────────────
# The one place these five get named. Every page should import from here
# instead of retyping hex — this is what Fed Monitor's own _BLUE/_AMBER/
# _RED/_GREEN/_GREY already were; consolidated here per the 2026-10 IA/color
# audit so the three reds (#d9534f/#E5484D/#E8534C) and three greens
# (#5CBA8A/#2e9e5b/#5CB85C) that had drifted across pages stop drifting.
BLUE   = "#4C9BE8"   # rate / neutral-primary
AMBER  = "#E8A317"   # watch / flagged / amber-tier
GREEN  = "#2e9e5b"   # good / built / positive
RED    = "#d9534f"   # critical / negative
GREY   = "#8a97a8"   # muted / inactive

# Per-force accent colors — distinct from the semantic set above (a force's
# identity color isn't a "good/bad" judgment), but registered once so every
# page that needs "the Growth color" draws from the same list instead of
# redefining its own block of six constants.
FORCE_COLOR: dict[str, str] = {
    "growth":       "#5CBA8A",
    "inflation":    "#E8734C",
    "rate":         "#4C9BE8",
    "credit":       "#B07FD4",
    "volatility":   "#F4C842",
    "productivity": "#3FBFB0",
}

# ── Monitor-card primitives (promoted from fed_monitor.py, Phase 3) ───────
# The "Fed Monitor style" every Monitors-group page should use: compact
# cards, muted grid, optional fill/dual-line overlay, a small info icon.

def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "—"
    if unit == "%":
        return f"{v:.2f}%"
    if unit == "$T":
        return f"${v/1000:.2f}T"
    if unit == "$B":
        return f"${v:,.0f}B"
    if unit == "idx":
        return f"{v:,.0f}"
    return f"{v:.2f}"


def _info_icon_id(text: str, scope: str = "") -> str:
    """Deterministic component id for one info icon, derived from its own
    content (plus an optional scope — usually the owning card's title).

    Content-addressed deliberately: this used to be a module-level counter
    that never reset, so the same icon got id `mon-info-7` on one render and
    `mon-info-31` on the next. A content hash is stable across re-renders of
    the same page AND across the per-page render callbacks that build cards
    outside get_layout() (e.g. central_bank_monitor's cbm-content), which a
    counter reset at the top of get_layout() cannot cover. `scope` exists so
    two cards that happen to share identical info prose still get distinct
    ids — identical text AND identical title on one page would collide.
    """
    key = f"{scope}\x1f{text}"
    return f"mon-info-{_hashlib.sha1(key.encode()).hexdigest()[:10]}"


def _info_icon(text: str, scope: str = "") -> html.Span:
    """A small ⓘ that reveals a detailed explanation of the chart on hover."""
    if not text:
        return html.Span()
    iid = _info_icon_id(text, scope)
    return html.Span([
        html.Span("ⓘ", id=iid, style={
            "cursor": "help", "color": "var(--muted-color)", "fontSize": "0.72rem",
            "marginLeft": "5px", "opacity": "0.75", "fontWeight": "400"}),
        dbc.Tooltip(text, target=iid, placement="top"),
    ])


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """'#5CBA8A' -> 'rgba(92,186,138,0.12)'. Falls back to the color as-is if
    it isn't a plain 6-digit hex (e.g. an already-rgba string)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _chart_card(title: str, df: pd.DataFrame, cur: float | None, unit: str, read: str,
                *, hline: float | None = None, hline_txt: str = "",
                hline2: float | None = None, hline2_txt: str = "",
                zero_line: bool = False,
                color: str = BLUE, fill: bool = False, info: str = "",
                df2: "pd.DataFrame | None" = None, color2: str = RED,
                label: str | None = None, label2: str | None = None,
                fmt_override: str | None = None,
                vline_x=None, sync_hover: bool = False) -> html.Div:
    """Single-line by default. Pass df2 (+ optional label/label2) for a dual-line
    overlay card — e.g. Real Growth vs. Potential Growth, Short Rate vs. Long Rate.
    hline/hline2 draw one or two dashed reference lines (e.g. symmetric ± regime
    thresholds). fmt_override replaces the computed `_fmt(cur, unit)` header value
    with an already-formatted string — for callers whose unit vocabulary (e.g. a
    signal's native `units`, or a signed Z-score) isn't one `_fmt` knows. vline_x
    draws a single vertical dashed reference line (e.g. a "you are here" marker
    for a stepped/selected date) — distinct from hline/hline2, which are
    horizontal. sync_hover=True joins the card to the page-wide shared crosshair
    (assets/hover_sync.js): hovering one such card shows the same date on all the
    others, like the old stacked multi-panel figure did."""
    dual = df2 is not None and not df2.empty
    fig = go.Figure()
    if df is not None and not df.empty:
        fig.add_trace(go.Scatter(
            x=df["as_of"], y=df["value"], mode="lines", name=label or title,
            line=dict(color=color, width=1.7),
            fill="tozeroy" if fill else None,
            fillcolor=_hex_to_rgba(color, 0.12) if fill else None,
            hovertemplate="%{x|%b %Y}: %{y:.2f}<extra></extra>"))
    if dual:
        fig.add_trace(go.Scatter(
            x=df2["as_of"], y=df2["value"], mode="lines", name=label2 or "secondary",
            line=dict(color=color2, width=1.7),
            hovertemplate="%{x|%b %Y}: %{y:.2f}<extra></extra>"))
    if zero_line:
        fig.add_hline(y=0, line=dict(color=GREY, width=1))
    if hline is not None:
        fig.add_hline(y=hline, line=dict(color=AMBER, dash="dash", width=1),
                      annotation_text=hline_txt, annotation_position="top left",
                      annotation_font=dict(size=9, color=AMBER))
    if hline2 is not None:
        fig.add_hline(y=hline2, line=dict(color=AMBER, dash="dash", width=1),
                      annotation_text=hline2_txt, annotation_position="bottom left",
                      annotation_font=dict(size=9, color=AMBER))
    if vline_x is not None:
        fig.add_vline(x=vline_x, line=dict(color="rgba(255,255,255,0.35)", dash="dot", width=1.5))
    lay = figure_layout(DEFAULT_THEME)
    lay.update(height=180, margin=dict(l=6, r=8, t=6, b=18),
               xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"))
    if sync_hover:
        lay.update(hovermode="x")
        lay["xaxis"].update(showspikes=True, spikemode="across", spikesnap="cursor",
                            spikethickness=1, spikedash="dot", spikecolor="rgba(210,215,225,0.72)")
    if dual:
        lay.update(showlegend=True,
                   legend=dict(orientation="h", x=0, y=1.22, font=dict(size=9), bgcolor="rgba(0,0,0,0)"))
    else:
        lay.update(showlegend=False)
    fig.update_layout(**lay)
    value_str = fmt_override if fmt_override is not None else _fmt(cur, unit)
    return html.Div([
        html.Div([
            html.Span(title, style={"fontSize": "0.78rem", "fontWeight": "700",
                                    "color": "var(--font-color)"}),
            _info_icon(info, scope=title),
            html.Span(value_str, style={"fontSize": "0.95rem", "fontWeight": "700",
                                        "fontFamily": "monospace", "color": color,
                                        "float": "right"}),
        ]),
        html.Div(read, style={"fontSize": "0.66rem", "color": "var(--muted-color)",
                              "marginBottom": "2px", "minHeight": "1.6em"}),
        dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "180px"}),
    ], style={"background": "var(--card-bg)", "border": "1px solid var(--border-color)",
              "borderRadius": "8px", "padding": "10px 12px", "flex": "1 1 300px",
              "minWidth": "280px"},
        className="sync-hover-card" if sync_hover else None)


def _section(title: str, subtitle: str, cards: list, *, columns: int | None = None) -> html.Div:
    return html.Div([
        html.Div(title, style={"fontSize": "0.72rem", "fontWeight": "800",
                               "textTransform": "uppercase", "letterSpacing": "0.06em",
                               "color": "var(--muted-color)", "marginTop": "22px"}),
        html.Div(subtitle, style={"fontSize": "0.72rem", "color": "var(--muted-color)",
                                  "opacity": "0.8", "marginBottom": "10px"}),
        html.Div(cards, style=(
            {"display": "grid", "gap": "8px",
             "gridTemplateColumns": f"repeat({columns}, minmax(0, 1fr))"} if columns
            else {"display": "flex", "flexWrap": "wrap", "gap": "12px"})),
    ])


def _chip(text: str, color: str) -> html.Span:
    return html.Span(text, style={"background": f"{color}22", "border": f"1px solid {color}",
                                  "color": color, "borderRadius": "5px", "padding": "3px 10px",
                                  "fontSize": "0.76rem", "fontWeight": "700",
                                  "whiteSpace": "nowrap"})


# ── External validator rollup (docs/external_validators_plan.md, 2026-10-03) ──
# Mirrors CreovaOne's own app.core.validator_badges.summarize_axis() exactly —
# same rollup rule, so a badge here and a badge there never disagree about
# what a mixed set of per-benchmark verdicts rolls up to.

VERDICT_COLOR: dict[str, str] = {
    "AGREE": GREEN, "PARTIAL": AMBER, "CONTRADICT": RED, "UNKNOWN": GREY,
}


def summarize_validator_axis(verdicts) -> dict:
    """Roll up one axis' validator rows (each with a 'verdict' key) into a
    single badge. 'No judgement calls': UNKNOWN rows are ignored (an
    unreachable/unfitted benchmark says nothing about agreement); any
    CONTRADICT wins over everything else — a validation badge exists to
    surface disagreement, not average it away; otherwise any PARTIAL wins;
    otherwise AGREE if every graded row agrees; None if nothing was
    gradeable (empty, or every row UNKNOWN)."""
    graded = [v for v in verdicts if v.get("verdict") != "UNKNOWN"]
    n_unknown = len(verdicts) - len(graded)
    n_agree = sum(1 for v in graded if v["verdict"] == "AGREE")
    n_partial = sum(1 for v in graded if v["verdict"] == "PARTIAL")
    n_contradict = sum(1 for v in graded if v["verdict"] == "CONTRADICT")
    if not graded:
        verdict = None
    elif n_contradict > 0:
        verdict = "CONTRADICT"
    elif n_partial > 0:
        verdict = "PARTIAL"
    else:
        verdict = "AGREE"
    return {
        "verdict": verdict, "n_agree": n_agree, "n_partial": n_partial,
        "n_contradict": n_contradict, "n_unknown": n_unknown,
    }


# Dark-theme palette anchors — interpolate from washed-out light end to vivid.
# At low magnitude the washed-out tone is still clearly visible on a dark
# background (unlike low-alpha rgba which blends to near-invisible).
_CLR_GREEN_LO = (148, 210, 178)   # soft sage/mint
_CLR_GREEN_HI = (46,  204, 113)   # vivid emerald
_CLR_RED_LO   = (232, 178, 158)   # soft salmon
_CLR_RED_HI   = (231, 76,  60)    # vivid red-orange


def _lerp_rgb(t: float, lo: tuple, hi: tuple) -> str:
    """Linear interpolate between two RGB 3-tuples. t=0 → lo, t=1 → hi."""
    return "rgb({},{},{})".format(
        int(lo[0] + t * (hi[0] - lo[0])),
        int(lo[1] + t * (hi[1] - lo[1])),
        int(lo[2] + t * (hi[2] - lo[2])),
    )


def _signal_link(label: str, signal_id: str) -> html.Span:
    """Clickable signal label that opens the time-series drill-down modal."""
    return html.Span(
        label,
        id={"type": "signal-link", "index": signal_id},
        n_clicks=0,
        style={
            "cursor": "pointer",
            "borderBottom": "1px dotted rgba(200,200,200,0.3)",
        },
    )


def _signal_info_icon(signal_id: str) -> html.Span:
    """Small info icon that opens the signal metadata popup."""
    return html.Span(
        "ⓘ",
        id={"type": "info-icon", "index": signal_id},
        n_clicks=0,
        style={
            "cursor": "pointer",
            "marginLeft": "6px",
            "fontSize": "0.72rem",
            "color": "rgba(140,170,220,0.55)",
            "verticalAlign": "middle",
            "userSelect": "none",
        },
    )


def _concept_label(signal_id: str) -> str:
    parts = signal_id.split(".")
    concept = parts[-1] if len(parts) >= 3 else signal_id
    return concept.replace("_", " ").title()


def _zscore_color(z: Any) -> str:
    if z is None or (isinstance(z, float) and _math.isnan(z)):
        return "#888"
    z = float(z)
    if z > 2:  return "#ff6666"
    if z > 1:  return "#ffaa66"
    if z < -2: return "#6699ff"
    if z < -1: return "#88bbff"
    return "#cccccc"


def _fmt_value(val: Any, units: str) -> str:
    if val is None or (isinstance(val, float) and _math.isnan(val)):
        return "—"
    if units in ("yoy_pct", "yoy_pct_spread"):
        return f"{val*100:+.2f}%"
    if units in (
        "pct_level", "pct_gdp", "pct_pot_gdp",
        "pct_working_age", "pct_pop_15plus", "pct_annual",
        "pct_total_pop", "net_pct",
    ):
        return f"{val:.2f}%"
    if units in ("diffusion_index", "index", "index_2020eq100", "index_2010eq100"):
        return f"{val:.1f}"
    if units == "ratio":
        return f"{val:.3f}"
    if units == "thousands":
        return f"{val/1000:.1f}M" if abs(val) >= 1000 else f"{val:.0f}k"
    if units == "millions_usd":
        if abs(val) >= 1_000_000:
            return f"${val/1_000_000:.2f}T"
        if abs(val) >= 1_000:
            return f"${val/1_000:.1f}B"
        return f"${val:.0f}M"
    return f"{val:.4g}"


def build_force_table(
    lens_signals: "pd.DataFrame",
    histories_by_id: dict | None = None,
) -> html.Div:
    """Build a force signal table as Dash html components.

    Identical in structure to the lens tables on the Regime Map page.
    `histories_by_id` is accepted for API compatibility but not yet used
    (sparklines are a potential future addition).
    """
    if lens_signals is None or lens_signals.empty:
        return html.Div(
            "No signals available.",
            style={"color": "#666", "fontSize": "0.85em", "padding": "8px"},
        )

    _ll_color = {
        "leading": "#aaffaa", "coincident": "#aaaaff",
        "lagging": "#ffaaaa", "structural": "#ddddaa",
    }

    def _pct_badge(pct: Any, low_history: bool) -> html.Span:
        if pct is None or (isinstance(pct, float) and _math.isnan(pct)):
            bg, txt = "#3a3a3a", "—"
        elif low_history:
            bg, txt = "#555", f"{pct:.0%}"
        elif pct > 0.85:
            bg, txt = "#9b1c1c", f"{pct:.0%}"
        elif pct > 0.70:
            bg, txt = "#c05a00", f"{pct:.0%}"
        elif pct < 0.15:
            bg, txt = "#1a3a6e", f"{pct:.0%}"
        elif pct < 0.30:
            bg, txt = "#2155a0", f"{pct:.0%}"
        else:
            bg, txt = "#444", f"{pct:.0%}"
        return html.Span(txt, style={
            "background": bg, "color": "#eee", "padding": "2px 5px",
            "borderRadius": "3px", "fontSize": "0.75em", "fontFamily": "monospace",
        })

    def _quality_badges(row: Any) -> list:
        parts: list = []

        def _bs(txt, bg, fg="#ddd", title=""):
            return html.Span(txt, title=title, style={
                "background": bg, "color": fg, "padding": "1px 4px",
                "borderRadius": "3px", "fontSize": "0.7em", "marginRight": "3px",
            })

        if row.get("is_proxy"):
            parts.append(_bs("proxy", "#5a5a5a", title="proxy series"))
        if row.get("is_stale"):
            parts.append(_bs("stale", "#7a4a00", fg="#ffcc80",
                             title="not updated within release window"))
        if not row.get("vintage_available", True):
            parts.append(_bs("no vintage", "#383838", fg="#aaa",
                             title="latest-revised only"))
        if row.get("low_history"):
            parts.append(_bs("low hist", "#4a5a5a", fg="#cdd",
                             title="<15 observations"))
        return parts

    header_row = html.Tr([
        html.Th("Indicator", style={
            "padding": "4px 8px", "color": "#666", "fontSize": "0.78em",
            "fontWeight": "600", "borderBottom": "1px solid #333",
        }),
        html.Th("Value", style={
            "padding": "4px 8px", "textAlign": "right", "color": "#666",
            "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333",
        }),
        html.Th("Dir", style={
            "padding": "4px 8px", "textAlign": "center", "color": "#666",
            "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333",
        }),
        html.Th("Pct", style={
            "padding": "4px 8px", "textAlign": "center", "color": "#666",
            "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333",
        }),
        html.Th("Z", style={
            "padding": "4px 8px", "textAlign": "center", "color": "#666",
            "fontSize": "0.78em", "fontWeight": "600", "borderBottom": "1px solid #333",
        }),
        html.Th("Quality", style={
            "padding": "4px 8px", "color": "#666", "fontSize": "0.78em",
            "fontWeight": "600", "borderBottom": "1px solid #333",
        }),
    ])

    data_rows = []
    for _, row in lens_signals.iterrows():
        sid      = str(row["id"])
        label    = _concept_label(sid)
        linkage  = str(row.get("linkage") or "")
        val_str  = _fmt_value(row.get("value"), str(row.get("units", "")))
        arrow    = _DIR_ARROW.get(str(row.get("direction") or "flat"), "→")
        pct      = row.get("level_percentile")
        z        = row.get("zscore")
        z_val    = (f"{z:+.2f}" if z is not None
                    and not (isinstance(z, float) and _math.isnan(z)) else "—")
        z_color  = _zscore_color(z)
        ll       = str(row.get("lead_lag", ""))
        ll_col   = _ll_color.get(ll, "#888")
        source   = str(row.get("source", ""))

        data_rows.append(html.Tr([
            html.Td([
                _signal_link(label, sid),
                html.Span(f" {ll}", style={"fontSize": "0.7em", "color": ll_col}),
                html.Br(),
                html.Span(source, style={"fontSize": "0.7em", "color": "#555"}),
            ], style={"padding": "5px 8px"}),
            html.Td(val_str, style={
                "padding": "5px 8px", "textAlign": "right",
                "fontFamily": "monospace", "color": "#ccc",
            }),
            html.Td(arrow, style={
                "padding": "5px 8px", "textAlign": "center", "fontSize": "1.1em",
            }),
            html.Td(
                _pct_badge(pct, bool(row.get("low_history"))),
                style={"padding": "5px 8px", "textAlign": "center"},
            ),
            html.Td(z_val, style={
                "padding": "5px 8px", "textAlign": "center",
                "fontFamily": "monospace", "color": z_color,
            }),
            html.Td(_quality_badges(row), style={"padding": "5px 8px"}),
        ], style={"borderBottom": "1px solid #1e1e2e"}))

    return html.Table(
        [html.Thead(header_row), html.Tbody(data_rows)],
        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.88em"},
    )

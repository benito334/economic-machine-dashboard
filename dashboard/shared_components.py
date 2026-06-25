"""Shared Dash component builders reused across dashboard pages.

Extracted from charting.py so that signals_page.py and future pages
can build the same force-signal table without duplicating the logic.
"""
from __future__ import annotations

import math as _math
from typing import Any

from dash import html

_DIR_ARROW: dict[str, str] = {"rising": "↑", "falling": "↓", "flat": "→"}

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

"""Late-Stage Bubble Gauge — coverage-audit Phase C build-out, 2026-10-04.

Three of Dalio's six late-stage-bubble dimensions are genuinely free-
buildable (confirmed via a live scoping pass, docs/worklog.md 2026-10-03
"Coverage Audit Phase C"): valuation (already built — the Buffett Indicator,
`indicators/valuations.py`), leverage (FINRA margin debt), and positioning
(CFTC leveraged-fund futures positioning). The other three (sentiment,
forward-earnings pricing, new-buyer participation) are confirmed dead ends
— no free live source exists for any of them.

This page shows the 3 dimensions as INDEPENDENT reads, each a full-history
Z-score of its own series — never averaged into one "bubble score". A
3-of-6 composite would manufacture false precision the underlying data
doesn't support; Phase C's own scoping note was explicit that a full
6-dimension gauge was never realistic on free data.

Operator-only (same gating as /valuations, which this page's valuation
dimension reuses) — hidden in PUBLIC_MODE.

Feeds no composite; isolated force, same convention as fed.*/market.*/order.*.
Visual pattern is the shared Monitor-card style (`dashboard.shared_components.
_chart_card`/`_section`/`_chip`), same as every other Monitors-group page.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from dash import html

from dashboard.shared_components import (
    AMBER, FORCE_COLOR, GREY, RED, VERDICT_COLOR, _chart_card, _chip, _section,
)

_LABEL_COLOR = {"Extreme": RED, "Elevated": AMBER, "Normal": VERDICT_COLOR["AGREE"], "—": GREY}


def _direction_note(key: str, z: Optional[float]) -> str:
    if z is None or (isinstance(z, float) and pd.isna(z)):
        return ""
    if key == "positioning":
        return "crowded long" if z > 0 else "crowded short" if z < 0 else "balanced"
    return "above its own history" if z > 0 else "below its own history"


def _dimension_card(key: str, d: dict, color: str) -> html.Div:
    df = d["df"]
    z = d.get("z")
    label = d.get("z_label", "—")
    note = _direction_note(key, z)
    z_str = f"{z:+.2f}σ" if z is not None and not (isinstance(z, float) and pd.isna(z)) else "—"

    read = f"{label} ({z_str} {note})" if note else f"{label} ({z_str})"

    return _chart_card(
        d["label"], df, d.get("current"), d.get("unit", ""), read,
        color=color, zero_line=False,
        info=d.get("desc", "") + f" Full-history Z-score as of {d.get('as_of', '—')}.",
        fmt_override=(f"{d['current']:.2f}" if d.get("current") is not None else None),
    )


def get_layout() -> html.Div:
    from indicators.bubble_gauge import compute_bubble_gauge

    try:
        dims = compute_bubble_gauge()
    except Exception as exc:
        return html.Div(
            f"Bubble gauge unavailable: {exc}",
            style={"color": "var(--muted-color)", "padding": "20px"},
        )

    header = html.Div([
        html.Div([
            html.Span("\U0001fac7 ", style={"fontSize": "1.3rem"}),
            html.Span("Late-Stage Bubble Gauge", style={"fontSize": "1.15rem", "fontWeight": "700",
                                                        "color": "var(--font-color)"}),
            html.Span(" · United States", style={"fontSize": "0.8rem",
                                                       "color": "var(--muted-color)"}),
        ]),
        html.Div(
            "3 of Dalio's 6 late-stage-bubble dimensions, confirmed free-buildable (coverage-audit "
            "Phase C, 2026-10-03): valuation (Buffett Indicator), leverage (FINRA margin debt / "
            "GDP), and positioning (CFTC leveraged-fund net futures positioning). Each is an "
            "independent full-history Z-score — deliberately NOT averaged into one score. The "
            "other 3 dimensions (uniform bullish sentiment, forward-earnings pricing, new/"
            "unsophisticated buyer participation) have no free live data source and are confirmed "
            "dead ends, not oversights.",
            style={"fontSize": "0.74rem", "color": "var(--muted-color)", "marginTop": "6px",
                   "maxWidth": "920px"},
        ),
    ], style={"borderBottom": "1px solid var(--border-color)", "paddingBottom": "12px",
              "marginBottom": "4px"})

    colors = {
        "valuation": FORCE_COLOR.get("growth", "#888"),
        "leverage": FORCE_COLOR.get("credit", "#888"),
        "positioning": FORCE_COLOR.get("volatility", "#888"),
    }
    order = ["valuation", "leverage", "positioning"]

    cards = []
    chips = []
    for key in order:
        d = dims.get(key)
        if d is None:
            cards.append(html.Div(
                f"{key.title()} dimension unavailable — see server log.",
                style={"color": "var(--muted-color)", "fontSize": "0.8rem",
                       "padding": "20px", "flex": "1 1 300px"},
            ))
            continue
        cards.append(_dimension_card(key, d, colors[key]))
        chips.append(_chip(f"{d['label'].split('—')[-1].strip()}: {d['z_label']}",
                           _LABEL_COLOR.get(d['z_label'], GREY)))

    return html.Div([
        header,
        html.Div(chips, style={"display": "flex", "gap": "8px", "flexWrap": "wrap",
                               "marginTop": "10px", "marginBottom": "4px"}),
        _section("", "", cards),
    ], className="p-3", style={"maxWidth": "1500px"})

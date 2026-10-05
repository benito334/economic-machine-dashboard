"""AI Capex Cycle Monitor — Phase 1 (docs/ai_bubble_monitor_plan.md).

From the 2026-10-04 six-expert panel (Digital Ray + credit / semis-equity /
power / forensic-accounting / macro-transmission research agents).

Complements `/bubble-gauge` rather than overlapping it. That page asks whether
the MARKET is late-stage (valuation, margin leverage, futures positioning —
aggregate, Dalio's six dimensions). This one asks whether the AI CAPEX CYCLE
is breaking (mechanism-specific). Cross-linked, deliberately not merged.

Three rules carried from the plan and visible on the page itself:

  * **No blended score.** Ray: "I don't like blended scores for bubbles
    because they hide the real mechanics and create false confidence."
  * **No Z-scores on the Census series** — 12.7 years, zero prior downturns.
  * **The page states its own lead time.** Most of this is confirmation
    infrastructure, not foresight; a monitor that documents its blindness is
    worth more than one implying foresight it doesn't have.

Operator-only (same gating as /bubble-gauge) while the copy settles.
Feeds no composite; isolated force, same convention as fed.*/market.*/order.*.
"""
from __future__ import annotations

import logging

import pandas as pd
from dash import dcc, html

from dashboard.shared_components import (
    AMBER, BLUE, GREEN, GREY, RED, _chart_card, _chip, _section,
)

logger = logging.getLogger(__name__)

_STATE_COLOR = {"OK": GREEN, "WARNING": AMBER, "CRITICAL": RED, "—": GREY}

# Display order: the structural-lead metric first, then the fast credit
# tripwires, then the slower confirmers. This ordering is the argument.
_TIER1 = [
    ("divergence",      BLUE),
    ("trough_load",     GREEN),
    ("abcp",            RED),
    ("ndfi",            AMBER),
    ("ccc_bb",          RED),
    ("dc_construction", BLUE),
    ("concentration",   AMBER),
    ("new_orders",      BLUE),
]

_LEAD_TIMES = [
    ("Equity peak → recession", "12 months"),
    ("New-orders YoY zero-cross → recession", "~2 months"),
    ("Capex level peak → recession", "2 quarters"),
    ("Financing gap peak", "3 quarters AFTER the equity top"),
]


def _metric_card(key: str, m: dict, color: str) -> html.Div:
    """One Tier-1 metric as the shared Monitor chart card."""
    state = m.get("state", "—")
    read = m.get("read", "—")
    cur = m.get("current")

    kwargs = dict(
        color=color,
        info=m.get("desc", ""),
        fmt_override=(f"{cur:+.1f} {m.get('unit','')}"
                      if isinstance(cur, (int, float)) and not pd.isna(cur) else "—"),
    )
    # The divergence card is the one genuinely dual-series read on the page —
    # the comparison IS the signal, so it stays a two-line overlay rather than
    # being split into two cards that lose it.
    if key == "divergence" and m.get("df2") is not None:
        kwargs.update(df2=m["df2"], color2=RED,
                      label=m.get("label_a"), label2=m.get("label_b"))

    return _chart_card(
        m["label"], m.get("df", pd.DataFrame()), cur, m.get("unit", ""),
        f"{state} · {read}", **kwargs,
    )


def _header() -> html.Div:
    return html.Div([
        html.Div([
            html.Span("⚡ ", style={"fontSize": "1.3rem"}),
            html.Span("AI Capex Cycle Monitor",
                      style={"fontSize": "1.15rem", "fontWeight": "700",
                             "color": "var(--font-color)"}),
            html.Span(" · United States", style={"fontSize": "0.8rem",
                                                 "color": "var(--muted-color)"}),
        ]),
        html.Div([
            "Tier-1 metrics — the ones that can trigger a stage. ",
            html.B("Read the lead times below before acting on anything here: "),
            "most of this page is confirmation infrastructure, not foresight. The two "
            "genuine exceptions are the chip-fab divergence (a structural 18-24 month "
            "lead) and the concentration share (actionable today, with no forecast "
            "required). Nothing is averaged into a combined score — per the panel's own "
            "ruling, a blended bubble number hides the mechanics it exists to show. "
            "Market-wide late-stage internals live on ",
            dcc.Link("the Bubble Gauge", href="/bubble-gauge",
                     style={"color": "var(--slider-accent)"}),
            " instead; this page is about the capex cycle itself.",
        ], style={"fontSize": "0.74rem", "color": "var(--muted-color)",
                  "marginTop": "6px", "maxWidth": "920px"}),
    ], style={"borderBottom": "1px solid var(--border-color)", "paddingBottom": "12px",
              "marginBottom": "4px"})


def _lead_time_panel() -> html.Div:
    """The dot-com analogue's actual lead times, on the page per the plan."""
    rows = [html.Tr([
        html.Td(label, style={"padding": "3px 14px 3px 0",
                              "color": "var(--muted-color)"}),
        html.Td(value, style={"padding": "3px 0", "fontWeight": "600",
                              "whiteSpace": "nowrap"}),
    ]) for label, value in _LEAD_TIMES]

    return html.Div([
        html.Div("What the closest analogue actually delivered",
                 style={"fontSize": "0.8rem", "fontWeight": "700",
                        "marginBottom": "6px", "color": "var(--font-color)"}),
        html.Table(rows, style={"fontSize": "0.73rem", "borderCollapse": "collapse"}),
        html.Div(
            "AI's collateral depreciates far faster than dot-com's — 3-5 year GPUs "
            "against 20-30 year fibre — so expect lead time at or below two quarters. "
            "The BIS calibration worth keeping: the largest contraction followed the US "
            "dot-com boom even though that boom was small relative to GDP. Size does not "
            "predict damage; concentration and financing structure do.",
            style={"fontSize": "0.71rem", "color": "var(--muted-color)",
                   "marginTop": "8px", "maxWidth": "780px", "fontStyle": "italic"}),
    ], style={"border": "1px solid var(--border-color)", "borderRadius": "8px",
              "padding": "14px 16px", "marginTop": "18px",
              "background": "var(--card-bg, transparent)"})


def _blind_spots() -> html.Div:
    items = [
        ("The debtor identity", "Borrowers are increasingly SPVs, JVs and neoclouds — "
         "invisible in the Flow of Funds. The nonfinancial corporate financing gap sits "
         "at the 3rd percentile of its 80-year history while the BIS documents a $200bn+ "
         "private-credit book. The aggregates are measuring different entities than the "
         "ones carrying the risk."),
        ("The creditor concentration", "Every published figure traces to a licensed "
         "source. No free substitute exists."),
        ("The contract structure", "Take-or-pay commitments, residual-value guarantees "
         "and circular vendor financing are disclosed in 10-K prose, not in any time "
         "series. Only their balance-sheet residue is tagged."),
    ]
    return html.Div([
        html.Div("What free data cannot see",
                 style={"fontSize": "0.8rem", "fontWeight": "700",
                        "marginBottom": "6px", "color": "var(--font-color)"}),
        html.Ul([
            html.Li([html.B(t + ". "), d], style={"marginBottom": "5px"})
            for t, d in items
        ], style={"fontSize": "0.73rem", "color": "var(--muted-color)",
                  "paddingLeft": "18px", "margin": "0", "maxWidth": "860px"}),
    ], style={"border": "1px solid var(--border-color)", "borderRadius": "8px",
              "padding": "14px 16px", "marginTop": "14px"})


def get_layout() -> html.Div:
    from indicators.ai_capex import compute_ai_capex_metrics

    try:
        metrics = compute_ai_capex_metrics()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[ai_capex_monitor] unavailable: %s", exc)
        return html.Div(f"AI capex monitor unavailable: {exc}",
                        style={"color": "var(--muted-color)", "padding": "20px"})

    chips, cards = [], []
    for key, color in _TIER1:
        m = metrics.get(key)
        if m is None:
            cards.append(html.Div(
                f"{key.replace('_', ' ').title()} — source unavailable, see server log.",
                style={"color": "var(--muted-color)", "fontSize": "0.8rem",
                       "padding": "20px", "flex": "1 1 300px"}))
            continue
        cards.append(_metric_card(key, m, color))
        state = m.get("state", "—")
        if state in ("WARNING", "CRITICAL"):
            chips.append(_chip(f"{m['label']}: {state}", _STATE_COLOR[state]))

    if not chips:
        chips.append(_chip("No Tier-1 metric in warning", GREEN))

    return html.Div([
        _header(),
        html.Div(chips, style={"display": "flex", "gap": "8px", "flexWrap": "wrap",
                               "marginTop": "10px", "marginBottom": "4px"}),
        _section("", "", cards),
        _lead_time_panel(),
        _blind_spots(),
    ], className="p-3", style={"maxWidth": "1500px"})

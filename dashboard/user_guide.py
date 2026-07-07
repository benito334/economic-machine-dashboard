"""User Guide — a training course for the Ray-Dalio-approved tools (route /guide).

A sequential course for someone who knows Dalio's concepts from the books but
has never operated a live diagnostic tool. Teaches only the tools that came
out of the 2026-07 Ray review cycle, with live data woven into every lesson
(his "clear metrics" point: anchor abstract concepts to today's readings).

Pedagogy per Ray's review of the outline (2026-07-06, logged in
ray_dalio_review_log.md): front-load the three newcomer traps (Z-scores are
relative not grades; magnitude is not direction; never trust the two dials
alone), hook the long-term debt cycle right after the big picture BEFORE the
dial mechanics, and make the L0 diagram carry data-source labels, the credit
feedback loop, and an adaptive "normal" band that previews dynamic thresholds.

Formulas stay in the Methodology page — every lesson links to its section.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dash import Input, Output, callback, dcc, html, no_update

from dashboard.charting_data import (
    load_composite_history,
    load_debt_cycle_stage_history,
    load_debt_stress_history,
    load_latest_signals,
)
from dashboard.command_center import STAGE_COLORS, chip_direction_agreement
from dashboard.themes import DEFAULT_THEME, figure_layout

_COUNTRY_NAMES = {"US": "United States", "EZ": "Euro Area", "GB": "United Kingdom",
                  "JP": "Japan", "KR": "South Korea", "CN": "China",
                  "IN": "India", "DE": "Germany", "LU": "Luxembourg",
                  "BR": "Brazil", "CA": "Canada", "AU": "Australia",
                  "MX": "Mexico", "ID": "Indonesia"}

_G_COLOR, _I_COLOR, _AMBER = "#4C9BE8", "#E8734C", "#E8A317"

# ── Shared building blocks ────────────────────────────────────────────────────

_H2 = {"fontSize": "1.0rem", "fontWeight": "700", "color": "var(--font-color)",
       "margin": "6px 0 10px"}
_P = {"fontSize": "0.85rem", "color": "var(--font-color)", "lineHeight": "1.65",
      "maxWidth": "900px", "marginBottom": "10px"}
_MUTED = {"fontSize": "0.78rem", "color": "var(--muted-color)", "lineHeight": "1.6",
          "maxWidth": "900px"}


def _p(*txt) -> html.P:
    return html.P(list(txt), style=_P)


def _mlink(section: str, label: Optional[str] = None) -> dcc.Link:
    return dcc.Link(label or f"Methodology §{section}", href="/methodology",
                    style={"color": _AMBER, "textDecoration": "none",
                           "fontSize": "0.78rem"})


def _trap(title: str, body: str) -> html.Div:
    """Ray's 'common trap' callout — the three misconceptions he front-loaded."""
    return html.Div([
        html.Div(f"⚠ Common trap — {title}",
                 style={"color": _AMBER, "fontWeight": "700", "fontSize": "0.8rem",
                        "marginBottom": "4px"}),
        html.Div(body, style={"fontSize": "0.8rem", "color": "var(--font-color)",
                              "lineHeight": "1.6"}),
    ], style={"border": f"1px solid {_AMBER}", "borderLeft": f"4px solid {_AMBER}",
              "borderRadius": "6px", "padding": "10px 14px", "margin": "12px 0",
              "maxWidth": "900px", "background": "rgba(232,163,23,0.06)"})


def _live_box(children) -> html.Div:
    """'On your dashboard right now' callout — the live-data anchor per lesson."""
    return html.Div([
        html.Div("📡 On your dashboard right now",
                 style={"color": "#5CBA8A", "fontWeight": "700",
                        "fontSize": "0.78rem", "marginBottom": "5px"}),
        html.Div(children, style={"fontSize": "0.82rem", "color": "var(--font-color)",
                                  "lineHeight": "1.65"}),
    ], style={"border": "1px solid #5CBA8A", "borderRadius": "6px",
              "padding": "10px 14px", "margin": "12px 0", "maxWidth": "900px",
              "background": "rgba(92,186,138,0.06)"})


def _flow_box(label: str, color: str = _G_COLOR) -> html.Div:
    return html.Div(label, style={
        "border": f"1.5px solid {color}", "color": color, "borderRadius": "6px",
        "padding": "6px 12px", "fontSize": "0.78rem", "fontWeight": "600",
        "whiteSpace": "nowrap"})


def _flow_arrow(label: str = "") -> html.Div:
    return html.Div(["→", html.Div(label, style={"fontSize": "0.62rem",
                                                 "color": "var(--muted-color)"})],
                    style={"color": "var(--muted-color)", "fontSize": "1.1rem",
                           "textAlign": "center", "padding": "0 2px"})


def _fmt(v, spec="+.2f") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return format(float(v), spec)


# ── Diagrams (plotly = theme-adaptive) ────────────────────────────────────────

def _fig_machine(theme: str) -> go.Figure:
    """L0 — the three lines of the machine + the adaptive 'normal' band.

    Ray's additions: the shaded band around trend expands/contracts (previews
    dynamic thresholds); the order cycle is background shading, not a line.
    """
    x = np.linspace(0, 100, 600)
    trend = 0.9 * x
    long_wave = 16 * np.sin(2 * np.pi * (x - 12) / 75)
    short = 4.5 * np.sin(2 * np.pi * x / 7)
    total = trend + long_wave + short
    band = 6 + 4 * np.abs(np.sin(2 * np.pi * x / 33))     # calm ↔ chaotic

    fig = go.Figure()
    # Order cycle as background shading (internal/external order backdrop)
    fig.add_vrect(x0=55, x1=85, fillcolor="rgba(176,127,212,0.07)", line_width=0,
                  annotation_text="order stress era", annotation_position="top left",
                  annotation_font=dict(size=9, color="#B07FD4"))
    fig.add_trace(go.Scatter(x=x, y=trend + band, mode="lines",
                             line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=trend - band, mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor="rgba(232,163,23,0.10)",
                             name="adaptive 'normal' band", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=trend, mode="lines",
                             line=dict(color="#3FBFB0", width=2, dash="dash"),
                             name="productivity trend (the floor)"))
    fig.add_trace(go.Scatter(x=x, y=trend + long_wave, mode="lines",
                             line=dict(color=_I_COLOR, width=2),
                             name="long-term debt cycle (50–75y)"))
    fig.add_trace(go.Scatter(x=x, y=total, mode="lines",
                             line=dict(color=_G_COLOR, width=1.2),
                             name="short-term debt cycle (5–8y)"))
    layout = figure_layout(theme, "The economic machine — three lines, one band")
    layout.update(height=340, margin=dict(l=30, r=20, t=45, b=25),
                  legend=dict(orientation="h", y=-0.08, font=dict(size=10)),
                  xaxis=dict(title="years", showticklabels=False, showgrid=False),
                  yaxis=dict(title="output", showticklabels=False, showgrid=False))
    fig.update_layout(**layout)
    return fig


def _fig_debt_arc(theme: str, current_stage: Optional[str]) -> go.Figure:
    """L0.5 / L4 — the long-term debt-cycle arc, colored by stage, with a
    marker on the country's current stage."""
    seg = {
        "leveraging":   (np.linspace(0.00, 0.45, 100), "leveraging"),
        "squeeze":      (np.linspace(0.45, 0.58, 40),  "squeeze (the top)"),
        "deleveraging": (np.linspace(0.58, 0.80, 60),  "deleveraging"),
        "reflation":    (np.linspace(0.80, 1.00, 60),  "reflation"),
    }
    def arc(t):
        return np.sin(np.pi * np.clip(t, 0, 1)) ** 1.3

    fig = go.Figure()
    for stage, (t, label) in seg.items():
        fig.add_trace(go.Scatter(
            x=t, y=arc(t), mode="lines", name=label,
            line=dict(color=STAGE_COLORS[stage], width=4),
            hovertemplate=label + "<extra></extra>"))
    mids = {"leveraging": 0.22, "squeeze": 0.51, "deleveraging": 0.69, "reflation": 0.90}
    if current_stage in mids:
        tm = mids[current_stage]
        fig.add_trace(go.Scatter(
            x=[tm], y=[arc(np.array([tm]))[0]], mode="markers+text",
            marker=dict(size=16, color=STAGE_COLORS[current_stage],
                        line=dict(width=2.5, color="#ffffff")),
            text=["you are here"], textposition="top center",
            textfont=dict(size=10, color="var(--font-color)"),
            showlegend=False, hoverinfo="skip"))
    layout = figure_layout(theme, "The ~50–75 year debt cycle — four stages")
    layout.update(height=280, margin=dict(l=25, r=20, t=45, b=20),
                  legend=dict(orientation="h", y=-0.10, font=dict(size=10)),
                  xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
                  yaxis=dict(title="debt / income", showticklabels=False,
                             showgrid=False, zeroline=False))
    fig.update_layout(**layout)
    return fig


def _fig_seasons(theme: str, gz: float, iz: float,
                 g: Optional[float], i: Optional[float]) -> go.Figure:
    """L3 — the map geography in miniature: corner seasons + Transition band,
    with the country's current dot."""
    fig = go.Figure()
    corners = [
        (gz, 3, iz, 3, "#F4C842"), (gz, 3, -3, -iz, "#5CBA8A"),
        (-3, -gz, iz, 3, "#E8734C"), (-3, -gz, -3, -iz, "#4C9BE8"),
    ]
    for x0, x1, y0, y1, color in corners:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=color, opacity=0.12, line=dict(width=0), layer="below")
    for v, axis in [(gz, "x"), (-gz, "x"), (iz, "y"), (-iz, "y")]:
        kw = (dict(x0=v, x1=v, y0=-3, y1=3) if axis == "x"
              else dict(x0=-3, x1=3, y0=v, y1=v))
        fig.add_shape(type="line", line=dict(color="rgba(255,255,255,0.25)",
                                             width=1, dash="dash"), **kw)
    for txt, x, y, c in [("Inflationary Boom", 2.2, 2.7, "#F4C842"),
                         ("Expansion", 2.5, -2.7, "#5CBA8A"),
                         ("Stagflation", -2.4, 2.7, "#E8734C"),
                         ("Disinflationary Slowdown", -1.9, -2.7, "#4C9BE8"),
                         ("Transition band", 0, 0.15, "#888888")]:
        fig.add_annotation(x=x, y=y, text=txt, showarrow=False,
                           font=dict(size=9, color=c, family="monospace"))
    if g is not None and i is not None:
        fig.add_trace(go.Scatter(x=[g], y=[i], mode="markers",
                                 marker=dict(size=14, color=_AMBER,
                                             line=dict(width=2, color="#fff")),
                                 hovertemplate="today<extra></extra>",
                                 showlegend=False))
    layout = figure_layout(theme, "")
    layout.update(height=330, margin=dict(l=35, r=15, t=15, b=35),
                  xaxis=dict(title="Growth Z", range=[-3, 3], zeroline=False),
                  yaxis=dict(title="Inflation Z", range=[-3, 3], zeroline=False),
                  showlegend=False)
    fig.update_layout(**layout)
    return fig


# ── Layout + callback ─────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div(
        html.Div(id="guide-content"),
        className="pe-2 pt-2",
        style={"maxWidth": "1000px", "margin": "0 auto"},
    )


@callback(
    Output("guide-content", "children"),
    [Input("country-store", "data"),
     Input("theme-store", "data"),
     Input("page-trigger", "data"),
     Input("regime-threshold-store", "data"),
     Input("zscore-window-store", "data"),
     Input("inflation-window-store", "data")],
    prevent_initial_call=False,
)
def render_guide(country_data, theme_name, page_trigger, thresholds,
                 zscore_window=48, inflation_window=90):
    page = (page_trigger or {}).get("page", "")
    if page and page != "/guide":
        return no_update
    import dash_bootstrap_components as dbc
    from dashboard.charting import (
        _DEFAULT_THRESHOLDS, _FORCE_WINDOW_COL, _GROWTH_CHIP, _INFLAT_CHIP,
        _INFLATION_WINDOW_COL, _classify_regime, _dyn_threshold_input,
        _season_label, compute_dynamic_thresholds,
    )

    theme = theme_name or DEFAULT_THEME
    country = str(country_data or "US").upper()
    cname = _COUNTRY_NAMES.get(country, country)

    # ── Live state (same construction as the Command Center) ─────────────────
    hist = load_composite_history(country=country)
    latest_sig = load_latest_signals(country)
    g_sfx = _FORCE_WINDOW_COL.get(int(zscore_window or 0))
    i_sfx = _INFLATION_WINDOW_COL.get(int(inflation_window or 0))

    def _usable(col):
        return col in hist.columns and hist[col].notna().any()

    g_col = f"growth_score_{g_sfx}" if g_sfx and _usable(f"growth_score_{g_sfx}") else "growth_score"
    i_col = f"inflation_score_{i_sfx}" if i_sfx and _usable(f"inflation_score_{i_sfx}") else "inflation_score"

    def _last(col):
        if hist.empty or col not in hist.columns:
            return None
        s = hist[col].dropna()
        return float(s.iloc[-1]) if not s.empty else None

    def _dlt(col):
        if hist.empty or col not in hist.columns:
            return None
        s = hist[col].dropna()
        return float(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else None

    g, i = _last(g_col), _last(i_col)
    g_d, i_d = _dlt(g_col), _dlt(i_col)
    t = dict(thresholds or _DEFAULT_THRESHOLDS)
    dyn_on = bool(t.get("dynamic", False))
    dyn_df = (compute_dynamic_thresholds(_dyn_threshold_input(hist, g_col, i_col),
                                         base_gz=float(t.get("gz", 0.5)),
                                         base_iz=float(t.get("iz", 0.5)))
              if not hist.empty else pd.DataFrame())
    eff_gz = float(dyn_df["dyn_gz"].iloc[-1]) if dyn_on and not dyn_df.empty else float(t.get("gz", 0.5))
    eff_iz = float(dyn_df["dyn_iz"].iloc[-1]) if dyn_on and not dyn_df.empty else float(t.get("iz", 0.5))
    chip_t = {**t, "gz": eff_gz, "iz": eff_iz}
    g_chip, i_chip = _classify_regime(g, i, g_d, i_d, chip_t)
    season_now = _season_label(g, i, chip_t)
    g_agree = chip_direction_agreement(latest_sig, "growth", g_d)
    i_agree = chip_direction_agreement(latest_sig, "inflation", i_d)

    try:
        stage_hist = load_debt_cycle_stage_history(country=country)
        labeled = stage_hist[stage_hist["stage"].notna()] if not stage_hist.empty else pd.DataFrame()
        stage_row = labeled.iloc[-1] if not labeled.empty else None
    except Exception:
        stage_row = None
    stage_now = str(stage_row["stage"]) if stage_row is not None else None

    def _sig_val(tail):
        if latest_sig.empty:
            return None
        hit = latest_sig[latest_sig["id"].str.endswith(tail)]
        return float(hit.iloc[0]["value"]) if not hit.empty and hit.iloc[0]["value"] is not None else None

    dsr = _sig_val("credit.debt_service_ratio")
    gini = _sig_val("order.gini")
    rcs = _sig_val("order.reserve_currency_share")
    prod = _last("productivity_score")

    win_txt = (f"{zscore_window}m" if g_col != "growth_score" else "full history",
               f"{inflation_window}m" if i_col != "inflation_score" else "full history")

    chip_style = lambda label, color: html.Span(label, style={
        "background": f"{color}26", "border": f"1px solid {color}", "color": color,
        "borderRadius": "4px", "padding": "1px 8px", "fontWeight": "600",
        "fontSize": "0.8rem", "margin": "0 3px"})

    # ══ L0 — The machine in one picture ═══════════════════════════════════════
    l0 = [
        _p("Everything on this dashboard measures one machine. Its output is the sum of "
           "three curves: a slowly rising ", html.B("productivity trend"),
           " (knowledge and efficiency compound — it is the floor everything reverts to), "
           "a ", html.B("short-term debt cycle"), " of roughly 5–8 years (the familiar "
           "business cycle: credit expands, spending and incomes rise, inflation appears, "
           "policy tightens, credit contracts), and a ", html.B("long-term debt cycle"),
           " of roughly 50–75 years, made of dozens of short cycles that each leave a "
           "little more debt behind than they retire. Around all of it runs the slowest "
           "clock — the cycle of ", html.B("internal and external order"),
           " (wealth gaps, political cohesion, reserve-currency status)."),
        dcc.Graph(figure=_fig_machine(theme), config={"displayModeBar": False}),
        _p("The amber band around the trend is a preview of an idea you will meet again in "
           "Lesson 3: what counts as \"normal\" is not a fixed corridor. In calm eras the "
           "band is narrow — small moves are meaningful. In chaotic eras it widens — the "
           "machine demands more evidence before declaring anything."),
        html.Div("The engine of the short cycle — why credit is the machine's fuel:",
                 style={**_MUTED, "marginBottom": "6px", "fontWeight": "700"}),
        html.Div([
            _flow_box("Credit", _G_COLOR), _flow_arrow("creates"),
            _flow_box("Spending", _G_COLOR), _flow_arrow("is someone's"),
            _flow_box("Income", _G_COLOR), _flow_arrow("supports more"),
            _flow_box("Borrowing", _G_COLOR), _flow_arrow("↺ and services"),
            _flow_box("Debt", _I_COLOR),
        ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap",
                  "gap": "4px", "marginBottom": "10px"}),
        _p("One person's spending is another person's income — that loop is why credit "
           "expansions feel self-reinforcing on the way up and self-defeating on the way "
           "down. The productivity trend is the only part that isn't a loop: it is earned, "
           "not borrowed."),
        html.Div("What we actually measure (every force is observable data, not opinion):",
                 style={**_MUTED, "marginBottom": "6px", "fontWeight": "700"}),
        html.Table([
            html.Thead(html.Tr([html.Th(h, style={"fontSize": "0.72rem", "textAlign": "left",
                                                  "color": "var(--muted-color)", "padding": "3px 10px"})
                                for h in ["Force", "Example inputs", "Which clock it reads"]])),
            html.Tbody([
                html.Tr([html.Td(c, style={"fontSize": "0.78rem", "padding": "3px 10px",
                                           "borderTop": "1px solid var(--border-color)"})
                         for c in row])
                for row in [
                    ["Growth", "payrolls, industrial production, retail sales, PMI", "short-term cycle"],
                    ["Inflation", "core CPI/PCE, wages, breakevens, oil", "short-term cycle"],
                    ["Credit", "lending standards, loan demand, debt ratios", "short AND long cycle"],
                    ["Rate", "policy rate, real yields, 2y−funds expectations", "the policy lever"],
                    ["Volatility", "realized equity vol, VIX", "how trustworthy signals are"],
                    ["Productivity", "output/hour, TFP, R&D intensity", "the trend (the floor)"],
                    ["Order", "Gini, reserve-currency share", "the big cycle"],
                ]
            ]),
        ], style={"borderCollapse": "collapse", "marginBottom": "10px"}),
        _live_box([f"You are looking at {cname}. Its growth force reads {_fmt(g)} and "
                   f"inflation {_fmt(i)} right now (in Z-scores — Lesson 2 explains "
                   f"exactly what that means)."]),
        html.Div([_mlink("1", "Methodology §1–2 (signal contract & processing)")]),
    ]

    # ══ L1 — The long-term debt cycle hook (Ray: introduce BEFORE the dials) ══
    l1 = [
        _p("Before the dials, the backdrop. Ray's teaching order: understand the big wave "
           "first, because it sets the amplitude of everything the short-term tools "
           "measure. The long-term debt cycle has four stages:"),
        dcc.Graph(figure=_fig_debt_arc(theme, stage_now), config={"displayModeBar": False}),
        html.Ul([
            html.Li([html.B("Leveraging — "), "debt grows, but productively: incomes grow "
                     "faster than the interest bill. Feels great; nobody worries."],
                    style=_P),
            html.Li([html.B("Squeeze (the top) — "), "debt service starts eating income. "
                     "The earliest warning is the ", html.B("debt-service ratio"),
                     " — not the debt stock. A country can carry enormous debt cheaply; "
                     "what breaks things is the monthly payment."], style=_P),
            html.Li([html.B("Deleveraging — "), "the painful unwind: defaults, austerity, "
                     "falling asset prices."], style=_P),
            html.Li([html.B("Reflation (\"beautiful deleveraging\") — "), "policy engineers "
                     "nominal growth above bond yields and real rates below real growth, "
                     "so burdens erode gently instead of collapsing."], style=_P),
        ]),
        _p("Two numbers decide which stage you're in more than any others: ",
           html.B("r vs g"), " (is the real interest rate above or below real growth — "
           "is debt outgrowing income?) and ", html.B("nominal growth minus the 10-year "
           "yield"), " (do burdens erode or compound?). Lesson 5 shows the full "
           "classifier."),
        _live_box([f"{cname} is currently classified in the ",
                   chip_style(stage_now or "—", STAGE_COLORS.get(stage_now or "", "#888")),
                   f" stage. Its debt-service ratio is "
                   f"{_fmt(dsr, '.1f') if dsr is not None else '—'}"
                   + ("% of income." if dsr is not None else " (no free data for this country).")]),
        html.Div([_mlink("9", "Methodology §9 (Debt Stress + stage classifier)")]),
    ]

    # ══ L2 — The two dials ════════════════════════════════════════════════════
    l2 = [
        _p("The regime engine reduces dozens of signals to two dials: a Growth score and "
           "an Inflation score. Each is a ", html.B("Z-score"),
           ": how unusual is today compared with this country's own recent normal, "
           "measured in standard deviations. Z = +1 means \"one standard deviation "
           "hotter than typical for this country over the lookback window\". Z = 0 means "
           "\"perfectly ordinary\". Z = −2 means \"very unusually weak\"."),
        _trap("a Z-score is not a grade",
              "Z is relative, not absolute. Japan at growth Z = +1 may still be growing "
              "less in absolute terms than Korea at Z = 0 — the +1 says Japan is unusual "
              "FOR JAPAN. The dials measure surprise vs a country's own history, never "
              "\"is this economy healthy\". Cross-country levels are NOT comparable; "
              "cross-country cycles are (Lesson 7)."),
        _p("How many signals become one dial: each force has a basket (US growth uses "
           "payrolls, industrial production, retail sales and six more). Each signal "
           "gets a weight from its importance (how load-bearing it is), its quality, and "
           "its age — a signal that stops updating fades out on a half-life rather than "
           "lying about its freshness. The dial is the weighted average of the basket's "
           "Z-scores."),
        _p("Each dial also has a ", html.B("momentum"), " read — the month-over-month "
           "change. Level says where you are; momentum says which way you're heading. "
           "The regime chips (next lesson) require BOTH."),
        _live_box([f"{cname} growth dial: {_fmt(g)} (Δ {_fmt(g_d, '+.3f')} this month) · "
                   f"inflation dial: {_fmt(i)} (Δ {_fmt(i_d, '+.3f')}). Reading: growth is "
                   + ("unusually strong" if (g or 0) > 0.5 else
                      "unusually weak" if (g or 0) < -0.5 else "close to its own normal")
                   + " for this country vs its "
                   + f"{win_txt[0]} baseline, and heading "
                   + ("up" if (g_d or 0) > 0 else "down" if (g_d or 0) < 0 else "sideways")
                   + "."]),
        html.Div([_mlink("7", "Methodology §7 (force baskets & weights)")]),
    ]

    # ══ L3 — Chips, thresholds, windows ═══════════════════════════════════════
    l3 = [
        _p("A dial value alone is not a regime. The chip system requires two conditions "
           "at once: the level must be beyond a threshold (±gz for growth, ±iz for "
           "inflation) AND the momentum must agree. Miss either and the chip reads ",
           html.B("Transition"), " — which is honesty, not indecision: the machine is "
           "telling you the evidence is mixed."),
        html.Table([
            html.Thead(html.Tr([html.Th(h, style={"fontSize": "0.72rem", "textAlign": "center",
                                                  "color": "var(--muted-color)", "padding": "4px 12px"})
                                for h in ["", "momentum confirms", "momentum opposes"]])),
            html.Tbody([
                html.Tr([html.Td(html.B("level beyond threshold"), style={"fontSize": "0.78rem", "padding": "4px 12px"}),
                         html.Td(chip_style("Growth / Inflation chip", "#5CBA8A"),
                                 style={"textAlign": "center", "padding": "4px 12px",
                                        "borderTop": "1px solid var(--border-color)"}),
                         html.Td(chip_style("Transition", "#888888"),
                                 style={"textAlign": "center", "padding": "4px 12px",
                                        "borderTop": "1px solid var(--border-color)"})]),
                html.Tr([html.Td(html.B("level inside the band"), style={"fontSize": "0.78rem", "padding": "4px 12px"}),
                         html.Td(chip_style("Transition", "#888888"),
                                 style={"textAlign": "center", "padding": "4px 12px",
                                        "borderTop": "1px solid var(--border-color)"}),
                         html.Td(chip_style("Transition", "#888888"),
                                 style={"textAlign": "center", "padding": "4px 12px",
                                        "borderTop": "1px solid var(--border-color)"})]),
            ]),
        ], style={"borderCollapse": "collapse", "margin": "8px 0 14px"}),
        _trap("magnitude is not direction",
              "A big Z-score with opposing momentum is NOT a regime call. Inflation at "
              "Z = +1.8 but falling three months straight reads Transition — the level "
              "says 'hot', the direction says 'cooling', and the honest summary is "
              "'changing'. Most premature regime calls come from reading only the level."),
        _p(html.B("Windows — what counts as normal. "),
           "Every Z-score needs a baseline. The canonical defaults (Ray's ruling): growth "
           "vs its last 48 months, inflation vs its last 96 (inflation regimes run "
           "longer — a short window would forget the last inflation era too fast). The "
           "sidebar sliders change these; the Command Center header always shows which "
           "window you're reading."),
        _p(html.B("Dynamic thresholds — how far from normal counts as a regime. "),
           "The optional Ray algorithm (Regime Thresholds modal → checkbox) replaces the "
           "fixed ±0.5 with living boundaries: in calm eras the band tightens (small "
           "moves mean something), in chaotic eras it widens (demand more evidence), and "
           "very tight credit raises the inflation bar specifically. On the Regime Map "
           "you can step back in time and watch the band breathe — it was ~5× wider "
           "during the COVID chaos than it is in a calm period."),
        _p(html.B("Chip Direction Agreement"), " tells you which side to trust: the % of "
           "each force's signals moving with its chip's heading. G 85% / I 55% means "
           "the growth call is solid and the inflation call is contested. The ",
           html.B("DIVERGENCE"), " badge is the cycle-shift alarm: growth and inflation "
           "moving oppositely for 3+ months historically precedes policy-rate or "
           "credit-cycle turns."),
        _trap("never trust the two dials alone",
              "The dials are the summary, not the evidence. Before acting on a chip, "
              "check: the agreement bars (is one side contested?), the divergence badge "
              "(is the relationship itself shifting?), and the signal table (is the move "
              "broad or one noisy input?). One lens is never enough — that discipline is "
              "the whole point of a multi-signal machine."),
        _live_box([f"{cname} right now: ",
                   chip_style(f"Growth · {g_chip}", _GROWTH_CHIP.get(g_chip, "#888")),
                   chip_style(f"Inflation · {i_chip}", _INFLAT_CHIP.get(i_chip, "#888")),
                   f" with thresholds ±{eff_gz:.2f} / ±{eff_iz:.2f} "
                   f"({'dynamic' if dyn_on else 'static'} mode), windows "
                   f"{win_txt[0]} / {win_txt[1]}, chip agreement "
                   f"G {f'{g_agree:.0%}' if g_agree is not None else '—'} · "
                   f"I {f'{i_agree:.0%}' if i_agree is not None else '—'}."]),
        html.Div([_mlink("8", "Methodology §8 (classification & dynamic thresholds)")]),
    ]

    # ══ L4 — The Regime Map ═══════════════════════════════════════════════════
    l4 = [
        _p("The Regime Map plots the two dials as one dot: growth east–west, inflation "
           "north–south. The four corners are Dalio's four seasons — but note they are ",
           html.B("map geography, not the decision rule"), ". A season name applies only "
           "beyond the threshold lines; the cross-shaped band in the middle is the "
           "Transition zone. The grey cloud is this country's whole history; the "
           "colored trail is the last 12 months."),
        dcc.Graph(figure=_fig_seasons(theme, eff_gz, eff_iz, g, i),
                  config={"displayModeBar": False}),
        _p("How to use it: the trail's SHAPE is the story. A trail marching east = "
           "growth recovering. A trail curling from the top-right corner toward the "
           "band = an inflationary boom cooling. Use the ← Prev / Next → controls to "
           "replay history month by month — with dynamic thresholds on, the band "
           "itself expands and contracts as you step, showing you what the classifier "
           "demanded in each era."),
        _live_box([f"{cname}'s dot sits at ({_fmt(g)}, {_fmt(i)}) — "
                   f"map region: {season_now}."]),
        html.Div([_mlink("8", "Methodology §8 (what feeds the regime label)")]),
    ]

    # ══ L5 — Debt Stress vs Stage ═════════════════════════════════════════════
    ds_val = None
    try:
        ds_hist = load_debt_stress_history(country=country)
        if not ds_hist.empty and "stress_score" in ds_hist.columns:
            s = ds_hist["stress_score"].dropna()
            ds_val = float(s.iloc[-1]) if not s.empty else None
    except Exception:
        pass
    feats = []
    if stage_row is not None:
        for col, lbl, fmt in [("feat_debt_pct", "debt/GDP percentile", "{:.0%} of own history"),
                              ("feat_debt_traj", "debt/GDP trajectory", "{:+.1f} pp/yr"),
                              ("feat_dsr_trend", "debt-service trend", "{:+.2f} pp / 2y"),
                              ("feat_r_minus_g", "real rate − growth", "{:+.2f} pp"),
                              ("feat_ngdp_minus_yield", "nominal growth − yield", "{:+.2f} pp"),
                              ("feat_gov_interest_z", "gov interest Z", "{:+.2f}"),
                              ("feat_refi_gap", "refinancing gap", "{:+.2f} pp")]:
            v = stage_row.get(col)
            if v is not None and not pd.isna(v):
                feats.append(f"{lbl}: {fmt.format(float(v))}")
    priv_now = str(stage_row.get("stage_private")) if stage_row is not None and stage_row.get("stage_private") else None
    sov_now = str(stage_row.get("stage_sovereign")) if stage_row is not None and stage_row.get("stage_sovereign") else None
    l5 = [
        _p("Two different questions about the long cycle: ", html.B("Debt Stress"),
           " asks \"how much pressure?\" (a weighted composite of debt stocks and "
           "flows — a level). The ", html.B("Stage classifier"),
           " asks \"where in the 50–75 year arc?\" (Lesson 1's four stages — a position). "
           "A country can be low-stress but late-stage, or high-stress early — the "
           "pair matters more than either alone."),
        _p("The stage is a transparent vote across five observable features — no fitted "
           "model, every threshold in a config file: the debt/GDP percentile (vs the "
           "country's own history), its 3-year trajectory, the 2-year debt-service "
           "trend, r − g, and nominal-growth-minus-yield. Missing features renormalize "
           "honestly (some countries lack a free debt-service series, so they run on "
           "4 of 5). The label needs 2-of-3 quarters to flip — no flapping."),
        _p("Reading the pair: the earliest trouble signal is the ", html.B("debt-service "
           "ratio rising"), " while r − g crosses positive — that combination is the "
           "squeeze forming, and it appears BEFORE the stress composite peaks."),
        _p("The stage is actually two independent votes — ", html.B("private"),
           " (household + corporate debt) and ", html.B("sovereign"),
           " (government debt only) — with the headline being whichever reads worse. "
           "This matters because a deleveraged private sector can mask a stressed "
           "government: a separate ", html.B("SOVEREIGN SQUEEZE"),
           " flag fires independently of the headline whenever refinancing pressure "
           "or the government's own interest bill crosses its threshold — so you can "
           "see \"the current mechanism\" and \"the sovereign warning\" at the same time, "
           "even when they disagree."),
        _live_box([f"{cname}: stage ",
                   chip_style(stage_now or "—", STAGE_COLORS.get(stage_now or "", "#888")),
                   (f" · Debt Stress {_fmt(ds_val)}" if ds_val is not None
                    else " · Debt Stress composite is US-only today"),
                   (f" · private: {priv_now} · sovereign: {sov_now}"
                    if priv_now and sov_now and priv_now != sov_now else ""),
                   (". Driving features — " + " · ".join(feats)) if feats else "",
                   (" · ⚠ SOVEREIGN SQUEEZE flag is active" if
                    (stage_row is not None and bool(stage_row.get("sovereign_squeeze")))
                    else "")]),
        html.Div([_mlink("9", "Methodology §9 (formulas + stage conditions)")]),
    ]

    # ══ L6 — Productivity & order ═════════════════════════════════════════════
    l6 = [
        _p("Two slow gauges frame everything the fast tools say."),
        _p(html.B("Productivity trend vs cycle. "), "The Productivity dial is the trend "
           "force — output per hour, TFP, R&D intensity. Compare it against the Growth "
           "dial: \"cyclically strong but trend-decelerating\" is the classic late-era "
           "read (borrowed strength), while \"cyclically weak but trend-rising\" is the "
           "setup buyers of the next decade want. The productivity page overlays both "
           "lines for exactly this comparison."),
        _p(html.B("Order — the big-cycle position. "), "Internal order: the Gini index — "
           "widening wealth gaps precede populism and policy lurches (annual data with "
           "long lags; read it in decades, not quarters). External order: the country's "
           "share of global FX reserves — Dalio's \"last privilege an empire loses\". "
           "The USD share has drifted from 71% (1999) to ~57% today: slow, steady, and "
           "the single most important background fact for a dollar-based investor."),
        _live_box([f"{cname}: productivity trend Z {_fmt(prod)}"
                   + (f" · Gini {gini:.1f}" if gini is not None else "")
                   + (f" · reserve-currency share {rcs:.1f}%" if rcs is not None else "")
                   + ". (Order signals are structural — they feed no fast composite by design.)"]),
        html.Div([_mlink("7", "Methodology §7 · big-cycle order in the revision log")]),
    ]

    # ══ L7 — Diversification ══════════════════════════════════════════════════
    l7 = [
        _p("Dalio's core portfolio idea is uncorrelated return streams — and the "
           "prerequisite is uncorrelated ", html.I("cycles"), ". The Relative Cycles "
           "page answers this in two parts: five countries' three clocks side by side, "
           "and correlation matrices of their growth and inflation cycles (every "
           "country normalized on the same canonical window, so the matrix measures "
           "co-movement, not baseline differences)."),
        _p("Reading the matrix: orange (+1) means two economies are the same cycle in "
           "disguise — owning both is one bet twice. Blue (negative) is real "
           "diversification. Watch the last-10-years matrix more than the full "
           "history — correlations drift, and the recent window is the "
           "forward-looking read."),
        _p("Today's honest answer: US–EZ growth runs ~0.86 over the last decade, and "
           "inflation cycles are 0.84–0.90 correlated almost everywhere (the 2021–23 "
           "global wave). The one genuine diversifier in the mapped set is Japan's "
           "inflation cycle (~0.03 vs the US)."),
        _live_box(["Open Relative Cycles and find the bluest cell in the last-10y "
                   "matrices — that pair is your best cycle-diversification candidate "
                   "among the mapped countries right now."]),
    ]

    # ══ L8 — The reading routine ══════════════════════════════════════════════
    l8 = [
        _p("The tools only compound if you read them on a rhythm. A suggested practice:"),
        html.Ul([
            html.Li([html.B("Daily, 30 seconds — Command Center only. "),
                     "Chips changed? DIVERGENCE badge lit? Stage changed? Skim the "
                     "what-changed feed for any |ΔZ| > 0.5. If nothing moved, you're done."],
                    style=_P),
            html.Li([html.B("Weekly, 10 minutes. "), "Regime Map: is the trail bending? "
                     "Check chip agreement — a decaying agreement number often precedes "
                     "the chip itself flipping. Glance at Relative Cycles for correlation "
                     "drift."], style=_P),
            html.Li([html.B("Monthly, 30 minutes. "), "Debt Stress components (which "
                     "component moved?), the productivity-vs-cycle overlay, and the "
                     "order gauges. These move slowly — monthly is enough."], style=_P),
        ]),
        _p(html.B("When a chip flips: "), "don't act on day one. Check (1) agreement — is "
           "the move broad-based?, (2) the signal table — which inputs drove it, and are "
           "they revision-prone?, (3) the map — did the dot cross decisively or is it "
           "hugging the line? The backtest's lesson: with honest point-in-time data the "
           "chips almost never point the wrong DIRECTION, but they flip to Transition "
           "early and often. Transition is a posture (reduce conviction), not a signal."),
        _p(html.B("The boundary: "), "this is a diagnostic machine. It tells you what "
           "season it is and where the long cycle stands — it deliberately contains no "
           "position sizing, no asset selection, no risk parity. Keep the diagnosis and "
           "the allocation as separate disciplines, the way the machine keeps its "
           "layers separate."),
        html.Div([_mlink("15", "Methodology §15 (revision log — how this machine evolves)")]),
    ]

    lessons = [
        ("0 · The machine in one picture", l0),
        ("1 · The big wave — the long-term debt cycle in 60 seconds", l1),
        ("2 · The two dials — Z-scores and momentum", l2),
        ("3 · Chips, thresholds, and windows — the decision rule", l3),
        ("4 · The Regime Map — reading the seasons", l4),
        ("5 · Debt Stress vs Stage — pressure and position", l5),
        ("6 · Productivity and Order — the slow gauges", l6),
        ("7 · Diversification — the Relative Cycles page", l7),
        ("8 · The reading routine — putting it into practice", l8),
    ]
    return html.Div([
        html.Div([
            html.Span("User Guide — operating the Dalio machine",
                      style={"fontSize": "1.15rem", "fontWeight": "700",
                             "color": "var(--font-color)"}),
            html.Div(f"A training course on the Ray-reviewed tools. Live values are for "
                     f"{cname} and update with the country selector and sidebar windows. "
                     f"Work the lessons in order the first time; afterwards it's a reference.",
                     style={**_MUTED, "marginTop": "4px"}),
        ], style={"borderBottom": "1px solid var(--border-color)",
                  "paddingBottom": "10px", "marginBottom": "8px"}),
        dbc.Accordion(
            [dbc.AccordionItem(body, title=title) for title, body in lessons],
            start_collapsed=False, always_open=True, active_item="item-0",
        ),
    ])

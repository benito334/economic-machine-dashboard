"""Market Expectations — the discount rate and what the market prices in.

Built from a Digital Ray consult (ray_dalio_review_log.md, 2026-07-15). Turns Ray's
market-implied formulas into a diagnostic lens:

    Nominal yield (i) = Real rate (r) + Breakeven inflation (BEI)     [i = r + E(π) + RP]
    BEI = nominal − TIPS ;  E(π) ≈ BEI − term premium
    Real-growth signal ≈ the real (TIPS) yield

Six `market.*` FRED series (isolated force — page only, no composite/regime/DB):
DGS5/DGS10 nominal, DFII5/DFII10 real (TIPS), T5YIE/T10YIE breakevens, plus the
Cleveland-Fed 1y expected-inflation series. Read-only against the signals DB.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from dashboard.fed_monitor import (
    _BLUE, _AMBER, _RED, _GREEN, _GREY, _chart_card, _section, _chip, _info_icon,
    _hist, _latest, _fmt,
)
from dashboard.themes import DEFAULT_THEME, figure_layout

_ACCENT = _AMBER


# ── helpers ──────────────────────────────────────────────────────────────────

def _val_ago(concept: str, months: int) -> float | None:
    """Value ~`months` ago (nearest observation) for a market.* series."""
    df = _hist(f"market.{concept}", start=None)
    if df.empty:
        return None
    df = df.copy()
    df["as_of"] = pd.to_datetime(df["as_of"])
    cutoff = df["as_of"].iloc[-1] - pd.DateOffset(months=months)
    prior = df[df["as_of"] <= cutoff]
    return float(prior["value"].iloc[-1]) if not prior.empty else None


def _slope_series() -> pd.DataFrame:
    """10y − 5y breakeven (expectations-curve slope), date-aligned."""
    b10 = _hist("market.breakeven_10y")
    b5 = _hist("market.breakeven_5y")
    if b10.empty or b5.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    a = b10.rename(columns={"value": "b10"})[["as_of", "b10"]]
    b = b5.rename(columns={"value": "b5"})[["as_of", "b5"]]
    m = pd.merge(a, b, on="as_of", how="inner")
    m["value"] = m["b10"] - m["b5"]
    return m[["as_of", "value"]]


def _cur(concept: str):
    v, _ = _latest(f"market.{concept}")
    return v


# ── custom cards (decomposition + curve + 2×2) ───────────────────────────────

def _card_wrap(children) -> html.Div:
    return html.Div(children, style={
        "background": "var(--card-bg)", "border": "1px solid var(--border-color)",
        "borderRadius": "8px", "padding": "10px 12px", "flex": "1 1 300px", "minWidth": "280px"})


def _decomposition_card() -> html.Div:
    """Two horizontal stacked bars (5y, 10y): real + breakeven = nominal yield."""
    rows = []
    for tenor, real_c, bei_c, nom_c in [("10-Year", "real_10y", "breakeven_10y", "nominal_10y"),
                                        ("5-Year", "real_5y", "breakeven_5y", "nominal_5y")]:
        r, b, n = _cur(real_c), _cur(bei_c), _cur(nom_c)
        rows.append((tenor, r, b, n))
    fig = go.Figure()
    labels = [x[0] for x in rows]
    reals = [x[1] or 0 for x in rows]
    beis = [x[2] or 0 for x in rows]
    fig.add_trace(go.Bar(y=labels, x=reals, name="Real rate", orientation="h",
                         marker_color=_BLUE, hovertemplate="Real %{x:.2f}%<extra></extra>",
                         text=[f"{v:.2f}" for v in reals], textposition="inside",
                         insidetextanchor="middle", textfont=dict(size=10, color="#fff")))
    fig.add_trace(go.Bar(y=labels, x=beis, name="Breakeven inflation", orientation="h",
                         marker_color=_AMBER, hovertemplate="Breakeven %{x:.2f}%<extra></extra>",
                         text=[f"{v:.2f}" for v in beis], textposition="inside",
                         insidetextanchor="middle", textfont=dict(size=10, color="#1c1c1c")))
    for i, (_, _, _, n) in enumerate(rows):
        if n is not None:
            fig.add_annotation(y=labels[i], x=n, text=f"= {n:.2f}%", showarrow=False,
                               xanchor="left", xshift=5, font=dict(size=9, color="var(--font-color)"))
    lay = figure_layout(DEFAULT_THEME)
    lay.update(height=170, margin=dict(l=6, r=8, t=6, b=18), barmode="stack",
               legend=dict(orientation="h", y=-0.25, x=0, font=dict(size=9)),
               xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", ticksuffix="%",
                          range=[0, max([x[3] or 0 for x in rows]) * 1.55 + 0.5]),
               yaxis=dict(showgrid=False))
    fig.update_layout(**lay)
    return _card_wrap([
        html.Div([
            html.Span("Discount-rate decomposition", style={"fontSize": "0.78rem",
                      "fontWeight": "700", "color": "var(--font-color)"}),
            _info_icon("Ray's identity: a nominal Treasury yield = the real (TIPS) yield + "
                       "breakeven inflation. The blue segment is the market's real rate (its "
                       "real-growth signal); the amber segment is the inflation the market is "
                       "pricing in. Together they equal the nominal discount rate that values "
                       "every asset."),
        ]),
        html.Div("Nominal yield = real rate + breakeven inflation (i = r + E(π) + RP).",
                 style={"fontSize": "0.66rem", "color": "var(--muted-color)",
                        "marginBottom": "2px", "minHeight": "1.6em"}),
        dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "170px"}),
    ])


def _bei_curve_card() -> html.Div:
    """Term structure of inflation expectations: 1y / 5y / 10y at the latest date."""
    pts = [("1y", _cur("exp_infl_1y")), ("5y", _cur("breakeven_5y")), ("10y", _cur("breakeven_10y"))]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines+markers+text",
                               line=dict(color=_AMBER, width=2), marker=dict(size=8, color=_AMBER),
                               text=[f"{v:.2f}%" if v is not None else "" for v in ys],
                               textposition="top center", textfont=dict(size=10)))
    fig.add_hline(y=2.0, line=dict(color=_GREY, dash="dash", width=1),
                  annotation_text="2% target", annotation_position="bottom left",
                  annotation_font=dict(size=9, color=_GREY))
    lay = figure_layout(DEFAULT_THEME)
    lay.update(height=170, margin=dict(l=6, r=8, t=14, b=18), showlegend=False,
               xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, ticksuffix="%",
                          gridcolor="rgba(255,255,255,0.05)"))
    fig.update_layout(**lay)
    return _card_wrap([
        html.Div([
            html.Span("Inflation-expectations curve", style={"fontSize": "0.78rem",
                      "fontWeight": "700", "color": "var(--font-color)"}),
            _info_icon("The market's expected inflation at three horizons: 1-year (Cleveland-Fed "
                       "model), 5-year and 10-year breakevens. Upward-sloping = inflation expected "
                       "to build; a high 1y above the 5y flags a near-term shock the market sees as "
                       "transitory."),
        ]),
        html.Div("Near-term (1y) vs medium (5y) vs long (10y) market-implied inflation.",
                 style={"fontSize": "0.66rem", "color": "var(--muted-color)",
                        "marginBottom": "2px", "minHeight": "1.6em"}),
        dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "170px"}),
    ])


def _quadrant_card() -> html.Div:
    """Ray's Breakeven × Real-Yield 2×2 — 3-month change in each axis."""
    d_bei = None if _cur("breakeven_10y") is None or _val_ago("breakeven_10y", 3) is None \
        else _cur("breakeven_10y") - _val_ago("breakeven_10y", 3)
    d_real = None if _cur("real_10y") is None or _val_ago("real_10y", 3) is None \
        else _cur("real_10y") - _val_ago("real_10y", 3)
    fig = go.Figure()
    lim = 0.6
    if d_bei is not None and d_real is not None:
        lim = max(0.6, abs(d_bei) * 1.4, abs(d_real) * 1.4)
    fig.add_hline(y=0, line=dict(color=_GREY, width=1))
    fig.add_vline(x=0, line=dict(color=_GREY, width=1))
    quad = [(lim/2, lim/2, "Inflation ↑ &<br>growth ↑", _RED),
            (-lim/2, lim/2, "Stagflation-lean<br>infl ↑ growth ↓", _AMBER),
            (lim/2, -lim/2, "Disinflation,<br>growth firm", _GREEN),
            (-lim/2, -lim/2, "Easing:<br>weak growth+infl", _BLUE)]
    for x, y, txt, col in quad:
        fig.add_annotation(x=x, y=y, text=txt, showarrow=False,
                           font=dict(size=9, color=col), opacity=0.85)
    if d_bei is not None and d_real is not None:
        fig.add_trace(go.Scatter(x=[d_real], y=[d_bei], mode="markers",
                                 marker=dict(size=15, color=_ACCENT, line=dict(color="#fff", width=2)),
                                 hovertemplate=f"ΔReal {d_real:+.2f}pp · ΔBEI {d_bei:+.2f}pp<extra></extra>"))
    lay = figure_layout(DEFAULT_THEME)
    lay.update(height=210, margin=dict(l=6, r=8, t=6, b=6), showlegend=False,
               xaxis=dict(range=[-lim, lim], title="Δ real yield (3m, pp)", zeroline=False,
                          showgrid=False, title_font=dict(size=9)),
               yaxis=dict(range=[-lim, lim], title="Δ breakeven (3m, pp)", zeroline=False,
                          showgrid=False, title_font=dict(size=9)))
    fig.update_layout(**lay)
    return _card_wrap([
        html.Div([
            html.Span("Breakeven × Real-Yield read", style={"fontSize": "0.78rem",
                      "fontWeight": "700", "color": "var(--font-color)"}),
            _info_icon("Ray's 2×2: the 3-month change in 10y breakeven inflation (vertical) vs the "
                       "10y real yield (horizontal). Up-right = inflation and growth expectations "
                       "both rising (tightening); up-left = stagflation-lean; down-right = "
                       "disinflation with firm growth; down-left = easing. The dot is where the "
                       "market has moved over the last 3 months."),
        ]),
        html.Div(_quadrant_read(d_bei, d_real), style={"fontSize": "0.66rem",
                 "color": "var(--muted-color)", "marginBottom": "2px", "minHeight": "1.6em"}),
        dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "210px"}),
    ])


def _quadrant_read(d_bei, d_real) -> str:
    if d_bei is None or d_real is None:
        return "3-month change in breakeven vs real yield."
    if d_bei >= 0 and d_real >= 0:
        return "Both inflation and growth expectations rising — tightening bias."
    if d_bei >= 0 and d_real < 0:
        return "Inflation expectations up, growth weakening — stagflation-lean."
    if d_bei < 0 and d_real >= 0:
        return "Disinflation with firmer real growth."
    return "Weak growth and falling inflation — easing bias."


# ── header ───────────────────────────────────────────────────────────────────

def _header() -> html.Div:
    nom, real, bei = _cur("nominal_10y"), _cur("real_10y"), _cur("breakeven_10y")
    slope_df = _slope_series()
    slope = float(slope_df["value"].iloc[-1]) if not slope_df.empty else None
    slope_txt = ("flat" if slope is not None and abs(slope) < 0.05 else
                 "steepening" if (slope or 0) > 0 else "near-term shock")
    d_bei = None if bei is None or _val_ago("breakeven_10y", 3) is None else bei - _val_ago("breakeven_10y", 3)
    d_real = None if real is None or _val_ago("real_10y", 3) is None else real - _val_ago("real_10y", 3)
    return html.Div([
        html.Div([
            html.Span("📐 ", style={"fontSize": "1.3rem"}),
            html.Span("Market Expectations", style={"fontSize": "1.15rem", "fontWeight": "700",
                                                    "color": "var(--font-color)"}),
            html.Span(" · United States", style={"fontSize": "0.8rem", "color": "var(--muted-color)"}),
        ]),
        html.Div([
            _chip(f"10y nominal {nom:.2f}%" if nom is not None else "nominal —", _GREY),
            _chip(f"10y real {real:.2f}%" if real is not None else "real —",
                  _BLUE if (real or 0) < 1 else _RED),
            _chip(f"10y breakeven {bei:.2f}%" if bei is not None else "breakeven —",
                  _RED if (bei or 0) > 3 else _GREEN if (bei or 0) < 1.5 else _AMBER),
            _chip(f"BEI slope {slope:+.2f} · {slope_txt}" if slope is not None else "slope —", _BLUE),
            _chip(_quadrant_read(d_bei, d_real), _ACCENT),
        ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginTop": "8px"}),
    ], style={"borderBottom": "1px solid var(--border-color)", "paddingBottom": "12px"})


# ── layout ───────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    s1 = _section(
        "① Discount rate — what values every asset",
        "The nominal rate splits into the real rate (growth signal) + priced-in inflation.",
        [
            _decomposition_card(),
            _chart_card("10-year nominal yield", _hist("market.nominal_10y"), _cur("nominal_10y"),
                        "%", "The benchmark discount rate.", color=_GREY,
                        info="The 10-year Treasury yield — the benchmark rate off which equities, "
                             "credit and long-duration assets are discounted. It equals the real "
                             "yield plus 10-year breakeven inflation."),
        ])

    s2 = _section(
        "② Inflation expectations — the market's priced-in inflation",
        "Breakeven inflation = nominal − TIPS. Ray: E(π) ≈ breakeven − risk premium.",
        [
            _bei_curve_card(),
            _chart_card("5-year breakeven inflation", _hist("market.breakeven_5y"), _cur("breakeven_5y"),
                        "%", "2–3% moderate · >3.5% concern · <1.5% deflation.",
                        hline=2.0, hline_txt="2% target", color=_AMBER,
                        info="Market-implied average inflation over the next 5 years (5y nominal − "
                             "5y TIPS). Ray's read: 2–3% is moderate, above 3.5% is a concern, below "
                             "1.5% signals deflation risk."),
            _chart_card("10-year breakeven inflation", _hist("market.breakeven_10y"), _cur("breakeven_10y"),
                        "%", "Long-run anchor; watch the 5y–10y gap.",
                        hline=2.0, hline_txt="2% target", color=_AMBER,
                        info="Long-run market-implied inflation. Compare with the 5y: a 10y above "
                             "the 5y (steepening) means the market sees inflation building later; "
                             "below means a near-term shock fading."),
            _chart_card("Expectations-curve slope (10y − 5y)", _slope_series(),
                        (float(_slope_series()['value'].iloc[-1]) if not _slope_series().empty else None),
                        "pp", "Steepening (+) = inflation building; negative = near-term shock.",
                        zero_line=True, color=_BLUE,
                        info="10-year minus 5-year breakeven. Positive/steepening = the market "
                             "prices more inflation in the long run than the short; negative "
                             "(inverted) usually reflects a near-term price shock expected to fade."),
        ])

    s3 = _section(
        "③ Real rate — the market's growth signal",
        "The TIPS (real) yield is Ray's proxy for real-growth expectations and the policy stance.",
        [
            _chart_card("10-year real yield (TIPS)", _hist("market.real_10y"), _cur("real_10y"),
                        "%", ">1% restrictive · ~0–1% typical · <0 weak growth.",
                        zero_line=True, hline=1.0, hline_txt="1% restrictive", color=_BLUE, fill=True,
                        info="The 10-year TIPS yield — the real rate the market demands. Ray treats "
                             "it as the real-growth signal: rising = firmer growth expectations or a "
                             "tighter stance; negative = the market pricing very weak growth or "
                             "deflation risk."),
            _chart_card("5-year real yield (TIPS)", _hist("market.real_5y"), _cur("real_5y"),
                        "%", "The nearer-term real rate.", zero_line=True, hline=1.0,
                        hline_txt="1% restrictive", color=_BLUE, fill=True,
                        info="The 5-year TIPS yield — the nearer-term real rate. Read alongside the "
                             "10y: a higher 5y than 10y real yield points to a restrictive stance now "
                             "that the market expects to ease later."),
            _chart_card("1-year expected inflation", _hist("market.exp_infl_1y"), _cur("exp_infl_1y"),
                        "%", "Cleveland-Fed near-term expectation.", hline=2.0, hline_txt="2% target",
                        color=_AMBER,
                        info="The Cleveland Fed's model estimate of expected inflation over the next "
                             "year — a cleaner near-term read than breakevens. A wide gap over the 5y "
                             "breakeven flags a transitory shock rather than a structural shift."),
        ])

    s4 = _section(
        "④ Ray's 2×2 — inflation vs growth, at a glance",
        "The 3-month move in breakeven inflation against the real yield tells you the regime.",
        [_quadrant_card()])

    note = html.Div(
        "Formulas from a Digital Ray consult (2026-07-15) — an AI approximation of Ray Dalio's "
        "market-implied framework, not vetted by Ray Dalio. Nominal DGS5/DGS10, real DFII5/DFII10, "
        "breakevens T5YIE/T10YIE, 1y expectation EXPINF1YR — all FRED, verified. Diagnostic only: "
        "these market.* series feed this page, not the composites, regime label, or data-confidence score.",
        style={"fontSize": "0.68rem", "color": "var(--muted-color)", "marginTop": "24px",
               "opacity": "0.75"})

    return html.Div([_header(), s1, s2, s3, s4, note],
                    className="p-3", style={"maxWidth": "1500px"})

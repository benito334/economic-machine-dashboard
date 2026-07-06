"""Country command center — the front-door synthesis page (roadmap Phase CC).

One page that answers "where is this country, on all three clocks, and what's
changing" — assembled entirely from data the pipeline already computes. The
existing detail pages become drill-downs: every card links to its page.

Built around the handful of reads the 2026-07 Ray Dalio review said actually
matter: the two dials plus the credit/rate LEVERS (supply AND demand side,
policy stance + expected path), the debt-service ratio as the earliest
long-cycle signal, the productivity trend as the baseline, the growth/inflation
divergence flag as the cycle-shift alarm, and change-over-level throughout.

Routes "/" and "/country". The long-term-cycle STAGE card is live (Phase C);
a placeholder card marks the remaining unbuilt layer (big-cycle ORDER — Phase D).
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from dash import Input, Output, callback, dcc, html, no_update

from dashboard.charting_data import (
    load_change_feed,
    load_composite_history,
    load_debt_cycle_stage_history,
    load_debt_stress_history,
    load_latest_signals,
)

# Stage chip colors — shared with the Debt Stress page timeline.
STAGE_COLORS = {
    "leveraging": "#4C9BE8", "squeeze": "#E8734C",
    "deleveraging": "#B07FD4", "reflation": "#5CBA8A", "neutral": "#888888",
}

_COUNTRY_NAMES = {"US": "United States", "EZ": "Euro Area", "GB": "United Kingdom",
                  "JP": "Japan", "KR": "South Korea"}

_CARD = {
    "background": "var(--card-bg)", "border": "1px solid var(--border-color)",
    "borderRadius": "8px", "padding": "12px 14px", "minWidth": "170px",
    "flex": "1 1 170px",
}
_CARD_PLANNED = {**_CARD, "border": "1px dashed var(--border-color)", "opacity": "0.75"}
_LABEL = {"fontSize": "0.62rem", "textTransform": "uppercase",
          "letterSpacing": "0.08em", "color": "var(--muted-color)",
          "marginBottom": "3px"}
_BIG = {"fontSize": "1.25rem", "fontFamily": "monospace", "fontWeight": "700",
        "color": "var(--font-color)"}
_SUB = {"fontSize": "0.72rem", "color": "var(--muted-color)", "marginTop": "2px"}
_ROW = {"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "14px"}
_H = {"fontSize": "0.72rem", "textTransform": "uppercase", "letterSpacing": "0.10em",
      "color": "var(--muted-color)", "margin": "16px 0 8px", "fontWeight": "700"}


def get_layout() -> html.Div:
    return html.Div(
        html.Div(id="cc-content"),
        className="pe-2 pt-2",
        style={"maxWidth": "1250px", "margin": "0 auto"},
    )


def _fmt(v: Optional[float], spec: str = "+.3f") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return format(float(v), spec)


def _latest(hist: pd.DataFrame, col: str) -> Optional[float]:
    if hist.empty or col not in hist.columns:
        return None
    s = hist[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None


def _delta(hist: pd.DataFrame, col: str) -> Optional[float]:
    if hist.empty or col not in hist.columns:
        return None
    s = hist[col].dropna()
    return float(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else None


def _sig(latest: pd.DataFrame, concept: str) -> dict:
    """Latest value/direction for one signal by concept tail."""
    if latest.empty:
        return {}
    hit = latest[latest["id"].str.endswith(concept)]
    if hit.empty:
        return {}
    r = hit.iloc[0]
    return {"value": r.get("value"), "direction": r.get("direction"),
            "zscore": r.get("zscore"), "as_of": r.get("as_of"),
            "change_12m": r.get("change_12m")}


def _card(label: str, big: str, sub: str, href: Optional[str] = None,
          big_color: str = "var(--font-color)", planned: bool = False) -> html.Div:
    body = [
        html.Div(label, style=_LABEL),
        html.Div(big, style={**_BIG, "color": big_color}),
        html.Div(sub, style=_SUB),
    ]
    style = _CARD_PLANNED if planned else _CARD
    if href:
        return dcc.Link(html.Div(body, style=style), href=href,
                        style={"textDecoration": "none", "display": "flex", "flex": "1 1 170px"})
    return html.Div(body, style=style)


def _chip_span(text: str, color: str) -> html.Span:
    return html.Span(text, style={
        "background": f"{color}26", "border": f"1px solid {color}",
        "color": color, "borderRadius": "4px", "padding": "3px 10px",
        "fontSize": "0.78rem", "fontWeight": "600", "whiteSpace": "nowrap",
    })


@callback(
    Output("cc-content", "children"),
    [Input("country-store", "data"),
     Input("page-trigger", "data"),
     Input("regime-threshold-store", "data")],
    prevent_initial_call=False,
)
def render_command_center(country_data, page_trigger, thresholds):
    page = (page_trigger or {}).get("page", "")
    if page and page not in ("/", "/country"):
        return no_update

    # Lazy import — charting.py imports this module, so a top-level import
    # back into charting would be circular. Same pattern as indicators/backtest.
    from dashboard.charting import (
        _DEFAULT_THRESHOLDS, _GROWTH_CHIP, _INFLAT_CHIP,
        _classify_regime, compute_dynamic_thresholds,
    )

    country = str(country_data or "US").upper()
    hist = load_composite_history(country=country)
    if hist.empty:
        return html.Div("No composite data — run the pipeline.",
                        style={"color": "var(--muted-color)", "padding": "20px"})

    latest_sig = load_latest_signals(country)

    g = _latest(hist, "growth_score");        g_d = _delta(hist, "growth_score")
    i = _latest(hist, "inflation_score");     i_d = _delta(hist, "inflation_score")
    g_mom = _latest(hist, "growth_momentum"); i_mom = _latest(hist, "inflation_momentum")
    conf = _latest(hist, "confidence")
    diseq = _latest(hist, "disequilibrium_score")

    # ── Thresholds (honoring dynamic mode) + chips + divergence flag ──────────
    t = dict(thresholds or _DEFAULT_THRESHOLDS)
    dyn_df = compute_dynamic_thresholds(hist, base_gz=float(t.get("gz", 0.5)),
                                        base_iz=float(t.get("iz", 0.5)))
    dynamic_on = bool(t.get("dynamic", False))
    if dynamic_on and not dyn_df.empty:
        t["gz"] = float(dyn_df["dyn_gz"].iloc[-1])
        t["iz"] = float(dyn_df["dyn_iz"].iloc[-1])
    g_chip, i_chip = _classify_regime(g, i, g_d, i_d, t)
    # Divergence is diagnostic — computed regardless of threshold mode.
    diverging = bool(dyn_df["divergence_flag"].iloc[-1]) if not dyn_df.empty else False

    as_of = pd.Timestamp(hist["as_of"].iloc[-1])
    name = _COUNTRY_NAMES.get(country, country)

    header = html.Div([
        html.Div([
            html.Span(name, style={"fontSize": "1.15rem", "fontWeight": "700",
                                   "color": "var(--font-color)", "marginRight": "10px"}),
            html.Span(f"{as_of:%b %Y}", style={"fontSize": "0.78rem",
                                               "color": "var(--muted-color)"}),
        ]),
        html.Div([
            _chip_span(f"Growth · {g_chip}", _GROWTH_CHIP.get(g_chip, "#888")),
            _chip_span(f"Inflation · {i_chip}", _INFLAT_CHIP.get(i_chip, "#888")),
            html.Span(f"confidence {conf:.0%}" if conf is not None else "confidence —",
                      style={"fontSize": "0.74rem", "color": "var(--muted-color)"}),
            html.Span(f"diseq {_fmt(diseq, '.2f')}",
                      style={"fontSize": "0.74rem", "color": "var(--muted-color)"}),
            *( [html.Span("DIVERGENCE", title="Growth and inflation have moved in opposite "
                          "directions for 3+ months — historically associated with a "
                          "policy-rate or credit-cycle shift (Ray Dalio review #23).",
                          style={"color": "#E8A317", "fontSize": "0.70rem",
                                 "fontWeight": "800", "letterSpacing": "0.06em",
                                 "border": "1px solid #E8A317", "borderRadius": "4px",
                                 "padding": "2px 8px"})] if diverging else [] ),
            *( [html.Span("DYNAMIC", style={"color": "#E8A317", "fontSize": "0.70rem",
                                            "fontWeight": "800"})] if dynamic_on else [] ),
        ], style={"display": "flex", "gap": "10px", "alignItems": "center",
                  "flexWrap": "wrap"}),
    ], style={"display": "flex", "justifyContent": "space-between",
              "alignItems": "center", "flexWrap": "wrap", "gap": "8px",
              "borderBottom": "1px solid var(--border-color)",
              "paddingBottom": "10px"})

    # ── Short-term cycle levers ───────────────────────────────────────────────
    stand = _sig(latest_sig, "credit.lending_standards")
    demand = _sig(latest_sig, "credit.loan_demand")
    rexp = _sig(latest_sig, "policy.rate_expectations")
    credit = _latest(hist, "credit_score")
    rate = _latest(hist, "rate_score")

    def _dial_sub(delta, mom):
        d = _fmt(delta) if delta is not None else "—"
        m = f"{mom:.0%} mom" if mom is not None else ""
        return f"Δ {d}  ·  {m}".strip(" · ")

    if stand.get("value") is not None:
        supply_txt = f"supply {'tightening' if float(stand['value']) > 0 else 'easing'}"
    else:
        supply_txt = "supply —"
    if demand.get("value") is not None:
        demand_txt = f"demand {float(demand['value']):+.1f}"
    else:
        demand_txt = "demand —"

    if rate is not None:
        stance = "accommodative" if rate > 0 else "restrictive"
    else:
        stance = "—"
    if rexp.get("value") is not None:
        rx = float(rexp["value"])
        rexp_txt = f"2y−funds {rx:+.2f} · pricing {'hikes' if rx > 0.1 else ('cuts' if rx < -0.1 else 'hold')}"
    else:
        rexp_txt = "2y−funds —"

    levers = html.Div([
        html.Div("Short-term cycle — the levers", style=_H),
        html.Div([
            _card("Growth", _fmt(g), _dial_sub(g_d, g_mom), "/signals/growth",
                  _GROWTH_CHIP.get(g_chip, "var(--font-color)")),
            _card("Inflation", _fmt(i), _dial_sub(i_d, i_mom), "/signals/inflation",
                  _INFLAT_CHIP.get(i_chip, "var(--font-color)")),
            _card("Credit conditions", _fmt(credit),
                  f"{supply_txt} · {demand_txt}", "/signals/credit"),
            _card("Policy stance", _fmt(rate), f"{stance} · {rexp_txt}", "/signals/rate"),
        ], style=_ROW),
    ])

    # ── Long-term debt cycle ──────────────────────────────────────────────────
    dsr = _sig(latest_sig, "credit.debt_service_ratio")
    try:
        ds_hist = load_debt_stress_history(country=country)
    except Exception:
        ds_hist = pd.DataFrame()

    if not ds_hist.empty and "stress_score" in ds_hist.columns:
        ds = ds_hist["stress_score"].dropna()
        ds_val = float(ds.iloc[-1]) if not ds.empty else None
        n_comp = ds_hist["n_components"].iloc[-1] if "n_components" in ds_hist.columns else "—"
        stress_card = _card("Debt stress", _fmt(ds_val),
                            f"{n_comp}/7 components", "/debt-stress")
    else:
        stress_card = _card("Debt stress", "—",
                            f"not built for {country} yet", "/debt-stress")

    if dsr.get("value") is not None:
        dsr_sub = f"{float(dsr['value']):.1f}% of income · {dsr.get('direction') or '—'}"
    else:
        dsr_sub = "no data for this country"

    # Long-term cycle STAGE (Phase C classifier)
    try:
        stage_hist = load_debt_cycle_stage_history(country=country)
    except Exception:
        stage_hist = pd.DataFrame()
    if not stage_hist.empty:
        labeled = stage_hist[stage_hist["stage"].notna()]
        srow = labeled.iloc[-1] if not labeled.empty else None
    else:
        srow = None
    if srow is not None:
        stage_lbl = str(srow["stage"])
        s_conf = srow.get("confidence")
        n_feat = int(srow.get("n_features") or 0)
        stage_card = _card(
            "Cycle stage", stage_lbl,
            (f"confidence {s_conf:.2f} · " if s_conf is not None and not pd.isna(s_conf) else "")
            + f"{n_feat}/5 features · {pd.Timestamp(srow['as_of']):%b %Y}",
            "/debt-stress", STAGE_COLORS.get(stage_lbl, "var(--font-color)"))
    else:
        stage_card = _card("Cycle stage", "—",
                           "no stage read yet — run the pipeline", "/debt-stress")

    longcycle = html.Div([
        html.Div("Long-term debt cycle", style=_H),
        html.Div([
            stress_card,
            _card("Debt-service ratio", _fmt(dsr.get("zscore"), "+.2f"),
                  dsr_sub + " — the earliest stress signal", "/debt-stress"),
            stage_card,
        ], style=_ROW),
    ])

    # ── Trend + big cycle ─────────────────────────────────────────────────────
    prod = _latest(hist, "productivity_score")
    prod_mom = _latest(hist, "productivity_momentum")
    if prod is not None and g is not None:
        gap = prod - g
        trend_sub = ("trend above cycle" if gap > 0.25 else
                     "cycle running ahead of trend" if gap < -0.25 else
                     "trend and cycle aligned")
    else:
        trend_sub = "single-signal read" if prod is not None else "no data"
    if prod_mom is not None:
        trend_sub += f" · {prod_mom:.0%} mom"

    # Big-cycle ORDER reads (Phase D — partial: governance/GPR feeds deferred)
    rcs = _sig(latest_sig, "order.reserve_currency_share")
    gini = _sig(latest_sig, "order.gini")
    order_bits = []
    if rcs.get("value") is not None:
        cur = {"US": "USD", "EZ": "EUR", "JP": "JPY", "GB": "GBP"}.get(country, "FX")
        d12 = rcs.get("change_12m")
        d12_txt = f" ({float(d12):+.1f}pp/yr)" if d12 is not None and not pd.isna(d12) else ""
        order_bits.append(f"{cur} reserve share {float(rcs['value']):.1f}%{d12_txt}")
    if gini.get("value") is not None:
        gini_yr = pd.Timestamp(gini["as_of"]).year if gini.get("as_of") is not None else "?"
        order_bits.append(f"Gini {float(gini['value']):.1f} ({gini_yr})")
    if order_bits:
        order_big = (f"{float(rcs['value']):.1f}%" if rcs.get("value") is not None
                     else f"{float(gini['value']):.1f}")
        order_card = _card("Big-cycle position", order_big,
                           " · ".join(order_bits) + " — governance/GPR deferred",
                           "/data-dashboard")
    else:
        order_card = _card("Big-cycle position", "planned",
                           "Phase D — internal & external order", planned=True)

    trend = html.Div([
        html.Div("Trend & big cycle", style=_H),
        html.Div([
            _card("Productivity trend", _fmt(prod), trend_sub, "/signals/productivity"),
            order_card,
        ], style=_ROW),
    ])

    # ── What changed ──────────────────────────────────────────────────────────
    from dashboard.charting import _what_changed_children
    try:
        feed = load_change_feed(country)
    except Exception:
        feed = pd.DataFrame()
    watch = html.Div([
        html.Div("What changed — biggest Z-score moves vs. prior observation", style=_H),
        html.Div(_what_changed_children(feed),
                 style={**_CARD, "flex": "none"}),
        html.Div("Every card links to its detail page. The dashed card is the "
                 "remaining planned layer (Phase D — big-cycle order).",
                 style={"fontSize": "0.68rem", "color": "var(--muted-color)",
                        "marginTop": "10px"}),
    ])

    return html.Div([header, levers, longcycle, trend, watch])

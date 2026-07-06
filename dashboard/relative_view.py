"""Cross-country / relative-cycle view (roadmap Phase E).

The diversification payoff of the whole exercise: see which economies sit at
DIFFERENT points on the three clocks (short-term regime, long-term debt-cycle
stage, big-cycle order) and whether their cycles actually move independently.

Two sections:
  E1 — side-by-side country cards: regime chips + dial scores, cycle stage,
       debt stress, productivity, and the order reads (reserve share / Gini).
  E2 — regime-correlation matrices: pairwise Pearson correlation of the
       monthly growth and inflation composite scores over the common window,
       plus a 10-year recent-window variant. Low/negative correlation =
       genuine diversification; high correlation = same cycle in disguise.

Route "/relative". Regime chips honor the configurable thresholds store
(including dynamic mode, computed per country).
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from dash import Input, Output, callback, dcc, html, no_update

from dashboard.charting_data import (
    load_composite_history,
    load_debt_cycle_stage_history,
    load_debt_stress_history,
    load_latest_signals,
)
from dashboard.command_center import STAGE_COLORS

COUNTRIES = ["US", "EZ", "GB", "JP", "KR"]      # extend as Phase 2 rollout continues
_NAMES = {"US": "🇺🇸 United States", "EZ": "🇪🇺 Euro Area", "GB": "🇬🇧 United Kingdom",
          "JP": "🇯🇵 Japan", "KR": "🇰🇷 South Korea"}

_RECENT_WINDOW_YEARS = 10           # recent-correlation window

# Ray audit ruling 2026-07-06 (Q1b): every country in the cross-country view
# is normalized on the SAME canonical rolling windows — never per-country
# spans, never the user's sidebar selection — so the comparison measures
# co-movement rather than differences in historical baselines (Korea's
# development era would otherwise distort its "normal" vs the US).
_CANON_G_COL = "growth_score_48m"       # Ray Q1c: 48m growth
_CANON_I_COL = "inflation_score_90m"    # Ray ruled 96m; 90m is the existing grid point


def _canon_col(hist: pd.DataFrame, canon: str, base: str) -> str:
    """Canonical rolling column when populated, else the full-history base."""
    return canon if canon in hist.columns and hist[canon].notna().any() else base

_CARD = {
    "background": "var(--card-bg)", "border": "1px solid var(--border-color)",
    "borderRadius": "8px", "padding": "14px 16px", "flex": "1 1 280px",
    "minWidth": "260px",
}
_LABEL = {"fontSize": "0.62rem", "textTransform": "uppercase",
          "letterSpacing": "0.08em", "color": "var(--muted-color)"}
_H = {"fontSize": "0.72rem", "textTransform": "uppercase", "letterSpacing": "0.10em",
      "color": "var(--muted-color)", "margin": "18px 0 8px", "fontWeight": "700"}


def get_layout() -> html.Div:
    return html.Div(
        html.Div(id="relative-content"),
        className="pe-2 pt-2",
        style={"maxWidth": "1250px", "margin": "0 auto"},
    )


def _chip(text: str, color: str) -> html.Span:
    return html.Span(text, style={
        "background": f"{color}26", "border": f"1px solid {color}", "color": color,
        "borderRadius": "4px", "padding": "2px 8px", "fontSize": "0.72rem",
        "fontWeight": "600", "marginRight": "6px", "whiteSpace": "nowrap",
        "display": "inline-block", "marginBottom": "4px",
    })


def _kv(label: str, value: str) -> html.Div:
    return html.Div([
        html.Span(label + " ", style={"color": "var(--muted-color)", "fontSize": "0.72rem"}),
        html.Span(value, style={"fontFamily": "monospace", "fontSize": "0.78rem",
                                "color": "var(--font-color)"}),
    ], style={"padding": "1px 0"})


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


def _fmt(v: Optional[float], spec: str = "+.2f") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return format(float(v), spec)


def _country_card(country: str, thresholds: dict) -> html.Div:
    from dashboard.charting import (
        _DEFAULT_THRESHOLDS, _GROWTH_CHIP, _INFLAT_CHIP,
        _classify_regime, compute_dynamic_thresholds,
    )

    hist = load_composite_history(country=country)
    if hist.empty:
        return html.Div([html.Div(_NAMES.get(country, country)),
                         html.Div("no data", style={"color": "var(--muted-color)"})],
                        style=_CARD)

    g_col = _canon_col(hist, _CANON_G_COL, "growth_score")
    i_col = _canon_col(hist, _CANON_I_COL, "inflation_score")
    g = _latest(hist, g_col); g_d = _delta(hist, g_col)
    i = _latest(hist, i_col); i_d = _delta(hist, i_col)

    t = dict(thresholds or _DEFAULT_THRESHOLDS)
    if t.get("dynamic"):
        dyn_input = hist[["as_of", g_col, i_col]
                         + (["credit_score"] if "credit_score" in hist.columns else [])]
        dyn_input = dyn_input.rename(columns={g_col: "growth_score", i_col: "inflation_score"})
        dyn = compute_dynamic_thresholds(dyn_input, base_gz=float(t.get("gz", 0.5)),
                                         base_iz=float(t.get("iz", 0.5)))
        if not dyn.empty:
            t["gz"] = float(dyn["dyn_gz"].iloc[-1])
            t["iz"] = float(dyn["dyn_iz"].iloc[-1])
    g_chip, i_chip = _classify_regime(g, i, g_d, i_d, t)

    # Long-term cycle stage
    try:
        stage_hist = load_debt_cycle_stage_history(country=country)
        labeled = stage_hist[stage_hist["stage"].notna()] if not stage_hist.empty else pd.DataFrame()
        stage = str(labeled.iloc[-1]["stage"]) if not labeled.empty else None
    except Exception:
        stage = None

    # Debt stress (US-only model today)
    try:
        ds_hist = load_debt_stress_history(country=country)
        ds = _latest(ds_hist, "stress_score") if not ds_hist.empty else None
    except Exception:
        ds = None

    latest_sig = load_latest_signals(country)

    def sig_val(tail: str):
        if latest_sig.empty:
            return None, None
        hit = latest_sig[latest_sig["id"].str.endswith(tail)]
        if hit.empty:
            return None, None
        return hit.iloc[0].get("value"), hit.iloc[0].get("as_of")

    rcs, _ = sig_val("order.reserve_currency_share")
    gini, gini_dt = sig_val("order.gini")
    prod = _latest(hist, "productivity_score")
    as_of = pd.Timestamp(hist["as_of"].iloc[-1])

    chips = [
        _chip(f"Growth · {g_chip}", _GROWTH_CHIP.get(g_chip, "#888")),
        _chip(f"Inflation · {i_chip}", _INFLAT_CHIP.get(i_chip, "#888")),
    ]
    if stage:
        chips.append(_chip(f"Stage · {stage}", STAGE_COLORS.get(stage, "#888")))

    order_bits = []
    if rcs is not None:
        cur = {"US": "USD", "EZ": "EUR", "JP": "JPY", "GB": "GBP"}.get(country, "FX")
        order_bits.append(f"{cur} reserves {float(rcs):.1f}%")
    if gini is not None:
        yr = pd.Timestamp(gini_dt).year if gini_dt is not None else "?"
        order_bits.append(f"Gini {float(gini):.1f} ({yr})")

    return html.Div([
        html.Div([
            html.Span(_NAMES.get(country, country),
                      style={"fontWeight": "700", "fontSize": "0.95rem",
                             "color": "var(--font-color)"}),
            html.Span(f"  {as_of:%b %Y}", style={"fontSize": "0.7rem",
                                                 "color": "var(--muted-color)"}),
        ], style={"marginBottom": "8px"}),
        html.Div(chips, style={"marginBottom": "8px"}),
        _kv("Growth Z", _fmt(g) + (f" (Δ {_fmt(g_d)})" if g_d is not None else "")),
        _kv("Inflation Z", _fmt(i) + (f" (Δ {_fmt(i_d)})" if i_d is not None else "")),
        _kv("Debt stress", _fmt(ds) if ds is not None else "— (US-only model)"),
        _kv("Productivity Z", _fmt(prod)),
        _kv("Order", " · ".join(order_bits) if order_bits else "—"),
        dcc.Link("→ command center", href="/country",
                 style={"fontSize": "0.7rem", "color": "var(--slider-accent, #E8A317)",
                        "textDecoration": "none", "display": "block", "marginTop": "8px"}),
    ], style=_CARD)


def compute_score_correlations(
    histories: dict, col: str, start: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Pairwise Pearson correlation of one composite column across countries.

    Series are aligned on month-end before correlating (as_of days differ per
    country). Returns a countries×countries DataFrame; NaN where the common
    window has fewer than 24 monthly observations.
    """
    aligned = {}
    for cc, hist in histories.items():
        if hist.empty or col not in hist.columns:
            continue
        s = hist.set_index("as_of")[col].dropna()
        if start is not None:
            s = s[s.index >= start]
        s.index = s.index.to_period("M")
        aligned[cc] = s[~s.index.duplicated(keep="last")]
    ccs = list(aligned)
    out = pd.DataFrame(index=ccs, columns=ccs, dtype=float)
    for a in ccs:
        for b in ccs:
            if a == b:
                out.loc[a, b] = 1.0
                continue
            joined = pd.concat([aligned[a], aligned[b]], axis=1, join="inner").dropna()
            out.loc[a, b] = joined.iloc[:, 0].corr(joined.iloc[:, 1]) if len(joined) >= 24 else float("nan")
    return out


def _corr_heatmap(corr: pd.DataFrame, title: str, theme_name: str) -> dcc.Graph:
    from dashboard.themes import figure_layout
    fig = go.Figure(go.Heatmap(
        z=corr.values.astype(float),
        x=list(corr.columns), y=list(corr.index),
        zmin=-1, zmax=1,
        colorscale=[[0.0, "#4C9BE8"], [0.5, "#2b2b2b"], [1.0, "#E8734C"]],
        text=[[("" if pd.isna(v) else f"{v:+.2f}") for v in row] for row in corr.values],
        texttemplate="%{text}",
        textfont={"size": 13, "family": "monospace"},
        hovertemplate="%{y} × %{x}: %{z:+.2f}<extra></extra>",
        showscale=False,
    ))
    layout = figure_layout(theme_name, title)
    layout["margin"] = {"l": 50, "r": 20, "t": 40, "b": 30}
    layout["height"] = 260
    fig.update_layout(**layout)
    fig.update_yaxes(autorange="reversed")
    return dcc.Graph(figure=fig, config={"displayModeBar": False},
                     style={"flex": "1 1 300px", "minWidth": "280px"})


@callback(
    Output("relative-content", "children"),
    [Input("page-trigger", "data"),
     Input("theme-store", "data"),
     Input("regime-threshold-store", "data")],
    prevent_initial_call=False,
)
def render_relative_view(page_trigger, theme_name, thresholds):
    page = (page_trigger or {}).get("page", "")
    if page and page != "/relative":
        return no_update
    theme_name = theme_name or "carbon"

    cards = [_country_card(cc, thresholds) for cc in COUNTRIES]

    histories = {cc: load_composite_history(country=cc) for cc in COUNTRIES}
    recent_start = pd.Timestamp.today() - pd.DateOffset(years=_RECENT_WINDOW_YEARS)

    # Q1b: correlations use the same canonical rolling window for every
    # country (fall back to full-history only if a rolling column is empty
    # for every country, which would make the matrix trivially empty).
    def _corr_col(canon: str, base: str) -> str:
        return canon if any(
            canon in h.columns and h[canon].notna().any() for h in histories.values()
        ) else base

    gc = _corr_col(_CANON_G_COL, "growth_score")
    ic = _corr_col(_CANON_I_COL, "inflation_score")
    g_lbl = "48m window" if gc == _CANON_G_COL else "full history"
    i_lbl = "90m window" if ic == _CANON_I_COL else "full history"
    heatmaps_full = [
        _corr_heatmap(compute_score_correlations(histories, gc),
                      f"Growth score ({g_lbl}) — full common history", theme_name),
        _corr_heatmap(compute_score_correlations(histories, ic),
                      f"Inflation score ({i_lbl}) — full common history", theme_name),
    ]
    heatmaps_recent = [
        _corr_heatmap(compute_score_correlations(histories, gc, recent_start),
                      f"Growth score ({g_lbl}) — last {_RECENT_WINDOW_YEARS}y", theme_name),
        _corr_heatmap(compute_score_correlations(histories, ic, recent_start),
                      f"Inflation score ({i_lbl}) — last {_RECENT_WINDOW_YEARS}y", theme_name),
    ]

    return html.Div([
        html.Div("Where each economy sits — three clocks side by side", style=_H),
        html.Div(cards, style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),

        html.Div("Cycle correlation — is that diversification real?", style=_H),
        html.Div("Pairwise correlation of the monthly composite scores, every country "
                 "normalized on the SAME canonical rolling windows (48m growth / 90m "
                 "inflation — Ray audit ruling: uniform windows make the matrix measure "
                 "co-movement, not baseline differences). Blue (negative) = economies "
                 "moving oppositely — real diversification. Orange (positive) = the same "
                 "cycle in disguise. The recent window matters more than the full history "
                 "for forward-looking allocation questions.",
                 style={"fontSize": "0.75rem", "color": "var(--muted-color)",
                        "marginBottom": "8px", "maxWidth": "820px"}),
        html.Div(heatmaps_full, style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
        html.Div(heatmaps_recent, style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
        html.Div("Interpretation note: composite scores are Z-scores vs each country's own "
                 "history, so correlation here measures cycle synchronization, not return "
                 "co-movement. Allocation decisions belong to the separate Allocation Layer.",
                 style={"fontSize": "0.68rem", "color": "var(--muted-color)",
                        "marginTop": "10px"}),
    ])

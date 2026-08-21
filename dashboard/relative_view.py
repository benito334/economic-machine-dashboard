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

COUNTRIES = ["US", "EZ", "GB", "JP", "KR", "CN", "IN", "DE", "LU", "BR", "CA", "AU", "MX", "ID"]
_NAMES = {"US": "🇺🇸 United States", "EZ": "🇪🇺 Euro Area", "GB": "🇬🇧 United Kingdom",
          "JP": "🇯🇵 Japan", "KR": "🇰🇷 South Korea", "CN": "🇨🇳 China",
          "IN": "🇮🇳 India", "DE": "🇩🇪 Germany", "LU": "🇱🇺 Luxembourg",
          "BR": "🇧🇷 Brazil", "CA": "🇨🇦 Canada", "AU": "🇦🇺 Australia",
          "MX": "🇲🇽 Mexico", "ID": "🇮🇩 Indonesia"}

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


# ── Recent clock-change notes ─────────────────────────────────────────────────
# When a country's clock flips (Growth/Inflation chip or debt-cycle stage), the
# card shows a small "changed" note for ~a month so the flip is visible without
# having to remember last month's reads. Derived from history at render time —
# the change date is the as_of of the FIRST snapshot carrying the current label.
_CHANGE_NOTE_DAYS_CHIP = 30    # TUNABLE — monthly clocks
_CHANGE_NOTE_DAYS_STAGE = 45   # TUNABLE — quarterly stage surfaces with a lag
_CHANGE_LOOKBACK_ROWS = 8      # how many recent snapshots to scan per clock


def _label_run_start(labels: list) -> tuple:
    """For [(as_of, label), …] return (current, previous, started_at).

    `previous` is None when the whole window carries the current label
    (no change visible within the lookback).
    """
    if not labels:
        return None, None, None
    cur = labels[-1][1]
    started = labels[-1][0]
    prev = None
    for ts, v in reversed(labels[:-1]):
        if v != cur:
            prev = v
            break
        started = ts
    return cur, prev, started


def _chip_label_history(hist, g_col: str, i_col: str, t: dict, dyn) -> tuple:
    """Classify the last few composite rows → ([(as_of, g_chip)…], [(as_of, i_chip)…]).

    Uses per-row dynamic thresholds when available so past rows are judged the
    way the dashboard judged them, not by today's thresholds.
    """
    from dashboard.charting import _classify_regime
    total = len(hist)
    dg = hist[g_col].diff()
    di = hist[i_col].diff()
    g_out, i_out = [], []
    for pos in range(max(1, total - _CHANGE_LOOKBACK_ROWS), total):
        g, i = hist[g_col].iloc[pos], hist[i_col].iloc[pos]
        if pd.isna(g) or pd.isna(i):
            continue
        tt = dict(t)
        if dyn is not None and len(dyn) == total:
            tt["gz"] = float(dyn["dyn_gz"].iloc[pos])
            tt["iz"] = float(dyn["dyn_iz"].iloc[pos])
        gd, idd = dg.iloc[pos], di.iloc[pos]
        gc, ic = _classify_regime(
            float(g), float(i),
            None if pd.isna(gd) else float(gd),
            None if pd.isna(idd) else float(idd), tt)
        ts = pd.Timestamp(hist["as_of"].iloc[pos])
        g_out.append((ts, gc))
        i_out.append((ts, ic))
    return g_out, i_out


def _recent_change_notes(g_labels, i_labels, stage_labels,
                         now: Optional[pd.Timestamp] = None) -> list:
    """Build 'clock changed' note strings for flips within the display window."""
    now = now or pd.Timestamp.today()
    notes = []
    for labels, name, window in ((g_labels, "Growth", _CHANGE_NOTE_DAYS_CHIP),
                                 (i_labels, "Inflation", _CHANGE_NOTE_DAYS_CHIP),
                                 (stage_labels, "Stage", _CHANGE_NOTE_DAYS_STAGE)):
        cur, prev, started = _label_run_start(labels)
        if prev is None or started is None:
            continue
        if (now - pd.Timestamp(started)).days <= window:
            notes.append(f"{name} clock → {cur} (was {prev}) · {pd.Timestamp(started):%b %d}")
    return notes


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
    dyn = None
    if t.get("dynamic"):
        dyn_input = hist[["as_of", g_col, i_col]
                         + (["credit_score"] if "credit_score" in hist.columns else [])]
        dyn_input = dyn_input.rename(columns={g_col: "growth_score", i_col: "inflation_score"})
        dyn = compute_dynamic_thresholds(dyn_input, base_gz=float(t.get("gz", 0.5)),
                                         base_iz=float(t.get("iz", 0.5)))
        if dyn.empty:
            dyn = None
        else:
            t["gz"] = float(dyn["dyn_gz"].iloc[-1])
            t["iz"] = float(dyn["dyn_iz"].iloc[-1])
    g_chip, i_chip = _classify_regime(g, i, g_d, i_d, t)

    # Long-term cycle stage
    try:
        stage_hist = load_debt_cycle_stage_history(country=country)
        labeled = stage_hist[stage_hist["stage"].notna()] if not stage_hist.empty else pd.DataFrame()
        stage_row = labeled.iloc[-1] if not labeled.empty else None
        stage = str(stage_row["stage"]) if stage_row is not None else None
        # Ray ruling 2026-07-06: an early-warning flag independent of the
        # headline stage — surfaced as a ⚠ suffix on the stage chip.
        squeeze_flag = bool(stage_row.get("sovereign_squeeze")) if stage_row is not None else False
        # Ray Dalio consult 2026-08-19: debt-growth-vs-income-growth spread —
        # a distinct gauge from Sovereign Squeeze, kept as its own chip rather
        # than folded into the same ⚠ suffix (this repo has a history of
        # badges conflating unrelated signals into one alarm).
        spread_flag = stage_row.get("debt_income_spread_flag") if stage_row is not None else None
    except Exception:
        stage, squeeze_flag, spread_flag = None, False, None

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
        label = f"Stage · {stage}" + (" ⚠" if squeeze_flag else "")
        chips.append(_chip(label, STAGE_COLORS.get(stage, "#888")))
    if spread_flag in ("warning", "critical"):
        chips.append(_chip(f"Debt/Income spread · {spread_flag}",
                           "#E8A317" if spread_flag == "warning" else "#E5484D"))

    # Recent clock-change notes (~30d chips / ~45d stage)
    try:
        g_labels, i_labels = _chip_label_history(hist, g_col, i_col, t, dyn)
        stage_labels = ([
            (pd.Timestamp(r["as_of"]), str(r["stage"]))
            for _, r in labeled.tail(_CHANGE_LOOKBACK_ROWS).iterrows()
        ] if stage else [])
        change_notes = _recent_change_notes(g_labels, i_labels, stage_labels)
    except Exception:
        change_notes = []
    notes_block = ([html.Div(
        [html.Div(f"🔄 {n}", style={"fontSize": "0.68rem", "color": "#F4C842",
                                    "lineHeight": "1.5"}) for n in change_notes],
        style={"borderLeft": "2px solid #E8A317", "paddingLeft": "7px",
               "margin": "0 0 8px 0",
               "background": "rgba(232,163,23,0.06)", "borderRadius": "0 4px 4px 0",
               "padding": "3px 7px"},
    )] if change_notes else [])

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
        *notes_block,
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


# Countries with a live OECD/IMF REER unit-labor-cost-based series on FRED
# (verified 2026-08-19 — CCRETT02{cc}Q661N). Not available for CN/IN/BR/ID;
# shown as a documented gap rather than silently omitted (house convention:
# no silent caps).
_ULC_COUNTRIES = ["US", "EZ", "DE", "GB", "JP", "KR", "MX", "CA", "AU", "LU"]


def _competitiveness_table(thresholds: dict) -> html.Div:
    """Relative Cycles competitiveness ranking (Ray Dalio consult 2026-08-19):
    each country's `growth.relative_ulc` signal is the YoY %-change of an
    already trade-weighted, FX-adjusted REER unit-labor-cost index, so the
    Z-score/direction is directly comparable across countries without a
    cross-country normalization scheme — rising = losing competitiveness
    (unit labor costs increasing relative to trading partners), falling =
    gaining."""
    rows = []
    for cc in _ULC_COUNTRIES:
        sig = load_latest_signals(cc)
        if sig.empty:
            continue
        hit = sig[sig["id"].str.endswith("growth.relative_ulc")]
        if hit.empty:
            continue
        r = hit.iloc[0]
        z = r.get("zscore")
        val = r.get("value")
        as_of = r.get("as_of")
        if z is None or (isinstance(z, float) and math.isnan(z)):
            continue
        read = "gaining" if z < -0.25 else "losing" if z > 0.25 else "flat"
        color = "#5CBA8A" if read == "gaining" else "#E5484D" if read == "losing" else "#888"
        rows.append((cc, float(z), float(val) if val is not None else None, as_of, read, color))

    rows.sort(key=lambda t: t[1])   # most-improving (lowest Z) first

    body = [html.Tr([
        html.Td(_NAMES.get(cc, cc), style={"padding": "5px 10px"}),
        html.Td(f"{val:+.1%}" if val is not None else "—",
               style={"padding": "5px 10px", "textAlign": "right", "fontFamily": "monospace"}),
        html.Td(f"{z:+.2f}",
               style={"padding": "5px 10px", "textAlign": "right", "fontFamily": "monospace"}),
        html.Td(read, style={"padding": "5px 10px", "textAlign": "center", "color": color,
                             "fontWeight": "600", "textTransform": "uppercase",
                             "fontSize": "0.7rem"}),
        html.Td(f"{pd.Timestamp(as_of):%b %Y}" if as_of is not None else "—",
               style={"padding": "5px 10px", "textAlign": "right", "color": "var(--muted-color)",
                     "fontSize": "0.72rem"}),
    ]) for cc, z, val, as_of, read, color in rows]

    missing = [cc for cc in COUNTRIES if cc not in _ULC_COUNTRIES]
    footer = html.Div(
        f"No free REER unit-labor-cost series for {', '.join(_NAMES.get(cc, cc) for cc in missing)} "
        "— not shown rather than proxied.",
        style={"fontSize": "0.68rem", "color": "var(--muted-color)", "marginTop": "8px"},
    )

    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Country", style={"padding": "5px 10px", "textAlign": "left"}),
            html.Th("YoY Δ ULC (REER)", style={"padding": "5px 10px", "textAlign": "right"}),
            html.Th("Z-score", style={"padding": "5px 10px", "textAlign": "right"}),
            html.Th("Reading", style={"padding": "5px 10px", "textAlign": "center"}),
            html.Th("As of", style={"padding": "5px 10px", "textAlign": "right"}),
        ], style={"fontSize": "0.68rem", "textTransform": "uppercase",
                  "letterSpacing": "0.06em", "color": "var(--muted-color)",
                  "borderBottom": "1px solid var(--border-color)"})),
        html.Tbody(body),
    ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.82rem"})

    return html.Div([table, footer], style={
        "background": "var(--card-bg)", "border": "1px solid var(--border-color)",
        "borderRadius": "8px", "padding": "14px 16px", "marginBottom": "8px",
    })


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

        html.Div("Relative competitiveness — unit labor cost vs. trading partners", style=_H),
        html.Div("Ray Dalio's competitiveness gauge (2026-08-19 consult): the OECD/IMF REER "
                 "unit-labor-cost-based index is already trade-weighted and FX-adjusted, so its "
                 "YoY % change is directly comparable across countries — rising (losing) means "
                 "a country's labor costs are increasing relative to its trading partners; "
                 "falling (gaining) means the reverse. Ranked most-improving to most-eroding.",
                 style={"fontSize": "0.75rem", "color": "var(--muted-color)",
                        "marginBottom": "8px", "maxWidth": "820px"}),
        _competitiveness_table(thresholds),

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

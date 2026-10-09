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
from dashboard.shared_components import RED

# Stage chip colors — shared with the Debt Stress page timeline.
STAGE_COLORS = {
    "leveraging": "#4C9BE8", "squeeze": "#E8734C",
    "deleveraging": "#B07FD4", "reflation": "#5CBA8A", "neutral": "#888888",
}

_COUNTRY_NAMES = {"US": "United States", "EZ": "Euro Area", "GB": "United Kingdom",
                  "JP": "Japan", "KR": "South Korea", "CN": "China",
                  "IN": "India", "DE": "Germany", "LU": "Luxembourg",
                  "BR": "Brazil", "CA": "Canada", "AU": "Australia",
                  "MX": "Mexico", "ID": "Indonesia"}

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


_REGIME_CONFIDENCE_CUTOFF = 0.70  # coverage-audit Phase B's suggested threshold


def _conf_str(c: dict) -> str:
    conf = c.get("confidence")
    if conf is None:
        return "—"
    return f"{conf:.0%}" + (" (uncertain)" if conf < _REGIME_CONFIDENCE_CUTOFF else "")


def _conf_row_color(g_conf: dict, i_conf: dict) -> str:
    for c in (g_conf, i_conf):
        if c.get("confidence") is not None and c["confidence"] < _REGIME_CONFIDENCE_CUTOFF:
            return RED
    return "var(--muted-color)"


_VERDICT_SYMBOL = {"AGREE": "✓", "PARTIAL": "~", "CONTRADICT": "✗"}
_VERDICT_RANK = {"CONTRADICT": 2, "PARTIAL": 1, "AGREE": 0}  # worse wins the row color


def _validator_badge(rollup: Optional[tuple]):
    """Small clickable pill summarizing the external-validator rollup for
    both axes — None (omit entirely) when there's nothing to show yet."""
    if rollup is None:
        return None
    from dashboard.shared_components import VERDICT_COLOR
    g, i = rollup
    g_sym = _VERDICT_SYMBOL.get(g["verdict"], "—")
    i_sym = _VERDICT_SYMBOL.get(i["verdict"], "—")
    worst = max((g["verdict"], i["verdict"]), key=lambda v: _VERDICT_RANK.get(v, -1),
                default=None)
    color = VERDICT_COLOR.get(worst, "var(--muted-color)")
    return dcc.Link(
        html.Span(
            f"validated G {g_sym} · I {i_sym}",
            title="Independent FRED-benchmark cross-check against the chip "
                  "(CFNAI, trimmed-mean CPI/PCE, GDPNow, Sahm rule, ...) — "
                  "AGREE/PARTIAL/CONTRADICT per axis, click for detail. "
                  "docs/external_validators_plan.md, 2026-10-03.",
            style={"fontSize": "0.74rem", "color": color, "border": f"1px dashed {color}80",
                   "borderRadius": "4px", "padding": "2px 8px"},
        ),
        href="/validator-audit", style={"textDecoration": "none"},
    )


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


_ANCHOR_COLOR = {"Above Target": "#E8734C", "At Target": "#4C9BE8",
                 "Below Target": "#9B7CE8"}


def _anchor_chip(anchor: Optional[dict]):
    """Primary inflation chip: distance from the central-bank target.

    Ray, 2026-10-03: "Inflation has a target... That's the anchor." Rendered
    ahead of and larger than the relative read so the hierarchy is unambiguous —
    "If you just show two numbers, people will get confused."
    """
    if not anchor or anchor["anchor"].gap_pp is None:
        return _chip_span("Inflation · no target read", "#888")
    a = anchor["anchor"]
    label = f"Inflation · {a.label} {a.gap_pp:+.2f}pp"
    bits = [f"{a.inflation_pct:.2f}% vs {a.target_pct:.1f}% target "
            f"(via {a.gap_series}, {a.as_of})", f"gap {a.direction}"]
    if a.is_stale or (a.age_months or 0) > 4:
        bits.append(f"SOURCE {a.age_months}m old")
    sp = anchor.get("split") or {}
    if sp.get("impulse") is not None and sp.get("persistence") is not None:
        bits.append(f"impulse {sp['impulse']:+.2f} / persistence {sp['persistence']:+.2f}")
    else:
        # Ray 2026-10-03 Ruling 2: inflation is a two-part machine, and the
        # half-year lead of a flexible-price index is "a feature, not a bug" --
        # but it means such an index is LEADING, not a current-state gauge.
        # Ten of fourteen countries have no sticky member at all, and saying
        # nothing left them looking like the US's core-PCE-weighted read.
        try:
            from indicators.inflation_anchor import basket_split_composition
            comp = basket_split_composition(a.country)
        except Exception:
            comp = {}
        if comp and not comp.get("has_both"):
            bits.append("no sticky component — flexible-price only, so this "
                        "leads the trend rather than measuring it")
    return _chip_span(label, _ANCHOR_COLOR.get(a.label, "#888"), title=" · ".join(bits))


def _card(label: str, big: str, sub: str, href: Optional[str] = None,
          big_color: str = "var(--font-color)", planned: bool = False,
          data_note: Optional[dict] = None) -> html.Div:
    body = [
        html.Div(label, style=_LABEL),
        html.Div(big, style={**_BIG, "color": big_color}),
        html.Div(sub, style=_SUB),
    ]
    if data_note:
        body.append(html.Div([
            html.Span(data_note["grade"], style={
                "display": "inline-block", "minWidth": "14px", "padding": "0 4px",
                "borderRadius": "3px", "background": data_note["hex"], "color": "#fff",
                "fontSize": "0.58rem", "fontWeight": "700", "textAlign": "center"}),
            html.Span(f" data · {data_note['caveat']}", style={
                "fontSize": "0.64rem", "color": "var(--muted-color)"}),
        ], style={"marginTop": "5px"}, title=data_note.get("title", "")))
    style = _CARD_PLANNED if planned else _CARD
    if href:
        return dcc.Link(html.Div(body, style=style), href=href,
                        style={"textDecoration": "none", "display": "flex", "flex": "1 1 170px"})
    return html.Div(body, style=style)


def _chip_span(text: str, color: str, secondary: bool = False,
               title: str = "") -> html.Span:
    """A regime chip. `secondary` renders it visibly subordinate.

    Ray 2026-10-03: show the anchor and the relative read together, but "make it
    clear which is the anchor" — so the secondary chip is smaller, lighter and
    outline-only rather than a peer badge.
    """
    style = {
        "background": "transparent" if secondary else f"{color}26",
        "border": f"1px {'dashed' if secondary else 'solid'} {color}{'80' if secondary else ''}",
        "color": color, "borderRadius": "4px",
        "padding": "2px 8px" if secondary else "3px 10px",
        "fontSize": "0.68rem" if secondary else "0.78rem",
        "fontWeight": "500" if secondary else "600",
        "opacity": "0.75" if secondary else "1",
        "whiteSpace": "nowrap",
    }
    kw = {"title": title} if title else {}
    return html.Span(text, style=style, **kw)


def chip_direction_agreement(hist: pd.DataFrame, force: str) -> Optional[float]:
    """Chip Direction Agreement for the latest month — READ, not recomputed.

    Ray audit ruling 2026-07-06 (Q3): confidence is measured against the chips
    themselves — the heading is the sign of the composite's MoM delta, and the
    metric is the share of the basket moving with it.

    This used to recompute the number here from `latest_signals`, and drifted
    from the chip it describes in two ways (found 2026-10-07): it measured every
    signal carrying force=='growth' (19 for the US) rather than the 12 that
    actually build the composite, and it never flipped `invert` signals, so a
    FALLING unemployment rate counted as disagreeing with a RISING growth chip.
    The value is now computed once in the pipeline over the same basket the
    score uses (indicators/composites.py) and simply read here, so the screen
    and the stored column cannot say different things.
    """
    col = f"{force}_dir_agreement"
    if hist is None or hist.empty or col not in hist.columns:
        return None
    s = hist[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None


@callback(
    Output("cc-content", "children"),
    [Input("country-store", "data"),
     Input("page-trigger", "data"),
     Input("regime-threshold-store", "data"),
     Input("zscore-window-store", "data"),
     Input("inflation-window-store", "data"),
     Input("cc-learn-dismissed", "data")],
    prevent_initial_call=False,
)
def render_command_center(country_data, page_trigger, thresholds,
                          zscore_window=48, inflation_window=90,
                          learn_dismissed=False):
    page = (page_trigger or {}).get("page", "")
    if page and page not in ("/", "/country"):
        return no_update

    # Lazy import — charting.py imports this module, so a top-level import
    # back into charting would be circular. Same pattern as indicators/backtest.
    from dashboard.charting import (
        _DEFAULT_THRESHOLDS, _FORCE_WINDOW_COL, _GROWTH_CHIP, _GROWTH_MOMENTUM_STATE,
        _INFLAT_CHIP, _growth_breadth_state,
        _INFLATION_WINDOW_COL, _classify_regime, compute_dynamic_thresholds,
        gap_at as _gap_at,
        compute_regime_confidence, resolve_thresholds, thr,
    )
    from indicators.inflation_anchor import gap_series as _gap_series

    country = str(country_data or "US").upper()
    hist = load_composite_history(country=country)
    if hist.empty:
        return html.Div("No composite data — run the pipeline.",
                        style={"color": "var(--muted-color)", "padding": "20px"})

    latest_sig = load_latest_signals(country)

    # ── Data confidence (per-country + per-force) ─────────────────────────────
    from dashboard import data_score as _ds
    dscore = _ds.country_score(country)

    def _force_note(force: str) -> Optional[dict]:
        fi = (dscore or {}).get("forces", {}).get(force)
        if not fi:
            return None
        return {"grade": fi["grade"], "hex": fi["hex"],
                "caveat": _ds.force_caveat(fi),
                "title": "Data confidence for this force — coverage, freshness "
                         "and proxy reliance. A read on few/stale/proxy signals "
                         "is lower-confidence."}

    # ── Window selection (Ray audit ruling 2026-07-06, Q1a: the front door
    # honors the user's sidebar windows; canonical defaults 48m/90m) ──────────
    g_sfx = _FORCE_WINDOW_COL.get(int(zscore_window or 0))
    i_sfx = _INFLATION_WINDOW_COL.get(int(inflation_window or 0))

    def _usable(col: str) -> bool:
        return col in hist.columns and hist[col].notna().any()

    g_col = f"growth_score_{g_sfx}" if g_sfx and _usable(f"growth_score_{g_sfx}") else "growth_score"
    i_col = f"inflation_score_{i_sfx}" if i_sfx and _usable(f"inflation_score_{i_sfx}") else "inflation_score"
    win_label = (f"{zscore_window}m" if g_col != "growth_score" else "full") + " / " + \
                (f"{inflation_window}m" if i_col != "inflation_score" else "full")

    g = _latest(hist, g_col);                 g_d = _delta(hist, g_col)
    i = _latest(hist, i_col);                 i_d = _delta(hist, i_col)
    g_mom = _latest(hist, "growth_breadth"); i_mom = _latest(hist, "inflation_breadth")
    diseq = _latest(hist, "disequilibrium_score")

    # Chip Direction Agreement (replaces the legacy quadrant-based confidence)
    g_agree = chip_direction_agreement(hist, "growth")
    i_agree = chip_direction_agreement(hist, "inflation")

    # ── Thresholds (honoring dynamic mode) + chips + divergence flag ──────────
    t = resolve_thresholds(thresholds)
    dyn_input = hist[["as_of", g_col, i_col] + (["credit_score"] if "credit_score" in hist.columns else [])]
    dyn_input = dyn_input.rename(columns={g_col: "growth_score", i_col: "inflation_score"})
    dyn_df = compute_dynamic_thresholds(dyn_input, base_gz=float(t["gz"]),
                                        base_iz=float(t["iz"]))
    dynamic_on = bool(t["dynamic"])
    if dynamic_on and not dyn_df.empty:
        t["gz"] = float(dyn_df["dyn_gz"].iloc[-1])
        t["iz"] = float(dyn_df["dyn_iz"].iloc[-1])
    # Sustained-Z filter (Ray 2026-10-03): pass the windowed score history so the
    # Z leg must have held for N consecutive months, not just this one.
    # Inflation chip is target-anchored (Ray 2026-10-03 Ruling 1): the gate is
    # distance from the central bank's target, not distance from its own norm.
    _gaps = _gap_series(country)
    _gap, _gap_hist = _gap_at(_gaps, hist["as_of"].iloc[-1])
    g_chip, i_chip = _classify_regime(g, i, g_d, i_d, t,
                                      g_history=hist[g_col], i_history=hist[i_col],
                                      i_gap=_gap, i_gap_history=_gap_hist)
    # Momentum is no longer a gate on the growth chip (2026-10-06) — it
    # describes what is happening inside the regime, shown beside the chip.
    g_mom_state = _growth_breadth_state(g_chip, g, g_d, t)

    # Probabilistic regime confidence (coverage-audit Phase B, 2026-10-03):
    # empirical frequency that a reading like today's actually held into the
    # next month, historically. A complement to the chip, never a
    # replacement — g_chip/i_chip above are unchanged by this.
    g_conf = compute_regime_confidence(dyn_input, dynamic_on, t, "growth", _gaps)
    i_conf = compute_regime_confidence(dyn_input, dynamic_on, t, "inflation", _gaps)

    # External validator rollup (docs/external_validators_plan.md, 2026-10-03):
    # independent FRED-benchmark cross-check against the chip — a different
    # kind of confirmation than chip agreement/persistence above (outside
    # sources, not our own basket's internal agreement). US-only, since the
    # benchmark panel (CFNAI, trimmed-mean CPI/PCE, ...) is US-specific data.
    validator_rollup = None
    if country == "US":
        from dashboard.charting_data import load_validator_verdicts
        from dashboard.shared_components import summarize_validator_axis
        vdf = load_validator_verdicts("US")
        if not vdf.empty:
            validator_rollup = (
                summarize_validator_axis(vdf[vdf["axis"] == "growth"].to_dict("records")),
                summarize_validator_axis(vdf[vdf["axis"] == "inflation"].to_dict("records")),
            )

    # ── Inflation anchored to the target (Ray ruling 2026-10-03) ─────────────
    # "The main chip should be the distance from target. That's the number that
    #  matters for policy and markets. But you can also show a relative Z-score
    #  as a secondary read... you want to make it clear which is the anchor."
    # The relative chip stays, demoted to the secondary slot — a Z-score against
    # a 90-month window that is ~70% post-2021 shock said "below its own norm"
    # in the week the Fed hiked (docs/audits/dalio_audit/US_2026-10.md).
    try:
        from indicators.inflation_anchor import full_read as _anchor_full
        _anchor = _anchor_full(country)
    except Exception as exc:  # pragma: no cover - never take the page down
        logger.warning("[command_center] inflation anchor unavailable: %s", exc)
        _anchor = None
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
            *([html.Span(
                g_mom_state,
                title=f"Growth momentum is {_GROWTH_MOMENTUM_STATE[g_mom_state]}. The chip "
                      "itself is set by the LEVEL of the growth score; this says whether that "
                      "level is still building. Validated against NBER recession dating "
                      "(2026-10-06) — every month above the level gate sits outside a "
                      "recession, accelerating or not.",
                style={"fontSize": "0.68rem", "color": "var(--muted-color)",
                       "marginRight": "10px", "cursor": "help"},
            )] if g_mom_state else []),
            _anchor_chip(_anchor),
            _chip_span(f"vs own history · {i_chip}",
                       _INFLAT_CHIP.get(i_chip, "#888"), secondary=True),
            html.Span(
                "chip agreement "
                + (f"G {g_agree:.0%}" if g_agree is not None else "G —")
                + " · "
                + (f"I {i_agree:.0%}" if i_agree is not None else "I —"),
                title="Chip Direction Agreement — % of each force's signals moving "
                      "in the same direction as its chip's heading (Ray audit "
                      "2026-07-06; replaces the legacy quadrant-based confidence).",
                style={"fontSize": "0.74rem", "color": "var(--muted-color)"}),
            html.Span(
                "persistence "
                + f"G {_conf_str(g_conf)}" + " · " + f"I {_conf_str(i_conf)}",
                title="Probabilistic regime confidence — the empirical frequency "
                      "that a reading carrying today's chip label has historically "
                      "held into the following month (coverage-audit Phase B, "
                      "2026-10-03). A complement to the chip above, not a "
                      "replacement — the chip itself is unchanged by this; "
                      "'(uncertain)' flags below the audit's suggested ~70% cutoff. "
                      "'—' on Transition, which makes no persistence claim.",
                style={"fontSize": "0.74rem", "color": _conf_row_color(g_conf, i_conf)}),
            *([_validator_badge(validator_rollup)] if validator_rollup else []),
            html.Span(f"diseq {_fmt(diseq, '.2f')}",
                      style={"fontSize": "0.74rem", "color": "var(--muted-color)"}),
            html.Span(f"window {win_label}",
                      title="Z-score lookback windows (growth / inflation) from the "
                            "sidebar sliders — canonical defaults 48m / 90m.",
                      style={"fontSize": "0.70rem", "color": "var(--muted-color)"}),
            *( [html.Span("DIVERGENCE", title="Growth and inflation have moved in opposite "
                          "directions for 3+ months — historically associated with a "
                          "policy-rate or credit-cycle shift (Ray Dalio review #23).",
                          style={"color": "#E8A317", "fontSize": "0.70rem",
                                 "fontWeight": "800", "letterSpacing": "0.06em",
                                 "border": "1px solid #E8A317", "borderRadius": "4px",
                                 "padding": "2px 8px"})] if diverging else [] ),
            *( [html.Span("DYNAMIC", style={"color": "#E8A317", "fontSize": "0.70rem",
                                            "fontWeight": "800"})] if dynamic_on else [] ),
            *( [html.Span([
                    html.Span("Data ", style={"fontSize": "0.70rem",
                                              "color": "var(--muted-color)"}),
                    html.Span(dscore["overall"]["grade"], style={
                        "display": "inline-block", "minWidth": "15px", "padding": "0 5px",
                        "borderRadius": "4px", "background": dscore["overall"]["hex"],
                        "color": "#fff", "fontSize": "0.66rem", "fontWeight": "700",
                        "textAlign": "center"}),
                ], title=_ds.breakdown_text(dscore), style={"cursor": "help"})]
               if dscore else [] ),
        ], style={"display": "flex", "gap": "10px", "alignItems": "center",
                  "flexWrap": "wrap"}),
    ], style={"display": "flex", "justifyContent": "space-between",
              "alignItems": "center", "flexWrap": "wrap", "gap": "8px",
              "borderBottom": "1px solid var(--border-color)",
              "paddingBottom": "10px"})

    # ── Learn-to-read highlight (points newcomers at the Guide + Methodology) ──
    _learn_link = {
        "display": "inline-flex", "alignItems": "center", "gap": "5px",
        "textDecoration": "none", "fontSize": "0.8rem", "fontWeight": "700",
        "padding": "5px 12px", "borderRadius": "6px", "whiteSpace": "nowrap",
    }
    learn = html.Div([
        html.Span("🎓", style={"fontSize": "1.35rem", "lineHeight": "1"}),
        html.Div([
            html.Div("New to this? Learn to read the dashboard the Ray Dalio way.",
                     style={"fontSize": "0.86rem", "fontWeight": "700",
                            "color": "var(--font-color)"}),
            html.Div([
                html.Span("The ", ),
                html.B("User Guide"),
                html.Span(" is a hands-on walkthrough that teaches the framework on "),
                html.B(f"{_COUNTRY_NAMES.get(country, country)}'s live data"),
                html.Span(" — every lesson shows real current numbers. The "),
                html.B("Methodology"),
                html.Span(" page shows exactly how each number is built."),
            ], style={"fontSize": "0.76rem", "color": "var(--muted-color)",
                      "marginTop": "3px", "lineHeight": "1.5"}),
        ], style={"flex": "1 1 320px", "minWidth": "260px"}),
        html.Div([
            dcc.Link(["🎓 Open the User Guide ", html.Span("→")], href="/guide",
                     style={**_learn_link, "background": "var(--slider-accent, #E8A317)",
                            "color": "#1a1a1a"}),
            dcc.Link(["📖 Methodology ", html.Span("→")], href="/methodology",
                     style={**_learn_link, "color": "var(--font-color)",
                            "border": "1px solid var(--border-color)"}),
        ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap",
                  "alignItems": "center"}),
        html.Button("✕", id="cc-learn-close", title="Dismiss (won't show again)",
                    n_clicks=0, style={
                        "background": "transparent", "border": "none",
                        "color": "var(--muted-color)", "cursor": "pointer",
                        "fontSize": "0.9rem", "lineHeight": "1", "padding": "2px 4px",
                        "alignSelf": "flex-start"}),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "12px", "flexWrap": "wrap",
        "background": "var(--card-bg)",
        "border": "1px solid var(--border-color)",
        "borderLeft": "3px solid var(--slider-accent, #E8A317)",
        "borderRadius": "8px", "padding": "11px 14px", "margin": "12px 0 4px",
    }) if not learn_dismissed else None

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
                  _GROWTH_CHIP.get(g_chip, "var(--font-color)"),
                  data_note=_force_note("growth")),
            _card("Inflation", _fmt(i), _dial_sub(i_d, i_mom), "/signals/inflation",
                  _INFLAT_CHIP.get(i_chip, "var(--font-color)"),
                  data_note=_force_note("inflation")),
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
        # "/7" was accurate while this was US-only; the 2026-10 rollout to
        # other countries runs a 2- or 3-component minimum-viable subset by
        # design (see docs/worklog.md 2026-10-03), so a fixed denominator
        # would misreport those as missing data rather than scoped-down.
        comp_word = "component" if n_comp == 1 else "components"
        stress_card = _card("Debt stress", _fmt(ds_val),
                            f"{n_comp} {comp_word} active", "/debt-stress")
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
        stage_color = STAGE_COLORS.get(stage_lbl, "var(--font-color)")
        squeeze_flag = bool(srow.get("sovereign_squeeze"))
        spread_flag = srow.get("debt_income_spread_flag")
        fx_flag = srow.get("fx_debt_share_flag")
        fx_share = srow.get("feat_fx_debt_share")
        runway_flag = srow.get("fx_reserve_runway_flag")
        runway = srow.get("feat_fx_reserve_runway")
        priv = srow.get("stage_private")
        sov = srow.get("stage_sovereign")
        sub_bits = []
        if s_conf is not None and not pd.isna(s_conf):
            sub_bits.append(f"confidence {s_conf:.2f}")
        sub_bits.append(f"{n_feat}/5 features")
        sub_bits.append(f"{pd.Timestamp(srow['as_of']):%b %Y}")
        # Headline is the WORSE-of the private/sovereign votes (Ray ruling
        # 2026-07-06) — show both when they diverge so the read isn't opaque.
        if priv and sov and priv != sov:
            sub_bits.append(f"private: {priv} · sovereign: {sov}")
        stage_body = [
            html.Div("Cycle stage", style=_LABEL),
            html.Div([
                html.Span(stage_lbl, style={**_BIG, "color": stage_color}),
                *([html.Span(
                    "SOVEREIGN SQUEEZE",
                    title="Refinancing gap, government interest/GDP, or government "
                          "debt-service (interest/revenue) has crossed its threshold — "
                          "an early-warning signal that can fire even while the "
                          "headline still reads the current mechanism (Ray Dalio "
                          "ruling, 2026-07-06: 'reflation as a headline can be "
                          "misleading when the private side masks a sovereign "
                          "squeeze — keep the mechanism headline, add a separate flag').",
                    style={"color": "#E8A317", "fontSize": "0.62rem", "fontWeight": "800",
                           "letterSpacing": "0.04em", "border": "1px solid #E8A317",
                           "borderRadius": "4px", "padding": "1px 6px",
                           "marginLeft": "8px", "whiteSpace": "nowrap"})]
                  if squeeze_flag else []),
                *([html.Span(
                    f"DEBT-INCOME SPREAD: {spread_flag.upper()}",
                    title="Debt is growing faster than the income available to service "
                          "it in at least one sector (household/corporate/government) — "
                          "Spread = DebtGrowthRate − IncomeGrowthRate, both YoY %. "
                          "Independent early-warning gauge (Ray Dalio consult, "
                          "2026-08-19) alongside Sovereign Squeeze; see the Debt Stress "
                          "page for the per-sector breakdown.",
                    style={"color": "#E8A317" if spread_flag == "warning" else RED,
                           "fontSize": "0.62rem", "fontWeight": "800",
                           "letterSpacing": "0.04em",
                           "border": f"1px solid {'#E8A317' if spread_flag == 'warning' else RED}",
                           "borderRadius": "4px", "padding": "1px 6px",
                           "marginLeft": "8px", "whiteSpace": "nowrap"})]
                  if spread_flag in ("warning", "critical") else []),
                *([html.Span(
                    f"FX DEBT SHARE: {fx_flag.upper()} ({fx_share:.0f}%)",
                    title="Share of general-government external debt denominated in "
                          "foreign currency (IMF Currency Composition of the IIP) — "
                          "Dalio's sharpest EM distinction: own-currency debt can be "
                          "inflated away, foreign-currency debt cannot (hard default / "
                          "balance-of-payments risk instead). Coverage-audit High item "
                          "#4, 2026-10-03; BR/MX/ID only.",
                    style={"color": "#E8A317" if fx_flag == "warning" else RED,
                           "fontSize": "0.62rem", "fontWeight": "800",
                           "letterSpacing": "0.04em",
                           "border": f"1px solid {'#E8A317' if fx_flag == 'warning' else RED}",
                           "borderRadius": "4px", "padding": "1px 6px",
                           "marginLeft": "8px", "whiteSpace": "nowrap"})]
                  if fx_flag in ("warning", "critical") and fx_share is not None
                  and not pd.isna(fx_share) else []),
                *([html.Span(
                    f"FX RESERVE RUNWAY: {runway_flag.upper()} ({runway:.1f}mo)",
                    title="Months of import cover from FX reserves (reserves / average "
                          "monthly imports) — the standard IMF/market reserve-adequacy "
                          "gauge. Below 6 months is the wider caution band; below 3 is "
                          "the classic adequacy floor. Coverage-audit follow-up, "
                          "2026-10-03; CN/IN/ID/BR only.",
                    style={"color": "#E8A317" if runway_flag == "warning" else RED,
                           "fontSize": "0.62rem", "fontWeight": "800",
                           "letterSpacing": "0.04em",
                           "border": f"1px solid {'#E8A317' if runway_flag == 'warning' else RED}",
                           "borderRadius": "4px", "padding": "1px 6px",
                           "marginLeft": "8px", "whiteSpace": "nowrap"})]
                  if runway_flag in ("warning", "critical") and runway is not None
                  and not pd.isna(runway) else []),
            ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap",
                      "gap": "2px"}),
            html.Div(" · ".join(sub_bits), style=_SUB),
        ]
        stage_card = dcc.Link(html.Div(stage_body, style=_CARD), href="/debt-stress",
                              style={"textDecoration": "none", "display": "flex",
                                     "flex": "1 1 170px"})
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
    from dashboard.force_detail import _productivity_divergence
    prod = _latest(hist, "productivity_score")
    prod_mom = _latest(hist, "productivity_breadth")
    divergence = _productivity_divergence(prod, g, float(thr(t, "gz"))) if prod is not None else None
    if divergence:
        trend_sub = divergence["label"]
    elif prod is not None and g is not None:
        gap = prod - g
        trend_sub = ("trend above cycle" if gap > 0.25 else
                     "cycle running ahead of trend" if gap < -0.25 else
                     "trend and cycle aligned")
    else:
        trend_sub = "single-signal read" if prod is not None else "no data"
    if prod_mom is not None:
        trend_sub += f" · {prod_mom:.0%} mom"

    # Big-cycle ORDER reads (Phase D + D4 manual-load slots)
    rcs = _sig(latest_sig, "order.reserve_currency_share")
    fth = _sig(latest_sig, "order.foreign_treasury_holdings_share")
    ouis = _sig(latest_sig, "order.offshore_usd_issuance_share")
    gini = _sig(latest_sig, "order.gini")
    milex = _sig(latest_sig, "order.military_expenditure_gdp")
    gov = _sig(latest_sig, "order.governance")
    gpr = _sig(latest_sig, "order.geopolitical_risk")
    order_bits = []
    if rcs.get("value") is not None:
        cur = {"US": "USD", "EZ": "EUR", "JP": "JPY", "GB": "GBP", "CN": "CNY"}.get(country, "FX")
        d12 = rcs.get("change_12m")
        d12_txt = f" ({float(d12):+.1f}pp/yr)" if d12 is not None and not pd.isna(d12) else ""
        order_bits.append(f"{cur} reserve share {float(rcs['value']):.1f}%{d12_txt}")
    # Dollar-dominance monitor (Ray Dalio review, Session 2026-08-21): two more
    # legs beyond reserve share — sovereign debt foreign-held, offshore USD
    # issuance share. Both are US-only (derived from FRED/BIS-global data),
    # so they only populate when latest_sig is the US snapshot, same as rcs.
    if fth.get("value") is not None:
        order_bits.append(f"UST foreign-held {float(fth['value']):.1f}%")
    if ouis.get("value") is not None:
        order_bits.append(f"offshore USD debt share {float(ouis['value']):.1f}%")
    if gini.get("value") is not None:
        gini_yr = pd.Timestamp(gini["as_of"]).year if gini.get("as_of") is not None else "?"
        order_bits.append(f"Gini {float(gini['value']):.1f} ({gini_yr})")
    if milex.get("value") is not None:
        order_bits.append(f"military spend {float(milex['value']):.1f}% GDP")
    if gov.get("value") is not None:
        order_bits.append(f"V-Dem {float(gov['value']):.2f}")
    if gpr.get("value") is not None:
        order_bits.append(f"GPR {float(gpr['value']):.1f}")
    # Pending manual-load slots (D4): only flagged while the drops are absent.
    pending = [n for n, s in (("governance", gov), ("GPR", gpr)) if s.get("value") is None]
    if order_bits:
        order_big = (f"{float(rcs['value']):.1f}%" if rcs.get("value") is not None
                     else f"{float(gini['value']):.1f}")
        pending_txt = f" — {'/'.join(pending)} pending manual load" if pending else ""
        order_card = _card("Big-cycle position", order_big,
                           " · ".join(order_bits) + pending_txt,
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

    return html.Div([header, learn, levers, longcycle, trend, watch])


@callback(
    Output("cc-learn-dismissed", "data"),
    Input("cc-learn-close", "n_clicks"),
    prevent_initial_call=True,
)
def dismiss_learn_banner(n_clicks):
    """Persist the 'learn to read this' banner dismissal (localStorage store)."""
    return True

"""Regime Validator — independent FRED-benchmark cross-check of the
Growth/Inflation chips (docs/external_validators_plan.md, 2026-10-03).

Promotes `indicators/audit_benchmarks.py`'s one-off CLI audit into a live
dashboard page: one dual-line card per benchmark (our chip's own windowed
Z-score vs. the benchmark's own rolling Z-score, same comparison
`compare_axis()` already computes), an AGREE/PARTIAL/CONTRADICT verdict per
card, and the disagreement-episode list where one exists.

US-only — the benchmark panel (CFNAI, trimmed-mean CPI/PCE, GDPNow, Sahm
rule, Michigan 1y inflation expectations, ...) is US-specific data; there is
no equivalent panel for other countries. Recomputes live on each render
(same read-only DB access `audit_benchmarks.py` itself uses) rather than
reading the persisted `validator_verdicts` snapshot table, so the charts are
always current, not whatever the last pipeline run cached — the persisted
table exists for the lightweight Command Center badge and the CreovaOne
cross-project read, not this detail page.

Renamed "Validator Audit" -> "Regime Validator" on the user-facing surfaces
2026-10-06. The module name, the `/validator-audit` route and the
`navlnk-validator-audit` id are deliberately unchanged, so existing links
and the `validator_verdicts` table's vocabulary still line up.

Feeds no composite; isolated force, same convention as fed.*/market.*/order.*.
Visual pattern is the shared Monitor-card style (`dashboard.shared_components.
_chart_card`/`_section`/`_chip`), same as every other page in the Monitors
nav group.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from dash import html

from dashboard.shared_components import (
    AMBER, FORCE_COLOR, GREEN, GREY as _GREY, VERDICT_COLOR, _chart_card, _chip,
    _section, summarize_validator_axis,
)

_COUNTRY = "US"


def _load() -> Optional[dict]:
    """Live recompute (read-only) — None if the composites table is empty
    (pipeline never run) rather than letting the page crash."""
    from indicators.audit_benchmarks import (
        CANONICAL_GROWTH_WINDOW, CANONICAL_INFLATION_WINDOW,
        chip_state, compare_axis, load_benchmark_panel,
    )

    try:
        chip = chip_state(country=_COUNTRY)
    except RuntimeError:
        return None

    windows = {"growth": CANONICAL_GROWTH_WINDOW, "inflation": CANONICAL_INFLATION_WINDOW}
    axes = {}
    for axis in ("growth", "inflation"):
        panel = load_benchmark_panel(axis)
        result = compare_axis(axis, chip, panel, window=windows[axis])
        axes[axis] = {"result": result, "panel": panel, "window": windows[axis]}
    return {"chip": chip, "axes": axes}


def _rolling_z_df(panel: pd.DataFrame, key: str, window: int) -> pd.DataFrame:
    from indicators.audit_benchmarks import rolling_z
    if key not in panel.columns:
        return pd.DataFrame(columns=["as_of", "value"])
    z = rolling_z(panel[key], window).dropna()
    if z.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    return pd.DataFrame({"as_of": z.index, "value": z.values})


def _episodes_note(episodes: list) -> str:
    if not episodes:
        return ""
    parts = [f"{e['start']}→{e['end']} ({e['months']}mo, our Z {e['our_z_mean']:+.2f} "
             f"vs benchmark {e['benchmark_z_mean']:+.2f})" for e in episodes[:3]]
    more = f" (+{len(episodes) - 3} more)" if len(episodes) > 3 else ""
    return "Disagreement episodes: " + "; ".join(parts) + more


def _benchmark_card(axis: str, b: dict, chip_hist: pd.DataFrame,
                    panel: pd.DataFrame, window: int, color: str) -> html.Div:
    verdict = b.get("verdict", "UNKNOWN")
    vcolor = VERDICT_COLOR.get(verdict, _GREY)

    ours_df = chip_hist[["as_of", axis]].rename(columns={axis: "value"}).dropna()
    theirs_df = _rolling_z_df(panel, b["benchmark"], window)

    state = b.get("state", "—")
    spearman = b.get("spearman_full")
    lag = b.get("best_lag_months")
    read = (
        f"{state} vs. our own norm · Spearman "
        + (f"{spearman:+.2f}" if spearman is not None else "—")
        + " · lag "
        + (f"{lag:+d}mo" if lag is not None else "—")
    )
    info_bits = [b.get("note", "")]
    units = b.get("units")
    if units:
        info_bits.append(f"Units: {units}.")
    ep_note = _episodes_note(b.get("episodes") or [])
    if ep_note:
        info_bits.append(ep_note)

    return _chart_card(
        b.get("title", b["benchmark"]), ours_df, None, "verdict", read,
        zero_line=True, color=color,
        info=" ".join(x for x in info_bits if x),
        df2=theirs_df, color2=_GREY, label="Our chip Z", label2="Benchmark rolling Z",
        fmt_override=verdict,
    )
    # fmt_override colors the header value with `color` (the primary line
    # color) rather than the verdict color on purpose — the verdict is
    # already unmissable as the card's header text itself (AGREE/PARTIAL/
    # CONTRADICT/UNKNOWN), and keeping the number in the force color matches
    # every other chart card on the dashboard.


# ── Survey of Professional Forecasters (plan item 2, 2026-10-03) ──────────────
# Deliberately NOT part of the AGREE/PARTIAL/CONTRADICT tally above — quarterly,
# not monthly, and a genuinely different kind of read: a true forecaster-
# consensus SURPRISE (actual vs. what professional economists predicted before
# the quarter happened), closer to "surprise" in the academic sense than the
# Z-score-vs-own-history comparisons above. Its own section, own card style.

def _spf_card(key: str, label: str, surprise_data: dict, color: str) -> html.Div:
    from indicators.spf_loader import forecast_vs_realized

    fcst, realized = forecast_vs_realized(key)
    fcst_df = pd.DataFrame({"as_of": fcst.index, "value": fcst.values}) if not fcst.empty else pd.DataFrame(columns=["as_of", "value"])
    real_df = pd.DataFrame({"as_of": realized.index, "value": realized.values}).dropna() if not realized.empty else pd.DataFrame(columns=["as_of", "value"])

    surprise = surprise_data.get("surprise")
    target_q = surprise_data.get("surprise_target_quarter")
    fdate = surprise_data.get("surprise_forecast_date")
    nowcast = surprise_data.get("nowcast")
    next_q = surprise_data.get("next_q")

    if surprise is None:
        read = "No resolved quarter yet to compare (target quarter not yet realized)."
        fmt_override = "—"
    else:
        read = (f"Q{pd.Timestamp(target_q).quarter} {pd.Timestamp(target_q).year} actual vs. "
                f"the forecast made a quarter ahead (survey of {fdate}).")
        fmt_override = f"{surprise:+.2f}pp"

    info = (f"Current survey nowcast {nowcast:+.2f}pp, one-quarter-ahead forecast "
            f"{next_q:+.2f}pp. " if nowcast is not None and next_q is not None else "") + (
            "Surprise = realized actual minus the forecast made one quarter in advance "
            "(SPF's own 'one quarter ahead' horizon, shifted to the quarter it targets) — "
            "a genuine ex-ante forecast error, not an in-quarter nowcast. Philadelphia Fed, "
            "not FRED-hosted (own quarterly Excel files).")

    return _chart_card(
        f"SPF {label} — surprise", fcst_df, None, "pp", read,
        color=color, zero_line=False, info=info,
        df2=real_df, color2=_GREY, label="Forecast (1Q ahead)", label2="Realized",
        fmt_override=fmt_override,
    )


def _spf_section() -> Optional[html.Div]:
    from indicators.spf_loader import compute_spf_surprise

    try:
        data = compute_spf_surprise()
    except Exception:
        return None
    if data.get("as_of") is None:
        return None

    as_of = pd.Timestamp(data["as_of"])
    freshness = _chip(f"last SPF read: Q{as_of.quarter} {as_of.year}", _GREY)

    cards = [
        _spf_card("rgdp_growth", "Real GDP growth",
                  data["variables"]["rgdp_growth"], FORCE_COLOR.get("growth", "#888")),
        _spf_card("cpi", "Headline CPI inflation",
                  data["variables"]["cpi"], FORCE_COLOR.get("inflation", "#888")),
    ]

    return html.Div([
        html.Div([
            html.Span("Survey of Professional Forecasters (Philadelphia Fed)",
                      style={"fontSize": "0.9rem", "fontWeight": "700",
                             "color": "var(--font-color)", "marginRight": "10px"}),
            freshness,
        ], style={"marginTop": "18px", "display": "flex", "alignItems": "center", "gap": "8px"}),
        _section("", "A true forecaster-consensus surprise measure — a different kind of "
                     "validator from the monthly benchmarks above, quarterly and not part of "
                     "their AGREE/PARTIAL/CONTRADICT tally.", cards),
    ])


def get_layout() -> html.Div:
    data = _load()
    if data is None:
        return html.Div(
            "No composite data for United States — run the pipeline.",
            style={"color": "var(--muted-color)", "padding": "20px"},
        )

    chip = data["chip"]
    chip_hist = chip["history"]

    header = html.Div([
        html.Div([
            html.Span("\U0001f9ea ", style={"fontSize": "1.3rem"}),
            html.Span("Regime Validator", style={"fontSize": "1.15rem", "fontWeight": "700",
                                                         "color": "var(--font-color)"}),
            html.Span(" · United States", style={"fontSize": "0.8rem",
                                                       "color": "var(--muted-color)"}),
        ]),
        html.Div(
            "Independent, FRED-hosted benchmarks cross-checked against the live Growth/Inflation "
            "chips — CFNAI, trimmed-mean CPI/PCE, GDPNow, the Sahm rule, Michigan 1y inflation "
            "expectations and more. These benchmarks are independently CONSTRUCTED, not "
            "input-independent (several share underlying BLS/BEA source data with our own basket) "
            "— high correlation is therefore partly mechanical and proves little; the "
            "informative signal is CONTRADICT verdicts, disagreement episodes, and lead/lag. "
            "Validation-only: nothing here ever feeds a composite or the regime engine "
            "(indicators/audit_benchmarks.py's own NON-NEGOTIABLE header).",
            style={"fontSize": "0.74rem", "color": "var(--muted-color)", "marginTop": "6px",
                   "maxWidth": "920px"},
        ),
    ], style={"borderBottom": "1px solid var(--border-color)", "paddingBottom": "12px",
              "marginBottom": "4px"})

    sections = []
    for axis in ("growth", "inflation"):
        axis_data = data["axes"][axis]
        result = axis_data["result"]
        panel = axis_data["panel"]
        window = axis_data["window"]
        color = FORCE_COLOR.get(axis, "#888")

        rollup = summarize_validator_axis(result["benchmarks"])
        tally = result.get("tally", {})
        rollup_chip = _chip(
            f"{(rollup['verdict'] or '—')} overall · "
            f"{tally.get('AGREE', 0)}A / {tally.get('PARTIAL', 0)}P / {tally.get('CONTRADICT', 0)}C",
            VERDICT_COLOR.get(rollup["verdict"], _GREY),
        )

        cards = [
            _benchmark_card(axis, b, chip_hist, panel, window, color)
            for b in result["benchmarks"]
        ]

        sections.append(html.Div([
            html.Div([
                html.Span(f"{axis.title()} — chip reads “{result['chip']}”",
                          style={"fontSize": "0.9rem", "fontWeight": "700",
                                 "color": "var(--font-color)", "marginRight": "10px"}),
                rollup_chip,
            ], style={"marginTop": "18px", "display": "flex", "alignItems": "center", "gap": "8px"}),
            _section("", f"{result['n_benchmarks_graded']} benchmarks graded, "
                         f"canonical {window}-month window.", cards),
        ]))

    spf_section = _spf_section()
    if spf_section is not None:
        sections.append(spf_section)

    ep = _episode_section()
    if ep is not None:
        sections.append(ep)

    return html.Div([header] + sections, className="p-3", style={"maxWidth": "1500px"})


def _episode_section() -> Optional[html.Div]:
    """How many INDEPENDENT episodes each chip is built on, per country.

    Ray consult 2026-10-08: shown that our inflation chip had fired in
    essentially one macro episode in 43 years, he withdrew his own tilt advice
    — "with only one occurrence, that confidence is essentially zero" — and set
    a bar of at least 10-15 independent occurrences, tested across periods and
    countries. A bar nobody can see is not a bar, so it is published here, on
    the page whose job is to say how much the chip should be trusted.

    The bar is a reasonable heuristic, not a citable standard: no such rule was
    found in the regime-switching literature, and the nearest real convention
    is events-per-variable (~10) from prediction modelling.
    """
    try:
        import duckdb
        from indicators.backtest import (
            classify_history, independent_episodes, composite_variance_flags,
            MIN_INDEPENDENT_EPISODES, EPISODE_GAP_MONTHS, MIN_COMPOSITE_Z_SD,
        )
        from dashboard.charting_data import DB_PATH
    except Exception:
        return None

    countries = ["US", "EZ", "GB", "JP", "KR", "CN", "IN",
                 "DE", "LU", "BR", "CA", "AU", "MX", "ID"]
    rows = []
    try:
        conn = duckdb.connect(str(DB_PATH), read_only=True)
    except Exception:
        return None
    flags = {}
    try:
        flags = composite_variance_flags(conn, countries)
    except Exception:
        pass
    try:
        for cc in countries:
            try:
                sc = conn.execute(
                    "SELECT as_of, growth_score, inflation_score, credit_score "
                    "FROM composites_pit WHERE country = ? ORDER BY as_of", [cc],
                ).df()
                if sc.empty:
                    continue
                sc["as_of"] = pd.to_datetime(sc["as_of"])
                sc = sc.set_index("as_of").dropna(subset=["growth_score", "inflation_score"])
                if len(sc) < 24:
                    continue
                ep = independent_episodes(classify_history(sc, dynamic=True, country=cc))
            except Exception:
                continue
            rows.append((cc, ep.get("growth", {}), ep.get("inflation", {}),
                         flags.get(cc, {})))
    finally:
        conn.close()
    if not rows:
        return None

    def _cell(d: dict) -> html.Td:
        n = d.get("decisive_episodes", 0)
        ok = d.get("meets_bar", False)
        return html.Td([
            html.Span(str(n), style={"fontWeight": "700",
                                     "color": GREEN if ok else AMBER}),
            html.Span("" if ok else "  below bar",
                      style={"fontSize": "0.7rem", "color": AMBER}),
        ], style={"padding": "3px 14px 3px 0", "fontFamily": "monospace"})

    def _sd_cell(fl: dict) -> html.Td:
        sd = fl.get("inflation_sd")
        ok = fl.get("inflation_usable", True)
        return html.Td(
            "—" if sd is None else f"{sd:.3f}" + ("" if ok else "  too flat to fit"),
            style={"padding": "3px 14px 3px 0", "fontFamily": "monospace",
                   "color": "var(--font-color)" if ok else AMBER},
        )

    hdr = ("Country", "Growth episodes", "Inflation episodes",
           "Inflation composite Z sd")
    table = html.Table(
        [html.Tr([html.Th(h, style={"textAlign": "left", "padding": "0 14px 6px 0",
                                    "fontSize": "0.7rem", "textTransform": "uppercase",
                                    "letterSpacing": "0.06em", "color": "var(--muted-color)"})
                  for h in hdr])]
        + [html.Tr([html.Td(cc, style={"padding": "3px 14px 3px 0",
                                       "fontFamily": "monospace"}),
                    _cell(g), _cell(i), _sd_cell(fl)]) for cc, g, i, fl in rows],
        style={"borderCollapse": "collapse", "fontSize": "0.82rem"},
    )
    n_low = sum(1 for _, g, i, _fl in rows
                if not g.get("meets_bar", False) or not i.get("meets_bar", False))
    n_flat = sum(1 for *_x, fl in rows if not fl.get("inflation_usable", True))
    return html.Div([
        html.Div("Evidence behind each chip",
                 style={"marginTop": "22px", "fontSize": "0.9rem",
                        "fontWeight": "700", "color": "var(--font-color)"}),
        _section("", (
            f"Independent decisive episodes since the start of each country's history. "
            f"Runs of the same label separated by fewer than {EPISODE_GAP_MONTHS} months "
            f"are merged — one macro event that flickers is one event, and counting it "
            f"twice is how a single episode masquerades as a sample. "
            f"The bar is {MIN_INDEPENDENT_EPISODES} (Ray, 2026-10-08); "
            f"{n_low} of {len(rows)} countries fall below it on at least one chip. "
            f"Do not tilt on a chip marked below bar. "
            f"The last column is a separate concern: a composite Z-score with "
            f"almost no variance cannot support a fitted beta however many "
            f"months of it exist. {n_flat} countries fall below {MIN_COMPOSITE_Z_SD} "
            f"because they run on an annual bridge forward-filled into a near-flat "
            f"line. The CHIP is unaffected — it is gated on distance from target, "
            f"not on this Z — but anything FITTED to the composite is not."
        ), [table]),
    ])

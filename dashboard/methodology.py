"""Methodology page for the Dash dashboard.

Prose-level explanation of every calculation step. Each accordion section
embeds the relevant formula cards and exposes a copy button so the user can
grab the full section — prose + LaTeX — in one click.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from indicators.composites import build_formula_catalog
from indicators.longterm_stress import build_debt_stress_formula_catalog


# ── Visual helpers ─────────────────────────────────────────────────────────────

def _p(text: str, **style) -> html.P:
    return html.P(text, style={"fontSize": "0.85rem", "lineHeight": "1.6",
                                "color": "var(--font-color)", **style})


def _sub(title: str, *children) -> html.Div:
    return html.Div([
        html.H4(title, style={
            "fontSize": "0.92rem", "fontWeight": "700",
            "color": "var(--muted-color)", "marginTop": "14px", "marginBottom": "6px",
        }),
        *children,
    ])


def _note(text: str) -> html.Div:
    return html.Div(text, style={
        "fontSize": "0.78rem", "color": "var(--muted-color)",
        "borderLeft": "3px solid var(--border-color)",
        "paddingLeft": "10px", "marginBottom": "8px",
    })


def _table(headers: list[str], rows: list[list[str]]) -> html.Table:
    th_sty = {
        "textAlign": "left", "padding": "5px 12px",
        "fontSize": "0.72rem", "textTransform": "uppercase",
        "letterSpacing": "0.06em", "color": "var(--muted-color)",
        "borderBottom": "1px solid var(--border-color)",
        "whiteSpace": "nowrap",
    }
    td_sty = {
        "padding": "5px 12px", "fontSize": "0.82rem",
        "borderBottom": "1px solid var(--border-color)",
        "color": "var(--font-color)", "verticalAlign": "top",
    }
    return html.Table([
        html.Thead(html.Tr([html.Th(h, style=th_sty) for h in headers])),
        html.Tbody([
            html.Tr([html.Td(c, style=td_sty) for c in row])
            for row in rows
        ]),
    ], style={
        "width": "100%", "borderCollapse": "collapse",
        "backgroundColor": "var(--card-bg)",
        "border": "1px solid var(--border-color)",
        "borderRadius": "4px", "marginBottom": "12px",
    })


def _inline_formula(spec: dict) -> html.Div:
    """Compact formula block embedded inside a methodology section."""
    params = spec.get("parameters", [])
    return html.Div([
        html.Div([
            html.Span(str(spec["group"]).upper(), style={
                "fontSize": "0.60rem", "letterSpacing": "0.1em",
                "fontWeight": "700", "color": "var(--muted-color)",
            }),
            html.Span(f"  {spec['title']}", style={
                "fontSize": "0.82rem", "fontWeight": "600",
                "color": "var(--font-color)",
            }),
        ], style={"marginBottom": "2px"}),
        dcc.Markdown(
            f"$${spec['equation']}$$", mathjax=True,
            style={"fontSize": "0.98rem", "overflowX": "auto", "padding": "4px 0 2px 0"},
        ),
        html.P(str(spec["description"]), style={
            "fontSize": "0.78rem", "color": "var(--muted-color)",
            "marginBottom": "4px", "lineHeight": "1.5",
        }),
        html.Ul(
            [html.Li(str(p), style={"fontSize": "0.74rem"}) for p in params],
            style={"color": "var(--muted-color)", "paddingLeft": "18px",
                   "marginBottom": "4px"},
        ) if params else None,
        html.Code(str(spec["source"]), style={
            "fontSize": "0.62rem", "color": "var(--muted-color)",
            "overflowWrap": "anywhere",
        }),
    ], style={
        "borderLeft": "2px solid var(--border-color)",
        "paddingLeft": "12px", "marginTop": "10px", "marginBottom": "10px",
    })


def _copy_btn(text: str) -> html.Div:
    """Clipboard button pinned to the top-right of a section body."""
    return html.Div(
        dcc.Clipboard(
            content=text,
            title="Copy section",
            style={
                "cursor": "pointer", "color": "var(--muted-color)",
                "fontSize": "0.72rem", "opacity": "0.5",
                "transition": "opacity 0.15s",
                "background": "none", "border": "none", "padding": "0",
            },
            className="formula-copy-btn",
        ),
        style={"display": "flex", "justifyContent": "flex-end",
               "marginBottom": "4px"},
    )


# ── Clipboard text builders ────────────────────────────────────────────────────

def _fmt_formula(spec: dict) -> str:
    lines = [
        f"  [{spec['group'].upper()}] {spec['title']}",
        f"  $${spec['equation']}$$",
        f"  {spec['description']}",
    ]
    for p in spec.get("parameters", []):
        lines.append(f"    • {p}")
    lines.append(f"  Source: {spec['source']}")
    return "\n".join(lines)


def _fmt_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["  " + " | ".join(headers)]
    lines.append("  " + "-+-".join("-" * len(h) for h in headers))
    for row in rows:
        lines.append("  " + " | ".join(str(c) for c in row))
    return "\n".join(lines)


def _section_text(title: str, paras: list[str],
                  tables: list[tuple[list[str], list[list[str]]]] | None = None,
                  formulas: list[dict] | None = None,
                  notes: list[str] | None = None) -> str:
    parts = [f"{'═' * 60}", f"  {title}", f"{'═' * 60}", ""]
    for p in paras:
        parts.append(p)
        parts.append("")
    if tables:
        for hdrs, rows in tables:
            parts.append(_fmt_table(hdrs, rows))
            parts.append("")
    if notes:
        for n in notes:
            parts.append(f"  ⚠ {n}")
            parts.append("")
    if formulas:
        parts.append("FORMULAS")
        parts.append("─" * 40)
        for spec in formulas:
            parts.append(_fmt_formula(spec))
            parts.append("")
    return "\n".join(parts).rstrip()


# ── Page layout ───────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    all_specs = {s["title"]: s for s in
                 build_formula_catalog() + build_debt_stress_formula_catalog()}

    def F(title: str) -> dict:
        return all_specs[title]

    return html.Div([

        html.Div([
            html.H2("Methodology", style={"fontSize": "1.4rem", "marginBottom": "4px"}),
            html.P(
                "How every number on this dashboard is produced — from raw API response "
                "to regime quadrant.  Each section includes the relevant equations with "
                "live parameter values and a copy button to grab everything at once.",
                style={"color": "var(--muted-color)", "fontSize": "0.83rem"},
            ),
        ], className="pt-3 pb-1"),

        dbc.Accordion([

            # 1 ── Overview ────────────────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "1 · Overview & Concepts",
                    [
                        "This tool is a diagnostic, cross-country macro-regime dashboard in the "
                        "Ray Dalio 'Economic Machine' tradition. It ingests macroeconomic data "
                        "from free/open APIs, normalises each series into a standardised signal, "
                        "classifies each economy into one of four macro seasons, and presents a "
                        "multi-panel diagnostic terminal.",
                        "It is a diagnostic tool, not an allocator. No portfolio construction, "
                        "risk-parity weights, or trade recommendations are produced here. Those "
                        "belong to the separate Allocation Layer project.",
                    ],
                    tables=[(
                        ["Concept", "Definition"],
                        [
                            ["Force",     "One of the five fundamental economic forces: Growth, Inflation, Policy, Credit/Debt, External/Trade"],
                            ["Signal",    "A single normalised, time-stamped indicator observation for a given country and force"],
                            ["Composite", "Weighted mean Z-score across the signals that belong to Growth or Inflation"],
                            ["Quadrant",  "The four-season regime label derived from the signs of Growth and Inflation scores"],
                            ["Vintage",   "A point-in-time API snapshot (available for FRED series only)"],
                        ]
                    )],
                )),
                _p(
                    "This tool is a diagnostic, cross-country macro-regime dashboard in the "
                    "Ray Dalio 'Economic Machine' tradition.  It ingests macroeconomic data "
                    "from free/open APIs, normalises each series into a standardised signal, "
                    "classifies each economy into one of four macro seasons, and presents a "
                    "multi-panel diagnostic terminal."
                ),
                _p(
                    "It is a diagnostic tool, not an allocator.  No portfolio construction, "
                    "risk-parity weights, or trade recommendations are produced here.  Those "
                    "belong to the separate Allocation Layer project."
                ),
                _table(
                    ["Concept", "Definition"],
                    [
                        ["Force",        "One of the five fundamental economic forces: Growth, Inflation, Policy, Credit/Debt, External/Trade"],
                        ["Signal",       "A single normalised, time-stamped indicator observation for a given country and force"],
                        ["Composite",    "Weighted mean Z-score across the signals that belong to Growth or Inflation"],
                        ["Quadrant",     "The four-season regime label derived from the signs of Growth and Inflation scores"],
                        ["Vintage",      "A point-in-time API snapshot (available for FRED series only)"],
                    ]
                ),
            ], title="1 · Overview & Concepts"),

            # 2 ── Data Sources ─────────────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "2 · Data Sources & Ingestion",
                    [
                        "Data is fetched from open/free APIs on first use and cached locally. "
                        "Subsequent runs read from the cache; live network calls only occur when "
                        "the pipeline is re-run with --latest.",
                        "Idempotency: every ingestion pass upserts on (id, as_of). Re-running "
                        "the pipeline never duplicates rows.",
                        "Raw cache: API responses are cached to Parquet files under raw_cache/ "
                        "on first successful pull. Development always runs against the cache.",
                        "Vintage availability: point-in-time vintages are available for FRED "
                        "series only. All other providers return the latest-revised value "
                        "(vintage_available=false). Back-testing on non-FRED series uses revised "
                        "data and may overstate predictive accuracy.",
                    ],
                    tables=[(
                        ["Provider", "Scope", "Auth"],
                        [
                            ["FRED (St. Louis Fed)", "US macro — GDP, PCE, payrolls, rates, spreads, TIPS breakevens", "FRED_API_KEY env var"],
                            ["World Bank API v2",    "Cross-country annual — trade, FDI, debt, demographics, R&D", "None"],
                            ["IMF DataMapper",       "Cross-country annual — fiscal balances, structural indicators", "None"],
                            ["OECD SDMX REST",       "Cross-country — harmonised CPI, unemployment (planned)", "None"],
                        ]
                    )],
                )),
                _p("Data is fetched from open/free APIs on first use and cached locally. "
                   "Subsequent runs read from the cache; live network calls only occur when "
                   "the pipeline is re-run with --latest."),
                _table(
                    ["Provider", "Scope", "Auth"],
                    [
                        ["FRED (St. Louis Fed)", "US macro — GDP, PCE, payrolls, rates, spreads, TIPS breakevens", "FRED_API_KEY env var"],
                        ["World Bank API v2",   "Cross-country annual — trade, FDI, debt, demographics, R&D", "None"],
                        ["IMF DataMapper",      "Cross-country annual — fiscal balances, structural indicators", "None"],
                        ["OECD SDMX REST",      "Cross-country — harmonised CPI, unemployment (planned)", "None"],
                    ]
                ),
                _sub("Idempotency"),
                _p("Every ingestion pass upserts on (id, as_of).  Re-running the pipeline "
                   "never duplicates rows — it overwrites with the latest revised value."),
                _sub("Raw cache"),
                _p("API responses are cached to Parquet files under raw_cache/ on first "
                   "successful pull.  Development always runs against the cache.  This keeps "
                   "iteration fast and protects rate-limited endpoints."),
                _sub("Vintage availability"),
                _p("Point-in-time vintages (the value a series had on a specific past date, "
                   "before subsequent revisions) are available for FRED series only.  All other "
                   "providers return the latest-revised value, and vintage_available is set to "
                   "false.  Back-testing on non-FRED series therefore uses revised data and "
                   "may overstate predictive accuracy."),
            ], title="2 · Data Sources & Ingestion"),

            # 3 ── Signal Transformation ────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "3 · Signal Transformation",
                    [
                        "Raw API values are transformed before normalisation. The transformation "
                        "type is declared per signal in the binding config.",
                        "Pre-smoothing: crude oil (daily prices, highly volatile) receives a "
                        "7-day SMA before the monthly YoY transformation, configured via "
                        "pre_smooth_window in us_bindings.yaml.",
                        "Frequency: each signal retains its native frequency (D/W/M/Q/A). The "
                        "pipeline does not resample to a common frequency. Forward-fill within a "
                        "per-frequency carry cap bridges gaps in the composite engine.",
                    ],
                    tables=[(
                        ["Transformation", "Formula", "When used"],
                        [
                            ["yoy_pct",  "(x_t − x_{t−N}) / |x_{t−N}|  N = 1 year of native periods",
                             "Level series with trend (GDP, PCE, payrolls)."],
                            ["level",    "Pass-through (no change)",
                             "Already stationary: interest rates, spreads, PMI, capacity utilisation."],
                            ["spread",   "Pass-through (no change)",
                             "Already a difference: 10Y-2Y yield spread, TIPS breakeven."],
                            ["derived",  "Computed in pipeline from other signals",
                             "Ratios not available directly from a provider (e.g. debt/GDP)."],
                        ]
                    )],
                )),
                _p("Raw API values are transformed before normalisation.  The transformation "
                   "type is declared per signal in the binding config."),
                _table(
                    ["Transformation", "Formula", "When used"],
                    [
                        ["yoy_pct",  "( x_t − x_{t−N} ) / |x_{t−N}|  where N = 1 year of native periods",
                         "Level series with trend (GDP, PCE, payrolls).  YoY removes seasonal and level effects, making readings comparable across decades."],
                        ["level",    "Pass-through (no change)",
                         "Series already stationary: interest rates, spreads, diffusion indices (PMI), capacity utilisation."],
                        ["spread",   "Pass-through (no change)",
                         "Series already a difference: 10Y-2Y yield spread, TIPS breakeven (= nominal − real yield)."],
                        ["derived",  "Computed in pipeline from other signals",
                         "Ratios or combinations not available directly from a provider (e.g. debt/GDP ratios)."],
                    ]
                ),
                _sub("Pre-smoothing"),
                _p("Crude oil (daily prices, highly volatile) receives a 7-day SMA before "
                   "the monthly YoY transformation.  This is configured via pre_smooth_window "
                   "in us_bindings.yaml and applied in pipeline Pass 1."),
                _sub("Frequency"),
                _p("Each signal retains its native frequency (D/W/M/Q/A).  The pipeline does "
                   "not resample to a common frequency.  Forward-fill within a per-frequency "
                   "carry cap bridges gaps in the composite engine."),
            ], title="3 · Signal Transformation"),

            # 4 ── Force Z-Score ────────────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "4 · Force Z-Score",
                    [
                        "The Force Z-score answers: 'how far is this indicator from its "
                        "historical norm?' A score of +2 means the indicator is two standard "
                        "deviations above its average — unusually high.",
                        "Full-history mode (default): Z = clip((x − μ) / σ, −4, 4) where μ and "
                        "σ are computed over the entire available history of each signal. This "
                        "provides the most stable baseline. The trade-off is that history from "
                        "the 1970s stagflation or the Great Moderation anchors what 'normal' "
                        "looks like.",
                        "Rolling-window mode (sidebar sliders or ⚙ Settings): Z_rolling = "
                        "clip((x − μ_N) / σ_N, −4, 4) where μ_N and σ_N are computed over the "
                        "most recent N months (36/48/60 m). Rolling G/I scores are pre-computed "
                        "at pipeline time and stored alongside the baseline scores.",
                        "Outlier cap: Z-scores are clipped to ±4σ. COVID-era extremes in payrolls "
                        "and GDP would otherwise reach ±20+.",
                        "Low-history flag: signals with fewer than 15 observations are flagged "
                        "low_history=True and excluded from composites.",
                    ],
                    formulas=[F("Component Z-score")],
                )),
                _p("The Force Z-score answers: 'how far is this indicator from its historical "
                   "norm?'  A score of +2 means the indicator is two standard deviations above "
                   "its average — unusually high."),
                _sub("Full-history mode (default)"),
                _p("Z = clip( (x − μ) / σ , −4, 4 )  where μ and σ are computed over the "
                   "entire available history of each signal.  This provides the most stable "
                   "baseline and is the mode used by the stored composite snapshots.  "
                   "The trade-off is that history from the 1970s stagflation or the Great "
                   "Moderation anchors what 'normal' looks like, which can make the post-2021 "
                   "inflation regime appear less extreme than it was relative to recent decades."),
                _sub("Rolling-window mode (sidebar sliders or ⚙ Settings)"),
                _p("Z_rolling = clip( (x − μ_N) / σ_N , −4, 4 )  where μ_N and σ_N are "
                   "computed over the most recent N months.  Recommended window: 36–60 months "
                   "(3–5 years).  This makes the score more responsive to structural regime "
                   "changes — for example, treating the low-inflation 2010s as the baseline "
                   "rather than the inflationary 1970s-80s.  "
                   "Rolling G/I scores are pre-computed at pipeline time for 36 m, 48 m, and "
                   "60 m windows and stored alongside the baseline scores."),
                _note("Guidance: force Z-scores should use 36–60 months for monthly data; "
                      "momentum Z-scores should use 6–12 months."),
                _sub("Outlier cap"),
                _p("Z-scores are clipped to ±4σ.  COVID-era extremes in payrolls and GDP "
                   "would otherwise reach ±20+, which would overwhelm the composite.  "
                   "Clipping at ±4 preserves the extreme direction signal without distorting "
                   "the scale.  This applies in both full-history and rolling modes."),
                _sub("Low-history flag"),
                _p("Signals with fewer than 15 observations are flagged low_history=True "
                   "and their Z-scores should be interpreted cautiously.  They are excluded "
                   "from composites at runtime."),
                _inline_formula(F("Component Z-score")),
            ], title="4 · Force Z-Score"),

            # 5 ── Momentum ─────────────────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "5 · Momentum",
                    [
                        "Two complementary momentum metrics are shown in the regime summary strip.",
                        "Δ MoM: month-on-month change in force composite score. Positive = force "
                        "is intensifying; negative = force is easing.",
                        "Momentum Z (12 mo): Z-score of the current MoM delta against the "
                        "distribution of MoM deltas over the preceding 12 months. Answers: 'is "
                        "today's rate of change unusually fast or slow compared with recent "
                        "history?' A high positive value means the force is accelerating at a "
                        "historically unusual pace.",
                        "Force momentum breadth: fraction of contributing signals moving in the "
                        "force-positive direction. Growth counts rising signals (falling for "
                        "inverted unemployment); Inflation counts rising signals.",
                        "Direction flag: each signal is tagged rising/falling/flat based on its "
                        "3-month absolute change. The change must exceed 10% of the signal's own "
                        "historical standard deviation to be called directional.",
                        "Momentum percentile (D1): the 3-month change for each signal is "
                        "percentile-ranked against its own full history of 3-month changes.",
                    ],
                    formulas=[F("Force/momentum weight tilt"), F("Force momentum breadth")],
                )),
                _p("Two complementary momentum metrics are shown in the regime summary strip."),
                _sub("Δ MoM — month-on-month change in force score"),
                _p("The raw difference between the current composite force score and the "
                   "previous period's score.  Positive = force is intensifying; "
                   "negative = force is easing."),
                _sub("Momentum Z (12 mo) — Z-score of recent force-score changes"),
                _p("Z-score of the current MoM delta against the distribution of MoM deltas "
                   "over the preceding 12 months.  Answers: 'is today's rate of change "
                   "unusually fast or slow compared with recent history?'  "
                   "A high positive Momentum Z means the force is accelerating at a "
                   "historically unusual pace; a large negative value means it is decelerating "
                   "sharply."),
                _note("Guidance: momentum Z-scores should use a 6–12 month rolling window "
                      "for monthly data; the current implementation uses 12 months."),
                _sub("Force momentum breadth"),
                _p("Fraction of contributing signals moving in the force-positive direction.  "
                   "Growth counts rising signals (falling for inverted unemployment); Inflation "
                   "counts rising signals.  Direction is based on each signal's 3-month change."),
                _sub("Direction flag"),
                _p("Each signal is tagged rising / falling / flat based on its 3-month "
                   "absolute change.  The change must exceed 10% of the signal's own "
                   "historical standard deviation before it is called directional — "
                   "this prevents near-zero drift on low-volatility structural ratios "
                   "from appearing as a signal."),
                _sub("Momentum percentile (D1)"),
                _p("The 3-month change for each signal is also percentile-ranked against "
                   "its own full history of 3-month changes.  A percentile of 0.90 means "
                   "the current rate of change is faster than 90% of all historical readings.  "
                   "This normalises momentum across series with very different volatility."),
                _inline_formula(F("Force/momentum weight tilt")),
                _inline_formula(F("Force momentum breadth")),
            ], title="5 · Momentum"),

            # 6 ── Dynamic Force Weighting ──────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "6 · Dynamic Force Weighting",
                    [
                        "Each composite component carries a configured nominal weight plus two "
                        "dynamic adjustments applied at runtime. All parameters are tunable in "
                        "config/composites.yaml.",
                        "Nominal weight: w_cfg = base_share × importance × quality_factor, "
                        "then normalised to sum to 1.0 within each force basket. base_share is "
                        "a per-signal anchor multiplier: 1.0 = anchor (2× pre-normalisation "
                        "weight); 0.5 = supporting signal. Current US anchors — Growth: "
                        "capacity_util (1.0); all others (0.5). Inflation: pce_core and "
                        "cpi_core (1.0); all others (0.5). importance is the primary judgement "
                        "dial (0–1). quality_factor reflects data quality concerns.",
                        "Importance tiers: PRIMARY (0.85–1.00) — non-redundant anchors that "
                        "drive the composite; STRONG (0.60–0.84) — reliable supplementary "
                        "signals; CONTEXT (0.30–0.59) — marginal info, volatile or lagging; "
                        "VOLATILE (0.10–0.29) — high noise or annual-only, present but not "
                        "drivers. These are informed priors; Phase 3B calibrate.py will "
                        "optimize them against historical regime labels.",
                        "Momentum agreement tilt: w_momentum = clip(1 + α × sign(Z_adj) × "
                        "direction_sign, m_min, m_max). When the force Z-score and 3-month "
                        "direction agree, the weight is boosted up to 1.5×. When they conflict, "
                        "weight is reduced to as little as 0.1×. Default α = 0.5.",
                        "Observation-age decay: w_decay = 0.5^(age_months / half_life). A "
                        "signal not updated in 6 months with a 3-month half-life contributes "
                        "at 25% of its nominal weight. Carry caps (M: 3 months, Q: 9, A: 15) "
                        "zero out signals beyond their expected release window.",
                        "Effective weight: w_eff = w_cfg × w_momentum × w_decay, renormalised "
                        "over the active signal set.",
                    ],
                    tables=[(
                        ["Tier", "importance range", "Role"],
                        [
                            ["PRIMARY",  "0.85 – 1.00", "Non-redundant anchor; drives the composite"],
                            ["STRONG",   "0.60 – 0.84", "Reliable supplementary; some correlation to primary"],
                            ["CONTEXT",  "0.30 – 0.59", "Marginal info; volatile, lagging, or redundant"],
                            ["VOLATILE", "0.10 – 0.29", "High noise or annual-only; present but not a driver"],
                        ]
                    )],
                    formulas=[F("Configured component weight"), F("Observation-age decay")],
                )),
                _p("Each composite component carries a configured nominal weight plus two "
                   "dynamic adjustments applied at runtime.  All parameters are tunable in "
                   "config/composites.yaml."),
                _sub("Nominal weight"),
                _p("w_cfg = base_share × importance × quality_factor, then normalised to "
                   "sum to 1.0 within each force basket.  "
                   "base_share is a per-signal anchor multiplier: signals with base_share = 1.0 "
                   "receive 2× the pre-normalisation weight of signals with base_share = 0.5.  "
                   "Current US anchors — Growth: capacity_util (1.0); all others (0.5).  "
                   "Inflation: pce_core and cpi_core (1.0); all others (0.5).  "
                   "importance is the primary judgement dial (0–1); tune it here when you "
                   "believe a signal should carry more or less weight.  "
                   "quality_factor reflects data quality concerns — lower for proxy or "
                   "indirect measures."),
                _inline_formula(F("Configured component weight")),
                _sub("Importance tiers"),
                _p("importance values are grouped into four named tiers to make calibration "
                   "decisions explicit and consistent across countries:"),
                _table(
                    ["Tier", "importance range", "Role"],
                    [
                        ["PRIMARY",  "0.85 – 1.00",
                         "Non-redundant anchors; drive the composite.  "
                         "E.g. pce_core (inflation), payrolls (growth)."],
                        ["STRONG",   "0.60 – 0.84",
                         "Reliable supplementary signals; some correlation to primary.  "
                         "E.g. cpi_core (correlated with pce_core, r≈0.92 → demoted from PRIMARY)."],
                        ["CONTEXT",  "0.30 – 0.59",
                         "Adds marginal information; volatile, lagging, or partly redundant.  "
                         "E.g. wages_eci, breakeven_5y."],
                        ["VOLATILE", "0.10 – 0.29",
                         "High noise or annual-only; included for breadth but not a driver.  "
                         "E.g. breakeven_10y (r≈0.90 vs breakeven_5y → capped at VOLATILE), "
                         "ppi_broad."],
                    ]
                ),
                _note("These are informed priors — judgement calls based on economic theory and "
                      "observed correlations. Phase 3B (indicators/calibrate.py) will optimize "
                      "them against historical regime labels."),
                _sub("Momentum agreement tilt"),
                _p("w_momentum = clip( 1 + α × sign(Z_adj) × direction_sign , m_min, m_max ).  "
                   "When the force Z-score and 3-month direction agree (both positive or both "
                   "negative), the weight is boosted up to 1.5×.  When they conflict, weight "
                   "is reduced to as little as 0.1×.  Default α = 0.5.  This rewards signals "
                   "where the level and momentum are telling the same story."),
                _sub("Observation-age decay"),
                _p("w_decay = 0.5 ^ (age_months / half_life).  A signal that has not updated "
                   "in 6 months with a 3-month half-life contributes at 25% of its nominal "
                   "weight.  Carry caps (M: 3 months, Q: 9, A: 15) zero out signals beyond "
                   "their expected release window — those appear as BLANK rows in the "
                   "component table."),
                _inline_formula(F("Observation-age decay")),
                _sub("Effective weight"),
                _p("w_eff = w_cfg × w_momentum × w_decay, renormalised over the active "
                   "signal set.  The component table in Regime History shows the colour-coded "
                   "effective weight: orange = reduced by decay/carry expiry, "
                   "green = boosted by momentum agreement, yellow = reduced by conflict."),
            ], title="6 · Dynamic Force Weighting"),

            # 7 ── Composite Construction ───────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "7 · Composite Construction",
                    [
                        "The Growth Score and Inflation Score are the weighted means of their "
                        "respective component Z-scores, after dynamic weight adjustments.",
                    ],
                    tables=[(
                        ["Metric", "Formula", "Notes"],
                        [
                            ["Growth Score",
                             "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for growth signals",
                             "unemployment is inverted; up to 9 configured signals"],
                            ["Inflation Score",
                             "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for inflation signals",
                             "up to 8 configured; breakevens at base_share=0.5; pce_core/cpi_core at 1.0"],
                            ["Confidence",
                             "½ × (N_G_agree / N_G + N_I_agree / N_I)",
                             "Fraction of contributing signals (with non-null direction) consistent "
                             "with composite sign; averaged across both forces; defaults to 50% if "
                             "a basket has no directional signals"],
                            ["Disequilibrium",
                             "Mean |Z(distance from equilibrium)| across 5 force groups",
                             "Signals how stretched the economy is across all dimensions"],
                        ]
                    )],
                    notes=["Signals flagged is_stale=True or low_history=True are excluded at "
                           "runtime. n_growth_signals / n_inflation_signals in the header shows "
                           "how many active components contributed."],
                    formulas=[
                        F("Effective weight and force score"),
                        F("Regime confidence"),
                        F("Structural disequilibrium"),
                    ],
                )),
                _p("The Growth Score and Inflation Score are the weighted means of their "
                   "respective component Z-scores, after dynamic weight adjustments."),
                _table(
                    ["Metric", "Formula", "Notes"],
                    [
                        ["Growth Score",
                         "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for growth signals",
                         "unemployment is inverted (lower = better growth); "
                         "up to 9 configured signals (stale or low-history signals excluded at runtime)"],
                        ["Inflation Score",
                         "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for inflation signals",
                         "up to 8 configured signals; breakeven_5y and breakeven_10y each carry "
                         "base_share = 0.5 to avoid double-counting market-implied expectations; "
                         "pce_core and cpi_core are anchors at base_share = 1.0"],
                        ["Confidence",
                         "½ × (N_G_agree / N_G + N_I_agree / N_I)",
                         "Fraction of contributing signals (with a non-null direction) "
                         "whose 3-month direction is consistent with the composite sign; "
                         "averaged across Growth and Inflation baskets; "
                         "defaults to 50% if a basket has no directional signals"],
                        ["Disequilibrium",
                         "Mean absolute Z-score distance from declared equilibrium "
                         "across 5 force groups",
                         "Signals how stretched the economy is across all dimensions, "
                         "not just growth and inflation"],
                    ]
                ),
                _note("Signals flagged is_stale=True or low_history=True are excluded at "
                      "runtime.  n_growth_signals / n_inflation_signals in the header shows "
                      "how many active components contributed."),
                _inline_formula(F("Effective weight and force score")),
                _inline_formula(F("Regime confidence")),
                _inline_formula(F("Structural disequilibrium")),
            ], title="7 · Composite Construction"),

            # 8 ── Regime Classification ────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "8 · Regime Classification",
                    [
                        "The four macro seasons are determined by the signs of the Growth and "
                        "Inflation composite scores.",
                        "Expansion (G>0, I≤0): economy growing above trend; inflation below norm. "
                        "Goldilocks. Typical mid-cycle environment.",
                        "Inflationary Boom (G>0, I>0): strong growth with rising prices. "
                        "Late-cycle. Policy tightening pressure builds.",
                        "Stagflation (G≤0, I>0): below-trend growth with persistent inflation. "
                        "Most difficult policy environment.",
                        "Disinflationary Slowdown (G≤0, I≤0): contraction with falling prices. "
                        "Deflationary risk; policy easing conditions.",
                        "Confidence qualifies the label. A Stagflation reading with 30% confidence "
                        "means only 30% of active signals agree with the quadrant direction. "
                        "High disequilibrium means the economy is far from any steady state.",
                    ],
                    tables=[(
                        ["Quadrant", "Growth", "Inflation", "Description"],
                        [
                            ["Expansion",               "> 0", "≤ 0", "Goldilocks. Typical mid-cycle environment."],
                            ["Inflationary Boom",        "> 0", "> 0", "Strong growth with rising prices. Late-cycle."],
                            ["Stagflation",              "≤ 0", "> 0", "Below-trend growth with persistent inflation."],
                            ["Disinflationary Slowdown", "≤ 0", "≤ 0", "Contraction with falling prices. Deflationary risk."],
                        ]
                    )],
                    notes=["Historical note: the 2022 US reading shows Inflationary Boom (not Stagflation) "
                           "because employment Z-scores were strongly positive. Stagflation correctly "
                           "appears from March 2023 when growth Z-scores turned negative."],
                )),
                _p("The four macro seasons are determined by the signs of the Growth and "
                   "Inflation composite scores."),
                _table(
                    ["Quadrant", "Growth", "Inflation", "Description"],
                    [
                        ["Expansion",              "> 0", "≤ 0",
                         "Economy growing above trend; inflation below norm.  "
                         "Goldilocks.  Typical mid-cycle environment."],
                        ["Inflationary Boom",       "> 0", "> 0",
                         "Strong growth with rising prices.  Late-cycle.  "
                         "Policy tightening pressure builds."],
                        ["Stagflation",             "≤ 0", "> 0",
                         "Below-trend growth with persistent inflation.  "
                         "Most difficult policy environment."],
                        ["Disinflationary Slowdown","≤ 0", "≤ 0",
                         "Contraction with falling prices.  "
                         "Deflationary risk; policy easing conditions."],
                    ]
                ),
                _p("Confidence qualifies the label.  A Stagflation reading with 30% confidence "
                   "means only 30% of active signals agree with the quadrant direction — "
                   "the classification is tentative.  High disequilibrium means the economy is "
                   "far from any steady state across multiple force dimensions."),
                _note("Historical note: the 2022 US reading shows Inflationary Boom "
                      "(not Stagflation) because employment Z-scores were strongly positive.  "
                      "Stagflation correctly appears from March 2023 when growth Z-scores "
                      "turned negative."),
            ], title="8 · Regime Classification"),

            # 9 ── Long-Term Debt Stress ────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "9 · Long-Term Debt Stress",
                    [
                        "The Debt Stress indicator aggregates seven measures of long-run debt "
                        "sustainability into a single quarterly composite. It is separate from "
                        "the regime composite and does not feed into the quadrant classification.",
                        "Z-scores use a 40-quarter rolling window for quarterly components and a "
                        "10-year rolling window for annual components. shift(1) look-back is "
                        "applied before computing rolling statistics to prevent look-ahead bias.",
                        "Gap 1 — Exponential weight decay: a component not updated within its "
                        "expected publication lag (Q: 1 qtr, A: 4 qtrs) loses weight as "
                        "0.5^(k_excess / half_life) where half_life = 4 quarters. A component "
                        "whose effective weight falls below 20% of its nominal weight is dropped.",
                        "Gap 2 — Carry cap: a component carried beyond max_carry_quarters (4) "
                        "is zeroed. The composite is null if retained weight < 60% of basket.",
                        "Gap 3 — Extrapolation gate: model-based extrapolation available but "
                        "disabled by default. Enable in config/longterm_stress.yaml.",
                    ],
                    tables=[(
                        ["Component", "Weight", "Freq", "Source", "Stress direction"],
                        [
                            ["Govt + Household debt / GDP (combined)", "0.25", "Q",
                             "FRED: GFDEGDQ188S + HDTGPDUSQ163N", "positive"],
                            ["Corporate debt / GDP",                   "0.15", "Q",
                             "FRED: BCNSDODNS ÷ GDP (derived)",        "positive"],
                            ["Household debt-service ratio",           "0.20", "Q",
                             "FRED: TDSP",                             "positive"],
                            ["Federal interest outlays / GDP",         "0.15", "A→Q",
                             "FRED: FYOINT ÷ GDP (derived)",           "positive"],
                            ["Primary fiscal balance / GDP",           "0.10", "A→Q",
                             "IMF DataMapper: pb",                     "negative"],
                            ["Structural balance / potential GDP",      "0.05", "A→Q",
                             "IMF DataMapper: GGCB_G01_PGDP_PT",       "negative"],
                            ["Government revenue / GDP",               "0.10", "A→Q",
                             "World Bank: GC.REV.XGRT.GD.ZS",         "negative"],
                        ]
                    )],
                    notes=["Bands are exploratory display thresholds only — NOT validated risk "
                           "thresholds. Calibrate against known episodes before operational use."],
                    formulas=[
                        F("Rolling Z-score (quarterly components)"),
                        F("Rolling Z-score (annual components → quarterly)"),
                        F("Staleness weight decay"),
                        F("Aggregate stress score"),
                        F("Stress band labels"),
                    ],
                )),
                _p("The Debt Stress indicator aggregates seven measures of long-run debt "
                   "sustainability into a single quarterly composite.  It is separate from "
                   "the regime composite and does not feed into the quadrant classification."),
                _table(
                    ["Component", "Weight", "Freq", "Source", "Stress direction"],
                    [
                        ["Govt + Household debt / GDP (combined)", "0.25", "Q",
                         "FRED: GFDEGDQ188S + HDTGPDUSQ163N (derived sum)",
                         "positive — higher = more stress"],
                        ["Corporate debt / GDP",                   "0.15", "Q",
                         "FRED: BCNSDODNS ÷ GDP (raw, derived)",
                         "positive"],
                        ["Household debt-service ratio",           "0.20", "Q",
                         "FRED: TDSP (required payments % disposable income)",
                         "positive"],
                        ["Federal interest outlays / GDP",         "0.15", "A→Q",
                         "FRED: FYOINT ÷ GDP (annual, forward-filled quarterly)",
                         "positive"],
                        ["Primary fiscal balance / GDP",           "0.10", "A→Q",
                         "IMF DataMapper: pb (annual, forward-filled quarterly)",
                         "negative — surplus reduces stress"],
                        ["Structural balance / potential GDP",      "0.05", "A→Q",
                         "IMF DataMapper: GGCB_G01_PGDP_PT (annual, forward-filled quarterly)",
                         "negative"],
                        ["Government revenue / GDP",               "0.10", "A→Q",
                         "World Bank: GC.REV.XGRT.GD.ZS (annual, forward-filled quarterly)",
                         "negative — higher revenue capacity reduces stress"],
                    ]
                ),
                _note("Z-scores use a 40-quarter rolling window for quarterly components "
                      "and a 10-year rolling window for annual components.  "
                      "shift(1) look-back is applied before computing rolling statistics "
                      "to prevent look-ahead bias."),
                _sub("Staleness handling (three gaps)"),
                _p("Gap 1 — Exponential weight decay: a component that has not updated for "
                   "k quarters beyond its expected release window (Q: 1 quarter lag, "
                   "A: 4 quarters lag) loses weight as 0.5^(k_excess / half_life) "
                   "where half_life = 4 quarters.  A component whose effective weight falls "
                   "below 20% of its nominal weight is dropped entirely."),
                _p("Gap 2 — Carry cap: a component carried beyond max_carry_quarters (4) "
                   "is zeroed and displayed as a BLANK row with the last known value and "
                   "the carry expiry date.  The overall composite is null if retained "
                   "weight falls below 60% of the basket."),
                _p("Gap 3 — Extrapolation gate: a model-based extrapolation (rolling mean or "
                   "linear trend) is available but disabled by default.  Enable in "
                   "config/longterm_stress.yaml."),
                _note("The staleness mechanisms in Debt Stress are independent from and more "
                      "conservative than the regime composite staleness decay."),
                _inline_formula(F("Rolling Z-score (quarterly components)")),
                _inline_formula(F("Rolling Z-score (annual components → quarterly)")),
                _inline_formula(F("Staleness weight decay")),
                _inline_formula(F("Aggregate stress score")),
                _inline_formula(F("Stress band labels")),
            ], title="9 · Long-Term Debt Stress"),

            # 10 ── Data Quality Flags ──────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "10 · Data Quality Flags",
                    [
                        "Every signal carries quality flags checked at pipeline time and shown "
                        "as badges in the drill-down tables.",
                        "is_stale: latest observation is older than the expected release window "
                        "(M: 90 days, Q: 200 days, A: 600 days). obs_date is the period start "
                        "so thresholds include provider lag. Effect: excluded from composite.",
                        "is_proxy: signal approximates a concept but is not the ideal direct "
                        "measure. Shown as PROXY badge; included unless also stale.",
                        "is_constructed: derived by the pipeline from two or more raw series. "
                        "Shown as CNST badge; no impact on composite inclusion.",
                        "low_history: fewer than 15 observations available. Excluded from composite.",
                        "vintage_available: point-in-time vintages exist (FRED only). Enables "
                        "look-ahead-free back-testing in Phase 3.",
                        "The Data Quality Log panel on the Regime Map page lists every signal "
                        "with at least one active flag.",
                    ],
                    tables=[(
                        ["Flag", "Set when", "Effect"],
                        [
                            ["is_stale",          "Latest obs older than expected release window (M:90d, Q:200d, A:600d)",
                             "Excluded from composite; staleness decay continues"],
                            ["is_proxy",          "Signal approximates but is not the ideal direct measure",
                             "PROXY badge; included unless also stale"],
                            ["is_constructed",    "Derived by pipeline from two or more raw series",
                             "CNST badge; no impact on inclusion"],
                            ["low_history",       "Fewer than 15 observations available",
                             "Excluded from composite; Z-score unreliable"],
                            ["vintage_available", "Point-in-time vintages exist (FRED only)",
                             "Enables look-ahead-free back-testing in Phase 3"],
                        ]
                    )],
                )),
                _p("Every signal carries quality flags.  These are checked at pipeline "
                   "time and shown as badges in the drill-down tables."),
                _table(
                    ["Flag", "Set when", "Effect"],
                    [
                        ["is_stale",         "Latest observation is older than the expected release window "
                                             "(M: 90 days, Q: 200 days, A: 600 days).  "
                                             "Note: obs_date is the period start, not the publication date, "
                                             "so thresholds include provider lag.",
                         "Excluded from composite; staleness decay continues to reduce weight in "
                         "forward-fill scenarios"],
                        ["is_proxy",         "Signal approximates a concept but is not the ideal direct measure",
                         "Shown as PROXY badge; included in composite unless also stale"],
                        ["is_constructed",   "Derived by the pipeline from two or more raw series",
                         "Shown as CNST badge; no impact on composite inclusion"],
                        ["low_history",      "Fewer than 15 observations available",
                         "Excluded from composite; Z-score unreliable over short histories"],
                        ["vintage_available","Point-in-time vintages exist (FRED only)",
                         "Enables look-ahead-free back-testing in Phase 3"],
                    ]
                ),
                _sub("Data Quality Log"),
                _p("The Data Quality Log panel (collapsed by default on the Regime Map page) "
                   "lists every signal with at least one active flag so you can assess the "
                   "reliability of the current reading at a glance."),
            ], title="10 · Data Quality Flags"),

            # 11 ── Country Coverage ────────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "11 · Country Coverage & Rollout",
                    [
                        "Current coverage: United States only (Phase 1). Phase 2 will roll out "
                        "Eurozone first, then Japan, UK, South Korea, China, India, Brazil, "
                        "Saudi Arabia, and Russia.",
                        "Each country requires: binding instantiation → series ID verification "
                        "against the provider's metadata endpoint → spot-check vs. a public "
                        "reference → vintage_available set honestly → human sign-off. "
                        "No country is considered active until all checks pass.",
                        "NBS China and Rosstat/CBR Russia automated pulls are deferred; "
                        "World Bank / IMF harmonised data will be used with explicit gap flags.",
                    ],
                )),
                _p("Current coverage: United States only (Phase 1).  Phase 2 will roll out "
                   "Eurozone first, then Japan, UK, South Korea, China, India, Brazil, "
                   "Saudi Arabia, and Russia."),
                _p("Each country requires: binding instantiation → series ID verification "
                   "against the provider's metadata endpoint → spot-check vs. a public "
                   "reference → vintage_available set honestly → human sign-off.  "
                   "No country is considered active until all checks pass."),
                _note("NBS China and Rosstat/CBR Russia automated pulls are deferred; "
                      "World Bank / IMF harmonised data will be used with explicit gap flags."),
            ], title="11 · Country Coverage & Rollout"),

            # 12 ── Weight Calibration & Audit ─────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "12 · Weight Calibration & Audit",
                    [
                        "Three audit calculations check that configured importance values are "
                        "internally consistent. They are accessible on the Weight Audit page "
                        "(/weight-audit) and can be re-triggered at any time with the Re-run button.",
                        "Force Balance — checks that the total pre-normalisation weight mass of "
                        "the Growth basket and Inflation basket are roughly equal. "
                        "Mass = Σ(base_share × importance × quality_factor) for each basket. "
                        "Target ratio G/I: 0.75 – 1.33. "
                        "Triggered automatically on every pipeline Pass 5 (composites run) "
                        "and logged as [BALANCE] INFO or [BALANCE] WARN per country.",
                        "Correlation Audit — computes pairwise Pearson r of monthly Z-score "
                        "histories for all signals in each basket. Pairs with |r| > 0.80 in the "
                        "same basket violate the anti-redundancy rule: the secondary signal's "
                        "importance must be reduced to ≤40% of the primary's to avoid "
                        "double-counting correlated information. "
                        "Triggered automatically on pipeline Pass 5 after each country upsert "
                        "and logged as [CORR AUDIT] INFO or [CORR AUDIT] WARN.",
                        "Monte Carlo Sensitivity — holds the latest Z-scores fixed and perturbs "
                        "each signal's importance by N(0, 15%) multiplicatively across 500 trials, "
                        "recomputing growth and inflation scores each time. The scatter cloud and "
                        "donut chart show the resulting regime label distribution. "
                        "On-demand only — not run in the pipeline. "
                        "How to interpret: if ≥80% of trials confirm the base reading, the "
                        "regime label is robust to weight uncertainty. If the cloud straddles a "
                        "boundary or the donut splits across two regimes, the reading is fragile "
                        "and should be qualified (e.g. note low confidence or near-zero scores). "
                        "Current output is informational — the action is to manually review and "
                        "adjust importance values in {cc}_composites.yaml for signals that are "
                        "pulling the scatter toward the wrong quadrant. Phase 3B (calibrate.py) "
                        "will automate importance optimization against historical regime labels.",
                    ],
                    tables=[(
                        ["Audit", "Trigger", "Output", "Action threshold"],
                        [
                            ["Force Balance",
                             "Pipeline Pass 5 (auto) + Weight Audit page (on-demand)",
                             "[BALANCE] log line; Weight Audit bar chart",
                             "G/I ratio outside 0.75–1.33 → adjust base_share or importance"],
                            ["Correlation Audit",
                             "Pipeline Pass 5 after each country upsert (auto) + Weight Audit page",
                             "[CORR AUDIT] log line; heatmap + flagged-pairs table",
                             "|r| > 0.80 same basket → secondary importance ≤ 40% of primary"],
                            ["Monte Carlo",
                             "Weight Audit page only (on-demand)",
                             "Scatter + donut (500 trials, ±15% importance)",
                             "< 80% same-quadrant confirmation → review importance values"],
                        ]
                    )],
                )),
                _p("Three audit calculations verify that configured importance values are "
                   "internally consistent.  All three are accessible on the Weight Audit "
                   "page (/weight-audit) and can be re-triggered at any time with the "
                   "↺ Re-run button."),
                _sub("1 — Force Balance"),
                _p("Checks that the total pre-normalisation weight mass of the Growth basket "
                   "and Inflation basket are roughly equal.  "
                   "Mass = Σ(base_share × importance × quality_factor) for each basket.  "
                   "Target ratio G/I: 0.75 – 1.33.  A ratio outside this range means one "
                   "force has been over-configured relative to the other before normalisation."),
                _note("Trigger: runs automatically on every pipeline Pass 5 (composites run), "
                      "logged as [BALANCE] INFO (OK) or [BALANCE] WARN (out of range) per country.  "
                      "Also computed on-demand when the Weight Audit page loads or Re-run is clicked."),
                _p("Action: if the ratio is out of range, adjust base_share or importance on "
                   "the lighter basket's signals, or add signals to it."),
                _sub("2 — Correlation Audit"),
                _p("Computes pairwise Pearson r of monthly Z-score histories for all signals "
                   "in each basket.  The anti-redundancy rule requires that for any same-basket "
                   "pair with |r| > 0.80, the secondary signal's importance must be ≤ 40% of "
                   "the primary's.  Without this constraint, two highly correlated signals "
                   "each at PRIMARY importance would effectively double-count the same "
                   "macroeconomic signal."),
                _note("Trigger: runs automatically on pipeline Pass 5 after each country upsert "
                      "(audit_signal_correlations()), logged as [CORR AUDIT] WARN for flagged pairs.  "
                      "Full matrix computed on-demand in Weight Audit page with min_periods=24 months."),
                _p("Action: for each flagged pair, identify which signal is the primary anchor "
                   "and reduce the secondary's importance.  Examples applied: cpi_core→STRONG "
                   "(was PRIMARY, r≈0.92 with pce_core); breakeven_10y→VOLATILE "
                   "(r≈0.90 with breakeven_5y)."),
                _sub("3 — Monte Carlo Sensitivity"),
                _p("Holds the latest Z-scores fixed and perturbs each signal's importance by "
                   "N(0, 15%) multiplicatively across 500 trials, recomputing normalised growth "
                   "and inflation scores each time.  The results show how much the regime label "
                   "depends on the specific importance values chosen."),
                _note("Trigger: on-demand only — not part of the pipeline.  Runs when the "
                      "Weight Audit page loads or Re-run is clicked (~1–2 seconds for 500 trials)."),
                _p("How to interpret the outputs:"),
                _table(
                    ["Output", "What it shows", "Healthy reading"],
                    [
                        ["Scatter cloud",
                         "Each dot is one trial; colour = quadrant. "
                         "A tight cluster means the composite is stable across weight uncertainty.",
                         "Cloud contained within one quadrant"],
                        ["Donut chart",
                         "Percentage of trials landing in each regime label.",
                         "≥ 80% in the base quadrant"],
                        ["Caption %",
                         "Share of trials confirming the unperturbed (base) quadrant.",
                         "≥ 80% confirms a robust reading; < 60% is fragile"],
                    ]
                ),
                _p("How to act on the output: a fragile reading (scatter straddling a boundary, "
                   "donut split across two regimes) means the current regime label is sensitive "
                   "to weight assumptions.  Inspect which signals are near zero and whether "
                   "their importance tier is justified.  Adjust importance in "
                   "config/countries/{cc}_composites.yaml and re-run."),
                _note("Current use: informational + manual config tuning."),
                _table(
                    ["Audit", "Trigger", "Output", "Action threshold"],
                    [
                        ["Force Balance",
                         "Pipeline Pass 5 (auto) + Weight Audit on-demand",
                         "Bar chart + [BALANCE] log",
                         "G/I ratio outside 0.75–1.33"],
                        ["Correlation Audit",
                         "Pipeline Pass 5 (auto) + Weight Audit on-demand",
                         "Heatmap + flagged-pairs table + [CORR AUDIT] log",
                         "|r| > 0.80 in same basket"],
                        ["Monte Carlo",
                         "Weight Audit on-demand only",
                         "Scatter + donut (500 trials, ±15%)",
                         "< 80% same-quadrant confirmation"],
                    ]
                ),
                _sub("4 — Importance Editor"),
                _p("The Weight Audit page (/weight-audit) provides an in-browser editor for "
                   "signal importance values. All signals for the selected country are shown in "
                   "a table with their current importance, tier, base_share, and quality_factor. "
                   "Editing the importance column immediately updates the live G/I ratio preview. "
                   "A mandatory Reason field must be filled before saving — every change is "
                   "written to both the YAML file (config/countries/{cc}_composites.yaml) and "
                   "the weight_change_log table in DuckDB."),
                _note("Trigger: manual only — the user edits values and clicks Save. "
                      "YAML comment annotations (tier labels, CORR AUDIT flags) are preserved "
                      "line-by-line; PyYAML is not used to avoid stripping inline comments."),
                _sub("5 — GDP-Regression Calibration (Growth basket)"),
                _p("The calibration tool (indicators/calibrate.py) regresses each growth signal's "
                   "Z-score against the real GDP Z-score ({cc}.master.gdp_real) using OLS "
                   "to derive empirically grounded importance weights. "
                   "Monthly signals are resampled to quarterly mean before regression. "
                   "Signals with an invert=True flag are negated so all betas are directionally "
                   "consistent with GDP."),
                _p("Methodology:"),
                _table(
                    ["Step", "Detail"],
                    [
                        ["OLS",              "linregress(signal_z_quarterly, gdp_z_quarterly)"],
                        ["Positive filter",  "Signals with β ≤ 0 receive no recommendation — "
                                             "user decides whether to adjust manually (Option B)"],
                        ["Normalise",        "Positive betas → contribution_share = β / Σ(β⁺)"],
                        ["Scale",            "contribution_share / max_share × 0.95, floor 0.10 "
                                             "→ maps naturally onto the PRIMARY–VOLATILE importance range"],
                        ["Output",           "Table: β, R², p-value, contribution_share, "
                                             "recommended_imp, current_importance, Δ"],
                    ]
                ),
                _note("The regression is advisory — results are displayed in the UI and the user "
                      "chooses which signals to update. 'Apply Selected' populates the Importance "
                      "Editor for review; the user then confirms with Save. "
                      "Minimum 20 common quarterly observations required to run regression on a signal."),
                _sub("6 — Weight Change History"),
                _p("Every importance change saved from the editor is logged to the "
                   "weight_change_log DuckDB table with: timestamp, country, signal, basket, "
                   "old value, new value, delta, source (manual / regression), and user reason. "
                   "The Weight History page (/weight-history) presents this log as a browsable, "
                   "filterable table. The Reason column is editable — click Save Notes to "
                   "update or add reasoning at any time after the fact."),
                _note("This log is the audit trail for all human judgement calls on importance. "
                      "It is stored in DuckDB and persists across sessions and container rebuilds."),
            ], title="12 · Weight Calibration & Audit"),

            # 13 ── Deferred & Out of Scope ─────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "13 · Deferred Items",
                    ["Items deferred out of the current scope."],
                    tables=[(
                        ["Item", "Status"],
                        [
                            ["Risk-parity weighting, portfolio construction", "Out of scope — Allocation Layer project"],
                            ["WB WGI governance scores (Lens H)", "Deferred — WB v2 API deleted these series"],
                            ["EM-DAT disaster losses (Lens I)",   "Deferred — slot built, binding empty"],
                            ["ADF stationarity tests on debt ratios (B3)", "Planned — diagnostic only"],
                            ["Rolling-window sensitivity grid (C3, K1)",   "Phase 3 back-test"],
                            ["Expanding-window Z-scores for back-test (C4)", "Phase 3 back-test"],
                            ["OLS weight calibration (I1)",        "✅ Live — indicators/calibrate.py; advisory, user confirms changes"],
                            ["Dynamic momentum windows (D2)",      "Phase 3 — requires regime labels as input"],
                        ]
                    )],
                )),
                _table(
                    ["Item", "Status"],
                    [
                        ["Risk-parity weighting, portfolio construction", "Out of scope — Allocation Layer project"],
                        ["WB WGI governance scores (Lens H)", "Deferred — WB v2 API deleted these series"],
                        ["EM-DAT disaster losses (Lens I)",   "Deferred — slot built, binding empty"],
                        ["ADF stationarity tests on debt ratios (B3)", "Planned — diagnostic only"],
                        ["Rolling-window sensitivity grid (C3, K1)",   "Phase 3 back-test"],
                        ["Expanding-window Z-scores for back-test (C4)", "Phase 3 back-test"],
                        ["OLS weight calibration (I1)",        "Deferred — overfitting risk before Phase 3"],
                        ["Dynamic momentum windows (D2)",      "Phase 3 — requires regime labels as input"],
                    ]
                ),
            ], title="13 · Deferred Items"),

        ], start_collapsed=True, always_open=True),

    ], className="pe-2 pt-1", style={"maxWidth": "1100px", "margin": "0 auto"})

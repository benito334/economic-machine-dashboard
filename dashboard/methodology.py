"""Methodology page for the Dash dashboard.

Prose-level explanation of every calculation step, intended for an auditor or
a new contributor who wants to understand how the numbers are produced.  The
companion page at /formulas shows the same content in mathematical notation
(equations pulled live from the active config).
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section(title: str, *children) -> html.Div:
    return html.Div([
        html.H3(title, style={
            "fontSize": "1.1rem", "fontWeight": "700",
            "borderBottom": "1px solid var(--border-color)",
            "paddingBottom": "6px", "marginTop": "28px", "marginBottom": "12px",
        }),
        *children,
    ])


def _sub(title: str, *children) -> html.Div:
    return html.Div([
        html.H4(title, style={
            "fontSize": "0.92rem", "fontWeight": "700",
            "color": "var(--muted-color)", "marginTop": "14px", "marginBottom": "6px",
        }),
        *children,
    ])


def _p(text: str, **style) -> html.P:
    return html.P(text, style={"fontSize": "0.85rem", "lineHeight": "1.6",
                                "color": "var(--font-color)", **style})


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


def _card(*children) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(list(children)),
        style={
            "backgroundColor": "var(--card-bg)",
            "borderColor": "var(--border-color)",
            "marginBottom": "16px",
        },
    )


# ── Page layout ───────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div([

        # ── Header ───────────────────────────────────────────────────────────
        html.Div([
            html.H2("Methodology", style={"fontSize": "1.4rem", "marginBottom": "4px"}),
            html.P(
                "How every number on this dashboard is produced — from raw API response "
                "to regime quadrant.  Cross-reference with the Formula Reference (ƒ) for "
                "the exact equations and live parameter values.",
                style={"color": "var(--muted-color)", "fontSize": "0.83rem"},
            ),
        ], className="pt-3 pb-1"),

        dbc.Accordion([

            # 1 ── Overview ───────────────────────────────────────────────────
            dbc.AccordionItem([
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

            # 2 ── Data Sources ────────────────────────────────────────────────
            dbc.AccordionItem([
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

            # 3 ── Signal Transformation ──────────────────────────────────────
            dbc.AccordionItem([
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

            # 4 ── Force Z-Score ───────────────────────────────────────────────
            dbc.AccordionItem([
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
                _sub("Rolling-window mode (configurable in ⚙ Settings)"),
                _p("Z_rolling = clip( (x − μ_N) / σ_N , −4, 4 )  where μ_N and σ_N are "
                   "computed over the most recent N months.  Recommended window: 36–60 months "
                   "(3–5 years).  This makes the score more responsive to structural regime "
                   "changes — for example, treating the low-inflation 2010s as the baseline "
                   "rather than the inflationary 1970s-80s."),
                _note("Guidance (from docs/feedback/time-horizon_Z-Scores guidance.md): "
                      "force Z-scores should use 36–60 months for monthly data; "
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
            ], title="4 · Force Z-Score"),

            # 5 ── Momentum ───────────────────────────────────────────────────
            dbc.AccordionItem([
                _p("Two complementary momentum metrics are shown in the regime summary strip."),

                _sub("Δ MoM — month-on-month change in force score"),
                _p("The raw difference between the current composite force score and the "
                   "previous period's score.  Positive = force is intensifying; "
                   "negative = force is easing.  Quick to compute and easy to interpret, "
                   "but scales differ across series with different volatility."),

                _sub("Momentum Z — Z-score of recent force-score changes"),
                _p("Z-score of the current MoM delta against the distribution of MoM deltas "
                   "over the preceding 12 months.  Answers: 'is today's rate of change "
                   "unusually fast or slow compared with recent history?'  "
                   "A high positive Momentum Z means the force is accelerating at a "
                   "historically unusual pace; a large negative value means it is decelerating "
                   "sharply.  This is the metric recommended in the time-horizon guidance."),
                _note("Guidance: momentum Z-scores should use a 6–12 month rolling window "
                      "for monthly data; the current implementation uses 12 months."),

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
            ], title="5 · Momentum"),

            # 6 ── Dynamic Force Weighting ─────────────────────────────────────
            dbc.AccordionItem([
                _p("Each composite component carries a configured nominal weight plus two "
                   "dynamic adjustments applied at runtime.  All parameters are tunable in "
                   "config/composites.yaml."),

                _sub("Nominal weight"),
                _p("w_cfg = base_share × importance × quality_factor, then normalised to "
                   "sum to 1.0 within each force basket.  "
                   "base_share encodes the group-level multiplier (labour market ×0.75, "
                   "output/demand ×1.00, capacity ×1.05).  "
                   "importance is the primary judgement dial (0–1); tune it here when you "
                   "believe a signal should carry more or less weight.  "
                   "quality_factor reflects data quality concerns — lower for proxy or "
                   "indirect measures."),

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

                _sub("Effective weight"),
                _p("w_eff = w_cfg × w_momentum × w_decay, renormalised over the active "
                   "signal set.  The component table in Regime History shows the colour-coded "
                   "effective weight: orange = reduced by decay/carry expiry, "
                   "green = boosted by momentum agreement, yellow = reduced by conflict."),
            ], title="6 · Dynamic Force Weighting"),

            # 7 ── Composite Construction ──────────────────────────────────────
            dbc.AccordionItem([
                _p("The Growth Score and Inflation Score are the weighted means of their "
                   "respective component Z-scores, after dynamic weight adjustments."),

                _table(
                    ["Metric", "Formula", "Notes"],
                    [
                        ["Growth Score",
                         "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for growth signals",
                         "unemployment is inverted (lower = better growth); "
                         "9 signals in active set"],
                        ["Inflation Score",
                         "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for inflation signals",
                         "8 signals; breakeven_5y and breakeven_10y each carry 0.5 base_share "
                         "to avoid double-counting"],
                        ["Confidence",
                         "½ × (N_G_agree / N_G + N_I_agree / N_I)",
                         "Fraction of active signals whose direction is consistent with the "
                         "composite sign; averaged across both forces"],
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
            ], title="7 · Composite Construction"),

            # 8 ── Regime Classification ───────────────────────────────────────
            dbc.AccordionItem([
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

            # 9 ── Long-Term Debt Stress ───────────────────────────────────────
            dbc.AccordionItem([
                _p("The Debt Stress indicator aggregates seven measures of long-run debt "
                   "sustainability into a single quarterly composite.  It is separate from "
                   "the regime composite and does not feed into the quadrant classification."),
                _table(
                    ["Component", "Source", "Window"],
                    [
                        ["Total debt / GDP",         "FRED (derived)", "40 quarters"],
                        ["Household debt / GDP",     "FRED (HDTGPDUSQ163N)", "40 quarters"],
                        ["Corporate debt / GDP",     "FRED (BCNSDODNS + GDP)", "40 quarters"],
                        ["Federal deficit / GDP",    "FRED (FYFSD + GDP)", "40 quarters"],
                        ["Federal interest / GDP",   "FRED (FYOINT + GDP)", "40 quarters"],
                        ["Net international investment position / GDP", "BEA via FRED", "40 quarters"],
                        ["Debt service ratio",       "BIS / FRED proxy", "40 quarters"],
                    ]
                ),
                _sub("Staleness handling (three gaps)"),
                _p("Gap 1 — Exponential weight decay: a component that has not updated for "
                   "k quarters beyond its expected release loses weight as 0.5^(k/half_life) "
                   "where half_life = 4 quarters by default."),
                _p("Gap 2 — Carry cap: a component carried beyond max_carry_quarters (4) "
                   "is zeroed and displayed as a BLANK row with the last known value and "
                   "the carry expiry date."),
                _p("Gap 3 — Extrapolation gate: a model-based extrapolation (rolling mean or "
                   "linear trend) is available but disabled by default.  Enable in "
                   "config/longterm_stress.yaml."),
                _note("The staleness mechanisms in Debt Stress are independent from and more "
                      "conservative than the regime composite staleness decay."),
            ], title="9 · Long-Term Debt Stress"),

            # 10 ── Data Quality Flags ─────────────────────────────────────────
            dbc.AccordionItem([
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

            # 11 ── Country Coverage ───────────────────────────────────────────
            dbc.AccordionItem([
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

            # 12 ── Deferred & Out of Scope ────────────────────────────────────
            dbc.AccordionItem([
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
            ], title="12 · Deferred Items"),

        ], start_collapsed=True, always_open=True),

    ], className="pe-2 pt-1", style={"maxWidth": "1100px", "margin": "0 auto"})

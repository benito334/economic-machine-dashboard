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
from dashboard.global_overview import CYCLE_HEALTH_DEFAULT_CONFIG, _cycle_config_clipboard_text


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


# ── Regime input-flow diagram (theme-adaptive, built from styled boxes) ───────

_FLOW_BLUE = "#4C9BE8"
_FLOW_AMBER = "#E8A317"


def _flow_box(label: str, sublabel: str | None = None, accent: str | None = None,
              dashed: bool = False, strong: bool = False):
    border_style = "dashed" if dashed else "solid"
    border_col = accent or "var(--muted-color)"
    style = {
        "border": f"{'2px' if strong else '1px'} {border_style} {border_col}",
        "borderRadius": "8px",
        "padding": "8px 12px",
        "background": (f"{accent}26" if (accent and not dashed) else "transparent"),
        "color": "var(--font-color)",
        "fontSize": "0.8rem",
        "textAlign": "center",
        "minWidth": "118px",
        "lineHeight": "1.35",
    }
    children = [html.Div(label, style={"fontWeight": "600" if strong else "500"})]
    if sublabel:
        children.append(html.Div(sublabel, style={
            "fontSize": "0.68rem", "color": "var(--muted-color)", "marginTop": "1px"}))
    return html.Div(children, style=style)


def _flow_arrow(label: str | None = None, dashed: bool = False):
    arrow = html.Span("→", style={
        "fontSize": "1.2rem", "color": "var(--muted-color)",
        "opacity": "0.6" if dashed else "1"})
    if not label:
        return html.Div(arrow, style={"padding": "0 6px", "alignSelf": "center"})
    return html.Div([
        arrow,
        html.Div(label, style={"fontSize": "0.62rem", "color": "var(--muted-color)"}),
    ], style={"padding": "0 6px", "textAlign": "center", "alignSelf": "center"})


def _regime_input_flow() -> html.Div:
    _row = {"display": "flex", "flexWrap": "wrap", "alignItems": "center", "gap": "6px"}
    return html.Div([
        html.Div([
            html.Div([
                _flow_box("Growth score", "+ momentum", _FLOW_BLUE),
                _flow_box("Inflation score", "+ momentum", _FLOW_BLUE),
            ], style={"display": "flex", "flexDirection": "column", "gap": "6px"}),
            _flow_arrow("classified"),
            _flow_box("Regime category", "growth + inflation chips", _FLOW_BLUE, strong=True),
        ], style=_row),
        html.Div([
            _flow_box(
                "Dynamic mode only  —  bends the ± thresholds",
                "credit tightness · composite noise · country volatility",
                _FLOW_AMBER),
            _flow_arrow("adjusts the cutoffs", dashed=True),
            html.Span("(never enters the score)", style={
                "fontSize": "0.68rem", "color": "var(--muted-color)",
                "fontStyle": "italic", "alignSelf": "center"}),
        ], style={**_row, "marginTop": "12px"}),
        html.Div("Computed and shown, but not part of the regime label:", style={
            "fontSize": "0.72rem", "color": "var(--muted-color)", "margin": "14px 0 6px"}),
        html.Div([
            _flow_box("Rate score", dashed=True),
            _flow_box("Market volatility", dashed=True),
            _flow_box("Debt stress", dashed=True),
            _flow_box("Cycle Health Index", dashed=True),
        ], style=_row),
        html.Div([
            html.Span("■ ", style={"color": _FLOW_BLUE}),
            html.Span("feeds the label   ", style={"fontSize": "0.68rem", "color": "var(--muted-color)"}),
            html.Span("■ ", style={"color": _FLOW_AMBER}),
            html.Span("bends thresholds (dynamic only)   ", style={"fontSize": "0.68rem", "color": "var(--muted-color)"}),
            html.Span("▢ ", style={"color": "var(--muted-color)"}),
            html.Span("shown, not in label", style={"fontSize": "0.68rem", "color": "var(--muted-color)"}),
        ], style={"marginTop": "12px"}),
    ], style={
        "border": "1px solid var(--border-color)", "borderRadius": "10px",
        "padding": "16px", "margin": "8px 0 4px", "background": "var(--card-bg)",
    })


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
                            ["Force",          "One of the five fundamental economic forces: Growth, Inflation, Policy, Credit/Debt, External/Trade"],
                            ["Signal",         "A single normalised, time-stamped indicator observation for a given country and force"],
                            ["Composite",      "Weighted mean Z-score across the signals that belong to Growth or Inflation"],
                            ["Growth Regime",  "Growth / Transition / Retraction — classified by configurable Z and momentum thresholds"],
                            ["Inflation Regime","Inflation / Transition / Disinflation — classified independently using the same dual-condition logic"],
                            ["Vintage",        "A point-in-time API snapshot (available for FRED series only)"],
                        ]
                    )],
                )),
                _p(
                    "This tool is a diagnostic, cross-country macro-regime dashboard in the "
                    "Ray Dalio 'Economic Machine' tradition.  It ingests macroeconomic data "
                    "from free/open APIs, normalises each series into a standardised signal, "
                    "classifies each economy into two independent regime dimensions (Growth and "
                    "Inflation), and presents a multi-panel diagnostic terminal."
                ),
                _p(
                    "It is a diagnostic tool, not an allocator.  No portfolio construction, "
                    "risk-parity weights, or trade recommendations are produced here.  Those "
                    "belong to the separate Allocation Layer project."
                ),
                _table(
                    ["Concept", "Definition"],
                    [
                        ["Force",           "One of the five fundamental economic forces: Growth, Inflation, Policy, Credit/Debt, External/Trade"],
                        ["Signal",          "A single normalised, time-stamped indicator observation for a given country and force"],
                        ["Composite",       "Weighted mean Z-score across the signals that belong to Growth or Inflation"],
                        ["Growth Regime",   "Growth / Transition / Retraction — classified by configurable Z and momentum thresholds"],
                        ["Inflation Regime","Inflation / Transition / Disinflation — classified independently using the same dual-condition logic"],
                        ["Vintage",         "A point-in-time API snapshot (available for FRED series only)"],
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
                            ["FRED (St. Louis Fed)",  "US macro — GDP, PCE, payrolls, rates, spreads, TIPS breakevens", "FRED_API_KEY env var"],
                            ["World Bank API v2",     "Cross-country annual — trade, FDI, debt, demographics, R&D", "None"],
                            ["IMF DataMapper",        "Cross-country annual — fiscal balances, structural indicators", "None"],
                            ["Eurostat JSON stats API", "Euro area — industrial production, retail sales, unemployment, capacity, fiscal (monthly/quarterly)", "None"],
                            ["ECB SDW (SDMX-JSON 1.0)", "Euro area — Maastricht long-term interest rates (IRS flow)", "None"],
                            ["OECD SDMX REST",        "Cross-country — harmonised CPI, unemployment; some endpoints 404 in this env", "None"],
                        ]
                    )],
                )),
                _p("Data is fetched from open/free APIs on first use and cached locally. "
                   "Subsequent runs read from the cache; live network calls only occur when "
                   "the pipeline is re-run with --latest."),
                _table(
                    ["Provider", "Scope", "Auth"],
                    [
                        ["FRED (St. Louis Fed)",    "US macro — GDP, PCE, payrolls, rates, spreads, TIPS breakevens", "FRED_API_KEY env var"],
                        ["World Bank API v2",       "Cross-country annual — trade, FDI, debt, demographics, R&D", "None"],
                        ["IMF DataMapper",          "Cross-country annual — fiscal balances, structural indicators", "None"],
                        ["Eurostat JSON stats API", "Euro area — industrial production, retail sales, unemployment, "
                                                    "capacity utilisation, fiscal Q flows.  "
                                                    "Correct geo codes: EA21 (unemployment), EA20 (all others).",
                         "None"],
                        ["ECB SDW (SDMX-JSON 1.0)", "Euro area — Maastricht long-term interest rates.  "
                                                     "series_id format: FLOW/KEY (e.g. IRS/M.DE.L.L40.CI.0000.EUR.N.Z).  "
                                                     "BOP/current-account flows return HTTP 400 and are unresolvable from free APIs.",
                         "None"],
                        ["OECD SDMX REST",          "Partially available; some country/dataset endpoints return 404 in this env.", "None"],
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
                        "Independent rolling windows — Growth and Inflation have separate sliders: "
                        "Growth: Full / 36m / 48m / 60m. "
                        "Inflation: Full / 60m / 90m / 120m. "
                        "Inflation uses longer windows because price levels are slower-moving "
                        "structural processes; a 60m growth window and a 90m inflation window "
                        "may be appropriate simultaneously. "
                        "Both sliders are persisted in localStorage and work on any page.",
                        "Rolling Z-scores are pre-computed at pipeline time for all window variants "
                        "and stored as zscore_36m...zscore_120m on the signals table. "
                        "The Force Component Inputs table (Regime History) and Signals page "
                        "per-signal Z-bars both reflect the active slider selection.",
                        "Outlier cap: Z-scores are clipped to ±4σ. COVID-era extremes in payrolls "
                        "and GDP would otherwise reach ±20+.",
                        "Low-history flag: signals with fewer than 15 observations are flagged "
                        "low_history=True and excluded from composites.",
                    ],
                    tables=[(
                        ["Force", "Available windows", "Pre-computed DB columns", "Rationale"],
                        [
                            ["Growth",    "Full / 36m / 48m / 60m",   "zscore_36m, zscore_48m, zscore_60m",          "3–5 year window captures a full business cycle"],
                            ["Inflation", "Full / 60m / 90m / 120m",  "zscore_60m, zscore_90m, zscore_120m",         "Longer lookback suits slower structural price trends"],
                        ]
                    )],
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
                _sub("Independent rolling windows"),
                _p("Growth and Inflation have separate lookback controls so they can be "
                   "calibrated independently.  The Growth slider (Full / 36m / 48m / 60m) "
                   "controls the X-axis of the scatter plot, the Growth Force Z chart, and the "
                   "Growth rows in the component table.  The Inflation slider (Full / 60m / 90m / "
                   "120m) controls the Y-axis and Inflation rows.  Both persist in localStorage "
                   "across page navigation."),
                _table(
                    ["Force", "Available windows", "Pre-computed DB columns", "Rationale"],
                    [
                        ["Growth",    "Full / 36m / 48m / 60m",
                         "zscore_36m, zscore_48m, zscore_60m (signals table); "
                         "growth_score_36m/48m/60m (composites table)",
                         "3–5 year window captures a full business cycle; "
                         "shorter = more regime-sensitive, longer = more stable"],
                        ["Inflation", "Full / 60m / 90m / 120m",
                         "zscore_60m, zscore_90m, zscore_120m (signals table); "
                         "inflation_score_60m/90m/120m (composites table)",
                         "Price levels are slower-moving structural processes; "
                         "longer windows prevent misreading cyclical dips as regime changes"],
                    ]
                ),
                _note("Per-signal Z-bars in the Force Component Inputs table (Regime History) "
                      "and the Signals page update live when the sliders change.  "
                      "Composite-level scores (scatter plot axes, force score strip) also update.  "
                      "Regime quadrant re-derives from the active rolling scores when either window is set."),
                _sub("Rolling Z formula"),
                _p("Z_rolling = clip( (x − μ_N) / σ_N , −4, 4 )  where μ_N and σ_N are the "
                   "mean and standard deviation over the most recent N months (with "
                   "min_periods = N/2 so values appear before the window fully fills).  "
                   "Pre-computed at pipeline time for all variants; no live recomputation on render."),
                _note("Guidance: 36–60m for Growth (monthly data); 60–120m for Inflation."),
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
                        "dynamic adjustments applied at runtime. Global methodology parameters "
                        "are in config/composites_policy.yaml. Per-country signal lists and "
                        "importance values are in config/countries/{cc}_composites.yaml.",
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
                   "dynamic adjustments applied at runtime.  Global methodology parameters "
                   "(decay, momentum, confidence, disequilibrium) are in "
                   "config/composites_policy.yaml.  Per-country signal lists and importance "
                   "values are in config/countries/{cc}_composites.yaml."),
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
                _p("w_decay = 0.5 ^ (age_months / half_life).  The half-life is set "
                   "per-signal in the composites config (half_life_months field) and defaults "
                   "to the global 3-month value when not specified.  The appropriate half-life "
                   "depends on how fast the underlying economic process moves, not just the "
                   "release frequency:"),
                _table(
                    ["Half-life", "Signal type", "Rationale"],
                    [
                        ["3 months",
                         "Monthly flow signals (Bank Loans, payrolls, CPI, etc.)",
                         "Global default.  Data refreshes every month; a 3-month-old reading "
                         "already tells a different story."],
                        ["4 months",
                         "Quarterly flow or fast-moving leading indicators "
                         "(Lending Standards, Corporate Debt Growth)",
                         "Released quarterly but track the short-term cycle; two missed "
                         "releases drops the signal to 25% weight, which is appropriate."],
                        ["6 months",
                         "Quarterly stock-ish measures (Debt Service Ratio)",
                         "Slow to change; retains 50% weight after two full quarters — "
                         "still relevant if one release is delayed."],
                        ["9 months",
                         "Quarterly structural stock measures "
                         "(Household Debt / GDP, Corporate Debt / GDP)",
                         "Very slow-moving balance-sheet ratios; a 9-month-old reading is "
                         "still informative.  Carry cap (9 months) zeroes the signal if data "
                         "is missing for three consecutive quarters."],
                        ["12 months",
                         "Annual signals (Gov Debt / GDP, WB/IMF annual series)",
                         "Retains 50% weight after one full release cycle.  Carry cap (15 months) "
                         "provides a 3-month grace period before zeroing."],
                    ]
                ),
                _note("Carry caps (M: 3 months, Q: 9, A: 15) are hard limits — once exceeded "
                      "the signal is zeroed regardless of half-life and appears as a BLANK row "
                      "in the component table.  The half-life and carry cap together define the "
                      "full staleness policy: the half-life governs gradual decay; the carry cap "
                      "governs hard exclusion."),
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
                             "unemployment is inverted; up to 12 configured signals "
                             "(9 cyclical + 3 long-run productivity-trend, added 2026-07-05)"],
                            ["Inflation Score",
                             "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for inflation signals",
                             "up to 7 configured; breakeven_avg (blended 5Y/10Y) at base_share=0.5; "
                             "pce_core/cpi_core at 1.0"],
                            ["Volatility Score",
                             "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for volatility signals",
                             "US: realized vol + VIX; EZ/KR: realized vol only (single-signal, "
                             "low-coverage). Added 2026-07-05 — does not feed the regime label "
                             "directly; see Section 8"],
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
                         "up to 12 configured signals (stale or low-history signals excluded at "
                         "runtime) — 9 cyclical signals reweighted 2026-07-05 via GDP-regression "
                         "calibration, plus 3 long-run productivity-trend signals (productivity, "
                         "TFP, R&D intensity) added the same day; see the basket table below"],
                        ["Inflation Score",
                         "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for inflation signals",
                         "up to 7 configured signals; breakeven_avg (blended mean of 5Y and 10Y "
                         "TIPS breakevens, merged 2026-07-05 to avoid double-counting market-implied "
                         "expectations) carries base_share = 0.5; "
                         "pce_core and cpi_core are anchors at base_share = 1.0"],
                        ["Volatility Score",
                         "Σ(w_eff_i × Z_adj_i) / Σ(w_eff_i)  for volatility signals",
                         "Added 2026-07-05. US: realized equity volatility (21-day rolling std of "
                         "S&P 500 log returns, annualized ×√252) plus VIX at bonus weight. EZ/KR: "
                         "realized volatility only, computed from a monthly share-price index "
                         "(12-month window, ×√12) since no free daily equity feed exists for "
                         "either — single-signal, low-coverage, directional-only. Does not feed "
                         "the Growth/Inflation regime label directly; see Section 8"],
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

                _sub("Interest Rate basket — US default importances"),
                _p("The Interest Rate composite (financial accommodation score) is built from "
                   "six policy-rate signals spanning the short and long ends of the nominal and "
                   "real yield curve.  All six use invert=true so that rising rates reduce the "
                   "accommodation score (positive score = easy money, negative = tight money).  "
                   "These are the default importance values; adjust via the Importance Editor "
                   "(Weight Audit page) without changing this file."),
                _table(
                    ["Signal", "Why it matters", "Default tier", "Importance", "Half-life"],
                    [
                        ["Fed Funds Target",
                         "Directly reflects the Fed's policy stance; any change immediately shifts "
                         "the short-term discount rate that feeds into all other rates. "
                         "It is the primary anchor for the policy basket.",
                         "PRIMARY", "0.95", "3 m"],
                        ["Fed Funds (effective)",
                         "Market-based short-term rate that incorporates expectations about the "
                         "policy stance and risk premia. It is the first observable price of the "
                         "policy lever.",
                         "PRIMARY", "0.88", "3 m"],
                        ["Real Fed Funds",
                         "Removes inflation expectations from the short-term rate, isolating the "
                         "pure discount-rate component that drives the present value of cash flows. "
                         "It adds a second perspective on the same underlying force, but with a "
                         "different emphasis.",
                         "STRONG", "0.75", "3 m"],
                        ["Yield 2Y (nominal)",
                         "Short-term market pricing of the policy rate over a horizon where "
                         "inflation expectations are still modest. It is useful for detecting "
                         "forward-looking tightening or easing, especially when the Fed's "
                         "balance-sheet actions are large.",
                         "STRONG", "0.70", "4 m"],
                        ["Rate Expectations (2Y − fed funds)",
                         "Front-end slope = the market-implied EXPECTED CHANGE in policy over ~2 "
                         "years (positive = pricing hikes, negative = pricing cuts), vs. the rate "
                         "LEVELS elsewhere in the basket. Added on Ray Dalio's advice (review A1) as "
                         "the forward-looking dimension, since free Fed-funds-futures aren't available "
                         "and the FOMC dot-plot has no Z-scoreable history. Kept CONTEXT-tier pending "
                         "Phase G backtest validation of its incremental value over the 2Y level.",
                         "CONTEXT", "0.45", "4 m"],
                        ["Real Yield 10Y",
                         "Long-term real rate that captures the market's view of the long-run "
                         "discount rate after stripping out inflation expectations. It is a key "
                         "driver of the valuation of long-duration assets and therefore a strong "
                         "anchor for the long end of the curve. Less volatile than the short end.",
                         "PRIMARY", "0.90", "6 m"],
                        ["Yield 10Y (nominal)",
                         "The raw long-term nominal rate embeds both the expected real rate and "
                         "inflation expectations. It is highly correlated with Real Yield 10Y, "
                         "so its incremental information is limited, but it provides a useful "
                         "cross-check on the real yield signal. Less volatile than the short end.",
                         "CONTEXT", "0.45", "6 m"],
                    ]
                ),
                _note("Yield-curve slope signals (10Y–2Y, 10Y–3M) and credit spreads (IG, HY) "
                      "carry distinct information about risk appetite and are not included in this "
                      "basket to avoid mixing rate-level and spread signals. They may be assigned "
                      "to the Credit basket in a future calibration."),

                _sub("Credit basket — US default importances"),
                _p("The Credit composite (credit health score) measures the availability and "
                   "sustainability of credit in the economy.  Positive score = healthy/expanding "
                   "credit; negative = stressed/contracting.  Debt-burden and leverage signals use "
                   "invert=true so that rising stress reduces the score.  Bank Loans is the flow "
                   "anchor; Lending Standards (supply) and Loan Demand (demand) are the paired "
                   "leading indicators — a healthy credit cycle needs both willing lenders and "
                   "willing borrowers; the stock measures add context on sustainability.  Corporate "
                   "Debt Outstanding Growth captures non-bank borrowers and complements bank loans.  "
                   "Corporate Debt / GDP (BIS quarterly) adds the stock-of-leverage lens.  These are "
                   "defaults, adjustable via the Importance Editor."),
                _table(
                    ["Signal", "Why it matters", "Default tier", "Importance", "Half-life"],
                    [
                        ["Bank Loans",
                         "Core measure of total private-sector credit supplied by banks — the most "
                         "direct gauge of credit growth or contraction. It drives the short-term "
                         "debt-cycle dynamics.",
                         "PRIMARY", "0.90", "3 m"],
                        ["Lending Standards (supply side)",
                         "Reflects the stringency of bank underwriting. Tightening standards usually "
                         "precede a slowdown in loan growth; loosening signals an expansion. It "
                         "provides early-warning information about the next phase of the credit cycle.",
                         "STRONG", "0.75", "4 m"],
                        ["Loan Demand (demand side)",
                         "SLOOS net % of banks reporting stronger demand for C&I loans — the borrower-"
                         "appetite counterpart to lending standards (Ray Dalio review 2026-07-05 #9). "
                         "A healthy credit cycle needs both willing lenders and willing borrowers; "
                         "demand contracting is early-cycle weakness. Not inverted (stronger demand = "
                         "healthier).",
                         "STRONG", "0.65", "4 m"],
                        ["Corporate Debt Outstanding Growth",
                         "Direct flow of new corporate issuance (or net change in nonfinancial "
                         "corporate debt, YoY%).  When issuance is strong the short-term debt cycle "
                         "is expanding; when it stalls or reverses, tightening is underway.  "
                         "Complements bank loans by capturing demand from non-bank borrowers.",
                         "STRONG", "0.65", "4 m"],
                        ["Debt Service Ratio",
                         "Shows the burden of servicing existing debt on corporate earnings or "
                         "household income. A rising ratio signals stress that can lead to slower "
                         "credit growth or higher defaults, adding context to current supply conditions.",
                         "CONTEXT", "0.45", "6 m"],
                        ["Household Debt / GDP",
                         "Measures the overall household debt load relative to the economy's output. "
                         "High levels can limit future borrowing capacity and affect the long-run "
                         "credit environment. It is more static but important for assessing sustainability.",
                         "CONTEXT", "0.40", "9 m"],
                        ["Corporate Debt / GDP",
                         "Captures the size of the non-bank corporate debt pile relative to the "
                         "economy (BIS quarterly series).  High levels signal elevated refinancing "
                         "risk and credit-cycle vulnerability.  Stock measure so slow-moving.",
                         "CONTEXT", "0.40", "9 m"],
                        ["Gov Debt / GDP",
                         "Indicates the government's debt burden, which influences fiscal space and "
                         "the ability to support credit through policy tools. It is less volatile "
                         "than private-sector measures, so it serves as a background signal.",
                         "VOLATILE", "0.20", "12 m"],
                    ]
                ),

                _sub("Growth basket — long-run productivity trend (added 2026-07-05)"),
                _p("A 2026-07-05 review against Ray Dalio's framework flagged that the cyclical "
                   "growth basket above had no explicit long-run productivity-trend component — "
                   "his model treats productivity growth as one of the economy's three big forces, "
                   "distinct from the short-term debt cycle the cyclical signals mostly capture. "
                   "Three structural signals already existed in the signal universe but were "
                   "excluded from the composite; they were added back with modest weights since "
                   "they are slow-moving annual/quarterly series, not cyclical drivers."),
                _table(
                    ["Signal", "Why it matters", "Tier", "Importance", "Base share"],
                    [
                        ["Productivity (nonfarm labor productivity, quarterly)",
                         "Most timely of the three trend signals; secular productivity gains "
                         "support real wages and non-inflationary growth.",
                         "CONTEXT", "0.35", "0.4"],
                        ["TFP (Total Factor Productivity, annual)",
                         "Slower-moving secular trend; a genuine productivity-growth read, "
                         "distinct from cyclical labor/output measures.",
                         "VOLATILE", "0.20", "0.3"],
                        ["R&D Intensity (R&D spend / GDP, annual)",
                         "Structural driver of future productivity gains rather than current growth.",
                         "VOLATILE", "0.15", "0.3"],
                    ],
                ),
                _note("The 9 original cyclical signals were also reweighted 2026-07-05 via a "
                      "GDP-regression calibration (indicators/calibrate.py) — biggest changes: "
                      "Job Openings 0.85→0.25 (weak GDP fit), Real PCE 0.65→0.95 (strongest fit). "
                      "The 3 productivity-trend signals above were deliberately NOT calibrated "
                      "against short-run GDP fit, since they represent a structural/long-run "
                      "concept that a short-run regression would undervalue."),

                _sub("Volatility basket — US default importances (added 2026-07-05)"),
                _p("The Volatility composite tracks how noisy/risky the current environment is — "
                   "a genuinely different concept from Growth/Inflation/Rate/Credit, which describe "
                   "the underlying economic machine itself. It follows the same basket architecture "
                   "as every other force, but by design does not feed the Growth/Inflation regime "
                   "label directly (see Section 8)."),
                _table(
                    ["Signal", "Why it matters", "Tier", "Importance", "Countries"],
                    [
                        ["Realized volatility (rolling std of equity-index log returns)",
                         "Universal, country-agnostic signal — works anywhere daily or monthly "
                         "price data exists, unlike an implied-vol index which needs an options market.",
                         "STRONG", "0.70", "US (daily), EZ/KR (monthly proxy)"],
                        ["VIX (CBOE implied volatility)",
                         "Forward-looking (market-implied) volatility expectation; carries bonus "
                         "weight where available.",
                         "PRIMARY", "0.90", "US only"],
                    ],
                ),
                _note("EZ and KR have no free daily equity-index feed (FRED only carries a "
                      "monthly OECD share-price index for both) — their realized-vol signal is a "
                      "lower-resolution monthly-return proxy (quality_factor reduced to 0.70, "
                      "flagged is_proxy=true), and the composite is single-signal / low-coverage "
                      "for those two countries. See docs/Guidance/data_source_wishlist.md for the "
                      "ongoing search for a better daily source."),

                _sub("Productivity Trend basket — US default importances (added 2026-07-05)"),
                _p("Ray Dalio's framework treats productivity growth as one of the economy's "
                   "three big forces — the long-run line the two debt cycles oscillate around.  "
                   "This composite gives that trend a first-class read, separate from the "
                   "cyclical Growth basket (which also carries these signals at small weights "
                   "for level effects).  Slow-moving by nature: read its direction over quarters "
                   "and years, not months.  It does not feed the regime label.  The productivity "
                   "force-detail page overlays the cyclical Growth composite so 'cyclically "
                   "strong but trend-decelerating' is visible at a glance."),
                _table(
                    ["Signal", "Why it matters", "Tier", "Importance", "Half-life"],
                    [
                        ["Labor productivity (nonfarm, quarterly)",
                         "Most timely trend read; secular gains support real wages and "
                         "non-inflationary growth.",
                         "PRIMARY", "0.80", "6 m"],
                        ["TFP (Penn World Tables, annual)",
                         "The purest productivity-growth concept; slow-moving secular trend.",
                         "CONTEXT", "0.45", "12 m"],
                        ["R&D intensity (R&D/GDP, annual)",
                         "Structural driver of FUTURE productivity rather than current growth.",
                         "CONTEXT", "0.30", "12 m"],
                    ],
                ),
                _note("EZ and KR carry only annual R&D intensity free — their productivity "
                      "composite is single-signal, low-coverage, directional-only (quality_factor "
                      "0.70), and honestly ages out when the annual source lags. See "
                      "docs/Guidance/data_source_wishlist.md."),
            ], title="7 · Composite Construction"),

            # 8 ── Regime Classification ────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "8 · Regime Classification",
                    [
                        "Momentum plays two distinct roles in this system — weight tilt during "
                        "score computation, and a confirmation gate on the displayed regime chips — "
                        "and a third, simpler rule governs the stored historical quadrant.",

                        "ROLE 1 — Weight tilt (pipeline, always active): before the composite "
                        "Z-scores are computed, each signal's effective weight is multiplied by a "
                        "momentum agreement factor (see Section 6). When a signal's direction agrees "
                        "with its force's expected direction, its weight is boosted up to 1.5×; "
                        "disagreement damps it below 1.0×. This shifts how much each signal "
                        "contributes to growth_score and inflation_score, but does not gate the "
                        "regime label itself.",

                        "ROLE 2 — Regime chip classification (dashboard display): Growth and "
                        "Inflation are classified independently using a dual-condition rule — BOTH "
                        "the composite Z-score AND the month-over-month momentum delta must cross "
                        "their respective thresholds for a named regime to fire. Otherwise the "
                        "dimension lands in Transition. "
                        "Growth: Growth (Z > +gz AND ΔMoM > gm), Retraction (Z < -gz AND ΔMoM < -gm), "
                        "Transition (all other cases). "
                        "Inflation: Inflation (Z > +iz AND ΔMoM > im), Disinflation (Z < -iz AND ΔMoM < -im), "
                        "Transition (all other cases).",

                        "Default thresholds: gz = 0.5, iz = 0.5, gm = 0.0, im = 0.0. "
                        "With gm = im = 0.0 the momentum gate reduces to 'any positive tick' — "
                        "making the dual-condition effectively Z-score-only at defaults. Raise gm "
                        "or im above 0 to require a meaningful sustained move before a regime fires. "
                        "Adjust via the 'Regime Thresholds' button on the Regime History page; "
                        "settings persist in browser localStorage.",

                        "DYNAMIC THRESHOLDS (added 2026-07-05, opt-in): a 'Use dynamic thresholds "
                        "(Ray Dalio algorithm)' checkbox in the same modal replaces the flat gz/iz "
                        "with values computed fresh for each period: (1) a country-specific baseline "
                        "= 0.6 × the 24-month rolling standard deviation of that force's own Z-score "
                        "history (look-ahead safe); (2) an inflation-only credit-tightness multiplier "
                        "that widens iz when the Credit composite is very tight; (3) a volatility "
                        "multiplier on both gz and iz — a 12-month rolling standard deviation of the "
                        "force's own Z-score history ('vol of the vol', i.e. signal noisiness, "
                        "distinct from the market-based Volatility force) — that widens thresholds "
                        "when a force has been erratic recently; (4) the three combine "
                        "multiplicatively. A separate correlation-divergence flag (not fed back into "
                        "the thresholds) marks when Growth and Inflation have moved in opposite "
                        "directions for 3 consecutive months, historically associated with a "
                        "policy-rate or credit-cycle shift. Off by default — existing behavior is "
                        "unchanged unless a user opts in. See docs/Guidance/ray_dalio_review_log.md #23.",

                        "WHAT FEEDS THE LABEL: the regime category is classified from Growth and "
                        "Inflation only. Rate, the market Volatility force, Debt Stress, and the "
                        "Cycle Health Index are computed and displayed but do NOT enter the "
                        "classification. The one indirect exception is Credit tightness (plus each "
                        "composite's own recent noisiness and the country's rolling volatility), "
                        "which in dynamic mode bends the ± thresholds rather than becoming part of "
                        "the score. Direct: growth_score, inflation_score (+ momentum). Indirect "
                        "(dynamic mode only): credit tightness, composite noise, country volatility. "
                        "Not in the label: rate_score, volatility_score, debt stress, cycle health.",

                        "STORED QUADRANT (database) uses a different, simpler rule: "
                        "sign(growth_score) × sign(inflation_score) → one of four labels "
                        "(Expansion, Inflationary Boom, Stagflation, Disinflationary Slowdown). "
                        "No momentum condition is applied. This is the label used in the Global "
                        "Overview table and historical regime replay. The dashboard chips and the "
                        "stored quadrant will diverge whenever the Z-score is in the right half-plane "
                        "but momentum is flat or negative — the chips will show Transition while "
                        "the stored quadrant still shows the named season.",

                        "Confidence = fraction of active signals whose direction agrees with the "
                        "regime classification. High disequilibrium means structural forces are far "
                        "from equilibrium across multiple dimensions.",
                    ],
                    tables=[(
                        ["Layer", "Label", "Condition", "Note"],
                        [
                            ["Stored quadrant", "Expansion",             "growth_score ≥ 0  AND  inflation_score ≥ 0", "DB / Global Overview; no momentum gate"],
                            ["Stored quadrant", "Inflationary Boom",     "growth_score ≥ 0  AND  inflation_score < 0",  ""],
                            ["Stored quadrant", "Stagflation",           "growth_score < 0  AND  inflation_score ≥ 0",  ""],
                            ["Stored quadrant", "Disinflationary Slowdown","growth_score < 0 AND  inflation_score < 0", ""],
                            ["Growth chip",     "Growth",      "Z > +gz  AND  ΔMoM > gm",   "Dashboard chips; dual-condition"],
                            ["Growth chip",     "Transition",  "Neither threshold crossed",   ""],
                            ["Growth chip",     "Retraction",  "Z < -gz  AND  ΔMoM < -gm",   ""],
                            ["Inflation chip",  "Inflation",   "Z > +iz  AND  ΔMoM > im",    ""],
                            ["Inflation chip",  "Transition",  "Neither threshold crossed",   ""],
                            ["Inflation chip",  "Disinflation","Z < -iz  AND  ΔMoM < -im",   ""],
                        ]
                    )],
                    notes=[
                        "At default thresholds (gm = im = 0.0) the momentum gate is trivially "
                        "satisfied by any positive monthly tick, so the chips behave like a "
                        "pure Z-score rule. Set gm/im > 0 to require a meaningful upward move.",
                        "Historical note: 2022 US shows Growth + Inflation (not Retraction) "
                        "because employment Z-scores were strongly positive. Retraction correctly "
                        "appears from March 2023 when growth Z-scores turned negative.",
                    ],
                )),
                _p("Momentum plays two distinct roles.  First, during score computation the "
                   "pipeline tilts each signal's effective weight by a momentum-agreement factor "
                   "(see Section 6) — signals whose direction confirms the force get up to 1.5× "
                   "weight; conflicting signals are down-weighted.  This shapes the composite "
                   "Z-scores before any regime label is applied."),
                _p("Second, the dashboard regime chips use a dual-condition rule: a named regime "
                   "fires only when BOTH the composite Z-score AND the month-over-month momentum "
                   "delta cross their respective thresholds.  Otherwise the dimension lands in "
                   "Transition, preventing single-period spikes from triggering a regime change."),
                _table(
                    ["Layer", "Label", "Condition", "Note"],
                    [
                        ["Stored quadrant", "Expansion",              "growth_score ≥ 0  AND  inflation_score ≥ 0",  "DB / Global Overview; sign-only, no momentum gate"],
                        ["Stored quadrant", "Inflationary Boom",      "growth_score ≥ 0  AND  inflation_score < 0",  ""],
                        ["Stored quadrant", "Stagflation",            "growth_score < 0  AND  inflation_score ≥ 0",  ""],
                        ["Stored quadrant", "Disinflationary Slowdown","growth_score < 0  AND  inflation_score < 0", ""],
                        ["Growth chip",     "Growth",       "Z > +gz  AND  ΔMoM > gm",  "Dashboard dual-condition"],
                        ["Growth chip",     "Transition",   "Neither threshold crossed",  ""],
                        ["Growth chip",     "Retraction",   "Z < −gz  AND  ΔMoM < −gm",  ""],
                        ["Inflation chip",  "Inflation",    "Z > +iz  AND  ΔMoM > im",   ""],
                        ["Inflation chip",  "Transition",   "Neither threshold crossed",  ""],
                        ["Inflation chip",  "Disinflation", "Z < −iz  AND  ΔMoM < −im",  ""],
                    ]
                ),
                _p("Default thresholds: gz = 0.5, iz = 0.5, gm = 0.0, im = 0.0.  "
                   "With gm = im = 0.0 the momentum gate reduces to 'any positive tick', so at "
                   "defaults the chips behave like a pure Z-score rule.  Raise gm or im above 0 "
                   "to require a meaningful sustained move before a regime fires.  "
                   "Adjust via the 'Regime Thresholds' button on the Regime History page; "
                   "settings persist in localStorage.  Threshold lines are drawn on the scatter "
                   "chart and the Regime History Z-score panels."),
                _sub("Dynamic thresholds (added 2026-07-05, opt-in)"),
                _p("The same modal has a 'Use dynamic thresholds (Ray Dalio algorithm)' checkbox, "
                   "off by default.  When enabled, gz/iz stop being flat constants and are instead "
                   "recomputed every period as: (1) a country-specific baseline — 0.6 × the "
                   "24-month rolling standard deviation of that force's own Z-score history "
                   "(look-ahead safe, shift(1)); (2) an inflation-only credit-tightness "
                   "multiplier that widens iz when the Credit composite is very tight "
                   "(credit_z > 1.5); (3) a volatility multiplier on both gz and iz — the "
                   "12-month rolling standard deviation of the force's own Z-score history "
                   "('vol of the vol', i.e. how erratic the composite itself has been recently — "
                   "distinct from the market-based Volatility force in Section 7); (4) the three "
                   "combine multiplicatively.  The manual gz/iz sliders become a fallback used only "
                   "where there isn't yet enough history for a meaningful rolling calculation."),
                _p("A separate correlation-divergence flag — not fed back into the thresholds — "
                   "marks when Growth and Inflation have moved in opposite directions for 3 "
                   "consecutive months, which Ray's framework associates with a policy-rate or "
                   "credit-cycle shift breaking the usual co-movement pattern. It is computed "
                   "(compute_dynamic_thresholds() in dashboard/charting.py) but not yet surfaced "
                   "as its own UI badge."),
                _note("Dynamic thresholds are opt-in and off by default — existing dashboards see "
                      "identical behavior unless a user explicitly enables the checkbox.  Full "
                      "algorithm spec: docs/Guidance/ray_dalio_review_log.md, punch item #23."),
                _sub("What actually feeds the regime label"),
                _p("A common question after the 2026-07 changes: with five forces now computed, "
                   "how many of them drive the regime category?  The answer is deliberately narrow, "
                   "following the Ray Dalio review — the label is classified from Growth and "
                   "Inflation only.  Rate, the market Volatility force, Debt Stress, and the Cycle "
                   "Health Index are each computed and displayed, but none of them enter the "
                   "classification.  The one indirect exception is Credit: in dynamic mode, credit "
                   "tightness (plus each composite's own recent noisiness and the country's rolling "
                   "volatility) bends the ± thresholds that Growth and Inflation must cross — it "
                   "moves the goalposts rather than becoming part of the score.  This was Ray's "
                   "explicit design: keep the classifier clean, let the supporting forces adjust "
                   "the bar instead of muddying the inputs."),
                _regime_input_flow(),
                _table(
                    ["Force / input", "Role in the regime label", "How it enters"],
                    [
                        ["Growth score (+ momentum)", "Sets the Growth chip", "Direct input — classified"],
                        ["Inflation score (+ momentum)", "Sets the Inflation chip", "Direct input — classified"],
                        ["Credit tightness", "Raises the inflation threshold when credit is tight",
                         "Indirect — bends thresholds (dynamic mode only)"],
                        ["Composite noisiness", "Widens both thresholds when a force has been erratic",
                         "Indirect — bends thresholds (dynamic mode only)"],
                        ["Country rolling volatility", "Scales the baseline threshold per country",
                         "Indirect — sets the baseline (dynamic mode only)"],
                        ["Rate score", "None — displayed alongside", "Not in the label"],
                        ["Market Volatility force (VIX / realized vol)", "None — displayed alongside",
                         "Not in the label"],
                        ["Debt Stress", "None — separate long-cycle diagnostic", "Not in the label"],
                        ["Cycle Health Index", "None — separate Global Overview metric", "Not in the label"],
                    ]
                ),
                _note("The 'composite noisiness' that bends the thresholds is the statistical "
                      "jumpiness of the Growth/Inflation scores themselves (12-month rolling std of "
                      "each composite's own Z-score) — it is NOT the market-based Volatility force "
                      "(VIX / realized vol), which shares the word but does not feed the label."),
                _note("The stored quadrant (DB / Global Overview) and the dashboard chips can "
                      "diverge: if the Z-score is in the right half-plane but momentum is flat or "
                      "negative, the chips show Transition while the stored quadrant still shows "
                      "the named season.  This is intentional — the chips are the stricter, "
                      "confirmation-required view."),
                _p("Confidence = fraction of active signals whose direction agrees with the "
                   "classified regime.  High disequilibrium means structural forces are far from "
                   "their equilibrium levels across multiple force dimensions."),
                _note("Historical note: 2022 US shows Growth + Inflation rather than Retraction "
                      "because employment Z-scores were strongly positive.  Retraction correctly "
                      "appears from March 2023 when growth Z-scores turned negative."),
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
                        "Dynamic stock/flow weighting (added 2026-07-05): the weights below are "
                        "grouped into a 'stock' set (debt/GDP, corporate debt/GDP, federal interest "
                        "outlays — 0.55 combined) and a 'flow' set (debt-service ratio, primary "
                        "balance, structural balance, govt revenue — 0.45 combined). Each quarter, "
                        "effective_flow_weight = base_flow_weight × (1 + 0.2 × (debt_service_ratio "
                        "/ its own historical median)), effective_stock_weight = 1 − "
                        "effective_flow_weight, then each group's component weights are rescaled "
                        "proportionally. The model leans into flow measures — which move earlier "
                        "than stock measures — specifically when the debt-service ratio is elevated "
                        "above its own historical norm.",
                        "Missing-annual-observation interpolation (added 2026-07-05): a single "
                        "missing annual observation (a provider skipping one year) is linearly "
                        "interpolated from the surrounding known values before Z-scoring, rather "
                        "than left as a gap for the carry-forward logic to paper over from the "
                        "prior year alone. Trailing (most-recent) gaps are NOT interpolated — "
                        "those are genuine staleness and still go through Gap 1/2 above.",
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
                _sub("Dynamic stock/flow weighting (added 2026-07-05)"),
                _p("The 7 weights above are split into a 'stock' group (Govt+Household debt/GDP, "
                   "Corporate debt/GDP, Federal interest outlays/GDP — 0.55 combined, balance-sheet "
                   "measures of how far the debt burden has built up) and a 'flow' group "
                   "(Household debt-service ratio, Primary fiscal balance, Structural balance, "
                   "Government revenue — 0.45 combined, cash-flow measures of which direction "
                   "things are currently moving).  Each quarter: "
                   "effective_flow_weight = base_flow_weight × (1 + k × (debt_service_ratio / "
                   "its own historical median)), k = 0.2, effective_stock_weight = 1 − "
                   "effective_flow_weight — then each group's individual component weights are "
                   "rescaled proportionally to hit the new group total.  The composite leans into "
                   "flow measures specifically when the debt-service ratio (the earliest stress "
                   "signal) is elevated above its own historical norm, and reverts toward the "
                   "55/45 baseline otherwise."),
                _sub("Missing-data interpolation (added 2026-07-05)"),
                _p("A single missing annual observation is linearly interpolated from the "
                   "surrounding known values before Z-scoring, rather than left as a gap. This "
                   "only fills internal gaps — a missing value with no later observation after it "
                   "(i.e. the series has simply gone stale) is NOT interpolated, and still flows "
                   "through the staleness-decay/carry-cap logic in Gaps 1–2 above."),
                _note("For countries with sparser free data than the US (e.g. a future Japan "
                      "rollout), config/longterm_stress.yaml documents a minimum-viable 3-component "
                      "subset — Govt+Household debt/GDP, debt-service ratio, primary fiscal balance "
                      "— chosen because together they capture the size, cash-flow pressure, and "
                      "direction of the debt trajectory. The other 4 components add incremental, "
                      "not fundamental, insight."),
                _inline_formula(F("Rolling Z-score (quarterly components)")),
                _inline_formula(F("Rolling Z-score (annual components → quarterly)")),
                _inline_formula(F("Staleness weight decay")),
                _inline_formula(F("Aggregate stress score")),
                _inline_formula(F("Stress band labels")),
                _sub("Long-term debt-cycle STAGE classifier (added 2026-07-05, roadmap Phase C)"),
                _p("Debt Stress gives a LEVEL; the stage classifier "
                   "(indicators/debt_cycle_stage.py, config/debt_cycle_stage.yaml) gives a "
                   "STAGE — where in the ~50–75yr long-term debt cycle the country sits: "
                   "leveraging (debt growing productively: debt/GDP rising, debt service "
                   "manageable, growth above the real rate, nominal growth above yields), "
                   "squeeze (the top: debt stock high, debt service rising, real rate at/above "
                   "real growth, nominal growth below yields), deleveraging (debt/GDP falling, "
                   "debt service unwinding, growth weak), reflation ('beautiful deleveraging': "
                   "policy engineered so nominal growth runs well above yields and the real "
                   "rate sits well below real growth while the debt stock stabilizes), or "
                   "neutral when no stage clears the minimum score."),
                _p("Five feature families feed a transparent weighted-condition vote per stage "
                   "(argmax — NOT a fitted model; every threshold and weight is in the YAML): "
                   "(1) debt/GDP percentile — an expanding rank of the current value against "
                   "PRIOR history only (shift 1, no look-ahead), averaged across the available "
                   "government/household/corporate ratios; (2) debt/GDP trajectory — 3-year "
                   "annualized change in pp of GDP per year; (3) debt-service-ratio trend — "
                   "2-year change in pp; (4) real policy rate minus real growth — Ray's 'is "
                   "debt growing faster than income' test; (5) nominal growth minus the 10-year "
                   "yield — whether burdens erode or compound. Missing features renormalize "
                   "rather than zero out (EZ/KR run on 4 of 5 — no free debt-service series); "
                   "a stage whose evidence is mostly missing scores NaN, and fewer than 3 "
                   "families present means no label at all. The raw label is smoothed with a "
                   "3-quarter rolling mode (a new stage must persist to take over; smoothing "
                   "never carries a label across a data gap). Confidence = top score minus "
                   "runner-up."),
                _p("Where it surfaces: the Cycle Stage card on the Command Center, and the "
                   "colored stage timeline + per-stage score chart on this Debt Stress page. "
                   "US timeline sanity anchors: 1989–91 squeeze (S&L), 1992–95 reflation, "
                   "2007 pre-GFC squeeze, 2012–2020 reflation (the ZIRP 'beautiful "
                   "deleveraging'), 2020–23 COVID leveraging surge. Threshold calibration "
                   "against the point-in-time backtest is an explicit Phase G3 task."),
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
                        "Current coverage (Phase 2 in progress): US (63 signals), "
                        "Eurozone (34 signals), South Korea (22 signals). "
                        "Japan is next; then UK, China, India, Brazil, Saudi Arabia, Russia.",
                        "Country files: config/countries/{cc}_bindings.yaml (signal bindings) "
                        "+ config/countries/{cc}_composites.yaml (composite indicator lists). "
                        "The pipeline auto-discovers all *_bindings.yaml in this directory.",
                        "Each country requires: binding instantiation → series ID verification "
                        "against the provider's metadata endpoint → spot-check vs. a public "
                        "reference → vintage_available set honestly → human sign-off. "
                        "No country is considered active until all checks pass.",
                        "Known data gaps (EZ): current account balance is unavailable from any "
                        "free API (ECB BOP flows return HTTP 400/404; Eurostat bop_c6_q returns "
                        "413; FRED/IMF have no EA aggregate). Documented; dash shown in Global Overview.",
                        "NBS China and Rosstat/CBR Russia automated pulls are deferred; "
                        "World Bank / IMF harmonised data will be used with explicit gap flags.",
                    ],
                    tables=[(
                        ["Country", "Code", "Signals", "Status", "Key data sources"],
                        [
                            ["United States", "US", "63", "✅ Live", "FRED, World Bank, IMF, OECD"],
                            ["Eurozone",      "EZ", "34", "✅ Live (current account gap)", "Eurostat JSON, ECB SDW, World Bank, IMF"],
                            ["South Korea",   "KR", "22", "✅ Live (CPI proxy bridge)", "FRED OECD series, World Bank, IMF"],
                            ["Japan",         "JP", "—",  "🔄 Next", "FRED, World Bank, IMF"],
                        ]
                    )],
                )),
                _p("Current coverage (Phase 2 in progress): United States (63 signals), "
                   "Eurozone (34 signals), South Korea (22 signals).  "
                   "Japan is next; then UK, China, India, Brazil, Saudi Arabia, Russia."),
                _table(
                    ["Country", "Code", "Signals", "Status", "Key data sources"],
                    [
                        ["United States", "US", "63", "✅ Live", "FRED, World Bank, IMF, OECD"],
                        ["Eurozone",      "EZ", "34", "✅ Live (current account gap)",
                         "Eurostat JSON stats API (industrial prod, retail, unemployment, "
                         "fiscal); ECB SDW SDMX (long-term interest rates); World Bank; IMF"],
                        ["South Korea",   "KR", "22", "✅ Live (annual CPI proxy)",
                         "FRED OECD series; World Bank; IMF DataMapper; "
                         "monthly CPI bridged via IMF annual PCPIPCH (OECD direct feed ended Apr 2025)"],
                        ["Japan",         "JP", "—",  "🔄 Next", "FRED, World Bank, IMF"],
                    ]
                ),
                _p("Each country requires: binding instantiation → series ID verification "
                   "against the provider's metadata endpoint → spot-check vs. a public "
                   "reference → vintage_available set honestly → human sign-off.  "
                   "No country is considered active until all checks pass."),
                _sub("Country file architecture"),
                _p("config/composites_policy.yaml holds the global methodology (decay, momentum "
                   "tilt, confidence, disequilibrium force groups).  Per-country files "
                   "config/countries/{cc}_bindings.yaml and config/countries/{cc}_composites.yaml "
                   "hold signal bindings and composite indicator lists.  The pipeline auto-discovers "
                   "all *_bindings.yaml in that directory.  Adding a new country: create both files, "
                   "then run the pipeline."),
                _sub("Known data gaps"),
                _note("EZ current account: unavailable from any free API. "
                      "ECB BOP/BP6/BPS flows return HTTP 400/404; Eurostat bop_c6_q returns 413 "
                      "regardless of parameters; FRED and IMF have no EA aggregate.  "
                      "Documented in docs/Guidance/EU_singals_guidance.md; dash shown in Global Overview."),
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

            # 13 ── Cycle Health Index ─────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "13 · Cycle Health Index",
                    [
                        "The Cycle Health Index is a compact Global Overview diagnostic that "
                        "combines real growth, the policy-rate cost of credit, inflation, and "
                        "the debt burden into one short-cycle health reading. It is display-only: "
                        "it does not feed the stored regime quadrant, force composites, or any "
                        "allocation logic.",
                        "Interpretation: CHI asks whether the economy's real growth is "
                        "large enough to absorb the current cost of credit and price pressure. In "
                        "plain language, it is a quick read on whether credit conditions are still "
                        "supporting expansion or beginning to choke it. It links the short-term "
                        "debt cycle (growth, rates, inflation) with a simple long-term debt-cycle "
                        "drag (Debt/GDP above or below target).",
                        "The raw version uses real GDP growth minus the policy rate minus headline "
                        "inflation. This avoids double-counting price changes: nominal growth can "
                        "rise simply because inflation rose, and inflation is already a subtractive "
                        "term in the index. Positive values mean real growth is high relative to credit cost and price "
                        "pressure; negative values mean rates and inflation are dragging harder "
                        "than growth is expanding.",
                        "The debt-adjusted version adds the long-term debt-cycle constraint by "
                        "subtracting separate public and private debt gaps. Public debt is "
                        "government debt/GDP minus its target; private debt is the average of "
                        "available household and corporate debt/GDP minus its target. If private "
                        "debt is unavailable for a country, the model falls back to public-only debt drag.",
                        "Stage thresholds can be fixed or adaptive. Adaptive mode uses k times the "
                        "standard deviation of that country's CHI history, so the same labels remain "
                        "meaningful across countries and volatility regimes. Component contributions "
                        "can also be decayed by observation age, pulling stale values toward neutral "
                        "with an exponential half-life.",
                        "Conditional weighting (added 2026-07-05): wg/wr/wi default to an equal "
                        "0.30/0.30/0.30 split, but tilt toward whichever pillar is most active — "
                        "if inflation exceeds 5% annualized, wi rises to 0.35; otherwise if growth "
                        "is below 1% annualized, wr rises to 0.35 (the cost of capital becomes the "
                        "primary lever near the zero lower bound). Debt-gap weights (wp/wv) are "
                        "unaffected. Only one tilt applies at a time.",
                        "Nominal vs. real policy rate (added 2026-07-05): CHI uses the nominal "
                        "policy rate by design, not an oversight — it moves faster than a real rate "
                        "(which lags inflation data), is directly observable with no estimation "
                        "error, and doesn't double-count since inflation is already its own "
                        "separate subtractive term. A 'use_real_policy_rate' config flag (default "
                        "off) switches to a realized real policy rate (nominal minus contemporaneous "
                        "inflation) for users who want strict consistency with the Rate force "
                        "elsewhere, which prefers real rates.",
                    ],
                    tables=[
                        (
                            ["Formula", "Definition"],
                            [
                                ["Raw CHI", "CHI_raw = Real GDP growth - Policy rate - Inflation"],
                                ["Debt-adjusted CHI", "CHI_debt_adj = wg*RealGrowth - wr*Policy - wi*Inflation - wp*(PublicDebt/GDP - PublicTarget) - wv*(PrivateDebt/GDP - PrivateTarget)"],
                                ["Adaptive thresholds", "positive = +k*σ(CHI_debt_adj); negative = -k*σ(CHI_debt_adj)"],
                                ["Stage rule", "Expansion if CHI_debt_adj >= positive threshold; Late/Tight if <= negative threshold; Neutral otherwise"],
                            ],
                        ),
                        (
                            ["Stage", "Meaning", "Typical read-through"],
                            [
                                ["Expansion", "Growth is strong enough relative to rates, inflation, and debt drag.", "Credit is still relatively supportive; the short-term cycle has room to run."],
                                ["Neutral", "Growth, rates, inflation, and debt drag are roughly balanced.", "Transition zone; watch momentum and corroborating indicators."],
                                ["Late / Tight", "Rates, inflation, or debt burden are overwhelming growth.", "Late-cycle or early-contraction pressure; credit conditions are becoming a drag."],
                            ],
                        ),
                        (
                            ["Input", "Role in the index", "Higher value means"],
                            [
                                ["Real GDP growth", "Real output engine; positive contribution.", "More real capacity to service debt and absorb rates/inflation."],
                                ["Policy rate", "Cost of short-term credit; subtractive contribution.", "Tighter financing conditions."],
                                ["Inflation", "Price-pressure drag; subtractive contribution.", "More purchasing-power erosion and policy-tightening risk."],
                                ["Public debt gap", "Fiscal balance-sheet constraint; subtractive when above target.", "Less fiscal flexibility and more sensitivity to rates."],
                                ["Private debt gap", "Household/corporate leverage constraint; subtractive when above target.", "More private-sector refinancing and debt-service pressure."],
                                ["Freshness decay", "Confidence filter applied to aged observations.", "Stale data contributes less to the current index."],
                            ],
                        ),
                        (
                            ["Setting", "Default"],
                            [
                                ["Growth weight (wg)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['growth']:.2f}"],
                                ["Policy-rate weight (wr)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['policy_rate']:.2f}"],
                                ["Inflation weight (wi)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['inflation']:.2f}"],
                                ["Public debt weight (wp)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['public_debt_gap']:.2f}"],
                                ["Private debt weight (wv)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['private_debt_gap']:.2f}"],
                                ["Public debt target", f"{CYCLE_HEALTH_DEFAULT_CONFIG['debt_targets']['public']:.0f}% of GDP"],
                                ["Private debt target", f"{CYCLE_HEALTH_DEFAULT_CONFIG['debt_targets']['private']:.0f}% of GDP"],
                                ["Threshold mode", str(CYCLE_HEALTH_DEFAULT_CONFIG['threshold_mode'])],
                                ["Adaptive threshold multiplier", f"{CYCLE_HEALTH_DEFAULT_CONFIG['threshold_sigma_multiplier']:.2f} × σ"],
                                ["Freshness half-life", f"{CYCLE_HEALTH_DEFAULT_CONFIG['freshness_half_life_months']:.1f} months"],
                            ],
                        ),
                    ],
                    notes=[
                        "Cycle Health settings are edited from the Global Overview configuration "
                        "modal and persist in browser localStorage. They do not mutate YAML or DB state.",
                        "The guidance document includes portfolio-allocation language, but this "
                        "dashboard remains diagnostic only. No allocation or trade rule is produced.",
                        "CHI is not a recession model. It is a compact lens to triage macro-cycle "
                        "pressure and should be cross-checked against force composites, debt stress, "
                        "credit spreads, labor data, and data-quality flags.",
                    ],
                )),
                _p("The Cycle Health Index appears on the Global Overview table as three columns: "
                   "raw CHI, debt-adjusted CHI, and the interpreted weighted stage."),
                _sub("What CHI is measuring"),
                _p("CHI is a cycle-pressure gauge. It compares the economy's real growth engine "
                   "against the two forces that most directly eat into that growth: the policy-rate "
                   "cost of credit and inflation. The debt-adjusted version adds slower-moving "
                   "balance-sheet constraints: public debt measures fiscal space, while private "
                   "debt measures household/corporate leverage where those series are available."),
                _p("A rising CHI means the growth/rate/inflation/debt mix is becoming easier for "
                   "the economy to carry. A falling CHI means the mix is becoming more restrictive. "
                   "The level tells you where the pressure sits now; the direction tells you whether "
                   "the cycle is improving or deteriorating."),
                _sub("How to read the stage labels"),
                _table(
                    ["Stage", "Meaning", "What to check next"],
                    [
                        ["Expansion",
                         "Debt-adjusted CHI is above the positive threshold. Growth is strong enough "
                         "relative to rates, inflation, and debt drag.",
                         "Confirm with Growth composite breadth, credit health, and inflation momentum."],
                        ["Neutral",
                         "Debt-adjusted CHI is between thresholds. The system is balanced or in transition.",
                         "Watch the month-to-month direction and whether force scores agree or conflict."],
                        ["Late / Tight",
                         "Debt-adjusted CHI is below the negative threshold. Rates, inflation, or debt "
                         "burden are overwhelming growth.",
                         "Check debt stress, lending standards, credit spreads, unemployment, and fiscal balance."],
                    ],
                ),
                _sub("Input interpretation"),
                _table(
                    ["Input", "Role", "Audit question"],
                    [
                        ["Real GDP growth", "Positive term; proxy for real output growth.", "Is real activity expanding fast enough to carry financing costs?"],
                        ["Policy rate", "Negative term; proxy for the marginal cost of credit.", "Is policy restrictive relative to income growth?"],
                        ["Inflation", "Negative term; captures purchasing-power erosion and tightening pressure.", "Is inflation forcing tighter policy or absorbing nominal growth?"],
                        ["Public debt gap", "Negative term when government debt/GDP is above target.", "Is fiscal leverage amplifying the short-cycle signal?"],
                        ["Private debt gap", "Negative term when household/corporate debt/GDP is above target.", "Is private leverage creating credit-cycle fragility?"],
                        ["Freshness decay", "Exponential age filter applied to component contributions.", "Is the current reading relying on stale observations?"],
                    ],
                ),
                _sub("Formulas"),
                _table(
                    ["Formula", "Definition"],
                    [
                        ["Raw CHI", "CHI_raw = Real GDP growth - Policy rate - Inflation"],
                        ["Debt-adjusted CHI", "CHI_debt_adj = wg*RealGrowth - wr*Policy - wi*Inflation - wp*PublicDebtGap - wv*PrivateDebtGap"],
                        ["Freshness", "component_used = component_value * 0.5^(age_months / half_life_months)"],
                        ["Adaptive thresholds", "threshold = ± k * standard_deviation(CHI_debt_adj history)"],
                    ],
                ),
                _sub("Default configuration"),
                _table(
                    ["Setting", "Default"],
                    [
                        ["Growth weight (wg)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['growth']:.2f}"],
                        ["Policy-rate weight (wr)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['policy_rate']:.2f}"],
                        ["Inflation weight (wi)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['inflation']:.2f}"],
                        ["Public debt weight (wp)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['public_debt_gap']:.2f}"],
                        ["Private debt weight (wv)", f"{CYCLE_HEALTH_DEFAULT_CONFIG['weights']['private_debt_gap']:.2f}"],
                        ["Public debt target", f"{CYCLE_HEALTH_DEFAULT_CONFIG['debt_targets']['public']:.0f}% of GDP"],
                        ["Private debt target", f"{CYCLE_HEALTH_DEFAULT_CONFIG['debt_targets']['private']:.0f}% of GDP"],
                        ["Threshold mode", str(CYCLE_HEALTH_DEFAULT_CONFIG['threshold_mode'])],
                        ["Adaptive threshold multiplier", f"{CYCLE_HEALTH_DEFAULT_CONFIG['threshold_sigma_multiplier']:.2f} × σ"],
                        ["Fixed positive threshold", f"{CYCLE_HEALTH_DEFAULT_CONFIG['positive_threshold']:+.2f}"],
                        ["Fixed negative threshold", f"{CYCLE_HEALTH_DEFAULT_CONFIG['negative_threshold']:+.2f}"],
                        ["Freshness half-life", f"{CYCLE_HEALTH_DEFAULT_CONFIG['freshness_half_life_months']:.1f} months"],
                        ["Policy rate basis",
                         "realized real (nominal − inflation)" if CYCLE_HEALTH_DEFAULT_CONFIG.get("use_real_policy_rate")
                         else "nominal (default)"],
                    ],
                ),
                _sub("Conditional weighting & rate basis (added 2026-07-05)"),
                _p("The wg/wr/wi weights above are the base 0.30/0.30/0.30 split, but tilt "
                   "dynamically toward whichever pillar is currently most active: if inflation is "
                   "above 5% annualized, wi rises to 0.35; otherwise if growth is below 1% "
                   "annualized, wr rises to 0.35 — the cost of capital becomes the primary lever "
                   "near the zero lower bound. Only one tilt applies at a time; wp/wv are always "
                   "unaffected."),
                _p("The policy-rate term uses the nominal rate by design: it moves faster than a "
                   "real rate (no lag waiting on inflation data), is directly observable with no "
                   "estimation error, and doesn't double-count inflation since it's already its "
                   "own separate subtractive term in the formula. A 'use_real_policy_rate' config "
                   "flag (default off, shown above) switches to a realized real policy rate "
                   "(nominal minus contemporaneous inflation) for consistency with the Rate force "
                   "elsewhere, which prefers real rates."),
                _p("Stage labels are based on the debt-adjusted value: Expansion at or above "
                   "the positive threshold, Late / Tight at or below the negative threshold, and "
                   "Neutral between the two. In adaptive mode, these thresholds are computed from "
                   "the selected country's own CHI history; in fixed mode, the configured numeric "
                   "thresholds are used directly."),
                _note("Important limitation: CHI is an explanatory diagnostic, not a standalone "
                      "forecast. A negative reading can reflect healthy anti-inflation tightening, "
                      "a growth slowdown, excessive debt drag, or some combination of all three. "
                      "Use it to identify what deserves attention, then audit the component values "
                      "and the broader force pages."),
                _note("Settings are browser-local and can be copied from the Global Overview "
                      "configuration modal. The copied payload is:"),
                html.Pre(
                    _cycle_config_clipboard_text(CYCLE_HEALTH_DEFAULT_CONFIG),
                    style={
                        "fontSize": "0.72rem",
                        "color": "var(--muted-color)",
                        "backgroundColor": "var(--card-bg)",
                        "border": "1px solid var(--border-color)",
                        "borderRadius": "4px",
                        "padding": "10px",
                        "whiteSpace": "pre-wrap",
                    },
                ),
            ], title="13 · Cycle Health Index"),

            # 14 ── Deferred & Out of Scope ─────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "14 · Deferred Items",
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
                            ["Daily EA/KR equity index (Volatility force)", "Deferred — no free daily feed; monthly proxy in use, see data_source_wishlist.md"],
                            ["MOVE-equivalent bond volatility",   "Deferred — no free FRED series confirmed yet"],
                            ["Credit-spread volatility component", "Deferred — buildable from existing spread signals, not yet built"],
                            ["ECB/BOK loan-demand series (Credit force, EZ/KR)", "Deferred — US-side resolved (DRSDCILM); EZ/KR unconfirmed"],
                            ["Debt-service-to-consumption/investment ratios", "Deferred — needs free PCE/investment denominator series"],
                            ["Forward-looking Fed policy expectations", "✅ Resolved 2026-07-05 — FEDTARMD (FOMC dot-plot) confirmed free; not yet wired into the Rate basket"],
                            ["Investment-layer roadmap (regime-conditional returns, factor tilts, risk budgeting)", "Out of scope — Allocation Layer project; see ray_dalio_review_log.md #12"],
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
                        ["OLS weight calibration (I1)",        "✅ Live — indicators/calibrate.py; advisory, user confirms changes via Importance Editor"],
                        ["Dynamic momentum windows (D2)",      "Phase 3 — requires regime labels as input"],
                        ["Daily EA/KR equity index (Volatility force)",
                         "Deferred 2026-07-05 — no free daily equity feed exists via FRED for the "
                         "Euro Area or Korea; a monthly-return realized-vol proxy is in use instead. "
                         "See docs/Guidance/data_source_wishlist.md."],
                        ["MOVE-equivalent bond volatility",
                         "Deferred 2026-07-05 — no free FRED series confirmed yet for a US bond-market "
                         "volatility index."],
                        ["Credit-spread volatility component",
                         "Deferred 2026-07-05 — buildable in-house (rolling std of existing high-yield "
                         "spread/Treasury-yield signals), just not built yet."],
                        ["ECB/BOK loan-demand series (Credit force, EZ/KR)",
                         "Deferred 2026-07-05 — US side resolved (DRSDCILM confirmed free, pairs with "
                         "existing DRTSCILM); ECB Bank Lending Survey / BoK equivalent unconfirmed."],
                        ["Debt-service-to-consumption / -to-investment ratios (Debt Stress)",
                         "Deferred 2026-07-05 — needs a free consumption (FRED PCE) or investment "
                         "denominator series; not yet sourced."],
                        ["Forward-looking Fed policy expectations (Rate force)",
                         "✅ Data-feed resolved 2026-07-05 — FEDTARMD (FOMC dot-plot median) confirmed "
                         "free via FRED as a forward-guidance proxy; not yet wired into the Rate basket."],
                        ["Investment-layer roadmap (regime-conditional returns, factor tilts, dynamic "
                         "risk budgeting, scenario testing)",
                         "Out of scope for this repo — candidate for the separate Allocation Layer "
                         "project. Concrete 5-step roadmap logged in "
                         "docs/Guidance/ray_dalio_review_log.md, punch item #12."],
                    ]
                ),
            ], title="14 · Deferred Items"),

            # 15 ── Revision Log ────────────────────────────────────────────────
            dbc.AccordionItem([
                _copy_btn(_section_text(
                    "15 · Revision Log",
                    [
                        "A running log of methodology changes that alter what a number on this "
                        "dashboard means or how it is computed — as distinct from docs/worklog.md, "
                        "which logs every session at implementation-level detail. Add an entry here "
                        "whenever a change affects a formula, weight, threshold, or classification "
                        "rule described elsewhere on this page, so a reader can see at a glance "
                        "what changed and when without re-deriving it from the source code.",
                    ],
                    tables=[(
                        ["Date", "Change", "Sections affected"],
                        [
                            ["2026-07-06", "Unification audit (Ray rulings): canonical rolling-window defaults 48m growth / 90m inflation everywhere (rolling composite columns backfilled for ALL countries — were US-only); Command Center honors the sidebar windows; cross-country views normalize every country on the same canonical window", "2, 8"],
                            ["2026-07-06", "Regime Map: four-season names demoted to seasonal-archetype backdrop beyond the ±threshold lines only; inside the band the label is 'Transition — no clear season' (threshold-aware _season_label replaces all sign-based quadrant derivations)", "8"],
                            ["2026-07-06", "Confidence renamed to Chip Direction Agreement: per-force % of signals moving with the chip's heading (sign of composite MoM delta), G/I sub-metrics; legacy quadrant-based definition retired from display", "8"],
                            ["2026-07-06", "United Kingdom rolled out (Phase 2): 27 signals, all 6 force composites, stage classifier (current: squeeze, 0.53 confidence — the strongest stage read of any country) — monthly CPI ages out 2025-03 (IMF bridge covers); volatility is the monthly proxy (no free daily FTSE)", "7 (GB-specific coverage notes)"],
                            ["2026-07-06", "Phase G3 backtest verdicts: direction validation survives ALFRED vintage replay (wrong-direction ~0% on as-known data); rate_expectations keeps its Rate-basket slot at CONTEXT 0.45 (incremental IC +0.15 on fwd bond returns); dynamic thresholds stay opt-in; stage classifier calibration confirmed except late-engaging 2007 squeeze", "7, 8, 9 (validation, no formula change)"],
                            ["2026-07-05", "Japan rolled out (roadmap Phase F): 25 signals, all 6 force composites, stage classifier (current: reflation) — inflation is IMF-annual-bridge-only (no free monthly JP CPI); volatility is true daily Nikkei realized vol", "7 (JP-specific coverage notes)"],
                            ["2026-07-05", "Relative Cycles page added (/relative): per-country regime + stage + order cards and growth/inflation cycle-correlation heatmaps (full history + last 10y) — display-only, no formula changes (roadmap Phase E)", "— (display only)"],
                            ["2026-07-05", "Big-cycle ORDER lens added (roadmap Phase D): order.gini (WB) + order.reserve_currency_share (IMF COFER via new SDMX API) — structural signals, feed no composite; Command Center Big-cycle card live-partial (governance/GPR deferred)", "— (new data lens)"],
                            ["2026-07-05", "Long-term debt-cycle STAGE classifier added (leveraging / squeeze / deleveraging / reflation; 5-feature weighted-condition vote, config-driven thresholds, 3-quarter mode smoothing) — Cycle Stage card + Debt Stress page timeline (roadmap Phase C)", "9"],
                            ["2026-07-05", "Command Center added as the default landing page (/): regime strip with divergence badge, short-cycle lever cards, debt-stress + DSR, productivity-vs-cycle, what-changed feed — display-only synthesis, no formula changes (roadmap Phase CC)", "8, 9 (display only)"],
                            ["2026-07-05", "Productivity Trend promoted to a first-class per-country composite (productivity_score) with its own Signals section and force-detail page overlaying cyclical growth (roadmap Phase B)", "7"],
                            ["2026-07-05", "Credit force: added SLOOS loan-demand (demand side); Rate force: added rate_expectations = 2Y minus fed funds (Ray's pick after the dot-plot proved non-viable) (roadmap Phase A)", "7"],
                            ["2026-07-05", "Regime classifier: added an opt-in dynamic-threshold algorithm (country-vol-scaled + credit/volatility-adjusted, off by default)", "8"],
                            ["2026-07-05", "Documented what actually feeds the regime label (Growth+Inflation direct; Credit indirect via dynamic thresholds; Rate/Volatility/Debt Stress/CHI not in the label) + input-flow diagram", "8"],
                            ["2026-07-05", "Volatility force: restructured into a real basket composite (realized vol + VIX for US, monthly proxy for EZ/KR), replacing the old raw-VIX display", "7"],
                            ["2026-07-05", "Cycle Health Index: conditional growth/rate/inflation weight tilt; nominal/real policy-rate toggle", "13"],
                            ["2026-07-05", "Long-Term Debt Stress: dynamic stock/flow weighting formula; missing-annual-data interpolation; sparse-country minimum-viable component set documented", "9"],
                            ["2026-07-05", "Growth composite: GDP-regression calibration applied to the 9 cyclical signals; 3 long-run productivity-trend signals added", "7"],
                            ["2026-07-05", "Inflation composite: merged 5Y/10Y TIPS breakevens into one blended signal to remove double-counting", "7"],
                            ["2026-06-28", "Global Overview: added the Cycle Health Index (raw + debt-adjusted, adaptive thresholds, freshness decay)", "13"],
                            ["2026-06-26", "Added Rate and Credit force composites with per-signal age-decay half-lives; force detail sub-pages", "7"],
                            ["2026-06-25", "Regime classification restructured from a single 4-quadrant label to two independent Growth/Inflation chips with configurable dual-condition (Z + momentum) thresholds", "8"],
                            ["2026-06-23", "Weight calibration system: importance tiers, force-balance rule, GDP-regression calibration tool, Weight Audit page", "7, 12"],
                            ["2026-06-19", "Long-Term Debt Stress indicator added (7-component composite with staleness decay)", "9"],
                            ["2026-06-18", "Composites engine added: Growth Score, Inflation Score, Regime Quadrant, Confidence, Disequilibrium", "7, 8"],
                        ]
                    )],
                    notes=["See docs/Guidance/ray_dalio_review_log.md for the full session-by-session "
                           "detail behind the 2026-07-05 entries (a systematic review against a Ray "
                           "Dalio AI persona, with a 24-item punch list)."],
                )),
                _p("A running log of methodology changes that alter what a number on this "
                   "dashboard means or how it is computed — as distinct from docs/worklog.md, "
                   "which logs every session at implementation-level detail.  Add an entry here "
                   "whenever a change affects a formula, weight, threshold, or classification rule "
                   "described elsewhere on this page."),
                _table(
                    ["Date", "Change", "Sections affected"],
                    [
                        ["2026-07-06", "Unification audit (Ray rulings): canonical rolling-window defaults 48m growth / 90m inflation everywhere (rolling composite columns backfilled for ALL countries — were US-only); Command Center honors the sidebar windows; cross-country views normalize every country on the same canonical window", "2, 8"],
                        ["2026-07-06", "Regime Map: four-season names demoted to seasonal-archetype backdrop beyond the ±threshold lines only; inside the band the label is 'Transition — no clear season' (threshold-aware _season_label replaces all sign-based quadrant derivations)", "8"],
                        ["2026-07-06", "Confidence renamed to Chip Direction Agreement: per-force % of signals moving with the chip's heading (sign of composite MoM delta), G/I sub-metrics; legacy quadrant-based definition retired from display", "8"],
                        ["2026-07-06", "United Kingdom rolled out (Phase 2): 27 signals, all 6 force composites, stage classifier (current: squeeze, 0.53 confidence — the strongest stage read of any country) — monthly CPI ages out 2025-03 (IMF bridge covers); volatility is the monthly proxy (no free daily FTSE)", "7 (GB-specific coverage notes)"],
                        ["2026-07-06", "Phase G3 backtest verdicts: direction validation survives ALFRED vintage replay (wrong-direction ~0% on as-known data); rate_expectations keeps its Rate-basket slot at CONTEXT 0.45 (incremental IC +0.15 on fwd bond returns); dynamic thresholds stay opt-in; stage classifier calibration confirmed except late-engaging 2007 squeeze", "7, 8, 9 (validation, no formula change)"],
                        ["2026-07-05", "Japan rolled out (roadmap Phase F): 25 signals, all 6 force composites, stage classifier (current: reflation) — inflation is IMF-annual-bridge-only (no free monthly JP CPI); volatility is true daily Nikkei realized vol", "7 (JP-specific coverage notes)"],
                        ["2026-07-05", "Relative Cycles page added (/relative): per-country regime + stage + order cards and growth/inflation cycle-correlation heatmaps (full history + last 10y) — display-only, no formula changes (roadmap Phase E)", "— (display only)"],
                        ["2026-07-05", "Big-cycle ORDER lens added (roadmap Phase D): order.gini (WB) + order.reserve_currency_share (IMF COFER via new SDMX API) — structural signals, feed no composite; Command Center Big-cycle card live-partial (governance/GPR deferred)", "— (new data lens)"],
                        ["2026-07-05", "Long-term debt-cycle STAGE classifier added (leveraging / squeeze / deleveraging / reflation; 5-feature weighted-condition vote, config-driven thresholds, 3-quarter mode smoothing) — Cycle Stage card + Debt Stress page timeline (roadmap Phase C)", "9"],
                        ["2026-07-05", "Command Center added as the default landing page (/): regime strip with divergence badge, short-cycle lever cards, debt-stress + DSR, productivity-vs-cycle, what-changed feed — display-only synthesis, no formula changes (roadmap Phase CC)", "8, 9 (display only)"],
                        ["2026-07-05", "Productivity Trend promoted to a first-class per-country composite (productivity_score) with its own Signals section and force-detail page overlaying cyclical growth (roadmap Phase B)", "7"],
                        ["2026-07-05", "Credit force: added SLOOS loan-demand (demand side); Rate force: added rate_expectations = 2Y minus fed funds (Ray's pick after the dot-plot proved non-viable) (roadmap Phase A)", "7"],
                        ["2026-07-05", "Regime classifier: added an opt-in dynamic-threshold algorithm (country-vol-scaled + credit/volatility-adjusted, off by default)", "8"],
                        ["2026-07-05", "Documented what actually feeds the regime label (Growth+Inflation direct; Credit indirect via dynamic thresholds; Rate/Volatility/Debt Stress/CHI not in the label) + input-flow diagram", "8"],
                        ["2026-07-05", "Volatility force: restructured into a real basket composite (realized vol + VIX for US, monthly proxy for EZ/KR), replacing the old raw-VIX display", "7"],
                        ["2026-07-05", "Cycle Health Index: conditional growth/rate/inflation weight tilt; nominal/real policy-rate toggle", "13"],
                        ["2026-07-05", "Long-Term Debt Stress: dynamic stock/flow weighting formula; missing-annual-data interpolation; sparse-country minimum-viable component set documented", "9"],
                        ["2026-07-05", "Growth composite: GDP-regression calibration applied to the 9 cyclical signals; 3 long-run productivity-trend signals added", "7"],
                        ["2026-07-05", "Inflation composite: merged 5Y/10Y TIPS breakevens into one blended signal to remove double-counting", "7"],
                        ["2026-06-28", "Global Overview: added the Cycle Health Index (raw + debt-adjusted, adaptive thresholds, freshness decay)", "13"],
                        ["2026-06-26", "Added Rate and Credit force composites with per-signal age-decay half-lives; force detail sub-pages", "7"],
                        ["2026-06-25", "Regime classification restructured from a single 4-quadrant label to two independent Growth/Inflation chips with configurable dual-condition (Z + momentum) thresholds", "8"],
                        ["2026-06-23", "Weight calibration system: importance tiers, force-balance rule, GDP-regression calibration tool, Weight Audit page", "7, 12"],
                        ["2026-06-19", "Long-Term Debt Stress indicator added (7-component composite with staleness decay)", "9"],
                        ["2026-06-18", "Composites engine added: Growth Score, Inflation Score, Regime Quadrant, Confidence, Disequilibrium", "7, 8"],
                    ]
                ),
                _note("See docs/Guidance/ray_dalio_review_log.md for the full session-by-session "
                      "detail behind the 2026-07-05 entries (a systematic review against a Ray "
                      "Dalio AI persona, with a 24-item punch list)."),
            ], title="15 · Revision Log"),

        ], start_collapsed=True, always_open=True),

    ], className="pe-2 pt-1", style={"maxWidth": "1100px", "margin": "0 auto"})

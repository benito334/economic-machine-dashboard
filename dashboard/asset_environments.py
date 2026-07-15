"""Assets by Environment — which buckets do well in each growth/inflation regime.

A plain-language reference built from a Digital Ray consult (the user's chat
"Can you map out for me the buckets performance in each environment…",
logged in docs/Guidance/ray_dalio_review_log.md, 2026-07-15). The headline is a
four-box matrix (Growth × Inflation, the classic All-Weather quadrants) with each
asset placed in the box(es) it performs well in and a badge — (G) or (I) — for
which of the two drivers is its primary lever there. The full driver-by-driver
detail table and reasoning follow the visual.

Static reference content (no live data): educational, diagnostic — no allocation
advice. digitalray.ai output is an AI approximation of Ray Dalio's framework.
"""
from __future__ import annotations

from dash import html

# Driver-badge colours (match the site's growth/inflation semantics)
_G = "#2e9e5b"      # Growth is the primary lever
_I = "#e8a317"      # Inflation is the primary lever

# ── The four quadrants (Regime-Map orientation: Growth →, Inflation ↑) ────────
# Each: environment name, the two drivers, a tint, and the assets that do well
# there with their primary-lever badge.
_QUADRANTS = {
    "stag": {   # top-left: Falling Growth + Rising Inflation
        "title": "Stagflation", "growth": "Falling growth", "infl": "Rising inflation",
        "tint": "rgba(217,83,79,0.10)", "edge": "#d9534f",
        "assets": [("Gold", "I"), ("TIPS / inflation-linked bonds", "I"), ("Commodities", "I")],
    },
    "refl": {   # top-right: Rising Growth + Rising Inflation
        "title": "Reflation · Inflationary Boom", "growth": "Rising growth", "infl": "Rising inflation",
        "tint": "rgba(232,163,23,0.10)", "edge": "#e8a317",
        "assets": [("Equities", "G"), ("Commodities", "I")],
    },
    "defl": {   # bottom-left: Falling Growth + Falling Inflation
        "title": "Deflation · Disinflationary Bust", "growth": "Falling growth", "infl": "Falling inflation",
        "tint": "rgba(76,155,232,0.10)", "edge": "#4c9be8",
        "assets": [("Long-duration Treasuries", "G"), ("Cash / short-duration bonds", "I"),
                   ("Major currencies (home cash)", "I")],
    },
    "gold": {   # bottom-right: Rising Growth + Falling Inflation
        "title": "Goldilocks · Disinflationary Boom", "growth": "Rising growth", "infl": "Falling inflation",
        "tint": "rgba(46,158,91,0.10)", "edge": "#2e9e5b",
        "assets": [("Equities", "G"), ("REITs", "G"), ("Crypto", "G")],
    },
}

# ── Ray's full driver-by-driver table (Stronger / Weaker / Mixed + reason) ────
_S, _W, _M = "Stronger", "Weaker", "Mixed"
_RAY_TABLE = [
    ("Equities (global)",            (_S, "earnings expectations rise; valuations expand"),
                                     (_W, "earnings slowdown; risk-off"),
                                     (_M, "moderate inflation helps some sectors; high inflation hurts margins"),
                                     (_S, "lower input costs, stable demand")),
    ("Long-duration nominal bonds",  (_W, "rates rise to match growth"),
                                     (_S, "rates fall as growth slows → prices rise"),
                                     (_W, "real yields erode"),
                                     (_S, "real yields improve")),
    ("TIPS / inflation-linked",      (_W, "real yields rise if growth outpaces inflation"),
                                     (_M, "benefit from low rates, but real yields flat"),
                                     (_S, "principal adjusts upward with CPI"),
                                     (_W, "real yield can go negative if inflation falls fast")),
    ("Commodities (broad)",          (_M, "supply can boost prices, but demand may be weak"),
                                     (_W, "lower demand"),
                                     (_S, "direct hedge against rising prices"),
                                     (_W, "lower price pressures")),
    ("Gold",                         (_M, "safe haven when growth is uncertain"),
                                     (_W, "less demand for 'alternative money'"),
                                     (_S, "classic inflation hedge & store of value"),
                                     (_W, "lower demand for alternative money")),
    ("REITs",                        (_S, "rents and property values rise with growth"),
                                     (_W, "slower demand for space, higher financing costs"),
                                     (_M, "moderate inflation lifts rents, high inflation raises costs"),
                                     (_S, "lower financing costs, stable demand")),
    ("Major currencies (USD/EUR/JPY)", (_M, "depends on relative policy; growth can strengthen if policy tightens"),
                                     (_W, "policy easing usually weakens"),
                                     (_M, "higher inflation can weaken unless offset by higher rates"),
                                     (_S, "lower inflation supports purchasing power")),
    ("Crypto (Bitcoin, etc.)",       (_M, "speculative demand surges in bull markets; high volatility"),
                                     (_W, "risk-off sentiment"),
                                     (_M, "sometimes an inflation hedge, but evidence is inconsistent"),
                                     (_W, "less appeal as alternative money")),
    ("Short-duration nominal bonds", (_W, "rates tend to rise"),
                                     (_S, "rates fall, but limited duration → modest upside"),
                                     (_W, "real yields erode"),
                                     (_S, "real yields improve")),
]

# Why each badge — the primary lever rationale.
_WHY = [
    ("Equities", _G, "Earnings/growth dominate; disinflation is a tailwind, but growth leads."),
    ("Commodities", _I, "A direct inflation hedge; demand (growth) is the secondary factor."),
    ("REITs", _G, "Rents and property values track growth; low financing costs help."),
    ("Crypto", _G, "Speculative risk-on/liquidity asset; its inflation-hedge case is inconsistent."),
    ("Gold", _I, "The premier inflation / currency-debasement hedge and store of value."),
    ("TIPS", _I, "Principal adjusts with CPI — inflation-linked by construction."),
    ("Long Treasuries", _G, "The growth-hedge — yields fall as recession forces rate cuts."),
    ("Cash / short bonds", _I, "Real return improves as inflation falls; capital preserved."),
    ("Major currencies", _I, "Purchasing power is supported when inflation stays low."),
]


# ── rendering ────────────────────────────────────────────────────────────────

def _badge(driver: str) -> html.Span:
    col = _G if driver == "G" else _I
    return html.Span(driver, title=("Growth" if driver == "G" else "Inflation") + " is the primary lever",
                     style={"display": "inline-flex", "alignItems": "center", "justifyContent": "center",
                            "width": "17px", "height": "17px", "borderRadius": "50%",
                            "background": col, "color": "#fff", "fontSize": "9.5px",
                            "fontWeight": "800", "marginLeft": "7px", "flexShrink": "0"})


def _asset_row(name: str, driver: str) -> html.Div:
    return html.Div([
        html.Span(name, style={"fontSize": "0.82rem", "fontWeight": "600",
                               "color": "var(--font-color)"}),
        _badge(driver),
    ], style={"display": "flex", "alignItems": "center", "padding": "4px 0"})


def _box(q: dict) -> html.Div:
    return html.Div([
        html.Div(q["title"], style={"fontSize": "0.82rem", "fontWeight": "800",
                 "color": q["edge"], "marginBottom": "1px"}),
        html.Div(f"{q['growth']} · {q['infl']}", style={"fontSize": "0.64rem",
                 "color": "var(--muted-color)", "textTransform": "uppercase",
                 "letterSpacing": "0.05em", "marginBottom": "8px"}),
        html.Div([_asset_row(n, d) for n, d in q["assets"]]),
    ], style={"background": q["tint"], "border": f"1px solid {q['edge']}55",
              "borderRadius": "10px", "padding": "14px 16px", "minHeight": "150px"})


def _verdict_cell(v: str, reason: str) -> html.Td:
    col = {_S: _G, _W: "#d9534f", _M: _I}[v]
    return html.Td([
        html.Span(v, style={"color": col, "fontWeight": "700", "fontSize": "0.72rem"}),
        html.Div(reason, style={"color": "var(--muted-color)", "fontSize": "0.66rem",
                                "lineHeight": "1.35", "marginTop": "2px"}),
    ], style={"padding": "8px 10px", "borderBottom": "1px solid var(--border-color)",
              "verticalAlign": "top"})


def get_layout() -> html.Div:
    _hdr = {"fontSize": "0.62rem", "fontWeight": "800", "textTransform": "uppercase",
            "letterSpacing": "0.06em", "color": "var(--muted-color)", "textAlign": "left",
            "padding": "8px 10px", "borderBottom": "1px solid var(--border-color)"}

    # ── The 2×2 matrix, laid out in Regime-Map orientation ──
    matrix = html.Div([
        # y-axis label
        html.Div([
            html.Div("INFLATION", style={"writingMode": "vertical-rl", "transform": "rotate(180deg)",
                     "fontSize": "0.62rem", "fontWeight": "800", "letterSpacing": "0.12em",
                     "color": "var(--muted-color)"}),
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "center",
                  "gridRow": "1 / 3", "gridColumn": "1"}),
        html.Div("Rising ↑", style={"gridRow": "1", "gridColumn": "2", "fontSize": "0.6rem",
                 "color": "var(--muted-color)", "alignSelf": "center", "paddingRight": "6px",
                 "textAlign": "right"}),
        html.Div("Falling ↓", style={"gridRow": "2", "gridColumn": "2", "fontSize": "0.6rem",
                 "color": "var(--muted-color)", "alignSelf": "center", "paddingRight": "6px",
                 "textAlign": "right"}),
        # boxes
        html.Div(_box(_QUADRANTS["stag"]), style={"gridRow": "1", "gridColumn": "3"}),
        html.Div(_box(_QUADRANTS["refl"]), style={"gridRow": "1", "gridColumn": "4"}),
        html.Div(_box(_QUADRANTS["defl"]), style={"gridRow": "2", "gridColumn": "3"}),
        html.Div(_box(_QUADRANTS["gold"]), style={"gridRow": "2", "gridColumn": "4"}),
        # x-axis labels
        html.Div("Falling ↓", style={"gridRow": "3", "gridColumn": "3", "fontSize": "0.6rem",
                 "color": "var(--muted-color)", "textAlign": "center", "paddingTop": "4px"}),
        html.Div("Rising →", style={"gridRow": "3", "gridColumn": "4", "fontSize": "0.6rem",
                 "color": "var(--muted-color)", "textAlign": "center", "paddingTop": "4px"}),
        html.Div("GROWTH", style={"gridRow": "4", "gridColumn": "3 / 5", "fontSize": "0.62rem",
                 "fontWeight": "800", "letterSpacing": "0.12em", "color": "var(--muted-color)",
                 "textAlign": "center", "paddingTop": "2px"}),
    ], style={"display": "grid", "gridTemplateColumns": "22px 58px 1fr 1fr",
              "gridTemplateRows": "1fr 1fr auto auto", "gap": "12px", "maxWidth": "820px"})

    legend = html.Div([
        html.Span("Primary lever:", style={"color": "var(--muted-color)", "fontSize": "0.72rem",
                  "marginRight": "10px"}),
        _badge("G"), html.Span("Growth-driven", style={"fontSize": "0.72rem", "margin": "0 16px 0 6px",
                  "color": "var(--font-color)"}),
        _badge("I"), html.Span("Inflation-driven", style={"fontSize": "0.72rem", "marginLeft": "6px",
                  "color": "var(--font-color)"}),
    ], style={"display": "flex", "alignItems": "center", "marginTop": "16px", "flexWrap": "wrap"})

    # ── details: full driver table ──
    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Bucket", style=_hdr),
            html.Th("Rising growth", style=_hdr), html.Th("Falling growth", style=_hdr),
            html.Th("Rising inflation", style=_hdr), html.Th("Falling inflation", style=_hdr),
        ])),
        html.Tbody([
            html.Tr([
                html.Td(row[0], style={"padding": "8px 10px", "fontWeight": "700",
                        "fontSize": "0.76rem", "color": "var(--font-color)",
                        "borderBottom": "1px solid var(--border-color)", "verticalAlign": "top"}),
                _verdict_cell(*row[1]), _verdict_cell(*row[2]),
                _verdict_cell(*row[3]), _verdict_cell(*row[4]),
            ]) for row in _RAY_TABLE
        ]),
    ], style={"width": "100%", "borderCollapse": "collapse", "marginTop": "10px"})

    why = html.Div([
        html.Div([
            html.Span(name, style={"fontWeight": "700", "color": "var(--font-color)",
                      "fontSize": "0.78rem"}),
            _badge("G" if col == _G else "I"),
            html.Span(text, style={"color": "var(--muted-color)", "fontSize": "0.75rem",
                      "marginLeft": "8px"}),
        ], style={"padding": "5px 0", "display": "flex", "alignItems": "baseline", "flexWrap": "wrap"})
        for name, col, text in _WHY
    ])

    def _h2(txt):
        return html.Div(txt, style={"fontSize": "0.95rem", "fontWeight": "800",
                        "color": "var(--font-color)", "margin": "30px 0 6px"})

    def _p(txt):
        return html.Div(txt, style={"fontSize": "0.8rem", "color": "var(--muted-color)",
                        "lineHeight": "1.55", "marginBottom": "8px"})

    return html.Div([
        html.Div([
            html.Span("🧭 ", style={"fontSize": "1.3rem"}),
            html.Span("Assets by Environment", style={"fontSize": "1.15rem", "fontWeight": "700",
                      "color": "var(--font-color)"}),
        ]),
        html.Div("Which buckets tend to do well in each growth × inflation regime — the four "
                 "All-Weather quadrants. The badge on each asset marks its primary driver in "
                 "that box.", style={"color": "var(--muted-color)", "fontSize": "0.82rem",
                 "marginTop": "4px", "marginBottom": "18px", "maxWidth": "760px"}),
        matrix,
        legend,

        _h2("Why the badges"),
        _p("Most assets respond to both growth and inflation — the badge flags the one that "
           "usually dominates its return in that box, so you can see at a glance whether a "
           "holding is really a growth bet or an inflation bet."),
        why,

        _h2("Full driver-by-driver detail"),
        _p("Ray's read of each bucket under all four individual drivers. “Stronger” = tends to "
           "earn positive excess return for its risk in that regime; “Weaker” = typically lags "
           "or loses; “Mixed” = contingent on policy, sector, or liquidity."),
        table,

        _h2("Why this matters for diversification"),
        _p("Different assets have different sensitivities to growth and inflation. By holding a "
           "mix that covers all four quadrants, you build a portfolio that can perform reasonably "
           "well no matter which environment arrives — the core idea behind all-weather / "
           "risk-parity construction. This page is a diagnostic reference, not allocation advice."),

        html.Div("Source: a Digital Ray consult (2026-07-15). digitalray.ai output is an AI "
                 "approximation of Ray Dalio's framework, not vetted by Ray Dalio. Quadrant "
                 "placements and primary-lever badges are our reading of his driver table.",
                 style={"fontSize": "0.68rem", "color": "var(--muted-color)", "marginTop": "26px",
                        "opacity": "0.75"}),
    ], className="p-3", style={"maxWidth": "1100px"})

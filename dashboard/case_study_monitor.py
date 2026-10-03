"""Case Study Monitor — the charts Dalio's own EMP course uses to position a
country in its case studies (e.g. "Case: United States 2003-2018"), audited
directly against that course's interactive chart panel and built where a free
source existed. Visual pattern reused verbatim from dashboard.fed_monitor so
this reads as a sibling page, not a different dashboard style.

Three sections:
  1. Growth composition  — the GDP demand components beneath the headline
                            growth number (housing, business capex, savings)
  2. Output gap           — spare capacity vs. the CBO's potential-GDP estimate
  3. Credit creation       — the FLOW of new borrowing, not the debt stock —
                              paired with QE/balance-sheet growth to read
                              whether stimulus is "pushing on a string"

All ten signals feed no composite and don't touch the regime engine — purely
additive reference signals, same convention as fed.*/market.*/order.*.
"""
from __future__ import annotations

import pandas as pd
from dash import html

from dashboard.fed_monitor import (
    _CC, _chart_card, _section, _chip, _hist, _hist_pct, _latest, _pct,
    _BLUE, _AMBER, _RED, _GREEN, _GREY,
)


def _cur(concept: str):
    v, _ = _latest(concept)
    return v


def _yoy_from_level(concept: str, periods: int = 4) -> pd.DataFrame:
    """YoY % growth computed from a stored LEVEL series (e.g. potential GDP, which
    is bound as a level so it can feed growth.output_gap) — display-only, mirrors
    the on-the-fly derived calcs already used in fed_monitor._ratio()."""
    df = _hist(concept)
    if df.empty:
        return df
    s = df.set_index("as_of")["value"].sort_index()
    yoy = (s / s.shift(periods) - 1.0) * 100.0
    out = yoy.dropna().reset_index()
    out.columns = ["as_of", "value"]
    return out


def _header() -> html.Div:
    gap = _cur("growth.output_gap")
    priv = _cur("credit.private_credit_creation")
    home = _cur("growth.home_prices")
    dxy = _cur("currency.broad_dollar_index")

    gap_pct = None if gap is None else gap * 100.0
    gap_read = ("running hot" if (gap_pct or 0) > 1.0 else
                "running cold" if (gap_pct or 0) < -1.0 else "near potential")
    gap_col = _RED if (gap_pct or 0) > 1.0 else _BLUE if (gap_pct or 0) < -1.0 else _GREEN

    priv_read = ("private credit expanding" if (priv or 0) > 0.5 else
                 "private deleveraging" if (priv or 0) < -0.5 else "flat")
    priv_col = _RED if (priv or 0) > 0.5 else _GREEN if (priv or 0) < -0.5 else _AMBER

    return html.Div([
        html.Div([
            html.Span("🗂 ", style={"fontSize": "1.3rem"}),
            html.Span("Case Study Monitor", style={"fontSize": "1.15rem", "fontWeight": "700",
                                                    "color": "var(--font-color)"}),
            html.Span(" · United States", style={"fontSize": "0.8rem",
                                                 "color": "var(--muted-color)"}),
        ]),
        html.Div([
            _chip(f"Output gap {gap_pct:+.1f}% · {gap_read}" if gap_pct is not None else "output gap —", gap_col),
            _chip(f"Private credit creation {priv:+.1f}pp · {priv_read}" if priv is not None else "credit creation —", priv_col),
            _chip(f"Home prices {home*100:+.1f}% YoY" if home is not None else "home prices —", _BLUE),
            _chip(f"Dollar index {dxy*100:+.1f}% YoY" if dxy is not None else "dollar index —", _GREY),
        ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginTop": "8px"}),
    ], style={"borderBottom": "1px solid var(--border-color)", "paddingBottom": "12px"})


def get_layout() -> html.Div:
    # 1) Growth composition
    s1 = _section(
        "① Growth composition — beneath the headline number",
        "The GDP demand components the EMP course charts individually, not just the summary growth rate.",
        [
            _chart_card("Residential investment (YoY)", _hist_pct("growth.residential_investment"),
                        _pct(_cur("growth.residential_investment")), "%",
                        "Housing construction/improvement — earliest-turning GDP component.",
                        zero_line=True, color=_BLUE,
                        info="Real private residential fixed investment, year-over-year. Highly "
                             "rate-sensitive and historically one of the first components to turn in "
                             "both directions — a classic leading indicator for the short-term cycle."),
            _chart_card("Business investment (YoY)", _hist_pct("growth.business_investment"),
                        _pct(_cur("growth.business_investment")), "%",
                        "Capex — tracks credit availability and expected demand.",
                        zero_line=True, color=_AMBER,
                        info="Real private nonresidential fixed investment, year-over-year — business "
                             "capital expenditure. A leading signal for the productive capacity "
                             "businesses are willing to fund, and sensitive to both credit conditions "
                             "and demand expectations."),
            _chart_card("Personal saving rate", _hist("growth.savings_rate"),
                        _cur("growth.savings_rate"), "%",
                        "Rising = precautionary pullback; falling = pulling consumption forward.",
                        color=_GREEN,
                        info="Personal saving as a percent of disposable income. A rising rate signals "
                             "households retrenching (a consumption headwind ahead); a falling rate "
                             "signals consumption being pulled forward against future income — relevant "
                             "to how sustainable current spending is."),
            _chart_card("Home prices (YoY)", _hist_pct("growth.home_prices"),
                        _pct(_cur("growth.home_prices")), "%",
                        "Wealth effects feed consumption directly; a recurring debt-cycle trigger.",
                        zero_line=True, color=_RED,
                        info="S&P Case-Shiller US National Home Price Index, year-over-year. Housing "
                             "wealth effects flow directly into consumption and credit creation (home "
                             "equity borrowing); a home-price bust is a recurring trigger across Dalio's "
                             "own debt-cycle case studies, including the US 2008 case."),
        ])

    # 2) Output gap & rate backdrop
    s2 = _section(
        "② Output gap & rate backdrop — room to grow, cost of capital",
        "The EMP course's own paired overlay charts — Real Growth vs. Potential, and Short vs. Long Rate "
        "— shown as dual lines exactly as the course does, not as two separate signals.",
        [
            _chart_card("Real Growth vs. Potential Growth", _hist_pct("master.gdp_real"),
                        _pct(_cur("master.gdp_real")), "%",
                        "Running above the black line draws down spare capacity; below it, capacity builds.",
                        zero_line=True, color=_BLUE,
                        df2=_yoy_from_level("growth.potential_gdp"), color2=_GREY,
                        label="Real Growth", label2="Potential Growth",
                        info="Real GDP growth (YoY) against the CBO's estimate of potential GDP growth "
                             "(YoY) — the EMP course's own dual-line chart. When actual growth runs above "
                             "potential, the economy is drawing down spare capacity (the output gap is "
                             "closing or has gone positive); below potential, slack is building. The same "
                             "comparison the Output Gap chart expresses as a single percentage."),
            _chart_card("Short Rate vs. Long Rate", _hist("policy.fed_funds"),
                        _cur("policy.fed_funds"), "%",
                        "The short end (Fed-set) against the long end (market-set, growth+inflation priced in).",
                        color=_RED,
                        df2=_hist("policy.yield_10y"), color2=_BLUE,
                        label="Short Rate", label2="Long Rate",
                        info="The effective fed funds rate (short, policy-set) against the 10-year "
                             "Treasury yield (long, market-set) — the EMP course's own dual-line chart. "
                             "The gap between them (the long rate minus the short rate) is the yield "
                             "curve; watched together they show whether policy is leading or lagging "
                             "where the market expects growth and inflation to go."),
            _chart_card("Output gap vs. potential GDP", _hist_pct("growth.output_gap"),
                        _pct(_cur("growth.output_gap")), "%",
                        "(Real GDP − CBO potential) ÷ potential. Positive = running above sustainable speed.",
                        zero_line=True, color=_AMBER, fill=True,
                        info="The gap between actual real GDP and the CBO's estimate of potential GDP "
                             "(the non-inflationary speed limit), as a percent of potential. Positive = "
                             "spare capacity is being used up and growth above potential risks fuelling "
                             "inflation; negative = slack remains and growth can continue without "
                             "inflationary pressure. Directly from the EMP course's US case study (Q3)."),
            _chart_card("Capacity utilisation", _hist("growth.capacity_util"),
                        _cur("growth.capacity_util"), "%",
                        "Above ~82% = constrained supply; below ~75% = slack.",
                        hline=82.0, hline_txt="~82% constrained", color=_BLUE,
                        info="The percent of industrial capacity actually in use. A second, "
                             "industry-level read on the same question the output gap asks economy-wide: "
                             "how much spare capacity is left before growth itself becomes inflationary."),
        ])

    # 3) Credit creation — is the stimulus flowing
    s3 = _section(
        "③ Credit creation — is the stimulus actually flowing",
        "The FLOW of new borrowing (not the debt stock) — the EMP course's 'Pushing on a string' question: "
        "if the Fed eases but private credit doesn't pick up, policy is losing traction.",
        [
            _chart_card("Private credit creation", _hist("credit.private_credit_creation"),
                        _cur("credit.private_credit_creation"), "%",
                        "YoY point change in household+corporate debt/GDP. New borrowing, not the stock level.",
                        zero_line=True, color=_RED,
                        info="The year-over-year change (in percentage points) of household plus "
                             "corporate debt as a percent of GDP — the FLOW of new private credit "
                             "creation, distinct from the debt stock levels tracked elsewhere (credit."
                             "household_debt_gdp / credit.corporate_debt_gdp). Positive = new borrowing "
                             "is outpacing GDP growth; negative = private-sector deleveraging is "
                             "underway."),
            _chart_card("Govt. credit creation", _hist("credit.govt_credit_creation"),
                        _cur("credit.govt_credit_creation"), "%",
                        "YoY point change in government debt/GDP. The flow of new fiscal-deficit financing.",
                        zero_line=True, color=_AMBER,
                        info="The year-over-year change (in percentage points) of government debt as a "
                             "percent of GDP — how much new sovereign borrowing is being created, as "
                             "distinct from the total government debt stock already tracked elsewhere."),
            _chart_card("Fed balance sheet (YoY)", _hist_pct("policy.fed_balance_sheet"),
                        _pct(_cur("policy.fed_balance_sheet")), "%",
                        "QE growth — compare against private credit creation above.",
                        zero_line=True, color=_BLUE,
                        info="The Fed's own balance-sheet growth, shown again here (also on Fed Monitor) "
                             "specifically to sit beside private credit creation. If this rises while "
                             "private credit creation stays flat or falls, that is the literal 'pushing "
                             "on a string' pattern the EMP course names: QE isn't translating into actual "
                             "private borrowing."),
            _chart_card("Net domestic debt (% GDP, 12mo avg)", _hist("credit.net_domestic_debt_gdp"),
                        _cur("credit.net_domestic_debt_gdp"), "%",
                        "Gov + household + corporate debt, summed — the economy-wide leverage level.",
                        color=_GREY, fill=True,
                        info="Government, household, and corporate debt summed as a percent of GDP, "
                             "smoothed over a 4-quarter (12-month) moving average — the EMP course's own "
                             "'Net Domestic Debt' chart. The single-number economy-wide leverage level "
                             "that the long-term debt cycle ultimately has to deleverage."),
        ])

    s4 = _section(
        "④ Currency",
        "A nominal, trade-weighted read — distinct from the real/BIS REER already tracked elsewhere.",
        [
            _chart_card("Broad dollar index (YoY)", _hist_pct("currency.broad_dollar_index"),
                        _pct(_cur("currency.broad_dollar_index")), "%",
                        "Nominal trade-weighted dollar. Strength tightens conditions for the rest of the world.",
                        zero_line=True, color=_GREY,
                        info="The Fed's Nominal Broad US Dollar Index, year-over-year — a trade-weighted "
                             "basket, in nominal terms. Distinct from currency.reer (real, BIS-sourced), "
                             "this is the nominal gauge the EMP course's own indexed-currency chart uses. "
                             "Dollar strength tightens financial conditions globally, especially for "
                             "dollar-debtor economies."),
        ])

    note = html.Div(
        "Built from a direct chart-by-chart audit of the Dalio EMP course's own interactive case-study "
        "panel (\"Case: United States 2003-2018\") against the live signal catalog. All FRED series "
        "independently verified before binding, per house rule. These signals feed no composite and do "
        "not affect the regime engine — reference context only, same convention as Fed Monitor and "
        "Market Expectations.",
        style={"fontSize": "0.68rem", "color": "var(--muted-color)", "marginTop": "24px",
               "opacity": "0.75"})

    return html.Div([_header(), s1, s2, s3, s4, note],
                    className="p-3", style={"maxWidth": "1500px"})

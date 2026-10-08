"""Fed Monitor — a US Federal Reserve dashboard (Digital Ray consult 2026-07-10).

Sections, in Ray's Economic-Machine framing:
  1. Yield curve             — the term structure and the inversion read
  2. Short-term cycle        — where the Fed is in / headed for the business cycle
  3. Rates vs inflation      — is money easy/tight, is the Fed behind/ahead
  4. Balance sheet & liquidity — QE/QT, reserves, ON RRP
  5. Turning points          — inversion, real-rate zero cross, reserve scarcity
  6. Late-cycle monetization — MP1->MP2->MP3 (the "How Countries Go Broke" panel)
  7. Central bank balance sheet — the one cross-country section (US/EZ/JP)

Each chart is a time series with the current value and, where relevant, the
threshold Ray named. Curated from signals we already ingest plus seven new
`fed.*` monitoring series. Read-only against the signals DB.

Two pages were folded in here during the 2026-10-06 UI consolidation:

  * The standalone **Yield Curve** page — its term-structure chart is now
    section ①'s first card (latest observation only; the page's two date
    pickers and the compare-curve feature were dropped on instruction, so
    this is a glanceable read rather than an explorer). Its second chart,
    the historical 10y-2y spread, already existed here as a `_chart_card`,
    so it was moved up into ① rather than duplicated.

  * The standalone **Central Bank Monitor** — section ⑦. That page's whole
    point was being cross-country (US/EZ/JP) while this one is hardcoded
    US-only (`_CC = "us"` is a module constant, not threaded from the
    country selector), so rather than lose the Euro Area and Japan reads,
    ⑦ alone is country-reactive: it is rendered by a callback on
    `country-store`, exactly as central_bank_monitor.py was. Every other
    section on this page remains United States.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html, no_update

from dashboard.charting_data import (
    align_as_of,
    load_signal_history,
    load_yield_curve_term_structure,
)
from dashboard.shared_components import AMBER as _AMBER
from dashboard.shared_components import BLUE as _BLUE
from dashboard.shared_components import GREEN as _GREEN
from dashboard.shared_components import GREY as _GREY
from dashboard.shared_components import RED as _RED
from dashboard.shared_components import (
    _chart_card,
    _chip,
    _info_icon,
    _section,
)
from dashboard.themes import DEFAULT_THEME, figure_layout

_CC = "us"
_START = "2006-01-01"          # a useful window that spans the GFC, COVID, QT
_COLUMNS = 2                   # every section is two cards wide (2026-10-06 UI pass)

# colours
# Canonical semantic palette — sourced from shared_components (see the
# import above), not redefined here. Kept under these short names since
# case_study_monitor.py and market_expectations.py import them directly.


# ── data helpers ─────────────────────────────────────────────────────────────

def _hist(concept: str, start: str | None = _START) -> pd.DataFrame:
    return load_signal_history(f"{_CC}.{concept}", start_date=start)


def _hist_pct(concept: str, start: str | None = _START) -> pd.DataFrame:
    """For decimal-stored (yoy_pct) signals: scale to percent for display."""
    df = _hist(concept, start)
    if not df.empty:
        df = df.copy()
        df["value"] = df["value"] * 100.0
    return df


def _latest(concept: str):
    df = load_signal_history(f"{_CC}.{concept}")
    if df.empty:
        return None, None
    return float(df["value"].iloc[-1]), pd.to_datetime(df["as_of"].iloc[-1])


def _to_bn(concept: str, unit: str) -> pd.DataFrame:
    """Load a stock series and normalise to $ billions (some FRED series are millions)."""
    df = _hist(concept)
    if df.empty:
        return df
    df = df.copy()
    if unit == "m":                    # millions → billions
        df["value"] = df["value"] / 1000.0
    return df


def _ratio(num: pd.DataFrame, den: pd.DataFrame) -> pd.DataFrame:
    """Percent ratio of two (possibly different-frequency) series, date-aligned.

    Aligns on the DENSER series so the ratio is charted at its frequency: each
    row of the denser series is matched to the latest value of the sparser one.
    """
    if num.empty or den.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    # align_as_of on both sides: every caller currently feeds it DuckDB-sourced
    # frames (uniformly datetime64[us]), so the pair matches today — but a
    # parquet/FRED-cached series (ns) on either side would make merge_asof
    # raise, as it did on /debt-stress (worklog 2026-10-07). Cheap insurance.
    n = align_as_of(num.rename(columns={"value": "n"})).sort_values("as_of")
    d = align_as_of(den.rename(columns={"value": "d"})).sort_values("as_of")
    if len(d) >= len(n):                       # den is denser → base on it
        m = pd.merge_asof(d, n, on="as_of")
    else:
        m = pd.merge_asof(n, d, on="as_of")
    m["value"] = 100.0 * m["n"] / m["d"]
    return m[["as_of", "value"]].dropna()


def _fed_net_issuance_share(window_q: int = 4) -> pd.DataFrame:
    """Fed's share of NET NEW debt issuance over a trailing window, % (Ray: >30-40% = red).

    ΔFed Treasury holdings ÷ Δmarketable debt, both quarter-end, over `window_q`
    quarters. Ratio clipped to a sane band (issuance can be lumpy quarter-to-quarter).
    """
    th = _to_bn("fed.treasury_holdings", "m")     # weekly, $bn
    md = _to_bn("fed.marketable_debt", "b")        # monthly, $bn
    if th.empty or md.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    thq = (th.set_index("as_of")["value"].resample("QE").last())
    mdq = (md.set_index("as_of")["value"].resample("QE").last())
    d_th = thq.diff(window_q)
    d_md = mdq.diff(window_q)
    df = pd.concat([d_th, d_md], axis=1, keys=["dth", "dmd"]).dropna()
    df = df[df["dmd"].abs() > 1.0]                 # avoid divide-by-tiny
    df["value"] = (100.0 * df["dth"] / df["dmd"]).clip(-50, 150)
    return df.reset_index()[["as_of", "value"]]


def _fed_interest_to_revenue() -> pd.DataFrame:
    """Federal interest outlays ÷ receipts, % (Ray's debt-trap gauge, ~15-20% = danger)."""
    interest = _hist("fiscal.interest_payments")      # annual, $ millions
    receipts = _hist("fiscal.govt_receipts_qtr")      # quarterly, $ billions (annual rate)
    if interest.empty or receipts.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    interest = interest.copy()
    interest["value"] = interest["value"] / 1000.0    # → $ billions
    return _ratio(interest, receipts)


# ── Treasury term structure (folded in from the retired Yield Curve page) ────
# Not a `_chart_card`: its x-axis is MATURITY, not time, so the shared card's
# date hovertemplate and time-series trace don't apply. The chrome below is a
# deliberate copy of `_chart_card`'s so the two cards in section ① read as a
# matched pair — if that card's styling changes, this needs the same change.

# Short labels for the catalog's "3-Month"/"30-Year" names.
_TERM_TICK_LABEL = {"3-Month": "3M", "6-Month": "6M", "1-Year": "1Y", "2-Year": "2Y",
                    "3-Year": "3Y", "5-Year": "5Y", "7-Year": "7Y", "10-Year": "10Y",
                    "20-Year": "20Y", "30-Year": "30Y"}


def _term_structure_card() -> html.Div:
    """Latest US Treasury term structure, in the shared Monitor-card chrome."""
    title = "Treasury term structure (latest)"
    info = ("The yield on US Treasury debt at every maturity from 3 months to 30 years, "
            "plotted left to right — the 'shape' of the curve. Normally it slopes upward: "
            "lending for longer costs more. A flat or downward (inverted) shape means the "
            "market expects rate cuts, i.e. a slowing economy. This is the whole curve at "
            "one moment; the card beside it tracks the single most-watched slice of it "
            "(10y minus 2y) through time.")

    df = load_yield_curve_term_structure(pd.Timestamp.today().strftime("%Y-%m-%d"))
    fig = go.Figure()
    cur_txt = "—"
    read = "US Treasury yields by maturity — upward slope is normal, inverted is not."
    if not df.empty:
        df = df.sort_values("maturity_years")
        ticks = [_TERM_TICK_LABEL.get(lbl, lbl) for lbl in df["label"]]
        # Evenly spaced (categorical) maturities, not linear years: on a true
        # 0.25-to-30 numeric axis the entire short end — where inversions
        # actually show up — collapses into the leftmost few pixels with its
        # tick labels overlapping. Even spacing is also how a yield curve is
        # conventionally drawn.
        fig.add_trace(go.Scatter(
            x=ticks, y=df["yield_pct"],
            mode="lines+markers", name=title,
            line=dict(color=_BLUE, width=1.7, shape="spline", smoothing=0.5),
            marker=dict(size=6),
            customdata=df["label"],
            hovertemplate="<b>%{customdata}</b>: %{y:.2f}%<extra></extra>"))
        # Header value = the 10-year, the number people quote for "the" yield.
        tens = df[df["maturity_years"] == 10]
        anchor = tens if not tens.empty else df.tail(1)
        cur_txt = f"{float(anchor['yield_pct'].iloc[0]):.2f}%"
        short = float(df["yield_pct"].iloc[0])
        long = float(df["yield_pct"].iloc[-1])
        shape = ("inverted — short rates above long"
                 if long - short < -0.1 else
                 "flat — little term compensation"
                 if long - short < 0.25 else
                 "upward-sloping — the normal shape")
        read = f"{ticks[0]}→{ticks[-1]}: {shape}."

    lay = figure_layout(DEFAULT_THEME)
    # No `fill="tozeroy"` here, unlike the stock-level cards: anchoring to zero
    # squashes a 3.8-5.3% curve into a flat band at the top of the panel and
    # hides the shape, which is the only thing this chart is for.
    lay.update(height=180, margin=dict(l=6, r=8, t=6, b=18), showlegend=False,
               xaxis=dict(showgrid=False, type="category"),
               yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                          ticksuffix="%"))
    fig.update_layout(**lay)

    return html.Div([
        html.Div([
            html.Span(title, style={"fontSize": "0.78rem", "fontWeight": "700",
                                    "color": "var(--font-color)"}),
            _info_icon(info, scope=title),
            html.Span(cur_txt, style={"fontSize": "0.95rem", "fontWeight": "700",
                                      "fontFamily": "monospace", "color": _BLUE,
                                      "float": "right"}),
        ]),
        html.Div(read, style={"fontSize": "0.66rem", "color": "var(--muted-color)",
                              "marginBottom": "2px", "minHeight": "1.6em"}),
        dcc.Graph(figure=fig, responsive=True, config={"displayModeBar": False},
                  style={"height": "180px"}),
    ], style={"background": "var(--card-bg)", "border": "1px solid var(--border-color)",
              "borderRadius": "8px", "padding": "10px 12px", "flex": "1 1 300px",
              "minWidth": "280px"})


# ── header read ──────────────────────────────────────────────────────────────

def _header() -> html.Div:
    real, _ = _latest("policy.real_fed_funds")
    fwd, _ = _latest("fed.fwd_inflation_5y5y")
    rrp, _ = _latest("fed.on_rrp")
    remit, _ = _latest("fed.remittances")
    # Fed share of marketable debt
    th = _to_bn("fed.treasury_holdings", "m")
    md = _to_bn("fed.marketable_debt", "b")
    share = None
    if not th.empty and not md.empty:
        r = _ratio(th, md)
        share = float(r["value"].iloc[-1]) if not r.empty else None

    money = ("money tight" if (real or 0) > 0.25 else
             "money easy" if (real or 0) < -0.25 else "roughly neutral")
    money_col = _RED if (real or 0) > 0.25 else _GREEN if (real or 0) < -0.25 else _AMBER
    ahead = ("Fed ~on target" if fwd and abs(fwd - 2.0) < 0.25 else
             "expectations above target" if fwd and fwd >= 2.25 else "expectations soft")
    # MP-phase heuristic
    mp = "MP1 (rate policy)"
    if remit is not None and remit < 0 and share is not None and share > 12:
        mp = "MP2 → watch MP3 (losses + high Fed share)"
    elif share is not None and share > 12:
        mp = "MP2 (large Fed footprint)"

    return html.Div([
        html.Div([
            html.Span("🏛 ", style={"fontSize": "1.3rem"}),
            html.Span("Fed Monitor", style={"fontSize": "1.15rem", "fontWeight": "700",
                                            "color": "var(--font-color)"}),
            html.Span(" · United States", style={"fontSize": "0.8rem",
                                                 "color": "var(--muted-color)"}),
        ]),
        html.Div([
            _chip(f"Real policy rate {real:+.2f}% · {money}" if real is not None else "real rate —", money_col),
            _chip(f"5y5y fwd infl {fwd:.2f}% · {ahead}" if fwd is not None else "5y5y —", _BLUE),
            _chip(f"Fed share of debt {share:.1f}%" if share is not None else "fed share —",
                  _RED if (share or 0) > 15 else _AMBER),
            _chip(mp, _AMBER),
        ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginTop": "8px"}),
    ], style={"borderBottom": "1px solid var(--border-color)", "paddingBottom": "12px"})


# ── layout ───────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    # helper values for reads
    def cur(c):
        v, _ = _latest(c)
        return v

    # 1) yield curve — the two charts from the retired standalone page
    s0 = _section(
        "① Yield curve — term structure and the inversion read",
        "The whole curve right now, and the 10y−2y slice through time.",
        [
            _term_structure_card(),
            _chart_card("Yield curve (10y − 2y)", _hist("premium.yield_curve_10y2y"),
                        cur("premium.yield_curve_10y2y"), "%", "Inversion (<0) historically leads recession.",
                        zero_line=True, color=_GREEN,
                        info="The 10-year Treasury yield minus the 2-year. Normally positive — longer "
                             "money costs more. When it inverts (goes negative) the market is betting on "
                             "rate cuts ahead, i.e. a slowing economy. Inversion has preceded every US "
                             "recession of the last ~50 years, typically by 6–18 months."),
        ], columns=_COLUMNS)

    # 2) short-term cycle
    s1 = _section(
        "② Short-term cycle — where the Fed is headed",
        "The policy stance and the levers that steer the 5–8yr business cycle.",
        [
            _chart_card("Effective Fed Funds", _hist("policy.fed_funds"), cur("policy.fed_funds"),
                        "%", "The core policy lever.", color=_BLUE,
                        info="The interest rate banks charge each other for overnight loans, which "
                             "the Fed steers directly through its target range. It is the base cost "
                             "of money — nearly every other rate is priced off it. Rising = the Fed "
                             "tightening to cool growth and inflation; falling = easing to support "
                             "activity."),
            _chart_card("Real policy rate", _hist("policy.real_fed_funds"), cur("policy.real_fed_funds"),
                        "%", "Funds − core inflation. >0 tight, <0 easy.", zero_line=True, color=_AMBER,
                        info="The fed funds rate minus core inflation — the policy rate after stripping "
                             "out inflation. This is what actually bites: a 5% rate with 5% inflation "
                             "(0% real) isn't restrictive. Above 0 = money is genuinely tight and "
                             "restraining the economy; below 0 = stimulative even if the headline rate "
                             "looks high."),
            _chart_card("Rate expectations (2y − funds)", _hist("policy.rate_expectations"),
                        cur("policy.rate_expectations"), "%", "Market-implied path: + = hikes priced, − = cuts.",
                        zero_line=True, color=_BLUE,
                        info="The 2-year Treasury yield minus the current fed funds rate. The 2y yield "
                             "embeds the market's average expected policy rate over the next two years, "
                             "so the gap reveals what traders think the Fed will do next. Positive = "
                             "hikes are priced in; negative = the market expects cuts."),
            # The 10y−2y card that used to sit here moved up into section ①
            # alongside the term structure — it is the same chart, and two
            # adjacent sections showing it would read as a bug.
            _chart_card("Bank lending standards (SLOOS)", _hist("credit.lending_standards"),
                        cur("credit.lending_standards"), "%", "Net % tightening C&I standards; high = credit squeeze.",
                        color=_RED,
                        info="From the Fed's quarterly Senior Loan Officer Opinion Survey: the net "
                             "percent of banks tightening standards on business (C&I) loans. High "
                             "positive = banks are pulling back credit, which chokes off investment and "
                             "hiring. A leading indicator of credit-driven slowdowns."),
            _chart_card("Corporate credit spread", _hist("premium.credit_spread_corp"),
                        cur("premium.credit_spread_corp"), "%", "Widening = tighter financial conditions.", color=_RED,
                        info="The extra yield investment-grade corporate bonds pay over Treasuries of "
                             "the same maturity — the market's price for corporate default risk. "
                             "Widening spreads mean investors demand more compensation for risk, i.e. "
                             "financial conditions are tightening and stress is building, often before "
                             "it shows up in the real economy."),
        ], columns=_COLUMNS)

    # 2) rates vs inflation
    s2 = _section(
        "③ Rates vs inflation — easy or tight, behind or ahead",
        "Frame policy against inflation and expectations.",
        [
            _chart_card("Real policy rate", _hist("policy.real_fed_funds"), cur("policy.real_fed_funds"),
                        "%", "The single best easy/tight gauge.", zero_line=True, color=_AMBER,
                        info="Fed funds minus core inflation — the cleanest single read on whether "
                             "money is easy or tight. Sustained above zero restrains the economy; below "
                             "zero stimulates it. Watch the trend as much as the level: a rising real "
                             "rate tightens conditions even before it crosses into positive territory."),
            _chart_card("5y5y forward inflation", _hist("fed.fwd_inflation_5y5y"),
                        cur("fed.fwd_inflation_5y5y"), "%", "Long-run market anchor; > target = Fed behind.",
                        hline=2.0, hline_txt="2% target", color=_BLUE,
                        info="The inflation rate the market expects for the five-year period starting "
                             "five years from now, derived from inflation swaps and TIPS. Looking that "
                             "far out strips away today's oil-price noise and shows whether long-run "
                             "expectations stay anchored. Drifting above the Fed's 2% target signals the "
                             "Fed is seen as behind the curve."),
            _chart_card("Core PCE (YoY)", _hist_pct("inflation.pce_core"),
                        _pct(cur("inflation.pce_core")), "%", "The Fed's preferred inflation gauge.",
                        hline=2.0, hline_txt="2% target", color=_RED,
                        info="The year-over-year change in the core Personal Consumption Expenditures "
                             "price index (excluding volatile food and energy). This is the Fed's "
                             "preferred inflation measure — the one its 2% target is defined against. "
                             "Above 2% and sticky = pressure to keep policy tight."),
            _chart_card("Avg breakeven inflation", _hist("inflation.breakeven_avg"),
                        cur("inflation.breakeven_avg"), "%", "Market-implied CPI (5y/10y TIPS).", color=_BLUE,
                        info="The average of the 5-year and 10-year breakeven rates — the gap between "
                             "nominal Treasury yields and inflation-protected (TIPS) yields — i.e. the "
                             "inflation the bond market is actually pricing in. A market-based inflation "
                             "forecast; rising breakevens mean the market expects more inflation ahead."),
        ], columns=_COLUMNS)

    # 3) balance sheet & liquidity
    s3 = _section(
        "④ Balance sheet & liquidity — QE / QT",
        "The scale of the Fed's footprint and the liquidity in the system.",
        [
            _chart_card("Fed balance sheet (YoY)", _hist_pct("policy.fed_balance_sheet"),
                        _pct(cur("policy.fed_balance_sheet")), "%", "+ = QE (easing), − = QT (tightening).",
                        zero_line=True, color=_AMBER,
                        info="The year-over-year percent change in the Fed's total assets. Positive = "
                             "the Fed is expanding its balance sheet by buying bonds (quantitative "
                             "easing), injecting liquidity and easing; negative = it is shrinking "
                             "(quantitative tightening), draining liquidity. The direction and scale of "
                             "unconventional policy at a glance."),
            _chart_card("Fed Treasury holdings", _to_bn("fed.treasury_holdings", "m"),
                        (cur("fed.treasury_holdings") or 0)/1000, "$T", "SOMA Treasuries — the QE stockpile.",
                        color=_BLUE, fill=True,
                        info="The stock of US Treasury securities the Fed owns in its System Open Market "
                             "Account (SOMA) — the pile it accumulated through QE, shown in trillions. "
                             "Growing = active QE; flat or falling = QT, as maturing bonds roll off "
                             "without replacement. The core of the Fed's footprint in the government "
                             "bond market."),
            _chart_card("Bank reserves", _hist("fed.bank_reserves"), cur("fed.bank_reserves"),
                        "$B", "Liquidity backbone; QT drains this.", color=_BLUE, fill=True,
                        info="Cash that commercial banks hold on deposit at the Fed — the ultimate "
                             "liquidity in the banking system. QE creates reserves; QT destroys them. "
                             "When reserves fall too far, banks scramble for cash and money markets "
                             "seize up (as in September 2019), which can force the Fed to stop "
                             "tightening."),
            _chart_card("Overnight reverse repo (ON RRP)", _hist("fed.on_rrp"), cur("fed.on_rrp"),
                        "$B", "The cash buffer; near zero = QT now bites reserves.", color=_GREEN, fill=True,
                        info="The amount money-market funds park at the Fed overnight for a safe return "
                             "— essentially excess cash with nowhere better to go. It acts as a buffer: "
                             "during QT this drains first. Once it nears zero, further tightening starts "
                             "pulling down bank reserves directly, the point where liquidity stress can "
                             "begin."),
        ], columns=_COLUMNS)

    # 4) turning points
    resv = _to_bn("fed.bank_reserves", "b")
    gdp = _hist("master.gdp_level_bn")
    resv_gdp = _ratio(resv, gdp)
    s4 = _section(
        "⑤ Turning points — regime shift / forced pivot",
        "Signals that flag the Fed being forced to change course.",
        [
            _chart_card("2y/10y inversion", _hist("premium.yield_curve_10y2y"),
                        cur("premium.yield_curve_10y2y"), "%", "Sustained inversion precedes a pivot.",
                        zero_line=True, color=_GREEN,
                        info="The same 10y−2y curve, watched here as a turning-point trigger. A "
                             "sustained inversion is the bond market betting the Fed will be forced to "
                             "cut. The subsequent un-inversion (the curve steepening back above zero) "
                             "often coincides with the recession actually arriving and the pivot to "
                             "easing."),
            _chart_card("Real rate crossing zero", _hist("policy.real_fed_funds"),
                        cur("policy.real_fed_funds"), "%", "Neg→pos marks easing→tightening turn.",
                        zero_line=True, color=_AMBER,
                        info="The real policy rate again, watched here for the moment it crosses zero. "
                             "Moving from negative to positive marks the shift from stimulative to "
                             "restrictive policy; crossing back below zero marks a pivot to easing. "
                             "These crossings are regime boundaries for the whole cycle."),
            _chart_card("Reserves ÷ GDP", resv_gdp,
                        (float(resv_gdp['value'].iloc[-1]) if not resv_gdp.empty else None),
                        "%", "Near ~7% = reserve scarcity → money-market stress.",
                        hline=7.0, hline_txt="~7% scarcity", color=_BLUE,
                        info="Bank reserves as a percent of GDP — a way to judge whether reserves are "
                             "still abundant or getting scarce as the economy grows (reserves ÷ nominal "
                             "GDP). History suggests stress emerges somewhere around 7% of GDP. "
                             "Approaching that zone means QT is near its limit and money-market strains "
                             "become likely."),
            _chart_card("10y term premium (ACM)", _hist("fed.term_premium_10y"),
                        cur("fed.term_premium_10y"), "%",
                        "Extra yield to hold duration; a spike flags fiscal-dominance worry.",
                        zero_line=True, color=_AMBER,
                        info="The extra yield investors demand to hold a 10-year bond instead of rolling "
                             "short-term bills — estimated by the NY Fed's ACM model, since it can't be "
                             "observed directly. Usually low or negative; a sustained spike suggests the "
                             "market is worried about future supply, inflation, or fiscal dominance — "
                             "that too many bonds are being issued to absorb comfortably."),
            _chart_card("High-yield spread", _hist("premium.high_yield_spread"),
                        cur("premium.high_yield_spread"), "%", "Compression amid rising rates masks risk.",
                        color=_RED,
                        info="The yield gap between junk (high-yield) corporate bonds and Treasuries — "
                             "the market's price for the riskiest corporate credit. Unusually tight "
                             "spreads while the Fed is hiking signal investor complacency about risk; a "
                             "sudden blowout signals credit stress and is often the trigger that forces "
                             "the Fed to ease."),
        ], columns=_COLUMNS)

    # 5) monetization (the How Countries Go Broke panel)
    th = _to_bn("fed.treasury_holdings", "m")
    md = _to_bn("fed.marketable_debt", "b")
    fed_share = _ratio(th, md)
    fh = _to_bn("fed.foreign_holdings", "b")
    foreign_share = _ratio(fh, md)
    s5 = _section(
        "⑥ Late-cycle monetization — MP1 → MP2 → MP3  (How Countries Go Broke)",
        "Is the Fed being forced to fund the government and debase the currency?",
        [
            _chart_card("Fed share of marketable debt", fed_share,
                        (float(fed_share['value'].iloc[-1]) if not fed_share.empty else None),
                        "%", "Rising >20–25% during heavy issuance = monetization.",
                        hline=20.0, hline_txt="20% watch", color=_RED,
                        info="The Fed's Treasury holdings as a percent of all marketable US government "
                             "debt — how much of the nation's debt the central bank itself owns "
                             "(Fed SOMA Treasuries ÷ total marketable debt). Rising above ~20–25%, "
                             "especially while the government is issuing heavily, is the fingerprint of "
                             "monetization: the Fed absorbing debt the market won't."),
            _chart_card("Fed remittances / deferred asset", _to_bn("fed.remittances", "m"),
                        (cur("fed.remittances") or 0) / 1000.0, "$B",
                        "Negative = Fed running losses (solvency stress).",
                        zero_line=True, color=_RED,
                        info="Each year the Fed normally remits its profits to the Treasury. When its "
                             "interest costs exceed its income — as when it pays high rates on bank "
                             "reserves while holding low-yield bonds bought during QE — remittances go "
                             "negative and it books a 'deferred asset.' Negative = the Fed is running "
                             "losses, a sign the balance-sheet strategy is under solvency stress."),
            _chart_card("Foreign share of debt", foreign_share,
                        (float(foreign_share['value'].iloc[-1]) if not foreign_share.empty else None),
                        "%", "Falling = domestic/Fed must absorb more.", color=_AMBER,
                        info="The share of US marketable debt held by foreign investors — central banks "
                             "and overseas funds (foreign holdings ÷ total marketable debt). A falling "
                             "share means foreigners are stepping back and domestic buyers — ultimately "
                             "including the Fed — must absorb more issuance. A slow-moving gauge of who "
                             "is financing the deficit (Treasury Bulletin lags ~2 quarters — the custody "
                             "card is the live pulse)."),
            _chart_card("Foreign official custody (weekly)", _to_bn("fed.custody_holdings", "m"),
                        (cur("fed.custody_holdings") or 0) / 1000.0, "$B",
                        "Live weekly pulse of foreign official demand.", color=_AMBER,
                        info="Marketable Treasuries the Fed holds in custody for foreign central banks "
                             "and official institutions (H.4.1, weekly). It covers only official "
                             "accounts — a subset of total foreign holdings — but it updates weekly, "
                             "so a sustained decline flags buyers stepping away many months before the "
                             "quarterly Treasury Bulletin confirms it."),
            _chart_card("Federal interest ÷ revenue", _fed_interest_to_revenue(),
                        (float(_fed_interest_to_revenue()['value'].iloc[-1])
                         if not _fed_interest_to_revenue().empty else None),
                        "%", "Ray's debt-trap gauge; >15–20% = danger zone.",
                        hline=15.0, hline_txt="15% danger", color=_RED,
                        info="Annual federal interest payments as a percent of federal revenue — the "
                             "government's own debt-service ratio (interest outlays ÷ receipts). As it "
                             "climbs past ~15–20%, interest crowds out everything else and the debt "
                             "starts to compound faster than the government can tax it away — Ray's "
                             "classic debt-trap warning."),
            _chart_card("Fed % of net new issuance", _fed_net_issuance_share(),
                        (float(_fed_net_issuance_share()['value'].iloc[-1])
                         if not _fed_net_issuance_share().empty else None),
                        "%", "Fed absorbing net new debt (1yr); >30–40% = monetization.",
                        hline=30.0, hline_txt="30% red", zero_line=True, color=_RED,
                        info="Over the trailing year, the change in the Fed's Treasury holdings as a "
                             "percent of the change in total marketable debt — i.e. of every net new "
                             "dollar the Treasury borrowed, how much the Fed itself bought. Above "
                             "~30–40% means the central bank is directly financing the deficit rather "
                             "than the market absorbing it: the practical definition of monetization."),
        ], columns=_COLUMNS)

    note = html.Div(
        "Framework from a Digital Ray consult (2026-07-10) — an AI approximation of Ray Dalio's "
        "Economic-Machine / How-Countries-Go-Broke work, not vetted by Ray Dalio. FRED series IDs "
        "independently verified. Term premium (NY Fed ACM) and Fed-% -of-new-issuance are candidate "
        "additions.",
        style={"fontSize": "0.68rem", "color": "var(--muted-color)", "marginTop": "24px",
               "opacity": "0.75"})

    # 7) central-bank balance sheet — the one country-reactive section, filled
    #    by render_fed_central_bank_section() below.
    s6 = html.Div(id="fed-cb-section")

    return html.Div([_header(), s0, s1, s2, s3, s4, s5, s6, note],
                    className="p-3", style={"maxWidth": "1500px"})


def _pct(v):
    """Composite/derived signals are stored as decimals; show as %."""
    return None if v is None else v * 100.0


# ── ⑦ Central bank balance sheet — folded in from central_bank_monitor.py ────
# Verbatim in substance from that page (coverage-audit High item #5,
# 2026-10-03); see this module's docstring for why it is the only
# country-reactive section here. Its reasoning, which the merge must not
# lose:
#
#   * Concept ids are deliberately NOT unified across countries. EZ already
#     had `policy.central_bank_assets` bound (ECBASSETSW, already feeding
#     EZ's rate_score composite at CONTEXT weight) from an earlier phase —
#     reused as-is rather than creating a near-duplicate binding, which the
#     first version of that page did by mistake before it was caught. JP had
#     no prior binding, so `policy.central_bank_balance_sheet` is new.
#
#   * GB is NOT covered. Checked live 2026-10-03: every Bank-of-England
#     balance-sheet series on FRED is discontinued or years stale (the most
#     recent is annual, last real observation 2016). A genuine data gap, not
#     an oversight — shown as an explicit message rather than silently
#     omitted from the country list.
#
#   * The MP read here is deliberately simpler than _header()'s US-specific
#     one above, which leans on foreign-holder share and Fed remittances —
#     neither has a cross-country equivalent. The same YoY-growth-only rule
#     is applied uniformly to all three so they are genuinely comparable.
#
# For the US this section's YoY card overlaps section ④'s "Fed balance sheet
# (YoY)" (that one is the bound `policy.fed_balance_sheet` YoY signal; this
# one is computed from the `fed.balance_sheet` level). Kept rather than
# special-cased away: dropping it for the US alone would make the section
# stop being the like-for-like three-country comparison that is its reason
# to exist.

# country -> (balance-sheet concept id, divisor to display-unit trillions,
#             currency symbol, central bank name)
_CB_COVERAGE: dict[str, tuple[str, float, str, str]] = {
    "US": ("fed.balance_sheet", 1e6, "$", "Federal Reserve"),
    "EZ": ("policy.central_bank_assets", 1e6, "€", "European Central Bank"),
    "JP": ("policy.central_bank_balance_sheet", 1e4, "¥", "Bank of Japan"),
}
# Full 14-country map, not just the three covered ones: the "no live source
# for X yet" message is shown for every OTHER country, and the version
# inherited from central_bank_monitor.py only knew US/EZ/JP — so picking the
# UK printed "No live central-bank balance-sheet source for GB yet".
_CB_NAMES = {"US": "United States", "EZ": "Euro Area", "GB": "United Kingdom",
             "JP": "Japan", "KR": "South Korea", "CN": "China",
             "IN": "India", "DE": "Germany", "LU": "Luxembourg",
             "BR": "Brazil", "CA": "Canada", "AU": "Australia",
             "MX": "Mexico", "ID": "Indonesia"}

# Room-to-ease gauge: distance of the policy rate from the zero/effective
# lower bound — "how much conventional ammunition is left before this bank is
# forced into QE (MP2)." US/EZ only: no free BOJ policy-rate series exists on
# FRED (checked live) — JP has only the 10y JGB yield bound, not a short-rate
# equivalent, consistent with its other gap here.
_CB_RATE_COVERAGE: dict[str, str] = {
    "US": "policy.fed_funds_target",
    "EZ": "policy.fed_funds_target",
}
_CB_ELB = 0.0   # effective lower bound — a plain round-number floor, not a
                # model of each bank's own historical negative-rate episodes


def _cb_hist(cc: str, concept: str, start: str | None = _START) -> pd.DataFrame:
    return load_signal_history(f"{cc.lower()}.{concept}", start_date=start)


def _cb_latest(cc: str, concept: str):
    df = load_signal_history(f"{cc.lower()}.{concept}")
    if df.empty:
        return None, None
    return float(df["value"].iloc[-1]), pd.to_datetime(df["as_of"].iloc[-1])


def _cb_to_trillions(df: pd.DataFrame, divisor: float) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["value"] = df["value"] / divisor
    return df


def _cb_yoy_pct(df: pd.DataFrame) -> pd.DataFrame:
    """YoY % growth, resampled to monthly first so a weekly (EZ/US) and a
    monthly (JP) native series both produce a literal 'vs ~12 months ago'
    comparison rather than mismatched period counts."""
    if df.empty:
        return df
    s = df.set_index("as_of")["value"].sort_index().resample("ME").last()
    yoy = (s / s.shift(12) - 1.0) * 100.0
    out = yoy.dropna().reset_index()
    out.columns = ["as_of", "value"]
    return out


def _cb_mp_read(yoy_latest: float | None) -> tuple[str, str]:
    if yoy_latest is None:
        return "—", _GREY
    if yoy_latest > 5.0:
        return "MP2 (balance sheet expanding — QE underway)", _AMBER
    if yoy_latest < -5.0:
        return "MP1 / QT (balance sheet contracting)", _BLUE
    return "MP1 (roughly stable)", _GREEN


def _central_bank_section(cc: str) -> html.Div:
    """Section ⑦ for one country — cards + the chips that read them."""
    heading = "⑦ Central bank balance sheet — MP1 → MP2 → MP3, cross-country"

    if cc not in _CB_COVERAGE:
        gap = (
            "Checked live 2026-10-03: every Bank of England series on FRED is either "
            "discontinued or years stale (most recent is annual, last real observation "
            "2016) — a genuine gap, not an oversight. US/EZ/JP are covered."
            if cc == "GB" else
            f"{_CB_NAMES.get(cc, cc)} isn't one of the three covered central banks "
            "(US/EZ/JP) yet."
        )
        return _section(heading, "The one section on this page that follows the country selector.", [
            html.Div([
                html.Div(f"No live central-bank balance-sheet source for {_CB_NAMES.get(cc, cc)} yet.",
                         style={"color": "var(--muted-color)", "fontSize": "0.85rem",
                                "paddingBottom": "6px"}),
                html.Div(gap, style={"color": "var(--muted-color)", "fontSize": "0.78rem",
                                     "opacity": "0.85"}),
            ], style={"background": "var(--card-bg)", "border": "1px solid var(--border-color)",
                      "borderRadius": "8px", "padding": "16px 18px"}),
        ])

    concept, divisor, sym, bank_name = _CB_COVERAGE[cc]
    raw = _cb_hist(cc, concept)
    level = _cb_to_trillions(raw, divisor)
    yoy = _cb_yoy_pct(raw)
    cur_level, _ = _cb_latest(cc, concept)
    cur_yoy = float(yoy["value"].iloc[-1]) if not yoy.empty else None
    mp_label, mp_color = _cb_mp_read(cur_yoy)

    chips = [
        _chip(f"{bank_name} · {_CB_NAMES.get(cc, cc)}", _GREY),
        _chip(f"Balance sheet {sym}{(cur_level or 0) / divisor:.2f}T"
              if cur_level is not None else "level —", _BLUE),
        _chip(f"YoY {cur_yoy:+.1f}%" if cur_yoy is not None else "YoY —",
              _RED if (cur_yoy or 0) > 5 else _GREEN if (cur_yoy or 0) < -5 else _AMBER),
        _chip(mp_label, mp_color),
    ]
    rate_concept = _CB_RATE_COVERAGE.get(cc)
    if rate_concept:
        cur_rate, _ = _cb_latest(cc, rate_concept)
        if cur_rate is not None:
            room = cur_rate - _CB_ELB
            chips.append(_chip(
                f"Room to ease {room:+.2f}pp",
                _RED if room < 1.0 else _AMBER if room < 2.5 else _GREEN))

    cards = [
        _chart_card(
            f"Balance sheet level ({sym}T)", level,
            cur_level / divisor if cur_level is not None else None, "", "",
            color=_BLUE, fill=True,
            fmt_override=(f"{sym}{cur_level / divisor:.2f}T" if cur_level is not None else None),
            info="Total balance-sheet assets — the size of the QE stockpile. Raw level, not yet "
                 "GDP-normalized (the three countries' GDP signals are all USD-converted via "
                 "different providers, which would need an FX leg to pair cleanly against a "
                 "locally-denominated balance sheet — skipped rather than risking a "
                 "unit-mismatched ratio).",
        ),
        _chart_card(
            "Balance sheet YoY growth", yoy, cur_yoy, "pp",
            "> +5% = MP2 (QE underway); < −5% = unwinding.",
            color=_AMBER, zero_line=True,
            # `_fmt` has no "pp" case, so it would print a bare "2.04".
            fmt_override=(f"{cur_yoy:+.1f}%" if cur_yoy is not None else None),
            info="Year-over-year % change — unlike the raw level, this needs no currency "
                 "conversion at all, so it's the directly comparable read across the three "
                 "countries. >+5% = MP2 (QE underway); <-5% = unwinding; in between = "
                 "roughly stable.",
        ),
    ]

    # Chips lead the section, matching the page header's own chips-then-charts
    # order — underneath the cards they read as an orphaned footnote.
    return _section(
        heading,
        "The one section on this page that follows the country selector "
        "(US / Euro Area / Japan — the central banks with a live free source).",
        cards, columns=_COLUMNS,
        lead=html.Div(chips, style={"display": "flex", "gap": "10px",
                                    "flexWrap": "wrap", "marginBottom": "12px"}),
    )


@callback(
    Output("fed-cb-section", "children"),
    [Input("page-trigger", "data"),
     Input("country-store", "data")],
    prevent_initial_call=False,
)
def render_fed_central_bank_section(page_trigger, country):
    page = (page_trigger or {}).get("page", "")
    if page and page != "/fed":
        return no_update
    return _central_bank_section((country or "US").upper())

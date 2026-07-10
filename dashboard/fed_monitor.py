"""Fed Monitor — a US Federal Reserve dashboard (Digital Ray consult 2026-07-10).

Five sections, in Ray's Economic-Machine framing:
  1. Short-term cycle       — where the Fed is in / headed for the business cycle
  2. Rates vs inflation      — is money easy/tight, is the Fed behind/ahead
  3. Balance sheet & liquidity — QE/QT, reserves, ON RRP
  4. Turning points          — inversion, real-rate zero cross, reserve scarcity
  5. Late-cycle monetization — MP1->MP2->MP3 (the "How Countries Go Broke" panel)

Each chart is a time series with the current value and, where relevant, the
threshold Ray named. Curated from signals we already ingest plus seven new
`fed.*` monitoring series. Read-only against the signals DB.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from dashboard.charting_data import DB_PATH, load_signal_history
from dashboard.themes import DEFAULT_THEME, figure_layout

_CC = "us"
_START = "2006-01-01"          # a useful window that spans the GFC, COVID, QT

# colours
_BLUE, _AMBER, _RED, _GREEN, _GREY = "#4C9BE8", "#E8A317", "#d9534f", "#2e9e5b", "#8a97a8"


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
    n = num.rename(columns={"value": "n"}).sort_values("as_of")
    d = den.rename(columns={"value": "d"}).sort_values("as_of")
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


# ── chart card ───────────────────────────────────────────────────────────────

def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "—"
    if unit == "%":
        return f"{v:.2f}%"
    if unit == "$T":
        return f"${v/1000:.2f}T"
    if unit == "$B":
        return f"${v:,.0f}B"
    if unit == "idx":
        return f"{v:,.0f}"
    return f"{v:.2f}"


def _chart_card(title: str, df: pd.DataFrame, cur: float | None, unit: str, read: str,
                *, hline: float | None = None, hline_txt: str = "", zero_line: bool = False,
                color: str = _BLUE, fill: bool = False) -> html.Div:
    fig = go.Figure()
    if df is not None and not df.empty:
        fig.add_trace(go.Scatter(
            x=df["as_of"], y=df["value"], mode="lines",
            line=dict(color=color, width=1.7),
            fill="tozeroy" if fill else None,
            fillcolor=f"rgba(76,155,232,0.12)" if fill else None,
            hovertemplate="%{x|%b %Y}: %{y:.2f}<extra></extra>"))
    if zero_line:
        fig.add_hline(y=0, line=dict(color=_GREY, width=1))
    if hline is not None:
        fig.add_hline(y=hline, line=dict(color=_AMBER, dash="dash", width=1),
                      annotation_text=hline_txt, annotation_position="top left",
                      annotation_font=dict(size=9, color=_AMBER))
    lay = figure_layout(DEFAULT_THEME)
    lay.update(height=180, margin=dict(l=6, r=8, t=6, b=18), showlegend=False,
               xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"))
    fig.update_layout(**lay)
    return html.Div([
        html.Div([
            html.Span(title, style={"fontSize": "0.78rem", "fontWeight": "700",
                                    "color": "var(--font-color)"}),
            html.Span(_fmt(cur, unit), style={"fontSize": "0.95rem", "fontWeight": "700",
                                              "fontFamily": "monospace", "color": color,
                                              "float": "right"}),
        ]),
        html.Div(read, style={"fontSize": "0.66rem", "color": "var(--muted-color)",
                              "marginBottom": "2px", "minHeight": "1.6em"}),
        dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "180px"}),
    ], style={"background": "var(--card-bg)", "border": "1px solid var(--border-color)",
              "borderRadius": "8px", "padding": "10px 12px", "flex": "1 1 300px",
              "minWidth": "280px"})


def _section(title: str, subtitle: str, cards: list) -> html.Div:
    return html.Div([
        html.Div(title, style={"fontSize": "0.72rem", "fontWeight": "800",
                               "textTransform": "uppercase", "letterSpacing": "0.06em",
                               "color": "var(--muted-color)", "marginTop": "22px"}),
        html.Div(subtitle, style={"fontSize": "0.72rem", "color": "var(--muted-color)",
                                  "opacity": "0.8", "marginBottom": "10px"}),
        html.Div(cards, style={"display": "flex", "flexWrap": "wrap", "gap": "12px"}),
    ])


# ── header read ──────────────────────────────────────────────────────────────

def _chip(text: str, color: str) -> html.Span:
    return html.Span(text, style={"background": f"{color}22", "border": f"1px solid {color}",
                                  "color": color, "borderRadius": "5px", "padding": "3px 10px",
                                  "fontSize": "0.76rem", "fontWeight": "700",
                                  "whiteSpace": "nowrap"})


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

    # 1) short-term cycle
    s1 = _section(
        "① Short-term cycle — where the Fed is headed",
        "The policy stance and the levers that steer the 5–8yr business cycle.",
        [
            _chart_card("Effective Fed Funds", _hist("policy.fed_funds"), cur("policy.fed_funds"),
                        "%", "The core policy lever.", color=_BLUE),
            _chart_card("Real policy rate", _hist("policy.real_fed_funds"), cur("policy.real_fed_funds"),
                        "%", "Funds − core inflation. >0 tight, <0 easy.", zero_line=True, color=_AMBER),
            _chart_card("Rate expectations (2y − funds)", _hist("policy.rate_expectations"),
                        cur("policy.rate_expectations"), "%", "Market-implied path: + = hikes priced, − = cuts.",
                        zero_line=True, color=_BLUE),
            _chart_card("Yield curve (10y − 2y)", _hist("premium.yield_curve_10y2y"),
                        cur("premium.yield_curve_10y2y"), "%", "Inversion (<0) historically leads recession.",
                        zero_line=True, color=_GREEN),
            _chart_card("Bank lending standards (SLOOS)", _hist("credit.lending_standards"),
                        cur("credit.lending_standards"), "%", "Net % tightening C&I standards; high = credit squeeze.",
                        color=_RED),
            _chart_card("Corporate credit spread", _hist("premium.credit_spread_corp"),
                        cur("premium.credit_spread_corp"), "%", "Widening = tighter financial conditions.", color=_RED),
        ])

    # 2) rates vs inflation
    s2 = _section(
        "② Rates vs inflation — easy or tight, behind or ahead",
        "Frame policy against inflation and expectations.",
        [
            _chart_card("Real policy rate", _hist("policy.real_fed_funds"), cur("policy.real_fed_funds"),
                        "%", "The single best easy/tight gauge.", zero_line=True, color=_AMBER),
            _chart_card("5y5y forward inflation", _hist("fed.fwd_inflation_5y5y"),
                        cur("fed.fwd_inflation_5y5y"), "%", "Long-run market anchor; > target = Fed behind.",
                        hline=2.0, hline_txt="2% target", color=_BLUE),
            _chart_card("Core PCE (YoY)", _hist_pct("inflation.pce_core"),
                        _pct(cur("inflation.pce_core")), "%", "The Fed's preferred inflation gauge.",
                        hline=2.0, hline_txt="2% target", color=_RED),
            _chart_card("Avg breakeven inflation", _hist("inflation.breakeven_avg"),
                        cur("inflation.breakeven_avg"), "%", "Market-implied CPI (5y/10y TIPS).", color=_BLUE),
        ])

    # 3) balance sheet & liquidity
    s3 = _section(
        "③ Balance sheet & liquidity — QE / QT",
        "The scale of the Fed's footprint and the liquidity in the system.",
        [
            _chart_card("Fed balance sheet (YoY)", _hist_pct("policy.fed_balance_sheet"),
                        _pct(cur("policy.fed_balance_sheet")), "%", "+ = QE (easing), − = QT (tightening).",
                        zero_line=True, color=_AMBER),
            _chart_card("Fed Treasury holdings", _to_bn("fed.treasury_holdings", "m"),
                        (cur("fed.treasury_holdings") or 0)/1000, "$T", "SOMA Treasuries — the QE stockpile.",
                        color=_BLUE, fill=True),
            _chart_card("Bank reserves", _hist("fed.bank_reserves"), cur("fed.bank_reserves"),
                        "$B", "Liquidity backbone; QT drains this.", color=_BLUE, fill=True),
            _chart_card("Overnight reverse repo (ON RRP)", _hist("fed.on_rrp"), cur("fed.on_rrp"),
                        "$B", "The cash buffer; near zero = QT now bites reserves.", color=_GREEN, fill=True),
        ])

    # 4) turning points
    resv = _to_bn("fed.bank_reserves", "b")
    gdp = _hist("master.gdp_level_bn")
    resv_gdp = _ratio(resv, gdp)
    s4 = _section(
        "④ Turning points — regime shift / forced pivot",
        "Signals that flag the Fed being forced to change course.",
        [
            _chart_card("2y/10y inversion", _hist("premium.yield_curve_10y2y"),
                        cur("premium.yield_curve_10y2y"), "%", "Sustained inversion precedes a pivot.",
                        zero_line=True, color=_GREEN),
            _chart_card("Real rate crossing zero", _hist("policy.real_fed_funds"),
                        cur("policy.real_fed_funds"), "%", "Neg→pos marks easing→tightening turn.",
                        zero_line=True, color=_AMBER),
            _chart_card("Reserves ÷ GDP", resv_gdp,
                        (float(resv_gdp['value'].iloc[-1]) if not resv_gdp.empty else None),
                        "%", "Near ~7% = reserve scarcity → money-market stress.",
                        hline=7.0, hline_txt="~7% scarcity", color=_BLUE),
            _chart_card("10y term premium (ACM)", _hist("fed.term_premium_10y"),
                        cur("fed.term_premium_10y"), "%",
                        "Extra yield to hold duration; a spike flags fiscal-dominance worry.",
                        zero_line=True, color=_AMBER),
            _chart_card("High-yield spread", _hist("premium.high_yield_spread"),
                        cur("premium.high_yield_spread"), "%", "Compression amid rising rates masks risk.",
                        color=_RED),
        ])

    # 5) monetization (the How Countries Go Broke panel)
    th = _to_bn("fed.treasury_holdings", "m")
    md = _to_bn("fed.marketable_debt", "b")
    fed_share = _ratio(th, md)
    fh = _to_bn("fed.foreign_holdings", "b")
    foreign_share = _ratio(fh, md)
    s5 = _section(
        "⑤ Late-cycle monetization — MP1 → MP2 → MP3  (How Countries Go Broke)",
        "Is the Fed being forced to fund the government and debase the currency?",
        [
            _chart_card("Fed share of marketable debt", fed_share,
                        (float(fed_share['value'].iloc[-1]) if not fed_share.empty else None),
                        "%", "Rising >20–25% during heavy issuance = monetization.",
                        hline=20.0, hline_txt="20% watch", color=_RED),
            _chart_card("Fed remittances / deferred asset", _to_bn("fed.remittances", "m"),
                        (cur("fed.remittances") or 0) / 1000.0, "$B",
                        "Negative = Fed running losses (solvency stress).",
                        zero_line=True, color=_RED),
            _chart_card("Foreign share of debt", foreign_share,
                        (float(foreign_share['value'].iloc[-1]) if not foreign_share.empty else None),
                        "%", "Falling = domestic/Fed must absorb more.", color=_AMBER),
            _chart_card("Federal interest ÷ revenue", _fed_interest_to_revenue(),
                        (float(_fed_interest_to_revenue()['value'].iloc[-1])
                         if not _fed_interest_to_revenue().empty else None),
                        "%", "Ray's debt-trap gauge; >15–20% = danger zone.",
                        hline=15.0, hline_txt="15% danger", color=_RED),
            _chart_card("Fed % of net new issuance", _fed_net_issuance_share(),
                        (float(_fed_net_issuance_share()['value'].iloc[-1])
                         if not _fed_net_issuance_share().empty else None),
                        "%", "Fed absorbing net new debt (1yr); >30–40% = monetization.",
                        hline=30.0, hline_txt="30% red", zero_line=True, color=_RED),
        ])

    note = html.Div(
        "Framework from a Digital Ray consult (2026-07-10) — an AI approximation of Ray Dalio's "
        "Economic-Machine / How-Countries-Go-Broke work, not vetted by Ray Dalio. FRED series IDs "
        "independently verified. Term premium (NY Fed ACM) and Fed-% -of-new-issuance are candidate "
        "additions.",
        style={"fontSize": "0.68rem", "color": "var(--muted-color)", "marginTop": "24px",
               "opacity": "0.75"})

    return html.Div([_header(), s1, s2, s3, s4, s5, note],
                    className="p-3", style={"maxWidth": "1500px"})


def _pct(v):
    """Composite/derived signals are stored as decimals; show as %."""
    return None if v is None else v * 100.0

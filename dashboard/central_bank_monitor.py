"""Central Bank Monitor — the MP1->MP2->MP3 "late-cycle monetization" read,
generalized across the central banks with a live, verified free data source
(coverage-audit High item #5, 2026-10-03).

Fed Monitor's own version of this read (its section 5) is US-only by
architecture (`_CC = "us"` is a module-level constant there, not threaded
from the country selector) and leans on signals with no cross-country
equivalent (foreign-holder share of marketable debt, Fed remittances/losses).
Rather than retrofitting that page, this is a separate, deliberately simpler
page: one directly cross-country-comparable read — the central bank's own
balance sheet, level and YoY growth — reused from the SAME verified-live
sources as everything else in this codebase.

Coverage: US (FRED WALCL, already bound as policy.fed_balance_sheet), EZ
(FRED ECBASSETSW), JP (FRED JPNASSETS). GB is NOT covered — every
Bank-of-England balance-sheet series on FRED is discontinued or years stale
(checked live 2026-10-03: the most recent is annual, last real observation
2016). That is a genuine data gap, not an oversight; it stays undocumented
nowhere else, so it is documented here and shown as a plain "no live source"
message rather than silently omitted from the country list.

Visual pattern reused verbatim from dashboard.fed_monitor (same `_chart_card`/
`_section`/`_chip`/`_info_icon` helpers case_study_monitor.py and
market_expectations.py already import), so this reads as a sibling page.
Unlike those two (US-only, static layout), this page is country-reactive —
one callback rebuilds its content on country-store changes, same pattern as
relative_view.py.

Feeds no composite; isolated force, same convention as fed.*/market.*/order.*.

Room-to-ease chip (coverage-audit follow-up, 2026-10-03): distance of the
policy rate from the zero/effective lower bound, US/EZ only — no free BOJ
policy-rate series exists on FRED either (checked live), consistent with
JP's other gap on this page.
"""
from __future__ import annotations

import pandas as pd
from dash import Input, Output, callback, html, no_update

from dashboard.charting_data import load_signal_history
from dashboard.fed_monitor import _chart_card, _chip, _section
from dashboard.shared_components import AMBER as _AMBER
from dashboard.shared_components import BLUE as _BLUE
from dashboard.shared_components import GREEN as _GREEN
from dashboard.shared_components import GREY as _GREY
from dashboard.shared_components import RED as _RED

_START = "2006-01-01"

# country -> (balance-sheet concept id, divisor to display-unit trillions, currency symbol, central bank name)
# Concept ids are intentionally not unified across countries: EZ already had
# `policy.central_bank_assets` bound (same ECBASSETSW series, already feeding
# EZ's rate_score composite at CONTEXT weight) from an earlier phase of the
# project — reused as-is rather than creating a near-duplicate binding, which
# the first version of this page did by mistake before this was caught.
# JP had no prior binding, so `policy.central_bank_balance_sheet` is new.
_COVERAGE: dict[str, tuple[str, float, str, str]] = {
    "US": ("fed.balance_sheet", 1e6, "$", "Federal Reserve"),
    "EZ": ("policy.central_bank_assets", 1e6, "€", "European Central Bank"),
    "JP": ("policy.central_bank_balance_sheet", 1e4, "¥", "Bank of Japan"),
}
_NAMES = {"US": "United States", "EZ": "Euro Area", "JP": "Japan"}

# Room-to-ease gauge (coverage-audit follow-up, 2026-10-03): distance of the
# policy rate from the zero/effective lower bound — "how much conventional
# ammunition is left before this bank is forced into QE (MP2)." US/EZ only:
# no free BOJ policy-rate series exists on FRED (checked live) — JP has
# only the 10y JGB yield bound, not a short-rate equivalent, consistent
# with its other gap on this page (no balance-sheet source for GB either).
_RATE_COVERAGE: dict[str, str] = {
    "US": "policy.fed_funds_target",
    "EZ": "policy.fed_funds_target",
}
_ELB = 0.0   # effective lower bound, a plain round-number floor -- not modeling
             # each bank's own historical negative-rate episodes


def _hist(cc: str, concept: str, start: str | None = _START) -> pd.DataFrame:
    return load_signal_history(f"{cc.lower()}.{concept}", start_date=start)


def _latest(cc: str, concept: str):
    df = load_signal_history(f"{cc.lower()}.{concept}")
    if df.empty:
        return None, None
    return float(df["value"].iloc[-1]), pd.to_datetime(df["as_of"].iloc[-1])


def _to_trillions(df: pd.DataFrame, divisor: float) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["value"] = df["value"] / divisor
    return df


def _yoy_pct(df: pd.DataFrame) -> pd.DataFrame:
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


def _mp_read(yoy_latest: float | None) -> tuple[str, str]:
    """Deliberately simpler than Fed Monitor's own US-specific heuristic (which
    uses foreign-holder share + remittance losses, neither available outside
    the US) — the same YoY-growth-only read is applied uniformly to every
    country here so the three are genuinely comparable."""
    if yoy_latest is None:
        return "—", _GREY
    if yoy_latest > 5.0:
        return "MP2 (balance sheet expanding — QE underway)", _AMBER
    if yoy_latest < -5.0:
        return "MP1 / QT (balance sheet contracting)", _BLUE
    return "MP1 (roughly stable)", _GREEN


def _country_block(cc: str) -> html.Div:
    if cc not in _COVERAGE:
        return html.Div([
            html.Div(f"No live central-bank balance-sheet source for {_NAMES.get(cc, cc)} yet.",
                     style={"color": "var(--muted-color)", "fontSize": "0.85rem", "padding": "20px 0"}),
            html.Div(
                "Checked live 2026-10-03: every Bank of England series on FRED is either "
                "discontinued or years stale (most recent is annual, last real observation "
                "2016) — a genuine gap, not an oversight. US/EZ/JP are covered."
                if cc == "GB" else
                f"{_NAMES.get(cc, cc)} isn't one of the three covered central banks (US/EZ/JP) yet.",
                style={"color": "var(--muted-color)", "fontSize": "0.78rem", "opacity": "0.85"},
            ),
        ])

    concept, divisor, sym, bank_name = _COVERAGE[cc]
    level = _to_trillions(_hist(cc, concept), divisor)
    yoy = _yoy_pct(_hist(cc, concept))
    cur_level, _ = _latest(cc, concept)
    cur_yoy = float(yoy["value"].iloc[-1]) if not yoy.empty else None
    mp_label, mp_color = _mp_read(cur_yoy)

    rate_concept = _RATE_COVERAGE.get(cc)
    room_chip = None
    if rate_concept:
        cur_rate, _ = _latest(cc, rate_concept)
        if cur_rate is not None:
            room = cur_rate - _ELB
            room_color = _RED if room < 1.0 else _AMBER if room < 2.5 else _GREEN
            room_chip = _chip(f"Room to ease {room:+.2f}pp", room_color)

    header = html.Div([
        html.Div([
            html.Span("🏦 ", style={"fontSize": "1.3rem"}),
            html.Span(bank_name, style={"fontSize": "1.15rem", "fontWeight": "700", "color": "var(--font-color)"}),
            html.Span(f" · {_NAMES.get(cc, cc)}", style={"fontSize": "0.8rem", "color": "var(--muted-color)"}),
        ]),
        html.Div([
            _chip(f"Balance sheet {sym}{(cur_level or 0) / divisor:.2f}T" if cur_level is not None else "level —", _BLUE),
            _chip(f"YoY {cur_yoy:+.1f}%" if cur_yoy is not None else "YoY —",
                  _RED if (cur_yoy or 0) > 5 else _GREEN if (cur_yoy or 0) < -5 else _AMBER),
            _chip(mp_label, mp_color),
            *([room_chip] if room_chip is not None else []),
        ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginTop": "8px"}),
    ], style={"borderBottom": "1px solid var(--border-color)", "paddingBottom": "12px", "marginBottom": "4px"})

    cards = [
        _chart_card(
            f"Balance sheet level ({sym}T)", level, cur_level / divisor if cur_level is not None else None, "", "",
            color=_BLUE, fill=True,
            info="Total balance-sheet assets — the size of the QE stockpile. Raw level, not yet GDP-normalized "
                 "(the three countries' GDP signals are all USD-converted via different providers, which would "
                 "need an FX leg to pair cleanly against a locally-denominated balance sheet — skipped rather "
                 "than risking a unit-mismatched ratio).",
        ),
        _chart_card(
            "YoY growth (%)", yoy, cur_yoy, "pp", "",
            color=_AMBER, zero_line=True,
            info="Year-over-year % change — unlike the raw level, this needs no currency conversion at all, "
                 "so it's the directly comparable read across the three countries. >+5% = MP2 (QE underway); "
                 "<-5% = unwinding; in between = roughly stable.",
        ),
    ]
    return html.Div([header, _section(
        "", "", cards,
    )])


def get_layout() -> html.Div:
    return html.Div([
        html.Div(id="cbm-content"),
    ], className="pe-2", style={"maxWidth": "1200px", "margin": "0 auto", "paddingTop": "12px"})


@callback(
    Output("cbm-content", "children"),
    [Input("page-trigger", "data"),
     Input("country-store", "data")],
    prevent_initial_call=False,
)
def render_central_bank_monitor(page_trigger, country):
    page = (page_trigger or {}).get("page", "")
    if page and page != "/central-bank":
        return no_update
    cc = (country or "US").upper()
    return [
        html.Div(
            "Central-bank balance sheet, size and trend — the MP1->MP2->MP3 read, "
            "generalized to the central banks with a live free source (US/EZ/JP). "
            "Same signal family and convention as Fed Monitor (fed.*/policy.*), "
            "deliberately simpler so the three are genuinely comparable.",
            style={"fontSize": "0.78rem", "color": "var(--muted-color)", "marginBottom": "14px"},
        ),
        _country_block(cc),
    ]

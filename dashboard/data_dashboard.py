"""Data Dashboard — operational feed health monitor.

One row per signal, grouped by force. Shows source series, latest value,
as-of date, update frequency, next expected release, and colour-coded
status badges.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import duckdb
import pandas as pd
import yaml
from dash import html

_DB = os.getenv("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb")
_CONFIG_DIR = Path(__file__).parent.parent / "config"

# ── Display mappings ─────────────────────────────────────────────────────────

_FORCE_ORDER = [
    "master", "growth", "inflation", "policy", "credit",
    "premium", "capital", "currency", "external", "fiscal", "demo", "climate",
]
_FORCE_LABELS: dict[str, str] = {
    "master":       "GDP / Master",
    "growth":       "Growth",
    "inflation":    "Inflation",
    "policy":       "Monetary Policy",
    "credit":       "Credit & Debt",
    "premium":      "Risk Premia",
    "capital":      "Capital Flows",
    "currency":     "Currency",
    "external":     "External Sector",
    "fiscal":       "Fiscal",
    "demo":         "Demographics",
    "demographics": "Demographics",
    "climate":      "Climate",
}

_SIGNAL_NAMES: dict[str, str] = {
    "master.gdp_nominal":          "GDP Nominal",
    "master.gdp_real":             "GDP Real",
    "master.gdp_level_bn":         "GDP Level",
    "master.gdp_deflator":         "GDP Deflator",
    "master.ngdp_minus_yield":     "NGDP − Yield Spread",
    "master.spending_vs_labor":    "Spending vs. Labor",
    "growth.unemployment":         "Unemployment Rate",
    "growth.payrolls":             "Non-Farm Payrolls",
    "growth.job_openings":         "Job Openings (JOLTS)",
    "growth.industrial_prod":      "Industrial Production",
    "growth.retail_sales":         "Retail Sales",
    "growth.real_pce":             "Real PCE",
    "growth.capacity_util":        "Capacity Utilization",
    "growth.productivity":         "Labor Productivity",
    "growth.labor_force_part":     "Labor Force Part. (FRED)",
    "growth.pmi_proxy":            "PMI Proxy (Philly Fed)",
    "growth.rnd_intensity":        "R&D Intensity",
    "growth.tfp":                  "Total Factor Productivity",
    "inflation.cpi_headline":      "CPI Headline",
    "inflation.cpi_core":          "CPI Core",
    "inflation.pce_core":          "Core PCE",
    "inflation.ppi_broad":         "PPI Broad",
    "inflation.wages":             "Wage Growth",
    "inflation.breakeven_5y":      "Breakeven Inflation 5Y",
    "inflation.breakeven_10y":     "Breakeven Inflation 10Y",
    "inflation.crude_oil":         "Crude Oil WTI (YoY)",
    "policy.fed_funds":            "Fed Funds (Effective)",
    "policy.fed_funds_target":     "Fed Funds Target",
    "policy.real_fed_funds":       "Real Fed Funds Rate",
    "policy.yield_2y":             "2Y Treasury Yield",
    "policy.yield_10y":            "10Y Treasury Yield",
    "policy.real_yield_10y":       "10Y Real Yield (TIPS)",
    "policy.fed_balance_sheet":    "Fed Balance Sheet",
    "policy.monetary_base_gdp":    "Monetary Base / GDP",
    "credit.gov_debt_gdp":         "Govt Debt / GDP",
    "credit.household_debt_gdp":   "Household Debt / GDP",
    "credit.corporate_debt":       "Corporate Debt",
    "credit.bank_loans":           "Bank Loans Growth",
    "credit.debt_service_ratio":   "Debt Service Ratio",
    "credit.lending_standards":    "Lending Standards (SLOOS)",
    "premium.yield_curve_10y2y":   "Yield Curve 10Y–2Y",
    "premium.yield_curve_10y3m":   "Yield Curve 10Y–3M",
    "premium.credit_spread_corp":  "Corp. Credit Spread (BAA)",
    "premium.high_yield_spread":   "High Yield Spread",
    "capital.fdi_net_inflows_gdp": "FDI Net Inflows / GDP",
    "currency.reer":               "REER (FRED / BIS)",
    "currency.reer_xcountry":      "REER (World Bank)",
    "external.exports_gdp":        "Exports / GDP",
    "external.imports_gdp":        "Imports / GDP",
    "external.current_account":    "Current Account ($)",
    "external.current_account_gdp":"Current Account / GDP",
    "external.niip":               "Net IIP ($)",
    "fiscal.federal_deficit":      "Federal Deficit ($)",
    "fiscal.budget_balance_gdp":   "Budget Balance / GDP",
    "fiscal.interest_payments":    "Interest Payments ($)",
    "fiscal.govt_revenue_gdp":     "Govt Revenue / GDP",
    "fiscal.primary_balance_gdp":  "Primary Balance / GDP",
    "fiscal.structural_balance":   "Structural Balance",
    "demo.population_growth":      "Population Growth",
    "demo.population_total_mn":    "Total Population",
    "demo.age_dependency":         "Age Dependency Ratio",
    "demo.urbanization":           "Urbanization Rate",
    "demo.labor_force_part_wb":    "Labor Force Part. (WB)",
    "climate.disaster_loss":       "Disaster Losses / GDP",
}

_FREQ_LABELS: dict[str, str] = {
    "D": "Daily",
    "W": "Weekly",
    "M": "Monthly",
    "Q": "Quarterly",
    "A": "Annual",
}

# Days to add to last as_of to estimate next release (observation period + lag)
_NEXT_DAYS: dict[str, int] = {
    "D": 2,
    "W": 10,    # next weekly obs + a few days
    "M": 45,    # next monthly obs + ~2 week release lag
    "Q": 120,   # next quarter + ~4 week release lag
    "A": 400,   # next annual obs + some months lag
}

# ── YAML metadata ────────────────────────────────────────────────────────────

def _load_binding_meta() -> dict[str, dict]:
    """Load frequency and provider from us_bindings.yaml keyed by full signal id."""
    path = _CONFIG_DIR / "us_bindings.yaml"
    with open(path) as f:
        cfg = yaml.safe_load(f)
    country = cfg.get("country", "US").lower()
    meta: dict[str, dict] = {}
    for b in cfg.get("bindings", []):
        full_id = f"{country}.{b['id']}"
        meta[full_id] = {
            "frequency": b.get("frequency", "?"),
            "source_tier": b.get("source_tier", "free"),
        }
    return meta


# ── DB query ─────────────────────────────────────────────────────────────────

def _load_signals() -> pd.DataFrame:
    """Latest snapshot for every US signal."""
    con = duckdb.connect(_DB, read_only=True)
    df = con.execute("""
        SELECT id, force, as_of, value, units, source, provider,
               is_stale, low_history, is_proxy, vintage_available, is_constructed
        FROM signals
        WHERE country = 'US'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
        ORDER BY force, id
    """).df()
    con.close()
    return df


# ── Formatting helpers ───────────────────────────────────────────────────────

def _fmt_val(value: float, units: str) -> str:
    u = (units or "").lower()
    if u in ("yoy_pct", "yoy_pct_spread"):
        return f"{value * 100:+.2f}%"
    # Signed % — budget balances, current account, spreads (can be meaningfully negative)
    if u in ("pct_gdp", "pct_pot_gdp", "net_pct"):
        return f"{value:+.2f}%"
    # Unsigned % levels — rates, utilisation, ratios (inherently positive)
    if u in ("pct_level", "pct_working_age", "pct_total_pop",
             "pct_pop_15plus", "pct_annual"):
        return f"{value:.2f}%"
    if u == "billions_usd":
        return f"${value:,.0f}B"
    if u == "millions_usd":
        return f"${value / 1_000:,.1f}B"
    if u == "thousands":
        return f"{value:,.0f}K"
    if u == "persons":
        return f"{value / 1e6:.1f}M"
    if u.startswith("index_"):
        return f"{value:.1f}"
    if u == "ratio":
        return f"{value:.3f}"
    if u == "diffusion_index":
        return f"{value:.1f}"
    return f"{value:.2f}"


def _fmt_series(source: str, provider: str) -> tuple[str, str]:
    """Return (series_label, provider_label) from the 'source' column."""
    if not source or source == "derived":
        return "Derived", "—"
    if ":" in source:
        prov, sid = source.split(":", 1)
        return sid, prov
    return source, provider or "—"


def _next_release(as_of: str, freq: str) -> str:
    days = _NEXT_DAYS.get(freq)
    if days is None:
        return "—"
    dt = pd.Timestamp(as_of) + timedelta(days=days)
    return dt.strftime("%Y-%m-%d") if freq == "D" else dt.strftime("%Y-%m")


def _days_ago(as_of: str) -> str:
    delta = (pd.Timestamp.today() - pd.Timestamp(as_of)).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "1d ago"
    if delta < 32:
        return f"{delta}d ago"
    months = round(delta / 30.5)
    return f"{months}mo ago"


# ── Status badges ────────────────────────────────────────────────────────────

def _badges(row: pd.Series, next_rel: str, freq: str) -> list[html.Span]:
    today = pd.Timestamp.today()
    badges: list[html.Span] = []

    if row["is_stale"]:
        badges.append(html.Span("STALE", className="dd-badge dd-badge-stale"))

    # Check if next release is overdue but pipeline hasn't flagged stale yet
    if not row["is_stale"] and next_rel not in ("—", "") and freq not in ("D",):
        try:
            rel_dt = pd.Timestamp(next_rel + "-01" if len(next_rel) == 7 else next_rel)
            overdue = (today - rel_dt).days
            if overdue > 15:
                badges.append(html.Span(f"+{overdue}d", className="dd-badge dd-badge-due"))
        except Exception:
            pass

    if row["low_history"]:
        badges.append(html.Span("LOW HIST", className="dd-badge dd-badge-info"))

    if row["is_proxy"]:
        badges.append(html.Span("PROXY", className="dd-badge dd-badge-muted"))

    if row["is_constructed"]:
        badges.append(html.Span("DERIVED", className="dd-badge dd-badge-muted"))

    if not row["vintage_available"] and not row["is_constructed"]:
        badges.append(html.Span("NO VINTAGE", className="dd-badge dd-badge-muted"))

    if not badges:
        badges.append(html.Span("✓ OK", className="dd-badge dd-badge-ok"))

    return badges


# ── Table components ─────────────────────────────────────────────────────────

def _group_header(force: str, count: int) -> html.Tr:
    label = _FORCE_LABELS.get(force, force.title())
    return html.Tr([
        html.Td(
            [
                html.Span(label, className="dd-group-label"),
                html.Span(f"{count} signal{'s' if count != 1 else ''}",
                          className="dd-group-count"),
            ],
            colSpan=8,
            className="dd-group-header",
        )
    ])


def _signal_row(row: pd.Series, meta: dict) -> html.Tr:
    concept = ".".join(row["id"].split(".")[1:])   # strip country prefix
    name = _SIGNAL_NAMES.get(concept, concept.replace(".", " › ").replace("_", " ").title())
    series_label, prov_label = _fmt_series(str(row["source"]), str(row["provider"]))
    freq = meta.get("frequency", "?")
    freq_label = _FREQ_LABELS.get(freq, freq)
    next_rel = _next_release(str(row["as_of"]), freq)
    val_str = _fmt_val(float(row["value"]), str(row["units"]))
    ago = _days_ago(str(row["as_of"]))
    badges = _badges(row, next_rel, freq)
    # Highlight row if any non-OK badge
    has_issue = any("dd-badge-ok" not in b.className for b in badges if hasattr(b, "className") and b.className)

    return html.Tr([
        html.Td(name, className="dd-cell-name"),
        html.Td(
            html.Span(series_label, className="dd-series-chip"),
            className="dd-cell-series",
        ),
        html.Td(val_str, className="dd-cell-val"),
        html.Td(
            [
                html.Span(str(row["as_of"])[:7], className="dd-cell-date-main"),
                html.Br(),
                html.Span(ago, className="dd-cell-date-ago"),
            ],
            className="dd-cell-date",
        ),
        html.Td(freq_label, className="dd-cell-freq"),
        html.Td(prov_label, className="dd-cell-prov"),
        html.Td(next_rel, className="dd-cell-next"),
        html.Td(badges, className="dd-cell-badges"),
    ], className="dd-row dd-row-issue" if has_issue else "dd-row")


# ── Layout ───────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    df = _load_signals()
    meta = _load_binding_meta()

    # Group by force in display order
    force_order = _FORCE_ORDER + sorted(set(df["force"]) - set(_FORCE_ORDER))
    groups = {f: grp for f, grp in df.groupby("force")}

    header = html.Tr([
        html.Th("Signal",         className="dd-th"),
        html.Th("Series",         className="dd-th"),
        html.Th("Latest Value",   className="dd-th dd-th-r"),
        html.Th("As Of",          className="dd-th"),
        html.Th("Frequency",      className="dd-th"),
        html.Th("Source",         className="dd-th"),
        html.Th("Next Release",   className="dd-th"),
        html.Th("Status",         className="dd-th"),
    ])

    rows: list = []
    total_issues = 0
    for force in force_order:
        grp = groups.get(force)
        if grp is None or grp.empty:
            continue
        rows.append(_group_header(force, len(grp)))
        for _, r in grp.iterrows():
            sig_meta = meta.get(r["id"], {})
            rows.append(_signal_row(r, sig_meta))
            # Count signals with any issue
            if r["is_stale"] or r["low_history"]:
                total_issues += 1

    # Summary bar
    total = len(df)
    ok_count = total - total_issues
    summary = html.Div([
        html.Span(f"{total} signals", className="dd-summary-total"),
        html.Span(" · ", className="dd-summary-sep"),
        html.Span(f"✓ {ok_count} OK", className="dd-summary-ok"),
        html.Span(" · ", className="dd-summary-sep"),
        html.Span(f"⚠ {total_issues} with issues", className="dd-summary-warn") if total_issues else
        html.Span("All feeds current", className="dd-summary-ok"),
    ], className="dd-summary")

    legend = html.Div([
        html.Span("✓ OK", className="dd-badge dd-badge-ok"), html.Span(" — feed current  ", className="dd-legend-sep"),
        html.Span("STALE", className="dd-badge dd-badge-stale"), html.Span(" — past release window  ", className="dd-legend-sep"),
        html.Span("+Nd", className="dd-badge dd-badge-due"), html.Span(" — release overdue  ", className="dd-legend-sep"),
        html.Span("LOW HIST", className="dd-badge dd-badge-info"), html.Span(" — short history  ", className="dd-legend-sep"),
        html.Span("PROXY", className="dd-badge dd-badge-muted"), html.Span(" — proxy series  ", className="dd-legend-sep"),
        html.Span("DERIVED", className="dd-badge dd-badge-muted"), html.Span(" — computed from other feeds", className="dd-legend-sep"),
    ], className="dd-legend")

    return html.Div([
        html.Div([
            html.H4("Data Feed Monitor", style={"marginBottom": "2px", "fontSize": "1.1rem"}),
            html.P(
                "One row per signal. Grouped by force. Shows source series, latest ingested value, "
                "last observation date, and estimated next release window.",
                style={"color": "var(--muted-color)", "fontSize": "0.74rem", "marginBottom": "10px"},
            ),
            summary,
        ], className="pt-3 pb-2"),
        html.Div(
            html.Table(
                [html.Thead(header), html.Tbody(rows)],
                className="dd-table",
            ),
            style={"overflowX": "auto"},
        ),
        html.Div(legend, style={"marginTop": "14px"}),
    ], className="pe-2", style={"maxWidth": "1400px", "margin": "0 auto"})

"""Data Dashboard — operational feed health monitor with sort + filter.

Sticky header, sortable columns (Signal, As Of, Frequency, Source,
Next Release), and filter bar (search, force, status, frequency).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import yaml
import dash_bootstrap_components as dbc
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

_DB = os.getenv("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb")
_CONFIG_DIR = Path(__file__).parent.parent / "config"
_PROJECT_ROOT = Path(__file__).parent.parent

# ── Component IDs ─────────────────────────────────────────────────────────────
_SORT_STORE = "dd-sort-store"
_SEARCH_ID  = "dd-search"
_FORCE_ID   = "dd-force-filter"
_STATUS_ID  = "dd-status-filter"
_FREQ_ID    = "dd-freq-filter"
_TBODY_ID   = "dd-tbody"
_SUMMARY_ID = "dd-summary-text"
_THEAD_ID   = "dd-thead-tr"

_SORTABLE   = ["name", "as_of", "freq", "provider", "next_rel", "status"]
_RESET_BTN  = "dd-reset-sort"

# ── Display mappings ──────────────────────────────────────────────────────────

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
    # EZ-specific / multi-country signals (added 2026-06-23)
    "inflation.ppi":               "PPI (Producer Prices)",
    "inflation.wages_lci":         "Wages & Salaries (LCI)",
    "inflation.hicp_energy":       "HICP Energy",
    "inflation.hicp_food":         "HICP Food",
    "policy.central_bank_assets":  "Central Bank Assets",
    "policy.yield_spread":         "Yield Spread (10Y − Policy Rate)",
    # KR-specific
    "inflation.cpi_imf_annual":    "CPI Inflation (IMF Annual)",
}

_FREQ_LABELS: dict[str, str] = {
    "D": "Daily", "W": "Weekly", "M": "Monthly", "Q": "Quarterly", "A": "Annual",
}
_FREQ_ORDER = {"D": 0, "W": 1, "M": 2, "Q": 3, "A": 4}

_NEXT_DAYS: dict[str, int] = {
    "D": 2, "W": 10, "M": 45, "Q": 120, "A": 400,
}


# ── Pipeline refresh state ─────────────────────────────────────────────────────

_PASS_DEFS: list[dict] = [
    {"key": "us_ingest", "label": "FRED · WorldBank · IMF",              "country": "US", "marker": "Pass 1: FRED series [US]"},
    {"key": "us_comp",   "label": "Composites + rolling windows",         "country": "US", "marker": "Pass 5: Composites engine [US]"},
    {"key": "us_stress", "label": "Long-term Debt Stress",               "country": "US", "marker": "Pass 6: Long-Term Debt Stress"},
    {"key": "ez_ingest", "label": "FRED · Eurostat · ECB · WB · IMF",   "country": "EZ", "marker": "Country: EZ"},
    {"key": "ez_comp",   "label": "Composites",                          "country": "EZ", "marker": "Pass 5: Composites engine [EZ]"},
    {"key": "kr_ingest", "label": "FRED · WorldBank · IMF",              "country": "KR", "marker": "Country: KR"},
    {"key": "kr_comp",   "label": "Composites",                          "country": "KR", "marker": "Pass 5: Composites engine [KR]"},
]
_SKIP_MARKERS = ("Passes 5b-5d:", "Passes 5e-5f:")

_RUN_LOCK = threading.Lock()
_PIPELINE_STATE: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "elapsed_s": None,
    "exit_code": None,
    "current_pass": None,
    "log_tail": [],
    "passes": {p["key"]: {"status": "idle", "detail": ""} for p in _PASS_DEFS},
}


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    return f"{m}m {s}s"


def _reset_pipeline_state() -> None:
    _PIPELINE_STATE.update({
        "running": False, "started_at": None, "finished_at": None,
        "elapsed_s": None, "exit_code": None, "current_pass": None, "log_tail": [],
    })
    for key in _PIPELINE_STATE["passes"]:
        _PIPELINE_STATE["passes"][key] = {"status": "idle", "detail": ""}


def _update_pass_from_line(line: str) -> None:
    """Update pass status from one stdout line. Must be called with _RUN_LOCK held."""
    for skip in _SKIP_MARKERS:
        if skip in line:
            return
    for p in _PASS_DEFS:
        if p["marker"] in line:
            cur = _PIPELINE_STATE.get("current_pass")
            if cur and _PIPELINE_STATE["passes"][cur]["status"] == "running":
                _PIPELINE_STATE["passes"][cur]["status"] = "ok"
            _PIPELINE_STATE["passes"][p["key"]]["status"] = "running"
            _PIPELINE_STATE["current_pass"] = p["key"]
            return
    if "[ERROR]" in line:
        cur = _PIPELINE_STATE.get("current_pass")
        if cur:
            _PIPELINE_STATE["passes"][cur]["detail"] = line.strip()[:120]
    if "─── Summary" in line:
        cur = _PIPELINE_STATE.get("current_pass")
        if cur and _PIPELINE_STATE["passes"][cur]["status"] == "running":
            _PIPELINE_STATE["passes"][cur]["status"] = "ok"
            _PIPELINE_STATE["current_pass"] = None


def _run_pipeline_bg() -> None:
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "indicators.pipeline"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(_PROJECT_ROOT),
            env=os.environ.copy(),
        )
        for line in proc.stdout:
            line = line.rstrip()
            with _RUN_LOCK:
                _PIPELINE_STATE["log_tail"] = (_PIPELINE_STATE["log_tail"] + [line])[-30:]
                _update_pass_from_line(line)
        proc.wait()
        rc = proc.returncode
    except Exception as exc:
        rc = -1
        with _RUN_LOCK:
            _PIPELINE_STATE["log_tail"].append(f"[LAUNCH ERROR] {exc}")

    with _RUN_LOCK:
        cur = _PIPELINE_STATE.get("current_pass")
        if cur:
            _PIPELINE_STATE["passes"][cur]["status"] = "ok" if rc == 0 else "error"
            _PIPELINE_STATE["current_pass"] = None
        started = _PIPELINE_STATE["started_at"]
        _PIPELINE_STATE["elapsed_s"] = (
            (datetime.now() - datetime.fromisoformat(started)).total_seconds() if started else None
        )
        _PIPELINE_STATE["running"] = False
        _PIPELINE_STATE["finished_at"] = datetime.now().isoformat()
        _PIPELINE_STATE["exit_code"] = rc


def _start_pipeline_run() -> None:
    with _RUN_LOCK:
        if _PIPELINE_STATE["running"]:
            return
        _reset_pipeline_state()
        _PIPELINE_STATE["running"] = True
        _PIPELINE_STATE["started_at"] = datetime.now().isoformat()
    threading.Thread(target=_run_pipeline_bg, daemon=True).start()


def _render_pipeline_panel() -> html.Div:
    with _RUN_LOCK:
        state = {
            "running": _PIPELINE_STATE["running"],
            "started_at": _PIPELINE_STATE["started_at"],
            "elapsed_s": _PIPELINE_STATE["elapsed_s"],
            "exit_code": _PIPELINE_STATE["exit_code"],
            "passes": {k: dict(v) for k, v in _PIPELINE_STATE["passes"].items()},
        }

    if state["started_at"] is None:
        return html.Div()

    if state["running"]:
        elapsed = (datetime.now() - datetime.fromisoformat(state["started_at"])).total_seconds()
        hdr_icon, hdr_text, hdr_color = "⟳", f"Running — {_fmt_elapsed(elapsed)}", "#E8A317"
    elif state["exit_code"] == 0:
        hdr_icon, hdr_text, hdr_color = "✓", f"Completed in {_fmt_elapsed(state['elapsed_s'] or 0)}", "#5CB85C"
    else:
        hdr_icon, hdr_text, hdr_color = "✕", f"Failed after {_fmt_elapsed(state['elapsed_s'] or 0)}", "#E8534C"

    started_str = datetime.fromisoformat(state["started_at"]).strftime("%Y-%m-%d %H:%M")

    _cc_colors = {"US": "#4C9BE8", "EZ": "#F4C842", "KR": "#5CBA8A"}
    _st_cfg = {
        "idle":    ("○",  "var(--muted-color)", "Pending",  "var(--muted-color)"),
        "running": ("⟳",  "#E8A317",            "Running…", "#E8A317"),
        "ok":      ("✓",  "#5CB85C",            "Done",     "#5CB85C"),
        "error":   ("✕",  "#E8534C",            "Error",    "#E8534C"),
    }

    rows = []
    for p in _PASS_DEFS:
        ps = state["passes"][p["key"]]
        icon_ch, icon_col, lbl, lbl_col = _st_cfg.get(ps["status"], _st_cfg["idle"])
        cc = p["country"]
        cc_color = _cc_colors.get(cc, "#888")
        spin_cls = "pipe-spin" if ps["status"] == "running" else ""
        rows.append(html.Div([
            html.Span(icon_ch, className=spin_cls, style={"color": icon_col, "width": "16px", "display": "inline-block", "textAlign": "center"}),
            html.Span(cc, style={
                "fontSize": "0.62rem", "fontWeight": 700, "padding": "1px 5px",
                "borderRadius": "3px", "border": f"1px solid {cc_color}",
                "color": cc_color, "marginLeft": "8px", "marginRight": "8px",
            }),
            html.Span(p["label"], style={"fontSize": "0.76rem", "flexGrow": 1}),
            html.Span(lbl, style={"fontSize": "0.74rem", "color": lbl_col}),
            *(
                [html.Span(ps["detail"], style={"fontSize": "0.68rem", "color": "#E8534C", "marginLeft": "8px", "fontFamily": "monospace"})]
                if ps.get("detail") else []
            ),
        ], style={
            "display": "flex", "alignItems": "center", "gap": "4px",
            "padding": "5px 0", "borderBottom": "1px solid var(--border-color)",
        }))

    return html.Div([
        html.Div([
            html.Span(hdr_icon, className="pipe-spin" if state["running"] else "", style={"color": hdr_color, "marginRight": "6px"}),
            html.Span("Pipeline", style={"fontWeight": 600, "fontSize": "0.79rem", "marginRight": "10px"}),
            html.Span(hdr_text, style={"fontSize": "0.77rem", "color": hdr_color}),
            html.Span(f" · {started_str}", style={"fontSize": "0.71rem", "color": "var(--muted-color)", "marginLeft": "8px"}),
        ], style={"marginBottom": "10px", "display": "flex", "alignItems": "center"}),
        html.Div(rows),
    ], style={
        "backgroundColor": "var(--card-bg)",
        "border": "1px solid var(--border-color)",
        "borderRadius": "6px",
        "padding": "12px 16px",
        "marginBottom": "14px",
    })


# ── YAML metadata ─────────────────────────────────────────────────────────────

def _load_binding_meta(country: str = "US") -> dict[str, dict]:
    cc = (country or "US").upper()
    cc_path = _CONFIG_DIR / "countries" / f"{cc.lower()}_bindings.yaml"
    root_path = _CONFIG_DIR / f"{cc.lower()}_bindings.yaml"
    if cc_path.exists():
        path = cc_path
    elif root_path.exists():
        path = root_path
    else:
        path = _CONFIG_DIR / "us_bindings.yaml"
    with open(path) as f:
        cfg = yaml.safe_load(f)
    prefix = cc.lower()
    return {
        f"{prefix}.{b['id']}": {
            "frequency": b.get("frequency", "?"),
            "source_tier": b.get("source_tier", "free"),
        }
        for b in cfg.get("bindings", [])
    }


# ── DB query ──────────────────────────────────────────────────────────────────

def _load_signals(country: str = "US") -> pd.DataFrame:
    con = duckdb.connect(_DB, read_only=True)
    df = con.execute("""
        SELECT id, force, as_of, value, units, source, provider,
               is_stale, low_history, is_proxy, vintage_available, is_constructed
        FROM signals
        WHERE country = ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
        ORDER BY force, id
    """, [(country or "US").upper()]).df()
    con.close()
    return df


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_val(value: float, units: str) -> str:
    u = (units or "").lower()
    if u in ("yoy_pct", "yoy_pct_spread"):
        return f"{value * 100:+.2f}%"
    if u in ("pct_gdp", "pct_pot_gdp", "net_pct"):
        return f"{value:+.2f}%"
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
    if u in ("ratio", "diffusion_index"):
        return f"{value:.2f}"
    return f"{value:.2f}"


def _fmt_series(source: str) -> tuple[str, str]:
    """Return (series_id_label, provider_label)."""
    if not source or source in ("derived", "null", "None"):
        return "Derived", "—"
    if ":" in source:
        prov, sid = source.split(":", 1)
        return sid, prov
    return source, "—"


def _next_release(as_of: str, freq: str) -> str:
    days = _NEXT_DAYS.get(freq)
    if days is None:
        return "—"
    dt = pd.Timestamp(as_of) + timedelta(days=days)
    return dt.strftime("%Y-%m-%d") if freq == "D" else dt.strftime("%Y-%m")


def _days_ago(as_of: str) -> str:
    delta = (pd.Timestamp.today() - pd.Timestamp(as_of)).days
    if delta <= 0:
        return "today"
    if delta < 32:
        return f"{delta}d ago"
    months = round(delta / 30.5)
    return f"{months}mo ago"


# ── Badges ────────────────────────────────────────────────────────────────────

def _badges(row: pd.Series, next_rel: str, freq: str) -> list[html.Span]:
    today = pd.Timestamp.today()
    badges: list[html.Span] = []

    if row["is_stale"]:
        badges.append(html.Span("STALE", className="dd-badge dd-badge-stale"))
    elif next_rel not in ("—", "") and freq not in ("D", "W"):
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


def _has_issue(row: pd.Series) -> bool:
    return bool(row["is_stale"] or row["low_history"])


def _status_sort_key(row: pd.Series, freq: str, next_rel: str) -> int:
    """Lower = more severe (sorts issues to top on ascending)."""
    if row["is_stale"]:
        return 0
    if next_rel not in ("—", "") and freq not in ("D", "W"):
        try:
            rel_dt = pd.Timestamp(next_rel + "-01" if len(next_rel) == 7 else next_rel)
            if (pd.Timestamp.today() - rel_dt).days > 15:
                return 1   # overdue but not yet pipeline-flagged
        except Exception:
            pass
    if row["low_history"]:
        return 2
    if row["is_proxy"]:
        return 3
    if row["is_constructed"]:
        return 4
    return 5   # OK


# ── Table building ────────────────────────────────────────────────────────────

def _group_header(force: str, count: int) -> html.Tr:
    label = _FORCE_LABELS.get(force, force.title())
    return html.Tr(html.Td(
        [
            html.Span(label, className="dd-group-label"),
            html.Span(f"{count} signal{'s' if count != 1 else ''}",
                      className="dd-group-count"),
        ],
        colSpan=8,
        className="dd-group-header",
    ))


def _signal_row(row: pd.Series, sig_meta: dict) -> html.Tr:
    concept = ".".join(row["id"].split(".")[1:])
    name = _SIGNAL_NAMES.get(concept, concept.replace("_", " ").title())
    series_label, prov_label = _fmt_series(str(row["source"]))
    freq = sig_meta.get("frequency", "?")
    freq_label = _FREQ_LABELS.get(freq, freq)
    next_rel = _next_release(str(row["as_of"]), freq)
    val_str = _fmt_val(float(row["value"]), str(row["units"]))
    ago = _days_ago(str(row["as_of"]))
    badges = _badges(row, next_rel, freq)
    issue = _has_issue(row)

    return html.Tr([
        html.Td(name,  className="dd-cell-name"),
        html.Td(html.Span(series_label, className="dd-series-chip"),
                className="dd-cell-series"),
        html.Td(val_str, className="dd-cell-val"),
        html.Td([
            html.Span(str(row["as_of"])[:7], className="dd-cell-date-main"),
            html.Br(),
            html.Span(ago, className="dd-cell-date-ago"),
        ], className="dd-cell-date"),
        html.Td(freq_label,  className="dd-cell-freq"),
        html.Td(prov_label,  className="dd-cell-prov"),
        html.Td(next_rel,    className="dd-cell-next"),
        html.Td(badges,      className="dd-cell-badges"),
    ], className="dd-row dd-row-issue" if issue else "dd-row")


def _build_header(sort_state: dict) -> list:
    col = sort_state.get("col")
    asc = sort_state.get("dir", "asc") == "asc"

    def _icon(c: str) -> str:
        if col == c:
            return " ↑" if asc else " ↓"
        return " ⇅"

    def _th_s(label: str, c: str) -> html.Th:
        active = col == c
        return html.Th(
            html.Button(
                [label, html.Span(_icon(c), className="dd-sort-icon")],
                id=f"dd-hdr-{c}",
                n_clicks=0,
                className="dd-col-btn",
            ),
            className=f"dd-th dd-th-sort {'dd-th-active' if active else ''}",
        )

    return [
        _th_s("Signal",       "name"),
        html.Th("Series",      className="dd-th"),
        html.Th("Latest Value",className="dd-th dd-th-r"),
        _th_s("As Of",        "as_of"),
        _th_s("Frequency",    "freq"),
        _th_s("Source",       "provider"),
        _th_s("Next Release", "next_rel"),
        _th_s("Status",       "status"),
    ]


def _build_tbody(df: pd.DataFrame, meta: dict, sort_state: dict) -> list:
    sort_col = sort_state.get("col")
    asc = sort_state.get("dir", "asc") == "asc"

    # Sort key
    if sort_col == "name":
        df = df.copy()
        df["_sk"] = df["id"].apply(
            lambda x: _SIGNAL_NAMES.get(".".join(x.split(".")[1:]), x).lower())
        df = df.sort_values("_sk", ascending=asc).drop(columns=["_sk"])
    elif sort_col == "as_of":
        df = df.sort_values("as_of", ascending=asc)
    elif sort_col == "freq":
        df = df.copy()
        df["_sk"] = df["id"].apply(
            lambda x: _FREQ_ORDER.get(meta.get(x, {}).get("frequency", "?"), 99))
        df = df.sort_values("_sk", ascending=asc).drop(columns=["_sk"])
    elif sort_col == "provider":
        df = df.sort_values("provider", ascending=asc)
    elif sort_col == "next_rel":
        df = df.copy()
        df["_sk"] = df.apply(
            lambda r: _next_release(str(r["as_of"]), meta.get(r["id"], {}).get("frequency", "?")),
            axis=1,
        )
        df = df.sort_values("_sk", ascending=asc).drop(columns=["_sk"])
    elif sort_col == "status":
        df = df.copy()
        df["_sk"] = df.apply(
            lambda r: _status_sort_key(
                r,
                meta.get(r["id"], {}).get("frequency", "?"),
                _next_release(str(r["as_of"]), meta.get(r["id"], {}).get("frequency", "?")),
            ),
            axis=1,
        )
        df = df.sort_values("_sk", ascending=asc).drop(columns=["_sk"])

    rows: list = []
    if sort_col is not None:
        # Flat when sorting — no group headers
        for _, r in df.iterrows():
            rows.append(_signal_row(r, meta.get(r["id"], {})))
    else:
        # Grouped by force
        seen = set(_FORCE_ORDER)
        extras = sorted(set(df["force"]) - seen)
        for force in _FORCE_ORDER + extras:
            grp = df[df["force"] == force]
            if grp.empty:
                continue
            rows.append(_group_header(force, len(grp)))
            for _, r in grp.iterrows():
                rows.append(_signal_row(r, meta.get(r["id"], {})))

    if not rows:
        rows = [html.Tr(html.Td(
            "No signals match the current filters.",
            colSpan=8,
            className="dd-cell-empty",
        ))]
    return rows


def _build_summary(df: pd.DataFrame, total_all: int, active_filters: int) -> list:
    n = len(df)
    n_issues = int((df["is_stale"] | df["low_history"]).sum())
    n_ok = n - n_issues
    parts: list = [
        html.Span(f"{n}", style={"fontWeight": 700}),
        html.Span(" signals", style={"color": "var(--muted-color)"}),
    ]
    if active_filters and n < total_all:
        parts += [html.Span(f" of {total_all}", style={"color": "var(--muted-color)"})]
    parts += [
        html.Span("  ·  ", style={"color": "var(--muted-color)"}),
        html.Span(f"✓ {n_ok} OK", className="dd-summary-ok"),
        html.Span("  ·  ", style={"color": "var(--muted-color)"}),
        (html.Span(f"⚠ {n_issues} with issues", className="dd-summary-warn")
         if n_issues else html.Span("All feeds current", className="dd-summary-ok")),
    ]
    return parts


# ── Layout shell ──────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    # Static options — callback fills the table and updates description per country
    force_opts = [{"label": "All Forces", "value": ""}] + [
        {"label": _FORCE_LABELS.get(f, f.title()), "value": f}
        for f in _FORCE_ORDER
    ]
    freq_opts = [{"label": "All Frequencies", "value": ""}] + [
        {"label": _FREQ_LABELS.get(f, f), "value": f}
        for f in ["D", "W", "M", "Q", "A"]
    ]

    dd_style = {
        "backgroundColor": "var(--card-bg)",
        "color": "var(--font-color)",
        "borderColor": "var(--border-color)",
        "fontSize": "0.78rem",
    }

    filter_bar = dbc.Row([
        dbc.Col(dcc.Input(
            id=_SEARCH_ID, type="text", debounce=True,
            placeholder="Search signal name or series ID…",
            className="dd-search-input",
        ), md=4),
        dbc.Col(dcc.Dropdown(
            id=_FORCE_ID, options=force_opts, value="",
            clearable=False, style=dd_style, className="dd-dropdown",
        ), md=3),
        dbc.Col(dcc.Dropdown(
            id=_STATUS_ID,
            options=[
                {"label": "All Status",      "value": "all"},
                {"label": "✓ OK only",       "value": "ok"},
                {"label": "⚠ Issues only",   "value": "issues"},
                {"label": "STALE",           "value": "stale"},
                {"label": "LOW HIST",        "value": "low_hist"},
            ],
            value="all", clearable=False, style=dd_style, className="dd-dropdown",
        ), md=2),
        dbc.Col(dcc.Dropdown(
            id=_FREQ_ID, options=freq_opts, value="",
            clearable=False, style=dd_style, className="dd-dropdown",
        ), md=2),
        dbc.Col(
            html.Button(
                "↺ Reset Sort",
                id=_RESET_BTN,
                n_clicks=0,
                className="dd-reset-btn",
            ),
            md="auto",
        ),
    ], className="g-2 mb-3", align="center")

    legend = html.Div([
        html.Span("✓ OK", className="dd-badge dd-badge-ok"),
        html.Span(" feed current  ", className="dd-legend-sep"),
        html.Span("STALE", className="dd-badge dd-badge-stale"),
        html.Span(" past window  ", className="dd-legend-sep"),
        html.Span("+Nd", className="dd-badge dd-badge-due"),
        html.Span(" release overdue  ", className="dd-legend-sep"),
        html.Span("LOW HIST", className="dd-badge dd-badge-info"),
        html.Span(" short history  ", className="dd-legend-sep"),
        html.Span("DERIVED", className="dd-badge dd-badge-muted"),
        html.Span(" computed from other feeds", className="dd-legend-sep"),
    ], className="dd-legend", style={"marginTop": "12px"})

    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.H4("Data Feed Monitor",
                            style={"marginBottom": "2px", "fontSize": "1.1rem"}),
                    html.P(
                        id="dd-description",
                        children="Signals grouped by force. Click a column header to sort; sorting switches to flat view.",
                        style={"color": "var(--muted-color)", "fontSize": "0.74rem",
                               "marginBottom": "12px"},
                    ),
                ], style={"flex": 1}),
                html.Div(
                    dbc.Button(
                        "🔄 Refresh All",
                        id="dd-refresh-btn",
                        color="warning",
                        size="sm",
                        style={"fontSize": "0.76rem", "whiteSpace": "nowrap"},
                    ),
                    style={"alignSelf": "flex-start", "paddingTop": "4px"},
                ),
            ], style={"display": "flex", "alignItems": "flex-start", "gap": "12px"}),
            html.Div(id="dd-pipe-panel"),
            dcc.Interval(id="dd-pipe-interval", interval=1500, n_intervals=0, disabled=True),
            filter_bar,
            html.Div(id=_SUMMARY_ID, className="dd-summary", style={"marginBottom": "10px"}),
        ], className="pt-3"),

        dcc.Store(id=_SORT_STORE, data={"col": None, "dir": "asc"}),

        html.Div(
            html.Table([
                html.Thead(html.Tr(
                    _build_header({"col": None, "dir": "asc"}),
                    id=_THEAD_ID,
                )),
                html.Tbody(id=_TBODY_ID),
            ], className="dd-table"),
            className="dd-scroll-wrapper",
        ),
        legend,
    ], className="pe-2", style={"maxWidth": "1400px", "margin": "0 auto"})


# ── Callbacks ─────────────────────────────────────────────────────────────────

def register_callbacks(app) -> None:
    @app.callback(
        [
            Output(_TBODY_ID,       "children"),
            Output(_SUMMARY_ID,     "children"),
            Output(_SORT_STORE,     "data"),
            Output(_THEAD_ID,       "children"),
            Output("dd-description","children"),
        ],
        [
            Input(_SEARCH_ID,          "value"),
            Input(_FORCE_ID,           "value"),
            Input(_STATUS_ID,          "value"),
            Input(_FREQ_ID,            "value"),
            *[Input(f"dd-hdr-{c}", "n_clicks") for c in _SORTABLE],
            Input(_RESET_BTN,          "n_clicks"),
            Input("country-store",     "data"),
        ],
        State(_SORT_STORE, "data"),
        prevent_initial_call=False,
    )
    def _update(*args):
        n_inputs = 4 + len(_SORTABLE) + 2   # search/force/status/freq + headers + reset + country
        country: str = (args[n_inputs - 1] or "US").upper()
        sort_state: dict = args[-1] or {"col": None, "dir": "asc"}
        search, force_filter, status_filter, freq_filter = args[0], args[1], args[2], args[3]

        # Resolve sort column from which header was clicked; reset on country switch
        triggered = ctx.triggered_id or ""
        if triggered == "country-store":
            sort_state = {"col": None, "dir": "asc"}
        elif triggered == _RESET_BTN:
            sort_state = {"col": None, "dir": "asc"}
        elif isinstance(triggered, str) and triggered.startswith("dd-hdr-"):
            new_col = triggered[len("dd-hdr-"):]
            if sort_state.get("col") == new_col:
                new_dir = "desc" if sort_state.get("dir") == "asc" else "asc"
            else:
                new_dir = "asc"
            sort_state = {"col": new_col, "dir": new_dir}

        df = _load_signals(country)
        meta = _load_binding_meta(country)
        total_all = len(df)

        # ── Filters ────────────────────────────────────────────────────────
        if search and search.strip():
            q = search.strip().lower()
            def _match(r):
                concept = ".".join(r["id"].split(".")[1:])
                name = _SIGNAL_NAMES.get(concept, "").lower()
                return q in name or q in r["id"].lower() or q in str(r["source"]).lower()
            df = df[df.apply(_match, axis=1)]

        if force_filter:
            df = df[df["force"] == force_filter]

        if freq_filter:
            freq_mask = df["id"].apply(
                lambda x: meta.get(x, {}).get("frequency", "") == freq_filter)
            df = df[freq_mask]

        if status_filter == "ok":
            df = df[~df["is_stale"] & ~df["low_history"]]
        elif status_filter == "issues":
            df = df[df["is_stale"] | df["low_history"]]
        elif status_filter == "stale":
            df = df[df["is_stale"]]
        elif status_filter == "low_hist":
            df = df[df["low_history"]]

        # ── Build outputs ──────────────────────────────────────────────────
        active_filters = sum([
            bool(search and search.strip()),
            bool(force_filter),
            bool(freq_filter),
            status_filter not in ("all", None, ""),
        ])

        country_label = {"US": "United States", "EZ": "Euro Area", "KR": "South Korea",
                         "JP": "Japan", "GB": "United Kingdom", "CN": "China",
                         "IN": "India", "DE": "Germany", "LU": "Luxembourg"}.get(
            country, country
        )
        description = (
            f"{total_all} signals for {country_label}. "
            "Grouped by force. Click a column header to sort; sorting switches to flat view."
        )

        tbody    = _build_tbody(df, meta, sort_state)
        summary  = _build_summary(df, total_all, active_filters)
        header   = _build_header(sort_state)
        return tbody, summary, sort_state, header, description

    # ── Pipeline refresh callbacks ─────────────────────────────────────────

    @app.callback(
        Output("dd-pipe-panel",    "children"),
        Output("dd-pipe-interval", "disabled"),
        Output("dd-refresh-btn",   "disabled"),
        Input("dd-refresh-btn",    "n_clicks"),
        Input("dd-pipe-interval",  "n_intervals"),
        prevent_initial_call=True,
    )
    def _pipeline_update(n_clicks, n_intervals):
        triggered = ctx.triggered_id

        if triggered == "dd-refresh-btn":
            if not n_clicks:
                raise PreventUpdate
            _start_pipeline_run()
        elif triggered != "dd-pipe-interval":
            raise PreventUpdate

        panel = _render_pipeline_panel()
        with _RUN_LOCK:
            still_running = _PIPELINE_STATE["running"]
        return panel, not still_running, still_running

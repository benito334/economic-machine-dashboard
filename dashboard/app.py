"""Streamlit diagnostic terminal — Indicators Machine Phase 1C.

§5.1 grid layout:
  HUD   — Regime Quadrant · Confidence · Momentum arrows · Disequilibrium Speedometer
  Row 1 — 4-quadrant Plotly scatter + 12-month connected tail
  Row 2 — What Changed feed · Cross-Signal Conflict · Geopolitical-Risk Overlay
  Row 3 — Accordion drill-downs (lenses A–I + demographics)
  Row 4 — Data-quality log
"""
from __future__ import annotations

import math
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as _st_components
try:
    from dashboard.charting_data import (
        load_composite_component_status,
        load_debt_stress_component_dates,
        load_debt_stress_history,
    )
except ImportError:
    from charting_data import (  # type: ignore[no-redef]
        load_composite_component_status,
        load_debt_stress_component_dates,
        load_debt_stress_history,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════════

DB_PATH = Path(
    os.environ.get(
        "DB_PATH",
        "/mnt/data/db/all_weather/indicators_machine/signals.duckdb",
    )
)

QUADRANT_META: dict[str, dict] = {
    "Expansion": {
        "color": "#2ca02c",
        "bg": "rgba(44,160,44,0.12)",
        "symbol": "▲",
        "desc": "Growth ↑  Inflation ↓",
    },
    "Inflationary Boom": {
        "color": "#e67e00",
        "bg": "rgba(230,126,0,0.12)",
        "symbol": "◆",
        "desc": "Growth ↑  Inflation ↑",
    },
    "Stagflation": {
        "color": "#d62728",
        "bg": "rgba(214,39,40,0.12)",
        "symbol": "▼",
        "desc": "Growth ↓  Inflation ↑",
    },
    "Disinflationary Slowdown": {
        "color": "#1f77b4",
        "bg": "rgba(31,119,180,0.12)",
        "symbol": "◇",
        "desc": "Growth ↓  Inflation ↓",
    },
}

# Lens groups: (label, list of force values that belong to this lens)
LENS_GROUPS: list[tuple[str, list[str]]] = [
    ("Nominal Spending Master Indicators", ["master"]),
    ("A · Growth Force",                   ["growth"]),
    ("B · Inflation Force",                ["inflation"]),
    ("C · Monetary Policy & Rates",        ["policy"]),
    ("D · Credit, Debt & Fiscal",          ["credit", "fiscal"]),
    ("E · Risk Premiums",                  ["premium"]),
    ("F · External & Trade",               ["external"]),
    ("G · Capital Flows & Currency",       ["capital", "currency"]),
    ("H · Governance & Political Risk",    ["governance"]),
    ("I · Demographics & Structural",      ["demographics"]),
]

DIR_ARROW: dict[str, str] = {"rising": "↑", "falling": "↓", "flat": "→"}

# Brief description shown inside each lens accordion (educational layer)
LENS_ABOUT: dict[str, str] = {
    "Nominal Spending Master Indicators": (
        "Top-level view of nominal economic activity. GDP (real, nominal, deflator) and "
        "derived spreads that summarise the pace of money flowing through the economy. "
        "These are **lagging** — they confirm what already happened."
    ),
    "A · Growth Force": (
        "Real economic output and labour-market strength. The **Growth Score** composite "
        "is an equal-weight mean Z-score across 9 of these signals "
        "(Unemployment is *inverted* — lower unemployment = stronger growth). "
        "A positive score means the US economy is running above its long-run average."
    ),
    "B · Inflation Force": (
        "Price pressures across consumers, producers, and financial markets. The **Inflation Score** "
        "uses full weight (1×) for core measures (PCE, CPI, Wages, Breakevens) and half weight (0.5×) "
        "for commodity/headline items (Crude Oil, Headline CPI) to reduce short-term noise."
    ),
    "C · Monetary Policy & Rates": (
        "The price and quantity of money set by the Federal Reserve. "
        "Fed Funds and real yields tell you how tight or loose policy is; "
        "the balance sheet reflects QE/QT. These shape borrowing costs across the whole economy."
    ),
    "D · Credit, Debt & Fiscal": (
        "Leverage, debt sustainability, and the government's fiscal position. "
        "High debt/GDP or a widening deficit increases fragility; "
        "tightening lending standards are a leading warning of credit stress."
    ),
    "E · Risk Premiums": (
        "The extra return investors demand for holding risky or longer-duration assets. "
        "The yield curve (10Y−2Y, 10Y−3M) is a leading recession indicator — inversion has "
        "preceded every US recession since 1970. Credit spreads widen when default risk rises."
    ),
    "F · External & Trade": (
        "How the US economy relates to the rest of the world via trade flows. "
        "The current account deficit means the US imports more than it exports and must "
        "attract foreign capital to balance. Net IIP shows cumulative foreign ownership of US assets."
    ),
    "G · Capital Flows & Currency": (
        "Cross-border investment and the value of the dollar. "
        "FDI inflows signal long-term foreign confidence; the Real Effective Exchange Rate (REER) "
        "shows competitiveness — a stronger dollar makes exports pricier and imports cheaper."
    ),
    "H · Governance & Political Risk": (
        "Institutional quality, rule of law, and political stability (World Bank WGI scores). "
        "These structural indicators move slowly but matter for long-run capital allocation. "
        "⚠ Deferred — WB API unavailable; see G-03."
    ),
    "I · Demographics & Structural": (
        "Slow-moving forces that set the economy's long-run speed limit: population growth, "
        "urbanisation, labour force participation, and age dependency. "
        "These are **structural** — they update annually and change over decades, not months."
    ),
}

st.set_page_config(
    page_title="Indicators Machine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ═══════════════════════════════════════════════════════════════════════════════
# Regime History + Debt Stress — constants & helpers
# ═══════════════════════════════════════════════════════════════════════════════

_RH_COLORS = [
    "#4C9BE8", "#F4C842", "#5CBA8A", "#E8734C",
    "#B07FD4", "#E84C82", "#4CE8D4", "#E8C94C", "#8AB4F4", "#F4A442",
]
_RH_QUADRANT_COLOR = {
    "Expansion": "#5CBA8A",
    "Inflationary Boom": "#F4C842",
    "Stagflation": "#E8734C",
    "Disinflationary Slowdown": "#4C9BE8",
}
_GROWTH_COLOR    = "#4C9BE8"
_INFLATION_COLOR = "#E8734C"

_DEBT_STRESS_COMPONENTS = [
    ("z_gov_household_debt_gdp",   "Govt+HH Debt/GDP",      "positive"),
    ("z_corporate_debt_gdp",       "Corporate Debt/GDP",    "positive"),
    ("z_household_debt_service",   "HH Debt-Service Ratio", "positive"),
    ("z_federal_interest_gdp",     "Fed Interest/GDP",      "positive"),
    ("z_primary_balance_gdp",      "Primary Balance/GDP",   "negative"),
    ("z_structural_balance",       "Structural Balance",    "negative"),
    ("z_govt_revenue_gdp",         "Govt Revenue/GDP",      "negative"),
]
_STRESS_BAND_COLORS = {
    "Below-normal stress":  "#4C9BE8",
    "Near historical norm": "#aaaaaa",
    "Elevated stress":      "#F4C842",
    "High relative stress": "#E8734C",
}


def _stress_band_label(score: float) -> tuple[str, str]:
    try:
        from indicators.longterm_stress import load_longterm_stress_config, stress_band_label
        label = stress_band_label(score, load_longterm_stress_config()["bands"])
    except Exception:
        if score < -0.5:
            label = "Below-normal stress"
        elif score < 0.5:
            label = "Near historical norm"
        elif score < 1.0:
            label = "Elevated stress"
        else:
            label = "High relative stress"
    return label, _STRESS_BAND_COLORS.get(label, "#888")


def _parse_stress_components(raw: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            cid, lag = item.split(":", 1)
            result[cid.strip()] = int(lag)
        else:
            result[item] = 1
    return result


def _fmt_period(ts: "pd.Timestamp", freq: str) -> str:
    if freq == "Q":
        return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"
    return str(ts.year)


def _carry_expires(last_obs: "pd.Timestamp", freq: str, max_carry_q: int) -> str:
    carry_end = last_obs.to_period("Q") + max_carry_q
    return f"{carry_end.year}-Q{carry_end.quarter}"


# ── Figure builders (pure Plotly — usable in both Streamlit and Dash) ─────────

def _build_regime_history_fig(comp: pd.DataFrame, step: int = 0) -> go.Figure:
    if comp.empty:
        return go.Figure()
    fig = make_subplots(
        rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.25, 0.15, 0.25, 0.15, 0.20],
        subplot_titles=[
            "Growth Force Z-Score (composite)",
            "Growth Momentum (fraction of signals growth-positive)",
            "Inflation Force Z-Score (composite)",
            "Inflation Momentum (fraction of signals inflation-positive)",
            "Regime Quadrant",
        ],
    )
    fig.add_trace(go.Scatter(
        x=comp["as_of"], y=comp["growth_score"], name="Growth Score",
        line={"color": _GROWTH_COLOR, "width": 1.5}, fill="tozeroy",
        fillcolor="rgba(76,155,232,0.15)",
        hovertemplate="%{x|%Y-%m-%d}<br>Growth Z: %{y:.2f}<extra></extra>",
    ), row=1, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=1, col=1)
    if "growth_momentum" in comp.columns:
        fig.add_trace(go.Scatter(
            x=comp["as_of"], y=comp["growth_momentum"], name="Growth Momentum",
            line={"color": _GROWTH_COLOR, "width": 1.5, "dash": "dot"}, fill="tozeroy",
            fillcolor="rgba(76,155,232,0.10)",
            hovertemplate="%{x|%Y-%m-%d}<br>Growth Mom: %{y:.0%}<extra></extra>",
        ), row=2, col=1)
    fig.add_hline(y=0.5, line_dash="dot", line_color="#555", row=2, col=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1], row=2, col=1)
    fig.add_trace(go.Scatter(
        x=comp["as_of"], y=comp["inflation_score"], name="Inflation Score",
        line={"color": _INFLATION_COLOR, "width": 1.5}, fill="tozeroy",
        fillcolor="rgba(232,115,76,0.15)",
        hovertemplate="%{x|%Y-%m-%d}<br>Inflation Z: %{y:.2f}<extra></extra>",
    ), row=3, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=3, col=1)
    if "inflation_momentum" in comp.columns:
        fig.add_trace(go.Scatter(
            x=comp["as_of"], y=comp["inflation_momentum"], name="Inflation Momentum",
            line={"color": _INFLATION_COLOR, "width": 1.5, "dash": "dot"}, fill="tozeroy",
            fillcolor="rgba(232,115,76,0.10)",
            hovertemplate="%{x|%Y-%m-%d}<br>Inflation Mom: %{y:.0%}<extra></extra>",
        ), row=4, col=1)
    fig.add_hline(y=0.5, line_dash="dot", line_color="#555", row=4, col=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1], row=4, col=1)
    q_map = {"Expansion": 1, "Inflationary Boom": 2, "Stagflation": 3, "Disinflationary Slowdown": 0}
    fig.add_trace(go.Scatter(
        x=comp["as_of"], y=comp["quadrant"].map(q_map).fillna(-1),
        mode="markers", name="Quadrant", showlegend=False,
        marker={"color": [_RH_QUADRANT_COLOR.get(q, "#888") for q in comp["quadrant"]], "size": 5},
        hovertemplate="%{x|%Y-%m-%d}<br>%{customdata}<extra></extra>",
        customdata=comp["quadrant"],
    ), row=5, col=1)
    fig.update_yaxes(tickvals=[0,1,2,3], ticktext=["Dis.Slow","Expansion","Inf.Boom","Stagflation"], row=5, col=1)
    fig.update_layout(
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font={"color": "#cccccc"}, hovermode="x unified", height=1050,
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 60, "r": 20, "t": 80, "b": 40},
    )
    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikedash="dot", spikethickness=1, spikecolor="rgba(180,180,180,0.6)",
    )
    # Step marker
    n = len(comp)
    sel = comp.iloc[max(0, min(n - 1 - step, n - 1))]
    fig.add_vline(x=sel["as_of"], line_dash="dot", line_color="rgba(255,255,255,0.35)", line_width=1.5)
    for row_idx, col_key, color, size in [
        (1, "growth_score",     _GROWTH_COLOR,    11),
        (2, "growth_momentum",  _GROWTH_COLOR,     9),
        (3, "inflation_score",  _INFLATION_COLOR, 11),
        (4, "inflation_momentum", _INFLATION_COLOR, 9),
    ]:
        v = sel.get(col_key)
        if v is not None and not pd.isna(v):
            fig.add_trace(go.Scatter(
                x=[sel["as_of"]], y=[v], mode="markers",
                marker={"size": size, "color": color, "line": {"width": 2, "color": "#ffffff"}},
                showlegend=False, hoverinfo="skip",
            ), row=row_idx, col=1)
    return fig


def _build_debt_stress_fig(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    comp_labels = [lbl for _, lbl, _ in _DEBT_STRESS_COMPONENTS]
    comp_cols   = [col for col, _, _ in _DEBT_STRESS_COMPONENTS]
    comp_dirs   = [d   for _, _, d   in _DEBT_STRESS_COMPONENTS]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        row_heights=[0.45, 0.55],
        subplot_titles=["Composite Stress Score", "Component Z-Scores"],
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=1, col=1)
    fig.add_hrect(y0=0.5, y1=3.5, fillcolor="rgba(232,115,76,0.07)", line_width=0, row=1, col=1)
    fig.add_hrect(y0=1.0, y1=3.5, fillcolor="rgba(232,115,76,0.07)", line_width=0, row=1, col=1)
    fig.add_hrect(y0=-3.5, y1=-0.5, fillcolor="rgba(76,155,232,0.07)", line_width=0, row=1, col=1)
    score_col = df["stress_score"].where(~df["low_coverage"].fillna(False))
    fig.add_trace(go.Scatter(
        x=df["as_of"], y=score_col, name="Stress Score",
        line={"color": "#E8734C", "width": 2}, fill="tozeroy",
        fillcolor="rgba(232,115,76,0.12)",
        hovertemplate="%{x|%Y-Q%q}<br>Score: %{y:.2f}<extra></extra>",
    ), row=1, col=1)
    low_cov = df[df["low_coverage"].fillna(False)]
    if not low_cov.empty:
        fig.add_trace(go.Scatter(
            x=low_cov["as_of"], y=[0] * len(low_cov), mode="markers",
            marker={"color": "#555", "size": 5, "symbol": "x"},
            name="Low coverage",
            hovertemplate="%{x|%Y-Q%q}<br>Low coverage<extra></extra>",
        ), row=1, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#555", row=2, col=1)
    for i, (col, label, direction) in enumerate(zip(comp_cols, comp_labels, comp_dirs)):
        if col not in df.columns:
            continue
        z_series = df[col] if direction == "positive" else -df[col]
        fig.add_trace(go.Scatter(
            x=df["as_of"], y=z_series, name=label,
            line={"color": _RH_COLORS[i % len(_RH_COLORS)], "width": 1.2},
            hovertemplate=f"%{{x|%Y-Q%q}}<br>{label}: %{{y:.2f}}<extra></extra>",
        ), row=2, col=1)
    fig.update_yaxes(title_text="Z-Score", row=1, col=1)
    fig.update_yaxes(title_text="Z-Score (stress dir.)", row=2, col=1)
    fig.update_layout(
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font={"color": "#cccccc"}, hovermode="x unified", height=700,
        legend={"orientation": "h", "y": -0.12, "x": 0},
        margin={"l": 60, "r": 20, "t": 60, "b": 40},
    )
    return fig


# ── HTML table builders ────────────────────────────────────────────────────────

_TH = 'style="text-align:left;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;white-space:nowrap;"'
_TD = 'style="padding:5px 10px;font-size:0.82rem;border-bottom:1px solid #222;color:#ccc;vertical-align:middle;"'
_TD_MONO = 'style="padding:5px 10px;font-size:0.82rem;border-bottom:1px solid #222;color:#ccc;vertical-align:middle;font-family:monospace;"'


def _zbar_html(z: float, color: str) -> str:
    bar_w = min(abs(z) / 2.5 * 80, 80)
    return (
        f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:6px;">'
        f'<div style="width:{bar_w:.0f}px;height:6px;background:{color};border-radius:2px;opacity:0.6;flex-shrink:0;"></div>'
        f'<span style="color:{color};font-family:monospace;font-size:0.82rem;">{z:+.2f}</span>'
        f'</div>'
    )


def _badge_html(text: str, bg: str, fg: str) -> str:
    return f'<span style="background:{bg};color:{fg};padding:1px 5px;border-radius:3px;font-size:0.70rem;">{text}</span>'


def _render_regime_component_table(
    comp_df: pd.DataFrame,
    stale_dict: dict,
    weight_audit: Optional[dict] = None,
) -> str:
    if comp_df is None or comp_df.empty:
        return '<div style="color:#666;padding:8px;">No component data.</div>'
    audit_by_signal: dict[str, dict] = {}
    for force_audit in (weight_audit or {}).values():
        if isinstance(force_audit, dict):
            audit_by_signal.update(force_audit)
    rows_html: list[str] = []
    for force, color in [("growth", _GROWTH_COLOR), ("inflation", _INFLATION_COLOR)]:
        df_f = comp_df[comp_df["composite"] == force]
        n_active = (
            sum(float(audit_by_signal.get(sid, {}).get("effective_weight", 0.0)) > 0 for sid in df_f["signal_id"])
            if audit_by_signal
            else int((df_f["zscore"].notna() & ~df_f["is_stale"] & ~df_f["low_history"]).sum())
        )
        rows_html.append(
            f'<tr><td colspan="8" style="padding:8px 10px;background:rgba(0,0,0,0.3);'
            f'border-bottom:1px solid {color};">'
            f'<span style="color:{color};font-weight:700;font-size:0.72rem;'
            f'text-transform:uppercase;letter-spacing:0.07em;">'
            f'{force.upper()} FORCE INPUTS  ·  {n_active}/{len(df_f)} active</span></td></tr>'
        )
        for _, sr in df_f.iterrows():
            z = sr.get("zscore")
            direction = sr.get("direction") or ""
            change3m  = sr.get("change_3m")
            invert    = bool(sr.get("invert", False))
            is_stale  = bool(sr.get("is_stale", False))
            low_hist  = bool(sr.get("low_history", False))
            as_of     = sr.get("as_of")
            weight    = float(sr.get("weight", 1.0))
            z_missing = z is None or (isinstance(z, float) and pd.isna(z))
            sig_id = sr.get("signal_id", "")
            audit = audit_by_signal.get(sig_id, {})
            z_missing = z_missing or bool(audit.get("missing", False))
            importance = float(audit.get("importance", sr.get("importance", 1.0)))
            config_wt = float(audit.get("config_weight", weight))
            eff_wt = float(audit.get("effective_weight", 0.0 if z_missing else config_wt))
            momentum_mult = float(audit.get("momentum_multiplier", 1.0))
            decay = float(audit.get("decay_fraction", 1.0))
            age = max(stale_dict.get(sig_id, 0), int(round(float(audit.get("age_months", 0)))))
            last_str = pd.Timestamp(as_of).strftime("%b %Y") if (as_of is not None and not pd.isna(as_of)) else "—"
            # Z-score cell
            if z_missing:
                z_cell = '<td style="text-align:right;padding:5px 10px;border-bottom:1px solid #222;color:#555;">—</td>'
            else:
                z_cell = f'<td style="text-align:right;padding:5px 10px;border-bottom:1px solid #222;">{_zbar_html(float(z), color)}</td>'
            # Direction cell
            if direction:
                positive_dir = "falling" if (force == "growth" and invert) else "rising"
                arrow = "↑" if direction == "rising" else "↓"
                dir_color = color if (direction == positive_dir) else "#666"
                inv_note = " (inv)" if invert else ""
                ch_note = f' <span style="color:#555;font-size:0.72rem;font-family:monospace;">{float(change3m):+.3f} 3m</span>' if (change3m is not None and not pd.isna(change3m)) else ""
                dir_cell = f'<span style="color:{dir_color};">{arrow} {direction}{inv_note}</span>{ch_note}'
            else:
                dir_cell = '<span style="color:#555;">—</span>'
            # Status cell
            if not z_missing and (is_stale or age > 0):
                status = _badge_html(f"DECAYED · {age}m", "#7a4a00", "#ffcc80")
                status += f' <span style="color:#666;font-size:0.72rem;">time {decay:.0%} · momentum {momentum_mult:.1f}×</span>'
            elif low_hist:
                status = _badge_html("LOW HISTORY", "#3a3a00", "#cccc88")
            elif z_missing:
                status = _badge_html("BLANK", "#3a2020", "#cc7777")
            else:
                suffix = " · BOOSTED" if momentum_mult > 1 else (" · CONFLICT" if momentum_mult < 1 else "")
                status = _badge_html(f"ACTIVE{suffix}", "#1a3a1a", "#88cc88")
                if suffix:
                    status += f' <span style="color:#666;font-size:0.72rem;">momentum {momentum_mult:.1f}×</span>'
            row_bg = "rgba(60,20,20,0.12)" if (z_missing or is_stale or age > 0 or low_hist) else "transparent"
            rows_html.append(
                f'<tr style="background:{row_bg};">'
                f'<td {_TD}>{sr["label"]}</td>'
                f'<td {_TD_MONO}>{importance:.2f}</td>'
                f'<td {_TD_MONO}>{config_wt * 100:.1f}%</td>'
                f'<td {_TD_MONO}>{eff_wt * 100:.1f}%</td>'
                f'<td style="text-align:center;padding:5px 10px;font-family:monospace;font-size:0.75rem;border-bottom:1px solid #222;color:#666;">{last_str}</td>'
                f'{z_cell}'
                f'<td {_TD}>{dir_cell}</td>'
                f'<td {_TD}>{status}</td>'
                f'</tr>'
            )
    header = (
        f'<tr><th {_TH}>Signal</th>'
        f'<th {_TH}>Importance</th><th {_TH}>Config Wt</th><th {_TH}>Eff Wt</th>'
        f'<th style="text-align:center;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;">Last Data</th>'
        f'<th style="text-align:right;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;">Force Z</th>'
        f'<th {_TH}>Momentum</th>'
        f'<th {_TH}>Status / Detail</th></tr>'
    )
    return f'<div style="overflow-x:auto;"><table style="width:100%;min-width:1050px;border-collapse:collapse;">{header}{"".join(rows_html)}</table></div>'


def _render_debt_stress_table(
    ds_latest: "pd.Series | None",
    comp_dates: "dict | None",
) -> str:
    if ds_latest is None or ds_latest.empty:
        return '<div style="color:#666;padding:8px;">No debt stress data — run pipeline.</div>'
    try:
        from indicators.longterm_stress import load_longterm_stress_config
        stress_cfg    = load_longterm_stress_config()
        comp_cfg_list = stress_cfg.get("components", [])
        stale_cfg     = stress_cfg.get("staleness", {})
        max_carry_q   = int(stale_cfg.get("max_carry_quarters", 4))
        halflife      = stale_cfg.get("stale_weight_halflife")
        min_frac      = float(stale_cfg.get("stale_min_weight_fraction", 0.20))
        expected_lags = stale_cfg.get("expected_lag_quarters", {"Q": 1, "A": 4})
        extrap_on     = bool(stale_cfg.get("extrapolation", {}).get("enabled", False))
    except Exception:
        comp_cfg_list, max_carry_q, halflife, min_frac, expected_lags, extrap_on = [], 4, None, 0.20, {"Q": 1, "A": 4}, False
    comp_cfg_by_id = {c["id"]: c for c in comp_cfg_list}
    score  = ds_latest.get("stress_score")
    n_comp = int(ds_latest.get("n_components", 0))
    ret_wt = ds_latest.get("retained_weight")
    low_cov = bool(ds_latest.get("low_coverage", False))
    stale_dict  = _parse_stress_components(ds_latest.get("stale_components") or "")
    extrap_dict = _parse_stress_components(ds_latest.get("extrapolated_components") or "")
    as_of_ts = ds_latest.get("as_of")
    try:
        as_of_ts_p = pd.Timestamp(as_of_ts)
        as_of_str  = as_of_ts_p.strftime("%b %Y")
    except Exception:
        as_of_ts_p = None
        as_of_str  = str(as_of_ts)[:7]
    if score is not None and not (isinstance(score, float) and pd.isna(score)):
        band_label, band_color = _stress_band_label(float(score))
        score_str = f"{score:+.2f}"
    else:
        band_label, band_color = ("⚠ low coverage" if low_cov else "No data"), "#888"
        score_str = "—"
    ret_str = f"{ret_wt * 100:.0f}%" if (ret_wt is not None and not pd.isna(ret_wt)) else "—"
    summary = (
        f'<div style="display:flex;align-items:baseline;gap:20px;margin-bottom:14px;flex-wrap:wrap;">'
        f'<div><span style="font-size:0.65rem;color:#666;text-transform:uppercase;letter-spacing:0.08em;margin-right:6px;">DEBT STRESS</span>'
        f'<span style="font-size:0.65rem;color:#666;">as of {as_of_str}</span></div>'
        f'<span style="font-size:2.2rem;font-weight:700;color:{band_color};font-family:monospace;line-height:1.0;">{score_str}</span>'
        f'<span style="font-size:0.88rem;color:{band_color};opacity:0.85;">{band_label}</span>'
        f'<span style="font-size:0.75rem;color:#666;">{n_comp}/{len(comp_cfg_list) or len(_DEBT_STRESS_COMPONENTS)} components active</span>'
        f'<span style="font-size:0.75rem;color:#666;">retained weight: {ret_str}</span>'
        + (f'<span style="font-size:0.75rem;color:#E8734C;font-weight:600;">⚠ LOW COVERAGE</span>' if low_cov else '')
        + f'</div>'
    )
    header = (
        '<tr>'
        f'<th {_TH}>Component</th>'
        '<th style="text-align:center;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;">Freq</th>'
        '<th style="text-align:center;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;">Config Wt</th>'
        '<th style="text-align:center;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;">Eff Wt</th>'
        '<th style="text-align:center;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;">Last Data</th>'
        '<th style="text-align:right;padding:5px 10px;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#666;border-bottom:1px solid #333;">Z-Score</th>'
        f'<th {_TH}>Status / Detail</th>'
        '</tr>'
    )
    rows_html: list[str] = []
    for col, label, direction in _DEBT_STRESS_COMPONENTS:
        cid      = col.replace("z_", "")
        z        = ds_latest.get(col)
        val      = ds_latest.get(f"val_{cid}")
        cfg      = comp_cfg_by_id.get(cid, {})
        freq     = cfg.get("frequency", "Q")
        config_wt = float(cfg.get("weight", 0.0))
        lag_q    = stale_dict.get(cid, 0)
        extrap_q = extrap_dict.get(cid, 0)
        z_missing = z is None or (isinstance(z, float) and pd.isna(z))
        bar_color = "#E8734C" if direction == "positive" else "#4C9BE8"
        last_obs: "pd.Timestamp | None" = (comp_dates or {}).get(cid)
        last_data_str = _fmt_period(last_obs, freq) if last_obs is not None else ("active (derived)" if not z_missing else "derived")
        if z_missing and extrap_q == 0:
            eff_wt = 0.0
        elif halflife and halflife > 0 and (lag_q > 0 or extrap_q > 0):
            from indicators.longterm_stress import staleness_weight_fraction
            decay  = staleness_weight_fraction(max(lag_q, extrap_q), halflife)
            eff_wt = config_wt * decay
            if eff_wt < min_frac * config_wt:
                eff_wt = 0.0
        else:
            eff_wt = config_wt if not z_missing else 0.0
        config_wt_str = f"{config_wt * 100:.0f}%"
        eff_wt_str    = f"{eff_wt * 100:.0f}%"
        eff_wt_color  = "#ccc" if eff_wt == config_wt else ("#E8734C" if eff_wt == 0 else "#F4C842")
        z_cell = ('<td style="text-align:right;padding:5px 10px;border-bottom:1px solid #222;color:#555;">—</td>'
                  if z_missing else
                  f'<td style="text-align:right;padding:5px 10px;border-bottom:1px solid #222;">{_zbar_html(float(z), bar_color)}</td>')
        if extrap_q > 0:
            detail = f" · last: {_fmt_period(last_obs, freq)}" if last_obs is not None else ""
            status_html = _badge_html(f"EXTRAPOLATED · {extrap_q}q stale", "#2a3a5a", "#88aadd") + f'<span style="color:#666;font-size:0.75rem;">{detail}</span>'
        elif lag_q > 0:
            detail = f" · last: {_fmt_period(last_obs, freq)} · active with decay" if last_obs is not None else " · active with decay"
            status_html = _badge_html(f"STALE · {lag_q}q excess", "#7a4a00", "#ffcc80") + f'<span style="color:#666;font-size:0.75rem;">{detail}</span>'
        elif z_missing:
            if last_obs is not None and as_of_ts_p is not None:
                total_lag = max(0, as_of_ts_p.to_period("Q").ordinal - last_obs.to_period("Q").ordinal)
                carry_end = _carry_expires(last_obs, freq, max_carry_q)
                reason = f"carry expired · last: {_fmt_period(last_obs, freq)} · cap {max_carry_q}q → {carry_end}"
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    reason += f" · last known: {float(val):.2f}"
            else:
                reason = "insufficient data for Z-score"
            status_html = _badge_html("BLANK", "#3a2020", "#cc7777") + f'<span style="color:#666;font-size:0.75rem;"> {reason}</span>'
        else:
            status_html = _badge_html("ACTIVE", "#1a3a1a", "#88cc88")
        row_bg = "rgba(60,20,20,0.15)" if z_missing else "transparent"
        rows_html.append(
            f'<tr style="background:{row_bg};">'
            f'<td {_TD}>{label}</td>'
            f'<td style="text-align:center;padding:5px 10px;font-size:0.75rem;border-bottom:1px solid #222;color:#666;">{"Annual" if freq == "A" else "Quarterly"}</td>'
            f'<td style="text-align:center;padding:5px 10px;font-family:monospace;font-size:0.82rem;border-bottom:1px solid #222;color:#ccc;">{config_wt_str}</td>'
            f'<td style="text-align:center;padding:5px 10px;font-family:monospace;font-size:0.82rem;border-bottom:1px solid #222;color:{eff_wt_color};font-weight:{"600" if eff_wt < config_wt else "400"};">{eff_wt_str}</td>'
            f'<td style="text-align:center;padding:5px 10px;font-family:monospace;font-size:0.75rem;border-bottom:1px solid #222;color:#666;">{last_data_str}</td>'
            f'{z_cell}'
            f'<td {_TD}>{status_html}</td>'
            f'</tr>'
        )
    footer = (
        f'<div style="font-size:0.65rem;color:#444;margin-top:10px;">'
        f'⚠ Bands are NOT validated risk thresholds · Eff Wt applies exponential staleness decay'
        + (f' (half-life {int(halflife)}q)' if halflife else ' (off)')
        + f' · carry cap {max_carry_q}q</div>'
    )
    table = f'<table style="width:100%;border-collapse:collapse;">{header}{"".join(rows_html)}</table>'
    return summary + table + footer


# ═══════════════════════════════════════════════════════════════════════════════
# DB helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_latest_signals(country: str, as_of: Optional[str] = None) -> pd.DataFrame:
    reference_date = as_of or date.today().isoformat()
    with _conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM signals
            WHERE country = ? AND as_of <= ?
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
            ORDER BY force, id
            """,
            [country, reference_date],
        ).df()


@st.cache_data(ttl=300, show_spinner=False)
def load_composite_history(country: str, n_months: int = 60) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=n_months * 31)).isoformat()
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM composites WHERE country = ? AND as_of >= ? ORDER BY as_of",
            [country, cutoff],
        ).df()


@st.cache_data(ttl=300, show_spinner=False)
def load_all_signal_histories(
    country: str,
    n_months: int = 36,
    as_of: Optional[str] = None,
) -> pd.DataFrame:
    """Bulk-load all signal time series for sparkline generation."""
    reference_date = pd.Timestamp(as_of).date() if as_of else date.today()
    cutoff = (reference_date - timedelta(days=n_months * 31)).isoformat()
    with _conn() as conn:
        return conn.execute(
            """
            SELECT id, as_of, value
            FROM signals
            WHERE country = ? AND as_of >= ? AND as_of <= ?
            ORDER BY id, as_of
            """,
            [country, cutoff, reference_date.isoformat()],
        ).df()


@st.cache_data(ttl=300, show_spinner=False)
def load_debt_stress_latest(country: str, as_of: Optional[str] = None) -> pd.Series:
    """Return the latest DebtStressSnapshot available at an optional as-of date."""
    with _conn() as conn:
        cutoff_clause = "AND as_of <= ?" if as_of else ""
        params = [country] + ([as_of] if as_of else [])
        df = conn.execute(
            f"SELECT * FROM debt_stress_snapshots WHERE country = ? {cutoff_clause} "
            "ORDER BY as_of DESC LIMIT 1",
            params,
        ).df()
    if df.empty:
        return pd.Series(dtype=object)
    return df.iloc[0]


@st.cache_data(ttl=300, show_spinner=False)
def load_change_feed(country: str, as_of: Optional[str] = None) -> pd.DataFrame:
    reference_date = pd.Timestamp(as_of).date() if as_of else date.today()
    cutoff = (reference_date - timedelta(days=120)).isoformat()
    with _conn() as conn:
        return conn.execute(
            """
            WITH ranked AS (
                SELECT id, force, lead_lag, as_of, value, zscore, direction,
                       ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) AS rn
                FROM signals
                WHERE country = ? AND as_of <= ?
            ),
            latest AS (SELECT * FROM ranked WHERE rn = 1),
            prior  AS (SELECT * FROM ranked WHERE rn = 2)
            SELECT
                l.id, l.force, l.lead_lag, l.as_of, l.value, l.zscore, l.direction,
                p.zscore  AS prior_zscore,
                p.as_of   AS prior_as_of,
                ABS(l.zscore - COALESCE(p.zscore, l.zscore)) AS zscore_delta
            FROM latest l
            LEFT JOIN prior p ON l.id = p.id
            WHERE l.lead_lag IN ('leading', 'coincident') AND l.as_of >= ?
            ORDER BY zscore_delta DESC
            """,
            [country, reference_date.isoformat(), cutoff],
        ).df()


# ═══════════════════════════════════════════════════════════════════════════════
# Visual helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _pct_badge(pct: Optional[float], low_history: bool = False) -> str:
    if pct is None or (isinstance(pct, float) and math.isnan(pct)):
        return '<span style="background:#3a3a3a;color:#888;padding:2px 5px;border-radius:3px;font-size:0.75em;">—</span>'
    if low_history:
        bg, title = "#555", ' title="low-history — interpret with caution"'
    elif pct > 0.85:
        bg, title = "#9b1c1c", ""
    elif pct > 0.70:
        bg, title = "#c05a00", ""
    elif pct < 0.15:
        bg, title = "#1a3a6e", ""
    elif pct < 0.30:
        bg, title = "#2155a0", ""
    else:
        bg, title = "#444", ""
    return (
        f'<span{title} style="background:{bg};color:#eee;padding:2px 5px;'
        f'border-radius:3px;font-size:0.75em;font-family:monospace;">'
        f"{pct:.0%}</span>"
    )


def _quality_badges(row: pd.Series) -> str:
    parts: list[str] = []
    if row.get("is_proxy"):
        parts.append(
            '<span title="proxy series — not the primary indicator"'
            ' style="background:#5a5a5a;color:#ddd;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">proxy</span>'
        )
    if row.get("is_stale"):
        parts.append(
            '<span title="stale — not updated within its expected release window"'
            ' style="background:#7a4a00;color:#ffcc80;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">stale</span>'
        )
    if not row.get("vintage_available", True):
        parts.append(
            '<span title="no point-in-time vintage — uses latest-revised data"'
            ' style="background:#383838;color:#aaa;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">no&nbsp;vintage</span>'
        )
    if row.get("low_history"):
        parts.append(
            '<span title="fewer than 15 observations — z-score / percentile unreliable"'
            ' style="background:#4a5a5a;color:#cdd;padding:1px 4px;'
            'border-radius:3px;font-size:0.7em;">low&nbsp;hist</span>'
        )
    return "&nbsp;".join(parts)


def _sparkline_svg(
    values: list[float],
    width: int = 80,
    height: int = 20,
    color: str = "#5590cc",
) -> str:
    vals = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(vals) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1.0
    step = width / (len(vals) - 1)
    pts = []
    for i, v in enumerate(vals):
        x = i * step
        y = height - (v - mn) / rng * (height - 4) - 2
        pts.append(f"{x:.1f},{y:.1f}")
    path = "M" + " L".join(pts)
    return (
        f'<svg width="{width}" height="{height}" style="vertical-align:middle;display:inline-block;">'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f"</svg>"
    )


def _fmt_value(val: Optional[float], units: str) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "—"
    # decimal percentage → display as %
    if units in ("yoy_pct", "yoy_pct_spread"):
        return f"{val*100:+.2f}%"
    # already-in-percentage form
    if units in (
        "pct_level", "pct_gdp", "pct_pot_gdp",
        "pct_working_age", "pct_pop_15plus", "pct_annual",
        "pct_total_pop", "net_pct",
    ):
        return f"{val:.2f}%"
    if units in ("diffusion_index", "index", "index_2020eq100", "index_2010eq100"):
        return f"{val:.1f}"
    if units == "ratio":
        return f"{val:.3f}"
    if units == "thousands":
        return f"{val/1000:.1f}M" if abs(val) >= 1000 else f"{val:.0f}k"
    if units == "millions_usd":
        if abs(val) >= 1_000_000:
            return f"${val/1_000_000:.2f}T"
        if abs(val) >= 1_000:
            return f"${val/1_000:.1f}B"
        return f"${val:.0f}M"
    return f"{val:.4g}"


def _concept_label(signal_id: str) -> str:
    parts = signal_id.split(".")
    concept = parts[-1] if len(parts) >= 3 else signal_id
    return concept.replace("_", " ").title()


def _zscore_color(z: Optional[float]) -> str:
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return "#888"
    if z > 1.5:
        return "#ff8888"
    if z > 0.5:
        return "#ffbb88"
    if z < -1.5:
        return "#88aaff"
    if z < -0.5:
        return "#aaccff"
    return "#cccccc"


# ═══════════════════════════════════════════════════════════════════════════════
# Component builders
# ═══════════════════════════════════════════════════════════════════════════════

def _stress_band_color(band_label: str) -> str:
    return {
        "Below-normal stress":    "#4C9BE8",
        "Near historical norm":   "#aaaaaa",
        "Elevated stress":        "#F4C842",
        "High relative stress":   "#E8734C",
    }.get(band_label, "#888")


def _parse_stale_components(raw: str) -> dict[str, int]:
    """Parse 'cid:lag_q,cid2:lag_q2' → {cid: lag_q}. Handles plain 'cid' (lag=1) for back-compat."""
    result: dict[str, int] = {}
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            cid, lag = item.split(":", 1)
            result[cid.strip()] = int(lag)
        else:
            result[item] = 1
    return result


def _render_hud_debt_stress(ds: Optional[pd.Series]) -> str:
    """Return the inline HTML block for the Debt Stress HUD cell, or empty string if no data."""
    if ds is None or ds.empty:
        return ""

    score = ds.get("stress_score")
    n_comp = ds.get("n_components", 0)
    low_cov = ds.get("low_coverage", False)
    stale_dict = _parse_stale_components(ds.get("stale_components", ""))
    extrap_dict = _parse_stale_components(ds.get("extrapolated_components", ""))
    n_stale = len(stale_dict)
    n_extrap = len(extrap_dict)

    if score is None or (isinstance(score, float) and math.isnan(score)):
        score_str = "—"
        band_label = "⚠ low coverage" if low_cov else "No data"
        band_color = "#888"
    else:
        # Band thresholds are read from config; fallback to hardcoded spec defaults
        # if the import fails (display layer only — not a computation dependency).
        try:
            from indicators.longterm_stress import load_longterm_stress_config, stress_band_label
            _cfg = load_longterm_stress_config()
            band_label = stress_band_label(score, _cfg["bands"])
        except Exception:
            if score < -0.5:
                band_label = "Below-normal stress"
            elif score < 0.5:
                band_label = "Near historical norm"
            elif score < 1.0:
                band_label = "Elevated stress"
            else:
                band_label = "High relative stress"
        score_str = f"{score:+.2f}"
        band_color = _stress_band_color(band_label)

    stale_badge = (
        f'&nbsp;<span style="background:#7a4a00;color:#ffcc80;padding:1px 4px;'
        f'border-radius:3px;font-size:0.65em;">{n_stale} stale</span>'
        if n_stale else ""
    )
    extrap_badge = (
        f'&nbsp;<span style="background:#2a3a5a;color:#88aadd;padding:1px 4px;'
        f'border-radius:3px;font-size:0.65em;">{n_extrap} extrap</span>'
        if n_extrap else ""
    )

    return (
        f'<div style="border-left:1px solid #333;flex:0 0 130px;width:130px;'
        f'text-align:center;padding:0 8px;" '
        f'title="Long-Term Debt Stress Indicator — ⚠ bands NOT validated risk thresholds; see docs/longterm_stress_indicator.md">'
        f'<div style="font-size:0.65em;color:#666;text-transform:uppercase;letter-spacing:1px;">Debt Stress</div>'
        f'<div style="font-size:1.6em;font-weight:600;color:{band_color};font-family:monospace;line-height:1.15;">{score_str}</div>'
        f'<div style="font-size:0.65em;color:{band_color};opacity:0.85;">{band_label}</div>'
        f'<div style="font-size:0.6em;color:#555;margin-top:1px;">{int(n_comp)}/7{stale_badge}{extrap_badge}</div>'
        f'</div>'
    )


def render_hud(
    latest_composite: pd.Series,
    prev_composite: Optional[pd.Series] = None,
    step: int = 0,
    debt_stress: Optional[pd.Series] = None,
) -> None:
    q = latest_composite.get("quadrant") or "—"
    conf = latest_composite.get("confidence")
    gs = latest_composite.get("growth_score")
    inf = latest_composite.get("inflation_score")
    dis = latest_composite.get("disequilibrium_score")
    low_cov = latest_composite.get("low_coverage", False)
    as_of = latest_composite.get("as_of", "")

    meta = QUADRANT_META.get(q, {"color": "#888", "symbol": "?", "desc": "—", "bg": "transparent"})
    color = meta["color"]
    symbol = meta["symbol"]
    desc = meta["desc"]

    conf_pct = f"{conf:.1%}" if conf is not None else "—"
    dis_val  = f"{dis:.2f}" if dis is not None else "—"
    gs_val   = f"{gs:+.3f}" if gs is not None else "—"
    inf_val  = f"{inf:+.3f}" if inf is not None else "—"

    g_lvl_color = "#2ca02c" if (gs or 0) > 0 else "#d62728"
    i_lvl_color = "#e67e00" if (inf or 0) > 0 else "#1f77b4"

    g_delta: Optional[float] = None
    i_delta: Optional[float] = None
    if prev_composite is not None and not prev_composite.empty:
        prev_gs  = prev_composite.get("growth_score")
        prev_inf = prev_composite.get("inflation_score")
        if gs is not None and prev_gs is not None:
            g_delta = gs - prev_gs
        if inf is not None and prev_inf is not None:
            i_delta = inf - prev_inf

    def _mom_arrow(d: Optional[float]) -> str:
        if d is None: return "→"
        return "↑" if d > 0.01 else ("↓" if d < -0.01 else "→")

    def _mom_color(d: Optional[float]) -> str:
        if d is None: return "#888"
        return "#7ecf7e" if d > 0.01 else ("#cf7e7e" if d < -0.01 else "#aaa")

    g_mom = f"{g_delta:+.3f}" if g_delta is not None else "—"
    i_mom = f"{i_delta:+.3f}" if i_delta is not None else "—"

    # Date + step label shown at bottom of box
    try:
        _date_fmt = pd.Timestamp(as_of).strftime("%b %Y")
    except Exception:
        _date_fmt = str(as_of)[:7]
    if step == 0:
        _date_label = _date_fmt
        _date_color = "#666"
    else:
        _date_label = f"{_date_fmt}  ·  {step} month{'s' if step != 1 else ''} back"
        _date_color = "#F4C842"

    # Fixed-width centered cell — flex:0 0 w locks position regardless of value length.
    def _cell(label: str, value: str, sub: str, val_color: str = "#eee",
              border: bool = True, w: str = "120px") -> str:
        bl = 'border-left:1px solid #333;' if border else ''
        return (
            f'<div style="{bl}flex:0 0 {w};width:{w};text-align:center;padding:0 8px;">'
            f'<div style="font-size:0.65em;color:#666;text-transform:uppercase;letter-spacing:1px;">{label}</div>'
            f'<div style="font-size:1.6em;font-weight:600;color:{val_color};font-family:monospace;line-height:1.15;">{value}</div>'
            f'<div style="font-size:0.65em;color:#555;">{sub}</div>'
            f'</div>'
        )

    st.html(f"""
    <div style="
        background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);
        border:1px solid {color}44;
        border-radius:8px;
        padding:8px 20px 6px 20px;
        margin-bottom:6px;
    ">
      <!-- Single row: all indicators — fixed-width cells so values never shift position -->
      <div style="display:flex;align-items:center;gap:0;flex-wrap:nowrap;">

        <!-- Macro Regime: widest cell to fit "Disinflationary Slowdown" on two lines -->
        <div style="flex:0 0 190px;width:190px;text-align:center;padding:0 8px;">
          <div style="font-size:0.65em;color:#666;text-transform:uppercase;letter-spacing:1px;">Macro Regime</div>
          <div style="font-size:1.7em;font-weight:700;color:{color};line-height:1.2;">{symbol} {q}</div>
          <div style="font-size:0.75em;color:#888;">{desc}</div>
        </div>

        {_cell("Confidence",     conf_pct, "signal agreement", w="110px")}
        {_cell("Disequilibrium", dis_val,
               "⚠ low coverage" if low_cov else "mean |Z|",
               "#ff8888" if (dis or 0) > 1.0 else "#eee", w="120px")}
        {_render_hud_debt_stress(debt_stress)}
        {_cell("Growth Force",    gs_val,  "Z-score", g_lvl_color)}
        {_cell("Inflation Force", inf_val, "Z-score", i_lvl_color)}
        {_cell("Growth Mom",
               f"{_mom_arrow(g_delta)}&nbsp;{g_mom}",
               "month Δ", _mom_color(g_delta), w="140px")}
        {_cell("Inflation Mom",
               f"{_mom_arrow(i_delta)}&nbsp;{i_mom}",
               "month Δ", _mom_color(i_delta), w="140px")}

      </div>

      <!-- Date / step label -->
      <div style="text-align:center;margin-top:4px;font-size:0.82em;color:{_date_color};letter-spacing:0.03em;">
        {_date_label}
      </div>
    </div>
    """)


def render_quadrant_scatter(comp_df: pd.DataFrame, step: int = 0) -> go.Figure:
    fig = go.Figure()

    # Quadrant background shading
    for label, meta in QUADRANT_META.items():
        x0 = 0 if label in ("Expansion", "Inflationary Boom") else -3
        x1 = 3 if label in ("Expansion", "Inflationary Boom") else 0
        y0 = 0 if label in ("Inflationary Boom", "Stagflation") else -3
        y1 = 3 if label in ("Inflationary Boom", "Stagflation") else 0
        fig.add_shape(
            type="rect",
            x0=x0, x1=x1, y0=y0, y1=y1,
            fillcolor=meta["bg"],
            line_width=0,
            layer="below",
        )
        fig.add_annotation(
            x=(x0 + x1) / 2,
            y=(y0 + y1) / 2,
            text=label,
            showarrow=False,
            font=dict(size=10, color=meta["color"]),
            opacity=0.5,
        )

    # Axis lines
    fig.add_hline(y=0, line_color="#555", line_width=1)
    fig.add_vline(x=0, line_color="#555", line_width=1)

    # 12-month trail ending at the selected step
    if not comp_df.empty:
        n_total = len(comp_df)
        selected_idx = max(0, min(n_total - 1 - step, n_total - 1))
        trail_start = max(0, selected_idx - 12)
        trail = comp_df.iloc[trail_start:selected_idx + 1].copy()
        n = len(trail)
        for i in range(1, n):
            opacity = 0.15 + 0.70 * (i / (n - 1))
            fig.add_trace(
                go.Scatter(
                    x=[trail.iloc[i - 1]["growth_score"], trail.iloc[i]["growth_score"]],
                    y=[trail.iloc[i - 1]["inflation_score"], trail.iloc[i]["inflation_score"]],
                    mode="lines",
                    line=dict(color="#aaaaaa", width=1.5),
                    opacity=opacity,
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

        # Historical scatter (older points in grey)
        if trail_start > 0:
            hist = comp_df.iloc[:trail_start]
            fig.add_trace(
                go.Scatter(
                    x=hist["growth_score"],
                    y=hist["inflation_score"],
                    mode="markers",
                    marker=dict(size=4, color="#555555"),
                    name="History",
                    customdata=hist[["as_of", "quadrant", "confidence"]].values,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "%{customdata[1]}<br>"
                        "Confidence: %{customdata[2]:.1%}<br>"
                        "Growth: %{x:.3f}<br>"
                        "Inflation: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        # Colored trail dots by quadrant
        for _, row in trail.iterrows():
            q = row.get("quadrant") or "Expansion"
            c = QUADRANT_META.get(q, {}).get("color", "#aaa")
            fig.add_trace(
                go.Scatter(
                    x=[row["growth_score"]],
                    y=[row["inflation_score"]],
                    mode="markers",
                    marker=dict(size=7, color=c),
                    showlegend=False,
                    customdata=[[row["as_of"], q, row.get("confidence") or 0]],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "%{customdata[1]}<br>"
                        "Confidence: %{customdata[2]:.1%}<br>"
                        "Growth: %{x:.3f}<br>"
                        "Inflation: %{y:.3f}<extra></extra>"
                    ),
                )
            )

        # Selected month — large marker (NOW when current, date label when past)
        cur = comp_df.iloc[selected_idx]
        q_cur = cur.get("quadrant") or "Expansion"
        c_cur = QUADRANT_META.get(q_cur, {}).get("color", "#fff")
        try:
            _cur_label = "NOW" if step == 0 else pd.Timestamp(cur["as_of"]).strftime("%b %Y")
        except Exception:
            _cur_label = "NOW" if step == 0 else str(cur["as_of"])[:7]
        fig.add_trace(
            go.Scatter(
                x=[cur["growth_score"]],
                y=[cur["inflation_score"]],
                mode="markers+text",
                marker=dict(size=16, color=c_cur, line=dict(color="white", width=2)),
                text=[_cur_label],
                textposition="top center",
                textfont=dict(size=10, color=c_cur),
                showlegend=False,
                customdata=[[cur["as_of"], q_cur, cur.get("confidence") or 0]],
                hovertemplate=(
                    "<b>%{customdata[0]} (current)</b><br>"
                    "%{customdata[1]}<br>"
                    "Confidence: %{customdata[2]:.1%}<br>"
                    "Growth: %{x:.3f}<br>"
                    "Inflation: %{y:.3f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font=dict(color="#ccc"),
        xaxis=dict(
            title="Growth Score (Z-score)",
            gridcolor="#222",
            zeroline=False,
            range=[-3, 3],
        ),
        yaxis=dict(
            title="Inflation Score (Z-score)",
            gridcolor="#222",
            zeroline=False,
            range=[-3, 3],
        ),
        height=500,
        margin=dict(l=60, r=20, t=20, b=50),
        showlegend=False,
        # Preserve user zoom/pan across Streamlit reruns triggered by Prev/Next.
        # When uirevision is constant the Plotly frontend keeps current viewport;
        # changing it would reset the view (useful if you ever want a hard reset).
        uirevision="regime_map",
    )
    return fig


def render_what_changed(change_df: pd.DataFrame) -> None:
    st.markdown("#### What Changed")
    if change_df.empty:
        st.caption("No data.")
        return
    top = change_df.head(8)
    for _, row in top.iterrows():
        label = _concept_label(str(row["id"]))
        z_now = row.get("zscore") or 0.0
        z_prev = row.get("prior_zscore") or z_now
        delta = z_now - z_prev
        d_str = f"{delta:+.2f}" if not math.isnan(delta) else "—"
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        color = "#ff8888" if delta > 0.3 else ("#88aaff" if delta < -0.3 else "#aaa")
        prior_date = row.get("prior_as_of", "")
        st.html(
            f'<div style="padding:4px 0;border-bottom:1px solid #222;font-size:0.88em;">'
            f'<span style="color:#aaa;">{row["force"]}</span> · '
            f'<b>{label}</b> '
            f'<span style="color:{color};font-size:1.1em;">{arrow} {d_str}</span> '
            f'<span style="color:#666;font-size:0.8em;">Δ Z-score vs {prior_date}</span>'
            f"</div>"
        )


def render_conflict_panel(latest_signals: pd.DataFrame) -> None:
    st.markdown("#### Cross-Signal Conflicts")
    conflicts: list[str] = []

    for force in ["growth", "inflation"]:
        force_sigs = latest_signals[latest_signals["force"] == force]
        leading = force_sigs[force_sigs["lead_lag"] == "leading"]["direction"].dropna()
        lagging = force_sigs[force_sigs["lead_lag"] == "lagging"]["direction"].dropna()
        coincident = force_sigs[force_sigs["lead_lag"] == "coincident"]["direction"].dropna()

        if leading.empty or (lagging.empty and coincident.empty):
            continue

        lead_rising = (leading == "rising").mean()
        lag_ref = pd.concat([lagging, coincident])
        lag_rising = (lag_ref == "rising").mean() if not lag_ref.empty else None

        if lag_rising is not None:
            gap = abs(lead_rising - lag_rising)
            if gap > 0.4:
                if lead_rising < 0.4 and lag_rising > 0.6:
                    conflicts.append(
                        f"⚠ **{force.title()}**: Leading indicators turning down "
                        f"({lead_rising:.0%} rising) while lagging/coincident still firm "
                        f"({lag_rising:.0%} rising)"
                    )
                elif lead_rising > 0.6 and lag_rising < 0.4:
                    conflicts.append(
                        f"ℹ **{force.title()}**: Leading indicators strengthening "
                        f"({lead_rising:.0%} rising) while lagging/coincident still soft "
                        f"({lag_rising:.0%} rising)"
                    )

    # PMI vs payrolls check
    pmi = latest_signals[latest_signals["id"].str.endswith("pmi_proxy")]
    pay = latest_signals[latest_signals["id"].str.endswith("payrolls")]
    if not pmi.empty and not pay.empty:
        pmi_d = pmi.iloc[0].get("direction")
        pay_d = pay.iloc[0].get("direction")
        if pmi_d and pay_d and pmi_d != pay_d:
            conflicts.append(
                f"ℹ **Leading vs Coincident**: PMI proxy is {pmi_d} "
                f"while Payrolls is {pay_d}"
            )

    if conflicts:
        for c in conflicts:
            st.markdown(c)
    else:
        st.html('<span style="color:#888;font-size:0.88em;">No significant conflicts detected.</span>')


def render_gpr_overlay() -> None:
    st.markdown("#### Geopolitical-Risk Overlay")
    st.html(
        '<div style="color:#666;font-size:0.85em;padding:8px 0;">'
        "WGI governance scores deferred (WB v2 API unavailable as of 2026-06-18). "
        "See session-checklist G-03 for resolution path."
        "</div>"
    )


def _build_lens_table(
    lens_signals: pd.DataFrame,
    histories_by_id: dict[str, list[float]],
) -> str:
    if lens_signals.empty:
        return '<div style="color:#666;font-size:0.85em;padding:8px;">No data for this lens.</div>'

    rows_html: list[str] = []
    for _, row in lens_signals.iterrows():
        sid = str(row["id"])
        label = _concept_label(sid)
        linkage = str(row.get("linkage") or "").replace('"', "&quot;")
        val_str = _fmt_value(row.get("value"), str(row.get("units", "")))
        arrow = DIR_ARROW.get(str(row.get("direction") or "flat"), "→")
        pct = row.get("level_percentile")
        z = row.get("zscore")
        pct_html = _pct_badge(pct, bool(row.get("low_history")))
        badges_html = _quality_badges(row)
        z_val = f"{z:+.2f}" if z is not None and not (isinstance(z, float) and math.isnan(z)) else "—"
        z_color = _zscore_color(z)
        spark_vals = histories_by_id.get(sid, [])
        spark_html = _sparkline_svg(spark_vals)

        lead_lag_label = str(row.get("lead_lag", ""))
        ll_color = {
            "leading": "#aaffaa",
            "coincident": "#aaaaff",
            "lagging": "#ffaaaa",
            "structural": "#ddddaa",
        }.get(lead_lag_label, "#888")

        source = str(row.get("source", ""))
        rows_html.append(
            f'<tr style="border-bottom:1px solid #1e1e2e;">'
            f'<td style="padding:5px 8px;">{spark_html}</td>'
            f'<td style="padding:5px 8px;">'
            f'  <span title="{linkage}" style="cursor:help;">'
            f'    <b style="color:#ddd;">{label}</b>'
            f"  </span>"
            f'  &nbsp;<span style="font-size:0.7em;color:{ll_color};">'
            f"    {lead_lag_label}</span>"
            f'  <br><span style="font-size:0.7em;color:#555;">{source}</span>'
            f"</td>"
            f'<td style="text-align:right;padding:5px 8px;font-family:monospace;color:#ccc;">{val_str}</td>'
            f'<td style="text-align:center;padding:5px 8px;font-size:1.1em;">{arrow}</td>'
            f'<td style="text-align:center;padding:5px 8px;">{pct_html}</td>'
            f'<td style="text-align:center;padding:5px 8px;font-family:monospace;color:{z_color};">{z_val}</td>'
            f'<td style="padding:5px 8px;">{badges_html}</td>'
            f"</tr>"
        )

    header = (
        '<tr style="border-bottom:1px solid #333;color:#666;font-size:0.78em;">'
        '<th style="text-align:left;padding:4px 8px;min-width:90px;">Trend</th>'
        '<th style="text-align:left;padding:4px 8px;">Indicator</th>'
        '<th style="text-align:right;padding:4px 8px;">Value</th>'
        '<th style="text-align:center;padding:4px 8px;">Dir</th>'
        '<th style="text-align:center;padding:4px 8px;">Pct</th>'
        '<th style="text-align:center;padding:4px 8px;">Z</th>'
        '<th style="text-align:left;padding:4px 8px;">Quality</th>'
        "</tr>"
    )
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:0.88em;">'
        f"<thead>{header}</thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )


def render_data_quality_log(latest_signals: pd.DataFrame) -> None:
    st.markdown("#### Data-Quality Log")
    issues: list[dict] = []

    for _, row in latest_signals.iterrows():
        sid = str(row["id"])
        if row.get("is_stale"):
            issues.append({"Signal": sid, "Issue": "stale", "Note": "Not updated within expected release window"})
        if row.get("is_proxy"):
            issues.append({"Signal": sid, "Issue": "proxy", "Note": "Not the primary statistical release"})
        if row.get("low_history"):
            issues.append({"Signal": sid, "Issue": "low history", "Note": "< 15 observations — Z-score unreliable"})
        if not row.get("vintage_available", True):
            issues.append({"Signal": sid, "Issue": "no vintage", "Note": "Latest-revised only; no point-in-time data"})

    if issues:
        st.dataframe(
            pd.DataFrame(issues),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("No data-quality issues detected.")


# ═══════════════════════════════════════════════════════════════════════════════
# Main app
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if "regime_step" not in st.session_state:
        st.session_state["regime_step"] = 0

    st.markdown("""
    <style>
    /* Hide Streamlit's toolbar to reclaim vertical space */
    [data-testid="stHeader"],
    [data-testid="stToolbar"] { display: none !important; }

    /* Max-width + centre; do not touch overflow or height — window scroll stays normal */
    .block-container,
    [data-testid="stMainBlockContainer"] {
        max-width: 1600px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 0.4rem !important;
        padding-bottom: 1rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar ─────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Indicators Machine")
        st.markdown("**Country:** United States 🇺🇸")
        st.caption("Phase 2 will add multi-country selector (Eurozone, Japan, …)")
        st.divider()
        if st.button("🔄 Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.divider()

        with st.expander("📚 Methodology Guide", expanded=False):
            st.markdown("""
#### Core Concepts

**Z-Score**
How many standard deviations above or below the long-run historical average the current reading is.
`Z = (current − mean) ÷ std_dev`
- Z = +1.0 → roughly top 16% of all historical readings
- Z = −2.0 → bottom 2% (very depressed)
- Lets you compare completely different indicators (e.g. unemployment vs. PCE inflation) on one common scale.

**Percentile**
Rank of the current value within its own history. 85th percentile = higher than 85 % of all observations on record. Bounded 0–100 %; less sensitive to extreme outliers than Z-scores.

**Direction (↑ ↓ →)**
Derived from the 3-month change in value. A small dead-band prevents noise from flipping the arrow.
            """)

            st.markdown("""
#### Composite Scores

**Growth Score**
Dynamic weighted mean Z-score across 9 signals. Nominal weights combine base share, editable importance, and data quality; force/momentum agreement and observation age then adjust each point-in-time effective weight. Unemployment is *inverted* (lower unemployment = stronger growth).

| Signal | Type |
|---|---|
| Payrolls (YoY %) | coincident |
| Industrial Production (YoY %) | coincident |
| Retail Sales (YoY %) | coincident |
| Real PCE (YoY %) | coincident |
| Capacity Utilization (%) | coincident |
| Job Openings (thousands) | leading |
| PMI Proxy — Philly Fed ⚠ proxy | leading |
| Labor Force Participation (%) | coincident |
| Unemployment Rate (%) **inverted** | lagging |

Positive score → economy running above its historical average.

**Inflation Score**
Uses the same dynamic formula across 8 signals. Core measures have the highest default importance; commodity and market inputs receive smaller documented priors.

`effective weight = normalized(base share × importance × quality) × momentum tilt × age decay`

- Momentum agreement: 1.5× default; conflict: 0.5×; neutral: 1.0×
- Age decay: three-month half-life within the configured carry cap
- Importance and global weighting settings: `config/composites.yaml`
            """)

            st.markdown("""
#### HUD Metrics

**Force Scores** — the current composite Z-score level. A positive Growth Score means the economy is running above its long-run average; the sign determines which regime quadrant you are in.

**Momentum** — the month-over-month *change* in each composite score. Distinct from the level: the economy can be deep in Stagflation (negative Force Score) but with positive momentum (slowly recovering). This is the true rate-of-change signal.

**Confidence** — fraction of constituent signals whose 3-month direction agrees with the assigned quadrant label. In Stagflation (Growth−, Inflation+) we expect growth signals falling and inflation signals rising. 100 % = all signals agree; 0 % = complete disagreement.

**Disequilibrium Score** — mean absolute Z-score across structural force groups (debt, external, technology, governance, climate). High score (>1.5) = system stretched far from long-run equilibrium. Unlike the cyclical quadrant, this captures slow-moving structural risks.
            """)

            st.markdown("""
#### Signal Classification

**Lead / Lag**
- 🟢 *Leading* — forward-looking; move before the economy (job openings, PMI, breakevens, yield curve)
- 🔵 *Coincident* — reflect current conditions (payrolls, CPI, industrial production)
- 🔴 *Lagging* — confirm trends after the fact (unemployment, wages, govt debt/GDP)
- 🟡 *Structural* — slow-moving, multi-year (demographics, TFP, R&D intensity)

**Quality Badges**
- `proxy` — substitute series, not the primary statistical release
- `stale` — not updated within its expected release window
- `no vintage` — only latest-revised data; no point-in-time history available
- `low hist` — fewer than 15 observations; Z-score should be treated with caution

**Dalio's Four Seasons**

| | Growth + | Growth − |
|---|---|---|
| **Inflation +** | 🟠 Inflationary Boom | 🔴 Stagflation |
| **Inflation −** | 🟢 Expansion | 🔵 Disinflationary Slowdown |
            """)

        st.divider()
        st.caption(f"DB: `{DB_PATH}`")

    # ── Guard: DB exists ─────────────────────────────────────────────────────────
    if not DB_PATH.exists():
        st.error("Signal database not found. Run `python3 -m indicators.pipeline` first.")
        st.stop()

    # ── Load selected point-in-time data ─────────────────────────────────────────
    with st.spinner("Loading signals…"):
        comp_history = load_composite_history("US", n_months=60)

    # Step-based composite selection (step=0 → latest, step=N → N months back)
    n_comp = len(comp_history)
    max_step = max(0, n_comp - 1)
    step = min(st.session_state.get("regime_step", 0), max_step)
    selected_idx = max(0, n_comp - 1 - step) if n_comp > 0 else 0
    cur_comp:  pd.Series = comp_history.iloc[selected_idx] if n_comp > 0 else pd.Series()
    prev_comp: pd.Series = comp_history.iloc[selected_idx - 1] if selected_idx > 0 else pd.Series()
    selected_as_of = str(cur_comp.get("as_of")) if not cur_comp.empty else None

    with st.spinner("Loading signals…"):
        latest_signals = load_latest_signals("US", as_of=selected_as_of)
        all_histories = load_all_signal_histories("US", n_months=36, as_of=selected_as_of)
        change_feed = load_change_feed("US", as_of=selected_as_of)

    if latest_signals.empty:
        st.warning("No signals in DB. Run the pipeline first.")
        st.stop()

    histories_by_id: dict[str, list[float]] = {}
    if not all_histories.empty:
        for sid, grp in all_histories.groupby("id"):
            histories_by_id[str(sid)] = grp.sort_values("as_of")["value"].tolist()

    debt_stress = load_debt_stress_latest(
        "US", selected_as_of
    )

    # ── HUD ──────────────────────────────────────────────────────────────────────
    if not cur_comp.empty:
        render_hud(cur_comp, prev_comp if not prev_comp.empty else None, step=step, debt_stress=debt_stress)

    # ── Regime stepper ──────────────────────────────────────────────────────────
    _, _sc1, _sc2, _sc3, _ = st.columns([2.5, 1, 1, 1, 2.5])
    with _sc1:
        if st.button("← Prev", key="regime_prev", disabled=(step >= max_step), use_container_width=True):
            st.session_state["regime_step"] = min(step + 1, max_step)
            st.rerun()
    with _sc2:
        if st.button("◉ Now", key="regime_current", disabled=(step == 0), use_container_width=True):
            st.session_state["regime_step"] = 0
            st.rerun()
    with _sc3:
        if st.button("Next →", key="regime_next", disabled=(step <= 0), use_container_width=True):
            st.session_state["regime_step"] = max(step - 1, 0)
            st.rerun()

    # ── Fixed header injection ───────────────────────────────────────────────────
    # Navigate UP from stTabs to its direct parent — avoids brittle deep selectors
    # that break when Streamlit changes wrapper nesting. position:fixed is used
    # (not sticky) because stMain has overflow:auto which breaks sticky.
    _st_components.html("""
    <script>
    (function() {
        function applyFixed() {
            try {
                var pdoc = window.parent.document;
                var tabs = pdoc.querySelector('[data-testid="stTabs"]');
                if (!tabs) return;
                var container = tabs.parentElement;
                if (!container) return;
                var children = Array.from(container.children);
                var tabIdx = children.indexOf(tabs);
                if (tabIdx <= 0) return;

                // Wait until pre-tab elements have real heights
                var prePadding = 0;
                for (var i = 0; i < tabIdx; i++) prePadding += children[i].getBoundingClientRect().height;
                if (prePadding < 10) return;

                var stMain = pdoc.querySelector('[data-testid="stMain"]');
                var contentLeft = stMain ? stMain.getBoundingClientRect().left : 0;

                // Cap fixed elements at 1600 px and centre them within the viewport,
                // matching the max-width constraint on .block-container.
                var viewportW = window.parent.innerWidth || pdoc.documentElement.clientWidth;
                var maxW = 1600;
                var availW = viewportW - contentLeft;
                var elW   = Math.min(availW, maxW);
                var elLeft = contentLeft + Math.max(0, Math.floor((availW - maxW) / 2));

                function pin(el, topPx, zIdx) {
                    el.style.setProperty('position', 'fixed', 'important');
                    el.style.setProperty('top',   topPx + 'px', 'important');
                    el.style.setProperty('left',  elLeft + 'px', 'important');
                    el.style.setProperty('width', elW    + 'px', 'important');
                    el.style.removeProperty('right');
                    el.style.setProperty('z-index', String(zIdx), 'important');
                    el.style.setProperty('background-color', '#0e1117', 'important');
                }

                // 1. Fix pre-tab elements (HUD, stepper …) to the top band
                var top = 0;
                for (var i = 0; i < tabIdx; i++) {
                    pin(children[i], top, 500 - i);
                    top += children[i].getBoundingClientRect().height;
                }
                container.style.setProperty('padding-top', top + 'px', 'important');

                // 2. Make stTabs a fixed full-height scrollable panel below the header
                pin(tabs, top, 494);
                tabs.style.setProperty('bottom', '0', 'important');
                tabs.style.setProperty('height', 'auto', 'important');
                tabs.style.setProperty('overflow-y', 'auto', 'important');

                // 3. Pin the tab button bar above the scroll area.
                // Streamlit/BaseWeb uses data-baseweb="tab-list"; fall back to
                // role="tablist" or firstElementChild if that attr isn't present.
                var tabList = tabs.querySelector('[data-baseweb="tab-list"]')
                    || tabs.querySelector('[role="tablist"]')
                    || tabs.firstElementChild;
                if (tabList) {
                    var tabListH = tabList.getBoundingClientRect().height;
                    if (tabListH <= 0) return; // tablist not rendered yet
                    pin(tabList, top, 495);
                    // Push stTabs scroll content below the pinned tab bar
                    tabs.style.setProperty('padding-top', tabListH + 'px', 'important');
                }
            } catch(e) {}
        }
        setInterval(applyFixed, 300);
        setTimeout(applyFixed, 200);

        // ── Zoom-preserve for the regime scatter ─────────────────────────────────
        // Streamlit reconstructs the Plotly DOM element on every rerun so uirevision
        // cannot help. Instead we capture the user's zoom in sessionStorage and
        // re-apply it as soon as we detect the chart element was swapped.
        (function() {
            var ZOOM_KEY = 'regime_scatter_zoom';
            var lastDiv  = null;
            var pwin     = window.parent;
            var pdoc     = pwin.document;

            function findScatterDiv() {
                // Grab the first js-plotly-plot that lives inside the tab panel area.
                var panel = pdoc.querySelector('[data-baseweb="tab-panel"]');
                return panel ? panel.querySelector('.js-plotly-plot') : null;
            }

            function saveZoom(eventData) {
                // plotly_relayout fires for zoom, pan, and reset.
                if (!eventData) return;
                // Double-click / Home resets axis — clear stored zoom.
                if (eventData['xaxis.autorange'] || eventData['yaxis.autorange']) {
                    sessionStorage.removeItem(ZOOM_KEY);
                    return;
                }
                var x0 = eventData['xaxis.range[0]'], x1 = eventData['xaxis.range[1]'];
                var y0 = eventData['yaxis.range[0]'], y1 = eventData['yaxis.range[1]'];
                if (x0 != null && y0 != null) {
                    sessionStorage.setItem(ZOOM_KEY, JSON.stringify([x0, x1, y0, y1]));
                }
            }

            function restoreZoom(div) {
                var stored = sessionStorage.getItem(ZOOM_KEY);
                if (!stored) return;
                try {
                    var z = JSON.parse(stored); // [x0, x1, y0, y1]
                    var Plotly = pwin.Plotly;
                    if (Plotly && div) {
                        Plotly.relayout(div, {
                            'xaxis.range[0]': z[0], 'xaxis.range[1]': z[1],
                            'yaxis.range[0]': z[2], 'yaxis.range[1]': z[3],
                            'xaxis.autorange': false, 'yaxis.autorange': false
                        });
                    }
                } catch(e) {}
            }

            function pollZoom() {
                try {
                    var div = findScatterDiv();
                    if (!div) return;
                    if (div !== lastDiv) {
                        // Chart element was (re)created by Streamlit — attach listener
                        // and restore previous zoom after a short paint delay.
                        lastDiv = div;
                        div.on('plotly_relayout', saveZoom);
                        setTimeout(function() { restoreZoom(div); }, 120);
                    }
                } catch(e) {}
            }
            setInterval(pollZoom, 300);
            setTimeout(pollZoom, 500);
        })();
    })();
    </script>
    """, height=0)

    # ── Main content tabs ────────────────────────────────────────────────────────
    tab_map, tab_regime, tab_debt = st.tabs(["📊 Regime Map", "📈 Regime History", "📉 Debt Stress"])

    # ── Tab: Regime Map ──────────────────────────────────────────────────────────
    with tab_map:
        st.markdown("### Macro Regime Map")
        st.caption("12-month trail shown. X = Growth Score · Y = Inflation Score (Z-scores). NOW / date marker = selected reading.")
        fig = render_quadrant_scatter(comp_history, step=step)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False},
                        key="regime_scatter")

        col_wc, col_cf, col_gpr = st.columns([2, 2, 1.5])
        with col_wc:
            render_what_changed(change_feed)
        with col_cf:
            render_conflict_panel(latest_signals)
        with col_gpr:
            render_gpr_overlay()

        st.divider()
        st.markdown("### Signal Drill-Downs")
        st.caption("Percentile badge: 85%+ elevated (dark red) · 15%- depressed (dark blue) · neutral grey · Hover indicator name for causal linkage.")

        for lens_label, forces in LENS_GROUPS:
            lens_df = latest_signals[latest_signals["force"].isin(forces)].copy()
            n_sigs = len(lens_df)
            n_stale = int(lens_df.get("is_stale", pd.Series(dtype=bool)).sum()) if not lens_df.empty else 0
            badges = f"({n_sigs} signals)"
            if n_stale:
                badges += f' <span style="background:#7a4a00;color:#ffcc80;padding:1px 4px;border-radius:3px;font-size:0.7em;">{n_stale} stale</span>'
            with st.expander(f"{lens_label}  {badges if not n_stale else ''}", expanded=(lens_label == "A · Growth Force")):
                if n_stale:
                    st.html(badges)
                about = LENS_ABOUT.get(lens_label)
                if about:
                    st.html(
                        f'<div style="font-size:0.83em;color:#888;padding:4px 0 10px 0;'
                        f'border-bottom:1px solid #222;margin-bottom:10px;">{about}</div>'
                    )
                if n_sigs == 0:
                    st.caption("No data for this lens (deferred or not yet ingested).")
                else:
                    st.html(_build_lens_table(lens_df, histories_by_id))

        st.divider()
        with st.expander("Data-Quality Log", expanded=False):
            render_data_quality_log(latest_signals)

    # ── Tab: Regime History ──────────────────────────────────────────────────────
    with tab_regime:
        st.markdown("### Regime History")
        st.caption("Growth and Inflation force Z-scores over time. Vertical marker = selected step.")

        _as_of_str = str(cur_comp.get("as_of", "")) if not cur_comp.empty else None
        _comp_df = load_composite_component_status(country="US", as_of=_as_of_str)
        _stale_dict = _parse_stress_components(cur_comp.get("stale_signals") or "") if not cur_comp.empty else {}
        try:
            _weight_audit = json.loads(cur_comp.get("weight_audit") or "{}") if not cur_comp.empty else {}
        except (TypeError, json.JSONDecodeError):
            _weight_audit = {}
        st.html(_render_regime_component_table(_comp_df, _stale_dict, _weight_audit))

        st.plotly_chart(
            _build_regime_history_fig(comp_history, step=step),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── Tab: Debt Stress ─────────────────────────────────────────────────────────
    with tab_debt:
        st.markdown("### Long-Term Debt Stress")
        st.caption("7-component weighted Z-score composite. Exponential staleness decay applied to lagged inputs.")

        _ds_df = load_debt_stress_history(
            country="US", end_date=selected_as_of
        )
        _ds_latest = _ds_df.iloc[-1] if not _ds_df.empty else None
        _comp_dates = load_debt_stress_component_dates(
            country="US",
            as_of=str(_ds_latest.get("as_of")) if _ds_latest is not None else None,
        )
        st.html(_render_debt_stress_table(_ds_latest, _comp_dates))

        st.plotly_chart(
            _build_debt_stress_fig(_ds_df),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── Footer ───────────────────────────────────────────────────────────────────
    n_signals = len(latest_signals)
    n_composites = len(comp_history)
    latest_as_of = latest_signals["as_of"].max() if not latest_signals.empty else "—"
    st.html(
        f'<div style="text-align:center;color:#444;font-size:0.78em;margin-top:24px;">'
        f"{n_signals} signals · {n_composites} composite snapshots · "
        f"Latest signal: {latest_as_of} · "
        f"DB: {DB_PATH.name}"
        f"</div>"
    )


# Streamlit runs scripts top-to-bottom; this guard prevents main() from
# firing when the module is imported in tests.
if os.environ.get("INDICATORS_TESTING") != "1":
    main()

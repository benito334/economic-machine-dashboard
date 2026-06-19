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
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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

st.set_page_config(
    page_title="Indicators Machine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ═══════════════════════════════════════════════════════════════════════════════
# DB helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_latest_signals(country: str) -> pd.DataFrame:
    with _conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM signals
            WHERE country = ?
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
            ORDER BY force, id
            """,
            [country],
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
def load_all_signal_histories(country: str, n_months: int = 36) -> pd.DataFrame:
    """Bulk-load all signal time series for sparkline generation."""
    cutoff = (date.today() - timedelta(days=n_months * 31)).isoformat()
    with _conn() as conn:
        return conn.execute(
            """
            SELECT id, as_of, value
            FROM signals
            WHERE country = ? AND as_of >= ?
            ORDER BY id, as_of
            """,
            [country, cutoff],
        ).df()


@st.cache_data(ttl=300, show_spinner=False)
def load_change_feed(country: str) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=120)).isoformat()
    with _conn() as conn:
        return conn.execute(
            """
            WITH ranked AS (
                SELECT id, force, lead_lag, as_of, value, zscore, direction,
                       ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) AS rn
                FROM signals
                WHERE country = ? AND as_of >= ?
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
            WHERE l.lead_lag IN ('leading', 'coincident')
            ORDER BY zscore_delta DESC
            """,
            [country, cutoff],
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

def render_hud(latest_composite: pd.Series) -> None:
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

    g_arrow = "↑" if (gs or 0) > 0 else "↓"
    i_arrow = "↑" if (inf or 0) > 0 else "↓"

    conf_pct = f"{conf:.1%}" if conf is not None else "—"
    dis_val  = f"{dis:.2f}" if dis is not None else "—"
    gs_val   = f"{gs:+.3f}" if gs is not None else "—"
    inf_val  = f"{inf:+.3f}" if inf is not None else "—"

    st.markdown(
        f"""
        <div style="
            background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);
            border:1px solid {color}44;
            border-radius:10px;
            padding:20px 28px;
            margin-bottom:16px;
        ">
          <div style="display:flex;align-items:center;gap:32px;flex-wrap:wrap;">
            <div>
              <div style="font-size:0.72em;color:#888;text-transform:uppercase;letter-spacing:1px;">
                Macro Regime &nbsp;<span style="color:#555;">as of {as_of}</span>
              </div>
              <div style="font-size:2.0em;font-weight:700;color:{color};margin-top:2px;">
                {symbol} {q}
              </div>
              <div style="font-size:0.82em;color:#aaa;margin-top:2px;">{desc}</div>
            </div>
            <div style="border-left:1px solid #333;padding-left:28px;">
              <div style="font-size:0.72em;color:#888;text-transform:uppercase;letter-spacing:1px;">Confidence</div>
              <div style="font-size:1.8em;font-weight:600;color:#eee;">{conf_pct}</div>
            </div>
            <div style="border-left:1px solid #333;padding-left:28px;">
              <div style="font-size:0.72em;color:#888;text-transform:uppercase;letter-spacing:1px;">Momentum Vectors</div>
              <div style="font-size:1.4em;margin-top:4px;">
                <span style="color:#aaa;font-size:0.7em;">Growth&nbsp;</span>
                <span style="color:{'#2ca02c' if (gs or 0) > 0 else '#d62728'};font-weight:700;">{g_arrow} {gs_val}</span>
                &nbsp;&nbsp;
                <span style="color:#aaa;font-size:0.7em;">Inflation&nbsp;</span>
                <span style="color:{'#e67e00' if (inf or 0) > 0 else '#1f77b4'};font-weight:700;">{i_arrow} {inf_val}</span>
              </div>
            </div>
            <div style="border-left:1px solid #333;padding-left:28px;">
              <div style="font-size:0.72em;color:#888;text-transform:uppercase;letter-spacing:1px;">Disequilibrium Score</div>
              <div style="font-size:1.8em;font-weight:600;color:{'#ff8888' if (dis or 0) > 1.0 else '#eee'};">{dis_val}</div>
              {"<div style='font-size:0.72em;color:#888;'>⚠ low coverage</div>" if low_cov else ""}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_quadrant_scatter(comp_df: pd.DataFrame) -> go.Figure:
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

    # 12-month trail
    if not comp_df.empty:
        trail = comp_df.tail(13).copy()
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
        if len(comp_df) > 13:
            hist = comp_df.iloc[:-13]
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

        # Current month — large marker
        cur = comp_df.iloc[-1]
        q_cur = cur.get("quadrant") or "Expansion"
        c_cur = QUADRANT_META.get(q_cur, {}).get("color", "#fff")
        fig.add_trace(
            go.Scatter(
                x=[cur["growth_score"]],
                y=[cur["inflation_score"]],
                mode="markers+text",
                marker=dict(size=16, color=c_cur, line=dict(color="white", width=2)),
                text=["NOW"],
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
        st.markdown(
            f'<div style="padding:4px 0;border-bottom:1px solid #222;font-size:0.88em;">'
            f'<span style="color:#aaa;">{row["force"]}</span> · '
            f'<b>{label}</b> '
            f'<span style="color:{color};font-size:1.1em;">{arrow} {d_str}</span> '
            f'<span style="color:#666;font-size:0.8em;">Δ Z-score vs {prior_date}</span>'
            f"</div>",
            unsafe_allow_html=True,
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
        st.markdown('<span style="color:#888;font-size:0.88em;">No significant conflicts detected.</span>', unsafe_allow_html=True)


def render_gpr_overlay() -> None:
    st.markdown("#### Geopolitical-Risk Overlay")
    st.markdown(
        '<div style="color:#666;font-size:0.85em;padding:8px 0;">'
        "WGI governance scores deferred (WB v2 API unavailable as of 2026-06-18). "
        "See session-checklist G-03 for resolution path."
        "</div>",
        unsafe_allow_html=True,
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
        st.caption(f"DB: `{DB_PATH}`")

    # ── Guard: DB exists ─────────────────────────────────────────────────────────
    if not DB_PATH.exists():
        st.error("Signal database not found. Run `python3 -m indicators.pipeline` first.")
        st.stop()

    # ── Load data ────────────────────────────────────────────────────────────────
    with st.spinner("Loading signals…"):
        latest_signals = load_latest_signals("US")
        comp_history   = load_composite_history("US", n_months=60)
        all_histories  = load_all_signal_histories("US", n_months=36)
        change_feed    = load_change_feed("US")

    if latest_signals.empty:
        st.warning("No signals in DB. Run the pipeline first.")
        st.stop()

    # Build sparkline lookup: {signal_id: [values...]}
    histories_by_id: dict[str, list[float]] = {}
    if not all_histories.empty:
        for sid, grp in all_histories.groupby("id"):
            histories_by_id[str(sid)] = grp.sort_values("as_of")["value"].tolist()

    # Current composite
    cur_comp: pd.Series = comp_history.iloc[-1] if not comp_history.empty else pd.Series()

    # ── Page header ──────────────────────────────────────────────────────────────
    st.markdown(
        '<h1 style="font-size:1.6em;margin-bottom:4px;">📊 Indicators Machine</h1>'
        '<p style="color:#666;font-size:0.85em;margin-top:0;">US Macro-Regime Diagnostic Terminal · Ray Dalio Economic Machine framework</p>',
        unsafe_allow_html=True,
    )

    # ── HUD ──────────────────────────────────────────────────────────────────────
    if not cur_comp.empty:
        render_hud(cur_comp)

    # ── Row 1: 4-Quadrant Scatter ────────────────────────────────────────────────
    st.markdown("### Macro Regime Map")
    st.caption("12-month trail shown. X = Growth Score · Y = Inflation Score (Z-scores). NOW marker = current reading.")
    fig = render_quadrant_scatter(comp_history)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Row 2: What Changed · Conflict · GPR ────────────────────────────────────
    col_wc, col_cf, col_gpr = st.columns([2, 2, 1.5])
    with col_wc:
        render_what_changed(change_feed)
    with col_cf:
        render_conflict_panel(latest_signals)
    with col_gpr:
        render_gpr_overlay()

    st.divider()

    # ── Row 3: Accordion drill-downs ─────────────────────────────────────────────
    st.markdown("### Signal Drill-Downs")
    st.caption(
        "Percentile badge: "
        '<span style="background:#9b1c1c;color:#eee;padding:1px 5px;border-radius:3px;font-size:0.8em;">85%+</span> '
        'elevated &nbsp; '
        '<span style="background:#1a3a6e;color:#eee;padding:1px 5px;border-radius:3px;font-size:0.8em;">15%-</span> '
        'depressed · Hover indicator name for causal linkage.',
        unsafe_allow_html=True,
    )

    for lens_label, forces in LENS_GROUPS:
        lens_df = latest_signals[latest_signals["force"].isin(forces)].copy()
        n_sigs = len(lens_df)
        n_stale = int(lens_df.get("is_stale", pd.Series(dtype=bool)).sum()) if not lens_df.empty else 0

        badges = f"({n_sigs} signals)"
        if n_stale:
            badges += f' <span style="background:#7a4a00;color:#ffcc80;padding:1px 4px;border-radius:3px;font-size:0.7em;">{n_stale} stale</span>'

        with st.expander(f"{lens_label}  {badges if not n_stale else ''}", expanded=(lens_label == "A · Growth Force")):
            if n_stale:
                st.markdown(badges, unsafe_allow_html=True)
            if n_sigs == 0:
                st.caption("No data for this lens (deferred or not yet ingested).")
            else:
                table_html = _build_lens_table(lens_df, histories_by_id)
                st.markdown(table_html, unsafe_allow_html=True)

    st.divider()

    # ── Row 4: Data-quality log ──────────────────────────────────────────────────
    with st.expander("Data-Quality Log", expanded=False):
        render_data_quality_log(latest_signals)

    # ── Footer ───────────────────────────────────────────────────────────────────
    n_signals = len(latest_signals)
    n_composites = len(comp_history)
    latest_as_of = latest_signals["as_of"].max() if not latest_signals.empty else "—"
    st.markdown(
        f'<div style="text-align:center;color:#444;font-size:0.78em;margin-top:24px;">'
        f"{n_signals} signals · {n_composites} composite snapshots · "
        f"Latest signal: {latest_as_of} · "
        f"DB: {DB_PATH.name}"
        f"</div>",
        unsafe_allow_html=True,
    )


# Streamlit runs scripts top-to-bottom; this guard prevents main() from
# firing when the module is imported in tests.
if os.environ.get("INDICATORS_TESTING") != "1":
    main()

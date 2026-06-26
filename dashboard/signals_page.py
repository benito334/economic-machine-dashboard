"""Signals page — 5-force signal breakdown styled as Regime History Force Components table.

Route: /signals
Five collapsible sections: Growth · Inflation · Interest Rate · Credit · Volatility.
Section header: force name · composite Z · momentum arrow · active/total count.
Table columns match the Force Component Inputs table from the Regime History page:
  Signal | Importance | Config Wt | Eff Wt | Last Data | Force Z (bar) | Momentum | Status
Growth, Inflation, Rate and Credit are all full composites with importance/weight columns.
For Volatility only the weight columns show "—" (not in composites).
"""
from __future__ import annotations

import json
import math
from typing import Optional

import pandas as pd

from dash import Input, Output, callback, html, no_update

from dashboard.charting_data import (
    load_composite_component_status,
    load_composite_history,
    load_latest_signals,
)
from dashboard.shared_components import (
    _CLR_GREEN_HI, _CLR_GREEN_LO, _CLR_RED_HI, _CLR_RED_LO,
    _concept_label, _lerp_rgb, _signal_info_icon, _signal_link, _zscore_color,
)

# ── Force accent colours ───────────────────────────────────────────────────────
_GROWTH_COLOR     = "#5CBA8A"
_INFLATION_COLOR  = "#E8734C"
_RATE_COLOR       = "#4C9BE8"
_CREDIT_COLOR     = "#B07FD4"
_VOLATILITY_COLOR = "#F4C842"

# ── Policy force exclusions per country ───────────────────────────────────────
_RATE_EXCLUDE: dict[str, set] = {
    "US": {"fed_balance_sheet", "monetary_base_gdp"},
    "EZ": {"central_bank_assets", "fed_funds_target"},
    "KR": set(),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _concept(signal_id: str) -> str:
    parts = signal_id.split(".")
    return parts[-1] if len(parts) >= 3 else signal_id


def _majority_arrow(directions) -> str:
    rising  = sum(1 for d in directions if d == "rising")
    falling = sum(1 for d in directions if d == "falling")
    return "↑" if rising > falling else ("↓" if falling > rising else "→")


def _direction_fraction(df: pd.DataFrame) -> Optional[float]:
    """Fraction of signals with direction == 'rising' (0.0–1.0)."""
    if df.empty or "direction" not in df.columns:
        return None
    dirs = df["direction"].dropna().tolist()
    return sum(1 for d in dirs if d == "rising") / len(dirs) if dirs else None


def _momentum_score_color(score: Optional[float], force: str) -> str:
    """Semantic color for a momentum fraction (0–1).

    0.5 = neutral (grey). Above 0.5 = more signals rising.
    For growth/rate/credit/vol: rising is good → green.
    For inflation: rising is bad → red.
    """
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return "#666"
    adj = score - 0.5
    if force == "inflation":
        adj = -adj
    magnitude = min(abs(adj) / 0.5, 1.0)
    if magnitude < 0.07:
        return "#888"
    if adj > 0:
        return _lerp_rgb(magnitude, _CLR_GREEN_LO, _CLR_GREEN_HI)
    return _lerp_rgb(magnitude, _CLR_RED_LO, _CLR_RED_HI)


def _mean_z(df: pd.DataFrame) -> Optional[float]:
    if df.empty or "zscore" not in df.columns:
        return None
    vals = df["zscore"].dropna()
    return float(vals.mean()) if not vals.empty else None


def _vix_df(country: str) -> pd.DataFrame:
    if country != "US":
        return pd.DataFrame()
    try:
        from indicators.regime_classifier import _load_vix

        vix = _load_vix()
        if vix is None or vix.empty:
            return pd.DataFrame()
        window   = 120
        roll     = vix.rolling(window, min_periods=24)
        z_series = (vix - roll.mean()) / roll.std()
        last_val  = float(vix.iloc[-1])
        prev_val  = float(vix.iloc[-2]) if len(vix) > 1 else last_val
        z_val = (
            float(z_series.iloc[-1])
            if not z_series.empty and not math.isnan(z_series.iloc[-1])
            else None
        )
        return pd.DataFrame([{
            "id":          "us.volatility.vix",
            "label":       "VIX",
            "direction":   "rising" if last_val > prev_val else "falling",
            "zscore":      z_val,
            "change_3m":   None,
            "is_stale":    False,
            "low_history": False,
            "as_of":       vix.index[-1],
            "invert":      False,
        }])
    except Exception:
        return pd.DataFrame()


# ── Table cell builders (match Regime History style exactly) ──────────────────

_TH = {
    "textAlign": "left", "padding": "5px 10px",
    "fontSize": "0.68rem", "textTransform": "uppercase",
    "letterSpacing": "0.06em", "color": "var(--muted-color)",
    "borderBottom": "1px solid var(--border-color)",
    "whiteSpace": "nowrap",
}
_TD = {
    "padding": "5px 10px", "fontSize": "0.82rem",
    "borderBottom": "1px solid var(--border-color)",
    "color": "var(--font-color)", "verticalAlign": "middle",
}
_TD_MONO = {**_TD, "fontFamily": "monospace"}


def _dash_td() -> html.Td:
    return html.Td("—", style={**_TD_MONO, "textAlign": "center", "color": "#555"})


def _semantic_z_color(z, force: str, invert: bool = False, thresh: float = 0.5) -> str:
    """Semantic color for a signal Z-score bar + text.

    Uses the configured threshold as the neutral zone boundary.
    Interpolates above the threshold from washed-out to vivid.
    """
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return "#666"
    adj_z = -float(z) if invert else float(z)
    if force == "inflation":
        adj_z = -adj_z
    if abs(adj_z) < thresh:
        return "#888"
    magnitude = min((abs(adj_z) - thresh) / max(2.0 * thresh, 0.01), 1.0)
    magnitude = 0.35 + 0.65 * magnitude
    if adj_z > 0:
        return _lerp_rgb(magnitude, _CLR_GREEN_LO, _CLR_GREEN_HI)
    return _lerp_rgb(magnitude, _CLR_RED_LO, _CLR_RED_HI)


def _z_bar_cell(z: Optional[float], color: str) -> html.Td:
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return html.Td("—", style={**_TD_MONO, "color": "#555", "textAlign": "right"})
    bar_w = min(abs(z) / 2.5 * 80, 80)
    return html.Td(
        html.Div(
            style={"display": "flex", "alignItems": "center",
                   "justifyContent": "flex-end", "gap": "6px"},
            children=[
                html.Div(style={
                    "width": f"{bar_w:.0f}px", "height": "6px",
                    "backgroundColor": color, "borderRadius": "2px",
                    "opacity": "0.7", "flexShrink": "0",
                }),
                html.Span(f"{z:+.2f}", style={
                    "color": color, "fontFamily": "monospace", "fontSize": "0.82rem",
                }),
            ],
        ),
        style={**_TD, "textAlign": "right"},
    )


def _momentum_cell(
    direction: Optional[str],
    change_3m: Optional[float],
    positive_dir: str = "rising",
    color: str = _GROWTH_COLOR,
    bad_color: str = "#666",
) -> html.Td:
    if not direction:
        return html.Td(html.Span("—", style={"color": "#555"}), style=_TD)
    arrow    = "↑" if direction == "rising" else "↓"
    fg_color = color if direction == positive_dir else bad_color
    if change_3m is not None and not (isinstance(change_3m, float) and math.isnan(change_3m)):
        content = html.Span([
            html.Span(f"{arrow} {direction}   ", style={"color": fg_color}),
            html.Span(f"{float(change_3m):+.3f} 3m",
                      style={"color": "var(--muted-color)", "fontSize": "0.72rem",
                             "fontFamily": "monospace"}),
        ])
    else:
        content = html.Span(f"{arrow} {direction}",
                            style={"color": fg_color, "fontSize": "0.80rem"})
    return html.Td(content, style=_TD)


def _status_cell(
    is_stale: bool,
    low_history: bool,
    z_missing: bool,
    fill_months: int = 0,
    momentum_mult: float = 1.0,
    decay_fraction: float = 1.0,
) -> html.Td:
    if not z_missing and (is_stale or fill_months > 0):
        content = html.Span([
            html.Span(f"DECAYED · {fill_months}m", style={
                "background": "#7a4a00", "color": "#ffcc80",
                "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.70rem",
            }),
            html.Span(f" · time {decay_fraction:.0%} · momentum {momentum_mult:.1f}×",
                      style={"color": "var(--muted-color)", "fontSize": "0.72rem"}),
        ])
    elif low_history:
        content = html.Span("LOW HISTORY", style={
            "background": "#3a3a00", "color": "#cccc88",
            "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.70rem",
        })
    elif z_missing:
        content = html.Span("BLANK", style={
            "background": "#3a2020", "color": "#cc7777",
            "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.70rem",
        })
    else:
        if momentum_mult > 1.0 + 1e-9:
            lbl, detail = "ACTIVE · BOOSTED",  f" · momentum {momentum_mult:.1f}×"
        elif momentum_mult < 1.0 - 1e-9:
            lbl, detail = "ACTIVE · CONFLICT", f" · momentum {momentum_mult:.1f}×"
        else:
            lbl, detail = "ACTIVE", ""
        content = html.Span([
            html.Span(lbl, style={
                "background": "#1a3a1a", "color": "#88cc88",
                "padding": "1px 5px", "borderRadius": "3px", "fontSize": "0.70rem",
            }),
            html.Span(detail, style={"color": "var(--muted-color)", "fontSize": "0.72rem"}),
        ])
    return html.Td(content, style=_TD)


# ── Row builders ──────────────────────────────────────────────────────────────

def _composite_rows(
    comp_df: pd.DataFrame,
    force: str,
    color: str,
    audit_by_signal: dict,
    thresh: float = 0.5,
) -> tuple[list[html.Tr], int]:
    """Build table rows for a Growth/Inflation composite force (full weight info)."""
    rows: list[html.Tr] = []
    n_active = 0

    for _, sr in comp_df[comp_df["composite"] == force].iterrows():
        sig_id    = str(sr.get("signal_id", ""))
        z         = sr.get("zscore")
        z_missing = z is None or (isinstance(z, float) and math.isnan(z))
        direction = str(sr.get("direction") or "")
        change_3m = sr.get("change_3m")
        invert    = bool(sr.get("invert", False))
        is_stale  = bool(sr.get("is_stale", False))
        low_hist  = bool(sr.get("low_history", False))
        as_of_raw = sr.get("as_of")
        last_str  = pd.Timestamp(as_of_raw).strftime("%b %Y") if pd.notna(as_of_raw) else "—"

        audit          = audit_by_signal.get(sig_id, {})
        if bool(audit.get("missing", False)):
            z_missing = True
        importance     = float(audit.get("importance",          sr.get("importance", 1.0)))
        config_wt      = float(audit.get("config_weight",       sr.get("weight", 0.0)))
        eff_wt         = float(audit.get("effective_weight",    0.0 if z_missing else config_wt))
        momentum_mult  = float(audit.get("momentum_multiplier", 1.0))
        decay_fraction = float(audit.get("decay_fraction",      1.0))
        age_months     = int(round(float(audit.get("age_months", 0.0))))

        if not z_missing:
            n_active += 1

        eff_wt_color = (
            "#E8734C" if eff_wt <= 0
            else (color if eff_wt > config_wt + 1e-9
                  else ("#F4C842" if eff_wt < config_wt - 1e-9 else "var(--font-color)"))
        )
        fill_months  = max(age_months, int(is_stale))
        row_bg       = (
            "rgba(60,20,20,0.12)"
            if z_missing or is_stale or fill_months > 0 or low_hist
            else "transparent"
        )
        # invert flag: signal's "positive" direction is falling, not rising
        positive_dir = "falling" if invert else "rising"

        # Semantic Z-color: green = economically good, red = bad, grey = neutral
        z_color = _semantic_z_color(
            None if z_missing else z, force, invert, thresh=thresh,
        )
        # Momentum arrow: for inflation rising = bad; for all others rising = good
        if force == "inflation":
            mom_good, mom_bad = "#E8734C", "#5CBA8A"
        else:
            mom_good, mom_bad = "#5CBA8A", "#E8734C"

        rows.append(html.Tr(
            style={"backgroundColor": row_bg},
            children=[
                html.Td([
                    _signal_link(str(sr.get("label", sig_id)), sig_id),
                    _signal_info_icon(sig_id),
                ], style=_TD),
                html.Td(f"{importance:.2f}",   style={**_TD_MONO, "textAlign": "center"}),
                html.Td(f"{config_wt*100:.1f}%", style={**_TD_MONO, "textAlign": "center"}),
                html.Td(f"{eff_wt*100:.1f}%", style={
                    **_TD_MONO, "textAlign": "center", "color": eff_wt_color,
                    "fontWeight": "600" if abs(eff_wt - config_wt) > 1e-9 else "400",
                }),
                html.Td(last_str, style={
                    **_TD_MONO, "textAlign": "center",
                    "color": "var(--muted-color)", "fontSize": "0.75rem",
                }),
                _z_bar_cell(None if z_missing else float(z), z_color),
                _momentum_cell(direction, change_3m, positive_dir, mom_good, mom_bad),
                _status_cell(is_stale, low_hist, z_missing,
                             fill_months, momentum_mult, decay_fraction),
            ],
        ))
    return rows, n_active


def _signal_rows(sig_df: pd.DataFrame, color: str) -> tuple[list[html.Tr], int]:
    """Build table rows for a raw-signal force (Rate / Credit / Volatility)."""
    rows: list[html.Tr] = []
    n_active = 0

    for _, sr in sig_df.iterrows():
        sid       = str(sr.get("id", ""))
        label     = str(sr.get("label", None) or _concept_label(sid))
        z         = sr.get("zscore")
        z_missing = z is None or (isinstance(z, float) and math.isnan(z))
        direction = str(sr.get("direction") or "")
        change_3m = sr.get("change_3m")
        is_stale  = bool(sr.get("is_stale", False))
        low_hist  = bool(sr.get("low_history", False))
        as_of_raw = sr.get("as_of")
        last_str  = (
            pd.Timestamp(as_of_raw).strftime("%b %Y")
            if as_of_raw is not None and pd.notna(as_of_raw) else "—"
        )

        if not z_missing:
            n_active += 1

        row_bg = (
            "rgba(60,20,20,0.12)"
            if z_missing or is_stale or low_hist else "transparent"
        )

        rows.append(html.Tr(
            style={"backgroundColor": row_bg},
            children=[
                html.Td([
                    _signal_link(label, sid),
                    _signal_info_icon(sid),
                ], style=_TD),
                _dash_td(),   # Importance — not applicable
                _dash_td(),   # Config Wt  — not applicable
                _dash_td(),   # Eff Wt     — not applicable
                html.Td(last_str, style={
                    **_TD_MONO, "textAlign": "center",
                    "color": "var(--muted-color)", "fontSize": "0.75rem",
                }),
                _z_bar_cell(None if z_missing else float(z), color),
                _momentum_cell(direction, change_3m, "rising", color),
                _status_cell(is_stale, low_hist, z_missing),
            ],
        ))
    return rows, n_active


# ── Section builder ───────────────────────────────────────────────────────────

_COL_HEADER = html.Tr([
    html.Th("Signal",           style=_TH),
    html.Th("Importance",       style={**_TH, "textAlign": "center"}),
    html.Th("Config Wt",        style={**_TH, "textAlign": "center"}),
    html.Th("Eff Wt",           style={**_TH, "textAlign": "center"}),
    html.Th("Last Data",        style={**_TH, "textAlign": "center"}),
    html.Th("Force Z",          style={**_TH, "textAlign": "right"}),
    html.Th("Momentum",         style=_TH),
    html.Th("Status / Detail",  style=_TH),
])


def _build_section(
    name: str,
    color: str,
    force_key: str,
    composite_z: Optional[float],
    momentum_score: Optional[float],
    momentum_arrow: str,
    n_active: int,
    n_total: int,
    data_rows: list[html.Tr],
) -> html.Details:
    z_str     = f"{composite_z:+.2f}" if composite_z is not None and not math.isnan(composite_z) else "—"
    z_color   = _semantic_z_color(composite_z, force_key) if composite_z is not None else "#888"
    mom_str   = f"{momentum_score:.0%}" if momentum_score is not None else "—"
    mom_color = _momentum_score_color(momentum_score, force_key)
    count     = f"{n_active}/{n_total} active" if n_total else "—"

    summary = html.Summary(
        html.Span([
            html.Span(f"{name.upper()} FORCE", style={
                "color": color, "fontWeight": "700",
            }),
            html.Span("  ·  Z ", style={"color": "var(--muted-color)"}),
            html.Span(z_str, style={
                "color": z_color, "fontFamily": "monospace", "fontWeight": "600",
            }),
            html.Span("  ·  Mom ", style={"color": "var(--muted-color)"}),
            html.Span(mom_str, style={
                "color": mom_color, "fontFamily": "monospace", "fontWeight": "600",
            }),
            html.Span(f"  ·  {momentum_arrow}",
                      style={"fontSize": "1.0em"}),
            html.Span(f"  ·  {count}",
                      style={"color": "var(--muted-color)"}),
        ]),
        style={
            "cursor": "pointer",
            "padding": "6px 10px",
            "fontSize": "0.72rem", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.07em",
            "backgroundColor": "rgba(0,0,0,0.18)",
            "borderBottom": "1px solid var(--border-color)",
            "userSelect": "none",
            "listStyle": "none",
            "WebkitAppearance": "none",
        },
    )

    table = html.Div(
        html.Table(
            [html.Thead(_COL_HEADER), html.Tbody(data_rows)],
            style={"width": "100%", "minWidth": "980px", "borderCollapse": "collapse"},
        ),
        style={"overflowX": "auto"},
    )

    return html.Details(
        open=True,
        style={"marginBottom": "6px"},
        children=[summary, table],
    )


# ── Layout ────────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    return html.Div(
        html.Div(id="signals-content"),
        className="pe-2",
        style={"maxWidth": "1600px", "margin": "0 auto"},
    )


# ── Callback ──────────────────────────────────────────────────────────────────

_SIGNALS_INFLATION_WINDOW_COL = {60: "60m", 90: "90m", 120: "120m"}
_SIGNALS_GROWTH_WINDOW_COL   = {36: "36m", 48: "48m", 60: "60m"}


@callback(
    Output("signals-content", "children"),
    [Input("country-store",          "data"),
     Input("page-trigger",           "data"),
     Input("zscore-window-store",    "data"),
     Input("inflation-window-store", "data"),
     Input("regime-threshold-store", "data")],
    prevent_initial_call=False,
)
def render_signals(country_data, page_trigger, zscore_window=0, inflation_window=0, thresholds=None):
    page = (page_trigger or {}).get("page", "")
    if page and page != "/signals":
        return no_update

    country = str(country_data or "US").upper()
    zscore_window    = int(zscore_window    or 0)
    inflation_window = int(inflation_window or 0)

    # ── Composite data (Growth / Inflation) ───────────────────────────────────
    g_sfx = _SIGNALS_GROWTH_WINDOW_COL.get(zscore_window)
    i_sfx = _SIGNALS_INFLATION_WINDOW_COL.get(inflation_window)
    g_zcol = f"zscore_{g_sfx}" if g_sfx else "zscore"
    i_zcol = f"zscore_{i_sfx}" if i_sfx else "zscore"

    comp_df = load_composite_component_status(
        country, g_zscore_col=g_zcol, i_zscore_col=i_zcol,
    )

    g_z = i_z = None
    g_mom = i_mom = None
    rate_z_comp = credit_z_comp = None
    rate_mom_comp = credit_mom_comp = None
    audit_by_signal: dict = {}
    try:
        hist = load_composite_history(country=country)
        if not hist.empty:
            row = hist.iloc[-1]
            # Composite-level Z: use rolling col if available
            g_roll_col = f"growth_score_{g_sfx}" if g_sfx else None
            if g_roll_col and g_roll_col in hist.columns and pd.notna(row.get(g_roll_col)):
                g_z = float(row[g_roll_col])
            else:
                g_z = float(row["growth_score"]) if pd.notna(row.get("growth_score")) else None
            i_roll_col = f"inflation_score_{i_sfx}" if i_sfx else None
            if i_roll_col and i_roll_col in hist.columns and pd.notna(row.get(i_roll_col)):
                i_z = float(row[i_roll_col])
            else:
                i_z = float(row["inflation_score"]) if pd.notna(row.get("inflation_score")) else None
            g_mom = float(row["growth_momentum"])    if pd.notna(row.get("growth_momentum"))    else None
            i_mom = float(row["inflation_momentum"]) if pd.notna(row.get("inflation_momentum")) else None
            # Rate and credit composites — stored from pipeline Pass 5
            if "rate_score" in hist.columns and pd.notna(row.get("rate_score")):
                rate_z_comp = float(row["rate_score"])
            if "credit_score" in hist.columns and pd.notna(row.get("credit_score")):
                credit_z_comp = float(row["credit_score"])
            if "rate_momentum" in hist.columns and pd.notna(row.get("rate_momentum")):
                rate_mom_comp = float(row["rate_momentum"])
            if "credit_momentum" in hist.columns and pd.notna(row.get("credit_momentum")):
                credit_mom_comp = float(row["credit_momentum"])
            wa_raw = row.get("weight_audit")
            if wa_raw:
                raw = json.loads(wa_raw) if isinstance(wa_raw, str) else wa_raw
                for force_dict in raw.values():
                    if isinstance(force_dict, dict):
                        audit_by_signal.update(force_dict)
    except Exception:
        pass

    # ── Raw signal data (Rate / Credit / Volatility) ──────────────────────────
    latest = load_latest_signals(country)
    exc_rate = _RATE_EXCLUDE.get(country, set())

    rate_df   = latest[
        (latest["force"] == "policy") &
        ~latest["id"].apply(_concept).isin(exc_rate)
    ]
    credit_df = latest[latest["force"].isin(["credit", "premium"])]
    vol_df    = _vix_df(country)

    # Use stored composite scores where available; fall back to unweighted mean
    rate_z   = rate_z_comp   if rate_z_comp   is not None else _mean_z(rate_df)
    credit_z = credit_z_comp if credit_z_comp is not None else _mean_z(credit_df)
    vol_z    = _mean_z(vol_df)

    # Use stored momentum fractions where available; fall back to direction fraction
    rate_mom   = rate_mom_comp   if rate_mom_comp   is not None else _direction_fraction(rate_df)
    credit_mom = credit_mom_comp if credit_mom_comp is not None else _direction_fraction(credit_df)
    vol_mom    = _direction_fraction(vol_df)

    # ── Build rows ────────────────────────────────────────────────────────────
    _thresh_z = float((thresholds or {}).get("gz", 0.5))
    g_rows,  g_active  = _composite_rows(comp_df, "growth",    _GROWTH_COLOR,    audit_by_signal, thresh=_thresh_z)
    i_rows,  i_active  = _composite_rows(comp_df, "inflation", _INFLATION_COLOR, audit_by_signal, thresh=_thresh_z)
    r_rows,  r_active  = _composite_rows(comp_df, "rate",      _RATE_COLOR,      audit_by_signal, thresh=_thresh_z)
    cr_rows, cr_active = _composite_rows(comp_df, "credit",    _CREDIT_COLOR,    audit_by_signal, thresh=_thresh_z)
    v_rows,  v_active  = _signal_rows(vol_df,    _VOLATILITY_COLOR)

    g_total  = len(comp_df[comp_df["composite"] == "growth"])
    i_total  = len(comp_df[comp_df["composite"] == "inflation"])
    r_total  = len(comp_df[comp_df["composite"] == "rate"])
    cr_total = len(comp_df[comp_df["composite"] == "credit"])

    # Momentum arrows for Growth/Inflation from composites
    def _comp_arrow(force: str) -> str:
        sub = comp_df[comp_df["composite"] == force]
        if sub.empty:
            return "→"
        return _majority_arrow(sub["direction"].dropna().tolist())

    # ── Sections ──────────────────────────────────────────────────────────────
    last_obs = latest["as_of"].max() if not latest.empty else "—"
    page_header = html.Div([
        html.H5(f"Signals — {country}",
                style={"color": "var(--font-color)", "margin": "0 0 4px 0", "paddingLeft": "4px"}),
        html.Div(f"Latest observation: {last_obs}",
                 style={"color": "var(--muted-color)", "fontSize": "0.75em",
                        "marginBottom": "14px", "paddingLeft": "4px"}),
    ])

    footer = html.Div(
        "Config Wt = normalized base share × importance × quality factor  ·  "
        "Eff Wt = Config Wt × momentum tilt × time-decay  ·  "
        "Volatility signals are not in the composites engine — weight columns show —",
        style={"fontSize": "0.65rem", "color": "#555", "marginTop": "8px", "paddingLeft": "4px"},
    )

    sections = [
        _build_section("Growth",        _GROWTH_COLOR,     "growth",        g_z,      g_mom,      _comp_arrow("growth"),    g_active,  g_total,   g_rows),
        _build_section("Inflation",     _INFLATION_COLOR,  "inflation",     i_z,      i_mom,      _comp_arrow("inflation"), i_active,  i_total,   i_rows),
        _build_section("Interest Rate", _RATE_COLOR,       "rate",          rate_z,   rate_mom,   _comp_arrow("rate"),      r_active,  r_total,   r_rows),
        _build_section("Credit",        _CREDIT_COLOR,     "credit",        credit_z, credit_mom, _comp_arrow("credit"),    cr_active, cr_total,  cr_rows),
        _build_section("Volatility",    _VOLATILITY_COLOR, "volatility",    vol_z,    vol_mom,    _majority_arrow(vol_df["direction"].dropna().tolist() if not vol_df.empty else []), v_active, len(vol_df), v_rows),
    ]

    return html.Div([page_header] + sections + [footer])

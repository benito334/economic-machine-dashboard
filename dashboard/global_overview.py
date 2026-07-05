"""Global Overview — cross-country macro summary table."""
from __future__ import annotations

import os
from copy import deepcopy
from datetime import date
from typing import Any

import duckdb
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from dashboard.themes import DEFAULT_THEME, figure_layout

_DB = os.getenv("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb")

_COUNTRY_NAMES: dict[str, str] = {
    "us": "United States",
    "ez": "Euro Area",
    "jp": "Japan",
    "gb": "United Kingdom",
    "kr": "South Korea",
    "cn": "China",
    "in": "India",
    "br": "Brazil",
    "sa": "Saudi Arabia",
    "ru": "Russia",
    "ca": "Canada",
    "de": "Germany",
    "fr": "France",
    "it": "Italy",
}

_COUNTRY_ORDER = ["us", "ez", "jp", "gb", "kr", "cn", "in", "br", "sa", "ru"]

CYCLE_HEALTH_DEFAULT_CONFIG: dict[str, Any] = {
    "weights": {
        "growth": 0.30,
        "policy_rate": 0.30,
        "inflation": 0.30,
        "public_debt_gap": 0.10,
        "private_debt_gap": 0.05,
    },
    "debt_targets": {
        "public": 70.0,
        "private": 130.0,
    },
    "threshold_mode": "adaptive",
    "threshold_sigma_multiplier": 0.50,
    "positive_threshold": 0.50,
    "negative_threshold": -0.50,
    "freshness_half_life_months": 3.0,
    "apply_freshness_decay": True,
    # 2026-07-05 Ray Dalio review (#22): nominal policy rate is intentional (faster-
    # moving, directly observable, no double-counting since inflation is already its
    # own separate term) — kept as default; this toggle lets users switch to a
    # "realized real policy rate" (nominal minus contemporaneous inflation) for
    # strict consistency with the Rate force elsewhere, which prefers real rates.
    "use_real_policy_rate": False,
}

# 2026-07-05 Ray Dalio review (#21): conditional weight shift replacing the flat
# 0.30/0.30/0.30 growth/rate/inflation split. Applied AFTER the base weights are
# read, only to the CHI weighting (not to the classification thresholds).
_CHI_HIGH_INFLATION_ANN_PCT = 5.0
_CHI_LOW_GROWTH_ANN_PCT = 1.0
_CHI_CONDITIONAL_WEIGHT = 0.35


def _conditional_chi_weights(
    weights: dict[str, float],
    inflation_rate_ann: "float | None",
    growth_rate_ann: "float | None",
) -> dict[str, float]:
    """Tilt growth/rate/inflation CHI weights toward whichever pillar is most active.

    If inflation > 5% annual, inflation gets more weight (0.35). Otherwise, if growth
    < 1% annual, policy rate gets more weight (0.35) since the cost of capital becomes
    the primary lever near the zero lower bound. Otherwise all three stay at 0.30.
    Debt-gap weights are untouched.
    """
    w = dict(weights)
    if inflation_rate_ann is not None and inflation_rate_ann > _CHI_HIGH_INFLATION_ANN_PCT:
        w["inflation"] = _CHI_CONDITIONAL_WEIGHT
    elif growth_rate_ann is not None and growth_rate_ann < _CHI_LOW_GROWTH_ANN_PCT:
        w["policy_rate"] = _CHI_CONDITIONAL_WEIGHT
    return w

# ── Column definitions ──────────────────────────────────────────────────────
# color keys: warn_le, warn_ge → orange   |   high_ge → blue   |   pos_ge, pos_le → green
_COLUMNS: list[dict] = [
    {
        "header": "GDP",
        "sub": "Billion USD",
        "concept": "master.gdp_level_bn",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:,.0f}",
        "color": {"high_ge": 5_000},
    },
    {
        "header": "Growth",
        "sub": "%",
        "concept": "master.gdp_real",
        "multiplier": 100.0,           # decimal → %
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_le": 0.0, "pos_ge": 2.5},
    },
    {
        "header": "Rate",
        "sub": "%",
        "concept": "policy.fed_funds_target",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_ge": 8.0},
    },
    {
        "header": "Inflation",
        "sub": "%",
        "concept": "inflation.cpi_headline",
        "multiplier": 100.0,           # decimal → %
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_ge": 5.0},
    },
    {
        "header": "Jobless",
        "sub": "%",
        "concept": "growth.unemployment",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_ge": 7.0, "pos_le": 3.0},
    },
    {
        "header": "Gov. Budget",
        "sub": "% GDP",
        "concept": "fiscal.budget_balance_gdp",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_le": -6.0, "pos_ge": 0.0},
    },
    {
        "header": "Debt/GDP",
        "sub": "%",
        "concept": "credit.gov_debt_gdp",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"high_ge": 110.0},
    },
    {
        "header": "C/A",
        "sub": "% GDP",
        "concept": "external.current_account_gdp",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_le": -4.0, "pos_ge": 4.0},
    },
    {
        "header": "Population",
        "sub": "Million",
        "concept": "demo.population_total_mn",
        "multiplier": 1e-6,            # persons → millions
        "fmt": lambda v: f"{v:.2f}",
        "color": {"high_ge": 1_000.0},
    },
]

_CYCLE_COMPONENT_CONCEPTS = [
    "master.gdp_real",
    "policy.fed_funds_target",
    "inflation.cpi_headline",
    "credit.gov_debt_gdp",
    "credit.household_debt_gdp",
    "credit.corporate_debt_gdp",
]

_COLUMN_BY_CONCEPT = {c["concept"]: c for c in _COLUMNS}
_CHI_METRICS = {
    "chi_raw": {
        "label": "Cycle Health Index",
        "sub": "raw",
        "fmt": lambda v: f"{v:.2f}",
    },
    "chi_adjusted": {
        "label": "Cycle Health Index",
        "sub": "debt adjusted",
        "fmt": lambda v: f"{v:.2f}",
    },
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def _color_class(value: float, spec: dict) -> str:
    """Return a CSS class name based on threshold spec, or empty string."""
    # Check warn first (takes priority over pos if both defined)
    if spec.get("warn_le") is not None and value <= spec["warn_le"]:
        return "ov-cell-warn"
    if spec.get("warn_ge") is not None and value >= spec["warn_ge"]:
        return "ov-cell-warn"
    if spec.get("high_ge") is not None and value >= spec["high_ge"]:
        return "ov-cell-high"
    if spec.get("pos_ge") is not None and value >= spec["pos_ge"]:
        return "ov-cell-pos"
    if spec.get("pos_le") is not None and value <= spec["pos_le"]:
        return "ov-cell-pos"
    return ""


def _coerce_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if value is None:
        return fallback
    return bool(value)


def _normalise_cycle_config(config: dict | None) -> dict[str, Any]:
    """Merge browser config with defaults and keep thresholds ordered."""
    merged = deepcopy(CYCLE_HEALTH_DEFAULT_CONFIG)
    if isinstance(config, dict):
        weights = config.get("weights")
        if isinstance(weights, dict):
            # Backward compatibility for the first CHI config version.
            if "debt_gap" in weights and "public_debt_gap" not in weights:
                merged["weights"]["public_debt_gap"] = _coerce_float(
                    weights.get("debt_gap"),
                    merged["weights"]["public_debt_gap"] + merged["weights"]["private_debt_gap"],
                )
                merged["weights"]["private_debt_gap"] = 0.0
            for key, default in merged["weights"].items():
                merged["weights"][key] = _coerce_float(weights.get(key), default)
        targets = config.get("debt_targets")
        if isinstance(targets, dict):
            for key, default in merged["debt_targets"].items():
                merged["debt_targets"][key] = _coerce_float(targets.get(key), default)
        elif "debt_target_pct" in config:
            merged["debt_targets"]["public"] = _coerce_float(
                config.get("debt_target_pct"),
                merged["debt_targets"]["public"],
            )
        for key in (
            "positive_threshold",
            "negative_threshold",
            "threshold_sigma_multiplier",
            "freshness_half_life_months",
        ):
            merged[key] = _coerce_float(config.get(key), merged[key])
        mode = str(config.get("threshold_mode", merged["threshold_mode"])).lower()
        merged["threshold_mode"] = mode if mode in {"fixed", "adaptive"} else "adaptive"
        merged["apply_freshness_decay"] = _coerce_bool(
            config.get("apply_freshness_decay"),
            merged["apply_freshness_decay"],
        )
        merged["use_real_policy_rate"] = _coerce_bool(
            config.get("use_real_policy_rate"),
            merged["use_real_policy_rate"],
        )

    if merged["negative_threshold"] >= merged["positive_threshold"]:
        merged["negative_threshold"] = CYCLE_HEALTH_DEFAULT_CONFIG["negative_threshold"]
        merged["positive_threshold"] = CYCLE_HEALTH_DEFAULT_CONFIG["positive_threshold"]
    if merged["threshold_sigma_multiplier"] <= 0:
        merged["threshold_sigma_multiplier"] = CYCLE_HEALTH_DEFAULT_CONFIG["threshold_sigma_multiplier"]
    if merged["freshness_half_life_months"] <= 0:
        merged["freshness_half_life_months"] = CYCLE_HEALTH_DEFAULT_CONFIG["freshness_half_life_months"]
    return merged


def _cycle_config_clipboard_text(config: dict | None = None) -> str:
    cfg = _normalise_cycle_config(config)
    w = cfg["weights"]
    t = cfg["debt_targets"]
    return "\n".join([
        "Cycle Health Index configuration",
        "",
        "Raw formula:",
        "  CHI_raw = Real GDP growth - Policy rate - Inflation",
        "",
        "Debt-adjusted formula:",
        "  CHI_debt_adj = wg*RealGrowth - wr*Policy - wi*Inflation",
        "                 - wp*(PublicDebt/GDP - PublicTarget)",
        "                 - wv*(PrivateDebt/GDP - PrivateTarget)",
        "  PrivateDebt/GDP = average of available household and corporate debt/GDP signals.",
        "  If private debt is unavailable, the private term is omitted.",
        "",
        "Configured settings:",
        f"  Growth weight:      {w['growth']:.4g}",
        f"  Policy-rate weight: {w['policy_rate']:.4g}",
        f"  Inflation weight:   {w['inflation']:.4g}",
        "  (Growth/rate/inflation weights shown are base values — a conditional rule tilts",
        "   one of them to 0.35 at read time: inflation if >5% annual, else policy rate if",
        "   growth <1% annual. See Ray Dalio review 2026-07-05 #21.)",
        f"  Public debt weight: {w['public_debt_gap']:.4g}",
        f"  Private debt weight:{w['private_debt_gap']:.4g}",
        f"  Public debt target (% GDP):  {t['public']:.4g}",
        f"  Private debt target (% GDP): {t['private']:.4g}",
        f"  Threshold mode: {cfg['threshold_mode']}",
        f"  Adaptive threshold multiplier: {cfg['threshold_sigma_multiplier']:.4g} * sigma",
        f"  Fixed positive threshold: {cfg['positive_threshold']:.4g}",
        f"  Fixed negative threshold: {cfg['negative_threshold']:.4g}",
        f"  Freshness decay: {cfg['apply_freshness_decay']}",
        f"  Freshness half-life (months): {cfg['freshness_half_life_months']:.4g}",
        f"  Policy rate basis: {'realized real (nominal - inflation)' if cfg['use_real_policy_rate'] else 'nominal'}",
        "",
        "Stage rule:",
        "  Expansion   if CHI_debt_adj >= positive threshold",
        "  Late/Tight  if CHI_debt_adj <= negative threshold",
        "  Neutral     otherwise",
        "",
        "Data note:",
        "  Raw CHI uses real GDP growth directly to avoid inflation double-counting.",
        "  Adaptive thresholds use the selected country's CHI history standard deviation.",
        "  Component contributions are optionally decayed toward zero as observations age.",
    ])


def _get_component_pct(
    country_data: dict[str, tuple[float, str]],
    concept: str,
    multiplier: float,
) -> tuple[float | None, str | None]:
    if concept not in country_data:
        return None, None
    raw_val, as_of = country_data[concept]
    return raw_val * multiplier, as_of


def _parse_month(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        return pd.to_datetime(str(value)[:10])
    except Exception:
        return None


def _month_age(as_of: str | pd.Timestamp | None, ref: pd.Timestamp | None = None) -> float:
    dt = _parse_month(str(as_of)) if as_of is not None else None
    if dt is None or pd.isna(dt):
        return 0.0
    ref = ref or pd.Timestamp(date.today())
    return max(0.0, (ref.year - dt.year) * 12 + (ref.month - dt.month))


def _freshness(as_of: str | pd.Timestamp | None, cfg: dict[str, Any], ref: pd.Timestamp | None = None) -> float:
    if not cfg.get("apply_freshness_decay", True):
        return 1.0
    half_life = float(cfg.get("freshness_half_life_months", 3.0))
    if half_life <= 0:
        return 1.0
    return float(0.5 ** (_month_age(as_of, ref) / half_life))


def _fresh_value(
    value: float | None,
    as_of: str | pd.Timestamp | None,
    cfg: dict[str, Any],
    ref: pd.Timestamp | None = None,
) -> tuple[float | None, float]:
    if value is None:
        return None, 0.0
    f = _freshness(as_of, cfg, ref)
    return value * f, f


def _private_debt_level(country_data: dict[str, tuple[float, str]]) -> tuple[float | None, str | None, str]:
    parts: list[tuple[float, str]] = []
    for concept in ("credit.household_debt_gdp", "credit.corporate_debt_gdp"):
        val, as_of = _get_component_pct(country_data, concept, 1.0)
        if val is not None and as_of is not None:
            parts.append((val, as_of))
    if not parts:
        return None, None, "missing"
    return sum(v for v, _ in parts) / len(parts), min(d for _, d in parts), "household+corporate"


def _debt_drag(
    public_debt: float | None,
    public_as_of: str | None,
    private_debt: float | None,
    private_as_of: str | None,
    cfg: dict[str, Any],
    ref: pd.Timestamp | None = None,
) -> tuple[float, dict[str, Any]]:
    w = cfg["weights"]
    targets = cfg["debt_targets"]
    public_gap = None if public_debt is None else public_debt - targets["public"]
    private_gap = None if private_debt is None else private_debt - targets["private"]

    public_adj, public_fresh = _fresh_value(public_gap, public_as_of, cfg, ref)
    private_adj, private_fresh = _fresh_value(private_gap, private_as_of, cfg, ref)
    drag = 0.0
    if public_adj is not None:
        drag += w["public_debt_gap"] * public_adj
    if private_adj is not None:
        drag += w["private_debt_gap"] * private_adj
    return drag, {
        "public_gap": public_gap,
        "private_gap": private_gap,
        "public_freshness": public_fresh,
        "private_freshness": private_fresh,
        "debt_mode": "public+private" if private_gap is not None else "public-only",
    }


def _cycle_stage(value: float, thresholds: tuple[float, float]) -> tuple[str, str]:
    neg, pos = thresholds
    if value >= pos:
        return "Expansion", "ov-cell-pos"
    if value <= neg:
        return "Late / Tight", "ov-cell-warn"
    return "Neutral", "ov-cell-high"


def _cycle_health(
    country_data: dict[str, tuple[float, str]],
    config: dict | None = None,
    country_code: str | None = None,
) -> dict[str, Any] | None:
    """Compute simple and debt-adjusted Cycle Health diagnostics.

    CHI v2 uses real GDP growth directly to avoid double-counting inflation,
    then optionally applies age-based confidence decay and public/private debt
    drag in the adjusted version.
    """
    cfg = _normalise_cycle_config(config)
    real_growth, g_date = _get_component_pct(country_data, "master.gdp_real", 100.0)
    inflation, i_date = _get_component_pct(country_data, "inflation.cpi_headline", 100.0)
    policy_rate, r_date = _get_component_pct(country_data, "policy.fed_funds_target", 1.0)
    public_debt, d_date = _get_component_pct(country_data, "credit.gov_debt_gdp", 1.0)
    private_debt, private_date, private_source = _private_debt_level(country_data)

    if real_growth is None or inflation is None or policy_rate is None:
        return None

    if cfg.get("use_real_policy_rate"):
        # Realized real policy rate = nominal rate minus contemporaneous inflation.
        policy_rate = policy_rate - inflation

    ref_dates = [_parse_month(x) for x in [g_date, i_date, r_date, d_date, private_date]]
    ref_dates = [x for x in ref_dates if x is not None]
    ref = max(ref_dates) if ref_dates else pd.Timestamp(date.today())

    g_adj, g_fresh = _fresh_value(real_growth, g_date, cfg, ref)
    r_adj, r_fresh = _fresh_value(policy_rate, r_date, cfg, ref)
    i_adj, i_fresh = _fresh_value(inflation, i_date, cfg, ref)
    if g_adj is None or r_adj is None or i_adj is None:
        return None

    simple = g_adj - r_adj - i_adj
    weights = _conditional_chi_weights(cfg["weights"], inflation_rate_ann=inflation, growth_rate_ann=real_growth)
    debt_drag, debt_meta = _debt_drag(public_debt, d_date, private_debt, private_date, cfg, ref)
    adjusted = (
        weights["growth"] * g_adj
        - weights["policy_rate"] * r_adj
        - weights["inflation"] * i_adj
        - debt_drag
    )
    thresholds = _cycle_thresholds(country_code or "", cfg)
    stage, stage_class = _cycle_stage(adjusted, thresholds)

    dates = [x for x in [g_date, r_date, i_date, d_date, private_date] if x]
    return {
        "simple": simple,
        "adjusted": adjusted,
        "stage": stage,
        "stage_class": stage_class,
        "as_of": min(dates) if dates else "",
        "growth_source": "real",
        "debt_gap": debt_meta["public_gap"],
        "private_debt_gap": debt_meta["private_gap"],
        "private_debt_source": private_source,
        "debt_mode": debt_meta["debt_mode"],
        "thresholds": thresholds,
        "freshness": {
            "growth": g_fresh,
            "policy_rate": r_fresh,
            "inflation": i_fresh,
            "public_debt": debt_meta["public_freshness"],
            "private_debt": debt_meta["private_freshness"],
        },
    }


def _load_data() -> dict[str, dict[str, tuple[float, str]]]:
    """Return {country_code: {concept: (display_value, as_of_str)}}."""
    concepts = sorted({c["concept"] for c in _COLUMNS} | set(_CYCLE_COMPONENT_CONCEPTS))
    like_clauses = " OR ".join(f"id LIKE '%.{concept}'" for concept in concepts)
    try:
        con = duckdb.connect(_DB, read_only=True)
        rows = con.execute(f"""
            SELECT id, value, as_of
            FROM signals
            WHERE ({like_clauses})
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
        """).fetchall()
        con.close()
    except Exception:
        return {}

    result: dict[str, dict[str, tuple[float, str]]] = {}
    for (id_, value, as_of) in rows:
        # id format: "{country}.{force}.{concept_tail}" e.g. "us.master.gdp_level_bn"
        parts = id_.split(".", 1)
        if len(parts) < 2:
            continue
        country, concept = parts[0], parts[1]
        result.setdefault(country, {})[concept] = (float(value), str(as_of)[:7])
    return result


def _clickable_value(
    text: str,
    class_name: str,
    country_code: str,
    metric: str,
    title: str | None = None,
) -> html.Span:
    return html.Span(
        text,
        id={"type": "overview-cell-link", "country": country_code, "metric": metric},
        n_clicks=0,
        className=f"{class_name} ov-cell-link",
        title=title or "Click to view history",
        role="button",
    )


def _make_cycle_cells(
    country_code: str,
    country_data: dict[str, tuple[float, str]],
    config: dict | None = None,
) -> list:
    health = _cycle_health(country_data, config, country_code)
    if health is None:
        return [
            html.Td("—", className="ov-cell-missing"),
            html.Td("—", className="ov-cell-missing"),
            html.Td("—", className="ov-cell-missing"),
        ]

    simple_cls = _color_class(health["simple"], {"warn_le": -0.5, "pos_ge": 0.5})
    adjusted_cls = _color_class(
        health["adjusted"],
        {
            "warn_le": health["thresholds"][0],
            "pos_ge": health["thresholds"][1],
        },
    )
    source = "real GDP"
    debt_note = health.get("debt_mode", "public-only")
    return [
        html.Td(
            [
                _clickable_value(
                    f"{health['simple']:.2f}",
                    simple_cls or "ov-cell-default",
                    country_code,
                    "chi_raw",
                    "Click to view raw Cycle Health history",
                ),
                html.Br(),
                html.Span(source, className="ov-cell-date"),
            ],
            className="ov-cell-num",
            title="Cycle Health = real GDP growth - policy rate - inflation",
        ),
        html.Td(
            [
                _clickable_value(
                    f"{health['adjusted']:.2f}",
                    adjusted_cls or "ov-cell-default",
                    country_code,
                    "chi_adjusted",
                    "Click to view debt-adjusted Cycle Health history",
                ),
                html.Br(),
                html.Span(debt_note, className="ov-cell-date"),
            ],
            className="ov-cell-num",
            title="Weighted Cycle Health includes public/private debt gaps, adaptive thresholds, and freshness decay.",
        ),
        html.Td(
            [
                html.Span(health["stage"], className=health["stage_class"]),
                html.Br(),
                html.Span("weighted", className="ov-cell-date"),
            ],
            className="ov-cell-num",
        ),
    ]


def _make_row(
    country_code: str,
    country_data: dict[str, tuple[float, str]],
    config: dict | None = None,
) -> html.Tr:
    name = _COUNTRY_NAMES.get(country_code, country_code.upper())
    cells: list = [html.Td(name, className="ov-country-name")]

    for col in _COLUMNS:
        concept = col["concept"]
        if concept not in country_data:
            cells.append(html.Td("—", className="ov-cell-missing"))
            continue
        raw_val, as_of = country_data[concept]
        val = raw_val * col["multiplier"]
        text = col["fmt"](val)
        cls = _color_class(val, col["color"])
        cells.append(html.Td(
            [
                _clickable_value(
                    text,
                    cls or "ov-cell-default",
                    country_code,
                    concept,
                    f"Click to view {col['header']} history",
                ),
                html.Br(),
                html.Span(as_of, className="ov-cell-date"),
            ],
            className="ov-cell-num",
        ))
    cells.extend(_make_cycle_cells(country_code, country_data, config))
    return html.Tr(cells, className="ov-row")


def _read_signal_history(country_code: str, concept: str, multiplier: float = 1.0) -> pd.DataFrame:
    signal_id = f"{country_code}.{concept}"
    try:
        con = duckdb.connect(_DB, read_only=True)
        df = con.execute(
            "SELECT as_of, value FROM signals WHERE id = ? ORDER BY as_of",
            [signal_id],
        ).df()
        con.close()
    except Exception:
        return pd.DataFrame(columns=["as_of", "value"])
    if df.empty:
        return pd.DataFrame(columns=["as_of", "value"])
    df["as_of"] = pd.to_datetime(df["as_of"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce") * multiplier
    return df.dropna(subset=["value"]).sort_values("as_of")


def _component_series(country_code: str, concept: str, multiplier: float) -> pd.Series:
    df = _read_signal_history(country_code, concept, multiplier)
    if df.empty:
        return pd.Series(dtype=float)
    month = df["as_of"].dt.to_period("M").dt.to_timestamp()
    s = pd.Series(df["value"].to_numpy(), index=month).sort_index()
    return s.groupby(level=0).last()


def _component_monthly_frame(
    country_code: str,
    concept: str,
    multiplier: float,
    idx: pd.DatetimeIndex,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    df = _read_signal_history(country_code, concept, multiplier)
    if df.empty:
        return pd.DataFrame(index=idx, columns=["value", "freshness"])
    month = df["as_of"].dt.to_period("M").dt.to_timestamp()
    value = pd.Series(df["value"].to_numpy(), index=month).sort_index().groupby(level=0).last()
    source_month = pd.Series(month.to_numpy(), index=month).sort_index().groupby(level=0).last()
    aligned = pd.DataFrame({
        "value": value.reindex(idx).ffill(),
        "source_month": source_month.reindex(idx).ffill(),
    }, index=idx)
    if not cfg.get("apply_freshness_decay", True):
        aligned["freshness"] = 1.0
    else:
        half_life = float(cfg.get("freshness_half_life_months", 3.0))
        ages = [
            max(0, (dt.year - src.year) * 12 + (dt.month - src.month))
            if pd.notna(src) else float("nan")
            for dt, src in zip(aligned.index, aligned["source_month"])
        ]
        aligned["freshness"] = [0.5 ** (age / half_life) if pd.notna(age) else float("nan") for age in ages]
    aligned["adjusted"] = aligned["value"] * aligned["freshness"]
    return aligned


def _cycle_health_history(country_code: str, config: dict | None = None) -> pd.DataFrame:
    cfg = _normalise_cycle_config(config)
    base_series = [
        _component_series(country_code, "master.gdp_real", 100.0),
        _component_series(country_code, "inflation.cpi_headline", 100.0),
        _component_series(country_code, "policy.fed_funds_target", 1.0),
    ]
    if any(s.empty for s in base_series):
        return pd.DataFrame(columns=["as_of", "chi_raw", "chi_adjusted"])

    optional_series = [
        _component_series(country_code, "credit.gov_debt_gdp", 1.0),
        _component_series(country_code, "credit.household_debt_gdp", 1.0),
        _component_series(country_code, "credit.corporate_debt_gdp", 1.0),
    ]
    all_series = [s for s in base_series + optional_series if not s.empty]
    if not all_series:
        return pd.DataFrame(columns=["as_of", "chi_raw", "chi_adjusted"])

    min_dt = min(s.index.min() for s in all_series)
    max_dt = max(s.index.max() for s in all_series)
    idx = pd.date_range(min_dt, max_dt, freq="MS")

    real = _component_monthly_frame(country_code, "master.gdp_real", 100.0, idx, cfg)
    inflation = _component_monthly_frame(country_code, "inflation.cpi_headline", 100.0, idx, cfg)
    policy = _component_monthly_frame(country_code, "policy.fed_funds_target", 1.0, idx, cfg)
    public_debt = _component_monthly_frame(country_code, "credit.gov_debt_gdp", 1.0, idx, cfg)
    household_debt = _component_monthly_frame(country_code, "credit.household_debt_gdp", 1.0, idx, cfg)
    corporate_debt = _component_monthly_frame(country_code, "credit.corporate_debt_gdp", 1.0, idx, cfg)

    aligned = pd.DataFrame({
        "real_growth": real["adjusted"],
        "inflation": inflation["adjusted"],
        "policy_rate": policy["adjusted"],
        "real_growth_raw": real["value"],
        "inflation_raw": inflation["value"],
        "policy_rate_raw": policy["value"],
        "public_debt_gap": (public_debt["value"] - cfg["debt_targets"]["public"]) * public_debt["freshness"],
        "public_debt_raw": public_debt["value"],
        "growth_freshness": real["freshness"],
        "inflation_freshness": inflation["freshness"],
        "policy_freshness": policy["freshness"],
        "public_debt_freshness": public_debt["freshness"],
    }, index=idx)

    private_raw = pd.concat(
        [household_debt["value"], corporate_debt["value"]],
        axis=1,
    ).mean(axis=1, skipna=True)
    private_fresh = pd.concat(
        [household_debt["freshness"], corporate_debt["freshness"]],
        axis=1,
    ).mean(axis=1, skipna=True)
    aligned["private_debt_gap"] = (private_raw - cfg["debt_targets"]["private"]) * private_fresh
    aligned["private_debt_raw"] = private_raw
    aligned["private_debt_freshness"] = private_fresh
    aligned = aligned.dropna(subset=["real_growth", "inflation", "policy_rate"])
    if aligned.empty:
        return pd.DataFrame(columns=["as_of", "chi_raw", "chi_adjusted"])

    aligned["chi_raw"] = (
        aligned["real_growth"]
        - aligned["policy_rate"]
        - aligned["inflation"]
    )
    w = cfg["weights"]
    aligned["chi_adjusted"] = (
        w["growth"] * aligned["real_growth"]
        - w["policy_rate"] * aligned["policy_rate"]
        - w["inflation"] * aligned["inflation"]
        - w["public_debt_gap"] * aligned["public_debt_gap"].fillna(0.0)
        - w["private_debt_gap"] * aligned["private_debt_gap"].fillna(0.0)
    )
    aligned["debt_mode"] = aligned["private_debt_raw"].notna().map(
        {True: "public+private", False: "public-only"}
    )
    return aligned.reset_index(names="as_of")


def _cycle_thresholds(country_code: str, cfg: dict[str, Any]) -> tuple[float, float]:
    if cfg.get("threshold_mode") != "adaptive" or not country_code:
        return float(cfg["negative_threshold"]), float(cfg["positive_threshold"])
    hist = _cycle_health_history(country_code, {**cfg, "threshold_mode": "fixed"})
    if hist.empty or "chi_adjusted" not in hist:
        return float(cfg["negative_threshold"]), float(cfg["positive_threshold"])
    sigma = float(hist["chi_adjusted"].dropna().std())
    if not pd.notna(sigma) or sigma <= 0:
        return float(cfg["negative_threshold"]), float(cfg["positive_threshold"])
    val = float(cfg["threshold_sigma_multiplier"]) * sigma
    return -val, val


def _empty_figure(message: str, theme_name: str = DEFAULT_THEME) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**figure_layout(theme_name, message), height=430)
    return fig


def _metric_title(country_code: str, metric: str) -> str:
    country = _COUNTRY_NAMES.get(country_code, country_code.upper())
    if metric in _CHI_METRICS:
        m = _CHI_METRICS[metric]
        return f"{country} · {m['label']} ({m['sub']})"
    col = _COLUMN_BY_CONCEPT.get(metric)
    if col:
        return f"{country} · {col['header']} ({col['sub']})"
    return f"{country} · {metric}"


def _overview_drill_figure(
    country_code: str,
    metric: str,
    config: dict | None = None,
    theme_name: str = DEFAULT_THEME,
) -> go.Figure:
    if metric in _CHI_METRICS:
        hist = _cycle_health_history(country_code, config)
        value_col = metric
        fmt = _CHI_METRICS[metric]["fmt"]
    else:
        col = _COLUMN_BY_CONCEPT.get(metric)
        if not col:
            return _empty_figure("Unknown Overview metric", theme_name)
        hist = _read_signal_history(country_code, metric, col["multiplier"])
        value_col = "value"
        fmt = col["fmt"]

    if hist.empty or value_col not in hist:
        return _empty_figure("No history available", theme_name)

    hover_vals = [fmt(float(v)) for v in hist[value_col]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist["as_of"],
        y=hist[value_col],
        mode="lines",
        line={"color": "#E8A317", "width": 2},
        hovertemplate="%{x|%Y-%m-%d}<br>%{customdata}<extra></extra>",
        customdata=hover_vals,
        name=_metric_title(country_code, metric),
    ))
    fig.update_layout(**figure_layout(theme_name))
    fig.update_layout(
        height=430,
        hovermode="x unified",
        margin={"l": 48, "r": 20, "t": 24, "b": 40},
        uirevision=f"overview-{country_code}-{metric}",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.18)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.18)", tickformat=",.2f")
    if metric == "chi_adjusted":
        cfg = _normalise_cycle_config(config)
        neg, pos = _cycle_thresholds(country_code, cfg)
        fig.add_hline(y=pos, line_dash="dot", line_color="#5CB85C", opacity=0.65)
        fig.add_hline(y=neg, line_dash="dot", line_color="#E8734C", opacity=0.65)
    elif metric == "chi_raw":
        fig.add_hline(y=0, line_dash="dot", line_color="#9AA4B2", opacity=0.6)
    return fig


# ── Layout ──────────────────────────────────────────────────────────────────

def _build_table(config: dict | None = None) -> html.Table:
    data = _load_data()
    # Show countries in rollout order; append any extras
    country_codes = [c for c in _COUNTRY_ORDER if c in data]
    for c in sorted(data):
        if c not in country_codes:
            country_codes.append(c)

    header = html.Tr([
        html.Th("Country", className="ov-th-country"),
        *[
            html.Th(
                [html.Div(col["header"]), html.Div(col["sub"], className="ov-th-sub")],
                className="ov-th-num",
            )
            for col in _COLUMNS
        ],
        html.Th([html.Div("CHI"), html.Div("raw", className="ov-th-sub")], className="ov-th-num", title="Cycle Health Index"),
        html.Th([html.Div("CHI"), html.Div("debt adj.", className="ov-th-sub")], className="ov-th-num", title="Debt-adjusted Cycle Health Index"),
        html.Th([html.Div("Stage"), html.Div("weighted", className="ov-th-sub")], className="ov-th-num", title="Weighted Cycle Stage"),
    ])

    return html.Table(
        [html.Thead(header), html.Tbody([_make_row(c, data[c], config) for c in country_codes])],
        className="ov-table",
    )


def _cycle_config_modal() -> dbc.Modal:
    def row(label: str, input_id: str, value: float, step: float = 0.05) -> html.Div:
        return html.Div([
            html.Label(label, className="ov-config-label"),
            dcc.Input(
                id=input_id,
                type="number",
                value=value,
                step=step,
                className="ov-config-input",
            ),
        ], className="ov-config-row")

    cfg = _normalise_cycle_config(None)
    w = cfg["weights"]
    targets = cfg["debt_targets"]
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Cycle Health Config"), close_button=True),
            dbc.ModalBody([
                html.Div([
                    row("Growth weight", "chi-weight-growth", w["growth"]),
                    row("Policy-rate weight", "chi-weight-rate", w["policy_rate"]),
                    row("Inflation weight", "chi-weight-inflation", w["inflation"]),
                    row("Public-debt weight", "chi-weight-public-debt", w["public_debt_gap"]),
                    row("Private-debt weight", "chi-weight-private-debt", w["private_debt_gap"]),
                    row("Public debt target (% GDP)", "chi-public-debt-target", targets["public"], 1.0),
                    row("Private debt target (% GDP)", "chi-private-debt-target", targets["private"], 1.0),
                    html.Div([
                        html.Label("Threshold mode", className="ov-config-label"),
                        dcc.Dropdown(
                            id="chi-threshold-mode",
                            options=[
                                {"label": "Adaptive (k × history σ)", "value": "adaptive"},
                                {"label": "Fixed", "value": "fixed"},
                            ],
                            value=cfg["threshold_mode"],
                            clearable=False,
                            className="ov-config-dropdown",
                        ),
                    ], className="ov-config-row"),
                    row("Adaptive k × σ", "chi-threshold-k", cfg["threshold_sigma_multiplier"], 0.05),
                    row("Positive threshold", "chi-positive-threshold", cfg["positive_threshold"], 0.10),
                    row("Negative threshold", "chi-negative-threshold", cfg["negative_threshold"], 0.10),
                    row("Freshness half-life (months)", "chi-freshness-half-life", cfg["freshness_half_life_months"], 0.5),
                    html.Div([
                        html.Label("Freshness decay", className="ov-config-label"),
                        dcc.Dropdown(
                            id="chi-freshness-enabled",
                            options=[
                                {"label": "On", "value": "true"},
                                {"label": "Off", "value": "false"},
                            ],
                            value="true" if cfg["apply_freshness_decay"] else "false",
                            clearable=False,
                            className="ov-config-dropdown",
                        ),
                    ], className="ov-config-row"),
                ], className="ov-config-grid"),
                html.Div(
                    "Raw CHI = real growth - policy - inflation. Debt-adjusted CHI uses public/private "
                    "debt gaps, optional freshness decay, and fixed or adaptive thresholds. Settings are stored in this browser.",
                    className="ov-config-note",
                ),
            ]),
            dbc.ModalFooter([
                dcc.Clipboard(
                    id="chi-copy-btn",
                    title="Copy configured settings",
                    style={
                        "cursor": "pointer",
                        "color": "var(--muted-color)",
                        "fontSize": "0.85rem",
                        "opacity": "0.75",
                        "marginRight": "auto",
                    },
                ),
                dbc.Button("Reset Defaults", id="chi-reset-btn", color="secondary", outline=True, size="sm"),
                dbc.Button("Apply", id="chi-apply-btn", color="primary", size="sm"),
            ]),
        ],
        id="cycle-health-config-modal",
        is_open=False,
        size="md",
    )


def _overview_drill_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(id="overview-drill-title"),
                close_button=True,
            ),
            dbc.ModalBody(
                dcc.Graph(
                    id="overview-drill-chart",
                    config={"displayModeBar": True},
                    style={"height": "450px"},
                ),
                style={"padding": "8px 14px 14px"},
            ),
            dbc.ModalFooter(
                dbc.Button("Close", id="overview-drill-close", color="secondary", size="sm")
            ),
        ],
        id="overview-drill-modal",
        is_open=False,
        size="lg",
    )


def get_layout() -> html.Div:
    table = _build_table()

    legend = html.Div([
        html.Span("■ ", style={"color": "#E8853A", "fontSize": "0.9rem"}),
        html.Span("Elevated / Concerning  ", className="ov-legend-label"),
        html.Span("■ ", style={"color": "#4C9BE8", "fontSize": "0.9rem"}),
        html.Span("Notable / High  ", className="ov-legend-label"),
        html.Span("■ ", style={"color": "#5CB85C", "fontSize": "0.9rem"}),
        html.Span("Positive / Favourable", className="ov-legend-label"),
    ], style={"marginTop": "14px", "paddingLeft": "2px"})

    return html.Div([
        dcc.Store(
            id="cycle-health-config-store",
            data=_normalise_cycle_config(None),
            storage_type="local",
        ),
        _cycle_config_modal(),
        _overview_drill_modal(),
        html.Div([
            html.Div([
                html.H4("Global Overview", style={"marginBottom": "2px", "fontSize": "1.1rem"}),
                html.P(
                    "Latest available value per country. Dates below each figure show the most recent observation in the database.",
                    style={"color": "var(--muted-color)", "fontSize": "0.74rem", "marginBottom": "0"},
                ),
            ]),
            html.Button(
                "Cycle Health Config",
                id="cycle-health-config-btn",
                className="btn btn-sm btn-warning",
                style={"fontWeight": "700", "whiteSpace": "nowrap"},
            ),
        ], className="pt-3", style={"display": "flex", "justifyContent": "space-between", "gap": "16px", "alignItems": "flex-start", "marginBottom": "16px"}),
        html.Div(table, id="overview-table-wrap", style={"overflowX": "auto"}),
        legend,
    ], className="pe-2", style={"maxWidth": "none", "margin": "0 auto"})


def register_callbacks(app) -> None:
    @app.callback(
        Output("overview-table-wrap", "children"),
        Input("cycle-health-config-store", "data"),
        prevent_initial_call=False,
    )
    def render_overview_table(config: dict | None):
        return _build_table(config)

    @app.callback(
        Output("cycle-health-config-modal", "is_open"),
        [Input("cycle-health-config-btn", "n_clicks"),
         Input("chi-apply-btn", "n_clicks"),
         Input("chi-reset-btn", "n_clicks")],
        State("cycle-health-config-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_cycle_modal(n_open: int, n_apply: int, n_reset: int, is_open: bool) -> bool:
        if ctx.triggered_id == "cycle-health-config-btn" and (n_open or 0) > 0:
            return True
        if ctx.triggered_id in {"chi-apply-btn", "chi-reset-btn"}:
            return False
        return bool(is_open)

    @app.callback(
        Output("cycle-health-config-store", "data"),
        [Input("chi-apply-btn", "n_clicks"),
         Input("chi-reset-btn", "n_clicks")],
        [State("chi-weight-growth", "value"),
         State("chi-weight-rate", "value"),
         State("chi-weight-inflation", "value"),
         State("chi-weight-public-debt", "value"),
         State("chi-weight-private-debt", "value"),
         State("chi-public-debt-target", "value"),
         State("chi-private-debt-target", "value"),
         State("chi-threshold-mode", "value"),
         State("chi-threshold-k", "value"),
         State("chi-positive-threshold", "value"),
         State("chi-negative-threshold", "value"),
         State("chi-freshness-half-life", "value"),
         State("chi-freshness-enabled", "value"),
         State("cycle-health-config-store", "data")],
        prevent_initial_call=True,
    )
    def save_cycle_config(
        n_apply: int,
        n_reset: int,
        wg: float,
        wr: float,
        wi: float,
        wpub: float,
        wpriv: float,
        pub_target: float,
        priv_target: float,
        thresh_mode: str,
        thresh_k: float,
        pos_thresh: float,
        neg_thresh: float,
        freshness_half_life: float,
        freshness_enabled: str,
        stored: dict | None,
    ):
        if ctx.triggered_id == "chi-reset-btn":
            return _normalise_cycle_config(None)
        if ctx.triggered_id != "chi-apply-btn":
            return no_update
        current = _normalise_cycle_config(stored)
        return _normalise_cycle_config({
            "weights": {
                "growth": _coerce_float(wg, current["weights"]["growth"]),
                "policy_rate": _coerce_float(wr, current["weights"]["policy_rate"]),
                "inflation": _coerce_float(wi, current["weights"]["inflation"]),
                "public_debt_gap": _coerce_float(wpub, current["weights"]["public_debt_gap"]),
                "private_debt_gap": _coerce_float(wpriv, current["weights"]["private_debt_gap"]),
            },
            "debt_targets": {
                "public": _coerce_float(pub_target, current["debt_targets"]["public"]),
                "private": _coerce_float(priv_target, current["debt_targets"]["private"]),
            },
            "threshold_mode": thresh_mode or current["threshold_mode"],
            "threshold_sigma_multiplier": _coerce_float(thresh_k, current["threshold_sigma_multiplier"]),
            "positive_threshold": _coerce_float(pos_thresh, current["positive_threshold"]),
            "negative_threshold": _coerce_float(neg_thresh, current["negative_threshold"]),
            "freshness_half_life_months": _coerce_float(
                freshness_half_life,
                current["freshness_half_life_months"],
            ),
            "apply_freshness_decay": freshness_enabled == "true",
        })

    @app.callback(
        [Output("chi-weight-growth", "value"),
         Output("chi-weight-rate", "value"),
         Output("chi-weight-inflation", "value"),
         Output("chi-weight-public-debt", "value"),
         Output("chi-weight-private-debt", "value"),
         Output("chi-public-debt-target", "value"),
         Output("chi-private-debt-target", "value"),
         Output("chi-threshold-mode", "value"),
         Output("chi-threshold-k", "value"),
         Output("chi-positive-threshold", "value"),
         Output("chi-negative-threshold", "value"),
         Output("chi-freshness-half-life", "value"),
         Output("chi-freshness-enabled", "value")],
        Input("cycle-health-config-modal", "is_open"),
        State("cycle-health-config-store", "data"),
        prevent_initial_call=True,
    )
    def sync_cycle_inputs(is_open: bool, stored: dict | None):
        if not is_open:
            raise PreventUpdate
        cfg = _normalise_cycle_config(stored)
        return (
            cfg["weights"]["growth"],
            cfg["weights"]["policy_rate"],
            cfg["weights"]["inflation"],
            cfg["weights"]["public_debt_gap"],
            cfg["weights"]["private_debt_gap"],
            cfg["debt_targets"]["public"],
            cfg["debt_targets"]["private"],
            cfg["threshold_mode"],
            cfg["threshold_sigma_multiplier"],
            cfg["positive_threshold"],
            cfg["negative_threshold"],
            cfg["freshness_half_life_months"],
            "true" if cfg["apply_freshness_decay"] else "false",
        )

    @app.callback(
        Output("chi-copy-btn", "content"),
        [Input("chi-weight-growth", "value"),
         Input("chi-weight-rate", "value"),
         Input("chi-weight-inflation", "value"),
         Input("chi-weight-public-debt", "value"),
         Input("chi-weight-private-debt", "value"),
         Input("chi-public-debt-target", "value"),
         Input("chi-private-debt-target", "value"),
         Input("chi-threshold-mode", "value"),
         Input("chi-threshold-k", "value"),
         Input("chi-positive-threshold", "value"),
         Input("chi-negative-threshold", "value"),
         Input("chi-freshness-half-life", "value"),
         Input("chi-freshness-enabled", "value")],
        State("cycle-health-config-store", "data"),
        prevent_initial_call=False,
    )
    def update_cycle_clipboard(
        wg: float,
        wr: float,
        wi: float,
        wpub: float,
        wpriv: float,
        pub_target: float,
        priv_target: float,
        thresh_mode: str,
        thresh_k: float,
        pos_thresh: float,
        neg_thresh: float,
        freshness_half_life: float,
        freshness_enabled: str,
        stored: dict | None,
    ) -> str:
        current = _normalise_cycle_config(stored)
        cfg = {
            "weights": {
                "growth": _coerce_float(wg, current["weights"]["growth"]),
                "policy_rate": _coerce_float(wr, current["weights"]["policy_rate"]),
                "inflation": _coerce_float(wi, current["weights"]["inflation"]),
                "public_debt_gap": _coerce_float(wpub, current["weights"]["public_debt_gap"]),
                "private_debt_gap": _coerce_float(wpriv, current["weights"]["private_debt_gap"]),
            },
            "debt_targets": {
                "public": _coerce_float(pub_target, current["debt_targets"]["public"]),
                "private": _coerce_float(priv_target, current["debt_targets"]["private"]),
            },
            "threshold_mode": thresh_mode or current["threshold_mode"],
            "threshold_sigma_multiplier": _coerce_float(thresh_k, current["threshold_sigma_multiplier"]),
            "positive_threshold": _coerce_float(pos_thresh, current["positive_threshold"]),
            "negative_threshold": _coerce_float(neg_thresh, current["negative_threshold"]),
            "freshness_half_life_months": _coerce_float(
                freshness_half_life,
                current["freshness_half_life_months"],
            ),
            "apply_freshness_decay": freshness_enabled == "true",
        }
        return _cycle_config_clipboard_text(cfg)

    @app.callback(
        [Output("overview-drill-modal", "is_open"),
         Output("overview-drill-title", "children"),
         Output("overview-drill-chart", "figure")],
        [Input({"type": "overview-cell-link", "country": ALL, "metric": ALL}, "n_clicks"),
         Input("overview-drill-close", "n_clicks")],
        [State("cycle-health-config-store", "data"),
         State("theme-store", "data"),
         State("overview-drill-modal", "is_open")],
        prevent_initial_call=True,
    )
    def open_overview_drill(
        clicks: list[int],
        close_clicks: int,
        config: dict | None,
        theme_name: str | None,
        is_open: bool,
    ):
        if ctx.triggered_id == "overview-drill-close":
            return False, no_update, no_update
        trig = ctx.triggered_id
        if not isinstance(trig, dict):
            raise PreventUpdate
        if not clicks or not any((c or 0) > 0 for c in clicks):
            raise PreventUpdate
        country = str(trig.get("country", "")).lower()
        metric = str(trig.get("metric", ""))
        if not country or not metric:
            raise PreventUpdate
        theme_name = theme_name or DEFAULT_THEME
        return (
            True,
            _metric_title(country, metric),
            _overview_drill_figure(country, metric, config, theme_name),
        )

"""
Phase 1B composites engine.

Computes Growth Score, Inflation Score, Regime Quadrant (+Confidence),
and Disequilibrium Score from signals stored in DuckDB.

Entry point:  compute_composite_history(conn, country, config)
              → list[CompositeSnapshot], ready for upsert_composites().
"""
from __future__ import annotations

import logging
import json
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from indicators.normalize import ZSCORE_CAP_SIGMA

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "config"

_QUADRANT_LABELS: dict[tuple[bool, bool], str] = {
    (True,  True):  "Inflationary Boom",
    (True,  False): "Expansion",
    (False, True):  "Stagflation",
    (False, False): "Disinflationary Slowdown",
}

# Expected 3-month momentum direction per (growth_up, inflation_up) pair
_EXPECTED_DIR: dict[tuple[bool, bool], tuple[str, str]] = {
    (True,  True):  ("rising",  "rising"),
    (True,  False): ("rising",  "falling"),
    (False, True):  ("falling", "rising"),
    (False, False): ("falling", "falling"),
}


_POLICY_YAML = _CONFIG_DIR / "composites_policy.yaml"
_COUNTRIES_DIR = _CONFIG_DIR / "countries"


def _load_policy(path: Path | None = None) -> dict:
    p = path or _POLICY_YAML
    with open(p) as f:
        return yaml.safe_load(f) or {}


def _load_country_composites(country: str, path: Path | None = None) -> dict:
    """Load {cc}_composites.yaml for the given country.  Errors loudly if missing."""
    if path is not None:
        p = path
    else:
        cc = country.lower()
        p = _COUNTRIES_DIR / f"{cc}_composites.yaml"
    if not p.exists():
        raise FileNotFoundError(
            f"No composites file for country '{country}': expected {p}. "
            "Create config/countries/{cc}_composites.yaml with growth_score and inflation_score indicator lists."
        )
    with open(p) as f:
        return yaml.safe_load(f) or {}


def load_composites_config(
    country: str = "US",
    policy_path: Path | None = None,
    country_path: Path | None = None,
) -> dict:
    """Return merged methodology policy + country indicator lists as one dict.

    Loads config/composites_policy.yaml (global methodology) and
    config/countries/{cc}_composites.yaml (country-specific indicator lists),
    then merges them into the single dict shape expected by compute_composite_history.
    """
    policy = _load_policy(policy_path)
    country_cfg = _load_country_composites(country, country_path)
    merged = {**policy, **country_cfg}
    _validate_weighting_config(merged)
    return merged


def _validate_weighting_config(config: dict) -> None:
    """Fail fast on invalid tunable importance/quality and dynamic-weight settings."""
    for section in ("growth_score", "inflation_score"):
        indicators = config.get(section, {}).get("indicators", [])
        for ind in indicators:
            for key in ("importance", "quality_factor"):
                if key in ind and not 0 <= float(ind[key]) <= 1:
                    raise ValueError(f"{section}.{ind.get('id')}.{key} must be in [0, 1]")
            if "base_share" in ind and float(ind["base_share"]) < 0:
                raise ValueError(f"{section}.{ind.get('id')}.base_share must be >= 0")

    dynamic = config.get("dynamic_weighting", {})
    if float(dynamic.get("momentum_alpha", 0.5)) < 0:
        raise ValueError("dynamic_weighting.momentum_alpha must be >= 0")
    min_mult = float(dynamic.get("min_multiplier", 0.1))
    max_mult = float(dynamic.get("max_multiplier", 1.5))
    if min_mult < 0 or max_mult < min_mult:
        raise ValueError("dynamic_weighting multipliers must satisfy 0 <= min <= max")

    decay = config.get("time_decay", {})
    if decay and float(decay.get("half_life_months", 3.0)) <= 0:
        raise ValueError("time_decay.half_life_months must be > 0")


def normalized_nominal_weights(indicators: list[dict]) -> dict[str, float]:
    """Return config weights normalized to 1.0 for one force basket.

    New configs use ``base_share × importance × quality_factor``. Legacy configs
    containing only ``weight`` remain supported for tests and downstream users.
    """
    raw: dict[str, float] = {}
    for ind in indicators:
        if any(key in ind for key in ("base_share", "importance", "quality_factor")):
            value = (
                float(ind.get("base_share", 1.0))
                * float(ind.get("importance", 1.0))
                * float(ind.get("quality_factor", 1.0))
            )
        else:
            value = float(ind.get("weight", 1.0))
        raw[ind["id"]] = max(0.0, value)
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("Composite nominal weights must sum to more than zero")
    return {signal_id: value / total for signal_id, value in raw.items()}


def momentum_weight_multiplier(
    force_z: float,
    direction: object,
    *,
    invert: bool = False,
    alpha: float = 0.5,
    min_multiplier: float = 0.1,
    max_multiplier: float = 1.5,
    zero_epsilon: float = 0.05,
) -> float:
    """Apply the guidance's force/momentum agreement tilt."""
    adjusted_z = -float(force_z) if invert else float(force_z)
    force_sign = 0 if abs(adjusted_z) < zero_epsilon else (1 if adjusted_z > 0 else -1)
    if direction == "rising":
        momentum_sign = 1
    elif direction == "falling":
        momentum_sign = -1
    else:
        momentum_sign = 0
    if invert:
        momentum_sign *= -1
    multiplier = 1.0 + alpha * force_sign * momentum_sign
    return float(np.clip(multiplier, min_multiplier, max_multiplier))


def age_weight_fraction(age_months: float, half_life_months: float = 3.0) -> float:
    """Exponential time decay: a signal loses half its weight each half-life."""
    age = max(0.0, float(age_months))
    if half_life_months <= 0:
        raise ValueError("half_life_months must be > 0")
    return float(0.5 ** (age / float(half_life_months)))


# ── Weight audit helpers ──────────────────────────────────────────────────────

def _log_force_balance(country: str, growth_cfg: list[dict], inflation_cfg: list[dict]) -> None:
    """Log the pre-normalization weight mass for growth vs inflation baskets.

    Fires a WARNING when one basket outweighs the other by >33% (ratio outside
    0.75–1.33). This catches cases where adding new signals tilts the composite
    toward one regime type without a matching addition on the other side.

    Runs once per country per pipeline pass — zero DB access needed.
    """
    def _basket_mass(indicators: list[dict]) -> float:
        return sum(
            float(ind.get("base_share", 1.0))
            * float(ind.get("importance", 1.0))
            * float(ind.get("quality_factor", 1.0))
            for ind in indicators
        )

    g_mass = _basket_mass(growth_cfg)
    i_mass = _basket_mass(inflation_cfg)
    ratio = g_mass / i_mass if i_mass > 0 else float("inf")
    balanced = 0.75 <= ratio <= 1.33

    if balanced:
        logger.info(
            "[BALANCE] %s  G_mass=%.3f  I_mass=%.3f  ratio=%.2f  OK",
            country, g_mass, i_mass, ratio,
        )
    else:
        heavier = "inflation" if ratio < 1.0 else "growth"
        logger.warning(
            "[BALANCE] %s  G_mass=%.3f  I_mass=%.3f  ratio=%.2f  "
            "WARN — %s basket is disproportionately heavier. "
            "Adjust base_share/importance or add signals on the lighter side.",
            country, g_mass, i_mass, ratio, heavier,
        )


def audit_signal_correlations(
    conn,
    country: str,
    config: dict,
    threshold: float = 0.80,
    min_periods: int = 36,
) -> list[dict]:
    """Compute pairwise Z-score correlations across all composite signals for a country.

    Logs and returns pairs with |r| >= threshold. High within-basket correlation
    signals redundancy — the weaker signal's importance should be reduced
    (anti-redundancy rule: secondary importance ≤ 40% of primary's).

    Country-agnostic: works for any {cc}_composites.yaml configuration.

    Args:
        conn: DuckDB connection.
        country: Two-letter internal country code (e.g. "EZ", "US", "KR").
        config: Loaded composites config (from load_composites_config).
        threshold: Pearson |r| above which a pair is flagged (default 0.80).
        min_periods: Minimum overlapping observations required to compute r (default 36).

    Returns:
        List of dicts with keys: country, signal_a, signal_b, r, same_basket, n_periods.
    """
    country_prefix = country.lower()
    growth_cfg = config["growth_score"]["indicators"]
    inflation_cfg = config["inflation_score"]["indicators"]

    growth_ids = [f"{country_prefix}.{ind['id']}" for ind in growth_cfg]
    inflation_ids = [f"{country_prefix}.{ind['id']}" for ind in inflation_cfg]
    all_ids = list(dict.fromkeys(growth_ids + inflation_ids))

    if len(all_ids) < 2:
        return []

    placeholders = ", ".join(["?"] * len(all_ids))
    df = conn.execute(
        f"SELECT id, as_of, zscore FROM signals WHERE id IN ({placeholders}) ORDER BY as_of",
        all_ids,
    ).df()
    if df.empty:
        logger.info("[CORR AUDIT] %s: no signal data in DB; skipping.", country)
        return []

    wide = df.pivot(index="as_of", columns="id", values="zscore")
    wide.index = pd.to_datetime(wide.index)
    wide = wide.sort_index()

    corr = wide.corr(min_periods=min_periods)

    growth_set = set(growth_ids)
    inflation_set = set(inflation_ids)

    pairs: list[dict] = []
    ids = corr.columns.tolist()
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1:]:
            r = corr.loc[id_a, id_b]
            if pd.isna(r) or abs(r) < threshold:
                continue
            same_basket = (
                (id_a in growth_set and id_b in growth_set)
                or (id_a in inflation_set and id_b in inflation_set)
            )
            n = int(wide[[id_a, id_b]].dropna().shape[0])
            pairs.append({
                "country": country,
                "signal_a": id_a,
                "signal_b": id_b,
                "r": round(float(r), 3),
                "same_basket": same_basket,
                "n_periods": n,
            })

    if pairs:
        sorted_pairs = sorted(pairs, key=lambda x: abs(x["r"]), reverse=True)
        logger.warning(
            "[CORR AUDIT] %s: %d high-correlation pair(s) found (|r|>=%.2f). "
            "Consider reducing importance of the secondary signal.",
            country, len(pairs), threshold,
        )
        for p in sorted_pairs:
            basket_tag = "SAME BASKET" if p["same_basket"] else "cross-basket"
            logger.warning(
                "  [%s]  r=%+.3f  n=%d  %s  ↔  %s",
                basket_tag, p["r"], p["n_periods"], p["signal_a"], p["signal_b"],
            )
    else:
        logger.info(
            "[CORR AUDIT] %s: no pairs above |r|=%.2f — no redundancy detected.",
            country, threshold,
        )

    return pairs


def build_formula_catalog(config: dict | None = None) -> list[dict[str, object]]:
    """Describe the live composite formulas using their active runtime settings.

    The dashboard consumes this catalog rather than maintaining a second set of
    parameter values. Formula cards therefore change with ``composites.yaml``.
    """
    cfg = config or load_composites_config()
    dynamic = cfg.get("dynamic_weighting", {})
    decay = cfg.get("time_decay", {})
    carry = cfg.get("per_frequency_ffill_limit", {})
    confidence = cfg.get("regime_confidence", {})
    diseq = cfg.get("disequilibrium_score", {})
    force_groups = diseq.get("forces", [])
    group_names = [next(iter(group)) for group in force_groups if isinstance(group, dict) and group]

    alpha = float(dynamic.get("momentum_alpha", 0.5))
    min_mult = float(dynamic.get("min_multiplier", 0.1))
    max_mult = float(dynamic.get("max_multiplier", 1.5))
    epsilon = float(dynamic.get("force_zero_epsilon", 0.05))
    half_life = float(decay.get("half_life_months", 3.0))
    hard_drop = decay.get("hard_drop_months")
    min_signals = int(confidence.get("min_signals_required", 4))
    min_forces = int(diseq.get("min_forces_required", 3))

    return [
        {
            "group": "Force",
            "title": "Component Z-score",
            "equation": r"Z_i = \operatorname{clip}\!\left(\frac{x_i-\mu_i}{s_i},-c,c\right)",
            "description": (
                "Each transformed signal is standardized against its full available history "
                "using the sample standard deviation."
            ),
            "parameters": [f"c = {ZSCORE_CAP_SIGMA:g}σ", "history = all available non-null observations"],
            "source": "indicators/normalize.py::_zscore_series",
        },
        {
            "group": "Force",
            "title": "Configured component weight",
            "equation": r"w_i^{cfg}=\frac{b_i\,I_i\,q_i}{\sum_j b_j\,I_j\,q_j}",
            "description": "Base share, editable importance, and quality are normalized within each force basket.",
            "parameters": ["b = base share", "I = importance", "q = quality factor"],
            "source": "indicators/composites.py::normalized_nominal_weights",
        },
        {
            "group": "Momentum",
            "title": "Force/momentum weight tilt",
            "equation": r"m_i=\operatorname{clip}\!\left(1+\alpha\,\operatorname{sign}(Z_i^{adj})\,d_i,m_{min},m_{max}\right)",
            "description": "Agreement between the adjusted force sign and 3-month direction boosts weight; disagreement reduces it.",
            "parameters": [
                f"α = {alpha:g}", f"bounds = {min_mult:g}× to {max_mult:g}×",
                f"|Z| < {epsilon:g} is neutral", "d = −1 falling, 0 flat, +1 rising",
            ],
            "source": "indicators/composites.py::momentum_weight_multiplier",
        },
        {
            "group": "Decay",
            "title": "Observation-age decay",
            "equation": r"\delta_i(a)=0.5^{\,a/h}",
            "description": "A carried observation loses half its remaining weight every configured half-life.",
            "parameters": [
                f"h = {half_life:g} months",
                f"global hard drop = {hard_drop:g} months" if hard_drop is not None else "global hard drop = disabled",
                "carry caps = " + ", ".join(f"{k}:{v}m" for k, v in carry.items()),
            ],
            "source": "indicators/composites.py::age_weight_fraction + compute_composite_history",
        },
        {
            "group": "Force",
            "title": "Effective weight and force score",
            "equation": r"w_i^{eff}=w_i^{cfg}m_i\delta_i,\qquad F=\frac{\sum_i w_i^{eff}Z_i^{adj}}{\sum_i w_i^{eff}}",
            "description": "Only available, reliable components with positive effective weight enter Growth or Inflation force.",
            "parameters": ["inverted signals use Zᵃᵈʲ = −Z", "weights are renormalized over active components"],
            "source": "indicators/composites.py::compute_composite_history._score_force",
        },
        {
            "group": "Momentum",
            "title": "Force momentum breadth",
            "equation": r"M_F=\frac{N(\text{active signals moving force-positive})}{N(\text{active signals with direction})}",
            "description": "Growth counts rising signals (falling for inverted unemployment); Inflation counts rising signals.",
            "parameters": ["direction is based on the transformed signal's 3-month change"],
            "source": "indicators/composites.py::compute_composite_history",
        },
        {
            "group": "Confidence",
            "title": "Regime confidence",
            "equation": r"C=\frac{1}{2}\left(\frac{N_G^{agree}}{N_G}+\frac{N_I^{agree}}{N_I}\right)",
            "description": "Average agreement within Growth and Inflation between component directions and the assigned quadrant.",
            "parameters": [f"minimum active signals per force = {min_signals}", "empty direction set defaults to 50%"],
            "source": "indicators/composites.py::compute_composite_history",
        },
        {
            "group": "Disequilibrium",
            "title": "Structural disequilibrium",
            "equation": r"D=\frac{1}{K}\sum_{k=1}^{K}\operatorname{mean}_{i\in k}\!\left(|Z(\,x_i-e_i\,)|\right)",
            "description": "Mean absolute standardized distance from equilibrium, first within each available structural force group and then across groups.",
            "parameters": [
                f"configured groups = {', '.join(group_names)}",
                f"low coverage when K < {min_forces}",
                "groups without data are excluded from K",
            ],
            "source": "indicators/composites.py::compute_composite_history",
        },
    ]


# ── Data loading ─────────────────────────────────────────────────────────────

def _compute_fill_age(monthly_raw: pd.DataFrame) -> pd.DataFrame:
    """For each cell return the number of months since the last non-NaN observation.

    Fresh observations have fill_age == 0.  A cell that has been forward-filled
    for k months has fill_age == k.  Used by the staleness-decay logic (F1/L1).
    """
    fill_age = pd.DataFrame(0.0, index=monthly_raw.index, columns=monthly_raw.columns)
    for col in monthly_raw.columns:
        s = monthly_raw[col]
        count = 0
        for idx in s.index:
            if pd.notna(s.loc[idx]):
                count = 0
            else:
                count += 1
            fill_age.loc[idx, col] = float(count)
    return fill_age


def _load_wide(
    conn,
    signal_ids: list[str],
    value_col: str,
    ffill_limit: int = 13,
    per_signal_limits: Optional[dict[str, int]] = None,
    exclude_unreliable: bool = False,
    return_fill_age: bool = False,
) -> "pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]":
    """
    Load signal history for given IDs, pivot to a wide monthly DataFrame.
    index: month-end DatetimeIndex  |  columns: signal IDs  |  values: value_col.
    Forward-fills up to ffill_limit months to bridge inter-observation gaps.
    """
    if not signal_ids:
        empty = pd.DataFrame(columns=signal_ids)
        return (empty, empty) if return_fill_age else empty

    placeholders = ", ".join(["?"] * len(signal_ids))
    df = conn.execute(
        f"SELECT id, as_of, {value_col}, is_stale, low_history "
        f"FROM signals WHERE id IN ({placeholders}) ORDER BY id, as_of",
        signal_ids,
    ).df()

    if df.empty:
        empty = pd.DataFrame(columns=signal_ids)
        return (empty, empty) if return_fill_age else empty

    df["as_of"] = pd.to_datetime(df["as_of"])
    # De-dup (shouldn't happen, but guard against re-ingestion oddities)
    df = df.drop_duplicates(subset=["id", "as_of"], keep="last")
    pivot = df.pivot(index="as_of", columns="id", values=value_col)
    pivot = pivot.reindex(columns=signal_ids)

    monthly_raw = pivot.resample("ME").last()
    fill_age = _compute_fill_age(monthly_raw) if return_fill_age else None

    if per_signal_limits:
        monthly = monthly_raw.copy()
        for col in monthly_raw.columns:
            limit = per_signal_limits.get(col, ffill_limit)
            monthly[col] = monthly_raw[col].ffill(limit=limit)
    else:
        monthly = monthly_raw.ffill(limit=ffill_limit)

    if exclude_unreliable:
        latest_quality = df.sort_values("as_of").groupby("id", as_index=False).tail(1)
        for row in latest_quality.itertuples(index=False):
            if bool(row.low_history):
                monthly[row.id] = np.nan
            elif bool(row.is_stale):
                stale_from = pd.Timestamp(row.as_of).to_period("M").to_timestamp("M")
                monthly.loc[monthly.index >= stale_from, row.id] = np.nan

    if return_fill_age:
        return monthly, fill_age
    return monthly


def _build_force_groups(conn, country: str, config: dict) -> dict[str, list[str]]:
    """
    Parse disequilibrium_score.forces from config into {group_name: [full_signal_ids]}.
    Members containing "." are treated as concept IDs; otherwise as force field values.
    """
    country_prefix = country.lower()
    diseq_cfg = config.get("disequilibrium_score", {}).get("forces", [])
    groups: dict[str, list[str]] = {}

    for force_dict in diseq_cfg:
        for group_name, members in force_dict.items():
            ids: list[str] = []
            for m in members:
                if "." in m:
                    ids.append(f"{country_prefix}.{m}")
                else:
                    df = conn.execute(
                        "SELECT DISTINCT id FROM signals WHERE country = ? AND force = ?",
                        [country, m],
                    ).df()
                    ids.extend(df["id"].tolist())
            groups[group_name] = ids

    return groups


# ── Composite computation ─────────────────────────────────────────────────────

def compute_composite_history(
    conn,
    country: str,
    config: dict,
    start_date: Optional[date] = None,
    freq_map: Optional[dict[str, str]] = None,
    zscore_col: str = "zscore",
    diseq_window: int = 0,
) -> list:
    """
    Compute Growth Score, Inflation Score, Regime Quadrant, Confidence, and
    Disequilibrium Score for every month-end from first available data to today.

    zscore_col:   which signals column to use for force scoring
                  ("zscore" = full history; "zscore_36m" / "zscore_48m" / "zscore_60m" = rolling)
    diseq_window: rolling window in months for disequilibrium Z-score
                  (0 = full history std via global STDDEV_SAMP)

    Returns list[CompositeSnapshot] ready for store.upsert_composites().
    """
    from indicators.models import CompositeSnapshot

    country_prefix = country.lower()
    growth_cfg   = config["growth_score"]["indicators"]
    inflation_cfg = config["inflation_score"]["indicators"]
    min_signals  = config.get("regime_confidence", {}).get("min_signals_required", 4)
    min_forces   = config.get("disequilibrium_score", {}).get("min_forces_required", 3)

    # ── Signal ID lists ───────────────────────────────────────────────────────
    growth_ids    = [f"{country_prefix}.{ind['id']}" for ind in growth_cfg]
    inflation_ids = [f"{country_prefix}.{ind['id']}" for ind in inflation_cfg]
    composite_ids = list(dict.fromkeys(growth_ids + inflation_ids))

    force_groups = _build_force_groups(conn, country, config)
    diseq_ids    = list(dict.fromkeys(sid for ids in force_groups.values() for sid in ids))

    # ── Force-balance audit (logs WARNING if one basket outweighs the other >33%) ──
    _log_force_balance(country, growth_cfg, inflation_cfg)

    # ── Configurable nominal + dynamic weighting ─────────────────────────────
    growth_nominal = normalized_nominal_weights(growth_cfg)
    inflation_nominal = normalized_nominal_weights(inflation_cfg)
    dynamic_cfg = config.get("dynamic_weighting", {})
    dynamic_enabled = bool(dynamic_cfg.get("enabled", False))

    # New configs use a half-life; retain the old decay-factor form for custom
    # configs and historical tests that have not migrated yet.
    time_decay_cfg = config.get("time_decay", {})
    legacy_decay_cfg = config.get("staleness_decay", {})
    decay_enabled = bool(
        time_decay_cfg.get("enabled", False)
        or legacy_decay_cfg.get("enabled", False)
    )
    half_life_months = float(time_decay_cfg.get("half_life_months", 3.0))
    hard_drop_months = time_decay_cfg.get("hard_drop_months")
    legacy_decay_factor = float(legacy_decay_cfg.get("decay_factor", 0.9))

    # ── Per-frequency carry cap (L2) ──────────────────────────────────────────
    freq_limits_cfg = config.get("per_frequency_ffill_limit", {})
    default_limit   = int(freq_limits_cfg.get("default", 13))
    per_signal_limits: Optional[dict[str, int]] = None
    if freq_map and freq_limits_cfg:
        per_signal_limits = {
            sid: int(freq_limits_cfg.get(freq, default_limit))
            for sid, freq in freq_map.items()
            if sid in composite_ids
        }

    # ── Load wide DataFrames once ─────────────────────────────────────────────
    load_kwargs: dict = {
        "exclude_unreliable": True,
        "ffill_limit": default_limit,
        **({"per_signal_limits": per_signal_limits} if per_signal_limits else {}),
    }
    if decay_enabled:
        z_comp, fill_age_comp = _load_wide(
            conn, composite_ids, zscore_col, **load_kwargs, return_fill_age=True
        )
    else:
        z_comp = _load_wide(conn, composite_ids, zscore_col, **load_kwargs)
        fill_age_comp = None
    d_comp  = _load_wide(conn, composite_ids, "direction", **load_kwargs)

    # Express declared equilibrium distance in each signal's own historical
    # standard-deviation units before combining heterogeneous force groups.
    z_diseq = pd.DataFrame()
    if diseq_ids:
        dist = _load_wide(
            conn,
            diseq_ids,
            "distance_from_equilibrium",
            exclude_unreliable=True,
        )
        if diseq_window > 0:
            # Rolling std over the specified window (months = rows since dist is monthly)
            half = max(1, diseq_window // 2)
            roll_std = dist.rolling(diseq_window, min_periods=half).std()
            roll_std = roll_std.replace(0, np.nan)
            z_diseq = dist.divide(roll_std).clip(lower=-ZSCORE_CAP_SIGMA, upper=ZSCORE_CAP_SIGMA)
        else:
            placeholders = ", ".join(["?"] * len(diseq_ids))
            scales = conn.execute(
                f"SELECT id, STDDEV_SAMP(distance_from_equilibrium) AS scale "
                f"FROM signals WHERE id IN ({placeholders}) GROUP BY id",
                diseq_ids,
            ).df()
            scale_by_id = scales.set_index("id")["scale"].replace(0, np.nan)
            z_diseq = dist.divide(scale_by_id, axis="columns")

    if z_comp.empty:
        logger.warning("No composite signal data found for country=%s", country)
        return []

    if start_date:
        ts = pd.Timestamp(start_date)
        z_comp      = z_comp[z_comp.index >= ts]
        d_comp      = d_comp[d_comp.index >= ts]            if not d_comp.empty       else d_comp
        z_diseq     = z_diseq[z_diseq.index >= ts]          if not z_diseq.empty      else z_diseq
        fill_age_comp = fill_age_comp[fill_age_comp.index >= ts] if fill_age_comp is not None and not fill_age_comp.empty else fill_age_comp

    snapshots: list[CompositeSnapshot] = []

    for dt in z_comp.index:
        z_row = z_comp.loc[dt]
        d_row = d_comp.loc[dt]  if (not d_comp.empty  and dt in d_comp.index)  else pd.Series(dtype=object)
        zd_row = z_diseq.loc[dt] if (not z_diseq.empty and dt in z_diseq.index) else pd.Series(dtype=float)

        def _score_force(
            indicators: list[dict], nominal_weights: dict[str, float]
        ) -> tuple[Optional[float], list[str], dict[str, dict]]:
            weighted_sum = 0.0
            active_weight = 0.0
            contributing: list[str] = []
            audit: dict[str, dict] = {}

            for ind in indicators:
                concept_id = ind["id"]
                sid = f"{country_prefix}.{concept_id}"
                z = z_row.get(sid)
                direction = d_row.get(sid)
                nominal = nominal_weights[concept_id]
                age = 0.0
                if fill_age_comp is not None and sid in fill_age_comp.columns and dt in fill_age_comp.index:
                    age_raw = fill_age_comp.loc[dt, sid]
                    age = float(age_raw) if pd.notna(age_raw) else 0.0

                momentum_mult = 1.0
                decay_fraction = 1.0
                effective = 0.0
                adjusted_z: Optional[float] = None
                missing = bool(z is None or (isinstance(z, float) and np.isnan(z)))

                if not missing:
                    adjusted_z = -float(z) if ind.get("invert", False) else float(z)
                    if dynamic_enabled:
                        momentum_mult = momentum_weight_multiplier(
                            float(z),
                            direction,
                            invert=bool(ind.get("invert", False)),
                            alpha=float(dynamic_cfg.get("momentum_alpha", 0.5)),
                            min_multiplier=float(dynamic_cfg.get("min_multiplier", 0.1)),
                            max_multiplier=float(dynamic_cfg.get("max_multiplier", 1.5)),
                            zero_epsilon=float(dynamic_cfg.get("force_zero_epsilon", 0.05)),
                        )
                    if decay_enabled:
                        if time_decay_cfg:
                            decay_fraction = age_weight_fraction(age, half_life_months)
                        else:
                            decay_fraction = legacy_decay_factor ** age
                    if hard_drop_months is not None and age > float(hard_drop_months):
                        decay_fraction = 0.0
                    effective = nominal * momentum_mult * decay_fraction
                    if effective > 0:
                        weighted_sum += adjusted_z * effective
                        active_weight += effective
                        contributing.append(sid)

                audit[sid] = {
                    "base_share": round(float(ind.get("base_share", ind.get("weight", 1.0))), 6),
                    "importance": round(float(ind.get("importance", 1.0)), 6),
                    "quality_factor": round(float(ind.get("quality_factor", 1.0)), 6),
                    "config_weight": round(nominal, 8),
                    "momentum_multiplier": round(momentum_mult, 6),
                    "age_months": round(age, 3),
                    "decay_fraction": round(decay_fraction, 6),
                    "effective_weight": round(effective, 8),
                    "normalized_weight": 0.0,
                    "missing": missing,
                }

            if active_weight > 0:
                for sid in contributing:
                    audit[sid]["normalized_weight"] = round(
                        audit[sid]["effective_weight"] / active_weight, 8
                    )
            score = weighted_sum / active_weight if active_weight > 0 else None
            return score, contributing, audit

        growth_score, g_ids_contrib, growth_audit = _score_force(
            growth_cfg, growth_nominal
        )
        inflation_score, i_ids_contrib, inflation_audit = _score_force(
            inflation_cfg, inflation_nominal
        )
        n_growth = len(g_ids_contrib)
        n_inflation = len(i_ids_contrib)

        # ── Regime Quadrant + Confidence ──────────────────────────────────────
        quadrant   = None
        confidence = None

        if (
            growth_score is not None
            and inflation_score is not None
            and n_growth   >= min_signals
            and n_inflation >= min_signals
        ):
            growth_up    = growth_score   >= 0
            inflation_up = inflation_score >= 0
            quadrant = _QUADRANT_LABELS[(growth_up, inflation_up)]
            exp_g, exp_i = _EXPECTED_DIR[(growth_up, inflation_up)]

            g_agree: list[float] = []
            for ind in growth_cfg:
                sid = f"{country_prefix}.{ind['id']}"
                if sid not in g_ids_contrib:
                    continue
                d = d_row.get(sid)
                if not isinstance(d, str):
                    continue
                # Inverted signals (e.g. unemployment) flip the expected direction
                expected = ("falling" if growth_up else "rising") if ind.get("invert", False) else exp_g
                g_agree.append(1.0 if d == expected else 0.0)

            i_agree: list[float] = []
            for ind in inflation_cfg:
                sid = f"{country_prefix}.{ind['id']}"
                if sid not in i_ids_contrib:
                    continue
                d = d_row.get(sid)
                if not isinstance(d, str):
                    continue
                i_agree.append(1.0 if d == exp_i else 0.0)

            g_frac = float(np.mean(g_agree)) if g_agree else 0.5
            i_frac = float(np.mean(i_agree)) if i_agree else 0.5
            confidence = (g_frac + i_frac) / 2.0

        # ── Disequilibrium Score ──────────────────────────────────────────────
        force_scores: list[float] = []

        for group_ids in force_groups.values():
            present = [sid for sid in group_ids if sid in z_diseq.columns]
            z_vals  = [zd_row.get(sid) for sid in present]
            clean   = [float(v) for v in z_vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
            if clean:
                force_scores.append(float(np.mean(np.abs(clean))))

        n_forces    = len(force_scores)
        diseq_score = float(np.mean(force_scores)) if force_scores else None
        low_cov     = n_forces < min_forces

        # ── Momentum fractions ────────────────────────────────────────────────
        g_mom_pos = g_mom_total = 0
        for ind in growth_cfg:
            sid = f"{country_prefix}.{ind['id']}"
            if sid not in g_ids_contrib:
                continue
            d = d_row.get(sid)
            if not isinstance(d, str) or not d:
                continue
            positive_dir = "falling" if ind.get("invert", False) else "rising"
            if d == positive_dir:
                g_mom_pos += 1
            g_mom_total += 1
        growth_momentum = g_mom_pos / g_mom_total if g_mom_total > 0 else None

        i_mom_pos = i_mom_total = 0
        for ind in inflation_cfg:
            sid = f"{country_prefix}.{ind['id']}"
            if sid not in i_ids_contrib:
                continue
            d = d_row.get(sid)
            if not isinstance(d, str) or not d:
                continue
            if d == "rising":
                i_mom_pos += 1
            i_mom_total += 1
        inflation_momentum = i_mom_pos / i_mom_total if i_mom_total > 0 else None

        # ── Stale signal audit (L3) ───────────────────────────────────────────
        stale_signals: Optional[str] = None
        if fill_age_comp is not None and dt in fill_age_comp.index:
            parts: list[str] = []
            for sid in (g_ids_contrib + i_ids_contrib):
                if sid in fill_age_comp.columns:
                    age = fill_age_comp.loc[dt, sid]
                    if pd.notna(age) and float(age) > 0:
                        parts.append(f"{sid}:{int(age)}")
            stale_signals = ",".join(parts) if parts else None

        snapshots.append(
            CompositeSnapshot(
                country=country,
                # The current partial month must not masquerade as a future
                # month-end observation.
                as_of=min(dt.date(), date.today()),
                growth_score    =round(growth_score,    4) if growth_score    is not None else None,
                inflation_score =round(inflation_score, 4) if inflation_score is not None else None,
                quadrant=quadrant,
                confidence      =round(confidence,  4) if confidence  is not None else None,
                disequilibrium_score=round(diseq_score, 4) if diseq_score is not None else None,
                n_growth_signals  =n_growth,
                n_inflation_signals=n_inflation,
                n_forces=n_forces,
                low_coverage=low_cov,
                stale_signals=stale_signals,
                growth_momentum   =round(growth_momentum,    4) if growth_momentum    is not None else None,
                inflation_momentum=round(inflation_momentum, 4) if inflation_momentum is not None else None,
                weight_audit=json.dumps(
                    {"growth": growth_audit, "inflation": inflation_audit},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        )

    return snapshots

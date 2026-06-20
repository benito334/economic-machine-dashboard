"""
Phase 1B composites engine.

Computes Growth Score, Inflation Score, Regime Quadrant (+Confidence),
and Disequilibrium Score from signals stored in DuckDB.

Entry point:  compute_composite_history(conn, country, config)
              → list[CompositeSnapshot], ready for upsert_composites().
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

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


def load_composites_config(path: Path | None = None) -> dict:
    p = path or (_CONFIG_DIR / "composites.yaml")
    with open(p) as f:
        return yaml.safe_load(f)


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
        return pd.DataFrame(columns=signal_ids)

    placeholders = ", ".join(["?"] * len(signal_ids))
    df = conn.execute(
        f"SELECT id, as_of, {value_col}, is_stale, low_history "
        f"FROM signals WHERE id IN ({placeholders}) ORDER BY id, as_of",
        signal_ids,
    ).df()

    if df.empty:
        return pd.DataFrame(columns=signal_ids)

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
) -> list:
    """
    Compute Growth Score, Inflation Score, Regime Quadrant, Confidence, and
    Disequilibrium Score for every month-end from first available data to today.

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

    # ── Staleness-decay config (F1/L1) ────────────────────────────────────────
    decay_cfg     = config.get("staleness_decay", {})
    decay_enabled = bool(decay_cfg.get("enabled", False))
    decay_factor  = float(decay_cfg.get("decay_factor", 0.9))

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
            conn, composite_ids, "zscore", **load_kwargs, return_fill_age=True
        )
    else:
        z_comp = _load_wide(conn, composite_ids, "zscore", **load_kwargs)
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

        # ── Growth Score ──────────────────────────────────────────────────────
        g_sum, g_w = 0.0, 0.0
        g_ids_contrib: list[str] = []

        for ind in growth_cfg:
            sid = f"{country_prefix}.{ind['id']}"
            z = z_row.get(sid)
            if z is None or (isinstance(z, float) and np.isnan(z)):
                continue
            w   = ind.get("weight", 1.0)
            if decay_enabled and fill_age_comp is not None and sid in fill_age_comp.columns:
                age = fill_age_comp.loc[dt, sid] if dt in fill_age_comp.index else 0.0
                w *= decay_factor ** (float(age) if pd.notna(age) else 0.0)
            adj = -float(z) if ind.get("invert", False) else float(z)
            g_sum += adj * w
            g_w   += w
            g_ids_contrib.append(sid)

        growth_score = g_sum / g_w if g_w > 0 else None
        n_growth     = len(g_ids_contrib)

        # ── Inflation Score ───────────────────────────────────────────────────
        i_sum, i_w = 0.0, 0.0
        i_ids_contrib: list[str] = []

        for ind in inflation_cfg:
            sid = f"{country_prefix}.{ind['id']}"
            z = z_row.get(sid)
            if z is None or (isinstance(z, float) and np.isnan(z)):
                continue
            w = ind.get("weight", 1.0)
            if decay_enabled and fill_age_comp is not None and sid in fill_age_comp.columns:
                age = fill_age_comp.loc[dt, sid] if dt in fill_age_comp.index else 0.0
                w *= decay_factor ** (float(age) if pd.notna(age) else 0.0)
            i_sum += float(z) * w
            i_w   += w
            i_ids_contrib.append(sid)

        inflation_score = i_sum / i_w if i_w > 0 else None
        n_inflation     = len(i_ids_contrib)

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
            )
        )

    return snapshots

"""GDP-regression calibration for the Growth Force composite.

Regresses each growth signal's Z-score against the real GDP Z-score to derive
empirical weight estimates. Results are advisory — the user reviews them and
decides whether to apply via the Weight Audit importance editor.

Only the Growth basket is calibrated here. The GDP target is
`{country}.master.gdp_real` (quarterly, already in the signals table).
Monthly signals are resampled to quarterly (mean) before regression.

Signals with beta <= 0 receive no recommendation (Option B): their current
importance is unchanged until the user decides otherwise.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


def calibrate_growth_weights(
    country: str,
    conn,
    config: dict,
    min_obs: int = 20,
) -> pd.DataFrame:
    """OLS regression of each growth composite signal against real GDP Z-score.

    Args:
        country:  Two-letter internal code (e.g. "US").
        conn:     DuckDB connection.
        config:   Loaded composites config (from load_composites_config).
        min_obs:  Minimum common quarterly observations to run regression.

    Returns:
        DataFrame with columns:
            signal_id          str   — yaml id (no country prefix, e.g. "growth.payrolls")
            label              str   — short label (e.g. "payrolls")
            invert             bool
            n_obs              int   — common quarterly observations used
            beta               float | None
            r_squared          float | None
            p_value            float | None
            contribution_share float | None — normalized positive beta (sums to 1.0)
            recommended_imp    float | None — scaled to [0.10, 0.95]; None if beta <= 0
            current_importance float
            delta              float | None — recommended_imp - current_importance
            note               str
    """
    prefix = country.lower()
    gdp_id = f"{prefix}.master.gdp_real"

    gdp_df = conn.execute(
        "SELECT as_of, zscore FROM signals WHERE id = ? AND zscore IS NOT NULL ORDER BY as_of",
        [gdp_id],
    ).df()
    if gdp_df.empty:
        raise ValueError(f"GDP signal '{gdp_id}' not found in DB — run pipeline first.")

    gdp_df["as_of"] = pd.to_datetime(gdp_df["as_of"])
    gdp_q = (
        gdp_df.set_index("as_of")["zscore"]
        .resample("QE")
        .last()
        .dropna()
    )

    growth_cfg = config["growth_score"]["indicators"]
    raw: list[dict] = []

    for ind in growth_cfg:
        sig_id = f"{prefix}.{ind['id']}"
        invert = bool(ind.get("invert", False))
        current_imp = round(float(ind.get("importance", 1.0)), 2)

        sig_df = conn.execute(
            "SELECT as_of, zscore FROM signals WHERE id = ? AND zscore IS NOT NULL ORDER BY as_of",
            [sig_id],
        ).df()

        if sig_df.empty:
            raw.append(_no_data_row(ind["id"], invert, current_imp, "No Z-score data in DB"))
            continue

        sig_df["as_of"] = pd.to_datetime(sig_df["as_of"])
        sig_q = (
            sig_df.set_index("as_of")["zscore"]
            .resample("QE")
            .mean()
            .dropna()
        )
        if invert:
            sig_q = -sig_q

        aligned = pd.concat(
            [gdp_q.rename("gdp"), sig_q.rename("sig")], axis=1
        ).dropna()
        n = len(aligned)

        if n < min_obs:
            raw.append(_no_data_row(
                ind["id"], invert, current_imp,
                f"Only {n} common quarters (need {min_obs})",
            ))
            continue

        slope, _, r_value, p_value, _ = stats.linregress(
            aligned["sig"].values, aligned["gdp"].values
        )
        beta = float(slope)
        r2   = float(r_value ** 2)
        pval = float(p_value)

        note = ""
        if beta <= 0:
            note = f"β={beta:.3f} ≤ 0 — no recommendation (keep current importance)"

        raw.append({
            "signal_id":       ind["id"],
            "label":           ind["id"].split(".")[-1],
            "invert":          invert,
            "n_obs":           n,
            "beta":            round(beta, 4),
            "r_squared":       round(r2, 4),
            "p_value":         round(pval, 4),
            "_raw_beta":       max(0.0, beta),
            "current_importance": current_imp,
            "note":            note,
        })

    if not raw:
        return pd.DataFrame()

    # ── Normalize positive betas → contribution shares ────────────────────────
    total_pos = sum(r["_raw_beta"] for r in raw if r.get("_raw_beta", 0) > 0)
    max_share = 0.0
    for r in raw:
        if r.get("_raw_beta", 0) > 0 and total_pos > 0:
            r["contribution_share"] = round(r["_raw_beta"] / total_pos, 4)
            if r["contribution_share"] > max_share:
                max_share = r["contribution_share"]
        else:
            r["contribution_share"] = None

    # ── Scale shares → importance range [0.10, 0.95] ─────────────────────────
    for r in raw:
        if r.get("contribution_share") is not None and max_share > 0:
            scaled = r["contribution_share"] / max_share * 0.95
            r["recommended_imp"] = round(max(0.10, min(0.95, scaled)), 2)
        else:
            r["recommended_imp"] = None

    # ── Delta vs current ──────────────────────────────────────────────────────
    for r in raw:
        if r.get("recommended_imp") is not None:
            r["delta"] = round(r["recommended_imp"] - r["current_importance"], 2)
        else:
            r["delta"] = None

    df = pd.DataFrame(raw).drop(columns=["_raw_beta"])
    col_order = [
        "signal_id", "label", "invert", "n_obs",
        "beta", "r_squared", "p_value",
        "contribution_share", "recommended_imp",
        "current_importance", "delta", "note",
    ]
    return df[[c for c in col_order if c in df.columns]]


def _no_data_row(signal_id: str, invert: bool, current_imp: float, note: str) -> dict:
    return {
        "signal_id":          signal_id,
        "label":              signal_id.split(".")[-1],
        "invert":             invert,
        "n_obs":              0,
        "beta":               None,
        "r_squared":          None,
        "p_value":            None,
        "_raw_beta":          0.0,
        "contribution_share": None,
        "recommended_imp":    None,
        "current_importance": current_imp,
        "delta":              None,
        "note":               note,
    }

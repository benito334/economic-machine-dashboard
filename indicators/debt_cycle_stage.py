"""Long-Term Debt-Cycle STAGE Classifier (roadmap Phase C).

Debt Stress (longterm_stress.py) answers "how much pressure?"; this module
answers "WHERE in the ~50–75yr cycle are we?" — Ray Dalio's leveraging /
squeeze / deleveraging / reflation framing.

Classification is a transparent weighted-condition vote, not a fitted model:
five feature families (debt/GDP percentile, debt/GDP trajectory, debt-service
trend, real-rate-minus-real-growth, nominal-growth-minus-yield) feed per-stage
scores whose weights and thresholds all live in config/debt_cycle_stage.yaml.
Missing features degrade gracefully (renormalize over what's evaluable) —
a country with only a government debt ratio still gets an honest read.

Look-ahead discipline matches the rest of the repo: the debt/GDP percentile
is an expanding rank of the current value against PRIOR history only
(shift 1), and every feature at quarter t uses data dated ≤ t.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from indicators.models import DebtCycleStageSnapshot

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "config"

STAGES = ["leveraging", "squeeze", "deleveraging", "reflation"]


def _empty() -> pd.Series:
    """Empty float series with a DatetimeIndex — a plain pd.Series() carries a
    RangeIndex, which corrupts the index union when assembled into the feature
    DataFrame alongside datetime-indexed columns."""
    return pd.Series(dtype=float, index=pd.DatetimeIndex([]))

# Which feature family each stage-condition needs. Used to renormalize stage
# scores when a family is missing for a given country/quarter.
_CONDITION_FEATURE = {
    "debt_rising": "debt_traj", "debt_falling": "debt_traj",
    "debt_not_rising": "debt_traj", "debt_high": "debt_pct",
    "dsr_rising": "dsr_trend", "dsr_falling": "dsr_trend",
    "dsr_not_rising": "dsr_trend",
    "g_above_r": "r_minus_g", "r_at_or_above_g": "r_minus_g",
    "r_deep_below_g": "r_minus_g",
    "ngdp_above_yield": "ngdp_minus_yield", "ngdp_below_yield": "ngdp_minus_yield",
    "ngdp_well_above_yield": "ngdp_minus_yield",
    "growth_weak": "real_growth",
}


def load_stage_config(path: Path | None = None) -> dict:
    """Load and sanity-check config/debt_cycle_stage.yaml. Fails loudly."""
    cfg_path = path or (_CONFIG_DIR / "debt_cycle_stage.yaml")
    with open(cfg_path) as fh:
        cfg = yaml.safe_load(fh)
    for key in ("features", "thresholds", "weights", "classification", "countries"):
        if key not in cfg:
            raise ValueError(f"debt_cycle_stage.yaml missing required section '{key}'")
    for stage in STAGES:
        if stage not in cfg["weights"]:
            raise ValueError(f"debt_cycle_stage.yaml weights missing stage '{stage}'")
        for cond in cfg["weights"][stage]:
            if cond not in _CONDITION_FEATURE:
                raise ValueError(f"Unknown stage condition '{cond}' in weights.{stage}")
    return cfg


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_signal_values(conn, signal_id: str) -> pd.Series:
    df = conn.execute(
        "SELECT as_of, value FROM signals WHERE id = ? AND value IS NOT NULL ORDER BY as_of",
        [signal_id],
    ).df()
    if df.empty:
        return _empty()
    df["as_of"] = pd.to_datetime(df["as_of"])
    return df.set_index("as_of")["value"].sort_index()


def _to_quarterly(s: pd.Series, ffill_limit: int) -> pd.Series:
    """Resample to quarter-end (last obs in quarter), forward-fill up to limit.

    The limit keeps annual World Bank/IMF ratios honest: they cover at most
    ffill_limit quarters past their period before the feature goes missing
    (CLAUDE.md rule 7 — never carry data past its release cycle silently).
    """
    if s.empty:
        return s
    q = s.resample("QE").last()
    # Extend to the current quarter-end so a fresh annual/quarterly release
    # still covers "now" (within the limit) — resample().last() stops at the
    # last observation and would otherwise leave the latest quarters NaN.
    current_qe = pd.Timestamp.today().to_period("Q").to_timestamp("Q")
    if q.index[-1] < current_qe:
        q = q.reindex(pd.date_range(q.index[0], current_qe, freq="QE"))
    return q.ffill(limit=ffill_limit)


# ── Feature construction ──────────────────────────────────────────────────────

def expanding_percentile_lagged(s: pd.Series, min_periods: int) -> pd.Series:
    """Percentile of each value against PRIOR history only (no look-ahead).

    out[t] = fraction of observations s[0..t-1] that are <= s[t].
    NaN until min_periods prior observations exist.
    """
    vals = s.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        prior = vals[:i]
        prior = prior[~np.isnan(prior)]
        if len(prior) >= min_periods and not np.isnan(vals[i]):
            out[i] = float((prior <= vals[i]).mean())
    return pd.Series(out, index=s.index)


def _annualized_change(s: pd.Series, window_years: float) -> pd.Series:
    """Change over the window, expressed per year (pp/yr for pp series)."""
    periods = max(1, int(round(window_years * 4)))
    return (s - s.shift(periods)) / window_years


def build_features(conn, country: str, cfg: dict) -> pd.DataFrame:
    """Quarterly feature DataFrame for one country. All rate features in pp.

    Columns (any may be all-NaN if the country lacks the source):
      debt_pct          expanding percentile of avg debt/GDP components [0,1]
      debt_traj         avg annualized Δ debt/GDP (pp of GDP per year)
      dsr_trend         Δ debt-service ratio over the trend window (pp)
      r_minus_g         real policy rate − real GDP growth (pp)
      ngdp_minus_yield  nominal growth − long yield (pp)
      real_growth       smoothed real GDP growth (yoy %)
    """
    ccfg = cfg["countries"].get(country)
    if ccfg is None:
        raise ValueError(f"No debt_cycle_stage country block for '{country}'")
    fcfg = cfg["features"]
    prefix = country.lower()
    ffill = int(fcfg["ffill_limit_quarters"])
    smooth_q = max(1, int(fcfg.get("growth_smooth_quarters", 1)))

    def sig(tail: str) -> pd.Series:
        return _to_quarterly(_load_signal_values(conn, f"{prefix}.{tail}"), ffill)

    # ── Debt stock: per-component percentile + trajectory, averaged over
    # whatever components exist that quarter (start dates differ). ──────────
    pct_parts, traj_parts = [], []
    for tail in ccfg.get("debt_components") or []:
        comp = sig(tail)
        if comp.empty:
            logger.warning("[STAGE %s] debt component %s empty — skipped", country, tail)
            continue
        pct_parts.append(expanding_percentile_lagged(
            comp, int(fcfg["percentile_min_periods"])))
        traj_parts.append(_annualized_change(
            comp, float(fcfg["debt_traj_window_years"])))
    debt_pct = pd.concat(pct_parts, axis=1).mean(axis=1) if pct_parts else _empty()
    debt_traj = pd.concat(traj_parts, axis=1).mean(axis=1) if traj_parts else _empty()

    # ── Debt-service trend ───────────────────────────────────────────────────
    dsr_trend = _empty()
    if ccfg.get("dsr_signal"):
        dsr = sig(ccfg["dsr_signal"])
        if not dsr.empty:
            periods = max(1, int(round(float(fcfg["dsr_trend_window_years"]) * 4)))
            dsr_trend = dsr - dsr.shift(periods)

    # ── Real growth (yoy fraction → %, smoothed) ─────────────────────────────
    growth = sig(ccfg["real_growth_signal"]) * 100.0
    if not growth.empty and smooth_q > 1:
        growth = growth.rolling(smooth_q, min_periods=1).mean()

    # ── Real policy rate (pp) ────────────────────────────────────────────────
    rcfg = ccfg.get("real_rate") or {}
    if rcfg.get("signal"):
        real_rate = sig(rcfg["signal"])                       # already real, pp
    elif rcfg.get("nominal_signal"):
        nominal = sig(rcfg["nominal_signal"])                 # pp
        infl = sig(rcfg["inflation_signal"]) * 100.0          # yoy fraction → pp
        if smooth_q > 1 and not infl.empty:
            infl = infl.rolling(smooth_q, min_periods=1).mean()
        real_rate = (nominal - infl).dropna()
    else:
        real_rate = _empty()
    r_minus_g = (real_rate - growth).dropna() if (not real_rate.empty and not growth.empty) \
        else _empty()

    # ── Nominal growth minus yield (pp) ──────────────────────────────────────
    ncfg = ccfg.get("ngdp_minus_yield") or {}
    if ncfg.get("signal"):
        ngdp_my = sig(ncfg["signal"]) * float(ncfg.get("scale", 1))
    elif ncfg.get("derived"):
        yld = sig(ncfg["yield_signal"])                       # pp
        g = sig(ncfg["growth_signal"]) * 100.0
        infl = sig(ncfg["inflation_signal"]) * 100.0
        if smooth_q > 1:
            if not g.empty:
                g = g.rolling(smooth_q, min_periods=1).mean()
            if not infl.empty:
                infl = infl.rolling(smooth_q, min_periods=1).mean()
        ngdp_my = ((g + infl) - yld).dropna()
    else:
        ngdp_my = _empty()

    feats = pd.DataFrame({
        "debt_pct": debt_pct,
        "debt_traj": debt_traj,
        "dsr_trend": dsr_trend,
        "r_minus_g": r_minus_g,
        "ngdp_minus_yield": ngdp_my,
        "real_growth": growth,
    })
    return feats.dropna(how="all")


# ── Stage scoring ─────────────────────────────────────────────────────────────

def _conditions(feats_row: pd.Series, thr: dict) -> dict:
    """Evaluate every named condition for one quarter. NaN feature → None."""
    def have(f):
        v = feats_row.get(f)
        return v is not None and not (isinstance(v, float) and np.isnan(v))

    out: dict[str, Optional[bool]] = {}
    if have("debt_traj"):
        dt = float(feats_row["debt_traj"])
        out["debt_rising"] = dt > thr["debt_traj_rising"]
        out["debt_falling"] = dt < thr["debt_traj_falling"]
        out["debt_not_rising"] = dt <= thr["debt_traj_rising"]
    if have("debt_pct"):
        out["debt_high"] = float(feats_row["debt_pct"]) > thr["debt_pct_high"]
    if have("dsr_trend"):
        ds = float(feats_row["dsr_trend"])
        out["dsr_rising"] = ds > thr["dsr_rising"]
        out["dsr_falling"] = ds < thr["dsr_falling"]
        out["dsr_not_rising"] = ds <= thr["dsr_rising"]
    if have("r_minus_g"):
        rg = float(feats_row["r_minus_g"])
        out["g_above_r"] = rg < thr["r_minus_g_pos"]
        out["r_at_or_above_g"] = rg >= thr["r_minus_g_pos"]
        out["r_deep_below_g"] = rg < thr["r_minus_g_deep_neg"]
    if have("ngdp_minus_yield"):
        ny = float(feats_row["ngdp_minus_yield"])
        out["ngdp_above_yield"] = ny > 0.0
        out["ngdp_below_yield"] = ny < thr["ngdp_yield_neg"]
        out["ngdp_well_above_yield"] = ny > thr["ngdp_yield_pos"]
    if have("real_growth"):
        out["growth_weak"] = float(feats_row["real_growth"]) < thr["growth_weak"]
    return out


def score_stages(feats_row: pd.Series, cfg: dict) -> dict:
    """Per-stage scores in [0,1] for one quarter, renormalized over evaluable
    conditions. A stage whose evaluable weight < min_condition_weight → NaN."""
    conds = _conditions(feats_row, cfg["thresholds"])
    min_w = float(cfg["classification"]["min_condition_weight"])
    scores = {}
    for stage, weights in cfg["weights"].items():
        avail_w = hit_w = 0.0
        for cond, w in weights.items():
            if cond in conds:
                avail_w += w
                if conds[cond]:
                    hit_w += w
        scores[stage] = (hit_w / avail_w) if avail_w >= min_w else float("nan")
    return scores


def _rolling_mode(labels: pd.Series, window: int) -> pd.Series:
    """Mode over a trailing window; the current label breaks ties (so a new
    stage takes over as soon as it wins a strict majority, not before).

    A quarter with no raw label (insufficient features) stays unlabeled —
    smoothing must never carry a stale stage across a data gap."""
    if window <= 1:
        return labels
    out = labels.copy()
    vals = labels.tolist()
    for i in range(len(vals)):
        if not isinstance(vals[i], str):
            out.iloc[i] = None
            continue
        win = [v for v in vals[max(0, i - window + 1): i + 1] if isinstance(v, str)]
        counts: dict[str, int] = {}
        for v in win:
            counts[v] = counts.get(v, 0) + 1
        best = max(counts.values())
        winners = [k for k, c in counts.items() if c == best]
        out.iloc[i] = vals[i] if vals[i] in winners else winners[0]
    return out


def compute_stage_history(conn, country: str, cfg: dict) -> list[DebtCycleStageSnapshot]:
    """Full quarterly stage history for one country."""
    feats = build_features(conn, country, cfg)
    if feats.empty:
        logger.warning("[STAGE %s] no features — skipping", country)
        return []
    # Drop the in-progress quarter: its quarter-end is in the future and its
    # inputs are partial. The latest snapshot is the last COMPLETED quarter.
    feats = feats[feats.index <= pd.Timestamp.today()]

    ccls = cfg["classification"]
    min_features = int(ccls["min_features"])
    min_score = float(ccls["min_score"])
    families = ["debt_pct", "debt_traj", "dsr_trend", "r_minus_g", "ngdp_minus_yield"]

    rows = []
    for qt, frow in feats.iterrows():
        n_feat = int(sum(
            1 for f in families
            if frow.get(f) is not None and not (isinstance(frow[f], float) and np.isnan(frow[f]))
        ))
        scores = score_stages(frow, cfg)
        valid = {k: v for k, v in scores.items() if not np.isnan(v)}
        if n_feat < min_features or not valid:
            raw = None
            confidence = None
        else:
            ordered = sorted(valid.items(), key=lambda kv: kv[1], reverse=True)
            top_stage, top = ordered[0]
            second = ordered[1][1] if len(ordered) > 1 else 0.0
            raw = top_stage if top >= min_score else "neutral"
            confidence = round(min(1.0, max(0.0, top - second)), 4)
        rows.append({"as_of": qt, "raw": raw, "confidence": confidence,
                     "n_features": n_feat, "scores": scores, "feats": frow})

    # Smooth the label sequence (rolling mode; ties keep the current label).
    raw_series = pd.Series([r["raw"] for r in rows],
                           index=[r["as_of"] for r in rows], dtype=object)
    smoothed = _rolling_mode(raw_series, int(ccls["smoothing_quarters"]))

    def _f(v) -> Optional[float]:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 4)

    missing_all = set(families)
    snaps = []
    for r, stage in zip(rows, smoothed.tolist()):
        frow = r["feats"]
        present = {f for f in families
                   if frow.get(f) is not None
                   and not (isinstance(frow[f], float) and np.isnan(frow[f]))}
        snaps.append(DebtCycleStageSnapshot(
            country=country,
            as_of=r["as_of"].date(),
            stage=stage if isinstance(stage, str) else None,
            stage_raw=r["raw"],
            confidence=r["confidence"],
            n_features=r["n_features"],
            missing_features=sorted(missing_all - present),
            score_leveraging=_f(r["scores"].get("leveraging")),
            score_squeeze=_f(r["scores"].get("squeeze")),
            score_deleveraging=_f(r["scores"].get("deleveraging")),
            score_reflation=_f(r["scores"].get("reflation")),
            feat_debt_pct=_f(frow.get("debt_pct")),
            feat_debt_traj=_f(frow.get("debt_traj")),
            feat_dsr_trend=_f(frow.get("dsr_trend")),
            feat_r_minus_g=_f(frow.get("r_minus_g")),
            feat_ngdp_minus_yield=_f(frow.get("ngdp_minus_yield")),
            feat_real_growth=_f(frow.get("real_growth")),
        ))
    return snaps

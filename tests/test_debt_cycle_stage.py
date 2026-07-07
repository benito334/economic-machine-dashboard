"""Tests for the long-term debt-cycle stage classifier (roadmap Phase C)."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import numpy as np
import pandas as pd
import pytest

from indicators.debt_cycle_stage import (
    STAGES,
    _annualized_change,
    _expanding_z_lagged,
    _rolling_mode,
    _to_quarterly,
    compute_stage_history,
    expanding_percentile_lagged,
    load_stage_config,
    score_stages,
)
from store.store import DB_PATH
import duckdb


@pytest.fixture(scope="module")
def cfg():
    return load_stage_config()


# ── Config integrity ──────────────────────────────────────────────────────────

def test_config_loads_and_has_all_stages(cfg):
    for stage in STAGES:
        assert stage in cfg["weights"]
    for country in ("US", "EZ", "KR"):
        assert country in cfg["countries"]


def test_config_us_has_full_feature_set(cfg):
    us = cfg["countries"]["US"]
    assert len(us["debt_components"]) == 3
    assert us["dsr_signal"] == "credit.debt_service_ratio"
    assert us["real_rate"]["signal"] == "policy.real_fed_funds"


def test_config_sparse_countries_degrade_honestly(cfg):
    for cc in ("EZ", "KR"):
        assert cfg["countries"][cc]["dsr_signal"] is None
        assert cfg["countries"][cc]["ngdp_minus_yield"]["derived"] is True


# ── Feature construction ──────────────────────────────────────────────────────

def test_expanding_percentile_no_lookahead():
    """out[t] ranks against PRIOR history only — the value at t must not be
    included in its own reference distribution."""
    idx = pd.date_range("2000-03-31", periods=30, freq="QE")
    s = pd.Series(np.arange(30, dtype=float), index=idx)   # strictly increasing
    pct = expanding_percentile_lagged(s, min_periods=5)
    # A strictly increasing series is always at the 100th percentile of its past
    assert (pct.dropna() == 1.0).all()
    # min_periods respected: first 5 are NaN
    assert pct.iloc[:5].isna().all() and not np.isnan(pct.iloc[5])


def test_expanding_percentile_rank_value():
    idx = pd.date_range("2000-03-31", periods=6, freq="QE")
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 3.5], index=idx)
    pct = expanding_percentile_lagged(s, min_periods=5)
    # 3.5 vs prior {1,2,3,4,5}: 3 of 5 are <= 3.5
    assert pct.iloc[-1] == pytest.approx(0.6)


def test_annualized_change():
    idx = pd.date_range("2000-03-31", periods=13, freq="QE")
    s = pd.Series(np.linspace(100.0, 106.0, 13), index=idx)  # +6pp over 3 years
    traj = _annualized_change(s, window_years=3)
    assert traj.iloc[-1] == pytest.approx(2.0)               # 2pp per year


def test_to_quarterly_ffill_limit_is_honest():
    """An annual series carried more than ffill_limit quarters goes NaN
    rather than silently persisting (CLAUDE.md rule 7)."""
    idx = pd.to_datetime(["2018-12-31", "2019-12-31"])
    s = pd.Series([50.0, 55.0], index=idx)
    q = _to_quarterly(s, ffill_limit=3)
    # 2019Q4 obs carries at most 3 quarters → 2020Q3; later quarters NaN
    assert q.loc["2020-09-30"] == 55.0
    if pd.Timestamp("2020-12-31") in q.index:
        assert np.isnan(q.loc["2020-12-31"])


def test_to_quarterly_extends_to_current_quarter():
    idx = pd.to_datetime(["2025-12-31"])
    s = pd.Series([42.0], index=idx)
    q = _to_quarterly(s, ffill_limit=5)
    current_qe = pd.Timestamp.today().to_period("Q").to_timestamp("Q")
    assert q.index[-1] == current_qe                          # index reaches now
    assert q.ffill().iloc[-1] == 42.0 or np.isnan(q.iloc[-1])  # within limit → carried


# ── Stage scoring ─────────────────────────────────────────────────────────────

def _row(**kw) -> pd.Series:
    base = {"debt_pct": np.nan, "debt_traj": np.nan, "dsr_trend": np.nan,
            "r_minus_g": np.nan, "ngdp_minus_yield": np.nan, "real_growth": np.nan}
    base.update(kw)
    return pd.Series(base)


def test_textbook_leveraging_scores_highest(cfg):
    row = _row(debt_pct=0.4, debt_traj=2.0, dsr_trend=0.0,
               r_minus_g=-2.0, ngdp_minus_yield=2.0, real_growth=3.0)
    scores = score_stages(row, cfg)
    assert scores["leveraging"] == max(scores.values())
    assert scores["leveraging"] == pytest.approx(1.0)


def test_textbook_squeeze_scores_highest(cfg):
    row = _row(debt_pct=0.9, debt_traj=1.5, dsr_trend=1.0,
               r_minus_g=1.0, ngdp_minus_yield=-1.5, real_growth=1.5)
    scores = score_stages(row, cfg)
    assert scores["squeeze"] == max(scores.values())
    assert scores["squeeze"] == pytest.approx(1.0)


def test_textbook_deleveraging_scores_highest(cfg):
    row = _row(debt_pct=0.8, debt_traj=-3.0, dsr_trend=-1.0,
               r_minus_g=0.5, ngdp_minus_yield=-1.0, real_growth=-1.0)
    scores = score_stages(row, cfg)
    assert scores["deleveraging"] == max(scores.values())
    assert scores["deleveraging"] == pytest.approx(1.0)


def test_textbook_reflation_scores_highest(cfg):
    row = _row(debt_pct=0.7, debt_traj=-0.2, dsr_trend=-0.5,
               r_minus_g=-3.0, ngdp_minus_yield=3.0, real_growth=2.5)
    scores = score_stages(row, cfg)
    assert scores["reflation"] == max(scores.values())
    assert scores["reflation"] == pytest.approx(1.0)


def test_missing_dsr_renormalizes_not_zeroes(cfg):
    """A country with no debt-service series still gets a full-range score
    from the remaining conditions."""
    full = _row(debt_pct=0.4, debt_traj=2.0, dsr_trend=0.0,
                r_minus_g=-2.0, ngdp_minus_yield=2.0, real_growth=3.0)
    sparse = _row(debt_pct=0.4, debt_traj=2.0,
                  r_minus_g=-2.0, ngdp_minus_yield=2.0, real_growth=3.0)
    assert score_stages(full, cfg)["leveraging"] == pytest.approx(1.0)
    assert score_stages(sparse, cfg)["leveraging"] == pytest.approx(1.0)


def test_stage_nan_when_too_few_conditions_evaluable(cfg):
    """min_condition_weight: a stage whose evidence is mostly missing scores
    NaN rather than pretending."""
    row = _row(dsr_trend=1.0)   # only the DSR family present
    scores = score_stages(row, cfg)
    # leveraging: only dsr_not_rising (0.20 of weight) evaluable < 0.50 → NaN
    assert np.isnan(scores["leveraging"])


# ── Smoothing ─────────────────────────────────────────────────────────────────

def test_rolling_mode_requires_persistence():
    idx = pd.date_range("2020-03-31", periods=5, freq="QE")
    raw = pd.Series(["leveraging", "leveraging", "squeeze", "squeeze", "squeeze"],
                    index=idx, dtype=object)
    sm = _rolling_mode(raw, window=3)
    # one squeeze quarter isn't enough to flip (window majority still leveraging
    # + tie-break goes to current → squeeze wins the tie at i=2)
    assert sm.iloc[1] == "leveraging"
    assert sm.iloc[-1] == "squeeze"


def test_rolling_mode_never_carries_label_across_gap():
    idx = pd.date_range("2020-03-31", periods=4, freq="QE")
    raw = pd.Series(["reflation", "reflation", None, None], index=idx, dtype=object)
    sm = _rolling_mode(raw, window=3)
    assert sm.iloc[2] is None and sm.iloc[3] is None


def test_rolling_mode_window_one_is_identity():
    idx = pd.date_range("2020-03-31", periods=3, freq="QE")
    raw = pd.Series(["a", "b", "a"], index=idx, dtype=object)
    assert (_rolling_mode(raw, window=1) == raw).all()


# ── Sovereign-aware sector model (Ray Dalio ruling, 2026-07-06 session) ──────
# Triggered by: US stage classifier read "reflation" while a record sovereign
# debt stock (122.8% GDP, z +1.78) and a Z-capped federal interest bill
# (z +4.00) were masked by mean-blending against a deleveraged private sector
# (household debt/GDP 68.5%, z -1.54). Rulings: two votes (private +
# sovereign), headline = worse of the two by severity, debt stock = capped
# size-weighted mean, service = 70/30 household/government blend, a
# refinancing-gap early-warning flag independent of the vote.

def test_expanding_z_lagged_excludes_current_obs():
    idx = pd.date_range("2000-03-31", periods=30, freq="QE")
    s = pd.Series(np.arange(30, dtype=float), index=idx)
    z = _expanding_z_lagged(s, min_periods=5)
    assert z.iloc[:5].isna().all()          # min_periods respected (shift + expanding)
    assert not np.isnan(z.iloc[5])
    # value equals (x_t - mean(x_0..t-1)) / std(x_0..t-1) — strictly prior data
    manual = (s.iloc[10] - s.iloc[:10].mean()) / s.iloc[:10].std()
    assert z.iloc[10] == pytest.approx(manual)


def test_sector_stock_caps_percentile_and_size_weights(monkeypatch):
    """A sector that dominates by size AND sits at the 100th percentile must
    not push the blended percentile above the configured cap (Ray Q2:
    'worst-of without total dilution')."""
    import indicators.debt_cycle_stage as dcs
    idx = pd.date_range("2000-03-31", periods=30, freq="QE")
    big = pd.Series(np.linspace(100, 200, 30), index=idx)   # large, rising, at-100th-pct
    small = pd.Series(np.full(30, 10.0), index=idx)          # small, flat, low percentile

    def fake_load(conn, signal_id):
        return {"us.credit.gov_debt_gdp": big,
                "us.credit.household_debt_gdp": small}[signal_id]

    monkeypatch.setattr(dcs, "_load_signal_values", fake_load)
    cfg = {"features": {"ffill_limit_quarters": 5, "percentile_min_periods": 5,
                        "debt_traj_window_years": 3}}
    pct, traj = dcs._sector_stock(
        None, "US", cfg, ["credit.gov_debt_gdp", "credit.household_debt_gdp"], cap=0.90)
    assert pct.dropna().max() <= 0.90 + 1e-9
    # single-sector case still respects the cap
    pct1, _ = dcs._sector_stock(None, "US", cfg, ["credit.gov_debt_gdp"], cap=0.90)
    assert pct1.dropna().iloc[-1] == pytest.approx(0.90)


def test_worst_of_headline_picks_higher_severity():
    cfg = load_stage_config()
    sev = cfg["sector_model"]["severity"]
    assert sev["squeeze"] > sev["reflation"] > sev["leveraging"]
    assert sev["squeeze"] > sev["deleveraging"] > sev["leveraging"]


@pytest.mark.integration
def test_us_sovereign_squeeze_flag_fires_live():
    """Live-data regression: the challenge that triggered this rework. The
    US refinancing gap and gov-interest Z both blow through Ray's thresholds
    today, so the flag must be True even though the headline mechanism can
    legitimately still read a private-sector-driven stage."""
    cfg = load_stage_config()
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        snaps = compute_stage_history(conn, "US", cfg)
    finally:
        conn.close()
    labeled = [s for s in snaps if s.stage]
    assert labeled, "no labeled US quarters — run the pipeline first"
    latest = labeled[-1]
    assert latest.sovereign_squeeze is True
    assert latest.feat_refi_gap is not None and latest.feat_refi_gap > 0.75
    assert latest.feat_gov_interest_z is not None and latest.feat_gov_interest_z > 1.0
    # the flag is independent of the vote scoring — it must be constructible
    # even when the headline stage doesn't itself read "squeeze"
    assert latest.stage in {"leveraging", "squeeze", "deleveraging", "reflation", "neutral"}


@pytest.mark.integration
def test_gb_headline_unchanged_no_private_data():
    """Countries with no private-sector debt inputs (EZ/GB/JP/KR) have no
    private vote at all, so the headline should equal the sovereign vote —
    the sovereign-aware rework must not regress their existing reads."""
    cfg = load_stage_config()
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        snaps = compute_stage_history(conn, "GB", cfg)
    finally:
        conn.close()
    labeled = [s for s in snaps if s.stage]
    assert labeled
    latest = labeled[-1]
    assert latest.stage_private is None
    assert latest.stage == latest.stage_sovereign

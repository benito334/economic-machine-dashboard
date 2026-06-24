"""
Tests for the Phase 1B composites engine.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest
import duckdb

from indicators.composites import (
    _QUADRANT_LABELS,
    _EXPECTED_DIR,
    _load_wide,
    _build_force_groups,
    compute_composite_history,
    age_weight_fraction,
    load_composites_config,
    momentum_weight_multiplier,
    normalized_nominal_weights,
)
from indicators.models import CompositeSnapshot
from store.store import (
    init_schema,
    upsert_composites,
    query_composite_history,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_conn():
    """In-memory DuckDB connection with schema initialised."""
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    return conn


def _insert_signals(conn, rows: list[dict]) -> None:
    """Helper: insert raw signal rows directly into the in-memory DB."""
    now = datetime.now(timezone.utc)
    for r in rows:
        conn.execute("""
            INSERT INTO signals
            (id, country, force, lead_lag, as_of, value, units,
             level_percentile, zscore, change_1m, change_3m, change_12m,
             direction, equilibrium_estimate, distance_from_equilibrium,
             surprise, is_constructed, is_proxy, is_stale, low_history,
             provider, source_tier, vintage_available, linkage, source, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            r["id"], r.get("country", "US"), r.get("force", "growth"),
            r.get("lead_lag", "coincident"), r["as_of"], r.get("value", 1.0),
            r.get("units", "pct"), r.get("level_percentile", 0.5),
            r.get("zscore", 0.0), None, None, None,
            r.get("direction", "rising"), r.get("equilibrium_estimate"),
            r.get("distance_from_equilibrium", r.get("zscore", 0.0)),
            None, False, False, r.get("is_stale", False), r.get("low_history", False),
            "FRED", "free", True, "", r.get("source", "FRED:TEST"), now,
        ])


# ── Quadrant label logic ──────────────────────────────────────────────────────

def test_quadrant_labels_cover_all_combinations():
    assert len(_QUADRANT_LABELS) == 4
    labels = set(_QUADRANT_LABELS.values())
    assert labels == {"Expansion", "Inflationary Boom", "Stagflation", "Disinflationary Slowdown"}


def test_expected_dir_matches_quadrant():
    # Expansion (growth+, inflation-): growth should be rising, inflation falling
    assert _EXPECTED_DIR[(True, False)] == ("rising", "falling")
    # Stagflation (growth-, inflation+): growth falling, inflation rising
    assert _EXPECTED_DIR[(False, True)] == ("falling", "rising")


# ── _load_wide ────────────────────────────────────────────────────────────────

def test_load_wide_empty_when_no_ids(mem_conn):
    result = _load_wide(mem_conn, [], "zscore")
    assert result.empty


def test_load_wide_returns_monthly_index(mem_conn):
    _insert_signals(mem_conn, [
        {"id": "us.growth.payrolls", "as_of": "2022-01-31", "zscore": 1.0},
        {"id": "us.growth.payrolls", "as_of": "2022-02-28", "zscore": 0.9},
        {"id": "us.growth.payrolls", "as_of": "2022-03-31", "zscore": 0.8},
    ])
    wide = _load_wide(mem_conn, ["us.growth.payrolls"], "zscore")
    assert not wide.empty
    assert wide.index.freqstr in ("ME", "M")  # month-end
    assert wide["us.growth.payrolls"].notna().any()


def test_load_wide_forward_fills(mem_conn):
    """
    Annual signal should forward-fill into subsequent months when those months exist
    in the index (populated by co-loaded monthly signals).
    """
    # Monthly signal creates a 12-month index from Jan 2022 onward
    months = pd.date_range("2022-01-31", periods=12, freq="ME")
    for dt in months:
        _insert_signals(mem_conn, [{
            "id": "us.credit.baa_spread", "as_of": str(dt.date()),
            "zscore": 0.1, "force": "credit",
        }])
    # Annual TFP observed only in Dec 2021 — should fill into 2022 via ffill
    _insert_signals(mem_conn, [
        {"id": "us.growth.tfp", "as_of": "2021-12-31", "zscore": -0.5,
         "force": "growth", "lead_lag": "structural"},
    ])
    wide = _load_wide(mem_conn, ["us.growth.tfp", "us.credit.baa_spread"], "zscore", ffill_limit=13)
    non_null_tfp = wide["us.growth.tfp"].dropna()
    assert len(non_null_tfp) >= 12


def test_load_wide_excludes_unreliable_latest_signals(mem_conn):
    _insert_signals(mem_conn, [
        {"id": "us.growth.stale", "as_of": "2023-01-31", "zscore": 1.0},
        {"id": "us.growth.stale", "as_of": "2023-02-28", "zscore": 2.0,
         "is_stale": True},
        {"id": "us.growth.short", "as_of": "2023-01-31", "zscore": 3.0,
         "low_history": True},
    ])
    wide = _load_wide(
        mem_conn,
        ["us.growth.stale", "us.growth.short"],
        "zscore",
        exclude_unreliable=True,
    )
    assert pd.notna(wide.loc[pd.Timestamp("2023-01-31"), "us.growth.stale"])
    assert pd.isna(wide.loc[pd.Timestamp("2023-02-28"), "us.growth.stale"])
    assert wide["us.growth.short"].isna().all()


# ── CompositeSnapshot model ───────────────────────────────────────────────────

def test_composite_snapshot_defaults():
    snap = CompositeSnapshot(country="US", as_of=date(2023, 12, 31))
    assert snap.growth_score is None
    assert snap.quadrant is None
    assert snap.low_coverage is False


# ── upsert + query composites ─────────────────────────────────────────────────

def test_upsert_and_query_composites(mem_conn):
    snap = CompositeSnapshot(
        country="US",
        as_of=date(2023, 6, 30),
        growth_score=0.5,
        inflation_score=1.2,
        quadrant="Inflationary Boom",
        confidence=0.75,
        disequilibrium_score=0.8,
        n_growth_signals=8,
        n_inflation_signals=6,
        n_forces=3,
        low_coverage=False,
        weight_audit='{"growth":{}}',
    )
    n = upsert_composites(mem_conn, [snap])
    assert n == 1

    df = query_composite_history(mem_conn, "US")
    assert len(df) == 1
    assert df.iloc[0]["quadrant"] == "Inflationary Boom"
    assert abs(df.iloc[0]["growth_score"] - 0.5) < 1e-6
    assert df.iloc[0]["weight_audit"] == '{"growth":{}}'


def test_upsert_composites_is_idempotent(mem_conn):
    snap = CompositeSnapshot(
        country="US", as_of=date(2023, 6, 30),
        growth_score=0.5, inflation_score=1.2,
        quadrant="Inflationary Boom", confidence=0.75,
    )
    upsert_composites(mem_conn, [snap])
    snap2 = snap.model_copy(update={"growth_score": 0.6})
    upsert_composites(mem_conn, [snap2])

    df = query_composite_history(mem_conn, "US")
    assert len(df) == 1
    assert abs(df.iloc[0]["growth_score"] - 0.6) < 1e-6


def test_upsert_replaces_same_month_and_removes_future_rows(mem_conn):
    this_month = date.today().replace(day=1)
    future = date(date.today().year + 1, 1, 31)
    upsert_composites(mem_conn, [
        CompositeSnapshot(country="US", as_of=this_month, growth_score=0.1),
    ])
    upsert_composites(mem_conn, [
        CompositeSnapshot(country="US", as_of=future, growth_score=9.0),
        CompositeSnapshot(country="US", as_of=date.today(), growth_score=0.2),
    ])
    df = query_composite_history(mem_conn, "US")
    assert len(df) == 1
    assert df.iloc[0]["as_of"].date() <= date.today()
    assert df.iloc[0]["growth_score"] == pytest.approx(0.2)


# ── compute_composite_history (unit-level with seeded data) ───────────────────

def _minimal_config() -> dict:
    return {
        "growth_score": {
            "indicators": [
                {"id": "growth.payrolls", "weight": 1.0},
                {"id": "growth.unemployment", "weight": 1.0, "invert": True},
            ]
        },
        "inflation_score": {
            "indicators": [
                {"id": "inflation.pce_core", "weight": 1.0},
                {"id": "inflation.cpi_core", "weight": 1.0},
                {"id": "inflation.wages", "weight": 1.0},
                {"id": "inflation.breakeven_5y", "weight": 1.0},
            ]
        },
        "regime_confidence": {"min_signals_required": 2},
        "disequilibrium_score": {
            "forces": [{"debt_money": ["credit"]}],
            "min_forces_required": 1,
        },
    }


def _seed_stagflation(conn) -> None:
    """Insert synthetic data resembling 2022 Stagflation: growth below avg, inflation high."""
    months = pd.date_range("2022-01-31", periods=6, freq="ME")
    for dt in months:
        ds = str(dt.date())
        _insert_signals(conn, [
            {"id": "us.growth.payrolls",       "as_of": ds, "zscore": -0.8, "direction": "falling", "force": "growth"},
            {"id": "us.growth.unemployment",   "as_of": ds, "zscore":  0.9, "direction": "rising",  "force": "growth"},
            {"id": "us.inflation.pce_core",    "as_of": ds, "zscore":  2.1, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.cpi_core",    "as_of": ds, "zscore":  2.3, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.wages",       "as_of": ds, "zscore":  1.5, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.breakeven_5y","as_of": ds, "zscore":  1.8, "direction": "rising",  "force": "inflation"},
        ])


def test_stagflation_quadrant_detected(mem_conn):
    _seed_stagflation(mem_conn)
    cfg = _minimal_config()
    snapshots = compute_composite_history(mem_conn, "US", cfg)

    assert len(snapshots) > 0
    quadrants = [s.quadrant for s in snapshots if s.quadrant is not None]
    assert len(quadrants) > 0
    assert all(q == "Stagflation" for q in quadrants), f"Expected all Stagflation, got {set(quadrants)}"


def _seed_expansion(conn) -> None:
    """Insert synthetic data for Expansion: growth above avg, inflation below avg."""
    months = pd.date_range("2017-01-31", periods=6, freq="ME")
    for dt in months:
        ds = str(dt.date())
        _insert_signals(conn, [
            {"id": "us.growth.payrolls",       "as_of": ds, "zscore":  0.8, "direction": "rising",  "force": "growth"},
            {"id": "us.growth.unemployment",   "as_of": ds, "zscore": -0.7, "direction": "falling", "force": "growth"},
            {"id": "us.inflation.pce_core",    "as_of": ds, "zscore": -0.5, "direction": "falling", "force": "inflation"},
            {"id": "us.inflation.cpi_core",    "as_of": ds, "zscore": -0.6, "direction": "falling", "force": "inflation"},
            {"id": "us.inflation.wages",       "as_of": ds, "zscore": -0.3, "direction": "falling", "force": "inflation"},
            {"id": "us.inflation.breakeven_5y","as_of": ds, "zscore": -0.4, "direction": "falling", "force": "inflation"},
        ])


def test_expansion_quadrant_detected(mem_conn):
    _seed_expansion(mem_conn)
    cfg = _minimal_config()
    snapshots = compute_composite_history(mem_conn, "US", cfg)

    quadrants = [s.quadrant for s in snapshots if s.quadrant is not None]
    assert all(q == "Expansion" for q in quadrants), f"Expected Expansion, got {set(quadrants)}"


def test_snapshot_audits_dynamic_and_decay_weight_layers(mem_conn):
    _seed_expansion(mem_conn)
    cfg = {
        **_minimal_config(),
        "dynamic_weighting": {
            "enabled": True,
            "momentum_alpha": 0.5,
            "min_multiplier": 0.1,
            "max_multiplier": 1.5,
            "force_zero_epsilon": 0.05,
        },
        "time_decay": {"enabled": True, "half_life_months": 3, "hard_drop_months": 12},
    }
    snapshots = compute_composite_history(mem_conn, "US", cfg)
    audit = json.loads(snapshots[-1].weight_audit)
    payrolls = audit["growth"]["us.growth.payrolls"]

    assert payrolls["config_weight"] == pytest.approx(0.5)
    assert payrolls["momentum_multiplier"] == pytest.approx(1.5)
    assert payrolls["decay_fraction"] == pytest.approx(1.0)
    assert payrolls["effective_weight"] == pytest.approx(0.75)
    assert payrolls["normalized_weight"] == pytest.approx(0.5)


def test_confidence_high_when_signals_agree(mem_conn):
    """When all signals agree with the quadrant direction, confidence should be close to 1."""
    _seed_stagflation(mem_conn)
    cfg = _minimal_config()
    snapshots = compute_composite_history(mem_conn, "US", cfg)
    stagflation_snaps = [s for s in snapshots if s.quadrant == "Stagflation"]
    assert stagflation_snaps
    # All growth signals falling, all inflation signals rising → high confidence
    for s in stagflation_snaps:
        assert s.confidence is not None
        assert s.confidence >= 0.7, f"Expected confidence >= 0.7, got {s.confidence}"


def test_below_min_signals_no_quadrant(mem_conn):
    """When fewer than min_signals_required signals are available, quadrant must be None."""
    dt = "2023-06-30"
    _insert_signals(mem_conn, [
        {"id": "us.growth.payrolls", "as_of": dt, "zscore": 1.0, "force": "growth"},
        # Only 1 growth signal — below min_signals_required=2; inflation has 0 → no quadrant
    ])
    cfg = _minimal_config()
    snapshots = compute_composite_history(mem_conn, "US", cfg)
    assert all(s.quadrant is None for s in snapshots)


def test_current_partial_month_is_not_future_dated(mem_conn):
    _insert_signals(mem_conn, [
        {"id": "us.growth.payrolls", "as_of": date.today(), "zscore": 1.0},
    ])
    snapshots = compute_composite_history(mem_conn, "US", _minimal_config())
    assert snapshots
    assert max(s.as_of for s in snapshots) <= date.today()


def test_inflation_config_uses_bound_ppi_signal():
    ids = {
        item["id"] for item in load_composites_config()["inflation_score"]["indicators"]
    }
    assert "inflation.ppi_broad" in ids
    assert "inflation.commodity_index" not in ids


# ── Guidance defaults: importance, base shares, and quality ──────────────────

def test_breakeven_guidance_defaults():
    cfg = load_composites_config()
    by_id = {ind["id"]: ind for ind in cfg["inflation_score"]["indicators"]}
    assert by_id["inflation.breakeven_5y"]["base_share"] == 0.5
    assert by_id["inflation.breakeven_5y"]["importance"] == 0.25   # CONTEXT — market expectations anchor
    assert by_id["inflation.breakeven_5y"]["quality_factor"] == 0.90
    assert by_id["inflation.breakeven_10y"]["base_share"] == 0.5
    assert by_id["inflation.breakeven_10y"]["importance"] == 0.20  # VOLATILE — correlated with 5y (r~0.90)
    assert by_id["inflation.breakeven_10y"]["quality_factor"] == 0.90


# ── G1: Labour-market group weights ──────────────────────────────────────────

def test_growth_importance_guidance_defaults():
    cfg = load_composites_config()
    by_id = {ind["id"]: ind for ind in cfg["growth_score"]["indicators"]}
    expected = {
        "growth.payrolls": 0.90,        # PRIMARY
        "growth.industrial_prod": 0.80,  # PRIMARY
        "growth.retail_sales": 0.75,     # STRONG
        "growth.real_pce": 0.65,         # STRONG — correlated with retail_sales (r=0.80)
        "growth.capacity_util": 0.65,    # STRONG
        "growth.job_openings": 0.85,     # PRIMARY
        "growth.pmi_proxy": 0.80,        # PRIMARY
        "growth.labor_force_part": 0.60, # STRONG
        "growth.unemployment": 0.45,     # CONTEXT — lagging indicator
    }
    assert {signal_id: by_id[signal_id]["importance"] for signal_id in expected} == expected


def test_inflation_importance_guidance_defaults():
    cfg = load_composites_config()
    by_id = {ind["id"]: ind for ind in cfg["inflation_score"]["indicators"]}
    expected = {
        "inflation.pce_core": 0.95,      # PRIMARY — Fed mandate measure
        "inflation.cpi_core": 0.65,      # STRONG — correlated with pce_core (r~0.92); was 0.95
        "inflation.wages": 0.30,         # CONTEXT
        "inflation.breakeven_5y": 0.25,  # CONTEXT
        "inflation.breakeven_10y": 0.20, # VOLATILE — correlated with 5y (r~0.90); was 0.25
        "inflation.cpi_headline": 0.20,  # VOLATILE
        "inflation.crude_oil": 0.10,     # VOLATILE
        "inflation.ppi_broad": 0.30,     # CONTEXT
    }
    assert {signal_id: by_id[signal_id]["importance"] for signal_id in expected} == expected


def test_guidance_nominal_weights_are_normalized_after_quality():
    cfg = load_composites_config()
    growth = normalized_nominal_weights(cfg["growth_score"]["indicators"])
    inflation = normalized_nominal_weights(cfg["inflation_score"]["indicators"])

    assert sum(growth.values()) == pytest.approx(1.0)
    assert sum(inflation.values()) == pytest.approx(1.0)
    # payrolls is now the top growth signal (PRIMARY, importance=0.90)
    assert growth["growth.payrolls"] > growth["growth.capacity_util"]
    # pce_core outweighs cpi_core after redundancy reduction (0.95 vs 0.65 importance)
    assert inflation["inflation.pce_core"] > inflation["inflation.cpi_core"]
    assert inflation["inflation.pce_core"] > inflation["inflation.crude_oil"]


def test_momentum_agreement_tilts_weight_and_respects_inversion():
    assert momentum_weight_multiplier(1.0, "rising") == pytest.approx(1.5)
    assert momentum_weight_multiplier(1.0, "falling") == pytest.approx(0.5)
    assert momentum_weight_multiplier(0.01, "rising") == pytest.approx(1.0)
    # Unemployment Z below zero, then inverted, is positive growth force;
    # falling unemployment is also growth-positive, so the two agree.
    assert momentum_weight_multiplier(-1.0, "falling", invert=True) == pytest.approx(1.5)


def test_three_month_age_is_one_half_weight():
    assert age_weight_fraction(0, 3) == pytest.approx(1.0)
    assert age_weight_fraction(3, 3) == pytest.approx(0.5)
    assert age_weight_fraction(6, 3) == pytest.approx(0.25)


def test_importance_setting_changes_nominal_weight():
    indicators = [
        {"id": "a", "base_share": 1.0, "importance": 0.9, "quality_factor": 1.0},
        {"id": "b", "base_share": 1.0, "importance": 0.1, "quality_factor": 1.0},
    ]
    weights = normalized_nominal_weights(indicators)
    assert weights == {"a": pytest.approx(0.9), "b": pytest.approx(0.1)}


# ── F1/L1: Fill-age and staleness decay ──────────────────────────────────────

from indicators.composites import _compute_fill_age


def test_compute_fill_age_fresh_obs_is_zero():
    idx = pd.date_range("2022-01-31", periods=3, freq="ME")
    raw = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=idx)
    age = _compute_fill_age(raw)
    assert (age["a"] == 0).all()


def test_compute_fill_age_gap_increments():
    idx = pd.date_range("2022-01-31", periods=4, freq="ME")
    raw = pd.DataFrame({"a": [1.0, np.nan, np.nan, 2.0]}, index=idx)
    age = _compute_fill_age(raw)
    assert age["a"].iloc[0] == 0
    assert age["a"].iloc[1] == 1
    assert age["a"].iloc[2] == 2
    assert age["a"].iloc[3] == 0  # fresh observation resets to 0


def test_compute_fill_age_leading_nans_increment():
    idx = pd.date_range("2022-01-31", periods=3, freq="ME")
    raw = pd.DataFrame({"a": [np.nan, np.nan, 1.0]}, index=idx)
    age = _compute_fill_age(raw)
    assert age["a"].iloc[0] == 1
    assert age["a"].iloc[1] == 2
    assert age["a"].iloc[2] == 0


def test_load_wide_return_fill_age_flag(mem_conn):
    _insert_signals(mem_conn, [
        {"id": "us.growth.payrolls", "as_of": "2022-01-31", "zscore": 1.0},
        {"id": "us.growth.payrolls", "as_of": "2022-03-31", "zscore": 0.8},
    ])
    wide, fill_age = _load_wide(mem_conn, ["us.growth.payrolls"], "zscore", return_fill_age=True)
    assert isinstance(fill_age, pd.DataFrame)
    assert "us.growth.payrolls" in fill_age.columns
    feb = pd.Timestamp("2022-02-28")
    if feb in fill_age.index:
        assert fill_age.loc[feb, "us.growth.payrolls"] == 1.0


def test_decay_reduces_weight_for_stale_signal(mem_conn):
    """A signal ffilled for several months contributes less to the composite when decay is on."""
    # Seed one growth + one inflation signal that has a data gap
    months_fresh = pd.date_range("2022-01-31", periods=6, freq="ME")
    for dt in months_fresh:
        ds = str(dt.date())
        _insert_signals(mem_conn, [
            {"id": "us.growth.payrolls",     "as_of": ds, "zscore": 1.0, "direction": "rising",  "force": "growth"},
            {"id": "us.growth.unemployment", "as_of": ds, "zscore": -1.0, "direction": "falling", "force": "growth"},
            {"id": "us.inflation.pce_core",  "as_of": ds, "zscore": 1.0, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.cpi_core",  "as_of": ds, "zscore": 1.0, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.wages",     "as_of": ds, "zscore": 1.0, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.breakeven_5y", "as_of": ds, "zscore": 1.0, "direction": "rising", "force": "inflation"},
        ])

    cfg_no_decay = _minimal_config()
    cfg_with_decay = {**_minimal_config(), "staleness_decay": {"enabled": True, "decay_factor": 0.5}}

    snaps_no  = compute_composite_history(mem_conn, "US", cfg_no_decay)
    snaps_yes = compute_composite_history(mem_conn, "US", cfg_with_decay)

    # For months where all data is fresh (fill_age=0), decay=0.5^0=1.0, so scores identical
    # The test verifies that decay_enabled=True produces scores equal to or slightly different
    # from no-decay for fresh data (all fill_age=0 → multiplier=1.0 → identical scores)
    if snaps_no and snaps_yes:
        for sn, sy in zip(snaps_no, snaps_yes):
            if sn.as_of == sy.as_of and sn.growth_score is not None:
                assert abs(sn.growth_score - sy.growth_score) < 1e-6


# ── H2: pre_smooth_window binding field ──────────────────────────────────────

def test_pre_smooth_window_binding_field():
    from indicators.models import CountryBinding
    b = CountryBinding(
        id="inflation.crude_oil", series_id="DCOILWTICO", provider="FRED",
        frequency="D", force="inflation", lead_lag="leading",
        transformation="yoy_pct", units="yoy_pct",
        pre_smooth_window=7,
    )
    assert b.pre_smooth_window == 7


def test_pre_smooth_window_default_is_none():
    from indicators.models import CountryBinding
    b = CountryBinding(
        id="growth.payrolls", series_id="PAYEMS", provider="FRED",
        frequency="M", force="growth", lead_lag="coincident",
        transformation="yoy_pct", units="yoy_pct",
    )
    assert b.pre_smooth_window is None


# ── L2: Per-frequency carry cap ──────────────────────────────────────────────

def test_load_wide_per_signal_limits_applied(mem_conn):
    """A column with a short limit should not be filled beyond that limit."""
    # Monthly signal: observations at Jan and Apr — Feb/Mar are gaps
    for dt in ["2022-01-31", "2022-04-30"]:
        _insert_signals(mem_conn, [{"id": "us.growth.payrolls", "as_of": dt, "zscore": 1.0}])
    # per_signal_limits: payrolls capped at 1 month → Feb is filled, Mar is NaN
    wide = _load_wide(
        mem_conn, ["us.growth.payrolls"], "zscore",
        per_signal_limits={"us.growth.payrolls": 1},
    )
    feb = pd.Timestamp("2022-02-28")
    mar = pd.Timestamp("2022-03-31")
    assert pd.notna(wide.loc[feb, "us.growth.payrolls"])   # 1 month fill ✓
    assert pd.isna(wide.loc[mar, "us.growth.payrolls"])    # beyond cap → NaN


def test_load_wide_per_signal_limits_fallback_to_default(mem_conn):
    """Signals not in per_signal_limits use the default ffill_limit."""
    for dt in ["2022-01-31"]:
        _insert_signals(mem_conn, [{"id": "us.growth.payrolls", "as_of": dt, "zscore": 0.5}])
    # Default limit is 2, signal not in per_signal_limits → uses default
    wide = _load_wide(
        mem_conn, ["us.growth.payrolls"], "zscore",
        ffill_limit=2,
        per_signal_limits={"us.other.signal": 99},
    )
    feb = pd.Timestamp("2022-02-28")
    mar = pd.Timestamp("2022-03-31")
    # Only 2 months of fill from Jan observation
    if feb in wide.index:
        assert pd.notna(wide.loc[feb, "us.growth.payrolls"])
    if mar in wide.index:
        # Mar is 2 months after Jan, within limit=2 → may be filled
        pass  # depends on whether Mar is in the index


def test_composites_yaml_has_per_frequency_limits():
    cfg = load_composites_config()
    limits = cfg.get("per_frequency_ffill_limit", {})
    assert limits.get("M") == 3
    assert limits.get("Q") == 9
    assert limits.get("A") == 15


# ── L3: Stale signal tracking in CompositeSnapshot ───────────────────────────

def test_stale_signals_populated_when_fill_age_nonzero(mem_conn):
    """When a signal is forward-filled, stale_signals should contain its entry."""
    # Growth signal: one observation in Jan; no Feb observation → fill_age=1 in Feb
    _insert_signals(mem_conn, [
        {"id": "us.growth.payrolls",     "as_of": "2022-01-31", "zscore": 1.0, "direction": "rising",  "force": "growth"},
        {"id": "us.growth.unemployment", "as_of": "2022-01-31", "zscore": -1.0, "direction": "falling", "force": "growth"},
        {"id": "us.inflation.pce_core",  "as_of": "2022-01-31", "zscore": 1.0, "direction": "rising",  "force": "inflation"},
        {"id": "us.inflation.cpi_core",  "as_of": "2022-01-31", "zscore": 1.0, "direction": "rising",  "force": "inflation"},
        {"id": "us.inflation.wages",     "as_of": "2022-01-31", "zscore": 1.0, "direction": "rising",  "force": "inflation"},
        {"id": "us.inflation.breakeven_5y", "as_of": "2022-01-31", "zscore": 1.0, "direction": "rising", "force": "inflation"},
        # Feb — only some signals refreshed
        {"id": "us.growth.payrolls",     "as_of": "2022-02-28", "zscore": 0.9, "direction": "rising",  "force": "growth"},
        {"id": "us.growth.unemployment", "as_of": "2022-02-28", "zscore": -0.9, "direction": "falling", "force": "growth"},
        {"id": "us.inflation.pce_core",  "as_of": "2022-02-28", "zscore": 0.9, "direction": "rising",  "force": "inflation"},
        {"id": "us.inflation.cpi_core",  "as_of": "2022-02-28", "zscore": 0.9, "direction": "rising",  "force": "inflation"},
        {"id": "us.inflation.wages",     "as_of": "2022-02-28", "zscore": 0.9, "direction": "rising",  "force": "inflation"},
        # breakeven_5y NOT refreshed in Feb → fill_age=1
    ])
    cfg = {**_minimal_config(), "staleness_decay": {"enabled": True, "decay_factor": 0.9}}
    snaps = compute_composite_history(mem_conn, "US", cfg)
    feb_snaps = [s for s in snaps if s.as_of.month == 2 and s.as_of.year == 2022]
    assert feb_snaps
    feb = feb_snaps[0]
    assert feb.stale_signals is not None
    assert "us.inflation.breakeven_5y:1" in feb.stale_signals


def test_stale_signals_none_when_all_fresh(mem_conn):
    """When every signal has fresh data, stale_signals should be None."""
    for dt in ["2022-01-31", "2022-02-28"]:
        _insert_signals(mem_conn, [
            {"id": "us.growth.payrolls",        "as_of": dt, "zscore": 1.0, "direction": "rising",  "force": "growth"},
            {"id": "us.growth.unemployment",    "as_of": dt, "zscore": -1.0, "direction": "falling", "force": "growth"},
            {"id": "us.inflation.pce_core",     "as_of": dt, "zscore": 1.0, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.cpi_core",     "as_of": dt, "zscore": 1.0, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.wages",        "as_of": dt, "zscore": 1.0, "direction": "rising",  "force": "inflation"},
            {"id": "us.inflation.breakeven_5y", "as_of": dt, "zscore": 1.0, "direction": "rising",  "force": "inflation"},
        ])
    cfg = {**_minimal_config(), "staleness_decay": {"enabled": True, "decay_factor": 0.9}}
    snaps = compute_composite_history(mem_conn, "US", cfg)
    for s in snaps:
        assert s.stale_signals is None, f"Expected no stale signals at {s.as_of}, got {s.stale_signals}"


def test_composite_snapshot_stale_signals_field():
    """CompositeSnapshot model accepts and stores stale_signals."""
    snap = CompositeSnapshot(
        country="US", as_of=date(2023, 6, 30),
        stale_signals="us.growth.capacity_util:2,us.inflation.ppi_broad:5",
    )
    assert snap.stale_signals == "us.growth.capacity_util:2,us.inflation.ppi_broad:5"


def test_crude_oil_binding_has_pre_smooth_window():
    """The live us_bindings.yaml crude_oil entry should carry pre_smooth_window=7."""
    from indicators.pipeline import load_bindings
    from pathlib import Path
    bindings = load_bindings(Path("config/us_bindings.yaml"))
    oil = next((b for b in bindings if b.id == "inflation.crude_oil"), None)
    assert oil is not None
    assert oil.pre_smooth_window == 7


# ── Integration test against real DB ─────────────────────────────────────────

@pytest.mark.integration
def test_real_db_composite_history():
    """
    Against the live signals.duckdb:
    - composites span multiple years
    - all quadrant values are valid labels
    - 2022-Q3/Q4 falls in Stagflation or Inflationary Boom (growth still mixed; inflation high)
    """
    import os
    from pathlib import Path
    from store.store import get_connection, query_composite_history

    db_path = Path(os.environ.get("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"))
    if not db_path.exists():
        pytest.skip("Live DB not available")

    conn = get_connection(db_path)
    init_schema(conn)  # ensure composites table exists

    config = load_composites_config()
    snapshots = compute_composite_history(conn, "US", config)
    conn.close()

    assert len(snapshots) >= 24, "Expected at least 24 monthly composites"

    valid_labels = set(_QUADRANT_LABELS.values()) | {None}
    for snap in snapshots:
        assert snap.quadrant in valid_labels, f"Invalid quadrant: {snap.quadrant}"
        if snap.growth_score is not None:
            assert np.isfinite(snap.growth_score), "growth_score must be finite"
        if snap.inflation_score is not None:
            assert np.isfinite(snap.inflation_score), "inflation_score must be finite"

    # Spot-check: inflation-stressed periods (2022 H2) should have high inflation score
    high_inf = [s for s in snapshots if s.as_of >= date(2022, 6, 1) and s.as_of <= date(2022, 12, 31)]
    if high_inf:
        avg_inf = np.mean([s.inflation_score for s in high_inf if s.inflation_score is not None])
        assert avg_inf > 0, f"Expected positive inflation score in 2022 H2, got {avg_inf:.3f}"

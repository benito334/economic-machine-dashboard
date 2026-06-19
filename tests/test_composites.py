"""
Tests for the Phase 1B composites engine.
"""
from __future__ import annotations

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
    load_composites_config,
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
    )
    n = upsert_composites(mem_conn, [snap])
    assert n == 1

    df = query_composite_history(mem_conn, "US")
    assert len(df) == 1
    assert df.iloc[0]["quadrant"] == "Inflationary Boom"
    assert abs(df.iloc[0]["growth_score"] - 0.5) < 1e-6


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

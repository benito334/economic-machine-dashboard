"""Tests for the validation-only external benchmark panel (Dalio chip audit).

The most important test here is `test_no_benchmark_is_also_an_input_signal` —
it is the structural guard against the audit becoming circular.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from indicators import audit_benchmarks as ab

_CONFIG = Path(__file__).parents[1] / "config"


# ── Registry integrity ───────────────────────────────────────────────────────

def test_registry_keys_unique():
    keys = [b.key for b in ab.ALL_BENCHMARKS]
    assert len(keys) == len(set(keys))
    fred = [b.fred_id for b in ab.ALL_BENCHMARKS]
    assert len(fred) == len(set(fred))


def test_registry_fields_valid():
    for b in ab.ALL_BENCHMARKS:
        assert b.axis in ("growth", "inflation"), b.key
        assert b.kind in ("relative", "rate", "flag", "expect"), b.key
        assert b.orientation in (1, -1), b.key
        assert b.frequency in ("d", "w", "m", "q"), b.key
        assert b.independence.strip(), f"{b.key} must document its input overlap"


def test_benchmarks_for_partitions_registry():
    assert ab.benchmarks_for("growth") == ab.GROWTH_BENCHMARKS
    assert ab.benchmarks_for("inflation") == ab.INFLATION_BENCHMARKS
    with pytest.raises(ValueError):
        ab.benchmarks_for("credit")


def test_no_benchmark_is_also_an_input_signal():
    """Circularity guard: a benchmark may never be bound as a live signal.

    If this fails, something added a validation series to a country's bindings
    and the audit is now grading the dashboard against part of itself.
    """
    bench_ids = {b.fred_id for b in ab.ALL_BENCHMARKS}
    bound: set[str] = set()
    paths = [_CONFIG / "us_bindings.yaml"]
    paths += sorted((_CONFIG / "countries").glob("*_bindings.yaml"))
    for p in paths:
        if not p.exists():
            continue
        doc = yaml.safe_load(p.read_text()) or {}
        for binding in (doc.get("bindings") or []):
            sid = binding.get("series_id")
            if isinstance(sid, str):
                bound.add(sid)
    overlap = bench_ids & bound
    assert not overlap, (
        f"Validation-only benchmarks bound as live signals: {sorted(overlap)}. "
        "Remove them from the bindings or from the benchmark registry — the "
        "audit must never grade the composite against its own inputs."
    )


# ── State classification ─────────────────────────────────────────────────────

def _bench(**kw) -> ab.Benchmark:
    base = dict(key="x", fred_id="X", title="t", axis="growth", kind="relative",
                frequency="m", independence="n/a")
    base.update(kw)
    return ab.Benchmark(**base)


def test_publisher_thresholds_take_precedence():
    b = _bench(thresholds={"below": -0.70, "above": 0.70})
    assert ab._benchmark_state(b, 0.9, -5.0)[0] == "Above"
    assert ab._benchmark_state(b, -0.9, 5.0)[0] == "Below"
    assert ab._benchmark_state(b, 0.0, 5.0)[0] == "Neutral"


def test_orientation_inverts_publisher_threshold():
    """Sahm/recession flags fire HIGH to mean WEAK growth."""
    b = _bench(orientation=-1, thresholds={"above": 0.5})
    assert ab._benchmark_state(b, 0.8, None)[0] == "Below"


def test_unfired_flag_reads_neutral():
    b = _bench(orientation=-1, thresholds={"above": 0.5})
    assert ab._benchmark_state(b, 0.0, None)[0] == "Neutral"


def test_sigma_fallback_and_orientation():
    b = _bench()
    assert ab._benchmark_state(b, 1.0, 1.2)[0] == "Above"
    assert ab._benchmark_state(b, 1.0, -1.2)[0] == "Below"
    assert ab._benchmark_state(b, 1.0, 0.1)[0] == "Neutral"
    inv = _bench(orientation=-1)
    assert ab._benchmark_state(inv, 1.0, 1.2)[0] == "Below"


def test_unknown_state_without_history():
    assert ab._benchmark_state(_bench(), None, None)[0] == "Unknown"
    assert ab._benchmark_state(_bench(), 1.0, float("nan"))[0] == "Unknown"


# ── Verdict grid ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("chip,state,expected", [
    ("Growth", "Above", "AGREE"),
    ("Retraction", "Below", "AGREE"),
    ("Transition", "Neutral", "AGREE"),
    ("Inflation", "Above", "AGREE"),
    ("Disinflation", "Below", "AGREE"),
    ("Growth", "Below", "CONTRADICT"),
    ("Retraction", "Above", "CONTRADICT"),
    ("Inflation", "Below", "CONTRADICT"),
    ("Disinflation", "Above", "CONTRADICT"),
    ("Growth", "Neutral", "PARTIAL"),
    ("Transition", "Above", "PARTIAL"),
    ("Growth", "Unknown", "UNKNOWN"),
])
def test_verdict_grid(chip, state, expected):
    assert ab._verdict(chip, state) == expected


# ── Lead/lag ─────────────────────────────────────────────────────────────────

def test_best_lag_detects_our_series_leading():
    """Our series leads theirs by 3 months → best_lag must be +3."""
    idx = pd.date_range("2000-01-31", periods=140, freq="ME")
    wave = pd.Series(np.sin(np.arange(140) / 6.0), index=idx)
    ours = wave
    theirs = wave.shift(3)          # they repeat our move 3 months later
    out = ab.best_lag(ours, theirs)
    assert out["best_lag"] == 3
    assert out["corr_at_best"] > 0.95


def test_best_lag_zero_when_aligned():
    idx = pd.date_range("2000-01-31", periods=140, freq="ME")
    wave = pd.Series(np.sin(np.arange(140) / 6.0), index=idx)
    assert ab.best_lag(wave, wave.copy())["best_lag"] == 0


def test_best_lag_needs_history():
    idx = pd.date_range("2020-01-31", periods=10, freq="ME")
    s = pd.Series(range(10), index=idx, dtype=float)
    assert ab.best_lag(s, s)["best_lag"] is None


# ── Episodes ─────────────────────────────────────────────────────────────────

def test_disagreement_episode_detected_and_min_length_enforced():
    idx = pd.date_range("2000-01-31", periods=12, freq="ME")
    ours = pd.Series([1.5] * 12, index=idx)
    theirs = pd.Series([-1.5] * 4 + [1.5] * 6 + [-1.5] * 2, index=idx)
    eps = ab.disagreement_episodes(ours, theirs)
    assert len(eps) == 1                      # the 2-month clash is below the floor
    assert eps[0]["months"] == 4
    assert eps[0]["start"] == "2000-01-31"


def test_small_moves_are_not_disagreements():
    idx = pd.date_range("2000-01-31", periods=12, freq="ME")
    ours = pd.Series([0.2] * 12, index=idx)
    theirs = pd.Series([-0.2] * 12, index=idx)
    assert ab.disagreement_episodes(ours, theirs) == []


def test_episode_orientation_applied():
    idx = pd.date_range("2000-01-31", periods=6, freq="ME")
    ours = pd.Series([1.5] * 6, index=idx)
    theirs = pd.Series([-1.5] * 6, index=idx)
    assert ab.disagreement_episodes(ours, theirs, orientation=1)
    # inverted benchmark now agrees — no episode
    assert ab.disagreement_episodes(ours, theirs, orientation=-1) == []


# ── Resampling ───────────────────────────────────────────────────────────────

def test_quarterly_is_held_forward_within_the_quarter_only():
    idx = pd.to_datetime(["2020-01-01", "2020-04-01"])
    s = pd.Series([1.0, 2.0], index=idx)
    out = ab._to_monthly(s, "q")
    assert out.loc["2020-01-31"] == 1.0
    assert out.loc["2020-03-31"] == 1.0      # carried within the quarter
    assert out.loc["2020-04-30"] == 2.0


def test_weekly_is_averaged_into_months():
    idx = pd.date_range("2020-01-04", periods=4, freq="W-SAT")
    s = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    out = ab._to_monthly(s, "w")
    assert out.loc["2020-01-31"] == pytest.approx(2.5)


def test_rolling_z_is_centred():
    idx = pd.date_range("2000-01-31", periods=80, freq="ME")
    s = pd.Series(np.random.default_rng(0).normal(5, 2, 80), index=idx)
    z = ab.rolling_z(s, 48).dropna()
    assert abs(z.mean()) < 1.0
    assert not z.isna().all()


# ── Blind mode ───────────────────────────────────────────────────────────────

def test_blind_pack_withholds_our_read(monkeypatch):
    idx = pd.date_range("2010-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(1)

    def fake_panel(axis, force_refresh=False):
        return pd.DataFrame(
            {b.key: pd.Series(rng.normal(0, 1, 120), index=idx)
             for b in ab.benchmarks_for(axis)}
        )

    monkeypatch.setattr(ab, "load_benchmark_panel", fake_panel)
    pack = ab.build_blind_pack(country="US")
    blob = str(pack)
    assert pack["blind"] is True
    assert "chip" not in pack
    # Blind rows must carry no prose about our own system either — a reviewer who
    # learns a chip exists can start reasoning backwards from it.
    for leaked in ("chip", "verdict", "AGREE", "CONTRADICT", "growth_score",
                   "spearman", "composite", "dashboard", "our chip",
                   "our basket", "OVERLAPS"):
        assert leaked not in blob, f"blind pack leaked {leaked!r}"
    assert set(pack["axes"]) == {"growth", "inflation"}
    for axis in ("growth", "inflation"):
        rows = pack["axes"][axis]["benchmarks"]
        assert rows and all("state" in r for r in rows)


def test_blind_pack_respects_as_of(monkeypatch):
    idx = pd.date_range("2010-01-31", periods=120, freq="ME")

    def fake_panel(axis, force_refresh=False):
        return pd.DataFrame(
            {b.key: pd.Series(np.arange(120, dtype=float), index=idx)
             for b in ab.benchmarks_for(axis)}
        )

    monkeypatch.setattr(ab, "load_benchmark_panel", fake_panel)
    pack = ab.build_blind_pack(country="US", as_of="2015-06-30")
    row = pack["axes"]["growth"]["benchmarks"][0]
    assert row["latest_date"] <= "2015-06-30"


def test_unavailable_benchmark_is_reported_not_zeroed(monkeypatch):
    monkeypatch.setattr(ab, "load_benchmark_panel",
                        lambda axis, force_refresh=False: pd.DataFrame())
    pack = ab.build_blind_pack(country="US")
    rows = pack["axes"]["growth"]["benchmarks"]
    assert all(r.get("status") == "UNAVAILABLE" for r in rows)


# ── Window resolution ────────────────────────────────────────────────────────

def test_window_column_falls_back_when_empty():
    hist = pd.DataFrame({
        "growth_score": [1.0, 2.0],
        "growth_score_48m": [np.nan, np.nan],
        "inflation_score": [1.0, 2.0],
        "inflation_score_90m": [0.5, 0.6],
    })
    assert ab._window_column(hist, "growth", 48) == "growth_score"
    assert ab._window_column(hist, "inflation", 90) == "inflation_score_90m"
    assert ab._window_column(hist, "growth", None) == "growth_score"
    assert ab._window_column(hist, "growth", 36) == "growth_score"

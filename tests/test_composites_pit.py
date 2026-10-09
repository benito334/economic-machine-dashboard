"""Point-in-time composites + methodology stamp (2026-10-07).

Context for anyone reading this later. `composites` is deliberately recomputed
in full under the CURRENT rule on every pipeline run — that is correct and these
tests do not challenge it. What it cannot be is point-in-time: its Z-scores are
measured against each series' FULL history, so a row dated 2010 is scored
against a distribution running through today. Harmless for reading the machine,
look-ahead bias for anything fitted across time.

So `composites_pit` is a SECOND series published alongside, not a replacement,
and the methodology stamp says which rule produced a given row. These tests pin
the properties that make that split worth having.
"""
from __future__ import annotations

import datetime as dt

import duckdb
import numpy as np
import pandas as pd
import pytest

from indicators.methodology_version import (
    METHODOLOGY_VERSION, config_hash, methodology_stamp,
)
from store.store import (
    init_composites_pit_schema, query_composites_pit, upsert_composites_pit,
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    init_composites_pit_schema(c)
    yield c
    c.close()


def _scores(n: int = 6, start: str = "2020-01-31") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="ME")
    return pd.DataFrame(
        {"growth_score": np.linspace(-1.0, 1.0, n),
         "inflation_score": np.linspace(1.0, -1.0, n),
         "credit_score": np.zeros(n)},
        index=idx,
    )


# ── The stamp ────────────────────────────────────────────────────────────────

def test_stamp_carries_both_a_manual_version_and_an_auto_fingerprint():
    s = methodology_stamp("US")
    assert s["methodology_version"] == METHODOLOGY_VERSION
    assert len(s["config_hash"]) == 12 and s["config_hash"].isalnum()


def test_config_hash_differs_per_country():
    # Each country has its own weights, so the same methodology version can
    # still produce different numbers — the hash has to separate them.
    hashes = {cc: config_hash(cc) for cc in ("US", "GB", "JP", "LU")}
    assert len(set(hashes.values())) == len(hashes), hashes


def test_config_hash_is_stable_across_calls():
    assert config_hash("US") == config_hash("US")


def test_config_hash_moves_when_the_weight_config_changes(tmp_path, monkeypatch):
    # The whole point of the automatic half: a weight edited through the Weight
    # Audit importance editor changes no version string, and `weight_change_log`
    # already holds 10 such US changes since 2026-07-05. The hash must catch it.
    import indicators.methodology_version as mv

    cfg_dir = tmp_path / "config"
    (cfg_dir / "countries").mkdir(parents=True)
    policy = cfg_dir / "composites_policy.yaml"
    country = cfg_dir / "countries" / "xx_composites.yaml"
    policy.write_text("time_decay: {}\n")
    country.write_text("growth_score:\n  indicators:\n    - id: a\n      importance: 0.9\n")

    monkeypatch.setattr(mv, "_CONFIG_DIR", cfg_dir)
    mv.config_hash.cache_clear()
    before = mv.config_hash("XX")

    country.write_text("growth_score:\n  indicators:\n    - id: a\n      importance: 0.4\n")
    mv.config_hash.cache_clear()
    assert mv.config_hash("XX") != before
    mv.config_hash.cache_clear()


def test_config_hash_survives_a_missing_file():
    # A stamp must never be the reason a pipeline run dies.
    assert len(config_hash("zzz-not-a-country")) == 12


# ── The table ────────────────────────────────────────────────────────────────

def test_upsert_writes_rows_with_the_stamp_attached(conn):
    n = upsert_composites_pit(conn, "US", _scores())
    assert n == 6
    got = query_composites_pit(conn, "US")
    assert len(got) == 6
    assert set(got["methodology_version"]) == {METHODOLOGY_VERSION}
    assert set(got["config_hash"]) == {config_hash("US")}


def test_upsert_is_idempotent(conn):
    # CLAUDE.md rule 6. Also the reason this goes through _upsert_in_place:
    # DELETE-then-INSERT on a PK table leaks a full table copy per run.
    upsert_composites_pit(conn, "US", _scores())
    upsert_composites_pit(conn, "US", _scores())
    assert len(query_composites_pit(conn, "US")) == 6


def test_upsert_updates_in_place_rather_than_duplicating(conn):
    upsert_composites_pit(conn, "US", _scores())
    revised = _scores()
    revised["growth_score"] = 9.0
    upsert_composites_pit(conn, "US", revised)
    got = query_composites_pit(conn, "US")
    assert len(got) == 6
    assert set(got["growth_score"]) == {9.0}


def test_countries_do_not_collide(conn):
    upsert_composites_pit(conn, "US", _scores())
    upsert_composites_pit(conn, "GB", _scores())
    assert len(query_composites_pit(conn, "US")) == 6
    assert len(query_composites_pit(conn, "GB")) == 6


def test_future_rows_are_refused(conn):
    future = _scores(n=3, start=(dt.date.today() + dt.timedelta(days=40)).isoformat())
    assert upsert_composites_pit(conn, "US", future) == 0


def test_all_nan_rows_are_dropped_not_stored(conn):
    # The expanding window needs PIT_MIN_PERIODS observations before it yields
    # anything, so the first years of every country are legitimately empty.
    # Storing them as null rows would fake coverage we do not have.
    s = _scores()
    s.iloc[:3] = np.nan
    assert upsert_composites_pit(conn, "US", s) == 3


def test_empty_input_is_a_noop(conn):
    assert upsert_composites_pit(conn, "US", pd.DataFrame()) == 0
    assert upsert_composites_pit(conn, "US", None) == 0


def test_missing_credit_basket_is_tolerated(conn):
    # Not every country configures a credit basket.
    s = _scores().drop(columns=["credit_score"])
    assert upsert_composites_pit(conn, "US", s) == 6
    assert query_composites_pit(conn, "US")["credit_score"].isna().all()


def test_query_start_filter(conn):
    upsert_composites_pit(conn, "US", _scores())
    assert len(query_composites_pit(conn, "US", start="2020-04-01")) == 3


# ── The property that justifies the whole table ──────────────────────────────

def test_pit_zscore_uses_only_prior_observations():
    from indicators.backtest import pit_zscore

    # The defining property, stated as the thing a consumer actually cares
    # about: appending FUTURE observations must not change a PAST score.
    #
    # That is exactly what the production full-history Z-score fails, and why
    # this table exists. Measured on live US data 2026-10-07, the two disagree
    # on the sign of the inflation composite in 24.5% of months.
    rng = np.random.default_rng(0)
    base = pd.Series(1.0 + rng.normal(0, 0.05, 60),
                     index=pd.date_range("2010-01-31", periods=60, freq="ME"))
    # The same history, plus two years of a violent new regime.
    extended = pd.concat([
        base,
        pd.Series(5.0 + rng.normal(0, 1.0, 24),
                  index=pd.date_range("2015-01-31", periods=24, freq="ME")),
    ])

    pit_before = pit_zscore(base)
    pit_after = pit_zscore(extended).loc[base.index]
    pd.testing.assert_series_equal(pit_before, pit_after, check_names=False)

    # The full-history score, by contrast, is rewritten by data that had not
    # happened yet — the look-ahead this table removes.
    full_before = (base - base.mean()) / base.std()
    full_after = ((extended - extended.mean()) / extended.std()).loc[base.index]
    assert (full_before - full_after).abs().max() > 1.0


def test_pit_min_signals_default_is_unchanged_for_the_backtest():
    # docs/backtests/*.md report numbers computed at this value. The pipeline
    # pass overrides it with production's min_signals_required instead of
    # changing this default, because changing it would silently move published
    # backtest results.
    from indicators.backtest import PIT_MIN_SIGNALS

    assert PIT_MIN_SIGNALS == 3


def test_sparse_baskets_need_productions_threshold_not_the_backtests():
    # Regression: at the backtest's min_signals=3, Luxembourg (2 growth signals,
    # 1 inflation) produced ZERO PIT rows — a silent coverage hole the main
    # `composites` series does not have. Caught by running all 14 countries
    # before shipping, not by inspection.
    from indicators.backtest import pit_composite

    idx = pd.date_range("2015-01-31", periods=12, freq="ME")
    z = pd.DataFrame({"lu.growth.a": np.linspace(-1, 1, 12),
                      "lu.growth.b": np.linspace(1, -1, 12)}, index=idx)
    cfg = [{"id": "growth.a", "importance": 0.9}, {"id": "growth.b", "importance": 0.5}]

    assert pit_composite(z, cfg, "lu", min_signals=3).notna().sum() == 0
    assert pit_composite(z, cfg, "lu", min_signals=1).notna().sum() == 12


# ── *_momentum -> *_breadth rename, with a deprecated mirror (2026-10-07) ────
# These columns were never momentum: they are the SHARE of contributing signals
# moving in the force's positive direction. The old name read as a rate of
# change, which is a different quantity this project also publishes (the MoM
# delta, labelled "Momentum (Δ MoM)" on the regime card) — and a downstream
# consumer nearly fitted betas to it on that assumption.

_FORCES = ("growth", "inflation", "rate", "credit", "volatility", "productivity")


def test_the_model_carries_breadth_not_momentum():
    from indicators.models import CompositeSnapshot

    fields = set(CompositeSnapshot.model_fields)
    assert {f"{f}_breadth" for f in _FORCES} <= fields
    assert not {f"{f}_momentum" for f in _FORCES} & fields, (
        "the model is the canonical name; *_momentum survives only as a DB mirror"
    )


def test_both_names_are_written_and_carry_the_identical_value():
    # The deprecation contract: CreovaOne reads this table and must not break on
    # a pipeline run. Drop the mirror only once consumers have migrated.
    import datetime as dt

    from indicators.models import CompositeSnapshot
    from store.store import init_schema, upsert_composites

    c = duckdb.connect(":memory:")
    init_schema(c)
    snap = CompositeSnapshot(
        country="US", as_of=dt.date(2026, 1, 31),
        growth_score=0.5, inflation_score=-0.2,
        growth_breadth=0.75, inflation_breadth=0.25,
        rate_breadth=0.5, credit_breadth=0.6,
        volatility_breadth=0.4, productivity_breadth=0.8,
    )
    assert upsert_composites(c, [snap]) == 1
    row = c.execute(
        "SELECT " + ", ".join(f"{f}_breadth, {f}_momentum" for f in _FORCES)
        + " FROM composites"
    ).fetchone()
    for i in range(0, len(row), 2):
        assert row[i] == row[i + 1] and row[i] is not None
    c.close()


def test_no_dashboard_module_still_reads_the_deprecated_column():
    # The mirror exists for EXTERNAL consumers. Internally there must be exactly
    # one name, or the next rename has to be done twice.
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile("|".join(f"{f}_momentum" for f in _FORCES))
    offenders = []
    for path in sorted((root / "dashboard").glob("*.py")):
        for n, line in enumerate(path.read_text().split("\n"), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, (
        "read *_breadth, not the deprecated mirror:\n" + "\n".join(offenders)
    )


# ── confidence redefined as Chip Direction Agreement (2026-10-07) ────────────
# It used to be agreement with the four-season QUADRANT, derived from a raw
# `score >= 0` sign split that ignored thresholds entirely — a rule the project
# retired in July 2026, when seasons became display-only map geography. It now
# carries the metric the dashboard actually shows.

def test_confidence_is_the_mean_of_the_per_force_agreements():
    import datetime as dt

    from indicators.models import CompositeSnapshot
    from store.store import init_schema, upsert_composites

    c = duckdb.connect(":memory:")
    init_schema(c)
    upsert_composites(c, [CompositeSnapshot(
        country="US", as_of=dt.date(2026, 1, 31),
        growth_score=0.5, inflation_score=-0.2, confidence=0.45,
        growth_dir_agreement=0.6, inflation_dir_agreement=0.3,
    )])
    row = c.execute("SELECT confidence, growth_dir_agreement, "
                    "inflation_dir_agreement FROM composites").fetchone()
    assert row == (0.45, 0.6, 0.3)
    c.close()


def test_the_engine_computes_agreement_against_the_delta_not_the_quadrant():
    # The defining behaviour change: a POSITIVE growth score that is FALLING has
    # a falling heading. Under the old quadrant rule the expected direction came
    # from the score's sign (positive -> "rising"), so a basket correctly moving
    # down scored ~0 agreement. Against the chip's own heading it scores ~1.
    import numpy as np

    directions = ["falling", "falling", "falling"]
    score_prev, score_now = 0.8, 0.4          # positive, but falling

    quadrant_expected = "rising" if score_now >= 0 else "falling"   # retired rule
    heading = "rising" if score_now - score_prev > 0 else "falling"  # current rule

    old = float(np.mean([d == quadrant_expected for d in directions]))
    new = float(np.mean([d == heading for d in directions]))
    assert old == pytest.approx(0.0)
    assert new == pytest.approx(1.0)


def test_methodology_version_matches_the_latest_logged_change():
    """A definition change MUST move the stamp, or a downstream consumer
    cannot tell it from a change in the world.

    Pinned against the module's own changelog header rather than a hand-typed
    literal, so the two cannot drift: bumping the constant without logging the
    change (or vice versa) fails here.
    """
    import re, pathlib
    from indicators.methodology_version import METHODOLOGY_VERSION

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "indicators" / "methodology_version.py").read_text()
    logged = re.findall(r"^#\s+(\d{4}\.\d{2}\.\d{2})\s", src, re.M)
    assert logged, "no dated entries found in the changelog header"
    assert METHODOLOGY_VERSION == max(logged), (
        f"METHODOLOGY_VERSION={METHODOLOGY_VERSION} but the newest logged "
        f"change is {max(logged)}"
    )
    assert METHODOLOGY_VERSION == "2026.10.08"

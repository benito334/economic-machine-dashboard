"""Integration tests for store/store.py — uses a real in-memory DuckDB, no mocks."""
from datetime import date
from pathlib import Path

import duckdb
import pytest

from indicators.models import DebtStressSnapshot, Signal
from store.store import (
    delete_future_signals,
    get_connection,
    init_schema,
    query_latest,
    query_series,
    upsert_debt_stress,
    upsert_signals,
)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.duckdb"
    c = get_connection(db)
    init_schema(c)
    yield c
    c.close()


def _signal(**kwargs) -> Signal:
    defaults = dict(
        id="us.growth.payrolls",
        country="US",
        force="growth",
        lead_lag="coincident",
        as_of=date(2024, 1, 1),
        value=0.025,
        units="yoy_pct",
        zscore=0.5,
        level_percentile=0.65,
        change_1m=0.001,
        change_3m=0.003,
        change_12m=-0.002,
        direction="rising",
        equilibrium_estimate=0.015,
        distance_from_equilibrium=0.010,
        provider="FRED",
        source_tier="free",
        vintage_available=False,
        linkage="test linkage",
        source="FRED:PAYEMS",
    )
    defaults.update(kwargs)
    return Signal(**defaults)


class TestInitSchema:
    def test_signals_table_exists(self, conn):
        result = conn.execute("SELECT COUNT(*) FROM signals").fetchone()
        assert result[0] == 0


class TestUpsertSignals:
    def test_insert_one(self, conn):
        sig = _signal()
        n = upsert_signals(conn, [sig])
        assert n == 1
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        assert count == 1

    def test_insert_multiple(self, conn):
        sigs = [
            _signal(as_of=date(2024, m, 1)) for m in range(1, 7)
        ]
        n = upsert_signals(conn, sigs)
        assert n == 6
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        assert count == 6

    def test_upsert_replaces_duplicate(self, conn):
        sig1 = _signal(value=0.025)
        upsert_signals(conn, [sig1])
        sig2 = _signal(value=0.030)  # same id + as_of, different value
        upsert_signals(conn, [sig2])
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        assert count == 1
        val = conn.execute("SELECT value FROM signals").fetchone()[0]
        assert abs(val - 0.030) < 1e-10


class TestUpsertDebtStress:
    def test_replaces_same_quarter_and_rejects_future(self, conn):
        current = date.today()
        quarter_start = date(current.year, ((current.month - 1) // 3) * 3 + 1, 1)
        future = date(current.year + 1, 3, 31)
        upsert_debt_stress(conn, [
            DebtStressSnapshot(country="US", as_of=quarter_start, stress_score=0.1),
        ])
        inserted = upsert_debt_stress(conn, [
            DebtStressSnapshot(country="US", as_of=current, stress_score=0.2),
            DebtStressSnapshot(country="US", as_of=future, stress_score=9.0),
        ])
        rows = conn.execute(
            "SELECT as_of, stress_score FROM debt_stress_snapshots ORDER BY as_of"
        ).fetchall()
        assert inserted == 1
        assert rows == [(current, 0.2)]

    def test_empty_list_returns_zero(self, conn):
        assert upsert_signals(conn, []) == 0

    def test_idempotent_rerun(self, conn):
        sigs = [_signal(as_of=date(2024, m, 1)) for m in range(1, 4)]
        upsert_signals(conn, sigs)
        upsert_signals(conn, sigs)  # second identical run
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        assert count == 3  # no duplicates

    def test_none_value_stored(self, conn):
        sig = _signal(value=None, zscore=None)
        upsert_signals(conn, [sig])
        row = conn.execute("SELECT value, zscore FROM signals").fetchone()
        assert row[0] is None
        assert row[1] is None


class TestQueryLatest:
    def test_returns_one_row_per_id(self, conn):
        sigs = [
            _signal(id="us.growth.payrolls", as_of=date(2024, m, 1)) for m in range(1, 6)
        ] + [
            _signal(id="us.inflation.cpi_core", as_of=date(2024, m, 1), force="inflation") for m in range(1, 4)
        ]
        upsert_signals(conn, sigs)
        df = query_latest(conn)
        assert set(df["id"]) == {"us.growth.payrolls", "us.inflation.cpi_core"}

    def test_returns_max_date(self, conn):
        sigs = [_signal(as_of=date(2024, m, 1), value=float(m)) for m in range(1, 6)]
        upsert_signals(conn, sigs)
        df = query_latest(conn)
        row = df[df["id"] == "us.growth.payrolls"].iloc[0]
        assert str(row["as_of"])[:10] == "2024-05-01"
        assert abs(row["value"] - 5.0) < 1e-9


class TestQuerySeries:
    def test_full_series(self, conn):
        sigs = [_signal(as_of=date(2024, m, 1)) for m in range(1, 7)]
        upsert_signals(conn, sigs)
        df = query_series(conn, "us.growth.payrolls")
        assert len(df) == 6

    def test_filtered_by_start(self, conn):
        sigs = [_signal(as_of=date(2024, m, 1)) for m in range(1, 7)]
        upsert_signals(conn, sigs)
        df = query_series(conn, "us.growth.payrolls", start="2024-04-01")
        assert len(df) == 3  # Apr, May, Jun


class TestDeleteFutureSignals:
    def test_removes_only_future_rows(self, conn):
        upsert_signals(conn, [
            _signal(as_of=date(2024, 1, 1)),
            _signal(as_of=date(2099, 1, 1)),
        ])

        assert delete_future_signals(conn) == 1
        rows = query_series(conn, "us.growth.payrolls")
        assert list(rows["as_of"].dt.year) == [2024]

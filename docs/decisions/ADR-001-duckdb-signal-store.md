# ADR-001: DuckDB as the Signal Store

**Date:** 2026-06-18
**Status:** Accepted

## Context

We need a local, queryable store for `Signal` records. Requirements:
- Handles time-series data with ~35–100 columns and potentially millions of rows across 10 countries and years of history.
- Must support fast analytical queries (percentile calculations, windowed aggregations, cross-country comparisons).
- Must support upserts (`INSERT OR REPLACE` on `id + as_of`).
- Must run embedded inside the container (no separate database server to manage).
- Should be readable from Python and from the Streamlit dashboard process.

## Decision

Use **DuckDB** (embedded, file-based analytical database).

## Rationale

- DuckDB is OLAP-optimized and handles aggregations, window functions, and percentile calculations natively and fast.
- Embedded — no network, no server, no auth config, works inside Docker with a bind-mounted file.
- Excellent Python integration via `duckdb` package.
- Supports parquet import/export (useful for snapshot archiving).
- Handles our `Signal` schema naturally as a columnar table.
- Already used in the sibling All-Weather Machine project.

## Alternatives Rejected

- **SQLite:** Row-oriented; window functions and analytical queries are significantly slower. Not designed for OLAP.
- **PostgreSQL/TimescaleDB:** Requires a separate container, network config, auth. Overkill for a single-user local tool.
- **InfluxDB / ClickHouse:** Adds operational complexity for marginal benefit at our data volume.
- **Pure parquet files:** No SQL query layer; harder to join across lenses.

## Consequences

- DB file lives at `/mnt/data/db/all_weather/indicators_machine/signals.duckdb`.
- Only one writer at a time (DuckDB WAL limitation) — pipeline and dashboard must not write concurrently. Dashboard is read-only; pipeline has the write lock.
- Schema migrations must be scripted (no Alembic equivalent; manage with versioned `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` scripts in `store/store.py`).

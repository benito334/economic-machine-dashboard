# ADR-003: ALFRED Point-in-Time Vintages Deferred to Phase 3

**Date:** 2026-06-18
**Status:** Accepted

## Context

The project plan (§0.4, §9.4) requires point-in-time vintage data for look-ahead-free backtests, accessed via the FRED API's `realtime_start`/`realtime_end` parameters and `get_series_vintage_dates`.

Ingesting and archiving full vintage histories for all ~50+ US series means:
- Potentially downloading every historical revision of every series back to the 1940s–1980s.
- Significant storage and API call volume (FRED rate limits: 120 calls/minute).
- Complex schema: a separate `raw_vintages` table keyed on `(series_id, vintage_date, observation_date)`.
- Not needed for the core dashboard display (which shows current/latest readings).

## Decision

- **Phase 1A–1C:** Ingest series using `realtime_start="2000-01-01"` for the initial pull but **do not** archive rolling vintage snapshots. Store only the current latest-revised values.
- **Phase 3 (Backtest):** Implement full vintage ingestion for Phase 3 back-test scenarios only, for the specific series and date ranges required by each named scenario.

## Rationale

- Vintage ingestion is not on the critical path for the dashboard (Phases 1–2).
- Deferring keeps Phase 1A simple and avoids burning FRED API quota during initial development.
- Phase 3 is explicitly scoped as a separate milestone; vintage complexity belongs there.
- The FRED API for vintages is well-documented and stable — no risk in deferring.

## Consequences

- Phase 1A–1C backtest capability is limited: we can replay using latest-revised data, but not point-in-time.
- The data-quality log and `vintage_available` field must surface this honestly: all series set `vintage_available=false` in Phase 1; only after Phase 3 ingestion should any series flip to `true`.
- Phase 3 acceptance gate requires explicit `vintage_available=true` only for FRED series where vintage data was actually ingested.
- **ALFRED note:** Effective January 5, 2026, the FRED *website* no longer supports saving ALFRED data. The API (`realtime_start`/`realtime_end`) is unaffected. All vintage access must go through the API, not the web UI.

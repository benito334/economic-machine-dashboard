# ADR-002: APScheduler for Pipeline Orchestration

**Date:** 2026-06-18
**Status:** Accepted

## Context

The pipeline needs to run on a schedule:
- Daily: high-frequency series (rates, spreads, weekly claims)
- Weekly: weekly series (Fed balance sheet, bank loans)
- Monthly: monthly series (payrolls, CPI, PMIs)
- Quarterly: quarterly series (GDP, debt ratios, DSR)
- Annually: structural series (WB, IMF WEO, WGI)

Requirements:
- Must run inside the Docker container without an external orchestration service.
- Must be configurable per-series (different cadences for different lenses).
- Should not require a separate process/daemon.
- Must log run results and failures clearly.

## Decision

Use **APScheduler** (Advanced Python Scheduler) embedded in the pipeline process.

## Rationale

- Pure Python, no external service, runs inside the container.
- Supports multiple job stores (in-memory is sufficient; optionally SQLite for persistence across restarts).
- Native support for interval, cron, and date triggers — covers all our cadences.
- Already in the All-Weather Machine stack.
- Integrates naturally with the `pipeline.py` orchestration entry point.

## Alternatives Rejected

- **Airflow / Prefect / Dagster:** Full orchestration platforms — significant operational overhead for a single-user local tool. No benefit at our scale.
- **Cron (system):** Would require host-level cron config, harder to containerize cleanly, no Python-native job state.
- **Celery + Redis:** Message-broker overhead unnecessary for sequential serial tasks at daily/monthly cadence.

## Consequences

- Scheduling config (cadence per lens) lives in `config/composites.yaml` or a dedicated `config/schedule.yaml`.
- The scheduler runs in-process with the pipeline. If the pipeline process restarts, in-memory jobs are re-registered on startup.
- For Phase 1, manual invocation of `python -m indicators.pipeline` is acceptable. APScheduler is wired up in Phase 1B.

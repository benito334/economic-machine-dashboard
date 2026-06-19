# Repository Code Review

**Date:** 2026-06-18

**Scope:** Entire repository

**Review type:** Read-only code, configuration, tests, documentation, and container setup review

**Status:** All findings resolved and verified on 2026-06-18.

## Findings

### 1. High — Pipeline succeeds when ingestion is incomplete

Empty provider results increment the `empty` counter, but only `error` produces a non-zero exit. Docker and CI can therefore report success with missing signals, contrary to the project's explicit acceptance rule.

**Location:** `indicators/pipeline.py:349`

### 2. High — Signal IDs and source labels are hardcoded incorrectly

Every signal ID receives a `us.` prefix, and every non-derived source is labeled `FRED`, including World Bank and IMF data. This already corrupts provenance and will cause ID collisions during the planned country rollout.

**Location:** `indicators/normalize.py:78`

### 3. High — Docker dashboard service cannot start

Docker Compose runs `dashboard/app.py`, but that file does not exist. The documented `docker compose up` acceptance gate therefore cannot currently pass for the full stack.

**Location:** `docker-compose.yml:24`

### 4. High — PMI equilibrium contradicts the series definition

`growth.pmi_proxy` has an equilibrium value of `52.0`, while its linkage correctly says the Philadelphia Fed diffusion index is centered at zero. Its calculated distance from equilibrium is consequently wrong by roughly 52 points.

**Location:** `config/us_bindings.yaml:251`

### 5. Medium — Signal upserts are not atomic

Existing rows are deleted before the replacement insert, without an explicit transaction. An insert failure can therefore leave previously valid data deleted. The `INSERT INTO signals SELECT * FROM _staging` statement also makes correctness depend on DataFrame column order.

**Location:** `store/store.py:72`

### 6. Medium — Non-finite transformed values enter normalization

Calling `dropna()` does not remove positive or negative infinity. The tests explicitly accept infinity from percentage changes, but these values can poison means, standard deviations, percentiles, sanity checks, and stored output.

**Location:** `indicators/transform.py:26`

### 7. Medium — Current-year IMF forecasts are treated as observations

Only years after the current calendar year are removed. A current-year forecast is dated December 31—even when that date is still in the future—and becomes the latest signal without being marked stale.

**Location:** `indicators/loader.py:251`

### 8. Medium — Phase 1A is documented as complete despite a missing climate slot

The configuration contains 59 verified bindings and five deferred governance bindings, but no `climate` binding. The session checklist states that a deferred Lens I climate slot is required for the Phase 1A acceptance gate.

**Locations:** `config/us_bindings.yaml`, `docs/session-checklist.md`

## Verification performed

- Reviewed all repository source, configuration, test, documentation, and container files.
- Ran the complete test suite: **73 tests passed in 32.9 seconds**.
- Confirmed `dashboard/app.py` is absent.
- Confirmed the binding configuration contains 64 bindings: 59 active and 5 deferred.
- Confirmed no climate binding currently exists.
- Preserved the existing uncommitted change to `docs/start.md`.

## Recommended order of work

At review time, findings 1–4 were recommended before Phase 1B and findings 5–8 before Phase 1A acceptance. That remediation is now complete.

## Resolution

- Pipeline exits non-zero for empty results as well as raised errors.
- Signal namespaces and source labels now derive from each country binding.
- Added a read-only Streamlit status entry point; the full Compose stack starts successfully.
- Corrected the Philly Fed equilibrium from `52.0` to `0.0`.
- DuckDB replacements now use a transaction and explicit column list.
- Infinite transform results are converted to missing values and excluded from signals.
- Current-year IMF estimates, future forecasts, and future-dated stored rows are excluded.
- Added the deferred `climate.disaster_loss` Lens I binding.
- Added regression coverage; the complete suite passes with 79 tests.

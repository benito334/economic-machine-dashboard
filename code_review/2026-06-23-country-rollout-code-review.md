# Country Rollout Code Review — 2026-06-23

Scope: changes since the prior repository-wide/Phase 1F reviews, focusing on the Data Dashboard updates, Formula Reference page, and Phase 2 EZ/KR country rollout now present at commit `470c5a1`.

Review type: code, configuration, dashboard, and tests review. Findings remediated on 2026-06-23.

## Findings

### 1. High — US composite/debt-stress failures no longer fail the pipeline

`indicators.pipeline.run()` catches exceptions from the US composite pass, rolling-composite pass, and Long-Term Debt Stress pass, logs them, and then continues without incrementing an error counter or exiting non-zero. The final exit condition only checks `us_results` from ingestion passes 1–4, so the command can report success even when the core derived dashboard tables were not refreshed.

Locations:

- `indicators/pipeline.py:447-487`
- `indicators/pipeline.py:489-506`
- `indicators/pipeline.py:550-571`

Why this matters: `docker compose`/CI/cron can mark the run healthy while `/regime-history`, `/regime-map`, rolling windows, or Debt Stress are still showing stale prior snapshots. This regresses the earlier acceptance rule that pipeline failures must be visible through process status.

Recommended fix: accumulate errors for every primary US post-ingestion pass and include them in the final non-zero exit condition. For "no snapshots produced" warnings, treat that as an error for US.

Resolution: `indicators.pipeline.run()` now tracks US post-ingestion errors across the baseline composite pass, rolling composite pass, and Debt Stress pass. Exceptions and no-snapshot outcomes increment the error count and cause a non-zero exit.

### 2. High — EZ/KR ingestion and composite errors are ignored by the final status

The additional-country loop assigns `country_results = run_country(...)`, but the variable is never used. Non-US ingestion errors/empties are intentionally non-fatal inside `run_country(is_primary=False)`, and composite exceptions in the country loop are also only logged. The summary prints only US totals plus the number of country files processed.

Locations:

- `indicators/pipeline.py:512-548`
- `indicators/pipeline.py:550-571`

Why this matters: EZ and KR are now selectable in the dashboard. If Eurostat, World Bank, IMF, or country composites fail, the pipeline can still exit successfully and the UI can keep showing stale/partial data with no operational signal beyond logs. "Country files processed" is not equivalent to "countries refreshed successfully."

Recommended fix: track per-country `ok/empty/error/sanity_warn` totals and composite success. Decide whether country rollout failures should be hard-fail or soft-fail, but expose the result explicitly; for enabled dashboard countries, hard-failing is safer.

Resolution: enabled country files now contribute to pipeline status. Ingestion `empty/error` counts, missing country composite configs, composite exceptions, and no-snapshot country composite outcomes are reported per country and cause a non-zero exit.

### 3. Medium — Tests do not cover pipeline failure propagation for the new country rollout

The suite covers calculation behavior and dashboard rendering, but there are no tests around `indicators.pipeline.run()` status behavior when composite, debt-stress, or non-US country passes fail. That is why the two failure-accounting regressions above are not caught despite the full test suite passing.

Location:

- `tests/` has no pipeline orchestration/status tests for `run()` or `run_country()`.

Recommended fix: add unit tests that monkeypatch `run_country`, `compute_composite_history`, `compute_debt_stress_history`, and/or `upsert_composites` to raise or return no snapshots, then assert that enabled-country failures are reflected in the final exit behavior and summary.

Resolution: added `tests/test_pipeline.py` with regression coverage for US composite failure, US Debt Stress no-snapshot failure, enabled-country ingestion failure, and enabled-country composite no-snapshot failure.

## Verification

- `pytest -q`: 353 passed, 6 warnings
- `python3 -m compileall -q indicators dashboard tests`: passed
- `git diff --check`: passed

## Notes

- Existing untracked file observed before review: `docs/Guidance/EU_singals_guidance.md`.

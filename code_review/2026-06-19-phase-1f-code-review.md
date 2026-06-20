# Phase 1F Code Review — 2026-06-19

Scope: all commits after `b38ebe4`, covering the Long-Term Debt Stress engine, staleness handling, dashboard panels, Regime History component details, and feedback documentation.

## Findings and resolutions

1. **High — Corporate debt/GDP had a 1,000× unit error.** `BCNSDODNS` is millions of dollars while `GDP` is billions. The numerator is now converted to billions, with a regression test against a known 50% ratio.
2. **High — Historical staleness used present-day last-observation dates.** Each snapshot now derives the latest eligible source date at that quarter; multi-source components use the restrictive date and synthetic carry dates are excluded.
3. **High — Historical Regime History details showed current signal components.** Component queries now accept an as-of cutoff matching the selected composite month.
4. **High — Streamlit's historical regime stepper always showed current Debt Stress.** The HUD now selects the latest debt-stress snapshot available at the selected regime date.
5. **Medium — Carry/extrapolation behavior was inconsistent.** Corporate debt now honors the configured carry cap; extrapolation triggers from total lag beyond that cap instead of excess publication lag.
6. **Medium — `stale_weight_halflife` was linear and reached zero at the named half-life.** It now uses exponential decay, so the configured four-quarter half-life actually halves weight after four excess quarters.
7. **Medium — Debt Stress persistence could retain future rows or duplicate a provisional quarter.** Upserts now reject and clean future rows and replace matching country/quarter rows atomically.
8. **Medium — Derived component dates and displayed effective weights were incomplete.** The UI now reads raw FRED dates for derived components and applies the same exponential decay to stale and extrapolated rows.
9. **Medium — Configuration and country scope were not enforced.** Loading now validates weights, thresholds, lag settings, coverage, extrapolation method, and look-back shift. The US configuration cannot silently run for another country.
10. **Low — Schema migration errors were swallowed, model list defaults were mutable-style declarations, an integration test ignored `DB_PATH`, and an empty misspelled document was tracked.** Migrations now use `IF NOT EXISTS`, lists use factories, the test respects its container environment, and the typo file was removed.

## Verification

- `pytest -q`: 249 passed
- Live pipeline: 59 signals OK, 0 empty, 0 errors, 0 sanity warnings
- Debt Stress: 185 snapshots; latest 2026-Q1 score +0.488, 5/7 active components, 72.7% retained weight
- Latest corporate debt/GDP raw ratio: 0.4542
- Future debt-stress rows: 0
- The same 249-test suite passes both locally and in the Docker image
- Python compilation and whitespace checks passed

## Remaining methodological limitation

Historical inputs are latest-revised and period-dated. `shift(1)` prevents a value from entering its own normalization window, but publication-lag and revision-safe backtesting requires Phase 3 vintage/availability metadata.

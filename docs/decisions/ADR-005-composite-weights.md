# ADR-005: Composite Weights for Growth and Inflation Scores

**Date:** 2026-06-18
**Status:** Accepted

## Context

The project plan defines Growth Score and Inflation Score as "weighted indexes" over their respective signal lenses (§3.1) but **never specifies the weights**. Without weights, the composites cannot be computed. This is a material gap in the spec.

## Decision

Use **equal weights across all signals within each composite** as the default. Weights are defined in `config/composites.yaml` and can be overridden per-indicator without code changes.

### Default scheme

**Growth Score** — equal weight over all `lead_lag != "lagging"` signals in Lens A:
- `growth.payrolls`, `growth.industrial_prod`, `growth.retail_sales`, `growth.real_pce`, `growth.capacity_util`, `growth.job_openings` (leading), `growth.pmi_proxy` (leading), `growth.labor_force_part`
- Productivity (`growth.productivity`) and TFP/R&D (`growth.tfp`, `growth.rnd_intensity`) are structural/annual and are **excluded** from the high-frequency Growth Score; they feed the Disequilibrium Score instead.

**Inflation Score** — equal weight over:
- `inflation.cpi_core`, `inflation.pce_core`, `inflation.wages`, `inflation.breakeven_5y`, `inflation.breakeven_10y`
- `inflation.cpi_headline` and `inflation.crude_oil` are included with half-weight (0.5×) to avoid double-counting with core measures.
- `inflation.commodity_index` is included at half-weight.

**Regime Quadrant Confidence %** — defined as the fraction of contributing signals whose direction vector agrees with the assigned quadrant. E.g. if 7/10 growth signals are rising and 8/10 inflation signals are rising → Inflationary Boom confidence = average(7/10, 8/10) = 75%.

**Disequilibrium Score** — equal weight over absolute `distance_from_equilibrium` across all five force lenses (Debt/Money, Internal Order, External Order, Climate, Technology), where data exists. Forces with no data contribute 0 to the average but reduce the denominator, with a `low_coverage` flag if fewer than 3 of 5 forces have data.

## Rationale

- Equal weights are the honest choice when no empirical calibration has been done. Named composite weights are better than hidden/implicit weights.
- Putting weights in config makes them auditable and overridable without code changes.
- Dalio's original framework does not publish explicit weights for these composites — equal weights are the most defensible neutral prior.
- The half-weight scheme for headline/commodity inflation prevents crude oil volatility from dominating the Inflation Score.

## Consequences

- `config/composites.yaml` must define weight maps for Growth Score and Inflation Score.
- Signals with `is_stale=true` or `low_history=true` are excluded from composite computation (they cannot contribute reliably).
- The dashboard must display which signals are included/excluded from each composite in the accordion drill-down.
- This decision can be revisited once the system is running and we can observe how composites track known regimes (Phase 1B acceptance gate).

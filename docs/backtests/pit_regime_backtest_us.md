# Point-in-time regime backtest — US

Phase G (stages G1+G2) of docs/Guidance/ray_framework_roadmap.md.
All Z-scores are expanding-window, shift(1) — the classifier at month t
uses only data available before t (warm-up: 36 months).

**Not covered here (stage G3, future):** data-revision look-ahead
(this uses final-revised data, not ALFRED vintages) and asset-outcome
predictive tests. The production momentum weight-tilt and age-decay
modifiers are not applied to the PIT composite (bounded weight
multipliers; they shift magnitudes, rarely signs).

Scored era: 1983-01 → 2026-07 (559 months).

Reading the numbers: `strict` = months showing exactly the expected
chip; `acceptable` also counts Transition (the momentum gate parks
plateau months there by design); `wrong` = months showing the
OPPOSITE pole — the number that must stay near zero.

## Fixed thresholds

| Scenario | Dim | Months | Strict | Acceptable | Wrong dir | Labels |
|---|---|---|---|---|---|---|
| 1990-91 recession | growth | 8 | 50% | 100% | 0% | Retraction 4, Transition 4 |
| Late-90s boom | growth | 48 | 33% | 100% | 0% | Growth 16, Transition 32 |
| 2001 dot-com bust | growth | 8 | 75% | 100% | 0% | Retraction 6, Transition 2 |
| 2008 GFC bust | growth | 9 | 67% | 100% | 0% | Retraction 6, Transition 3 |
| 2009 disinflation | inflation | 10 | 60% | 100% | 0% | Disinflation 6, Transition 4 |
| 2020 COVID crash | growth | 6 | 33% | 100% | 0% | Retraction 2, Transition 4 |
| 2021-22 inflation surge | inflation | 13 | 69% | 100% | 0% | Inflation 9, Transition 4 |
| 2023 disinflation | inflation | 13 | 0% | 92% | 8% | Inflation 1, Transition 12 |

## Dynamic thresholds

| Scenario | Dim | Months | Strict | Acceptable | Wrong dir | Labels |
|---|---|---|---|---|---|---|
| 1990-91 recession | growth | 8 | 88% | 100% | 0% | Retraction 7, Transition 1 |
| Late-90s boom | growth | 48 | 54% | 98% | 2% | Growth 26, Retraction 1, Transition 21 |
| 2001 dot-com bust | growth | 8 | 75% | 100% | 0% | Retraction 6, Transition 2 |
| 2008 GFC bust | growth | 9 | 67% | 100% | 0% | Retraction 6, Transition 3 |
| 2009 disinflation | inflation | 10 | 60% | 100% | 0% | Disinflation 6, Transition 4 |
| 2020 COVID crash | growth | 6 | 33% | 100% | 0% | Retraction 2, Transition 4 |
| 2021-22 inflation surge | inflation | 13 | 69% | 100% | 0% | Inflation 9, Transition 4 |
| 2023 disinflation | inflation | 13 | 0% | 92% | 8% | Inflation 1, Transition 12 |

## Dynamic vs. fixed — head to head

| Scenario | Δ strict | Δ acceptable | Δ wrong (lower is better) |
|---|---|---|---|
| 1990-91 recession | +38% | +0% | +0% |
| Late-90s boom | +21% | -2% | +2% |
| 2001 dot-com bust | +0% | +0% | +0% |
| 2008 GFC bust | +0% | +0% | +0% |
| 2009 disinflation | +0% | +0% | +0% |
| 2020 COVID crash | +0% | +0% | +0% |
| 2021-22 inflation surge | +0% | +0% | +0% |
| 2023 disinflation | +0% | +0% | +0% |

# Long-Term Debt Stress Indicator

## Purpose

The indicator measures whether public and private debt burdens are becoming harder to service from the income available to borrowers. Higher values mean greater stress. It is a monitoring indicator, not a default-probability model or a claim that any debt level is intrinsically unsustainable.

## Components

All components are converted to quarterly frequency and standardized before aggregation.

| Component | Weight | Stress direction | Source already available |
|---|---:|---|---|
| Government plus household debt / GDP | 0.25 | Higher increases stress | `us.credit.gov_debt_gdp`, `us.credit.household_debt_gdp` |
| Corporate debt / GDP | 0.15 | Higher increases stress | Raw FRED `BCNSDODNS` level divided by raw nominal GDP |
| Household debt-service ratio | 0.20 | Higher increases stress | `us.credit.debt_service_ratio` (`TDSP`) |
| Federal interest outlays / GDP | 0.15 | Higher increases stress | Raw `FYOINT` divided by raw nominal GDP |
| Primary fiscal balance / GDP | 0.10 | Higher reduces stress | `us.fiscal.primary_balance_gdp` |
| Structural balance / potential GDP | 0.05 | Higher reduces stress | `us.fiscal.structural_balance` |
| Government revenue / GDP | 0.10 | Higher reduces stress | `us.fiscal.govt_revenue_gdp` |
| **Total** | **1.00** | | |

The first component intentionally covers government and household leverage; corporate leverage remains separate so its contribution is visible. This is not a complete all-sector debt total because it does not include every financial-sector liability.

## Important data definitions

- `BCNSDODNS` is a corporate debt **level in millions of dollars** in the raw FRED cache, while `GDP` is in billions. Convert the numerator to billions before division. The processed `us.credit.corporate_debt` signal is its year-over-year growth rate, so the ratio must be constructed from the raw level rather than reconstructed by compounding growth.
- Raw nominal GDP (`GDP`) is already downloaded. The processed `us.master.gdp_nominal` signal is a year-over-year growth rate and cannot serve as the denominator.
- `TDSP` directly measures household required debt payments relative to disposable personal income. It should be used directly, not inverted or combined with federal fiscal flows.
- `FYFSD` is the federal surplus/deficit, a borrowing flow. It is not principal repayment and must not be added to interest outlays as “debt service.”
- `FYFSD` and `FYOINT` are annual fiscal-year series reported in millions of dollars, not quarterly series in billions. If `FYOINT` is divided by quarterly GDP, convert units and align the annual fiscal-year observation explicitly.
- Primary and structural balances are signed so that a larger surplus reduces stress. Government revenue also reduces stress. Their signs must therefore be inverted in the final stress formula.
- Do not introduce guessed FRED identifiers. Any additional level series must be verified against provider metadata before it is added to the bindings.

## Frequency alignment

Use quarter-end dates as the common grid.

- Quarterly series retain their published quarter.
- Annual fiscal and cross-country series are currently aligned by observation period and then carried forward. Actual publication timestamps are not yet stored, so this history must not be treated as a real-time vintage backtest.
- Never interpolate annual observations into quarters that predate publication.
- Phase 3 must add availability-date and vintage metadata before historical results can be interpreted as information that was genuinely known at the time.
- Report component coverage and staleness alongside the indicator. Do not silently substitute a stale component.

## Standardization

For each component, calculate a trailing 10-year Z-score using only information before the current observation:

```python
def rolling_z(series, window=40, min_periods=20):
    prior = series.shift(1)
    return (series - prior.rolling(window, min_periods=min_periods).mean()) / \
           prior.rolling(window, min_periods=min_periods).std()
```

Annual inputs have fewer independent observations than quarterly inputs even after forward filling. Their Z-scores should therefore be calculated on the native annual series and then carried forward, or use an explicitly documented annual window. Repeating one annual value four times must not make it count as four independent observations.

## Formula

```text
DebtStress =
    0.25 × z(government debt/GDP + household debt/GDP)
  + 0.15 × z(corporate debt/GDP)
  + 0.20 × z(household debt-service ratio)
  + 0.15 × z(federal interest outlays/GDP)
  - 0.10 × z(primary fiscal balance/GDP)
  - 0.05 × z(structural balance/potential GDP)
  - 0.10 × z(government revenue/GDP)
```

If a component is unavailable or stale, renormalize the available absolute weights only when a documented minimum-coverage rule is met. The output must expose both the number of active components and the retained weight. It should not fall back from corporate debt/GDP to corporate debt growth without identifying the result as a different model variant.

## Interpretation

The raw score is measured in weighted standard deviations. Initial display bands may be used for exploration, but they are not validated risk thresholds:

| Score | Descriptive band |
|---:|---|
| below -0.5 | Below-normal stress |
| -0.5 to 0.5 | Near historical norm |
| 0.5 to 1.0 | Elevated stress |
| above 1.0 | High relative stress |

Before using these bands for decisions, backtest the indicator against known tightening, recession, deleveraging, and fiscal-stress episodes. Test weight sensitivity, real-time vintages, publication lags, and whether each component adds information beyond the others.

## Implementation in this project

1. Add a derived-series module that reads the existing raw caches and Signal table through the current DuckDB pipeline.
2. Construct corporate debt/GDP and federal interest/GDP with explicit unit conversion and availability dates.
3. Align native-frequency inputs without look-ahead and calculate native-frequency trailing Z-scores.
4. Aggregate with the fixed signs and weights above, enforcing minimum coverage and staleness rules.
5. Store the component contributions and final score in DuckDB so the result is auditable.
6. Add unit tests for units, signs, publication timing, missing components, weight renormalization, and look-ahead prevention.
7. Add a dashboard view only after the historical output and component contributions pass review.

## Known limitations

- Debt ratios measure balance-sheet burden, while the service ratios measure current cash-flow pressure; combining them is useful but not a structural causal model.
- Federal interest outlays are annual and respond slowly to market-rate changes because debt reprices over time.
- Cross-source annual fiscal series may use different accounting conventions and revision schedules.
- Rolling Z-scores describe deviation from recent history, not absolute sustainability.
- The initial weights are transparent priors. They require robustness testing before production use.
- Historical inputs are latest-revised and period-dated. The statistical `shift(1)` guard prevents a value from entering its own normalization window, but it does not solve publication-lag or revision look-ahead bias.

## Dealing with Stale Data Sources

When a data source becomes stale, the system should treat it as a signal that its reliability has been compromised. In a principled, cycle‑aware framework, you don’t simply drop the series outright; you first assess how long the lag is and what impact it would have on the overall picture.

- **Detect staleness:** Compare the latest observation period with the expected release schedule. If the gap exceeds one quarter for quarterly series or one year for annual series, flag the value as stale.

- **Quantify uncertainty:** Reduce stale-component weights with the configured exponential half-life. Older data still informs the long-term trend, but with diminished influence.

- **Apply a fallback rule:** Carry the latest valid observation only to the configured horizon. Optional rolling-mean or linear-trend extrapolation exists behind a disabled-by-default configuration gate.

- **Rebalance weights:** Renormalize active effective weights when minimum coverage is met. Below the coverage threshold, emit a null score rather than a synthetic baseline.

- **Signal the condition:** Store stale and extrapolated component IDs with their lags, and surface low coverage in both dashboards.

- **Review and refresh:** Recompute after each source release and audit the component-level contribution table.

By treating staleness as a systematic, quantifiable risk rather than an automatic exclusion, the machine preserves the integrity of its cause‑effect mapping across cycles while maintaining robustness. This approach aligns with the principle that a well‑diversified, principle‑driven system should be resilient to imperfect information, adjusting incentives and feedback loops dynamically as the quality of inputs evolves.

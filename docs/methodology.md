# Macro Regime Classification — Methodology

> **Purpose:** This document explains exactly how raw macroeconomic data is transformed into the macro-regime scores and quadrant label shown on the dashboard. It is written for a reviewer who wants to understand, critique, or replicate the methodology. Code references are provided throughout so the reader can verify each step.
>
> All calculation logic lives in `indicators/composites.py`, `indicators/normalize.py`, and `indicators/transform.py`. Configuration (weights, force groups) lives in `config/composites.yaml`.

---

## 1. Overview

The system classifies any economy into one of four macro "seasons," derived from two independent composite scores:

| Score | Sign | Interpretation |
|:------|:-----|:---------------|
| **Growth Score** | ≥ 0 | Growth is above its historical norm |
| **Growth Score** | < 0 | Growth is below its historical norm |
| **Inflation Score** | ≥ 0 | Inflation is above its historical norm |
| **Inflation Score** | < 0 | Inflation is below its historical norm |

The intersection of the two signs defines the **Regime Quadrant**:

|  | Inflation above norm | Inflation below norm |
|:---|:---|:---|
| **Growth above norm** | Inflationary Boom | Expansion |
| **Growth below norm** | Stagflation | Disinflationary Slowdown |

Two secondary outputs describe how confident we should be in the classification:

- **Confidence** — fraction of individual signals whose current momentum direction is consistent with the assigned quadrant.
- **Disequilibrium Score** — average absolute Z-score across five structural force lenses; measures how far the economy is from historical norms, regardless of direction.

---

## 2. Signal Inventory

There are currently **59 active US signals** spanning 10 force lenses (A–I):

| Lens | Force | Provider(s) | Frequency | Count |
|:-----|:------|:------------|:----------|------:|
| A | Growth | FRED, World Bank | M / Q / A | 12 |
| B | Inflation | FRED | D / M | 7 |
| C | Policy (monetary) | FRED | D / W | 7 |
| D | Credit / Debt | FRED | Q / W | 6 |
| E | Risk Premiums | FRED | D | 4 |
| F | External / Trade | FRED, World Bank | Q / A | 5 |
| G | Capital / Currency | FRED, World Bank | M / A | 4 |
| H | Governance | World Bank WGI | A | 5 (deferred) |
| I | Fiscal | FRED, World Bank, IMF | A | 5 |
| — | Demographics | World Bank | A | 4 |

The composite scores (Growth + Inflation) use a **subset of 16 monthly/daily signals** from Lenses A and B only. The disequilibrium score draws on the full 59-signal universe grouped into five structural force groups. See Sections 4 and 7 below.

---

## 3. Signal Processing Pipeline

Before any composite score is computed, each raw series is processed into a normalized **Signal** record. This happens in `indicators/transform.py` and `indicators/normalize.py`.

### 3.1 Transformation

The first step converts raw provider data into a comparable unit. Three transformation modes exist:

| Mode | Applied to | Formula | Example |
|:-----|:-----------|:--------|:--------|
| `yoy_pct` | Level series (GDP, payrolls, CPI) | `series.pct_change(N)` where N = number of native periods in one year | Monthly CPI: N=12; Quarterly GDP: N=4; Daily yields: N=252 |
| `level` | Rates, ratios, diffusion indices | Pass-through (no transformation) | Fed funds rate, capacity utilisation, unemployment rate |
| `spread` | Spreads already expressed as differences | Pass-through | Yield curve (10Y–2Y), credit spreads |

This brings every series into a common conceptual space: *how does the current level compare to a year ago?* for flow/price series, or *what is the current level?* for rates and spreads.

**Code:** `indicators/transform.py` → `apply_transformation()`

### 3.2 Z-Score Normalization

Once transformed, each observation is standardized against the **full available history** of that series:

```
Z = (x - μ) / σ
```

where:
- `x` is the current transformed value
- `μ` is the mean of all non-NaN observations in the series history
- `σ` is the sample standard deviation (ddof=1) of the same history

If `σ = 0` (constant series), the Z-score is set to 0.

> **Critical implication:** The Z-score tells you where the current observation sits relative to the full historical distribution, *not* relative to any theoretical notion of what is "healthy." A Z-score of +1.5 means the value is 1.5 standard deviations above its own history, which is high — but it does not say whether that level is good or bad for the economy.
>
> **Look-ahead bias note:** Computing Z-scores against the full history means that historical Z-scores are computed with the benefit of future data. This is intentional for Phase 1 (diagnostic display). Phase 3 back-tests will switch to expanding windows to eliminate look-ahead bias.

**Code:** `indicators/normalize.py` → `_zscore_series()`

### 3.3 Percentile Rank

Each observation also receives a percentile rank: the fraction of all historical values strictly below the current value.

```
percentile = rank(pct=True, method="average") - 0.5 / n
```

This is a continuous rank (not a simple integer percentile), adjusted to avoid ties at 0 or 1. A value of 0.78 means the current reading is higher than 78% of all historical readings.

**Code:** `indicators/normalize.py` → `_percentile_series()`

### 3.4 Momentum

Three momentum windows are computed as **absolute differences** in the transformed series (not percentage changes of the transformed series):

| Window | Daily | Weekly | Monthly | Quarterly | Annual |
|:-------|------:|-------:|--------:|----------:|-------:|
| 1-month | 21 trading days | 4 weeks | 1 period | 1 period | 1 period |
| 3-month | 63 trading days | 13 weeks | 3 periods | 1 period | 1 period |
| 12-month | 252 trading days | 52 weeks | 12 periods | 4 periods | 1 period |

For example, a monthly CPI series transformed to YoY%:
- `change_3m = cpi_yoy(t) - cpi_yoy(t-3 months)` — the change in the year-over-year rate over the past quarter.

**Code:** `indicators/transform.py` → `compute_momentum()`

### 3.5 Direction Flag

Each signal carries a directional label derived from its 3-month momentum:

| Condition | Direction |
|:----------|:----------|
| `change_3m > 1e-9` | `"rising"` |
| `change_3m < -1e-9` | `"falling"` |
| Otherwise | `"flat"` |

The threshold `1e-9` treats floating-point near-zero as flat.

This direction flag is used in the **Confidence Score** calculation (Section 6).

**Code:** `indicators/normalize.py` → `_direction()`

### 3.6 Forward-Fill Policy

Raw series arrive at different frequencies (daily, weekly, monthly, quarterly, annual). To build a consistent monthly composite history, reliable signals are resampled to month-end and **forward-filled up to 13 months**. This means:

- A quarterly GDP figure (e.g., dated 2026-01-01 for Q1 2026) will be carried forward for up to 13 monthly composite snapshots, until a newer observation replaces it.
- Signals flagged `low_history` are excluded. A signal flagged `is_stale` stops contributing from the month of its latest stale observation, so an old release cannot silently drive the current composite.

**Code:** `indicators/composites.py` → `_load_wide()` with `ffill_limit=13`

---

## 4. Growth Score

### 4.1 Indicator Selection

The Growth Score uses **9 coincident and leading indicators** from Lens A (Growth force). Structural-frequency signals (TFP, R&D intensity, productivity) are explicitly excluded because their annual/lagging nature would distort a monthly composite.

| Signal ID | Description | Frequency | Weight | Inverted? |
|:----------|:------------|:----------|-------:|:---------:|
| `growth.payrolls` | Nonfarm payrolls YoY% | Monthly | 1.0 | No |
| `growth.industrial_prod` | Industrial production YoY% | Monthly | 1.0 | No |
| `growth.retail_sales` | Advance retail sales YoY% | Monthly | 1.0 | No |
| `growth.real_pce` | Real personal consumption YoY% | Monthly | 1.0 | No |
| `growth.capacity_util` | Capacity utilisation (level) | Monthly | 1.0 | No |
| `growth.job_openings` | JOLTS job openings (level) | Monthly | 1.0 | No |
| `growth.pmi_proxy` | Philly Fed Business Outlook Index | Monthly | 1.0 | No |
| `growth.labor_force_part` | Labour force participation rate | Monthly | 1.0 | No |
| `growth.unemployment` | Unemployment rate (level) | Monthly | 1.0 | **Yes** |

The unemployment rate is **inverted** (multiplied by −1 before averaging) because a falling unemployment rate is a positive growth signal. All other signals are positively oriented.

### 4.2 Calculation Formula

For each monthly snapshot:

```
Growth Score = Σ (Z_i × w_i × sign_i) / Σ w_i
```

where the sum is over all signals with a non-NaN Z-score at that date, and:
- `Z_i` is the Z-score of signal i
- `w_i` is the weight (all 1.0 currently)
- `sign_i` is −1 if `invert=True`, else +1

Signals with NaN Z-scores (no data available yet) are excluded and their weight is dropped from the denominator. This means the score is always a weighted average of available signals — partial data does not collapse the score to zero.

**Minimum coverage:** A quadrant label will not be assigned unless at least **4 signals** contribute to each score.

**Code:** `indicators/composites.py` → `compute_composite_history()`, lines 158–174

---

## 5. Inflation Score

### 5.1 Indicator Selection

The Inflation Score uses **8 active signals** from Lens B (Inflation force). Three signals receive half-weight to reduce the influence of volatile input prices:

| Signal ID | Description | Frequency | Weight | Rationale |
|:----------|:------------|:----------|-------:|:----------|
| `inflation.pce_core` | Core PCE YoY% | Monthly | 1.0 | Fed's official target; most persistent |
| `inflation.cpi_core` | Core CPI YoY% | Monthly | 1.0 | Broadest consumer basket; high public salience |
| `inflation.wages` | Average hourly earnings YoY% | Monthly | 1.0 | Wage-price spiral driver; services inflation anchor |
| `inflation.breakeven_5y` | 5Y TIPS breakeven (level) | Daily | 1.0 | Market's near-term inflation expectation |
| `inflation.breakeven_10y` | 10Y TIPS breakeven (level) | Daily | 1.0 | Long-run inflation anchoring signal |
| `inflation.cpi_headline` | Headline CPI YoY% | Monthly | **0.5** | Correlated with core but adds commodity noise |
| `inflation.crude_oil` | WTI crude oil YoY% | Daily | **0.5** | Leading indicator but highly volatile |
| `inflation.ppi_broad` | Producer Price Index YoY% | Monthly | **0.5** | Broad upstream price pressure |

### 5.2 Calculation Formula

Identical structure to the Growth Score, without inversion:

```
Inflation Score = Σ (Z_i × w_i) / Σ w_i
```

**Code:** `indicators/composites.py` → `compute_composite_history()`, lines 178–190

---

## 6. Regime Quadrant

### 6.1 Classification Logic

The quadrant is determined by the signs of the two composite scores:

```python
growth_up    = (Growth Score >= 0)
inflation_up = (Inflation Score >= 0)

quadrant = {
    (True,  True):  "Inflationary Boom",
    (True,  False): "Expansion",
    (False, True):  "Stagflation",
    (False, False): "Disinflationary Slowdown",
}[(growth_up, inflation_up)]
```

The sign boundary (zero) is deliberate: it means "above or below this economy's own historical average." An economy can be in "Expansion" while growing at only 1% if its historical average growth is even lower.

**Code:** `indicators/composites.py` → `_QUADRANT_LABELS`, line 26

### 6.2 The Four Seasons — Economic Interpretation

**Expansion** *(Growth ↑, Inflation ↓)*
Growth is running above historical norms while inflation is subdued. The classic "Goldilocks" regime. Productive capacity is expanding faster than price pressures. In portfolio terms, traditionally favourable for equities.

**Inflationary Boom** *(Growth ↑, Inflation ↑)*
Strong demand is pushing both output and prices higher. Late-cycle characteristics: tight labour markets, rising commodity prices, central bank tightening. Growth is still positive in absolute terms but the seeds of the next slowdown are being sown via rate hikes.

**Stagflation** *(Growth ↓, Inflation ↑)*
The most adverse quadrant. Growth is below historical norms while inflation remains elevated. Supply shocks (energy, trade disruption) are the classic trigger. Real purchasing power falls, central banks face a policy dilemma (tighten to fight inflation vs. ease to support growth), and most asset classes underperform in real terms.

**Disinflationary Slowdown** *(Growth ↓, Inflation ↓)*
Growth has fallen below trend and inflation is retreating. The classic recession/post-shock recovery setup. Central banks typically ease aggressively. In portfolio terms, traditionally favourable for long-duration bonds.

---

## 7. Confidence Score

### 7.1 What It Measures

The Confidence Score answers: *"How consistently are the underlying signals pointing in the direction implied by the current quadrant?"*

A regime label can be assigned even when signals are mixed — for example, a Growth Score of −0.05 puts the economy in the "below norm" half, but barely. If half the growth signals are still rising, that label is fragile. Confidence quantifies this fragility.

### 7.2 Calculation

For the **expected direction** of each quadrant:

| Quadrant | Expected growth signal direction | Expected inflation signal direction |
|:---------|:---------------------------------|:------------------------------------|
| Inflationary Boom | rising | rising |
| Expansion | rising | falling |
| Stagflation | falling | rising |
| Disinflationary Slowdown | falling | falling |

For each growth signal that contributed to the Growth Score:
- Compare its `direction` field (the 3-month momentum flag) to the expected growth direction.
- Exception: if the signal has `invert=True` (unemployment), the expected direction is flipped (unemployment is *expected to be falling* when growth is above norm).
- Score 1.0 if the direction matches, 0.0 if it does not. "Flat" never matches.

```
g_fraction = (number of growth signals with matching direction) / (total growth signals with a direction)
i_fraction = (number of inflation signals with matching direction) / (total inflation signals with a direction)

Confidence = (g_fraction + i_fraction) / 2
```

The growth and inflation fractions are averaged with equal weight, so neither force dominates the confidence reading.

**Code:** `indicators/composites.py` → `compute_composite_history()`, lines 206–232

### 7.3 Interpretation

| Confidence | Interpretation |
|:-----------|:---------------|
| ≥ 0.75 | Strong — most signals confirm the regime label |
| 0.50–0.75 | Moderate — majority of signals consistent |
| 0.25–0.50 | Weak — signals are mixed; regime transition may be underway |
| < 0.25 | Very weak — signals actively contradict the label |

At the current reading (June 2026): **48%** — the Stagflation label is assigned but the directional signals remain mixed, consistent with the Growth Score being only marginally negative (−0.048).

---

## 8. Disequilibrium Score

### 8.1 What It Measures

The Disequilibrium Score answers: *"Across all economic forces, how far is this economy from its declared equilibrium levels?"*

Unlike the regime quadrant (which only cares about direction), disequilibrium is a magnitude signal. It tells you whether the economy is in a state of extremes — either very good or very bad — across multiple dimensions simultaneously. A high disequilibrium score increases the probability of a regime transition because extreme readings tend to mean-revert.

### 8.2 Force Group Construction

All 59 active signals are grouped into **five structural force categories**:

| Group | Constituent forces / signals | Lenses |
|:------|:----------------------------|:-------|
| `debt_money` | All `credit` and `policy` signals | C + D |
| `internal_order` | All `governance` signals | H |
| `external_order` | All `external`, `capital`, and `currency` signals | F + G |
| `climate` | All `climate` signals | I |
| `technology` | `growth.productivity`, `growth.tfp`, `growth.rnd_intensity` | A (structural) |

> **Current coverage:** `internal_order` (Lens H governance/WGI) is deferred — those 5 signals have no live data. `climate` is also deferred. This means the disequilibrium score currently draws on 3 of 5 groups. The `low_coverage` flag fires when fewer than 3 groups have data.

**Code:** `indicators/composites.py` → `_build_force_groups()`, `config/composites.yaml` → `disequilibrium_score.forces`

### 8.3 Calculation

For each monthly snapshot:

1. For each force group with at least one non-NaN signal:
   ```
   group_score = mean( |standardized_equilibrium_distance_i| )
   ```
   Each raw `distance_from_equilibrium` is divided by that signal's historical standard deviation. Taking its **absolute value** means displacement on either side of equilibrium counts equally.

2. The disequilibrium score is the mean across all contributing group scores:
   ```
   Disequilibrium = mean( group_score_1, group_score_2, ... )
   ```

> **Important nuance:** Declared equilibria are model assumptions (for example, a 4% unemployment rate), not observed constants. Standardization makes heterogeneous raw distances comparable but does not eliminate uncertainty in those assumptions.

**Code:** `indicators/composites.py` → `compute_composite_history()`, lines 234–245

### 8.4 Interpretation

| Disequilibrium | Interpretation |
|:---------------|:---------------|
| < 0.5 | Low — most forces near historical norms |
| 0.5–1.0 | Moderate — some forces stretched but not extreme |
| 1.0–1.5 | Elevated — multiple forces are 1+ SD from historical norms |
| > 1.5 | High — economy is in a state of sustained extremes; transition risk elevated |

At the current reading (June 2026): **0.82** — moderate, driven primarily by interest payments at a historic extreme (Z=+4.0) and government debt-to-GDP at the 98th percentile.

---

## 9. Data Flow Summary

```
Raw API data
    │
    ▼ apply_transformation() — YoY%, level, or spread
Transformed series
    │
    ▼ build_signals()
    │   ├── _zscore_series()         → zscore (full-history)
    │   ├── _percentile_series()     → level_percentile
    │   ├── compute_momentum()       → change_1m / change_3m / change_12m
    │   ├── _direction()             → direction ("rising" / "falling" / "flat")
    │   └── _is_stale()              → is_stale flag
Signal records (59 per month-end, stored in DuckDB)
    │
    ▼ compute_composite_history()
    │   ├── _load_wide("zscore")        → monthly Z-score matrix (with ffill ≤13m)
    │   ├── _load_wide("direction")     → monthly direction matrix
    │   │
    │   ├── Growth Score               → weighted avg of 9 Z-scores (invert unemployment)
    │   ├── Inflation Score            → weighted avg of 7 Z-scores
    │   ├── Regime Quadrant            → sign(Growth) × sign(Inflation)
    │   ├── Confidence                 → direction-agreement fraction
    │   └── Disequilibrium Score       → mean( mean(|Z|) per force group )
    │
    ▼ upsert_composites()
CompositeSnapshot records (558 months stored in DuckDB, 1980-present)
```

---

## 10. Known Limitations and Design Choices

### 10.1 Z-Scores Relative to Own History, Not a Theoretical Neutral
The sign boundary (zero) means "above or below this series' own historical average." This is empirical, not structural. For example, if US payrolls growth averaged 1.5% YoY for 40 years, a reading of 1.0% scores negative — even though 1% payroll growth is perfectly healthy in absolute terms. This is intentional: the diagnostic question is "are conditions better or worse than normal?" not "are conditions good?"

### 10.2 Equal Weights
All growth indicators carry weight 1.0. This is the simplest defensible prior when there is genuine uncertainty about which signal is most predictive. The config (`composites.yaml`) accepts per-indicator weight overrides without code changes. No empirical optimization of weights has been done — doing so risks overfitting to the historical period.

### 10.3 Full-History Z-Scores (Look-Ahead Bias in Backtests)
Z-scores are computed against the full available history, including future data relative to any historical snapshot. This means a 1995 Z-score "knows" what 2008 or 2020 looked like. For the display/diagnostic purpose of Phase 1, this is acceptable. Phase 3 will implement expanding-window Z-scores for proper backtesting.

### 10.4 Forward-Fill Policy
Quarterly signals (GDP, productivity, credit metrics) are carried forward into monthly composites for up to 13 months. This convention can lag turning points, so `low_history` signals are excluded and stale signals stop contributing from their flagged month.

### 10.5 Confidence Can Mislead Near Boundaries
When the Growth or Inflation Score is very close to zero (e.g., −0.05), the assigned quadrant label is sensitive to small data revisions. A confidence reading below 50% in this situation is the natural signal — the label is technically correct but fragile. Users should interpret the composite score value alongside the quadrant label.

### 10.6 Disequilibrium Uses Standardized Equilibrium Distances
The disequilibrium score uses each signal's `distance_from_equilibrium`, standardized by its own historical variability. This honors the declared theoretical neutral while allowing values in different units to be combined. Results remain sensitive to the quality of those declared equilibria.

### 10.7 Coverage Gaps
Five governance signals (World Bank WGI) are currently deferred — the WGI `.EST` API endpoint was removed from the World Bank v2 API. This means `internal_order` contributes no data to the disequilibrium score. The `low_coverage` flag fires if fewer than 3 of 5 force groups contribute data.

---

## 11. Current US Readings (as of 2026-06-19)

| Metric | Value | Interpretation |
|:-------|:------|:---------------|
| **Regime** | Stagflation | Growth below norm, inflation above norm |
| **Growth Score** | −0.048 | Barely below historical average; near the boundary |
| **Inflation Score** | +0.428 | Meaningfully above historical average |
| **Confidence** | 48% | Weak — signals are mixed, especially on growth side |
| **Disequilibrium** | 0.702 | Moderate displacement from declared equilibria |
| Growth signals active | 9 of 9 | Full coverage |
| Inflation signals active | 8 of 8 | Full configured coverage |
| Force groups (Diseq.) | 3 of 5 | `governance` and `climate` deferred |

### Narrative

The US is technically in Stagflation — growth Z-scores are slightly negative while inflation Z-scores are positive. However the borderline Growth Score (−0.048) means this is a weak classification, and the 48% confidence confirms that directional signals remain mixed. The economy has been in the Stagflation quadrant since March 2023, preceded by an Inflationary Boom period from mid-2021 through early 2023.

The disequilibrium reading reflects standardized displacement from each signal's declared equilibrium. Component contributions should be inspected before attributing the aggregate to particular forces.

---

## 12. Configuration Reference

All tunable parameters live in `config/composites.yaml`. No code changes are needed to:

- Add or remove signals from the Growth or Inflation composite
- Change signal weights (e.g., give core PCE 2.0× weight)
- Change the forward-fill limit (`ffill_limit` in `_load_wide`)
- Change the minimum signals required for a quadrant label (`min_signals_required`)
- Reorganise the disequilibrium force groups

The pipeline must be re-run after any config change to recompute the full historical composite history.

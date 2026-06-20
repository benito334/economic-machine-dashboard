# Methodology Feedback — Implementation Tracker

> Source: `docs/macro_methodology_feedback.md` (Dalio-style review)  
> Last updated: 2026-06-19  
> Legend: ✅ Done · 🟡 In progress · 🔵 Planned · ⬜ Deferred · ❌ Out of scope

---

## Master Tracking Table

| ID | Area | Feedback Item | Action | Effort | Status | Notes |
|---|---|---|---|---|---|---|
| A1 | Signal selection | Add a small subset from Policy / Credit / External lenses as leading inputs to the regime composite | Evaluate top 2–3 candidates (e.g. Fed funds spread, credit growth momentum, trade balance trend); add to composites.yaml | Medium | ⬜ Deferred | Phase 2+ — need cross-country generalisation first |
| A2 | Signal selection | Run correlation matrix + PCA before finalising the 16-signal composite subset | Analysis task: produce heatmap and explained-variance chart in Data Explorer | Medium | 🔵 Planned | Good diagnostic before Eurozone rollout |
| A3 | Signal selection | Apply temporal weighting to annual-frequency lens signals (WB/IMF) to reflect lower timeliness | Build into forward-fill policy or per-signal weight multiplier | Medium | 🔵 Planned | Closely related to F1/L1 (decay); now partly covered by L1 |
| B1 | Transformation | Verify calendar-adjusted N for weekly/daily `pct_change` (52 weeks, 252 trading days) | Audit `apply_transformation()` against each series frequency | Low | 🟡 In progress | Likely already correct; needs explicit test |
| B2 | Transformation | Add short moving-average (e.g. 3-month) before YoY differencing for noisy series | Optional smoothing step in `transform.py`; config-gated per signal | Medium | ⬜ Deferred | Risk of masking genuine turning points; evaluate per series |
| B3 | Transformation | ADF stationarity test on long-run debt / structural ratio series | Add one-time diagnostic script; log findings in decisions/ | Low | 🔵 Planned | Affects debt stress components most |
| C1 | Z-score | Winsorise at ±4σ before computing Z-score | Z-score capped at ±4 after computing — simpler and always bounded | Low | ✅ Done | `_zscore_series()` clips Z at ±4σ; all 269 tests pass |
| C2 | Z-score | Robust statistics option: median + MAD instead of mean + SD for heavy-tailed series | Add `robust=True` mode to `_zscore_series()`; config-gated per signal | Low | ⬜ Deferred | Evaluate after winsorisation is in place |
| C3 | Z-score | Dynamic scaling: track rolling 24-month σ; if volatility spikes, scale Z accordingly | Add rolling-vol normalisation layer post Z-score | High | ⬜ Deferred | Adds complexity; revisit after Phase 3 back-test |
| C4 | Z-score | Expanding-window Z-scores for back-testing (no look-ahead bias) | Phase 3 back-test mode; already planned in methodology.md | High | ⬜ Deferred | Phase 3 work item |
| D1 | Momentum | Percentile-rank the momentum value to normalise across series with different volatilities | Add `momentum_percentile` field alongside existing `change_3m` | Low | 🔵 Planned | Useful for Confidence Score refinement |
| D2 | Momentum | Dynamic window weighting (shorter windows more relevant in volatile regimes) | Research task; implement as regime-conditional weight on 1m/3m/12m | High | ⬜ Deferred | Phase 3 — requires regime labels to define dynamism |
| E1 | Direction flag | Replace `1e-9` threshold with a variance-based significance test (e.g. 95% confidence that 3m change ≠ 0) | `_direction(change_3m, series_std)` — threshold = 10% of series σ | Low | ✅ Done | `normalize.py`; series_std computed in `build_signals()` and passed through |
| E2 | Direction flag | Add strong / moderate / weak qualifier based on change magnitude vs. σ | Extend direction field to include magnitude tier | Low | ⬜ Deferred | Dashboard impact large; design UI first |
| E3 | Direction flag | Store direction flag with lag index for leading indicators | Add `direction_lead_months` metadata field | Medium | ⬜ Deferred | Requires per-signal lead-lag classification |
| F1 | Forward-fill / staleness | Apply exponential decay to forward-filled signal weights in regime composite (0.9^k per month filled) | `_compute_fill_age()` + `return_fill_age` flag in `_load_wide()`; decay applied in score loops | Medium | ✅ Done | `composites.py`; config-gated via `staleness_decay.enabled` in composites.yaml |
| F2 | Forward-fill | Linear interpolation between quarterly release dates instead of flat forward-fill | Optional interpolation mode in `_load_wide()` | Medium | ⬜ Deferred | More accurate but complex; evaluate on GDP / capacity util |
| G1 | Growth composite | Implement group multipliers: labour market ×0.75, output/demand ×1.00, capacity ×1.05 | YAML weight changes: labour signals 0.75, output/demand 1.00, capacity 1.05 | Medium | ✅ Done | `composites.yaml`; engine already reads per-signal weights — no code change needed |
| H1 | Inflation composite | Merge 5Y + 10Y TIPS breakevenss into single `breakeven_avg` signal OR reduce each to 0.5 weight | Reduced each to weight 0.5 in `composites.yaml` | Low | ✅ Done | YAML-only; combined contribution unchanged at 1.0 |
| H2 | Inflation composite | Apply 7-day SMA to daily crude oil before monthly aggregation | `pre_smooth_window: 7` in `us_bindings.yaml`; `CountryBinding.pre_smooth_window` field; applied in pipeline Pass 1 | Low | ✅ Done | `models.py`, `us_bindings.yaml`, `pipeline.py` |
| I1 | Composite construction | OLS-based weight calibration against macro outcomes (incremental explanatory power) | Research task; regression of composite vs. actual GDP / CPI; adjust weights modestly (±20%) | High | ⬜ Deferred | Risk of overfitting; Phase 3 — do after expanding-window Z-scores |
| I2 | Composite construction | PCA orthogonalisation as diagnostic for signal independence | Analysis task: run PCA on 9 growth signals and 8 inflation signals | Low | 🔵 Planned | Good companion to A2; no code change needed |
| J1 | Staleness — **debt stress only** | Exponential weight decay for stale components | Implemented in `indicators/longterm_stress.py` | — | ✅ Done (debt stress) | true half-life=4q, min_frac=0.20 — **NOT applied to regime composite** |
| J2 | Staleness — **debt stress only** | Carry-forward cap | Implemented in all builder functions | — | ✅ Done (debt stress) | max_carry_quarters=4 — **NOT applied to regime composite** |
| J3 | Staleness — **debt stress only** | Model-based extrapolation gate | Implemented; `enabled: false` by default | — | ✅ Done (debt stress) | rolling_mean or linear_trend — **NOT applied to regime composite** |
| J4 | Staleness — **debt stress only** | Structured stale strings ("cid:lag_q") and audit trail | `stale_components` + `extrapolated_components` in DB | — | ✅ Done (debt stress) | Dashboard shows badges — **NOT applied to regime composite** |
| J5 | Staleness — **debt stress only** | Dashboard display of blank component reasons | Full-width component table with BLANK / STALE / ACTIVE badges | — | ✅ Done (debt stress) | Deployed on :8502 — **NOT applied to regime composite** |
| L1 | Staleness — **regime composite** | Forward-fill weight decay in `_load_wide()` | Implemented as part of F1 — `_compute_fill_age()` + decay in score loops | Medium | ✅ Done | Covered by F1 implementation in `composites.py` |
| L2 | Staleness — **regime composite** | Explicit carry cap per signal (replace hard ffill_limit with per-frequency cap) | Mirror max_carry_quarters logic from debt stress; Q signals cap at ~3 months, A at ~15 | Medium | 🔵 Planned | Regime equivalent of J2; 13m blanket limit ignores signal frequency |
| L3 | Staleness — **regime composite** | Per-signal staleness tracking in CompositeSnapshot | Store which signals were decayed/dropped at each snapshot month in a structured field | Medium | 🔵 Planned | Regime equivalent of J4; needed for audit trail and dashboard |
| L4 | Staleness — **regime composite** | Dashboard staleness lag detail in Regime History component table | Show "stale Nq" badge with lag count per signal (component table already has STALE badge but no lag) | Low | 🔵 Planned | Regime equivalent of J5; UI already half-done |
| L5 | Staleness — **regime composite** | Extrapolation gate for long-stale regime signals | Config-gated; likely low value for monthly signals that refresh frequently | Low | ⬜ Deferred | Regime equivalent of J3; monthly series rarely gap >3 months |
| K1 | General | Back-test each modification on rolling window; compare out-of-sample performance to baseline | Phase 3 infrastructure; requires expanding-window Z-scores (C4) | High | ⬜ Deferred | Phase 3 |
| K2 | General | Continuous feedback loop: compare regime prediction to actual monthly macro outcomes | Post-Phase 3; automated monthly audit | High | ⬜ Deferred | Phase 3+ |

---

## Component-by-Component Summary

### Signal Universe (A1–A3)
The feedback calls for broadening the regime composite beyond Lenses A and B to include leading signals from Policy (C), Credit/Debt (D), and External/Trade (F). **Deferred to Phase 2** — the cross-country generalisation problem makes ad-hoc US-only additions risky before we know which signals will exist in Eurozone. A correlation matrix + PCA analysis (A2) is the right pre-work and can be done in the Data Explorer before the next phase. Annual-frequency signals from WB/IMF (A3) should have their forward-fill contribution decay-weighted — this is the same mechanism as F1 and the two should be implemented together.

### Transformation (B1–B3)
Three items. Calendar-adjusted N (B1) is likely already correct but needs a targeted test — low effort. Pre-differencing smoothing (B2) is risky because a moving average can mask genuine turning points; leave deferred and evaluate series-by-series. ADF stationarity testing (B3) is a one-time analysis task, most relevant to the debt stress components (long-run debt ratios, structural balance) — plan to run before Eurozone rollout.

### Z-Score Normalisation (C1–C4)
**C1 is done.** Implemented as Z-score capping at ±4σ (clip the resulting Z, not the raw values) in `_zscore_series()` — simpler than pre-value-winsorisation and always bounds the output. COVID spikes now cap at ±4 rather than distorting the scale. Robust statistics (C2) is a follow-on. Dynamic scaling (C3) and expanding windows (C4) are Phase 3 work.

### Momentum (D1–D2)
Percentile-ranking the momentum value (D1) is a clean, low-effort addition to normalize_py — this makes the `change_3m` comparable across series with very different volatility (e.g. oil vs. PCE). Dynamic window weighting (D2) requires regime labels as input to define the weighting, making it inherently Phase 3.

### Direction Flag (E1–E3)
**E1 is done.** `_direction(change_3m, series_std)` — threshold is now 10% of the series standard deviation, passed from `build_signals()`. Prevents low-volatility series (e.g. structural ratios) from triggering "rising/falling" on near-zero drift. The strong/moderate/weak qualifier (E2) is useful but requires a dashboard redesign — deferred. Lag-index metadata (E3) deferred.

### Forward-Fill and Staleness for Regime Composite (F1–F2)
**F1 is done (= L1).** `_compute_fill_age()` tracks months since last observation per signal. In `compute_composite_history()`, effective weight = `base_weight × 0.9^fill_age`. Config-gated via `staleness_decay.enabled` in `composites.yaml` (default: `true`, `decay_factor: 0.9`). At 13 months of fill the signal still contributes at ~25% weight before the stale exclusion zeroes it. Linear interpolation (F2) deferred.

### Growth Composite Weighting (G1)
**Done.** YAML weight changes in `composites.yaml`: payrolls, job_openings, labor_force_part, unemployment → 0.75 each; industrial_prod, retail_sales, real_pce, pmi_proxy remain 1.00; capacity_util → 1.05. Effective group totals: labour=3.0, output/demand=4.0, capacity=1.05. No engine changes needed.

### Inflation Composite Weighting (H1–H2)
**Both done.** H1: breakeven_5y and breakeven_10y weights both reduced from 1.0 to 0.5 in `composites.yaml` — combined contribution stays 1.0, double-counting eliminated. H2: `pre_smooth_window: 7` added to crude_oil binding in `us_bindings.yaml`; `CountryBinding.pre_smooth_window` optional field added to model; Pass 1 of pipeline applies `rolling(7).mean()` to raw prices before YoY transformation.

### Composite Construction — General (I1–I2)
PCA analysis (I2) is a low-cost diagnostic that can reveal whether the current 9-signal growth composite is dominated by 2–3 underlying factors. This is analysis, not a code change, and can be run in a notebook. OLS weight calibration (I1) is intentionally deferred — the existing equal-weight prior is a deliberate choice to avoid overfitting to the relatively short post-1980 US macro history. Revisit after Phase 3 expanding windows are in place.

### Staleness — Debt Stress (J1–J5)
**All five items are complete for the Long-Term Debt Stress Indicator only.** The three-gap staleness implementation (weight decay, carry cap, extrapolation gate) is live in `indicators/longterm_stress.py`. Dashboard displays STALE / BLANK / EXTRAPOLATED badges with full audit detail. None of this has been applied to the macro regime composite — see L1–L5 below.

### Staleness — Regime Composite (L1–L5)
**L1 is done (implemented as F1).** The decay is live in `composites.py` via `_compute_fill_age()` + per-signal `0.9^fill_age` multiplier. **L2 (per-frequency carry cap)** is the next item — it requires looking up the frequency of each signal from the binding YAML and passing a `per_signal_limits` dict to `_load_wide()`. **L3 (structured per-signal stale tracking in CompositeSnapshot)** enables the audit trail and feeds the L4 dashboard lag badges. L5 (extrapolation gate) remains deferred — monthly signals rarely gap long enough.

### General / Phase 3 (K1–K2)
Both items depend on the Phase 3 back-test infrastructure (expanding-window Z-scores, rolling-window performance measurement). Tracked here for completeness.

---

## Prioritised Implementation Queue

Items recommended for the next working session, roughly in order:

| Priority | ID | Item | Rationale | Status |
|---|---|---|---|---|
| — | H1 | Breakeven weights → 0.5 | ✅ Done this session | ✅ |
| — | H2 | 7-day SMA for crude oil | ✅ Done this session | ✅ |
| — | G1 | Labour ×0.75, capacity ×1.05 | ✅ Done this session | ✅ |
| — | C1 | Z-score cap at ±4σ | ✅ Done this session | ✅ |
| — | E1 | Variance-based direction threshold | ✅ Done this session | ✅ |
| — | F1/L1 | Staleness decay in regime composite | ✅ Done this session | ✅ |
| 1 | L2 | Per-frequency carry cap in `_load_wide()` | Q cap ~3 months, A cap ~15; needs frequency metadata lookup | 🔵 Planned |
| 2 | L3 | Per-signal staleness tracking in CompositeSnapshot | Structured stale field for regime composite; feeds L4 dashboard | 🔵 Planned |
| 3 | A2 / I2 | Correlation matrix + PCA on composite signals | Analysis; informs further weight tuning | 🔵 Planned |
| 4 | D1 | Percentile-rank momentum value | Normalises change_3m across series with different volatilities | 🔵 Planned |
| 5 | B1 | Audit calendar-adjusted N in transformation | Quick verification; add test | 🟡 In progress |

---

*All items and their status are reflected in the master table above. Update the Status column as each is completed.*

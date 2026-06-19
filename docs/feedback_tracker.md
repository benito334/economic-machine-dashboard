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
| A3 | Signal selection | Apply temporal weighting to annual-frequency lens signals (WB/IMF) to reflect lower timeliness | Build into forward-fill policy or per-signal weight multiplier | Medium | 🔵 Planned | Closely related to F1 (decay); do together |
| B1 | Transformation | Verify calendar-adjusted N for weekly/daily `pct_change` (52 weeks, 252 trading days) | Audit `apply_transformation()` against each series frequency | Low | 🟡 In progress | Likely already correct; needs explicit test |
| B2 | Transformation | Add short moving-average (e.g. 3-month) before YoY differencing for noisy series | Optional smoothing step in `transform.py`; config-gated per signal | Medium | ⬜ Deferred | Risk of masking genuine turning points; evaluate per series |
| B3 | Transformation | ADF stationarity test on long-run debt / structural ratio series | Add one-time diagnostic script; log findings in decisions/ | Low | 🔵 Planned | Affects debt stress components most |
| C1 | Z-score | Winsorise at ±4σ before computing Z-score | Add `winsorise` step in `_zscore_series()` — config flag | Low | 🔵 Planned | Small change; high benefit for outlier events like COVID |
| C2 | Z-score | Robust statistics option: median + MAD instead of mean + SD for heavy-tailed series | Add `robust=True` mode to `_zscore_series()`; config-gated per signal | Low | ⬜ Deferred | Evaluate after winsorisation is in place |
| C3 | Z-score | Dynamic scaling: track rolling 24-month σ; if volatility spikes, scale Z accordingly | Add rolling-vol normalisation layer post Z-score | High | ⬜ Deferred | Adds complexity; revisit after Phase 3 back-test |
| C4 | Z-score | Expanding-window Z-scores for back-testing (no look-ahead bias) | Phase 3 back-test mode; already planned in methodology.md | High | ⬜ Deferred | Phase 3 work item |
| D1 | Momentum | Percentile-rank the momentum value to normalise across series with different volatilities | Add `momentum_percentile` field alongside existing `change_3m` | Low | 🔵 Planned | Useful for Confidence Score refinement |
| D2 | Momentum | Dynamic window weighting (shorter windows more relevant in volatile regimes) | Research task; implement as regime-conditional weight on 1m/3m/12m | High | ⬜ Deferred | Phase 3 — requires regime labels to define dynamism |
| E1 | Direction flag | Replace `1e-9` threshold with a variance-based significance test (e.g. 95% confidence that 3m change ≠ 0) | Replace fixed epsilon with `change_3m / rolling_std > t_crit` in `_direction()` | Low | 🔵 Planned | Reduces false "rising/falling" on nearly-flat series |
| E2 | Direction flag | Add strong / moderate / weak qualifier based on change magnitude vs. σ | Extend direction field to include magnitude tier | Low | ⬜ Deferred | Dashboard impact large; design UI first |
| E3 | Direction flag | Store direction flag with lag index for leading indicators | Add `direction_lead_months` metadata field | Medium | ⬜ Deferred | Requires per-signal lead-lag classification |
| F1 | Forward-fill / staleness | Apply exponential decay to forward-filled signal weights in regime composite (0.9^k per month filled) | Add decay multiplier in `_load_wide()` alongside ffill; config-gated | Medium | 🔵 Planned | Dalio explicitly recommends this; analogous to debt stress decay |
| F2 | Forward-fill | Linear interpolation between quarterly release dates instead of flat forward-fill | Optional interpolation mode in `_load_wide()` | Medium | ⬜ Deferred | More accurate but complex; evaluate on GDP / capacity util |
| G1 | Growth composite | Implement group multipliers: labour market ×0.75, output/demand ×1.00, capacity ×1.05 | Add `groups:` block to `composites.yaml`; update `compute_composite_history()` | Medium | 🔵 Planned | Specific weights from feedback; config-only if group logic added to engine |
| H1 | Inflation composite | Merge 5Y + 10Y TIPS breakevenss into single `breakeven_avg` signal OR reduce each to 0.5 weight | Either add derived signal in pipeline OR change YAML weights to 0.5 each | Low | 🔵 Planned | YAML-only change if we keep both at 0.5; pipeline change if we merge |
| H2 | Inflation composite | Apply 7-day SMA to daily crude oil before monthly aggregation | Add `daily_to_monthly_sma()` in `transform.py`; wire into oil signal loader | Low | 🔵 Planned | Clean, low-risk change; keeps oil at 0.5 weight |
| I1 | Composite construction | OLS-based weight calibration against macro outcomes (incremental explanatory power) | Research task; regression of composite vs. actual GDP / CPI; adjust weights modestly (±20%) | High | ⬜ Deferred | Risk of overfitting; Phase 3 — do after expanding-window Z-scores |
| I2 | Composite construction | PCA orthogonalisation as diagnostic for signal independence | Analysis task: run PCA on 9 growth signals and 8 inflation signals | Low | 🔵 Planned | Good companion to A2; no code change needed |
| J1 | Staleness — debt stress | Linear weight decay for stale components | Implemented in `indicators/longterm_stress.py` | — | ✅ Done | halflife=4q, min_frac=0.20 |
| J2 | Staleness — debt stress | Carry-forward cap | Implemented in all builder functions | — | ✅ Done | max_carry_quarters=4 |
| J3 | Staleness — debt stress | Model-based extrapolation gate | Implemented; `enabled: false` by default | — | ✅ Done | rolling_mean or linear_trend |
| J4 | Staleness — debt stress | Structured stale strings ("cid:lag_q") and audit trail | `stale_components` + `extrapolated_components` in DB | — | ✅ Done | Dashboard shows badges |
| J5 | Staleness — debt stress | Dashboard display of blank component reasons | Full-width component table with BLANK / STALE / ACTIVE badges | — | ✅ Done | Deployed on :8502 |
| K1 | General | Back-test each modification on rolling window; compare out-of-sample performance to baseline | Phase 3 infrastructure; requires expanding-window Z-scores (C4) | High | ⬜ Deferred | Phase 3 |
| K2 | General | Continuous feedback loop: compare regime prediction to actual monthly macro outcomes | Post-Phase 3; automated monthly audit | High | ⬜ Deferred | Phase 3+ |

---

## Component-by-Component Summary

### Signal Universe (A1–A3)
The feedback calls for broadening the regime composite beyond Lenses A and B to include leading signals from Policy (C), Credit/Debt (D), and External/Trade (F). **Deferred to Phase 2** — the cross-country generalisation problem makes ad-hoc US-only additions risky before we know which signals will exist in Eurozone. A correlation matrix + PCA analysis (A2) is the right pre-work and can be done in the Data Explorer before the next phase. Annual-frequency signals from WB/IMF (A3) should have their forward-fill contribution decay-weighted — this is the same mechanism as F1 and the two should be implemented together.

### Transformation (B1–B3)
Three items. Calendar-adjusted N (B1) is likely already correct but needs a targeted test — low effort. Pre-differencing smoothing (B2) is risky because a moving average can mask genuine turning points; leave deferred and evaluate series-by-series. ADF stationarity testing (B3) is a one-time analysis task, most relevant to the debt stress components (long-run debt ratios, structural balance) — plan to run before Eurozone rollout.

### Z-Score Normalisation (C1–C4)
**Winsorisation at ±4σ (C1) is the most actionable and lowest-risk change here** — a single line in `_zscore_series()`, config-gated. COVID readings (March 2020) likely push several series beyond ±4σ and distort the full-history mean and standard deviation for everything else. This should be an early implementation. Robust statistics (C2) is a follow-on once winsorisation is tested. Dynamic scaling (C3) and expanding windows (C4) are Phase 3 work already planned.

### Momentum (D1–D2)
Percentile-ranking the momentum value (D1) is a clean, low-effort addition to normalize_py — this makes the `change_3m` comparable across series with very different volatility (e.g. oil vs. PCE). Dynamic window weighting (D2) requires regime labels as input to define the weighting, making it inherently Phase 3.

### Direction Flag (E1–E3)
The variance-based significance threshold (E1) replaces `1e-9` with something more principled — a series should only be called "rising" if the 3-month change is statistically distinguishable from noise. Small code change with meaningful downstream effects on Confidence Score quality. The strong/moderate/weak qualifier (E2) is useful but requires a dashboard redesign to display — deferred. The lag-index metadata (E3) is a data modelling enhancement deferred to a later phase.

### Forward-Fill and Staleness for Regime Composite (F1–F2)
**F1 is the most directly impactful near-term improvement.** Currently the regime composite does a hard forward-fill (ffill_limit=13 months) with no weight decay — a quarterly signal contributes at full weight whether it was observed last month or 12 months ago. Adding 0.9^k decay (or the linear decay already built for debt stress) would make the composite more responsive near revision dates. This is the debt-stress staleness pattern applied to `_load_wide()`. Linear interpolation (F2) is more complex and lower priority.

### Growth Composite Weighting (G1)
The feedback proposes explicit group multipliers: labour-market signals collectively at 0.75× individual weight, output/demand at 1.00×, capacity utilisation at 1.05×. **The simplest implementation is a YAML-only change** — set the four labour-market signals to `weight: 0.75` and the four output/demand signals to `weight: 1.00` (they are already there). The composites engine already reads per-signal weights. No group-multiplier infrastructure needed. Effective total weights become: labour=3.0, output/demand=4.0, capacity=1.05.

### Inflation Composite Weighting (H1–H2)
**H1 (breakeven consolidation) is a one-line YAML change** — reduce both `breakeven_5y` and `breakeven_10y` to `weight: 0.5`. This immediately eliminates the double-counting while preserving both series as independent inputs for correlation diagnostics. Merging into a single derived signal is the cleaner long-term approach but requires a pipeline change. **H2 (crude oil SMA) is a small, well-scoped pipeline change** — add a 7-day SMA step in the oil signal's transformation before monthly resampling. Both H1 and H2 can be done together in one session.

### Composite Construction — General (I1–I2)
PCA analysis (I2) is a low-cost diagnostic that can reveal whether the current 9-signal growth composite is dominated by 2–3 underlying factors. This is analysis, not a code change, and can be run in a notebook. OLS weight calibration (I1) is intentionally deferred — the existing equal-weight prior is a deliberate choice to avoid overfitting to the relatively short post-1980 US macro history. Revisit after Phase 3 expanding windows are in place.

### Staleness — Debt Stress (J1–J5)
**All five items are complete.** The three-gap staleness implementation (weight decay, carry cap, extrapolation gate) is live in `indicators/longterm_stress.py`. Dashboard displays STALE / BLANK / EXTRAPOLATED badges with full audit detail.

### General / Phase 3 (K1–K2)
Both items depend on the Phase 3 back-test infrastructure (expanding-window Z-scores, rolling-window performance measurement). Tracked here for completeness.

---

## Prioritised Implementation Queue

Items recommended for the next working session, roughly in order:

| Priority | ID | Item | Rationale |
|---|---|---|---|
| 1 | H1 | Reduce both TIPS breakevens to weight 0.5 | One-line YAML change; eliminates double-counting immediately |
| 2 | H2 | 7-day SMA for crude oil before monthly aggregation | Small pipeline change; removes intra-month noise |
| 3 | G1 | Labour-market signals → 0.75 weight; output/demand → 1.00 | YAML change; brings composite in line with economic logic |
| 4 | C1 | Winsorise at ±4σ in `_zscore_series()` | Protects all historical Z-scores from COVID/GFC outlier distortion |
| 5 | E1 | Variance-based direction threshold (replace 1e-9) | Improves Confidence Score quality; small normalise.py change |
| 6 | F1 | Exponential decay for forward-filled regime signals | Carries debt-stress staleness pattern into regime composite |
| 7 | A2 / I2 | Correlation matrix + PCA on composite signals | Analysis task; informs whether further weight changes are warranted |
| 8 | B1 | Audit calendar-adjusted N in transformation | Quick verification; add test |

---

*All items and their status are reflected in the master table above. Update the Status column as each is completed.*

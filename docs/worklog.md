# Worklog — Indicators Machine

Log entries are newest-first. Each entry: date, what was done, what is next, any blockers.

---

## 2026-06-26 — Rolling Z fix, chart polish, signals subnav, repo made private

**Done:**
- **Rolling Z fix on force detail pages**: `load_signal_history` allowlist expanded to include all rolling Z columns (`zscore_36m/48m/60m/90m/120m`). Force detail callback now passes `g_zcol`/`i_zcol` to `load_multi_signal_history` so per-signal Z panels update when the lookback slider changes.
- **Composite Z chart styling**: `fill="tozeroy"` with per-force shading; line width 1.5; `y=0` dotted midline; amber dashed ±threshold hlines for growth/inflation pages — matches Regime History style.
- **Composite Momentum panel**: new Row 2 on growth/inflation/rate/credit force pages; amber `#E8A317` with fill, 50% dotted midline, % Y-axis. Volatility page skipped (no DB momentum column).
- **Signals subnav collapse**: sub-pages (Growth/Inflation/Rate/Credit/Volatility) now hidden by default and expand on hover or when any `/signals/*` page is active. Pure CSS: `max-height` transition on `.signals-subnav`, `:hover` + `:has(.active)` selectors. Signals NavLink changed to `active="partial"` so it stays highlighted on all sub-routes.
- **Repo made private**: `github.com/benito334/indicators-machine` set to PRIVATE via `gh repo edit`.

**Next:**
- Phase 3: Back-testing engine (FRED vintage replay — named scenarios: 1970s stagflation, 2008 GFC, 2020 COVID) + simulation engine (parameter sweep / sensitivity to weights, thresholds, lookback windows).

---

## 2026-06-26 — Force detail sub-pages + chart alignment fixes

**Done:**

- **Force detail sub-pages** (`dashboard/force_detail.py`, new ~290-line file): 5 pages at `/signals/{force}` (growth, inflation, rate, credit, volatility). Each page: banner strip (Force Z · Momentum · Active · In Agreement · Threshold · Lookback), collapsible 8-column signal table (same as `/signals` main page), stacked time-series chart (composite Z row 1, then raw-value + Z-score dual panels per signal). Shared hover spike via clientside JS mirrors Regime History tab. VIX page uses daily raw data (no composite row); composite forces use monthly-resampled data.
- **`load_signal_units()`** added to `dashboard/charting_data.py`: queries `signals` table for `units` per signal_id list; used by force detail chart builder.
- **`_comp_arrow()`** promoted to module-level in `dashboard/signals_page.py` (was a closure inside `render_signals()`); signature `_comp_arrow(comp_df, force)` — importable by `force_detail.py`.
- **Sidebar sub-nav**: 5 `.sidebar-subnav` links under Signals in `charting.py`; `.sidebar-subnav` CSS class in `theme.css` (0.78rem, 0.80 opacity, full opacity on hover/active).
- **Bug fixes (this session):**
  - *Z-score column mismatch*: `_build_force_chart()` was hardcoding base `growth_score`/`inflation_score` regardless of rolling-window store. Now `_render()` computes `chart_score_col` (e.g., `growth_score_36m`) matching the banner, and passes it explicitly.
  - *Date misalignment*: Composites store month-end dates (`2026-05-31`); signals store native observation dates (`2026-05-01` for monthly FRED, weekly dates for bank loans, etc.). Both are now normalized to first-of-month before plotting — composite via `dt.to_period("M").dt.to_timestamp()`, signals via index resample + `.groupby().last()`. VIX (no composite row) skips resampling and keeps daily granularity.
  - *Regime History divergence*: Same root cause as Z-score mismatch — force detail always plotted full-history `growth_score` while Regime History used the window-adjusted variant. Fixed by the same `chart_score_col` parameter.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after BEA Q1 2026 data release to clear 3 stale US signals.
- KR monthly CPI: BoK ECOS API registration needed.

---

## 2026-06-26 — Rate/Credit composites + per-signal age-decay half-lives

**Done:**

- **Rate/Credit composites engine** (`indicators/composites.py`, `indicators/models.py`, `store/store.py`): Extended `_score_force()` path (importance × momentum tilt × age decay) to all four forces. Added `rate_score`, `credit_score`, `rate_momentum`, `credit_momentum` DB columns and `CompositeSnapshot` fields. `weight_audit` JSON now includes `"rate"` and `"credit"` keys alongside growth/inflation.
- **Signals page rate/credit display** (`dashboard/signals_page.py`): Rate and Credit sections now use `_composite_rows()` (full 8-column table with importance, config wt, eff wt, Z-bar, momentum) instead of `_signal_rows()`. Fixed two generic bugs in `_composite_rows()`: `positive_dir` was hardcoded for growth (`invert` check now force-agnostic); momentum color flip only applies to `inflation` force now (not every non-growth force).
- **`charting_data.py`**: `load_composite_component_status()` extended to iterate `rate_score` and `credit_score` config sections; `_zscore_col_for` mapping covers `rate` and `credit`.
- **US Interest Rate basket redesign** (`config/countries/us_composites.yaml`): Replaced 9-signal basket (mixed policy + premium + balance-sheet) with 6 pure policy-rate / term-structure signals: `fed_funds_target` (PRIMARY 0.95), `real_yield_10y` (PRIMARY 0.90), `fed_funds` (PRIMARY 0.88), `real_fed_funds` (STRONG 0.75), `yield_2y` (STRONG 0.70), `yield_10y` (CONTEXT 0.45).
- **US Credit basket rebuilt** (`config/countries/us_composites.yaml`): Expanded from 5 to 7 signals — added `corporate_debt` (STRONG 0.65, Corporate Debt Outstanding Growth YoY%) and new `corporate_debt_gdp` (CONTEXT 0.40, BIS/FRED quarterly stock measure). Full basket: bank_loans → lending_standards → corporate_debt → debt_service_ratio → household_debt_gdp → corporate_debt_gdp → gov_debt_gdp.
- **New binding** (`config/us_bindings.yaml`): `credit.corporate_debt_gdp` → FRED `QUSNAM770A` ("Total Credit to Non-Financial Corporations as % of GDP", BIS quarterly). Equilibrium 70.0, sanity 30–130. Signal live (72.2% GDP at Oct 2025).
- **EZ/KR composites** (`config/countries/ez_composites.yaml`, `kr_composites.yaml`): Added `rate_score` and `credit_score` sections (EZ: 5+4 signals; KR: 1+1 minimal stubs pending data rollout).
- **Per-signal age-decay half-lives** — Interest Rate basket: `fed_funds_target`/`fed_funds`/`real_fed_funds` = 3m (short-end, discrete FOMC jumps); `yield_2y` = 4m (forward-pricing); `real_yield_10y`/`yield_10y` = 6m (long-end, structurally slow). Credit basket: `bank_loans` = 3m; `lending_standards`/`corporate_debt` = 4m (fast-moving quarterly flow); `debt_service_ratio` = 6m (stock-ish, quarterly); `household_debt_gdp`/`corporate_debt_gdp` = 9m (slow structural); `gov_debt_gdp` = 12m (annual). Engine reads `half_life_months` per-signal from composites YAML; falls back to global 3m; stored in `weight_audit` JSON.
- **Methodology Section 6** (`dashboard/methodology.py`): "Observation-age decay" subsection now has a 5-row half-life tier table (3m → 4m → 6m → 9m → 12m) with signal-type descriptions and rationale; carry-cap vs half-life distinction clarified.
- **Methodology Section 7**: Both basket tables extended with "Half-life" column. Interest Rate table row order changed to group short-end (3m) then long-end (6m). Credit table shows all 7 signals.
- **Methodology Section 8**: Rewritten to cover three distinct momentum roles — (1) weight tilt in pipeline, (2) dual-condition chip classification in dashboard, (3) stored quadrant (sign-only).
- **65 US signals** (was 64); **558 US composite snapshots** recomputed with updated baskets and half-lives. 354 tests still pass.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after BEA Q1 2026 data release to clear 3 stale US signals.
- KR monthly CPI: BoK ECOS API registration needed.

---

## 2026-06-25 — Regime UI polish + methodology audit

**Done:**
- **Slider styling fixes** (`dashboard/assets/theme.css`): tooltip boxes below sliders hidden (`dash-slider-tooltip { display: none }`); slider track/range/thumb styled with `--slider-accent` amber; value-display input box (`.dash-input-container`) given dark background (`var(--card-bg)`) with amber text and monospace font; mark labels forced amber via `.modal-body .dash-slider-mark`.
- **Modal dark-theme overrides**: `.modal-content`, `.modal-header`, `.modal-footer` wired to `--card-bg`/`--border-color`; all modal slider parts inherit the sidebar slider palette.
- **Auto-open bug fix** (`_toggle_threshold_modal` callback): Dash 4.x resolves `ctx.triggered_id` to the first Input even at n_clicks=0; fixed with `if ctx.triggered_id == "rh-threshold-open" and (n_open or 0) > 0` guard.
- **Header threshold display**: `html.Div(id="rh-threshold-display")` added to Regime History header; `_update_threshold_display` callback renders live G·Z / I·Z / G·Δ / I·Δ chips in amber monospace inline with Prev/Now/Next buttons.
- **Regime chart wired to threshold store**: `update_regime_chart` now takes `Input("regime-threshold-store", "data")`; Row 1 redesigned to dual-band scatter (Growth band at y=0.25, Inflation band at y=0.75); ±gz hlines added to Row 2 (Growth Z); ±iz hlines added to Row 4 (Inflation Z).
- **"Regime Thresholds" button**: replaced ⚙ gear icon with `dbc.Button("Regime Thresholds", color="warning")` for visibility.
- **Methodology page Section 1 updated**: description changed from "four macro seasons" to "two independent regime dimensions"; "Quadrant" concept row replaced with separate "Growth Regime" and "Inflation Regime" rows.
- **Methodology page Section 8 rewritten**: old 4-season quadrant table replaced with dual-condition classification table (Growth/Transition/Retraction + Inflation/Transition/Disinflation), threshold explanation, configurable defaults, and localStorage persistence note.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).

---

## 2026-06-25 — Configurable regime classification system

**Done:**
- **New two-label regime classification** (`dashboard/charting.py`): replaced single "Inflationary Boom / Stagflation / Expansion / Disinflationary Slowdown" badge with two independent chips — Growth chip (Growth · Transition · Retraction) and Inflation chip (Inflation · Transition · Disinflation).
- **`_classify_regime(g_score, i_score, g_delta, i_delta, thresholds)`** function: dual condition — Z threshold (±gz/±iz) AND MoM delta threshold (gm/im) must both be satisfied to enter a named regime; otherwise lands in Transition.
- **`regime-threshold-store`** (localStorage): default `{gz:0.5, iz:0.5, gm:0.0, im:0.0}`.
- **`_THRESHOLD_MODAL`**: ⚙ button in Regime History header opens modal with four sliders (Growth Z, Inflation Z, Growth Mom, Inflation Mom); "Apply" persists to store, "Reset Defaults" reverts; sliders populate from store on open.
- **Threshold-aware `_sem_z_color`** in `charting.py` and `_semantic_z_color` in `signals_page.py`: neutral zone = ±thresh (configurable); colour magnitude scales above it (floored at 35% intensity so never invisible).
- **Scatter chart threshold lines**: four dashed lines at ±gz (vertical) and ±iz (horizontal) update live with store.
- **`update_regime_info` callback** now accepts `regime-threshold-store` as Input; `_regime_info_children` passes `thresholds` through to classify and color.
- **Signals page** (`render_signals`) receives `regime-threshold-store`; passes `thresh` to `_composite_rows` → `_semantic_z_color`.
- **354/354 tests pass.** Container rebuilt and serving HTTP 200.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).

---

## 2026-06-25 — Composites stale-exclusion fix + signal QAQC

**Done:**
- **Fix: `_load_wide(exclude_unreliable=True)` now preserves the observation month for stale signals** (`indicators/composites.py`). Previously, a daily signal marked `is_stale=True` (e.g., crude oil last obs June 15) had its Z-score zeroed from the END of the observation month (June 30) onward — wiping it from the June composite. Fix: `stale_from = (period + 1).to_timestamp("M")`. A June 15 observation is now available at the June composite; zeroing starts from July onward.
- **Pipeline re-run** — fetched fresh crude oil data (June 22, `is_stale=False`); crude oil now contributing to June inflation composite (`eff_wt=0.0097`, `missing=False`).
- **US quadrant updated to Inflationary Boom** (growth=+0.015, inflation=+0.434). Was misclassified as Stagflation while crude oil was excluded.
- **Signal QAQC**: `us.credit.bank_loans` / `ez.policy.central_bank_assets` (weekly, ~15d) — display-only stale, not in composites. EZ yields (ECB IRS lag, 145-175d) — no free-API fix. KR CPI/IP — correctly excluded. All genuinely stale signals confirmed not affecting composite calculations.
- **US signal count corrected to 64** in tests (`test_load_signal_overview_returns_all_signals`, `test_explorer_signal_table_callback`).
- **354/354 tests pass.**

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).

---

## 2026-06-25 — Signal drill-down, info popup, color palette, composite momentum

**Done:**
- **Debt stress 5→7 components**: added FRED-derived `primary_balance_gdp` (FYFSD+FYOINT) and `govt_revenue_gdp` (FGRECPT quarterly) replacements; `us.fiscal.govt_receipts_qtr` binding in `us_bindings.yaml`; `longterm_stress.yaml` updated; both built by new `_build_primary_balance_gdp_fred()` + `_build_govt_receipts_gdp_fred()` in `longterm_stress.py`.
- **Signal drill-down modal**: pattern-matching `{"type": "signal-link"}` Dash callback; `_signal_link()` in `shared_components.py` wired into all tables (lens tables, Force Component Inputs, Debt Stress table, Signals page). Click → dual-panel chart (value + Z-score) with shared spike hover line.
- **3rd panel raw data**: `_load_signal_binding()` + `_load_raw_cache_series()` in `charting.py`; for FRED `yoy_pct` signals a 3rd subplot shows the raw level from parquet cache before YoY transformation.
- **Shared vertical hover spike across all drill panels**: clientside JS callback mirrors regime history page — draws SVG `<line>` spanning all subplot y-extents on `plotly_hover`; `hovermode="x"` + `showspikes=True` on all traces.
- **Signal info popup (ⓘ icon)**: `_signal_info_icon()` in `shared_components.py` added to all Signals page rows. Pattern-matching `{"type": "info-icon"}` callback opens `signal-info-modal` with signal description, transformed units, raw FRED units (when different), frequency, provider, series ID, last updated.
- **FRED metadata sidecar**: `get_fred_meta(series_id)` in `loader.py` reads/writes `fred_{id}_meta.json` (365-day TTL cache). 76 sidecars backfilled on first access.
- **Dark-theme color palette**: `_lerp_rgb()` + opaque anchors in `shared_components.py`. Replaces `rgba(color, low_alpha)` (invisible on dark bg) with lerp from light washed-out pastel (soft sage/salmon) → vivid saturated (emerald/red-orange). Applied to `_semantic_z_color`, `_momentum_score_color`, `_stress_z_color`, `_sem_z_color`.
- **Signals page composite momentum**: `growth_momentum` + `inflation_momentum` from composites table shown in section headers as `Mom XX%`, color-coded. Rate/Credit/Vol momentum computed on the fly as direction fraction.
- **`ALL`, `PreventUpdate`, `ctx` import fix**: added to top-level Dash import in `charting.py`; removed 3 redundant local `from dash import ctx` lines.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after 2026-06-26 (BEA Q1 2026 data clears 3 stale US signals).

---

## 2026-06-24 — Regime History step reset on navigation

**Done:**
- **Fix: Regime History now defaults to current date on every visit** — added `Input("page-trigger", "data")` to `update_regime_step` callback in `dashboard/charting.py`; when the triggered input is `page-trigger` and the page is `/regime-history`, the step is reset to 0 (most recent composite). Previously, the in-memory `regime-step-index` store retained whatever step the user last navigated to, so returning to the page could show data from a prior month.
- **Investigation: Growth momentum score discrepancy between Regime History and Signals tabs** — confirmed by design: Regime History summary strip shows three distinct momentum metrics (composite Z, MoM Δ, Momentum Z over 12mo) while Signals page section header shows a simple majority-vote direction arrow; the composite Z values (`growth_score`) are the same at step=0 but differ at any non-zero step since Regime History is date-sensitive and Signals always shows latest.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after 2026-06-26 (BEA Q1 2026 release clears 3 stale US signals).

---

## 2026-06-24 — Methodology page audit + per-signal Z-bar window fix

**Done:**
- **Fix: per-signal Z-bars now update with slider changes** — `load_composite_component_status()` gained `g_zscore_col`/`i_zscore_col` params; fetches the appropriate rolling column (e.g. `zscore_36m`) from the signals table and substitutes it into the returned `zscore` field. Both `update_regime_info` (Force Component Inputs table in Regime History) and `render_signals` (/signals page) pass the active col names derived from their window stores.
- **Methodology page audit** (`dashboard/methodology.py`) — updated five sections:
  - **Section 2** (Data Sources): Added Eurostat JSON stats API + ECB SDW SDMX-JSON rows; noted EA20/EA21 geo codes, IRS SDMX format, BOP 400 limitation.
  - **Section 4** (Force Z-Score): Documented independent Growth/Inflation windows (Growth Full/36/48/60m; Inflation Full/60/90/120m); added table of pre-computed DB columns per force; noted per-signal Z-bar live update behaviour.
  - **Section 6** (Dynamic Force Weighting): Replaced stale `config/composites.yaml` reference with `composites_policy.yaml` + `countries/{cc}_composites.yaml` split.
  - **Section 11** (Country Coverage): Replaced "US only (Phase 1)" with current live status (US 63 signals, EZ 34, KR 22); added country table with data sources and known gaps; documented file architecture and EZ current account gap.
  - **Section 13** (Deferred Items): Fixed visible table OLS calibration row from "Deferred" to "✅ Live".
- **353/353 tests pass.** Docker rebuilt; HTTP 200.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after 2026-06-26 (BEA Q1 2026 release clears 3 stale US signals).

---

## 2026-06-24 — Inflation Z-Score window separation + Signals page reformatting

**Done:**
- **Separate Growth / Inflation Z-score lookback windows** — Growth keeps Full/36m/48m/60m slider; Inflation gets a new independent slider: Full / 60m / 90m / 120m.
  - New `inflation-window-store` (`dcc.Store`, `storage_type="local"`) + sidebar "Inflation Z-Score Window" slider (`id=inflation-window-slider`) + Settings modal mirror.
  - New `_INFLATION_WINDOW_COL = {60:"60m", 90:"90m", 120:"120m"}` constant in `charting.py`.
  - Three sync callbacks wire sidebar ↔ modal ↔ store for inflation window (matches pattern used for growth window).
  - `update_regime_info`: added `Input("inflation-window-store")`, now resolves `g_sfx` and `i_sfx` independently; `rolling` dict carries separate `window` + `inflation_window` keys.
  - `update_regime_chart`: same input added; subplot title labels encode `G:Xmo / I:Ymo` for independent windows; quadrant re-derives from combined rolling g/i cols.
  - `update_scatter_chart`: same; axis titles show independent window suffixes.
  - `render_signals` (signals page): added `Input("zscore-window-store")` + `Input("inflation-window-store")`; resolves Growth/Inflation Z independently from rolling cols.
- **New DB columns** — `zscore_90m`, `zscore_120m` in signals table; `inflation_score_90m`, `inflation_score_120m` in composites table.
  - `indicators/models.py`: `zscore_90m`, `zscore_120m` Optional fields.
  - `indicators/normalize.py`: `_ROLLING_MONTHS = [12,18,24,36,48,60,90,120]` — computes new columns.
  - `store/store.py`: DDL + migration + `update_inflation_rolling()` function.
  - `dashboard/charting_data.py`: SELECT includes `inflation_score_90m`, `inflation_score_120m`.
  - `indicators/pipeline.py`: Passes 5e-5f write 90m/120m inflation composites (558 US rows).
- **Signals page reformatted** to Regime History "Force Component Inputs" table style (8 columns: Signal / Importance / Config Wt / Eff Wt / Last Data / Z-bar / Momentum / Status).
- **353/353 tests pass.** Docker rebuilt; HTTP 200 at `:8502`.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.

---

## 2026-06-24 — Signals page (/signals) — 5-force signal breakdown

**Done:**
- **New page** `dashboard/signals_page.py` at `/signals` (nav: Indicators → 📡 Signals).
  - Five collapsible sections: Growth · Inflation · Interest Rate · Credit · Volatility.
  - Each section header shows force name, composite Z-score, and majority-direction momentum arrow.
  - Growth/Inflation Z pulled from `composites` table; Rate/Credit/Volatility computed as unweighted mean of constituent signal Z-scores.
  - Section body: same Indicator/Value/Dir/Pct/Z/Quality table as Regime Map lens drill-downs.
  - Rate section: `force='policy'`, excludes balance-sheet/monetary-base signals (US) and wrongly-mapped fed_funds_target (EZ).
  - Credit section: `force IN ('credit','premium')` — covers spreads, debt ratios, lending standards, yield curves.
  - Volatility section: VIX (US only, 120-month rolling Z), loaded from raw cache; empty for EZ/KR.
- **New shared module** `dashboard/shared_components.py` — extracted force-table helpers (`build_force_table`, `_DIR_ARROW`, `_concept_label`, `_zscore_color`, `_fmt_value`) for reuse.
- `charting.py`: added import, nav entry under Indicators group, `_page_signals()`, `/signals` in `_PAGE_MAP`.
- **353/353 tests pass.** Docker rebuilt at `:8502`; `/signals` returns HTTP 200.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.

---

## 2026-06-23 — Weight Audit page (/weight-audit)

**Done:**
- **New Dash page** `dashboard/weight_audit.py` at `/weight-audit` (nav: Reference → 🔍 Weight Audit). Three panels:
  - **Force Balance**: clustered bar chart of G_mass vs I_mass for all countries (US/EZ/KR); ratio badge green (0.75–1.33) or red.
  - **Signal Correlations**: per-country Pearson r heatmaps for growth and inflation baskets separately; |r| ≥ 0.80 cells outlined in orange; flagged pairs table (|r| ≥ 0.70, same-basket "redundant" pairs in red).
  - **Monte Carlo**: 500-trial ±15% importance perturbation → scatter of (growth_score, inflation_score) outcomes + donut of regime distribution + caption showing % of trials confirming current reading.
- **New `composites.py` functions** (country-agnostic):
  - `compute_force_balance(config)` → `(g_mass, i_mass, ratio)`
  - `compute_signal_correlation_matrix(conn, country, config)` → `(corr_df, growth_ids, inflation_ids)`
  - `monte_carlo_regime_sensitivity(conn, country, config, n_trials, sigma)` → dict
- **353/353 tests pass.** Docker rebuilt and live.
- Committed `3a071c1` and pushed.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.
- Phase 3B `indicators/calibrate.py`: country-agnostic weight calibration via supervised regime scoring.

---

## 2026-06-23 — Signal weight calibration: tier system, force-balance audit, correlation audit

**Done:**
- **Weight tier system** (PRIMARY / STRONG / CONTEXT / VOLATILE) documented and applied across all three country composites (`us_composites.yaml`, `ez_composites.yaml`, `kr_composites.yaml`) as a country-agnostic template. Matches guidance in `docs/Guidance/signal_weight_guidance.md`.
- **Anti-redundancy rule** applied: secondary signal's importance reduced to ≤40% of primary when `[CORR AUDIT]` surfaces |r| > 0.80 same-basket pairs: US cpi_core 0.95→0.65 (vs pce_core), breakeven_10y 0.25→0.20 (vs 5y); EZ cpi_headline base_share 1.0→0.7 importance 0.65→0.45, hicp_energy importance 0.25→0.20; KR cpi_headline 0.60→0.45.
- **`_log_force_balance()`** private function added to `composites.py`: logs `[BALANCE]` INFO/WARNING per country per Pass 5 run. All three now within 0.75–1.33 (US: 1.32, EZ: 0.83, KR: 0.82). Previously US=1.52, EZ=0.63, KR=0.64.
- **`audit_signal_correlations()`** public function added to `composites.py`: queries Z-score history, builds correlation matrix, logs `[CORR AUDIT] WARN` for same-basket pairs above threshold. Called in pipeline after every country's composite upsert.
- **4 test assertions updated** to reflect calibrated values (`test_breakeven_guidance_defaults`, `test_growth_importance_guidance_defaults`, `test_inflation_importance_guidance_defaults`, `test_guidance_nominal_weights_are_normalized_after_quality`). **353/353 tests pass.**
- Committed and pushed: `b095880`.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.
- Phase 3B `indicators/calibrate.py`: country-agnostic weight calibration via supervised regime scoring (see guidance doc Sections 5–9).

---

## 2026-06-23 — EZ signal expansion (cont.) — ECB fetcher, GDP, Debt/GDP, CA investigation

**Done:**
- **Data Explorer country-awareness** (`dashboard/explorer.py`): all 6 callbacks now accept `country-store` as `Input` or `State`. Signal table resets `selected_rows` on country switch. `load_signal_overview(country)` and `load_composite_zscore_matrix(country)` called with selected country throughout.
- **ECB SDW fetcher** (`indicators/loader.py` + `indicators/pipeline.py`): `fetch_ecb_series(flow, key)` added — SDMX-JSON 1.0, parquet cache, TTL-based refresh, same retry/error pattern as Eurostat. Pass 1.6 (ECB) added to `run_country()`: parses `series_id` as `"FLOW/KEY"`, e.g. `"IRS/M.DE.L.L40.CI.0000.EUR.N.Z"`.
- **7 new EZ bindings** (`config/countries/ez_bindings.yaml`):
  - `growth.employment_growth` — Eurostat `namq_10_pe` (EA20, SCA, EMP_DC, PCH_SM_PER, Q). `raw_scale: 100`.
  - `growth.construction_prod` — Eurostat `sts_copr_m` (EA20, F, s_adj=CA, PCH_SM, M). `raw_scale: 100`. Key finding: `SCA` returns empty; `CA` works.
  - `growth.capacity_util` — Eurostat `ei_bsin_q_r2` (EA20, BS-ICU-PC, SA, Q). Level in %, no raw_scale.
  - `fiscal.budget_balance_gdp` — Eurostat `gov_10q_ggnfa` (EA20, B9, S13, PC_GDP, Q). Annual `gov_10dd_edpt1` is EDP-procedure data only; quarterly net lending via `gov_10q_ggnfa`.
  - `credit.yield_de_10y` / `credit.yield_it_10y` — ECB SDW IRS flow (M). Correct flow for Maastricht-criterion 10Y yields; BOP flow returns 400.
  - `credit.btp_bund_spread` — derived (IT − DE); 317 monthly obs, latest May 2026 = 79.4 bps.
- **EZ HICP energy/food sources corrected**: `prc_hicp_manr` publishes Mean Annual Rate and stops at Dec of prior year — switched to FRED index series with `yoy_pct` transform: `CP0450EZ19M086NEST` (electricity/gas) and `CP0100EZ19M086NEST` (food). Both through May 2026.
- **EZ composites re-run**: growth 3→6 signals, inflation 4→6 signals. `ez_composites.yaml` updated. Latest (May 2026): Inflationary Boom, Growth=+0.242, Inflation=+0.666, Confidence=58%.
- **Regime History / Global Overview signal counts fixed**: `n_growth_signals` and `n_inflation_signals` now reflect live signal count from composites engine, not hardcoded values.
- **`ez.master.gdp_level_bn`** — WB `NY.GDP.MKTP.CD` (EMU, annual). `raw_scale: 1e9` converts USD → billions. 35 obs; 2024 = 16,485B USD. Global Overview "GDP" column now populated for EZ.
- **`ez.credit.gov_debt_gdp`** — Eurostat `gov_10dd_edpt1` (EA20, GD, S13, PC_GDP, annual). 27 obs; 2025 = 87.8% GDP. Global Overview "Debt/GDP" now populated for EZ.
- **EA current account — exhaustive investigation, no free source found**: WB EMU (`BN.CAB.XOKA.GD.ZS`) all null; ECB BOP/BP6/BPS/ECB_BOP1/BOP_BNT all HTTP 400 or 404; FRED series don't exist or cut off 2012; Eurostat `bop_c6_q` always 413 (dataset too large even with all dims specified); IMF Datamapper empty for all EA codes. Fully documented in `docs/Guidance/EU_singals_guidance.md` — slot stays in bindings, returns empty, Global Overview shows dash.
- **EZ now 34 signals live** (was 19). **353 tests pass.**

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.
- EZ current_account_gdp: only option left is a paid ECB Data License or manual Eurostat bulk download. Accept gap for now.

---

## 2026-06-23 — EZ signal expansion + country-aware Data Dashboard

**Done:**
- Added 4 new Eurostat bindings to `config/countries/ez_bindings.yaml`: `inflation.ppi` (PPI), `inflation.wages_lci` (LCI wages, quarterly), `inflation.hicp_energy`, `inflation.hicp_food`. Also 2 derived: `policy.real_yield_10y`, `policy.yield_spread`.
- Added derived dispatch cases for `policy.real_yield_10y` and `policy.yield_spread` in `indicators/pipeline.py`.
- Expanded `config/countries/ez_composites.yaml` inflation_score from 2 → 6 signals (cpi_core + cpi_headline + wages_lci + ppi + hicp_energy + hicp_food).
- Added EZ signal display labels to `_COMPOSITE_SIGNAL_LABELS` in `dashboard/charting_data.py` (ppi, wages_lci, hicp_energy, hicp_food) — fixes force component table for EZ.
- Added EZ + KR signal names to `_SIGNAL_NAMES` in `dashboard/data_dashboard.py`.
- Made Data Dashboard fully country-aware: `_load_binding_meta(country)` and `_load_signals(country)` parameterized; layout uses static force/freq options; callback reads `country-store` and passes it through; sort resets on country switch; description shows country name + signal count.
- `country-store` in `charting.py` changed to `storage_type="local"` — country selection persists over browser refresh.
- **353 tests pass** (4 new from EZ signal additions earlier in session).

**Next:**
- Run pipeline to ingest new EZ signals into DuckDB (`python3 -m indicators.pipeline` for EZ).
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA data refresh (after 2026-06-26) will clear 3 stale US signals.

---

## 2026-06-22 — Per-country composites config split

**Done:**
- Split monolithic `config/composites.yaml` into:
  - `config/composites_policy.yaml` — global methodology (dynamic_weighting, time_decay, per_frequency_ffill_limit, regime_confidence, disequilibrium_score, what_changed)
  - `config/countries/us_composites.yaml` — US indicator lists (9 growth + 8 inflation)
  - `config/countries/ez_composites.yaml` — EZ indicator lists (3 growth + 2 inflation)
  - `config/countries/kr_composites.yaml` — KR indicator lists (3 growth + 3 inflation incl. IMF bridge)
- Refactored `indicators/composites.py`: `load_composites_config(country="US")` merges policy + country file; `_load_country_composites()` errors loudly if `{cc}_composites.yaml` is missing
- Updated `indicators/pipeline.py`: US pass loads `load_composites_config("US")`; country loop tries `load_composites_config(country_code.upper())` and skips with warning if no file found
- Updated `dashboard/charting_data.py`, `dashboard/charting.py`, `dashboard/explorer_data.py`: all replaced direct `composites.yaml` reads with `load_composites_config(country)`
- `cpi_imf_annual` removed from US composites (it's a KR-only bridge); test updated 18→17 for `test_returns_17_columns`
- `config/composites.yaml` marked DEPRECATED; no code reads it anymore
- **349 tests pass**

**Next:**
- Phase 2 — Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`)
- EZ current_account_gdp: investigate ECB SDW
- BEA data refresh (after 2026-06-26)

---

## 2026-06-22 — Eurostat fetcher + data gap resolution (EZ growth signals, KR CPI bridge)

**Done:**
- **Eurostat JSON stats API fetcher** (`fetch_eurostat_series()`) added to `loader.py`. Fixed `geo=EA` → correct codes (`EA21` for unemployment, `EA20` for industrial prod/retail sales). Fixed `s_adj` filter: `CA` (calendar-adjusted) is the correct value for PCH_SM industrial production — `SCA` returns 0 values for EA20.
- **`eurostat_params: Optional[dict]`** field added to `CountryBinding` (models.py).
- **Pass 1.5 (Eurostat)** added to `run_country()` in pipeline.py — sits between FRED and WB passes; applies `raw_scale` before transformation.
- **IMF `raw_scale` fix** in pipeline Pass 3 — was missing the `raw_scale` division; now consistent with FRED/WB/Eurostat passes.
- **EZ bindings updated** — 3 stale FRED growth series replaced with live Eurostat bindings:
  - `growth.industrial_prod` → Eurostat `sts_inpr_m?geo=EA20,nace_r2=B-D,s_adj=CA,unit=PCH_SM` (through 2026-04)
  - `growth.retail_sales` → Eurostat `sts_trtu_m?geo=EA20,nace_r2=G47,indic_bt=VOL_SLS,s_adj=CA,unit=PCH_SM` (through 2026-04)
  - `growth.unemployment` → Eurostat `une_rt_m?geo=EA21,s_adj=SA,unit=PC_ACT,sex=T,age=TOTAL` (through 2026-04)
- **KR IMF CPI bridge** (`PCPIPCH`) added to `kr_bindings.yaml` as `inflation.cpi_imf_annual` (annual, `raw_scale: 100`, `is_proxy: true`). Provides 2025 annual CPI = 2.1% while monthly OECD FRED feed is stale (discontinued Apr 2025).
- **Composites config updates**:
  - `min_signals_required`: 4 → 1 (Phase 2 multi-country support; confidence metric captures uncertainty)
  - `inflation.cpi_imf_annual` added to inflation_score indicator list (weight=0.30, quality=0.70; silently excluded for US/EZ)
- **Final composite quadrants**: EZ = Inflationary Boom 67% conf (3G+2I); KR = Expansion 25% conf (2G+1I annual bridge); US = Stagflation 40% conf (unchanged).
- **349 tests pass** (1 count assertion updated for new indicator).

**Next:**
- Phase 2 country 3: Japan (JP).
- EZ current_account_gdp: WB EMU has no `BN.CAB.XOKA.GD.ZS` and Eurostat BOP EA aggregate also returns 0 values. Investigate ECB SDW or IMF BOP.
- BEA refresh (after 2026-06-26) to clear 3 stale US signals.

---

## 2026-06-22 — Phase 2: Euro Area (EZ) + South Korea (KR) rollout

**Done:**
- **`config/countries/ez_bindings.yaml`**: 20 bindings (10 FRED + 10 WB). FRED: `CLVMNACSCAB1GQEA19` (GDP real Q), `CP0000EZ19M086NEST` (HICP M), `00XEFDEZ19M086NEST` (HICP core M), `ECBDFR` (ECB rate D), `IRLTLT01EZM156N` (10Y M), `RBXMBIS` (REER M), `ECBASSETSW` (ECB assets W), `EA19PRINTO01IXOBSAM`/`EA19SLRTTO01IXOBSAM`/`LRHUTTTTEZM156S` (growth — stale). WB EMU: demographics, external, capital, fiscal, R&D.
- **`config/countries/kr_bindings.yaml`**: 22 bindings (8 FRED + 10 WB + 4 IMF). FRED: `NGDPRSAXDCKRQ` (GDP real Q), `KORCPALTT01CTGYM` / `CPGRLE01KRM659N` (CPI headline+core, `raw_scale: 100`), `LRUNTTTTKRM156S` (unemployment M), `KORSLRTTO01GYSAM` (retail sales, `raw_scale: 100`), `KORPRINTO01IXOBM` (industrial prod M), `IRLTLT01KRM156N` (10Y M), `RBKRBIS` (REER M). IMF KOR: GDP$ (`NGDPD`), govt debt, budget/primary balance. WB KOR: same structural set.
- **`indicators/models.py`**: added `raw_scale: Optional[float]` field to `CountryBinding` — divides raw FRED value by this factor before transformation (converts already-YoY% percent-form series to decimal).
- **`indicators/loader.py`**: `_WB_COUNTRY_MAP` maps internal 2-letter codes → WB API codes (`EZ→EMU`, `KR→KOR`, etc.); `fetch_wb_series()` now uses this map for URL and cache path. `_IMF_COUNTRY_MAP` updated with `EZ` key.
- **`indicators/pipeline.py`**: refactored to multi-country architecture. `run_country()` helper runs passes 1–4 for any binding YAML (with `raw_scale` applied and `is_primary` flag for error handling). `run()` now runs US first, then loops over `config/countries/*.yaml` for Phase 2+ countries and runs composites for each.
- **`indicators/composites.py`**: bug fix — `_load_wide()` returned plain DataFrame on empty input even when `return_fill_age=True`, causing "too many values to unpack" crash for countries with no signals; now returns proper tuple.
- **Pipeline results**: EZ 19/20 signals live (1 empty: `external.current_account_gdp` — WB EMU doesn't publish this); KR 22/22 signals live. EZ composites: 545 snapshots, latest Inflation=+0.886 (HICP 3.1%), LowCov growth (stale series excluded). KR composites: 436 snapshots, latest Growth=+0.093, LowCov inflation (CPI stale >12m).
- **Global Overview now shows EZ + KR rows**: EZ — HICP 3.14%, ECB 2.25%, GDP 0.3%, unemployment 6.7% (2023 stale). KR — CPI 2.09%, GDP 3.78%, unemployment 2.8%, CA +5.33%, debt 52.3%.
- **349 tests pass** (no test regressions).

**Next:**
- Add EZ current account slot via alternate source (Eurostat or IMF BOP); or remove from EZ row.
- Phase 2 country 3: Japan (JP).
- BEA refresh (after 2026-06-26) to clear 3 stale US signals.

---

## 2026-06-22 — Global Overview table, Data Dashboard, sort/filter/reset

**Done:**
- **Global Overview page** (`/overview`): TE-style cross-country macro summary table — 9 columns (GDP $B, GDP Growth %, Interest Rate, Inflation, Jobless Rate, Govt Budget, Debt/GDP, Current Account, Population). Color-coded: `ov-cell-warn` (orange) for stress signals, `ov-cell-pos` (green) for positives, `ov-cell-high` (blue) for scale highlights. Date shown below each value as `yyyy-mm`. Only US row live; architecture supports future Phase 2 countries via `id LIKE '%.{concept}'` DuckDB query.
- **4 new series added** (`config/us_bindings.yaml`): `master.gdp_level_bn` (FRED:GDP, billions), `policy.fed_funds_target` (FRED:DFEDTARU, daily), `fiscal.budget_balance_gdp` (FRED:FYFSGDA188S, annual), `demo.population_total_mn` (WB:SP.POP.TOTL, annual). Total signals: 63.
- **Data Dashboard page** (`/data-dashboard`): operational feed health monitor. 63 signals grouped by force. Columns: Signal, Series ID chip, Latest Value (formatted by units), As Of (+ X days ago), Frequency, Source, Next Release (estimated), Status badges.
- **Status badges**: `✓ OK` (green), `STALE` (orange), `+Nd overdue` (amber), `LOW HIST` (blue), `PROXY`/`DERIVED`/`NO VINTAGE` (grey).
- **Sticky header**: `position: sticky; top: 0` on `thead tr th`; `box-shadow: inset 0 -2px 0 var(--border-color)` replaces `border-bottom` (which disappears under sticky).
- **Sort + Filter**: sortable columns (Signal, As Of, Frequency, Source, Next Release, Status); filter bar (search text, force, status, frequency dropdowns). Sorting switches to flat view; no sort = grouped by force.
- **Status sort key**: 0=stale → 1=overdue → 2=low_hist → 3=proxy → 4=derived → 5=OK.
- **↺ Reset Sort button**: clears sort state back to default grouped view.
- **`/overview` nav link** enabled (removed `disabled=True`; Docker was running stale image — required `docker compose build + up -d`).
- Tests updated: 3 hardcoded `== 59` counts → `== 63`; formula-route test replaced with overview-route test. **349 tests pass.**

**Next:**
- Phase 2 Eurozone rollout (`config/countries/eu_bindings.yaml`) — unblocked
- Run `python3 -m indicators.pipeline --latest` after 2026-06-26 (BEA Q1 2026 data; clears 3 stale signals)

---

## 2026-06-22 — Methodology audit, UI polish, formula clipboard, confidence fix

**Done:**
- **Confidence score fix**: rolling quadrant-consistency override (last 12 months) trivially hit 100% in a 3-year Stagflation regime. Removed the override entirely — `_regime_info_children` now always uses the raw DB `confidence` value (directional signal agreement fraction from the composites engine).
- **Formula / Methodology audit**: cross-referenced `methodology.py` prose against `composites.yaml`, `longterm_stress.yaml`, and actual computation code. Found and corrected: base_share fabricated values (Section 6), completely wrong debt stress component table (Section 9), and 4 minor description errors.
- **Debt stress formula catalog**: added `build_debt_stress_formula_catalog()` to `indicators/longterm_stress.py` — reads live from `longterm_stress.yaml`, same pattern as composites. Returns 5 formula cards (rolling Z quarterly, rolling Z annual→quarterly, staleness weight decay, aggregate stress score, band labels).
- **Clipboard copy on formula cards**: added `dcc.Clipboard` button to each card in `formulas.py`; `_clipboard_text()` formats card as plain text with raw LaTeX.
- **Formulas embedded in Methodology**: rewrote `methodology.py` — each accordion section ends with relevant inline formulas and the entire section is copyable via `dcc.Clipboard`; helper `_section_text()` generates clipboard-ready plain text including formula LaTeX. Removed the separate "ƒ Formula Reference" sub-tab and route.
- **Slider accent color**: replaced blue slider color with theme-aware amber/gold (`--slider-accent` CSS var — `#E8A317` Carbon, `#F4C842` Slate, `#4C6EF5` Dawn). Added to `THEME_CSS_VARS` in `themes.py`. Slider track tint and hover glow use `color-mix()`.
- **Slider thumb centering**: removed `top: 50%` / `transform: translate(-50%, -50%)` overrides on `.dash-slider-thumb` — Radix UI centers the thumb naturally within the track area; overriding these fought the mark-label space and caused misalignment.
- **Debt Stress nav icon**: changed from 📉 to ⚖️ (was too similar to Regime History).
- **Force Components title bar**: `html.Summary` color changed from `var(--muted-color)` to `var(--slider-accent)` (amber) for the main rollup row only; sub-headings (Growth / Inflation) unchanged.
- **Date block under PAST DATA warning**: added `date_block` div to `_regime_info_children()` quadrant column — shows "Month Year" (large, bold) + "X months/years ago" (small) for both current and historical selected dates. Uses month difference calculation with year/remainder formatting ≥24 months.
- **Settings icon size fix**: `⚙` (text glyph, renders small) → `⚙️` (emoji variation selector); icon span `fontSize: "1.1em"`; button `fontSize` raised to `"0.875rem"`; added `className="sidebar-nav-link"` so tooltip wires to same class.
- **Sidebar nav tooltips (minimized)**: nav links got unique `id` props; `_nl()` helper appends `dbc.Tooltip` to `_tooltips` list; Settings button gets its own tooltip. Overdue sync banner: `⚠` icon always visible, `html.Span(text, className="sidebar-text")` hidden when collapsed.

**Next:**
- Phase 2 Eurozone rollout (`config/countries/eu_bindings.yaml`) — unblocked
- Run `python3 -m indicators.pipeline --latest` after 2026-06-26 (BEA Q1 2026 data; clears 3 stale signals)

---

## 2026-06-22 — Sidebar slider polish + scatter map fix + rolling confidence

**Done:**
- **Scatter map blank bug fixed**: `update_scatter_chart` hovertemplate had invalid f-string `{sel_g:.2f if sel_g is not None else '—'}` (format spec can't contain conditional logic); pre-computed `_g_str`/`_i_str` strings before the f-string
- **Sidebar Z-Score + Disequilibrium sliders**: added `dcc.Slider` widgets directly to `_left_nav()` for both windows; `step=None` snaps to pre-computed marks only; wired to existing `zscore-window-store` / `diseq-window-store` via `ctx.triggered_id` dispatch
- **Slider persistence across refreshes**: changed both stores to `storage_type="local"` (browser localStorage); added `sync_zscore_slider` / `sync_diseq_slider` callbacks (`prevent_initial_call=False`) to restore slider positions from store on page load
- **Rolling confidence**: when a Z-score window is active, confidence now shows quadrant-consistency % over the last 12 months of rolling g/i scores instead of baseline directional-agreement; updates visibly when slider moves; `_RQ_MAP` promoted to module level
- **Slider visual polish** (Dash 4.x / Radix UI class names — NOT rc-slider):
  - Tooltip hidden: `.dash-slider-tooltip { display: none }`
  - Track background: `rgba(76,155,232,0.28)` — reads on Carbon/Slate/Dawn
  - Filled range: `#4C9BE8` solid blue
  - Thumb: 5×18px vertical pill (`dash-slider-thumb`); hover glow
  - Mark text: `var(--font-color)` inline style in `marks` dict (overrides Radix default dark ink)
- **Country selector**: `dbc.Select` in sidebar; US enabled, EZ/JP/GB disabled (Phase 2 hooks)
- **Settings modal**: separate Disequilibrium window radio added alongside Force Z radio

**Next:**
- Phase 2 Eurozone rollout per user direction
- BEA refresh after 2026-06-26: `python3 -m indicators.pipeline --latest`

---

## 2026-06-22 — Full pipeline rolling Z implementation + dashboard panels update

**Done:**
- **`indicators/transform.py`**: added `months_to_periods(months, frequency)` — converts month-count windows to native observation counts per frequency (M→months, Q→months÷3, A→months÷12, min 4)
- **`indicators/models.py`**: added 6 rolling Z-score fields to `Signal`: `zscore_12m`, `zscore_18m`, `zscore_24m`, `zscore_36m`, `zscore_48m`, `zscore_60m`
- **`indicators/normalize.py`**: `build_signals()` now pre-computes all 6 rolling Z-scores for each signal using `zscore_rolling()` and `months_to_periods()` with frequency-adjusted windows
- **`store/store.py`**: added 6 rolling Z columns to signals table schema + 9 rolling composite columns (`growth_score_36m/48m/60m`, `inflation_score_36m/48m/60m`, `disequilibrium_12m/18m/24m`) to composites table; `init_schema()` migrations; `update_rolling_composites()` batch-UPDATE function
- **`indicators/composites.py`**: `compute_composite_history()` gains `zscore_col` and `diseq_window` parameters; supports rolling Z for force scoring and rolling std for disequilibrium normalization
- **`indicators/pipeline.py`**: added Passes 5b–5d — runs composites engine 3× more with (36m/12m), (48m/18m), (60m/24m) window pairs; stores results via `update_rolling_composites()`; 558 composite rows updated per pass
- **`dashboard/charting_data.py`**: `load_composite_history()` now includes all 9 rolling columns in SELECT + accepts `country` parameter
- **`dashboard/charting.py`**:
  - Settings modal: removed 24mo force option (below guidance range), added **Disequilibrium Window** section (Full History / 24mo / 18mo★ / 12mo) with `diseq-window-radio` wired to `diseq-window-store`
  - `app.layout`: added `diseq-window-store` and `country-store` dcc.Stores
  - `_left_nav()`: added country dropdown (`dbc.Select`, id=`country-selector`) above nav groups; shows US (enabled), EZ/JP/GB (disabled, "soon")
  - New callbacks: `update_diseq_window`, `update_country`
  - `_FORCE_WINDOW_COL`/`_DISEQ_WINDOW_COL` maps for column routing
  - `update_regime_info`: uses DB pre-computed rolling columns instead of on-the-fly computation; accepts `diseq-window-store`, `country-store` inputs
  - `_regime_info_children()`: uses `rolling["diseq_score"]` when diseq window active
  - `update_regime_chart`: uses `g_col`/`i_col`/`d_col` rolling columns for all 7 subplots (quadrant derived from rolling scores when window active)
  - `update_scatter_chart`: uses rolling columns for context dots, trail, selected point; axis labels show window when active
- **Pipeline re-run**: 558 baseline composites + 3×558 rolling variants stored; all signals refreshed with 6 rolling Z columns; 349 tests pass; `:8502` HTTP 200

**Pipeline note:** 11 FRED series still returning API-key errors (breakeven, yields, spreads, crude oil) — these hit rate limits without cached parquets. Those are pre-existing; rolling Z for those series is NaN. The composite passes use zscore_36m/48m/60m from the cached signals that do have data.

**Next:** Phase 2 Eurozone rollout; BEA refresh after 2026-06-26; further :8502 UI polish per user direction

---

## 2026-06-21 — Rolling Z-score window, Momentum Z, and Methodology page

**Done:**
- **`indicators/normalize.py`**: added `zscore_rolling(series, window)` — rolling mean/std Z-score capped at ±4σ with `min_periods = window // 2`
- **`dashboard/charting_data.py`**: added `load_composite_signal_values(country)` — bulk-loads all growth + inflation composite signal transformed values from DuckDB for rolling Z computation
- **`dashboard/charting.py`**:
  - Imported `numpy`, `Path`, `load_composite_signal_values`, `dashboard.methodology`
  - Added `_compute_rolling_history(country, window)` — recomputes full composite score history with rolling Z-scores; applies nominal weights from composites.yaml; aligns quarterly series to monthly index via ffill ≤ 95 days
  - Added `_momentum_z_at(comp, idx, window=12)` — Z-score of the current MoM force-score change against the preceding 12 monthly changes
  - **Settings modal** (`dbc.Modal`, id=`settings-modal`) with 5 window options: Full History / 60mo / 48mo (recommended) / 36mo / 24mo; wired to `zscore-window-store` dcc.Store
  - **⚙ Settings** button added at the bottom of the left sidebar (`id="settings-btn"`)
  - **`_page_methodology()`** + `/methodology` route added to `_PAGE_MAP`
  - **📖 Methodology** nav link added to the Data section in the left sidebar
  - `update_regime_info` callback: added `Input("zscore-window-store")` input; when window > 0, recomputes growth/inflation scores from rolling Z history, derives rolling quadrant label, and computes rolling MoM deltas; always computes Momentum Z from stored composite history
  - `_regime_info_children()`: added `rolling` dict parameter; Force Z-Score group header shows "rolling Nmo" when window active; new **Momentum Z (12mo)** group shows Z-score of recent MoM changes; quadrant label derived from rolling scores when active
- **`dashboard/methodology.py`** (new): comprehensive 12-section methodology page covering overview, data sources, signal transformation, force Z-score (both modes), momentum (both metrics), dynamic weighting, composite construction, regime classification, debt stress, data quality flags, country coverage, and deferred items
- 349 tests pass; `:8502` rebuilt and returns HTTP 200; `/methodology` and settings modal confirmed in Dash layout JSON

**Next:** Phase 2 Eurozone rollout; BEA refresh after 2026-06-26; further :8502 UI polish per user direction

---

## 2026-06-21 — Code-backed Formula Reference

- Added a Formula Reference page at `/formulas` under the Dash Data navigation
- The page renders live equations for component/force Z-scores, configured and effective weights, momentum tilt and breadth, confidence, structural disequilibrium, and observation-age decay
- Formula cards read active values directly from the composite calculation modules and `config/composites.yaml`, including momentum alpha/bounds, neutral-Z threshold, decay half-life/hard drop, frequency carry caps, and coverage minimums
- Each card identifies its authoritative calculation function so formulas and displayed settings remain traceable as the methodology evolves
- Rebuilt :8502, verified `/formulas` in headless Chromium, and passed all 349 tests in Docker

---

## 2026-06-21 — Dynamic Growth/Inflation force weighting

- Replaced legacy fixed force weights with the documented `base_share × importance × quality_factor` model; all 17 importance defaults match `docs/feedback/force-momentum weighting guidance.md` and remain editable in `config/composites.yaml`
- Added point-in-time momentum agreement tilts (1.5× agreement, 0.5× conflict by default) and exponential observation-age decay with a configurable three-month half-life
- Preserved frequency-specific carry caps and provider-stale/low-history exclusions; each monthly snapshot now stores a JSON audit of config weight, momentum multiplier, age, decay, effective weight, and normalized contribution for every component
- Rebuilt Force Component Inputs to mirror Debt Stress: Importance, Config Wt, Eff Wt, Last Data, Z-score, Momentum, and explicit ACTIVE/BOOSTED/CONFLICT/DECAYED/BLANK tags; disclosure state remains persistent across dates
- Migrated and regenerated 558 US composite snapshots; latest remains Stagflation (Growth −0.079, Inflation +0.399, Confidence 36%)
- Updated methodology/help text and both dashboard component tables; 347 tests pass on host and Docker, :8501/:8502 rebuilt, and the live :8502 table passed Chromium interaction/content checks

---

## 2026-06-21 — Regime History synchronized hover and disclosure state

- Synchronized hover across all seven Regime History subplots by mirroring the hovered date through Plotly's client-side hover API
- Added a full-height dashed vertical guide and placed each value label on its respective graph with consistent black styling
- Preserved the Force Component Inputs disclosure state while stepping through dates; an opened table now remains open as the snapshot changes
- Raised the minimum Plotly version to 5.21 for cross-subplot hover support and added callback/layout/state regressions
- Verified the rendered interactions in headless Chromium; 339 repository tests pass and rebuilt :8502 returns HTTP 200

---

## 2026-06-21 — Regime History graph point selection

- Wired all five Regime History subplots through Dash's native graph click event; clicking a past point now selects the corresponding composite snapshot
- The shared step index updates the sticky summary/component data and every graph's selected-point marker together
- Date-based selection works across traces with different point counts and resolves sparse series to the nearest available composite date
- Added exact-date, nearest-date/timezone, and invalid-click regressions; 335 tests pass on host and Docker
- Rebuilt :8502; Regime History returns HTTP 200 and the click callback is registered without server errors

---

## 2026-06-21 — Routed Regime History step controls

- Replaced page-specific Prev/Now/Next callback inputs with shared structured button IDs, so the callback remains active when only the routed Regime History page is mounted
- Prev now selects the immediately older data point; Next moves one point toward the present; Now returns to the latest point
- The shared `regime-step-index` continues to drive the sticky summary/component table and all five graph rows together
- Added routed-layout and step-transition regressions; 329 tests pass on host and Docker
- Rebuilt :8502; Regime History rendered all controls in a headless-browser smoke test with HTTP 200 and no callback errors

---

## 2026-06-21 — Post-UI-restructure code review remediation

- Fixed the Data Explorer initial-load callback error caused by passing Plotly's `title` layout argument twice
- Made Regime Map panels point-in-time in both Dash and Streamlit: historical stepping now controls What Changed, Conflicts, lens drill-downs, quality flags, and sparkline windows
- Made the Streamlit Debt Stress tab honor the selected regime date instead of always showing the latest snapshot
- Corrected change-feed ranking so the latest reading must be recent but its comparison reading may fall outside the 120-day display window, preserving quarterly-series deltas
- Updated the Regime History callback tests to the routed-page signature and added as-of/change-feed regressions
- 324 tests pass; rebuilt :8501/:8502 containers return HTTP 200; all six :8502 routes completed headless-browser smoke tests with no callback errors
- Next: continue Phase 1I UI consolidation, then Phase 2 Eurozone rollout
- Blockers: BEA refresh remains pending until after 2026-06-26

---

## 2026-06-21 — :8502 Dash UI restructuring + Regime Map panels

**Done:**
- **Left-sidebar navigation**: replaced tabbed layout with persistent vertical pill nav. Two groups — *Data* (Chart Overlay, Data Explorer) and *Indicators* (Yield Curve, Regime Map, Regime History, Debt Stress). Series selector moved inside Chart Overlay.
- **Browser back button**: `dcc.Location(id="url", refresh=False)` + `dbc.NavLink` hrefs push to browser history; `page-trigger` store guarantees downstream callbacks fire after DOM is updated.
- **Regime Map scatter zoom**: quadrant backgrounds widened to ±100 (always fill viewport); initial axis range now computed from actual data with 15% buffer; `uirevision="scatter-map"` preserves user zoom across step changes.
- **Below-map panels on :8502 Regime Map page** (ported from :8501):
  - *What Changed* — top-8 Z-score movers (leading/coincident only), Δ vs prior reading
  - *Cross-Signal Conflicts* — leading vs lagging/coincident direction gap > 40%; PMI vs Payrolls check
  - *Geopolitical-Risk Overlay* — static deferred placeholder (WGI G-03)
  - *Signal Drill-Downs* — collapsible `dbc.Accordion` for all 10 lens groups (A–I + Master); each panel shows indicator table with value, direction, percentile badge, Z-score, quality flags, causal-linkage tooltip
  - *Data-Quality Log* — collapsed by default; `dash_table.DataTable` of stale/proxy/low-history/no-vintage signals
- **Fixed chart height clipping bug**: removed hardcoded `height=` from regime history and debt stress figures; set `responsive=True` on `dcc.Graph` components with `calc(100vh - Xpx)` CSS heights; fixed double `margin=` keyword argument error in `update_layout` calls.
- **Lens table rendering fix**: replaced `dcc.Markdown(dangerously_allow_html=True)` (unreliable for complex HTML in Dash 4.2) with proper `html.Table` / `html.Tr` / `html.Td` Dash components; accordion `title` props changed to plain strings.
- `dashboard/charting_data.py`: added `load_latest_signals`, `load_change_feed`, `load_all_signal_histories`.
- All services rebuild cleanly; :8502 HTTP 200; no callback errors in logs.

**Next session:** Continue :8502 UI improvements. Consider migrating remaining :8501 content (methodology guide, footnotes). Phase 2 Eurozone rollout remains queued.

**Blockers:** BEA refresh still pending (run `python3 -m indicators.pipeline --latest` after 2026-06-26).

---

## 2026-06-20 — Post-Phase-1H code review remediation

- Fixed Regime History carry-age badges: `stale_signals` point-in-time metadata now marks forward-filled components as `STALE · Nm` even when the source observation's ingestion-time stale flag is false
- Made the Lightweight Charts frontend runtime self-contained: the pinned v4.1.3 asset is vendored into the nginx image at build time and protected by a SHA-256 check
- Hardened composite PCA against wholly missing columns, non-finite inputs, undersized matrices, and zero-variance datasets; the dashboard now renders a controlled unavailable state instead of raising
- Added regression tests; 321 host tests pass and rebuilt charting/API/frontend services return HTTP 200
- Next: Phase 2 Eurozone rollout; refresh BEA data after 2026-06-26
- Blockers: `FRED_API_KEY` is not available in the host shell, so no live ingestion refresh was run

---

## 2026-06-20 — TradingView Lightweight Charts system (ADR-007 Option B)

Built the full TradingView system. All 319 tests pass; both Docker services healthy.

**Backend** (`dashboard/charting_lc/main.py`): FastAPI on :8004 (Docker: :8000 internal). Five endpoints: `/catalog`, `/series/{signal_id}`, `/composite-history`, `/signals/snapshot`, `/yield-curve/{date}`. CORS enabled; nginx at :8503 reverse-proxies `/api/` so the browser uses one port.

**Frontend** (`dashboard/charting_lc/frontend/index.html`): Single-page app with four tabs:
- 📈 Charts: TradingView Lightweight Charts multi-pane chart; 50-series sidebar grouped by force; 1Y/3Y/5Y/10Y/MAX horizon; Value/Z-Score toggle; panes time-synchronized; default series: GDP / Core PCE / Fed Funds
- 📊 Macro Table: all 59 signals; sortable columns (Z-score bar, direction, 1m/3m/12m deltas, momentum percentile); force filter pills; search box
- 🔄 Regime: 4-pane chart (Growth Score / Growth Momentum / Inflation Score / Inflation Momentum); ⏮ ‹ › ⏭ step controls + Play/Pause + arrow-key navigation; live info strip showing quadrant/scores/confidence per step
- 📉 Yield Curve: bar chart + table for any selected date

**Docker**: `lc_api` (Python/uvicorn, port 8004→8000) + `lc_frontend` (nginx:alpine, port 8503→80) in docker-compose.yml.

Next: Phase 2 Eurozone rollout (unblocked; see session-checklist.md). BEA refresh after 2026-06-26.

---

## 2026-06-19 — Session close: TradingView system spec reviewed; docs and memory updated

All 319 tests pass. Reviewed ADR-007 Option B (FastAPI :8000 + TradingView Lightweight Charts :8503) and confirmed the skeleton at `dashboard/charting_lc/main.py`. Next session will implement the full TradingView system per the ADR.

Next: Build TradingView Lightweight Charts system (Option B, ADR-007). Backend: `api/main.py` FastAPI with DuckDB endpoints. Frontend: nginx-served HTML/JS with Lightweight Charts v4 at :8503. Docker: two new services in docker-compose.yml.

---

## 2026-06-19 — D1, B1, A2/I2 (momentum percentile, period audit, composite PCA)

**D1** (momentum percentile): `momentum_percentile DOUBLE` added to `Signal` model and DB. In `build_signals()`, `_percentile_series()` is applied to the valid `change_3m` slice — rank of current 3-month change within its own full history. Aligns momentum comparisons across high/low-volatility series. 5 new tests.

**B1** (calendar-adjusted N audit): All 5 frequencies audited. `_YOY_PERIODS` and `_MOMENTUM_PERIODS` constants are correct: D=252/21/63/252, W=52/4/13/52, M=12/1/3/12, Q=4/1/1/4, A=1/1/1/1. 14 new explicit tests covering all frequency × period combinations including weekly and annual YoY.

**A2/I2** (composite correlation + PCA): New "📊 Composite Analysis" subtab added to the Data Explorer right panel. `load_composite_zscore_matrix()` + `compute_pca()` added to `explorer_data.py`. Shows: (1) 17×17 Pearson correlation heatmap of composite signal Z-scores with a growth/inflation divider line; (2) Scree plot + PC1/PC2 loadings heatmap. 10 new tests. Container rebuilt.

Pipeline re-run: 59 signals updated with `momentum_percentile`. 319/319 tests pass.
Next: Phase 2 Eurozone rollout (user sign-off after BEA refresh on 2026-06-26).

## 2026-06-19 — Regime History tab UX improvements (momentum display, table rollup, chart subplots)

Three improvements to the Dash :8502 Regime History tab:

1. **Momentum in summary box**: Dedicated `_mom_block` components for Growth Momentum and Inflation Momentum now appear as separate stat blocks (e.g. "4/9") after the force scores, separated by a vertical divider. Force score subtitles simplified to "N/N signals active" only.

2. **Momentum charts**: `update_regime_chart` now uses 5 subplot rows (was 3). New layout: Growth Score → Growth Momentum (%) → Inflation Score → Inflation Momentum (%) → Quadrant. Momentum rows are 15% height; force rows 25%; quadrant 20%. Both momentum rows use 0–100% Y-axis with 50% dotted reference line. Step-selection markers added for all 5 rows. Chart container height raised to 85vh.

3. **Signal table rollup**: Each force section now wrapped in `html.Details`/`html.Summary` for independent collapse/expand (open by default). Each summary shows "GROWTH/INFLATION FORCE INPUTS · N/M active" — same information as before but now clickable headers.

   DB change: `growth_momentum DOUBLE` + `inflation_momentum DOUBLE` columns added to composites table (schema migration + pipeline re-run). 558 snapshots re-generated. 287 tests pass (7 new tests).

Next: A2/I2 correlation matrix + PCA analysis, or D1 momentum percentile-rank.

## 2026-06-19 — Feedback tracker remediation: L4 (regime composite stale-lag badges)

L4 (dashboard stale-lag badges): `load_composite_history()` in `charting_data.py` now includes `stale_signals` in the SELECT. `_regime_info_children()` gains a `stale_dict: dict[str, int]` parameter. `update_regime_info` callback parses the `stale_signals` string (reusing `_parse_stress_components()`) and passes the dict through. In the component table, STALE badges now render as "STALE · Nm" (e.g. "STALE · 2m") for signals with known fill-months — matching the J5 debt stress pattern.

5 new tests (3 unit, 2 integration); 280/280 pass. All L1–L4 staleness items for regime composite are now done. L5 deferred.
Next: A2/I2 correlation + PCA analysis in Data Explorer, or D1 (percentile-rank momentum).

## 2026-06-19 — Feedback tracker remediation: L2, L3 (regime composite staleness)

L2 (per-frequency carry cap): `per_frequency_ffill_limit` added to composites.yaml (M:3, Q:9, A:15, D:1); `_load_wide()` accepts `per_signal_limits: dict[str, int]` for per-column ffill; pipeline Pass 5 builds freq_map from verified bindings and passes it to `compute_composite_history()`. Monthly signals are now capped at 3 months fill (was 13 uniformly).

L3 (stale signal tracking): `CompositeSnapshot.stale_signals: Optional[str]` field added; DB schema updated with migration; snapshot loop populates `"signal_id:months,..."` string from fill_age data. Verified: 2026-06-19 shows 13 signals with 1-2 months fill — correct for mid-month before all releases land.

6 new tests; 275/275 pass. Pipeline re-run: 558 composite snapshots, 59/59 signals.
Next: L4 (dashboard stale-lag badges in Regime History), then A2/I2 PCA analysis.

---

## 2026-06-19 — Feedback tracker remediation: C1, E1, F1/L1, G1, H1, H2

Implemented six items from `docs/feedback_tracker.md` — all 269 tests pass:

- **H1**: Both TIPS breakeven weights halved to 0.5 in `composites.yaml`; combined contribution stays 1.0
- **G1**: Labour-market signals (payrolls, unemployment, job_openings, labor_force_part) → 0.75 weight; capacity_util → 1.05; output/demand stays 1.00
- **C1**: `_zscore_series()` now caps Z-scores at ±4σ; prevents COVID/GFC spikes from distorting all other historical Z-scores
- **E1**: `_direction(change_3m, series_std)` uses `series_std × 10%` as the significance threshold; `series_std` computed in `build_signals()` and passed through; eliminates false directional calls on low-volatility flat series
- **F1/L1**: `_compute_fill_age()` tracks months since last observation; in `compute_composite_history()` each signal's effective weight is `base_weight × decay_factor^fill_age`; config-gated via `staleness_decay.enabled/decay_factor` in `composites.yaml` (default: enabled, factor=0.9)
- **H2**: `CountryBinding.pre_smooth_window` optional field; `pre_smooth_window: 7` in crude_oil binding; Pass 1 of pipeline applies 7-day rolling mean to raw prices before YoY transformation

20 new tests added across `test_normalize.py` and `test_composites.py`.
Tracker updated: H1, H2, G1, C1, E1, F1, L1 all marked ✅ Done.
Next: pipeline re-run to regenerate signals/composites with new weights + decay; Phase 2 Eurozone rollout; L2 per-frequency carry cap.

---

## 2026-06-19 — Post-Phase-1F code review remediation

- Reviewed all changes from the Long-Term Debt Stress implementation, staleness work, Debt Stress UI, Regime History component table, and methodology-feedback documentation
- Corrected `BCNSDODNS` from millions to billions before dividing by GDP; latest corporate debt/GDP raw value is now 0.454 rather than 454.2
- Made staleness point-in-time: historical snapshots now use only source dates available at that quarter, and forward-filled synthetic dates no longer masquerade as observations
- Replaced the misleading linear “halflife” with true exponential half-life decay; repaired corporate carry-forward and the extrapolation trigger at the carry boundary
- Fixed both historical UIs: Regime History loads component values as of the selected month, and the Streamlit HUD loads Debt Stress as of the selected regime date
- Added derived-source dates and consistent effective-weight calculations to the Debt Stress table
- Hardened storage against future rows and duplicate provisional quarters; added config validation, country-scope guards, safe list defaults, and explicit schema migrations
- Removed the empty misspelled `docs/macro_methodoloy.md`; retained the correctly named feedback document
- Full suite: 249 passed; live pipeline: 59/59 signals, 185 debt-stress snapshots, latest stress +0.488 with 5/7 components and 72.7% retained weight; no future rows
- Next: Phase 2 Eurozone rollout; debt-stress configuration must be country-specific before enabling it outside the US
- Blockers: real-time publication/vintage metadata remains Phase 3 work; historical stress output is latest-revised, not a real-time backtest

---

## 2026-06-19 — Session 17: Debt Stress tab — full-width component detail table

- `dashboard/charting_data.py`: added `_COMPONENT_SIGNAL_MAP` + `load_debt_stress_component_dates()` — queries signals table for last `as_of` per underlying signal (min of sub-components for derived series)
- `dashboard/charting.py`: Debt Stress tab layout changed from 3/9 split to stacked (full-width info card → full-width chart); `_build_debt_stress_info` rewritten with score summary strip + 7-column component table; new helpers `_fmt_period`, `_carry_expires`; callback now passes `component_dates` dict; old narrow bar list replaced
- Component table columns: Component · Freq · Config Wt · Eff Wt (post-decay, coloured amber/red when reduced/zero) · Last Data (YYYY-Qn or YYYY) · Z-Score (mini bar) · Status/Detail
- `BLANK` status rows explain carry expiry in full: "carry expired · last data: 2024 · carry cap 4q → covered to 2025-Q4 · extrapolation disabled · last known value: −4.08"
- 239/239 tests pass; committed + pushed
- Next: Phase 2 Eurozone rollout; pipeline re-run after June 26 BEA release
- Blockers: None

---

## 2026-06-19 — Session 16: Long-Term Debt Stress — Staleness Handling (Gaps 1–3)

- **Gap 1 (weight decay)**: Components with excess staleness lag decay linearly toward zero weight; drops below `stale_min_weight_fraction` are excluded from the score. Parameters in `config/longterm_stress.yaml` under `staleness:`.
- **Gap 2 (carry limit + extrapolation)**: All builder functions and `_rolling_z_annual_then_ffill` now take `ffill_limit=max_carry_q` from config; `_extrapolate_z_score` adds `rolling_mean` / `linear_trend` extrapolation behind `extrapolation.enabled: false` config gate.
- **Gap 3 (structured stale strings)**: `stale_components` and new `extrapolated_components` fields store `"cid:lag_q"` strings; dashboards parse and display amber (stale Nq) and blue (extrap Nq) badges; backward-compatible parser handles old plain-`"cid"` format.
- `indicators/models.py`, `store/store.py`: `extrapolated_components` column added with migration guard.
- 14 new tests; bug fix in `test_extrapolated_components_populated_when_enabled` — dsr used `periods=80` (ends 2019), which meant q_index never reached recent stale quarters; fixed to `pd.Timestamp.today()`.
- 239/239 tests pass; committed `2f0a97f`; pushed.
- Next: rebuild containers to pick up staleness changes; pipeline re-run after June 26 BEA release; Phase 2 Eurozone rollout.
- Blockers: None

---

## 2026-06-19 — Session 15: Long-Term Debt Stress Indicator (UI layer)

- Fixed invalid Z-scores in prior session's pipeline output: root causes were `ffill(limit=1)` not covering BIS publication lag + `resample("QE").last()` not extending past last data point; added `_extend_to_current_quarter()` helper; all 7/7 components now active at 2026-Q1 (stress=+0.447, retained_weight=100%); stale component tracking introduced (`stale_components` field)
- `dashboard/charting_data.py`: added `load_debt_stress_history(country, start_date, end_date)` query helper
- `dashboard/app.py`: added `load_debt_stress_latest()` cached loader; added `_render_hud_debt_stress()` HTML helper; added `debt_stress` parameter to `render_hud()`; HUD now shows Debt Stress gauge after Disequilibrium with score, band label (color-coded), component count (N/7), and stale badge
- `dashboard/charting.py`: added "📉 Debt Stress" tab with 2-row layout (left info card + right chart); info card shows score, band, per-component Z-score bars with stale badges; chart shows composite score time series (row 1, band shading) + all 7 component Z-scores as lines (row 2, shown as stress-direction contribution i.e. negative-direction components are negated); `load_debt_stress_history` imported; two callbacks wired
- 225/225 tests pass; both dashboards unchanged for existing tabs
- Next: Phase 2 Eurozone rollout (pending user sign-off on US data); pipeline re-run after June 26 BEA release to clear 3 stale signals; consider adding band-change alerts to change feed
- Blockers: None

---

## 2026-06-19 — Session 14: Long-Term Debt Stress Indicator (computation layer)

- Implemented the Long-Term Debt Stress Indicator per `docs/longterm_stress_indicator.md`
- `config/longterm_stress.yaml`: all tunable parameters (weights, rolling windows, coverage threshold, interpretation bands) explicitly annotated with `# TUNABLE` comments and rationale; no tunable values buried in code
- `indicators/models.py`: added `DebtStressSnapshot` Pydantic model with per-component Z-scores and raw values for full auditability
- `indicators/longterm_stress.py`: computation module; load_longterm_stress_config, rolling Z-score with shift(1) look-ahead protection at quarterly (window=40) and annual (window=10) frequency, weight renormalisation under missing components, low_coverage flag when retained_weight < 0.60
- `store/store.py`: `debt_stress_snapshots` table + `upsert_debt_stress` + `query_debt_stress_history`; wired into `init_schema`
- `indicators/pipeline.py` Pass 6: runs stress computation, upserts, prints latest reading
- `tests/test_longterm_stress.py`: 19 tests covering unit conversion (FYOINT millions→billions), look-ahead prevention (shift=1 vs shift=0), sign convention (negative-direction components lower score), missing-component renormalisation, coverage threshold, no future-dated snapshots, band labels, config-driven weight change, model defaults, and config structural integrity
- Pipeline verified: 222/222 tests pass; 185 debt stress snapshots stored; latest (2026-03-31): stress=null, 5/7 components active, retained_weight=55% (< 60% threshold) → low_coverage=True (correct — TDSP and one other stale at current date)
- Key design: all tunable parameters in YAML with rationale; no hardcoded values; component Z-scores + raw values stored for dashboard decomposition later
- Next: Phase 2 Eurozone rollout; pipeline re-run after June 26 BEA release; dashboard panel for debt stress (after historical output review)
- Blockers: None

---

## 2026-06-19 — Repository-wide code review remediation

- Fixed all nine findings from the review of changes since the prior repository audit
- Prevented future-dated composite snapshots and made current-month upserts replace the provisional row atomically
- Activated the bound PPI inflation input; excluded stale and low-history signals from composite scoring; aligned disequilibrium with standardized declared-equilibrium distances
- Removed the duplicate Dash callback for the Explorer Latest card; corrected weekly bank-loan gap detection and the swapped BIS/World Bank REER catalog entries
- Converted `chart_series.yaml` to valid YAML and replaced the regex/duplicate catalog parsers with one canonical loader
- Rewrote the Long-Term Debt Stress Indicator specification to correct units, frequencies, component signs, debt-service definitions, and weights
- Added regression coverage and registered the integration marker; full suite passes: 203 tests, with only Dash's upstream DataTable deprecation warnings
- Live pipeline verified: 59/59 signals, 558 snapshots, latest date 2026-06-19, 8/8 inflation inputs, no future composite rows; Growth=−0.048, Inflation=+0.428, Confidence=48%, Disequilibrium=0.702
- Next: implement the corrected Long-Term Debt Stress Indicator specification
- Blockers: None

---

## 2026-06-19 — Session 13: Regime stepper (:8501) + Sync banner (:8502)

- Added `← Prev` / `Next →` stepper to Streamlit :8501 — controls both the Macro Regime HUD and the 4-quadrant scatter map; when stepping back, the HUD shows a gold `⚠ Jun 2024` warning in the bottom-right of the regime box; scatter trail and selected marker shift to the chosen date; step clamped to available history and persisted via `st.session_state["regime_step"]`
- Added sync banner to Dash :8502 header (inline with title): shows "Next sync: Jun 26, 2026 · BEA Q1 2026 current account / NIIP (7d)" today; auto-flips to gold "⚠ Update data now" after the release date passes; `_UPCOMING_RELEASES` list at top of `charting.py` should be updated each session
- Rebuilt Docker containers (`docker compose build && up -d`) to pick up code changes; 195/195 tests passing
- User added `docs/longterm_stress_indicator.md` — spec for a new Long-Term Debt Stress Gauge feature (two-layer framework: Short-Term Health + Long-Term Stress Index as complementary composites); to be implemented in next session
- Next: implement Long-Term Stress Indicator per `docs/longterm_stress_indicator.md`; also re-run `python3 -m indicators.pipeline --latest` after June 26 (BEA release) to clear 3 stale signals

---

## 2026-06-19 — Session 12: Data docs + Regime History navigation

- Added `docs/data_release_calendar.md` — full table of all 59 signals with period type, period start/end, release lag by provider, latest obs in DB, and staleness status; explains FRED period-start date convention (2026-01-01 = Q1 2026) and why Trading Economics can show Q1 2026 data that we also have
- Added `docs/methodology.md` — comprehensive methodology document covering signal pipeline (transform → Z-score → percentile → momentum → direction → ffill), Growth Score, Inflation Score, Regime Quadrant, Confidence, Disequilibrium; includes formulas, code references, indicator rationale table, and known-limitations section aimed at reviewer feedback
- Ran pipeline to check for BEA Q1 2026 data (current account, NIIP, debt service); still at Q4 2025 — BEA release expected June 26; re-run after that date
- Added ← / → nav buttons to Regime History tab: step through monthly composite snapshots; Macro Regime info box (quadrant badge + Growth/Inflation/Confidence/Disequilibrium scores) updates on each step; `⚠ Past Data` warning appears bottom-right for any non-current selection; chart gets dashed vline + highlighted circle marker at selected date
- Fixed remaining `themes['midnight']` fallback in clientside callback (was dead code but incorrect)
- 195/195 tests passing (+8 new tests for nav feature and composite query columns)
- Next: Phase 2 Eurozone rollout; BEA re-run on June 26

---

## 2026-06-19 — Session 11: Theme switcher + staleness fix

- Added multi-theme support to Dash app (:8502): Carbon (dark, default), Slate (dark), Dawn (light) — `dashboard/themes.py` is single source of truth; CSS custom properties + clientside callback drive all styling changes without page reloads
- Created `dashboard/assets/theme.css` for static CSS defaults and fixed `dcc.Checklist` label colour inheritance bug (labels need explicit `#series-selector-body label { color: var(--series-label-color) !important; }`)
- Fixed staleness false-positive bug in `indicators/normalize.py`: `_is_stale()` was comparing `today - period_start_date` against thresholds that assumed release dates, not period starts; raised M: 50→90d, Q: 120→200d, A: 400→600d
- After threshold fix and pipeline re-run: 53/59 signals correctly not-stale; 6 remain legitimately stale (TFP/R&D: 2-3yr structural lag; household debt BIS + BEA current account/NIIP/debt-service: 1-3 quarter structural lag)
- 191/191 tests passing; Midnight theme removed; Carbon is now default
- Next: Phase 2 — Eurozone rollout (user data quality sign-off satisfied)

---

## 2026-06-19 — Session 10: Phase 1E — Data Explorer + session close

- Shipped Phase 1E end-to-end: Data Explorer tab in the Dash app (:8502) with signal browser (59 signals, filterable by force/flags), Time Series tab (dual raw+Z-score chart, equilibrium reference, stale markers, ±2/3σ bands, stat cards, reference spot-check vs provider), Observations tab (full paginated table, outlier/stale row highlighting, CSV download), Quality & Gaps tab (metadata, flag badges, gap detection), Raw vs Processed tab (parquet cache vs DB delta to verify transforms)
- Decided: Data Explorer lives as a new tab in the existing Dash app (not a separate page) — lowest friction, data helpers already built
- 31 new tests; total suite 187/187 passing; Docker :8502 HTTP 200 confirmed
- User will use Explorer to verify data accuracy before committing to Phase 2 country rollout
- Next: Phase 2 — Eurozone rollout (once user is satisfied with US data quality)

---

## 2026-06-19 — Session 9: Phase 1D — Dash charting view + session close

- Shipped Phase 1D end-to-end: Plotly Dash app (`dashboard/charting.py`) on `:8502` with series selector sidebar (50 series, 9 lens groups), Chart Overlay tab (multi-pane, shared X-axis, independent Y-axes, `hovermode="x unified"`), Yield Curve tab (full term structure 3M→30Y + historical 10Y-2Y spread bar), Regime History tab (growth/inflation scores + quadrant colour bands)
- Created `config/chart_series.yaml` (series catalog), `dashboard/charting_data.py` (DuckDB query helpers + FRED parquet cache reads), `dashboard/charting_lc/` (Option B TradingView skeleton, deferred per ADR-007)
- Pre-fetched DGS3MO, DGS1, DGS5, DGS30 into raw_cache for complete yield curve term structure
- Added `charting` service to `docker-compose.yml`; Docker acceptance gate passed: `:8502` returns HTTP 200
- 25 new tests; total suite 156/156 passing
- Next: Data explorer — verify raw signal data accuracy before Phase 2 country rollout

---

## 2026-06-18 — Session 8: Dashboard rendering fix + session close

- Fixed critical rendering bug: Streamlit 1.39+ silently ignores `unsafe_allow_html=True` in `st.markdown()`; replaced all 10 affected call sites with `st.html()` — HUD, What Changed rows, conflict panel, GPR overlay, lens "About" boxes, signal tables, page header, and footer now render correctly
- Confirmed Docker dashboard healthy after rebuild on port :8501
- All project docs, CLAUDE.md, session-checklist, ADR-007, and memory updated
- 131/131 tests passing throughout
- Next: Phase 1D — Plotly Dash charting view (`:8502`)

---

## 2026-06-18 — Session 7: Dashboard tweaks + Phase 1D planning

- Fixed HUD "Momentum Vectors" mislabeling: renamed to **Force Scores** (current composite Z-score level that determines the regime quadrant) + added separate **Momentum** metric (month-over-month Δ in composite score — true rate of change)
- Added **📚 Methodology Guide** to sidebar: collapsible reference covering Z-score, percentile, Growth/Inflation Score composition (with signal tables and weights), Confidence, Disequilibrium, lead/lag classification, quality badges, and Dalio's four seasons
- Added **"About this lens"** description line inside each accordion — explains what each lens measures, which signals feed the composites, and weighting rationale
- Created **ADR-007** (`docs/decisions/ADR-007-charting-architecture.md`): documents decision to build Phase 1D as Plotly Dash on :8502; Option B (FastAPI + TradingView Lightweight Charts) deferred with skeleton committed
- Updated CLAUDE.md, session-checklist, project docs with Phase 1D plan
- 131/131 tests still passing; dashboard container confirmed healthy
- Next: Phase 1D — Plotly Dash charting view

---

## 2026-06-18 — Session 6: Phase 1C — Streamlit Dashboard

- Wired Telegram `Stop` hook into `~/.claude/settings.json` (bot already authorized; Telegram was the existing notification mechanism, not Signal)
- Shipped Phase 1C end-to-end: full `dashboard/app.py` rewrite (~380 lines) with HUD, 4-quadrant Plotly scatter + 12-month trail, What Changed feed, Cross-Signal Conflict panel, Geopolitical-Risk Overlay placeholder (WGI deferred per G-03), accordion drill-downs for all 10 lens groups, per-signal sparklines (SVG), percentile color badges, quality badges (proxy/stale/no-vintage/low-hist), causal linkage tooltips (via HTML `title` attribute), data-quality log
- Added `tests/test_dashboard.py`: 39 tests (35 unit + 4 integration) — all passing; total suite 131 tests
- Docker acceptance gate passed: `docker compose up dashboard` serves on :8501; health endpoint returns HTML
- Current regime: Stagflation — Growth=−0.05 / Inflation=+0.31 / Confidence=45%
- Next: Phase 2 — Eurozone rollout (first non-US country binding)

---

## 2026-06-18 — Session 5: Phase 1B — Composites Engine

- Merged `codex/code-review-fixes` → `main`; all 8 code review findings closed, 79 tests passing
- Shipped Phase 1B end-to-end: `indicators/composites.py` (Growth Score, Inflation Score, Regime Quadrant + Confidence, Disequilibrium Score); `CompositeSnapshot` Pydantic model; `composites` DuckDB table with idempotent upserts; Pass 5 in `pipeline.py`; 13 new tests (91 total passing)
- Pipeline verified: 59/59 signals OK, 558 monthly composite snapshots stored (full US history)
- Key finding: 2022 engine labels are "Inflationary Boom" (not "Stagflation" as spec assumed) — employment Z-scores stayed strongly positive all year; Stagflation label correctly emerges from Mar 2023 when growth Z-scores turn negative. Spec acceptance gate updated to reflect this.
- Current regime (Jun 2026): Stagflation — Growth=−0.05 / Inflation=+0.31 / Confidence=45% / Diseq=0.82
- Next: Phase 1C — Streamlit dashboard (4-quadrant scatter, HUD, accordion lenses A–I)

---

## 2026-06-18 — Repository-wide code review remediation

- Resolved all eight findings in `code_review/2026-06-18-repository-code-review.md`
- Fixed ingestion failure exit status, country/provider metadata, PMI equilibrium, non-finite values, IMF forecast handling, future-date cleanup, and atomic DuckDB upserts
- Added the deferred Lens I climate slot and a read-only Streamlit status entry point
- Expanded regression suite from 73 to 79 tests; all pass
- Live pipeline verified: 59/59 OK, 0 empty, 0 errors, 0 sanity warnings, 0 future-dated rows
- Full `docker compose up --build -d` acceptance run passed: pipeline exited 0 and dashboard served on port 8501
- Next: Phase 1B composites engine (Growth Score, Inflation Score, Regime Quadrant, Disequilibrium Score)
- Blockers: None

---

## 2026-06-18 — Session 4: Phase 1A-iii Fiscal / IMF lenses

- Shipped Phase 1A-iii end-to-end: 9 new bindings (FRED: TFP, PPI broad, household debt/GDP, corporate debt, federal deficit, interest payments; WB: govt revenue % GDP; IMF: primary balance, structural balance); 13 new tests; suite 73/73 passing
- Added `fetch_imf_series()` to `loader.py` using IMF Datamapper REST API (no auth, ISO-3 country codes, forecast-year filter, parquet cache, tenacity retry)
- Added Pass 3 (IMF) and renumbered Derived as Pass 4 in `pipeline.py`; header updated to reflect all four providers
- Pipeline verified: 59/59 OK, 0 empty, 0 errors, 0 sanity warnings; `growth.tfp` (RTFPNAUSA632NRUG) was last unresolved ⚠ VERIFY — now confirmed and ingesting
- Key finding: IMF Datamapper uses ISO-3 codes (USA not US); `fiscal.structural_balance` last obs is 2026-12-31 (in-year WEO projection) — flagged in `notes`
- Next: Phase 1B — composites engine (Growth Score, Inflation Score, Regime Quadrant, Disequilibrium Score)

---

## 2026-06-18 — Session 3: Phase 1A-ii World Bank lenses

- Shipped Phase 1A-ii end-to-end: `fetch_wb_series()` (direct REST, parquet cache, tenacity retry) in `loader.py`; WorldBank Pass 2 in `pipeline.py`; 13 new bindings in `us_bindings.yaml`; 9 new tests; suite 60/60 passing
- Pipeline verified live: 50/50 OK, 0 empty, 0 errors, 0 sanity warnings — Lens F (external/trade), Lens G (capital/currency), Lens A supplement (R&D), Demographics all ingesting cleanly
- Key finding: WGI `.EST` governance series confirmed deleted/archived from WB v2 API — 5 deferred slots created; resolution requires WGI bulk CSV download from WGI portal
- Decided: use direct `requests` for World Bank API (not `wbgapi`, which produces JSON-decoding errors in this environment)
- Updated `docs/project_plan.md`: Phase 1A-i/ii marked ✅ complete, all verified series IDs updated ✓/⛔, Appendix A reorganized; added project_plan update step to session-close checklist
- Next: Phase 1A-iii (IMF/OECD fiscal lenses) — verify FYFSD/FYOINT, GGXONLB/GGSB, bind GC.REV.XGRT.GD.ZS, PPIACO, HDTGPDUSQ163N, BCNSDODNS

---

## 2026-06-18 — Session close
- Shipped Phase 1A-i end-to-end: FRED loader, transform, normalize, DuckDB store, pipeline orchestrator, 51 tests (all pass)
- Pipeline verified live against FRED: 37/37 signals OK, 0 errors, 0 sanity warnings; ~85k rows in DuckDB
- Fixed spec error: Philly Fed PMI series ID `GACDISA066MSFRBPHI` → `GACDFSA066MSFRBPHI`; documented ICE BofA FRED truncation (HY spread 3yr history only, G-10)
- ADRs 001–005 decided and written; G-01 through G-10 tracked in session-checklist.md
- Next: Phase 1A-ii (World Bank lenses) or Phase 1B (composites engine) — user's choice at next session open

---

## 2026-06-18 — Session 2: Phase 1A-i Code Complete

**Done:**
- Scaffolded full project structure: `indicators/`, `store/`, `config/`, `tests/`, `dashboard/`
- `requirements.txt`, `Dockerfile`, `docker-compose.yml`
- `indicators/models.py`: Pydantic `CountryBinding` + `Signal` contract
- `indicators/loader.py`: FRED fetcher with parquet disk cache, tenacity retry, TTL-based freshness
- `indicators/transform.py`: YoY%, level/spread pass-through, momentum period maps
- `indicators/normalize.py`: Z-score, percentile, direction, staleness, `build_signals`, `sanity_check`
- `indicators/pipeline.py`: full orchestrator (Pass 1 FRED, Pass 2 derived series, sanity gates, `--refresh`/`--latest` flags)
- `store/store.py`: DuckDB schema init, idempotent upsert, `query_latest`, `query_series`
- `config/us_bindings.yaml`: 29 FRED bindings (lenses A–E + Master, all `verified: true`) + 4 derived
- `config/composites.yaml`: Growth/Inflation Score weights (ADR-005), disequilibrium forces
- **51 tests written and passing** (test_transform, test_normalize, test_store)
- Pushed to https://github.com/benito334/indicators-machine

**Pipeline run results (2026-06-18):**
- 36/37 FRED OK, 1 empty (GACDISA066MSFRBPHI — bad ID in spec), 0 errors, 0 sanity warnings
- Fixed PMI proxy ID: `GACDISA066MSFRBPHI` → `GACDFSA066MSFRBPHI` (one char off)
- After fix: **37/37 signals OK, 0 empty, 0 errors, 0 sanity warnings**
- Discovered: all ICE BofA series on FRED truncated to 2023-06-19 (licensing change). HY spread has only 787 obs. Documented as G-10. BAA10Y (since 1986) is the primary long-history credit spread.
- DuckDB now has signals across: lenses A–E + Master, 33 FRED series + 4 derived
- Total rows: ~85,000+ time-series observations stored

**Current signal state (as of 2026-06-17/18):**
- Growth: cooling (payrolls +0.3% YoY P=22%, capacity util 76% P=23%)
- Inflation: above target (core PCE 3.3% YoY P=72%, core CPI 2.8% P=58%)
- Policy: mild restriction (real fed funds +0.81%, real 10Y yield +2.14% at P=88%)
- Credit: very loose (Baa spread 1.55% at P=9%, HY spread 2.63%)
- Regime: Disinflationary Slowdown / mild Stagflation border

**Next session:**
- Phase 1A-ii: add World Bank lenses (F external, G capital/currency, H governance, demographics)
- OR begin Phase 1B composites engine if user prefers to see the regime quadrant first

**Blockers:** None — pipeline is fully operational.

---

## 2026-06-18 — Session 1: Project Bootstrap

**Done:**
- Read and analyzed `docs/project_plan.md` (Master Technical Specification v2).
- Identified key weaknesses and gaps in the plan (see session-checklist.md).
- Created all project documentation:
  - `CLAUDE.md` — authoritative session guide with locked-in paths, rules, stack, phase map
  - `worklog.md` — this file
  - `session-checklist.md` — per-session pre/post checklist + open items
  - `docs/decisions/ADR-001-duckdb-signal-store.md`
  - `docs/decisions/ADR-002-apscheduler-orchestration.md`
  - `docs/decisions/ADR-003-alfred-vintages-deferred.md`
  - `docs/decisions/ADR-004-philly-fed-pmi-proxy.md`
  - `docs/decisions/ADR-005-composite-weights.md`

**Locked in (confirmed by user):**
- Data path: `/mnt/data/project_data/all_weather/indicators_machine/`
- DB path: `/mnt/data/db/all_weather/indicators_machine/`
- Rule: Dockerize everything
- Rule: Use existing tools/packages before building from scratch

**Next session should start with:**
- Phase 1A: scaffold directory structure, `requirements.txt`, `docker-compose.yml`, `.env.example`
- Define Pydantic models for `IndicatorConcept`, `CountryBinding`, `Signal` in `indicators/models.py`
- Write DuckDB schema in `store/store.py`
- Write FRED fetcher with cache in `indicators/loader.py`

**Blockers:**
- `FRED_API_KEY` must be provisioned before ingestion can run. Check with `echo $FRED_API_KEY`.
- `EIA_API_KEY` required for commodity data (Lens B / crude oil) — lower priority, Phase 1A can proceed without it if crude oil is fetched via FRED `DCOILWTICO` (no key needed via FRED).

---

---

## 2026-06-23 — Session: Weight Audit enhancements + Weight History page

**Done:**

### Bug fixes
- Fixed blank graphs on Weight Audit page (`/weight-audit`): two separate Plotly bugs:
  1. `figure_layout()` returns `margin`/`xaxis`/`yaxis` keys — callers were passing duplicates → split into two sequential `update_layout()` calls across all four chart functions
  2. Plotly rejects 8-digit hex colors (`#RRGGBBAA`) — added `_hex_alpha()` helper to convert to `rgba(r,g,b,a)` format

### New features shipped
1. **Re-run button** on Weight Audit page — triggers force balance, correlation heatmaps, and Monte Carlo on demand without a page reload
2. **Importance Editor (Section 4)** — editable DataTable showing all signals for the selected country with importance, tier, base_share, quality_factor; live G/I ratio preview recalculates as values are edited; Reset and Save buttons; Reason text input before save
3. **GDP-Regression Calibration (Section 5)** — `indicators/calibrate.py`: OLS of each growth signal's quarterly Z-score against `{cc}.master.gdp_real`; positive betas normalized to contribution shares then scaled to [0.10, 0.95]; β ≤ 0 signals get no recommendation (Option B — user decides); results table shown in UI with recommended importance and Δ from current; "Apply Selected to Editor" button populates editor for review before save
4. **Weight Change Log** — `weight_change_log` table added to DuckDB (log_id, changed_at, country, signal_id, basket, old/new importance, delta, reason, source); every save from the editor writes a row; `log_weight_changes()`, `query_weight_change_log()`, `update_weight_change_reason()` in `store/store.py`
5. **Weight History page** (`/weight-history`) — new `dashboard/weight_history.py`; table of all importance changes, editable Reason column, Save Notes button, country filter; wired into charting.py nav and `_PAGE_MAP`
6. **Methodology page** — Section 12 expanded with importance tier table, GDP regression calibration subsection; row in deferred table updated (OLS calibration now live)

**Files changed:**
- `indicators/calibrate.py` — NEW
- `store/store.py` — `weight_change_log` DDL + 3 new functions
- `dashboard/weight_audit.py` — Re-run store, editor section, calibration section, `_hex_alpha()`, split `update_layout()` calls
- `dashboard/weight_history.py` — NEW
- `dashboard/methodology.py` — expanded Section 12, updated Section 13 deferred table
- `dashboard/charting.py` — import + nav link + page function + `_PAGE_MAP` entry for weight-history

**Current state:** 353 tests pass. 119 signals (63 US + 34 EZ + 22 KR). Docker rebuilt clean, :8502 HTTP 200.

**Next session:** Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`). BEA refresh available after 2026-06-26.

---

## 2026-06-24 — Bug fixes: Monte Carlo graphs + Importance Editor copy button

**Done:**
- **Monte Carlo blank graphs fixed**: `titlefont` is a deprecated Plotly v4 property — removed in v5. Two axes in `_mc_scatter` (Growth Score, Inflation Score) and the Y-axis in the force balance bar chart used it, causing a silent `ValueError` that killed the callback. Fixed to `title={"text": ..., "font": {...}}` in all three places.
- **Importance Editor copy button**: `dcc.Clipboard` added to Section 4 header (top-right). Content callback converts table rows to TSV (Signal, Basket, base_share, importance, Tier, quality_factor, Raw Weight) on every table update — paste directly into a spreadsheet. Content updates automatically on country switch, reset, or applied calibration.

**Files changed:** `dashboard/weight_audit.py`

---

## 2026-06-24 — Threshold-Based Regime Classifier (Phase 3 analysis tool)

**Done:**
- `indicators/regime_classifier.py` (new): standalone `classify_regimes_threshold()` function — 5-dimension hard Z-score threshold classifier (Growth · Inflation · Rate · Credit · Volatility). Signal map per country (US/EZ/KR) with inversion flags for spread-based credit signals. Independent rolling Z-score (not from pipeline's pre-computed column). GDP quarterly fill: forward-fill or decay-weighted (Z-score decays toward 0 between releases with configurable half-life). VIX loaded from raw parquet cache or FRED fetch (US only, gracefully skipped if unavailable).
- `dashboard/regime_classifier_page.py` (new): full Dash page at `/regime-classifier`. Config panel: lookback dropdown (5/10/20yr), upper/lower threshold inputs, GDP fill toggle (ffill/decay) with conditional halflife slider, credit signal dropdown (BAA Spread / Gov Debt-GDP), Run button. Three result sections: (1) dimension flag heatmap, (2) threshold quadrant step chart, (3) comparison vs composites engine with agreement rate metric.
- `dashboard/charting.py`: new "Analysis" nav group + import + page function + `_PAGE_MAP` entry.

**Signal map:**
- US: growth=`us.master.gdp_real`, inflation=`us.inflation.cpi_headline`, rate=`us.policy.real_fed_funds`, credit=[`us.premium.credit_spread_corp`|`us.credit.gov_debt_gdp`], volatility=VIXCLS
- EZ: growth=`ez.master.gdp_real`, inflation=`ez.inflation.cpi_headline`, rate=`ez.policy.real_yield_10y`, credit=[`ez.credit.btp_bund_spread`|`ez.credit.gov_debt_gdp`]
- KR: growth=`kr.master.gdp_real`, inflation=`kr.inflation.cpi_headline`, rate=`kr.policy.yield_10y`, credit=`kr.credit.gov_debt_gdp`

**Smoke test (US, 10yr lookback):** 517 months 1983–2026. 2020-04 → Disinflationary Slowdown ✅, 2021-06 → Inflationary Boom ✅. EZ: 336 months.

**Next session:** Phase 2 Japan rollout. BEA refresh after 2026-06-26.

---

## 2026-06-24 — Regime Classifier: placeholder fix + guidance doc reorganisation

**Done:**
- Fixed blank graphs on `/regime-classifier` page: `dcc.Graph` components initialise with `_placeholder_fig()` ("Click ▶ Run Classifier to generate results") instead of empty white boxes. Chart callbacks also return placeholder instead of `PreventUpdate` when store is empty.
- Reorganised `docs/Guidance/`: consumed guidance docs moved to `docs/Guidance/Used/`; `Backtesting_Indicator_imporvements.md` is the active working document for Phase 3.

**Files changed:** `dashboard/regime_classifier_page.py`, `docs/Guidance/` structure.

---

## 2026-06-28 — Global Overview Cycle Health Index

**Done:**
- Added Cycle Health columns to `/overview`: raw index, debt-adjusted weighted index, and interpreted cycle stage.
- Implemented browser-local Cycle Health config modal for weights, debt target, and stage thresholds.
- Direct nominal GDP growth is used when available; otherwise the Overview uses `real GDP growth + headline inflation` as a display proxy so EZ/KR can participate.
- Added focused tests for the Cycle Health math and Overview route rendering.
- Follow-up: added Methodology documentation for the Cycle Health formulas/defaults and a config-modal clipboard button that copies the current settings.
- Follow-up: Overview table values are now clickable and open a time-series modal. Standard cells plot their underlying DB signal history; CHI cells plot dynamically computed raw/debt-adjusted history using the active browser config.
- Follow-up: CHI v2 implemented from feedback — raw formula now uses real GDP growth; debt-adjusted CHI separates public/private debt gaps with public-only fallback; thresholds default to adaptive `k × σ`; component contributions support age-based freshness decay.

**Validation:** `python3 -m pytest` → 360 passed; follow-up `python3 -m pytest tests/test_charting.py` → 77 passed.

**Next:** Review the default weights/thresholds against Phase 3 back-test scenarios, then decide whether to persist country-specific defaults in YAML.

---

## 2026-07-05 — Ray Dalio AI review process (systematic, all 5 forces + Debt Stress + CHI)

**Done:**
- Started a new process reviewing the project against a "Ray Dalio" AI persona (digitalray.ai, browser-driven) to sanity-check the methodology from a genuine macro-cycle framework perspective. New tracking doc: `docs/Guidance/ray_dalio_review_log.md` — coverage matrix, session log, and a 23-item triaged punch list (ready-to-implement / needs-design-pass / needs-data-feed-check / acknowledged-no-build).
- Discovered and mined a large amount of pre-existing informal review history in the same tool (growth/inflation composite critique, historical ground-truth validation against 1990s/2008/QE episodes).
- Systematically reviewed all 5 forces, the Long-Term Debt Stress composite, and the Cycle Health Index, each landing on a concrete, implementable plan (see log for full detail per area).
- Biggest structural output: a complete, ordered 7-step regime-classifier threshold algorithm (country-vol-scaled baseline → credit multiplier → volatility multiplier → multiplicative combination → classify → correlation-divergence overlay), with worked Python pseudocode and a numerical example — supersedes 4 previously-open punch items.
- Confirmed two free data feeds via direct FRED series-search (not guessed): `DRSDCILM` (SLOOS loan-demand, pairs with existing `DRTSCILM` lending-standards signal) and `FEDTARMD` (FOMC dot-plot median, a forward-guidance proxy since true Fed-funds-futures data isn't free).
- Nothing implemented yet — this was the review/planning pass only.

**Next:** Work through the 23-item punch list; start with the ready-to-implement items (#1, #2, #3, #7, #13, #16, #17, #19, #21, #22, #23), then resolve remaining data-feed checks (#15, #18).

---

## 2026-07-05 — Ray Dalio review punch-list implementation (part 1: 8 of 11 items)

**Done:**
- **#1 Growth weights**: ran `indicators/calibrate.py` GDP-regression, applied recommended importances to all 9 cyclical growth signals (e.g. job_openings 0.85→0.25, real_pce 0.65→0.95), logged to `weight_change_log` (source="regression").
- **#2 Inflation breakevens**: new derived signal `inflation.breakeven_avg` (mean of T5YIE/T10YIE) replacing the two separate breakeven slots in the composite; both raw signals still exist individually.
- **#3 Crude oil rolling avg**: found already implemented from an earlier session (`pre_smooth_window: 7`) — no work needed.
- **#7 Growth productivity trend**: added `growth.productivity`/`growth.tfp`/`growth.rnd_intensity` to the growth composite at modest weights (previously excluded as "structural frequency" even though the signals already existed).
- **#16/#17/#19 Debt Stress**: documented a sparse-country minimum-viable 3-component fallback in `longterm_stress.yaml`; implemented Ray's dynamic stock/flow weighting formula (`_dynamic_group_weights()`); added linear interpolation for single missing annual observations (`_fill_missing_annual_via_interpolation()`).
- **#21/#22 Cycle Health Index**: conditional growth/rate/inflation weight rule (`_conditional_chi_weights()`) and a nominal/real policy-rate toggle (`use_real_policy_rate`, defaults nominal).
- **Data-feed checks resolved but not yet coded**: #8 (`FEDTARMD` FOMC dot-plot as forward-guidance proxy — no free futures feed exists) and #9 (`DRSDCILM` SLOOS loan-demand series confirmed free, pairs with existing `DRTSCILM`).
- **#13 Volatility restructure — data constraint found**: FRED only has daily `SP500` for the US (from 2016-07), and just *monthly* share-price indices for EZ (`SPASTT01EZM661N`) / KR (`SPASTT01KRM661N`) — no daily equity feed for EZ/KR, so true realized vol isn't feasible there without a lower-resolution monthly-return proxy. Architecture work still pending.

**Validation:** `python3 -m pytest` → 370 passed, 1 pre-existing unrelated failure (`test_compare_raw_vs_processed_level_signal`, a pandas dtype bug, reproduces on main without any of these changes — spawned as a separate task). Pipeline re-run clean after each change.

**Remaining:** #13 (Volatility restructure, needs a data-feed decision given the constraint above) and #23 (the full regime-classifier threshold algorithm — the biggest, most invasive remaining change).

---

## 2026-07-05 — Ray Dalio review punch-list implementation (part 2: Volatility restructure, #13)

**Done:**
- **New signals**: `volatility.equity_index` (US: `SP500` daily; EZ: `SPASTT01EZM661N` monthly; KR: `SPASTT01KRM661N` monthly) and `volatility.vix` (US only, `VIXCLS`). All confirmed via direct FRED series-search, not guessed.
- **New derived signal**: `volatility.realized_vol` — annualized rolling std of log returns on the equity index (21-day/√252 window for US daily data, 12-month/√12 window for the EZ/KR monthly proxy). `indicators/pipeline.py::compute_derived`.
- **Volatility is now a real basket composite** (`volatility_score`/`volatility_momentum`), matching the same architecture as Growth/Inflation/Rate/Credit: added to `models.py`, `store.py` (schema + migration), `composites.py` (validation, scoring, momentum, weight_audit), `charting_data.py::load_composite_component_status` and `load_composite_history`. US basket = realized_vol (importance 0.70) + VIX (importance 0.90, bonus weight); EZ/KR = realized_vol only (single-signal, `quality_factor: 0.70`, low-coverage/directional-only, documented in each composites.yaml).
- **Removed the old ad-hoc raw-VIX path**: deleted `_vix_df()`/`_signal_rows()`/`_dash_td()` (dead code) from `signals_page.py`; `force_detail.py`'s `/signals/volatility` page dropped its special-case branch and now uses the same generic composite-driven banner/table/chart path as every other force.
- **Bug found + fixed along the way**: `load_composite_history()` in `charting_data.py` had an explicit column SELECT list that omitted the (pre-existing) `rate_score`/`credit_score` columns from ever showing up correctly if they'd been missing too — added `volatility_score`/`volatility_momentum` to that list. Also fixed a `PermissionError` in `loader.py`'s cache-write step (pre-existing root-owned cache file blocking a legitimate new-binding fetch) by logging a warning and proceeding without caching instead of crashing the pipeline.
- **New doc**: `docs/Guidance/data_source_wishlist.md` — running checklist of data we want but don't have a free source for yet (daily EA/KR equity index, MOVE-equivalent, credit-spread vol, ECB/BOK loan-demand series, debt-service-to-consumption/investment denominators), with guidance for the next country rollout (Japan).
- **Verified live in the dashboard** (rebuilt `docker compose build/up charting`): `/signals/volatility` and `/signals` overview both render the new composite correctly (Force Z, momentum, weight columns, 4-panel stacked chart with composite Z + momentum + per-signal dual panels) for US; confirmed EZ/KR ingest correctly too (EZ currently shows `NaN` for the latest few months because the OECD source lags beyond the monthly forward-fill window — same expected staleness behavior as other known-lagging EZ signals, not a bug).

**Validation:** `python3 -m pytest` → 377 passed, 1 pre-existing unrelated failure (dtype bug, already tracked separately). Full pipeline re-run clean across US/EZ/KR.

**Next:** #23 — the full regime-classifier threshold algorithm (the last, most invasive punch-list item).

---

## 2026-07-05 — Ray Dalio review punch-list implementation (part 3: regime-classifier algorithm, #23 — punch list complete)

**Done:**
- Implemented `compute_dynamic_thresholds()` in `dashboard/charting.py` — Ray's full 7-step algorithm: country-vol-scaled baseline (24-mo rolling σ of growth_score/inflation_score, look-ahead safe), credit-tightness multiplier (inflation threshold only), volatility multiplier ("vol of the vol" — 12-mo rolling σ of the composite's own Z-score history, both chips), multiplicative combination, and a correlation-divergence overlay (diagnostic only, N=3-month lookback).
- Opt-in, not a silent behavior change: added a "Use dynamic thresholds (Ray Dalio algorithm)" checkbox to the existing Regime Thresholds modal (`regime-threshold-store`). Off by default — every existing user sees identical behavior unless they explicitly turn it on. Wired into both the Regime History full-history chart loop and the single-row regime-info card (`update_regime_info` callback), so switching modes changes the actual classification, not just a display label.
- Verified live: enabling the toggle visibly changes the Growth/Inflation regime band pattern on `/regime-history`, and the header threshold display now shows a "DYNAMIC" badge. Confirmed via direct query that the computed thresholds are real and time-varying (US: dyn_gz ranges ~0.06–0.95, dyn_iz ~0.03–0.64 over history; credit_adj 1.0–1.07; vol_adj 1.0–1.12; divergence_flag fires ~33% of months) — no degenerate/constant values.
- Added 5 focused unit tests for `compute_dynamic_thresholds` (fallback on short history, credit-tightness affecting inflation only, volatility widening both chips, divergence-flag timing, graceful handling of a missing credit_score column).
- **Punch-list item #23 was the last one of the original 23** (plus #24, the wishlist doc) — all are now either implemented or explicitly deferred with a documented reason (data-feed gaps for #10/#15/#18, out-of-scope for #12).

**Validation:** `python3 -m pytest` → 382 passed, 1 pre-existing unrelated failure (dtype bug, tracked separately). Verified live in the rebuilt dashboard.

**Next:** Punch list is done. Remaining open items are all explicitly deferred (data-feed research per `docs/Guidance/data_source_wishlist.md`, or out-of-scope per the Allocation Layer boundary). Divergence-flag UI badge is a small nice-to-have follow-up, not blocking. BEA Q1 2026 refresh still pending per `session-checklist.md`.

---

## 2026-07-05 — Roadmap Phase A complete + Phase G backtest (G1+G2)

**Done:**
- **Roadmap created + Phase CC added**: `docs/Guidance/ray_framework_roadmap.md` — phased plan (A–H) for the 5-layer Ray-framework dashboard; Phase CC = country command center (single synthesis front-door page per country; v1 is assembly-only from existing data, closes the divergence-badge follow-up).
- **Phase A2**: `credit.loan_demand` (FRED `DRSDCILM`, SLOOS demand side) added to the US credit basket — pairs with supply-side lending standards (Ray #9). 139 quarterly obs, verified live.
- **Phase A1**: the assumed forward-guidance feed (`FEDTARMD` dot-plot) proved non-viable (future-dated forecast snapshot, no Z-scoreable history). Asked Ray; he chose a derived `policy.rate_expectations` = `yield_2y − fed_funds` ("money is made by identifying change rather than forecasting it"). Built at CONTEXT tier (0.45, inverted), 11,625 daily obs; keep/weight decision deferred to Phase G3 per his caveat.
- **Phase G1 — point-in-time backtest engine** (`indicators/backtest.py`): expanding-window shift(1) Z-scores (no statistical look-ahead), PIT composites (momentum tilt/age decay deliberately omitted — documented), classification via the production `_classify_regime`/`compute_dynamic_thresholds` (single source of truth). 9 unit tests.
- **Phase G2 — scenario scoring**: 8 named scenarios 1990→2024 (history starts 1980-81, so no 1970s replay). Results: wrong-direction ≈ 0% everywhere (direction validation PASSED with zero look-ahead); dynamic thresholds ≥ fixed (won 1990-91 recession 50→88% strict and late-90s boom 33→54%, tied the rest, cost 1 mislabeled month in 48). Verdict: supportive of dynamic, keep opt-in until G3. Design insight: the ΔMoM gate parks fast V-shaped episodes (COVID 33% strict) in Transition during the rebound — exit-condition asymmetry is a future refinement candidate.
- Report: `docs/backtests/pit_regime_backtest_us.md` (regenerate with `python -m indicators.backtest`).

**Validation:** `python3 -m pytest` → 397 passed, 1 pre-existing unrelated failure (dtype bug).

**Next (per roadmap sequence):** Phase B (promote productivity trend) → Phase CC (command center v1) → Phase C (debt-cycle stage classifier). G3 (ALFRED vintage replay + asset-outcome tests incl. rate_expectations validation) stays open.

---

## 2026-07-05 — Roadmap Phase B: productivity trend as a first-class read

**Done:**
- `productivity_score`/`productivity_momentum` composite (Ray's third big force) added end-to-end: models/store (columns+migration), composites engine, per-country configs (US 3-signal basket: labor productivity 0.80 / TFP 0.45 / R&D 0.30; EZ+KR single-signal R&D-only low-coverage), charting_data SELECT + component-status loop.
- UI: sixth "Productivity Trend" section on /signals (teal #3FBFB0) + full force-detail page /signals/productivity with the cyclical Growth Z overlaid (dotted) on the trend composite panel — the "cyclically strong but trend-decelerating" glance. Subnav link added.
- Methodology §7 basket table + revision-log entries (Phase A + B). 2 new composite tests.

**Validation:** 399 passed, 1 pre-existing failure. Pipeline populates all three countries (EZ/KR trend read ends 2023 — annual R&D source aging out honestly). Verified live.

**Next:** Phase CC — country command center v1 (assembly-only front-door page; closes the divergence-badge follow-up).

---

## 2026-07-05 — Roadmap Phase CC: country command center v1 (new default landing page)

**Done:**
- `dashboard/command_center.py` (new): one synthesis page per country answering "where is this country, on all three clocks, and what's changing." Routes `/` (now the default landing page — was Chart Overlay) + `/country`; "🎛 Command Center" nav entry at the top of Overviews.
- Cards (each links to its detail page): regime strip (Growth/Inflation chips via the production `_classify_regime`, honoring the threshold store *including dynamic mode* — computes `compute_dynamic_thresholds` and uses the latest dyn_gz/dyn_iz when dynamic is on; confidence, diseq, DYNAMIC badge); short-cycle levers (Growth/Inflation dials with Δ + momentum %, Credit conditions = composite + SLOOS supply-tightening/easing + loan-demand reads, Policy stance = rate_score accommodative/restrictive + 2y−funds hikes/hold/cuts read); long-term debt cycle (Debt Stress score + n/7 components, DSR Z + % of income + direction — "the earliest stress signal"); trend & big cycle (productivity trend with above/below-cycle read); what-changed top-8 Z movers (reuses `load_change_feed` + `_what_changed_children`).
- **Divergence badge live** — amber DIVERGENCE chip with tooltip when growth/inflation Z-scores have opposed signs for 3+ consecutive months (closes the open review-log #23 follow-up; the flag was computed but never surfaced).
- CC2 placeholder cards (dashed border, "planned") for Phase C cycle *stage* and Phase D big-cycle *order*.
- Lazy imports from `dashboard.charting` inside the callback (avoids circular import); module-level `@callback` pattern matching signals_page.
- `tests/test_command_center.py` (8 tests: layout, all cards present, drill-down hrefs, no_update on other pages, dynamic badge, EZ/KR no-crash, route registration). Methodology §15 revision-log row (also fixed a duplicated-row bug in the §15 copy-text table). Roadmap Phase CC marked ✅.

**Validation:** 407 passed, 1 pre-existing failure (dtype). Docker rebuilt; verified live in browser at `/` and `/country` — US renders all cards, card click navigates to `/signals/credit`, nav highlights Command Center; EZ/KR verified via direct callback tests.

**Next (per roadmap sequence):** Phase C — long-term debt-cycle *stage* classifier (calibrated against Phase G output; upgrades its CC placeholder card). Then Phase D research spike in parallel.

---

## 2026-07-05 — Roadmap Phase C: long-term debt-cycle stage classifier

**Done:**
- `indicators/debt_cycle_stage.py` + `config/debt_cycle_stage.yaml` (every threshold/weight TUNABLE-annotated): classifies leveraging / squeeze / deleveraging / reflation / neutral from 5 feature families — debt/GDP expanding percentile (ranked vs PRIOR history only, no look-ahead) + 3y trajectory (pp/yr), DSR 2y trend, real-rate−real-growth, nominal-growth−yield. Transparent weighted-condition argmax; per-quarter renormalization over available features (EZ/KR honestly run on 4/5 — no free debt-service series); <3 families → no label; 3-quarter rolling-mode smoothing that never carries a label across a data gap.
- Storage/pipeline: `DebtCycleStageSnapshot` model, `debt_cycle_stage_snapshots` DuckDB table (+ upsert/query in store.py), pipeline Pass 7 looping all configured countries.
- Dashboard: Command Center Cycle Stage card now LIVE (stage-colored, confidence + n/5 features, links to /debt-stress); Debt Stress page gained a Long-Term Cycle Stage section (current-stage chip + driving-features readout + colored quarterly stage band + per-stage score chart). Works for US/EZ/KR (stage section renders even where the US-only stress model shows its placeholder).
- Bugs fixed during build: empty pd.Series RangeIndex corrupting the feature-frame index union (EZ/KR produced zero features); resample().last() not reaching the current quarter (annual ratios went NaN at the newest quarters — added extend-to-current-quarter within ffill limit); smoothing carrying a stale label across raw=None gaps; in-progress future quarter emitted as "latest"; Python strftime %q (only plotly supports %q).
- US timeline sanity anchors hit: 1989–91 squeeze (S&L), 1992–95 reflation, 2007 pre-GFC squeeze, 2012–2020 reflation ("beautiful deleveraging"), 2020–23 COVID leveraging. Current reads: US=reflation, EZ=reflation, KR=leveraging.
- 17 new tests (`tests/test_debt_cycle_stage.py`); CC test updated (stage card live, Phase D placeholder remains). Methodology §9 subsection + §15 revision-log row; roadmap Phase C ✅.

**Deferred to G3 (explicit):** stage-threshold calibration against the PIT backtest.

**Next:** Phase D research spike (order-layer data hunt), then E (cross-country view), F (Japan), G3.

---

## 2026-07-05 — Roadmap Phase D: big-cycle ORDER layer (research spike + confirmed subset)

**Done:**
- **D1 research spike** (all feeds verified against provider endpoints, results in data_source_wishlist.md): WB Gini `SI.POV.GINI` ✔ (US 2024 / KR 2021 / JP 2020; EMU aggregate empty; WB v2 API intermittently 400s — retries recover); IMF COFER reserve-currency shares ✔ via the NEW IMF SDMX 2.1 API (`api.imf.org`, legacy dataservices host is dead) — pre-computed quarterly shares `G001.AFXRA.CI_{CUR}.SHRO_PT.Q`, 109 obs 1999→2026, USD 71.2%→57.1%; WB external debt `DT.DOD.DECT.CD` ✘ NULL for all high-income countries; V-Dem/Polity governance + GPR index ✘ no API → manual-load slots.
- **D2 build**: `fetch_imf_sdmx_series()` in loader.py (CSV Accept header, parquet cache, tenacity retry, stale-cache fallback); pipeline Pass 3.5 for `provider: IMF_SDMX` (series_id `"DATAFLOW/KEY"`, ECB convention); Lens J `order.*` bindings — us.order.gini (41.8), us.order.reserve_currency_share (57.1%), ez.order.reserve_currency_share (20.0%), kr.order.gini (32.9). KR reserve share honestly N/A (KRW inside "Other"); EZ Gini deferred (constructed big-4 proxy). 136 signals total. All `lead_lag: structural`, feed no composite.
- **D3**: Command Center Big-cycle position card live-partial — reserve share (level + 12m Δ) + Gini (level + year) + "governance/GPR deferred" note; placeholder retained for countries with neither.
- Wishlist: new ORDER section + A1 rate-expectations entry marked resolved. Roadmap Phase D ✅ (D4 = manual-load governance/GPR remains open). Methodology §15 revision row.

**Next:** Phase E — cross-country / relative-cycle view. Then F (Japan), G3.

---

## 2026-07-05 — Roadmap Phase E: cross-country relative-cycle view

**Done:**
- `dashboard/relative_view.py` (route `/relative`, "🌍 Relative Cycles" nav under Overviews): per-country cards showing all three clocks side by side — regime chips (threshold-store aware incl. dynamic mode, computed per country), debt-cycle stage chip, Growth/Inflation Z + Δ, debt stress, productivity Z, order reads (reserve share / Gini); each card links to the command center.
- Correlation section: 4 heatmaps — growth-score + inflation-score pairwise Pearson correlation over full common history AND last 10y. Month-period alignment (US composites land on the 5th, KR on month-end); <24 common months → NaN, never spurious.
- **The diversification answer as of today**: US–EZ growth correlation 0.86 over the last decade (same cycle in disguise; 0.60 full-history), US–KR 0.53. Inflation correlations 0.84–0.90 everywhere in the last 10y — the 2021–23 global inflation wave dominates; there is currently no inflation-cycle diversification among US/EZ/KR.
- 9 tests (`tests/test_relative_view.py`): correlation identities (±1), NaN on short overlap, start-window filter, day-of-month alignment, full-page render, route registration. Verified live in browser. Methodology §15 revision rows (script-inserted into both tables to avoid the duplicate-row bug pattern). Roadmap Phase E ✅.

**Next:** Phase F — Japan rollout (jp_bindings.yaml + jp_composites.yaml, sparse-country patterns end to end). Then G3, D4.

---

## 2026-07-05 — Roadmap Phase F: Japan rollout (25 signals, 6 composites, stage classifier)

**Done:**
- `config/countries/jp_bindings.yaml` (25 bindings, every FRED series verified via the metadata endpoint with observation ranges recorded per binding) + `jp_composites.yaml` (all 6 forces). Pipeline: **25/25 OK, 0 errors, 0 sanity warnings**; 161 signals total (73 US + 37 EZ + 25 JP + 26 KR).
- **JP data findings** (documented in the wishlist): NO live monthly CPI free — all OECD FRED CPI feeds ended 2021-06, so inflation = IMF WEO annual bridge only (is_proxy, quality 0.70; e-Stat API needs registration = highest-value follow-up). NIKKEI225 is a free DAILY feed → JP volatility is TRUE daily realized vol, US-quality (unlike EZ/KR proxies). Industrial production: index form died 2024-03, live feed is the GYSAM YoY form.
- JP added to `debt_cycle_stage.yaml` (4/5 features) — current stage **reflation** (textbook: r engineered below g at a 206%-of-GDP debt stock). Pipeline Pass 7 moved AFTER the country loop (was staging before new countries ingested).
- Dashboard: country selector enabled (was "soon"), Relative Cycles + Command Center + stage section all render JP; currency label map extended (JPY).
- **The payoff read**: JP inflation correlates +0.03 with US over the last 10y — the only real inflation diversifier among the four economies. JP growth correlates 0.74 with US/EZ.
- Spot-check passed: unemployment 2.5%, 10y JGB 2.65% (post-normalization), gov debt 206.5% (IMF), CA +4.9%, JPY reserve share 5.44%, REER 65.9 (weak-yen era). All vintage_available=false, honest flags.
- 433 tests pass. Roadmap Phase F ✅; wishlist JP section rewritten with results; UK noted as next rollout.

**Not built (honest):** JP Debt Stress composite — model stays US-only pending a JP DSR source.

**Next:** Phase G3 (ALFRED vintage replay + asset-outcome tests) — the last major open roadmap item; then D4 (manual-load governance/GPR).

---

## 2026-07-06 — Roadmap Phase G3: ALFRED vintage replay + asset-outcome tests (Phase G complete)

**Done:**
- `indicators/backtest_g3.py` (run: `python -m indicators.backtest_g3`; report: `docs/backtests/pit_regime_backtest_g3_us.md`): ALFRED full-vintage fetch (`fetch_alfred_vintages`, one call per series via realtime_start=1980/realtime_end=9999, cached `raw_cache/alfred_{id}.parquet`), `VintageSeries.as_known(t)` bisect lookup, `pit_vintage_zscores` (value AND its expanding reference history both from data-as-known-at-t), vintage PIT composites → production classifier → all 8 scenarios × fixed/dynamic vs the G1 final-data baseline. 15/19 basket signals fully replayed (crude oil, breakevens, Philly Fed, WB R&D use final values — market-priced/non-FRED, flagged in report).
- Chip-conditioned forward returns (no information overlap): 558-month bond test (DGS10 duration proxy) — Inflation chip → −10%/yr fwd bond returns vs +5% under Disinflation, the chip carries real information; equity test honest-flagged as tiny (free SP500 ≈ 10y).
- `rate_expectations` IC test: raw IC 0.079, 2Y-level IC 0.245, incremental IC (residualized on 2Y) **+0.153** over 555 months.
- Stage-episode calibration: post-GFC reflation 100%, COVID leveraging 100%, 2007-08 squeeze 50% (modal leveraging — engages late; logged as the one tweak candidate, not tuned on a single episode).
- **Verdicts** (in the report + roadmap): (1) direction validation survives vintage replay — G1/G2 was not revision-look-ahead; (2) **A1 closed: rate_expectations keeps its slot** at CONTEXT 0.45; (3) dynamic thresholds stay opt-in; (4) stage thresholds confirmed except the late squeeze.
- 6 new tests (`tests/test_backtest_g3.py`: as-known semantics incl. future-vintage invisibility, no-overlap forward windows, bond-return sign); backtest.py header updated. **Phase G fully complete.**

**Remaining open (small):** D4 (manual-load governance/GPR), UK rollout, e-Stat JP CPI registration, pre-existing dtype test failure, 2007-squeeze threshold tweak candidate.

---

## 2026-07-06 — UK rollout (Phase 2 continuation): 27 signals, 6 composites, stage classifier

**Done:**
- `config/countries/gb_bindings.yaml` (27 bindings, every FRED/WB/IMF ID verified against provider endpoints with ranges noted) + `gb_composites.yaml` (all 6 forces, KR structure). Pipeline: **27/27 OK, 0 errors, 0 sanity warnings**; 188 signals total (73 US + 37 EZ + 27 GB + 25 JP + 26 KR).
- **GB data findings** (wishlist updated): monthly CPI (headline + core) ends 2025-03 — same OECD cutoff as KR; IMF annual bridge covers; **ONS API (free, unregistered) is the highest-value follow-up**. No daily FTSE on FRED → monthly-proxy volatility (quality 0.70). ILO monthly unemployment is the LRHUTTTT form (LRUNTTTT 400s). Industrial-production index form died 2024-03 (same as JP) — GYSAM YoY form is live.
- GB added to `debt_cycle_stage.yaml` (4/5 features) — **current stage: squeeze, confidence 0.53, the strongest stage read of any country** (gov debt 102% GDP, gilts 4.94% vs real growth +0.9% → r > g, credit composite −1.76). A coherent Ray read for the UK.
- Dashboard: country selector enabled (GB was the last "soon" entry — dropdown is now fully live), Relative Cycles 5-country grid + 5×5 correlation matrices, Command Center + stage section render GB, GBP currency labels.
- Cross-country reads with 5 countries: GB inflation correlates 0.94 with EZ (last 10y) — no diversification there; GB growth 0.51 vs US. JP inflation (+0.03 vs US) remains the only real diversifier.
- Spot-check passed: CPI 3.4% (Mar-25), unemployment 4.9%, gilt 4.94%, gov debt 102.3%, CA −2.4% (the UK's structural deficit), GBP reserve share 4.40%, REER 111. All vintage_available=false, honest flags.
- 440 tests pass. Methodology §15 revision row.

**Next:** China is next in the Phase 2 order (WB/IMF harmonized only — NBS out of scope). Other open tails: D4 manual-load slots, ONS/e-Stat registrations, dtype test failure, 2007-squeeze threshold tweak.

---

## 2026-07-06 — Unification audit (Ray session): windows, taxonomy, confidence

**Ray session** (rulings logged in full in ray_dalio_review_log.md): Q1 lookback windows → rolling everywhere, canonical defaults 48m growth / 96m inflation / 36m policy, user-overridable, cross-country views on ONE uniform window; Q2 taxonomy → four seasons demoted to background shading beyond the ±threshold lines only, explicit "Transition — no clear season" inside the band; Q3 → confidence renamed **Chip Direction Agreement**, split G/I, measured against the chips' headings.

**Done:**
- **Root fix — rolling composite columns were US-only.** The sidebar window sliders silently fell back to full-history for every non-US country. Rolling passes (36/48/60m force + 90/120m inflation) now run inside the pipeline country loop; backfilled for EZ/GB/JP/KR (all 5 countries populated).
- Canonical defaults wired: sliders + localStorage stores default to 48m/90m (Ray ruled 96m — 90m is the existing DB grid point, Δ documented; policy 36m deferred: rate composite has no rolling variants yet, logged).
- **Command Center** now honors both window stores (dials, Δs, chips, dynamic-threshold inputs on windowed columns; "window 48m / 90m" header annotation) and displays **chip agreement G x% · I y%** instead of the legacy confidence.
- **Relative Cycles**: cards + correlation matrices normalized on canonical 48m/90m for every country (Q1b), annotated in the heatmap titles.
- **Regime Map/History**: season shading only beyond ±gz/±iz with a central "Transition — no clear season" label; new threshold-aware `_season_label()` replaces every sign-based quadrant re-derivation (scatter hovers, info card accent, history step row); `_hex_to_rgba` hardened for 3-digit hex.
- **Chip Direction Agreement** on the Regime Map info card: per-force agreement vs the chip heading (inverted signals flipped), G/I sub-line under the headline number; stored legacy `confidence` kept as fallback only.
- 5 new tests (season-label semantics, agreement math, CC window honoring incl. full-history mode, relative canonical windows); 445 total pass.

**Still open:** rate-basket rolling variants (36m policy default), stored `quadrant` column retirement (kept for legacy/backtest compat).

---

## 2026-07-06 — Dynamic thresholds re-paired with the window unification

**Trigger:** user asked how the Ray dynamic-threshold algorithm composes with the audit's rolling windows — the trace found a real seam.

**The bug:** the Regime History chart + regime info card fed FULL-HISTORY `growth_score`/`inflation_score` into `compute_dynamic_thresholds` while classifying the WINDOWED columns. Ray's step 1 scales by the σ of "the composite's own Z-score" — post-audit that is the windowed series, so thresholds were scaled to the wrong distribution. Material: at 48m/90m the correct US values are gz=0.205/iz=0.082 vs the mismatched 0.093/0.116 (growth threshold more than doubles). The CC and Relative pages were already correct (wired during the audit).

**Done:**
- `_dyn_threshold_input(comp, g_col, i_col)` shared helper — every dynamic call site now builds the input from the ACTIVE (windowed or full) columns: regime info card, Regime History chart, scatter, CC, Relative.
- Regime Map in dynamic mode: corner shading, threshold lines, and hover season labels all positioned by the latest dynamic gz/iz on the windowed series (latest-row convention, same as the Regime History hlines) — geometry and labels always agree.
- Regression test: windowed-vs-full dynamic thresholds genuinely differ AND the scatter geometry matches the windowed-input values. 445 tests pass.

---

## 2026-07-06 — Regime Map: dynamic band follows the time step

**Trigger:** user asked whether walking back in time moves the dynamic threshold bounds on the map. It didn't (geometry was pinned to the latest month, inconsistent with the info card's per-row values).

**Done:** selected-index resolution moved above the shading block; in dynamic mode the corner shading + threshold lines are positioned by the SELECTED month's dyn_gz/dyn_iz (on the active windowed columns), so Prev/Next steps move the band to what the classifier used that month. Hover labels are per-row — each history dot judged against its own month's thresholds. Verified: US step 0 → gz 0.205 (calm era, tight); step 60 (COVID-vol era) → gz 1.02/iz 1.13 (wide); fixed mode static at 0.5. 445 tests pass.

---

## 2026-07-06 — User Guide tab: a training course on the Dalio machine

**Done:**
- `dashboard/user_guide.py` (route `/guide`, "🎓 User Guide" nav in Reference): 9-lesson sequential course for someone who knows Dalio's concepts but hasn't operated a live diagnostic — L0 machine-in-one-picture, L1 debt-cycle hook, L2 dials/Z-scores, L3 chips/thresholds/windows/agreement/divergence, L4 Regime Map, L5 stress-vs-stage, L6 productivity/order, L7 diversification, L8 reading routine (daily/weekly/monthly + when-a-chip-flips playbook + scope boundary).
- **Ray pedagogy pass first** (logged in review log): 3 newcomer traps front-loaded as amber callouts (Z≠grade; magnitude≠direction; never the two dials alone); debt-cycle hook moved BEFORE the dial mechanics per his ordering ruling; L0 diagram upgraded with data-source labels, credit feedback loop, adaptive "normal" band (previews dynamic thresholds), order as background shading.
- Live data in every lesson ("On your dashboard right now" green boxes) — country/theme/window/threshold aware, same code paths as the Command Center; Methodology §N links wherever formulas live.
- 3 plotly diagrams: three-lines-and-band machine chart, stage-colored debt-cycle arc with a "you are here" marker, regime-map geography miniature with the live dot.
- 10 tests (Ray's teaching order asserted, traps present, live boxes ≥5, all countries render, page guard, route). Suite 455 passing. Verified live in browser.

---

## 2026-07-06 — UI cleanup: retired pre-Ray surfaces, fixed stale content

**Audit-driven cleanup (user-approved, full A+B scope):**
- **Retired to `archive/`** (with README): the standalone Regime Classifier page + engine (`/regime-classifier` — a second, sign-based 4-season classifier that could contradict the chips; nothing else imported it), the Streamlit :8501 proof (`dashboard/app.py` + its 41 tests — 4-quadrant HUD, legacy confidence), and the TradingView :8503/:8004 SPA (`charting_lc/` — quadrant history, duplicated Chart Overlay). docker-compose is now 2 services (pipeline + charting). The "Analysis" nav group is gone (was only the classifier).
- **Deleted outright:** `config/composites.yaml` (deprecated since 2026-06-22, read by nothing) and the dead `_RQ_MAP` constant.
- **Stale content fixed:** Regime History help panel rewritten to chips/thresholds/windows language (+ User Guide link; the old panel taught sign-based seasons, referenced a step-function chart removed in June, and pointed at the deleted composites.yaml); chart Row 6 relabeled "Direction Agreement (legacy)" with honest hover; footer "Confidence" definition → Chip Agreement; Weight Audit Monte Carlo now classifies trials by the threshold-aware season zones (`_season_label`, static ±0.5) with band-aware shading instead of sign quadrants; CLAUDE.md "What This Project Is" rewritten (three clocks, chips as the rule, seasons as map geography).

**Incident during rollout (resolved):** `docker compose up -d --remove-orphans` started the pipeline service, whose image was stale (June code — 63 US signals, 2 countries, no rate/credit/vol/productivity or rolling columns). Its Pass 5/6 overwrote composites + debt-stress for US/EZ/KR with old-schema output (signals + stage tables unharmed — upsert-only / not in old image). Recovery: stopped charting, re-ran the current pipeline from the host (188 signals, all 5 stages correct, all columns verified restored to exact pre-clobber counts), rebuilt BOTH images so the pipeline image can't lag the code again. **Lesson (worth remembering): `docker compose build` must build all services, not just charting — a stale pipeline image silently rewrites the DB with old formulas.**

**Validation:** 414 tests pass (455 − 41 archived Streamlit tests); MC smoke-tested; Command Center/Regime Map/Guide verified live post-rebuild.

---

## 2026-07-06 — Workbench: TV-style chart studio (replaces Chart Overlay + Data Explorer)

**Done (user-approved design: Plotly-in-Dash, JSON saved views, clean replacement):**
- `dashboard/workbench.py` + `dashboard/workbench_data.py` (route `/workbench`, "📈 Workbench" nav; `/charts` + `/explorer` are legacy routes landing there).
- **Search**: TV-style omnibox ("/" hotkey) over a unified index of all 321 plottable series — 188 signals, 35 composite scores, debt stress, 97 raw FRED cache series (titles from meta sidecars); all-token fuzzy match + country/force facet dropdowns; result rows show flag, label, force chip, span.
- **Charting**: overlay mode (one pane, right-side scale, minimap range slider) and stacked mode (pane-number per pill groups series into shared-X panes; the force-detail crosshair-sync JS reused). Per-series transform pills: Raw · Rebase=100 · % from start · YoY % · Z (stored) — window-anchored rebasing = TV "compare". Pan default, scroll zoom.
- **Inspector drawer** per series (🔍 on the pill): metadata + stats + Observations table with CSV export + Quality/Gaps + Raw-vs-Processed — the whole Data Explorer, docked. Reuses `explorer_data.py` (kept; UI archived as `archive/explorer_page.py`).
- **Saved views**: named layouts in `DATA_DIR/saved_views.json` (deliberately NOT signals.duckdb — dashboard readers + a writer would recreate the DuckDB lock conflict), 4 built-in ★ presets (US Inflation Stack, Policy Rates ×5, US Credit Conditions, The Two Dials), URL deep links `/workbench?view=name` verified live.
- **Retired**: chart-overlay layout + 4 callbacks + series-selector helpers excised from charting.py; `selected-series` store dropped; `date-range` store kept (many readers; None = full history as before). 8 old-UI tests removed; 14 new workbench tests.
- **Bonus fix**: the long-standing `test_compare_raw_vs_processed_level_signal` dtype failure (merge_asof `datetime64[us]` vs `[ns]`) — fixed in explorer_data; **the suite now runs 421 passed with ZERO exclusions** (first time since 2026-06).

**Verified live**: search → add US+JP 10Y, overlay + stacked with pane grouping, save "us vs jp 10y", deep-link reload restores the view.

---

## 2026-07-06 — Workbench: independent-axis overlay (TV multiple price scales)

**Ask:** overlaying series with very different magnitudes (US interest payments vs productivity) flattened the small one against zero on the shared axis.

**Done:** added an `axis: Shared | Independent` toggle to overlay mode (hidden in stacked). Independent puts each series on its own overlaying, auto-scaled y-axis (`yaxis`, `yaxis2`, …), hides tick labels (N scales can't share one label column), switches to `hovermode="x unified"` so the crosshair carries every value, and is a no-op with a single series. Persisted in `wb-config` and saved-view specs; the toggle hides itself in stacked mode via `wb_axis_sync`. 1 new test (`test_overlay_independent_axes`); suite 422 passed. Verified live: interest-payments vs productivity — productivity's COVID spike/collapse/recovery, invisible on the shared axis, is fully legible on independent.

---

## 2026-07-07 — Sovereign-aware debt-cycle stage classifier (Ray Dalio ruling)

**Trigger:** the interest-payments-vs-productivity chart made the sovereign squeeze visually obvious (interest at z=+4.00, pinned to the system Z-cap) — which surfaced a user challenge: the stage classifier reads the US as "reflation" while Ray's public position calls for a major deleveraging. The classifier's mean-of-3-sectors debt-stock feature was diluting a record government debt stock (122.8% GDP, z +1.78) against a genuinely deleveraged private sector (household debt/GDP 68.5%, z −1.54 — a multi-decade low). Same failure mode the G3 backtest flagged (2007 squeeze engaging late): squeeze conditions keyed to gauges that lag the real pressure.

**Consulted Ray** (full session in `ray_dalio_review_log.md`, Session 2026-07-06 (3)) — rulings: (1) two independent stage votes, PRIVATE and SOVEREIGN, headline = worse of the two by severity; (2) debt stock = size-weighted mean of sector percentiles, each sector capped at the 90th percentile ("worst-of without total dilution"); (3) debt-service blend = 70% household DSR / 30% government interest-to-GDP; (4) a refinancing-gap feature (marginal rate − effective rate on the government stock) triggers the sovereign vote's debt-service condition one quarter early once it exceeds +0.75pp; (5) keep the headline as "the mechanism currently operating" — do NOT force-flip it — and add a SEPARATE independent "Sovereign Squeeze" warning flag instead.

**Done:**
- `config/debt_cycle_stage.yaml`: new `sector_model` (cap, service weights, refi threshold, flag conditions, severity ranking) and `sovereign_inputs` (per-country gov debt/interest/revenue/marginal-yield signal bindings) sections, all TUNABLE.
- `indicators/debt_cycle_stage.py`: `_expanding_z_lagged()` (shift-1 expanding Z, no look-ahead), `_sector_stock()` (capped size-weighted percentile + trajectory), `build_sovereign_features()` (gov interest/GDP + Z + trend, gov DSR = interest/revenue + Z, refinancing gap), `_vote()` (shared scoring helper for either vote), reworked `compute_stage_history()`: builds private + sovereign feature frames, scores both, headline = worst-of by severity `{squeeze:3, deleveraging:2, reflation:1, leveraging:0}`, independent squeeze flag.
- `indicators/models.py` + `store/store.py`: `DebtCycleStageSnapshot` and the `debt_cycle_stage_snapshots` table gained `stage_private`, `stage_sovereign`, `sovereign_squeeze`, `feat_gov_interest_z`, `feat_refi_gap` (migration via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, safe on existing DBs).
- Re-ran the classifier for all 5 countries. **US: headline stays reflation (r−g −1.56pp, ngdp−yield +1.62pp are genuinely reflation-shaped — fiscal dominance operating right now) but SOVEREIGN SQUEEZE fires** (refinancing gap +1.81pp, gov-interest Z +1.43, both past threshold) — **and has been continuously True since 2022-Q2**, a multi-year early warning matching Ray's own public timeline, running underneath a headline that correctly still describes the current mechanism. Historical anchors preserved (2006/2009 squeeze episodes, etc). GB/EZ/JP/KR have no private-debt inputs, so headline = sovereign vote unchanged from before (GB stays squeeze) — no regression.
- Dashboard: Command Center Cycle Stage card gets an amber "SOVEREIGN SQUEEZE" badge (tooltip cites the ruling) + a private/sovereign sub-line when the two votes diverge; Debt Stress page info strip shows the same plus 2 new feature readouts (gov-interest Z, refinancing gap); Relative Cycles country cards append a ⚠ to the stage chip.
- 5 new tests (capped/size-weighted percentile via monkeypatched signal loader, expanding-Z no-lookahead, severity ordering, live US flag regression, live GB no-regression) — suite **427 passed, zero exclusions** (up from 422).
- Rebuilt the charting image only (NOT the pipeline — running the pipeline container while charting holds read-only connections was the incident two sessions ago; this session only ran the classifier from the host against the live DB with charting's connections already read-only, no conflict). Verified all three UI surfaces live for US and non-US countries.

**Design note carried forward:** the sovereign VOTE itself can read differently from the SQUEEZE FLAG (e.g. sovereign vote = "leveraging" this quarter while the flag is True) — this is intentional per Ray's Q5 ruling, not a bug: the vote scoring shares the country's macro conditions (r−g, ngdp−yield) across both votes by design, while the flag is built directly from independent thresholds specifically so it can fire ahead of the vote catching up.

---

## 2026-07-07 — China rollout (Phase 2 continuation — 6th economy live)

**Done:**
- `config/countries/cn_bindings.yaml` (32 signals, all endpoint-verified against FRED/WB/IMF/COFER before binding) + `config/countries/cn_composites.yaml` (6 force composites). **220 signals total** (73 US + 37 EZ + 27 GB + 25 JP + 26 KR + 32 CN). All 32 ingested clean: 0 empty, 0 errors, 0 sanity warnings.
- **The data-availability surprises (both directions), all logged in `data_source_wishlist.md`:**
  - **BIS credit is the star**: private (200.8% GDP), household (58.0%), corporate (142.8%) — quarterly, live. CN is the **second country after the US with a real private/sovereign two-vote split** in the stage classifier.
  - **WB external debt fills for China** ($2.42T) — first country in the system where `DT.DOD.DECT.CD` works (wishlist item partially closed).
  - **CNY COFER share confirmed** (1.99%, 2016-Q4→2026-Q1) — CN gets the same external-order read as the US.
  - **All OECD monthly activity feeds are dead** (IP → 2023, CLI → 2024-01, M2 → 2019, quarterly GDP → 2023-Q3, PPI → 2022). The live monthly growth reads are **merchandise exports/imports** (USD, → 2026-04), bound as the growth basket with LNY-noise caveats documented.
  - **No free bond yield at any maturity** — the 3m interbank rate (live) proxies the market rate everywhere, including both stage-classifier spreads (documented is_proxy).
  - Monthly CPI ages out 2025-04 (same OECD cutoff as KR/GB) → IMF annual bridge; no core CPI exists; unemployment is WB/ILO annual-only.
- Stage classifier: CN added to `debt_cycle_stage.yaml` (3 debt components + interbank-rate proxies) and `sovereign_inputs` (household+corporate private vote; no gov-interest series → SOVEREIGN SQUEEZE flag degrades honestly to never firing). **CN = leveraging on BOTH votes** (confidence 0.28, 4/5 features) — textbook: debt/GDP still rising, r−g deeply negative, ngdp above the short rate.
- Composites: 545 monthly snapshots. Latest (2026-05): Disinflationary Slowdown — Growth −0.68 / Inflation −0.77 (the 0.0% CPI deflation read pins inflation Z deeply negative — plausible and the defining China story right now). Growth flips month-to-month on trade YoY noise (documented; the Transition band + momentum gate absorb most of it). Force balance 0.78 OK; no CORR AUDIT flags.
- Spot-checks vs public references: BIS credit ratios, IMF gov debt 99.2%, FX reserves ~$3.4T, GDP $19.6T, FDI collapse to 0.23% GDP, population decline −0.17%, Gini 36.0, COFER 1.99% — all match.
- Dashboard: CN added to the country selector, Command Center/User Guide name maps, Relative Cycles `COUNTRIES`, Workbench facet + flags, Data Dashboard label map. Methodology §11 rollout table rewritten (was stale — still said "Japan next"); §15 revision-log row added (anchor-split pattern, verified 2 occurrences).
- 2 new tests (CN config integrity: 3-sector debt + interbank proxies + private-vote inputs; live CN two-vote regression pinned to leveraging) — suite **429 passed, zero exclusions**.
- Full pipeline run on host (charting stopped first, restarted after); docker images rebuilt; all 8 routes verified 200; CC/Relative/Guide render CN with live data.

**Next:** India is next in the Phase 2 order (expect the CN pattern: WB/IMF + FRED-mirrored feeds; check `DT.DOD.DECT.CD` early). Other open tails: D4 manual-load slots, ONS/e-Stat CPI registrations, the 2007-squeeze threshold tweak candidate.

---

## 2026-07-07 — India + Germany + Luxembourg rollouts (9 economies live)

**Ask:** India next per the Phase 2 order, plus Germany and Luxembourg by user request (both euro members — standalone codes alongside the EZ aggregate for core-vs-aggregate divergence reads).

**Done:**
- Three binding + composites file pairs, every series endpoint-verified first: **IN 32 signals / DE 29 / LU 27 — 308 signals total across 9 economies**. All clean (0 empty / 0 errors / 0 sanity warnings). Loader maps gained DE→DEU, LU→LUX (WB + IMF).
- **India is data-richer than China**: LIVE monthly IP (GYSAM form) + LIVE 10y gov yield (from 2011) + live quarterly real GDP + BIS 3-sector credit (2007→) + WB external debt fills ($716B, as predicted from CN). CPI dead 2025-03 → IMF bridge. INR not in COFER. Latest read: Expansion (G +2.76 / I −1.72); stage = reflation 0.38 (private vote leveraging, sovereign reflation — worst-of picks reflation correctly since leveraging is lower severity).
- **Germany is the richest non-US dataset in the system**: live monthly HICP (first bridge-free non-US country), live IP via the Eurostat JSON API (`geo=DE` — OECD FRED IP feeds died 2023/24), live retail/unemployment/Bund/3m interbank (first non-US 2-signal rate basket), BIS credit from 1970. Latest read: Stagflation (G −0.30 / I +0.39); **stage = deleveraging on BOTH votes at 0.44 — diverging sharply from the EZ aggregate's reflation, exactly the core-vs-aggregate contrast the standalone build was for.**
- **Luxembourg works but is structurally weird** (documented prominently in `lu_bindings.yaml` header + wishlist): BIS private credit 420% GDP (358.8% corporate = intra-group financing vehicles — read as a global credit-conditions gauge, quality_factor reduced), FDI ±100%+ GDP (sanity ±500/800), exports 190% GDP. Live HICP/unemployment/IP/10y. The growth composite under-reads LU because the financial sector (the real economy) has no free monthly gauge — LowCov flags honestly. Stage = reflation.
- **All three carry BIS household+corporate credit → all three run the private/sovereign two-vote stage split** (5 of 9 countries now: US/CN/IN/DE/LU). None has a gov-interest series → their SOVEREIGN SQUEEZE flags degrade honestly to never firing (CN pattern).
- Stage config: 3 new `countries` + `sovereign_inputs` entries (IN/DE/LU use real 10y yields in the spreads, unlike CN's interbank proxy).
- Dashboards: country selector (9 entries), CC/User Guide/Relative Cycles/Workbench/Data Dashboard maps all extended; Methodology §11 table updated (Brazil marked next) + §15 revision rows (anchor-split, verified 2 occurrences).
- Force balance: DE 1.20 / IN 1.03 OK; no CORR AUDIT flags on any new country. 4 new tests (config integrity for IN/DE/LU two-vote entries + live three-country two-vote regression); suite **431 passed, zero exclusions**.
- Spot-checks vs public references: DE Bund 3.05% / HICP ~2.2% / unemployment 3.8% / gov debt 62.9%; IN 10y 7.02% / growth 7.6% / gov debt 84.1%; LU credit 420% / gov debt 27% — all match.
- Docker rebuilt, all 8 routes 200, CC renders all three countries with live stage chips.

**Next:** Brazil is next in the original Phase 2 order (expect the IN pattern; check DT.DOD external debt early). Standing tails: D4 manual-loads, ONS/e-Stat CPI registrations, no free German core CPI (wishlist), 2007-squeeze threshold tweak.

---

## 2026-07-07 — D4: manual-load infrastructure (V-Dem governance + GPR)

**Ask:** build D4 — the last unbuilt piece of the big-cycle ORDER layer. V-Dem/Polity governance and the Caldara–Iacoviello GPR index publish no free API (bulk CSV/xls downloads only).

**Done:**
- **Drop-folder pattern**: `MANUAL_DATA_DIR` (default `DATA_DIR/manual_data/`, env-overridable, added to both docker-compose service blocks). `fetch_manual_series()` in `loader.py` reads per-signal `date,value` CSVs (bare years → year-end timestamps, ISO dates passthrough; case-insensitive headers). **Missing file = pending [SLOT]** (one INFO line, never an error); **present-but-malformed = loud ValueError**.
- **Pipeline Pass 3.8 (Manual-load series)**: new `provider: Manual` binding filter; `results["slot"]` counted separately — pending slots never fail a run; per-country and final summaries show "Pending slots: N" only when nonzero.
- **15 Manual bindings**: `order.governance` (V-Dem `v2x_libdem`, 0–1, annual) for US/CN/IN/DE/GB/JP/KR/LU; `order.geopolitical_risk` (GPR `GPRC_{ISO3}` share-of-articles, monthly since 1985) for the same set minus LU — **Luxembourg is not in the GPR country set** (honest gap, no binding). No EZ aggregate exists for either source.
- **Converter scripts**: `scripts/prepare_vdem.py` (V-Dem-CY-Core CSV → `vdem_{cc}.csv` × 8; 1900 start to keep expanding Z-scores sane) and `scripts/prepare_gpr.py` (`data_gpr_export.xls` → `gpr_{cc}.csv` × 7; needs `xlrd` for the legacy .xls — documented, not added to requirements since it's operator-side only).
- **Docs**: `docs/manual_data.md` (sources, download links, format spec, freshness expectations) — mirrored into the drop folder as its `README.md`. `us_bindings.yaml` deferred-comment block updated; the pre-existing `climate.disaster_loss` slot noted as the next candidate for the same pattern once EM-DAT access is sorted.
- **Command Center**: big-cycle card now shows V-Dem + GPR readouts when the files land, and names the *specific* pending slots ("governance/GPR pending manual load") until then — replaces the blanket "deferred" suffix. Also added CNY to the reserve-share currency label map.
- **Tests**: new `tests/test_manual_load.py` (9 tests — slot vs loud-failure semantics, year/ISO parsing, header case, config integrity incl. the LU-has-no-GPR rule).
- Roadmap D4 marked ✅; wishlist governance/GPR entries flipped to BUILT.

**Design note:** the "order score" composite stays deliberately unbuilt — premature until the manual drops are loaded and have survived a couple of refresh cycles (per the roadmap's validate-before-extend rationale).

**Next:** drop the two files (download V-Dem CY-Core + data_gpr_export.xls, run the converters, re-run the pipeline) — then the slots fill with no further code changes. Brazil remains next in the country order.

---

## 2026-07-07 — Digital Ray country-coverage consult + Brazil & commodity-hub rollouts (14 economies)

**Ask:** "Do Brazil and Switzerland. Also give Digital Ray our country list and see what input he has — too many, missing key players, etc."

**Ray consult** (digitalray.ai; full log in ray_dalio_review_log.md Session 2026-07-07): endorsed Brazil, flagged **Switzerland as marginal** for the order read, and flagged **Germany + Luxembourg as "borderline redundant"** with the EZ aggregate. His top missing economies, ranked: **1 Canada, 2 Australia, 3 Mexico, 4 Indonesia**, 5 Vietnam, 6 Turkey, 7 South Africa, 8 Saudi Arabia, 9 Russia, 10 Singapore — the signal being that the set was heavy on debt-cycle *pillars* and light on the *commodity-exporter / trade-hub* axis (he ranked the original spec's Saudi/Russia BELOW the commodity exporters). User chose "do the ones Ray suggested" → built Brazil + his top-4 commodity/trade hubs; dropped standalone Switzerland.

**Done — 5 rollouts (BR + CA/AU/MX/ID), 154 signals → 14 economies, 462 total:**
- 10 config files (5 bindings + 5 composites), every series endpoint-verified 2026-07-07; loader WB+IMF maps gained CA/AU/MX/ID. All clean (0 empty / 0 errors / 0 sanity warnings).
- **All 5 carry BIS 3-sector credit → all run the private/sovereign two-vote stage split** (9 of 14 countries now: US/CN/IN/DE/LU/BR/CA/AU/MX/ID... actually 10). Stage reads: **BR squeeze (0.62 — Selic ~21% real rates), CA squeeze (0.53 — 100% household debt), MX squeeze, AU leveraging, ID reflation.** None has a gov-interest series → SOVEREIGN SQUEEZE flags honestly never fire.
- Per-country data quirks (all in data_source_wishlist.md): BR uses the discount rate (Selic-linked) as the rate — no OECD bond yield exists; CA is the richest (live IP + 10y+3m + monthly unemployment); AU has **quarterly CPI** and no monthly IP (growth on unemployment+trade); MX has no IP and no live unemployment (trade-only growth); ID uses call-money rate (bond yield + discount rate both dead) and no IP. WB external debt fills for BR/MX/ID (EMs), null for CA/AU (high-income).
- Dashboards: all 14 countries in the selector, CC/Relative/Workbench/User Guide/Data Dashboard maps. Methodology §11 table + §15 revision row. 3 new tests (config integrity for the 5 + live two-vote regression); suite **442 passed, zero exclusions**.
- **Bug caught + fixed mid-build:** the YAML generator first emitted `transformation: yoy` (invalid) for master.gdp_real → all 5 GDP signals errored and starved the stage classifier ("insufficient features"). Fixed to `yoy_pct`, re-ran clean.

**Design note:** Germany/Luxembourg redundancy acknowledged by Ray but NOT reverted — they were an explicit user request for core-vs-aggregate divergence, and DE already diverged (deleveraging vs the aggregate's reflation). Switzerland dropped in favor of Ray's higher-value commodity picks.

**Next:** Ray's next tier (Vietnam, Turkey, South Africa, Saudi Arabia, Singapore; Russia hits the no-Rosstat constraint), or the standing tails (D4 manual drops, ONS/e-Stat CPI, no free German core CPI).

---

## 2026-07-09 — Daily auto-import scheduler + Settings menu audit/cleanup

**Ask:** run the data import daily at a time set in the dashboard Settings; also audit the (stale) Settings menu.

**Settings audit finding:** the three window sliders (Growth Z / Inflation Z / Disequilibrium) were DUPLICATED — present in both the always-visible left sidebar AND the Settings modal, kept mirrored by six sync callbacks. Classic organic-growth cruft. Per user's call: keep them in the sidebar, remove the duplicates from Settings. Also dropped the stale "re-run the pipeline to refresh" footer note.

**Scheduler (simple — automates the manual workflow):** the user rightly pushed back on my over-engineering (graceful-notice / staging-swap). The manual process already stops the dashboard during an import, so the auto-version just fires those same steps on a timer.
- `indicators/schedule_config.py` — file-based coordination (schedule.json / schedule_status.json / run_now.trigger in DATA_DIR); the dashboard and scheduler talk through files, never the single-writer DB. Atomic writes, validation, graceful fallbacks.
- `indicators/scheduler.py` — APScheduler daemon: reads schedule.json, fires a daily cron job at the set time (+ polls a run_now trigger), and the job = **stop the charting container → run the pipeline → start it** (the manual workflow). Uses the docker SDK via the mounted socket to bounce charting; degrades gracefully (skips the bounce, still imports) if docker is unavailable. Pipeline exit code isn't used for pass/fail (it exits 1 on the documented EZ current-account empty) — completion is "done".
- `docker-compose.yml` — new `scheduler` service (same image, `/var/run/docker.sock` mounted, `restart: unless-stopped`, `TZ` from .env). Starts with `docker compose up`. `requirements.txt` += `docker`; `.env.example` += TZ.
- **Settings → Data updates** section: enable toggle, time picker, timezone label, last-run/next-run status, "Save schedule", and "Update now" (writes the trigger). Opt-in (disabled by default) so the user sets their own time.

**Verified live:** built all images; scheduler service comes up, finds the running `indicators_machine-charting-1` container via the socket, detects a schedule.json change on its poll, schedules the daily job, and computed next run = 2026-07-10 03:00 America/Chicago; status file written; reset to disabled (opt-in). Settings modal renders the new controls; the duplicate sliders + stale note are gone. 9 new tests (`tests/test_scheduler.py`); suite **451 passed, zero exclusions**.

**To use:** Settings → Data updates → toggle on, pick a time, Save. (Timezone via TZ in .env, default America/Chicago.)

---

## 2026-07-09 — Public/read-only mode for untrusted multi-viewer deploys + rebrand

**Rebrand:** repo renamed on GitHub to `economic-machine-dashboard` (auto-redirect keeps old links working); app tab title → "Economic Machine Dashboard", sidebar brand → "Economic Machine". Package + locked `indicators_machine` paths unchanged. Repo is now PUBLIC.

**Public mode (`PUBLIC_MODE=1`):** hardens the dashboard for an untrusted public/cloud audience. The concern: most settings are per-browser (localStorage — theme, country, windows, thresholds → each viewer independent, no collision), but three surfaces write SHARED server-side state and would let any visitor affect everyone: (1) the Data-updates scheduler (esp. "Update now" → restarts the app for all), (2) Weight Audit/History (importance editor writes YAML + the DB), (3) Workbench save/delete views (shared saved_views.json).
- `dashboard/app_mode.py`: `PUBLIC_MODE` flag + `OPERATOR_ONLY_ROUTES`.
- In public mode: Settings Data-updates section replaced by a read-only "refreshes automatically" note (scheduler callbacks not registered); Weight Audit/History nav links hidden + routes return an "operator tool" notice (blocks direct-URL access); Workbench save/delete/name controls hidden (load dropdown kept) + the save callback no-ops.
- No defaults needed — hidden controls keep their existing config-driven values. For the scheduler specifically, added env-var config so a headless/cloud operator can set the daily import without the UI: `AUTO_IMPORT_ENABLED` / `AUTO_IMPORT_TIME` override schedule.json in `load_schedule()`.
- docker-compose: `PUBLIC_MODE` on charting, `AUTO_IMPORT_*` on scheduler (all default off/empty → local single-operator experience unchanged).
- 5 new tests (env overrides, invalid-time ignore, flag parsing); suite **454 passed, zero exclusions**. Verified both modes render correctly; normal mode still serves all routes with write controls present.

---

## 2026-07-09 — Dynamic thresholds ON by default + self-contained traffic metrics

**Dynamic thresholds default-on:** Ray's dynamic regime thresholds (his 7-step algorithm) now default ON — `_DEFAULT_THRESHOLDS["dynamic"]=True`, the `regime-threshold-store` initial data carries `dynamic:True`, and all 6 `.get("dynamic", …)` read-sites default True (so keyless/older stored dicts flip on too). An explicit user "off" (stored dynamic:False) is still respected; the Regime Thresholds modal checkbox syncs from the store. Backtest G2 found dynamic ≥ fixed, so this is defensible.

**Traffic metrics (`dashboard/traffic.py`, `/traffic`):** no third-party tracker. Every real page view (the route_page callback) is appended one JSON line to `DATA_DIR/traffic.log` (append-only, concurrency-safe, never the DB); the /traffic page aggregates total views, unique visitors (per-tab sessionStorage id), views today/7d, a 30-day per-day bar chart (HTML bars, theme-adaptive), and top pages. Assets/framework/self requests are skipped. Access: if `TRAFFIC_KEY` is set, `/traffic` requires `?key=…` (works on a public deploy — operator bookmarks the keyed URL, no nav link); with no key on a non-public instance it's open + sidebar-linked. docker-compose exposes `TRAFFIC_KEY`. 7 new tests. Verified end-to-end with a real browser (recorded views, unique visitors, top paths). Suite **461 passed, zero exclusions**.

---

## 2026-07-09 (2) — Traffic: region breakdown + mobile-friendly layout

**Region breakdown (privacy-preserving):** `/traffic` now shows a **Top regions** table derived from the visitor's browser IANA timezone (e.g. `Europe/London`) — captured client-side into a `tz-region` localStorage store and passed to `record_hit(path, session, tz)` (new `z` field on each log line). **No IP address, no geolocation** — a coarse region hint only, with an in-page note saying so. We chose this over a third-party tracker (e.g. Google Analytics) deliberately: GA would give city-level location but sends visitor data to Google and needs a cookie-consent banner in the EU, which cuts against the "no black box" framing. `read_metrics()` gains `top_regions`; layout renders pages + regions side-by-side. 1 new test (`test_region_aggregation`).

**Mobile-friendly:** the app was desktop-only — **no viewport meta tag** (so phones fake-rendered at ~980px and shrank everything) and **zero `@media` queries**. Added (1) the viewport meta tag to the Dash constructor, and (2) a `@media (max-width: 768px)` block in `theme.css` that forces the 195px sidebar down to its 46px icon rail, tightens page gutters, lets over-wide tables/flex-rows scroll/wrap instead of bursting the layout. Verified with a 390px headless render: Command Center cards stack full-width and readable, sidebar is a clean icon rail, /traffic cards + bar chart + tables all fit. A full off-canvas drawer nav is a possible future polish, but the rail is usable now. Suite **462 passed**.

---

## 2026-07-09 (3) — Public cloud deploy (Hugging Face Spaces, free)

Prepared a free, no-credit-card public deploy on Hugging Face Spaces (Docker
SDK). Key findings + artifacts:

- **DB was 2.3 GB of DuckDB bloat** (only 285K rows across 5 tables). A fresh
  copy-into-new-file compaction drops it to **67 MB** — makes baking data into
  an image trivial. `scripts/build_public_bundle.py` reproduces this: compacts
  the DB + tars it with raw_cache/snapshots into `emd_data.tar.gz` (~27 MB).
- **`deploy/hf/`**: `Dockerfile` (clones the public GitHub repo at build,
  installs deps, extracts the data bundle, runs gunicorn on 7860, `PUBLIC_MODE=1`),
  `README.md` (HF Space metadata — `sdk: docker`, `app_port: 7860`), and
  `DEPLOY.md` (5-min click-path: create Space → upload 3 files → optional
  `TRAFFIC_KEY` secret → live). The Space holds only Dockerfile + README + data
  bundle; code comes from GitHub so rebuilds auto-pick-up main.
- **gunicorn** added to requirements. Verified end-to-end: built the exact
  image, ran it on :7860 under gunicorn, headless-rendered the Command Center
  off the baked-in compacted DB — full live data, DYNAMIC badge, SOVEREIGN
  SQUEEZE flag, and operator-only nav (Weight Audit/History) correctly hidden
  in public mode. Data bundle is not committed (binary — uploaded to the Space).

---

## 2026-07-09 (4) — UI cleanup: nav tooltips, Overview names + Rate coverage

Three requested tweaks:
- **Removed the hover popup labels on the left nav** (all `dbc.Tooltip`s on the
  nav links + Settings). The icon rail no longer shows tooltips.
- **Overview spells out every country** — added Luxembourg/Australia/Mexico/
  Indonesia to `_COUNTRY_NAMES` (they were rendering as LU/AU/MX/ID codes) and
  refreshed `_COUNTRY_ORDER` to the real 14-country rollout order.
- **Overview Rate column now fills for all 14 countries.** It was hardcoded to
  `policy.fed_funds_target` (US-only). Added a per-country fallback —
  policy rate → 3-month interbank → 10-year gov-bond yield — so each country
  shows its best-available rate, with the actual instrument named on hover
  (`_RATE_CONCEPT_LABELS`). e.g. US/EZ policy rate, CN/DE/CA/AU/MX interbank,
  GB/JP/KR/IN/LU 10y yield, BR Selic 21.3%.

88 charting tests pass.

- **CHI now computes for all 14 countries** (follow-up to the Rate fix). The
  Cycle Health Index read the policy rate ONLY from `policy.fed_funds_target`
  and inflation ONLY from `inflation.cpi_headline`, so it returned None for
  every country lacking the US-shaped signals — the Overview CHI/Stage columns
  were blank for all but US/EZ. Applied the same per-country fallbacks
  (`_RATE_CONCEPTS`, `_INFLATION_CONCEPTS`) to `_cycle_health` and
  `_cycle_health_history`; Japan's inflation now bridges to the annual IMF
  estimate. Result: CHI raw / debt-adjusted / Stage fill for all 14. Instrument
  named on hover for both Rate and Inflation fallback cells.

---

## 2026-07-09 (5) — Data Confidence score/badge (per-country + per-force)

New `dashboard/data_score.py`: grades how trustworthy each country's reads are
from three signal properties we already track — freshness (`is_stale` + age,
graded so a normal lag ≠ an abandoned feed), directness (`is_proxy` /
`is_constructed`), and depth (# signals in the basket, with thin baskets capped:
1 signal ≤ C, 2 ≤ B). Per scored force (growth/inflation/rate/credit) → 0–100 →
A/B/C/D; overall = weighted avg (growth+inflation heaviest). Live spread: US/EZ
A, most others C, richer EMs B — honest.

Surfaced:
- **Overview**: colored A–D chip after each country name + legend note (hover =
  per-force breakdown).
- **Command Center**: a "Data <grade>" header chip, and — the key ask — a
  per-force caveat on the Growth/Inflation cards (e.g. Indonesia growth reads
  "C · data · 5 signals · 4 stale, 2 proxy", so the stale-growth story is
  visible right next to the number). 6 new tests; suite 468 passed.

---

## 2026-07-09 (6) — Data-quality drive: UK CPI live via ONS (C-country push)

Started the concerted C-country data-improvement effort (UK/JP/KR/CN/IN/LU/ID)
from the punch-list in `docs/Guidance/signal_sourcing_guide.md`. First win: UK.

- **New `fetch_ons_series()`** in `loader.py` — the UK ONS "append-/data" JSON
  API (free, unregistered). Topic-agnostic: series_id is `CDID/DATASET` and the
  fetcher walks the ONS economic topic paths until one resolves (or takes an
  explicit `topic/CDID/DATASET`). Pipeline **Pass 1.7** (provider `ONS`).
- **UK CPI repointed** from the dead OECD-on-FRED mirror (`CPALTT01GBM659N`,
  ended 2025-03) to ONS `d7g7/mm23` — **live to 2026-05 = 2.8%**, exact match to
  the published rate. GB **inflation force C→B**; overall 66→70.
- Verified end-to-end (rebuilt the pipeline image — it bakes code, so it needed
  rebuilding too; ran the full pipeline). 2 new ONS tests.

**Roadmap (rest of the C countries):** free/unregistered next → UK retail+IP+
unemployment via the same ONS fetcher (de-stale GB growth → likely B); India
MOSPI, Indonesia BPS/BI, Brazil BCB (verify). Registration-gated (operator key
needed) → Japan e-Stat (worst CPI staleness), Korea BoK ECOS. Hard/none → China
bond yield, Luxembourg (structural).

- **UK growth also moved to ONS** (retail `j5ek/drsi`, IP `k222/diop`,
  unemployment `mgsx/lms`; index series → yoy_pct, rate → level). Retail flipped
  fresh, IP/unemployment fresher. **GB growth C→B; GB overall C→B (73).** First
  C-country fully upgraded on free/unregistered data. `_fetch_ons_from_api` made
  topic-agnostic (walks ONS economic topic paths).

---

## 2026-07-10 — Japan CPI live via e-Stat (C-country push, key-gated win)

Operator supplied a free e-Stat appId (stored in git-ignored `.env` as
`ESTAT_APP_ID`). Wired Japan's live monthly CPI in — the worst-staleness gap in
the dashboard (JP inflation had been an IMF *annual* bridge since 2021).

- **New `fetch_estat_series()`** (loader) — Japan e-Stat getStatsData REST API.
  series_id = `statsDataId/cdTab/cdCat01/cdArea`. Reads `ESTAT_APP_ID`; returns
  None (graceful skip → IMF bridge) if the key is absent. Pipeline **Pass 1.8**
  (provider `eStat`).
- **JP `inflation.cpi_headline`** = e-Stat `0003427113/1/0001/00000` (CPI
  2020-base index, all-items 総合, national 全国) → yoy_pct. **Live to 2026-05,
  linked to 1970**, YoY 1.52%. Added as PRIMARY in `jp_composites.yaml`; the IMF
  annual bridge demoted to keyless backup.
- **Result: JP inflation C→B, JP overall C→B (71).** Second C-country upgraded.
  4 new tests (ONS+e-Stat parse + guarded live). Note: the appId lives only in
  `.env` (gitignored) and the baked DB snapshot — never committed.

Discovered + documented the e-Stat login-loop fix: the appId is issued from
**My Page → API function** (`/en/mypage/view/api`), NOT the `/api/` portal
(separate auth realm that loops).

**C-country scorecard:** UK ✅ B, Japan ✅ B. Remaining C: Korea (BoK key
pending), China (no free bond yield), India/Indonesia (free national sources
to verify), Luxembourg (structural).

---

## 2026-07-10 (2) — Brazil on the open BCB API (C-country drive continues)

Fully autonomous win (no key). New `fetch_bcb_series()` (loader) — the Banco
Central do Brasil SGS time-series API, open/unauthenticated. series_id = numeric
SGS code. Pipeline **Pass 1.9** (provider `BCB`). Repointed 3 BR signals off
dead/proxy feeds to live BCB:
- `inflation.cpi_headline` → IPCA 12m (`13522`), live to 2026-06 = 4.64% —
  replaces the dead OECD-on-FRED mirror. **BR inflation C→B.**
- `growth.unemployment` → PNAD monthly (`24369`), live to 2026-05 — replaces
  the WB annual ILO proxy (de-proxied).
- `policy.rate_policy` → Selic annualized (`4189`) — the real COPOM lever,
  replacing the FRED discount-rate proxy.

**BR overall B 71 → B 77.** 2 new tests. Brazil still can't reach the top tier
on policy (no free BR 10y yield → single rate signal) but the underlying data is
now live/native across inflation, labour and the policy rate.

**C-drive tally:** UK ✅B, Japan ✅B, Brazil ✅B(77, strengthened). Korea ⛔
(Korean ID-verification wall). Next free-but-keyed: India (data.gov.in — easy
email key, no ID check), Indonesia (BPS — key). China/Luxembourg structural.

---

## 2026-07-10 (3) — Indonesia CPI live via BPS WebAPI (4th C-country upgraded)

Operator supplied a free BPS key (git-ignored `.env` as `BPS_KEY`; the BPS
"login loop" was a false alarm — the app/key ARE created, the portal just
redirects to the account page after Generate Key). New `fetch_bps_series()`
(loader) — Indonesia BPS WebAPI. Non-trivial: the data endpoint needs internal
th_ids (year-1900), the national row is vervar label "INDONESIA", and the
datacontent key = vervar+var+turvar+th_id+turtahun. CPI is fragmented by
COICOP group and rebased (2012→2018→2022); the live general index is var **2245**
(CPI 150-regency, 2022=100). Pipeline **Pass 1.10** (provider `BPS`).

`inflation.cpi_headline` → BPS 2245 (yoy_pct), live to 2026-06 = 3.3% (short
history from 2024). **ID inflation C→B, overall C 68 → B 73.** 2 new tests.

**Final C-drive scorecard:** UK ✅B, Japan ✅B, Brazil ✅B(77), Indonesia ✅B(73).
Blocked by national-ID SSO (resident-only): Korea (본인인증), India (JanParichay).
Structural (no free source): China (no bond yield), Luxembourg (financial-centre).

---

## 2026-07-10 (4) — Schedule-aware composite decay (Digital Ray consult)

Consulted Digital Ray on the age-decay methodology (logged in
`ray_dalio_review_log.md`). Finding: the dashboard had THREE decay mechanisms
with inconsistent philosophies — `is_stale` (release-aware, 200d/Q) and the
debt-stress module (excess-lag-aware) both matched "release-schedule-aware",
but the growth/inflation composite decayed on RAW fill-age (pure recency),
silently down-weighting a quarterly reading (e.g. GDP) mid-quarter even though
it was the freshest data available.

Ray's ruling: "recency PLUS schedule awareness" — the schedule-aware hold
belongs to LOW-frequency signals (a monthly series' natural cadence already
does the job), and high-frequency "bridges" carry the gap while the coarse
quarterly signal stays the reliable anchor. We already satisfy the bridge point
(growth basket ≈9 signals; GDP is one input the monthlies outnumber).

Implemented: `time_decay.release_grace_months` (TUNABLE D0/M1/Q4/A14) in
`composites_policy.yaml`; `compute_composite_history` now decays on
`max(0, fill_age − grace[freq])` (via the already-threaded `freq_map`). A
quarterly signal keeps full weight through its release window and only decays
once genuinely overdue — aligning the composite with the other two mechanisms.
US/EZ regime reads unchanged/sane; recomputed all 8,264 composite snapshots.

Related observation (NOT changed here): JP growth reads None in recent months
because ALL its growth signals are `is_stale`-EXCLUDED (real data ends ~April,
now July). That's the is_stale *hard exclusion* — a stronger form of the same
recency-vs-schedule tension. Extending the grace concept to the exclusion is a
candidate follow-up, but JP's ~3-month lag is genuine, so left as-is.

---

## 2026-07-10 (5) — Fed Monitor dashboard (/fed) — Digital Ray consult

New US Federal Reserve monitoring page built from a two-part Digital Ray consult
(logged in ray_dalio_review_log.md). Five sections in Ray's framing: short-term
cycle, rates-vs-inflation, balance-sheet/liquidity, turning points, and — the
*How Countries Go Broke* heart — late-cycle monetization (MP1→MP2→MP3).

- **7 new `fed.*` FRED series** in us_bindings (TOTRESNS reserves, RRPONTSYD ON
  RRP, T5YIFR 5y5y fwd, TREAST Fed Tsy holdings, MVMTD marketable debt,
  RESPPLLOPNWW remittances, FDHBFIN foreign holdings) — isolated `force: fed`
  so they feed the page only, NOT the composites or data-score. Verified 4 of
  Ray's AI-supplied FRED IDs were WRONG and corrected them before binding.
- **`dashboard/fed_monitor.py`** — 5 sections of mini time-series charts +
  current value + Ray's thresholds; header strip (easy/tight, behind/ahead,
  Fed-share-of-debt, MP-phase). Computes Fed share, foreign share, reserves/GDP,
  federal interest÷revenue inline. Route `/fed`, nav "🏛 Fed Monitor".
- Live reads confirm the thesis: ON RRP ~$0.5B, remittances −$235B, Fed share
  15.5%, foreign share 55%→32%, interest÷revenue 16.5% (danger zone). 3 tests.

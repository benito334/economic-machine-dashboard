# Worklog — Indicators Machine

Log entries are newest-first. Each entry: date, what was done, what is next, any blockers.

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

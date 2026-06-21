# Worklog — Indicators Machine

Log entries are newest-first. Each entry: date, what was done, what is next, any blockers.

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

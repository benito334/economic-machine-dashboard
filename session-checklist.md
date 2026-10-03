# Session Checklist

## At session start
1. Read `CLAUDE.md`
2. Read last 3 entries of `docs/worklog.md`
3. Check this file for pending items

## At session end
1. Add worklog entry
2. Update this file
3. Update memory if key facts changed

---

## Pending / Blockers

### Dashboard IA/color cleanup — Phase 1+2 done, Phase 3-5 open (2026-10-03)
Nav regroup + color-palette consolidation shipped (`docs/worklog.md` 2026-10-03; full plan in that session's "Dashboard IA Blueprint" artifact). Still open: Phase 3 (promote Fed Monitor's `_chart_card` into `shared_components.py` as a public component), Phase 4 (retrofit the Signals pages to that card style — this is the "signal graphs look crude" fix), Phase 5 (retrofit Regime & Cycles + Overview/Relative Cycles charts). Standing placement framework for new pages: `docs/Guidance/dashboard_ia_framework.md`.

### Dalio Framework Coverage Audit — all 4 High items shipped (2026-10-03)
From the "Dalio Framework Coverage Audit" artifact's own prioritization table — #1 (Short-Term Health × Long-Term Stress combined view), #3 (Debt-Stress rollout to 12 countries), #4 (foreign-vs-domestic-currency debt split, BR/MX/ID via IMF IIPCC), #5 (Central Bank Monitor, US/EZ/JP) — all done, see `docs/worklog.md` 2026-10-03 entries 2-5 for full detail on each. Medium/Low items from the same audit (FX reserve runway, P/E ratio, military expenditure, probabilistic regime confidence, momentum-gate magnitude, room-to-ease gauge, rate-basket correlation check, internal-order stage, relative power index, bubble gauges) remain open for a future session.

**Confirmed gaps from this work** (not retried without new sourcing): GB has no live central-bank-balance-sheet source (every FRED BOE series discontinued/years-stale). EZ has no Debt-Stress model (not BIS-covered for debt-service AND missing `fiscal.primary_balance_gdp`). India/China have zero coverage in IMF's currency-composition (IIPCC) dataflow, so the FX-debt-share split is BR/MX/ID only, not project_plan.md §6.4's full original target list.

### Remaining coverage-audit items — free-source build plan (2026-10-03, in progress)
Everything left from the audit, triaged by whether it's buildable without a paid source. Sequence below; placement follows `docs/Guidance/dashboard_ia_framework.md`. See `docs/worklog.md` for research/verification detail on each as it lands.

**Phase A — mechanical, zero/near-zero new data:**
1. ✅ **DONE** — **Government interest payments** — IMF `GFS_SOO` (`G24_T`/`POGDP_PT`, direct %GDP). Real coverage: GB/JP/KR/CN/DE/LU/BR/CA/AU/MX/ID have data; India's rows are all `OBS_VALUE`-empty (confirmed gap, not covered despite initial miscount); EZ still has none. Of those, `ffill_limit_quarters` (5→10Q) fix was also needed for the carry-forward to actually reach the latest quarter — AU/MX/ID/CN's data is still too stale (11-20Q) even at 10Q, left as an honest gap. **South Korea's Sovereign Squeeze fired for the first time ever** as a result. See `docs/worklog.md` 2026-10-03 (6).
2. **FX reserve runway** (import-cover months) — zero new sourcing, `capital.fx_reserves_yoy` ÷ existing import series, CN/IN/ID/BR. → Regime & Cycles (new stage-classifier feature + badge, same pattern as `fx_debt_share_flag`).
3. **Room-to-ease gauge** (distance of policy rate from zero/ELB) — zero new sourcing, derived from existing policy-rate signals. → Central Bank Monitor (Monitors group) — US/EZ/JP already have policy-rate data there.
4. **Military expenditure % GDP** — new World Bank binding (`MS.MIL.XPND.GD.ZS`), same pattern as existing Gini/demographics. → Big-cycle position card + Relative Cycles Order line (same convention as Gini/COFER).
5. **Momentum gate: magnitude not sign** — classifier's `gm`/`im` momentum gates default to 0.0 (pure sign test); test a small nonzero default against a backtest comparison. → parameter change on the existing Regime Thresholds classifier, no new UI.
6. **Rate-basket correlation check** — due diligence only: confirm nominal-10Y isn't double-counting the inflation premium against the US composite's configured weights. → Weight Audit, possible reweight.

**Phase B — combines existing signals, more design judgment:**
7. **"Pushing on a string" QE-effectiveness flag** — MP2 balance-sheet growth (now live via Central Bank Monitor) + `credit.private_credit_creation` (live via Case Study Monitor) cross-check. → Case Study Monitor's credit-creation section.
8. **Probabilistic regime confidence** — assign a regime label only above ~70% historical-frequency confidence, else "uncertain"; a complement to (not replacement for) the existing dynamic thresholds. → Command Center header / Regime Map, alongside the existing Chip Direction Agreement stat.

**Phase C — needs a scoping pass before committing to a build:**
9. **Bubble gauges** — audit's own instruction: scope which of the 6 dimensions are realistically free-buildable before building any. Check: (a) `indicators/valuations.py`'s existing Buffett Indicator (market-cap/GDP) — already built, operator-only, never connected to this effort; (b) FINRA's free margin-debt statistics for the "leverage-financed buying" dimension. The other 4 dimensions (new/unsophisticated buyers, uniform bullish sentiment, extended forward purchases) likely have no free data at all — confirm or drop each explicitly rather than leaving them silently unaddressed.

**Confirmed NOT buildable free (drop, don't retry without new information):**
- P/E Ratio (Shiller CAPE) — file checked live 2026-10-03, stopped updating Sept 2024.
- Daily equity index for EZ/KR — no FRED series exists; stays on the monthly proxy.
- Cross-border Global Liquidity Impulse (`project_plan.md` §6.5) — PBOC has no free live balance-sheet series (checked live); recommend an explicit drop decision rather than shipping a misleading 3-of-4 "global" sum missing China.
- Dollar-dominance factors 3-5 (FX turnover, SWIFT, trade invoicing) — already confirmed no free API in the 2026-08-21 session, not re-investigated.

**Blocked on the user, not something to attempt solo:**
- V-Dem governance + GPR geopolitical-risk — manual-load pipeline fully built (`docs/manual_data.md`), just needs the operator to download 2 files (v-dem.net CY-Core, matteoiacoviello.com GPR xls) and drop them in `manual_data/`. Also unblocks the Internal-Order stage classifier below.

**Deferred — real architectural lift, not a quick add, flagged for a dedicated future session:**
- Internal-order stage classifier (blocked on V-Dem/GPR above, plus genuine design work).
- Relative power index / world-trade-share (needs a cross-country aggregation layer — world totals as denominators — the per-country binding model doesn't support today).

### Stale signal-count test assertion (pre-existing, not from this session's nav/color work)
`tests/test_explorer.py::test_load_signal_overview_returns_all_signals` hardcodes an expected signal count (currently asserts 91; live count is 105 after this session's earlier `growth.output_gap`/`credit.*`/etc. additions). Bump the assertion to match `len(load_signal_overview())` the next time signals are touched.

### BEA data refresh — partially resolved 2026-07-05
`debt_service_ratio` picked up Q1 2026 during the 2026-07-05 pipeline runs. `current_account` and `NIIP` are still stale (BEA hasn't published). Re-run `python3 -m indicators.pipeline` when it lands.

### Pre-existing test failure (unrelated, tracked)
`tests/test_explorer.py::test_compare_raw_vs_processed_level_signal` — pandas datetime-unit mismatch (`M8[us]` vs `M8[ns]`) in `dashboard/explorer_data.py::compare_raw_vs_processed` `merge_asof`. Reproduces on main before all 2026-07-05 work. Fix: normalize both sides to `datetime64[ns]` before the merge. (A spun-off fix session was started then deleted — still open.)

### Roadmap position (see docs/Guidance/ray_framework_roadmap.md)
**ALL major roadmap phases complete as of 2026-07-06** (A, B, CC, C, D spike+subset, E, F Japan, G1–G3) plus the UK rollout, the Ray unification audit (canonical 48m/90m windows everywhere, threshold-aware season backdrop, Chip Direction Agreement), and the User Guide (/guide). Open tails, rough priority: **China rollout** (Phase 2 order; WB/IMF harmonized only — NBS out of scope), **D4** (manual-load infrastructure for V-Dem/Polity governance + GPR index), ONS (free, unregistered) for live GB monthly CPI + e-Stat registration for JP, rate-basket rolling variants (for Ray's 36m policy window default), the 2007-squeeze stage-threshold tweak candidate (needs more episodes), stored 4-season `quadrant` column retirement decision.

### EA current account — accepted gap
All free API sources exhausted (WB, ECB, FRED, Eurostat, IMF). See `docs/Guidance/EU_singals_guidance.md` for full investigation table. Resolution requires ECB Data License or manual Eurostat bulk download. Accept gap for now — Global Overview shows dash for EZ current account column.

---

## Completed 2026-07-05/06 — roadmap finished (CC, C, D, E, F, G3) + UK + audit + User Guide
Full detail in `docs/worklog.md` (nine entries) and the review log. One-line version: Command Center default landing page; debt-cycle stage classifier (US/EZ/JP reflation, KR leveraging, GB squeeze); order lens (Gini + COFER via the new IMF SDMX API); Relative Cycles page with 5×5 correlation matrices; Japan (25 signals, daily-Nikkei vol, IMF-bridge inflation) + UK (27 signals) rollouts — 188 signals across 5 countries; G3 ALFRED vintage replay (direction validation survives; A1 closed: rate_expectations keeps CONTEXT 0.45; dynamic stays opt-in); Ray unification audit (per-country rolling columns — were US-only, canonical 48m/90m defaults, seasons as threshold-aware backdrop, Chip Direction Agreement, dynamic thresholds re-paired with windows + time-stepping map band); 9-lesson User Guide with Ray pedagogy pass. 455 tests pass.

## Completed 2026-07-05 — Ray review + roadmap phases A/B/G1-G2
Full detail in `docs/worklog.md` (five entries dated 2026-07-05) and `docs/Guidance/ray_dalio_review_log.md`. One-line version: systematic Ray Dalio AI review → 24-item punch list → all implemented or explicitly deferred; roadmap created (`ray_framework_roadmap.md`); Phases A (loan_demand, rate_expectations), B (productivity_score composite + /signals/productivity), G1+G2 (PIT backtest engine, direction validation passed, dynamic ≥ fixed) shipped; dynamic-threshold checkbox UX fixed (applies on click); Methodology page fully revised + Revision Log section added.

---

## Completed 2026-06-24 — session 2
- **Regime Classifier blank graphs fixed**: `_placeholder_fig()` set on all three `dcc.Graph` components; chart callbacks return placeholder instead of `PreventUpdate` when store empty
- **Guidance docs reorganised**: consumed files moved to `docs/Guidance/Used/`; `Backtesting_Indicator_imporvements.md` is the active Phase 3 planning doc

## Completed 2026-06-24 — session 1
- **Monte Carlo blank graphs fixed**: `titlefont` deprecated in Plotly v5 → `title={"text":..., "font":{...}}` in `_mc_scatter` (both axes) and force balance bar chart Y-axis
- **Importance Editor copy button**: `dcc.Clipboard` top-right of Section 4; TSV callback auto-updates on any table change

## Completed this session (2026-06-23) — session 2
- **Weight Audit blank graphs fixed**: split `update_layout()` calls to avoid duplicate `margin` kwarg; `_hex_alpha()` helper converts 8-digit hex to `rgba()` for Plotly compatibility
- **Re-run button**: `wa-run-store` dcc.Store; clicking ↺ Re-run re-triggers all three audit panels on demand
- **Importance Editor (Weight Audit Section 4)**: inline editable DataTable for all signals; live G/I ratio preview; reason field; saves to YAML + `weight_change_log` DuckDB table
- **GDP-Regression Calibration (Weight Audit Section 5)**: `indicators/calibrate.py`; OLS each growth signal against `{cc}.master.gdp_real`; positive betas scaled to [0.10, 0.95]; β≤0 → no recommendation; "Apply Selected" populates editor
- **weight_change_log table**: DDL + `log_weight_changes()` / `query_weight_change_log()` / `update_weight_change_reason()` in `store/store.py`
- **Weight History page** (`/weight-history`): `dashboard/weight_history.py`; table + editable Reason column + Save Notes; wired into charting.py nav + `_PAGE_MAP`
- **Methodology Section 12 expanded**: importance tier table, GDP regression methodology, importance editor docs, weight history docs; deferred table updated (OLS calibration now live)
- **CLAUDE.md + worklog.md + session-checklist.md updated**

## Completed this session (2026-06-23) — session 1
- **Data Explorer country-awareness**: all 6 callbacks wired to `country-store`; signal table resets on country switch
- **ECB SDW fetcher**: `fetch_ecb_series()` in `loader.py`; Pass 1.6 in `pipeline.py`; `"FLOW/KEY"` series_id format
- **7 new EZ bindings**: employment growth, construction prod, capacity util (Eurostat); BTP-Bund spread via ECB IRS; fiscal budget balance (Eurostat quarterly); HICP energy + food sources corrected to FRED index series (monthly through current)
- **EZ composites**: growth 3→6, inflation 4→6; latest Inflationary Boom 58% conf
- **EZ Global Overview**: `ez.master.gdp_level_bn` (WB `NY.GDP.MKTP.CD`, 16,485B USD 2024) + `ez.credit.gov_debt_gdp` (Eurostat `gov_10dd_edpt1`, 87.8% 2025) now live
- **Regime History + Global Overview signal counts fixed**: dynamic from composites engine
- **Guidance doc updated**: `docs/Guidance/EU_singals_guidance.md` — all signals reviewed; CA investigation table added; HICP energy/food source correction noted
- **EZ: 34 signals live** (was 19); **353 tests pass**; Docker rebuilt

## Completed 2026-06-24 — session 3
- **Signals page** (`/signals`) live: 5-force breakdown (Growth/Inflation/Rate/Credit/Volatility), per-section composite Z + momentum header, force tables matching Regime Map; `dashboard/shared_components.py` extracted for reuse.
- 353/353 tests pass; Docker rebuilt.

## Completed 2026-06-25

- **Debt stress repairs**: FYFSD+FYOINT+FGRECPT FRED-derived replacements for dropped IMF `primary_balance_gdp` + WB `govt_revenue_gdp`; 7/7 components active (was 5/7); `us.fiscal.govt_receipts_qtr` added to `us_bindings.yaml`
- **Debt stress semantic colors**: `_stress_z_color()` — red shades = stress-increasing, green = stress-reducing
- **Signal drill-down modal** (Option A): click any signal name across all tables (lens, Force Components, Debt Stress, Signals page) → dual-panel chart (computed value + Z-score). Pattern-matching `{"type": "signal-link"}` callback + `signal-drill-id` store.
- **3rd panel raw data**: for FRED `yoy_pct` signals, drill chart adds row 3 = raw underlying level from parquet cache. `_load_signal_binding()` + `_load_raw_cache_series()` in `charting.py`.
- **Shared vertical hover spike**: clientside callback on `signal-drill-chart` figure mirrors the regime history implementation; SVG line spans all subplot y-extents on hover.
- **Signal info popup** (ⓘ icon): `_signal_info_icon()` in `shared_components.py` added to all Signals page rows. Click → `signal-info-modal` with description, units (transformed + raw FRED units), frequency, provider, series ID, last updated.
- **FRED metadata sidecar**: `get_fred_meta(series_id)` in `loader.py` reads/writes `fred_{id}_meta.json` (365-day TTL). 76 sidecars backfilled.
- **Dark-theme color palette**: `_lerp_rgb()` + `_CLR_GREEN_LO/HI` + `_CLR_RED_LO/HI` in `shared_components.py`. Replaces `rgba(color, low_alpha)` (invisible on dark) with opaque lerp from light washed-out → vivid saturated. Applied to `_semantic_z_color`, `_momentum_score_color`, `_stress_z_color`, `_sem_z_color`.
- **Signals page composite momentum**: `growth_momentum` + `inflation_momentum` from composites table shown in section headers as `Mom XX%`, color-coded with same semantic palette. Rate/Credit/Vol momentum computed as direction fraction on the fly.
- **ALL import fix**: `ALL` + `PreventUpdate` + `ctx` added to top-level Dash imports in `charting.py`.

## Up next (next session)
| Priority | Item |
|---|---|
| 1 | Phase 2 — Japan (JP): `config/countries/jp_bindings.yaml` + `jp_composites.yaml` |
| 2 | BEA refresh (after 2026-06-26): `python3 -m indicators.pipeline` clears 3 stale US signals |
| 3 | KR monthly CPI: BoK ECOS API (requires registration) is the only remaining free source |

### Signals page — detailed spec

**Route:** `/signals`  
**Nav:** "📡 Signals" link under the existing "Indicators" group in `dashboard/charting.py`  
**File:** `dashboard/signals_page.py` (new)

**Layout:** Five force sections rendered as accordion or stacked cards:
`Growth · Inflation · Interest Rate · Credit · Volatility`

Each section has a **header row** showing:
- Force name
- Composite Z-Score for that force (weighted mean of component Z-scores, same calculation as `composites.py` but read from the `composites` table's `growth_score` / `inflation_score` columns where available; Rate/Credit/Volatility computed on the fly as unweighted mean of their signals' Z-scores)
- Composite Momentum score (mean of `change_1m` direction across signals in the force)

Each section body mirrors `_build_lens_table()` from `charting.py` (lines 401–530):
- Columns: Indicator | Value | Dir | Pct | Z | Quality
- Same colour coding: percentile badges, Z-score colour, direction arrows, stale/proxy badges
- Per-signal sparkline (same approach as existing lens tables)

**Signal sources per force** (use `country-store` to pick country):

| Force | Signals in DB |
|---|---|
| Growth | All signals where `force = 'growth'` for the country (same as existing Regime Map lens tables) |
| Inflation | All signals where `force = 'inflation'` |
| Interest Rate | `us.policy.real_fed_funds`, `us.policy.real_yield_10y`, `us.policy.fed_funds`, `us.policy.yield_2y`, `us.policy.yield_10y` (US); `ez.policy.real_yield_10y`, `ez.policy.yield_10y`, `ez.policy.yield_spread` (EZ); `kr.policy.yield_10y` (KR) — query by `force = 'policy'` and filter to rate/yield signals |
| Credit | `us.premium.credit_spread_corp`, `us.premium.high_yield_spread`, `us.credit.bank_loans`, `us.credit.lending_standards`, `us.credit.household_debt_gdp`, `us.credit.gov_debt_gdp` (US); `ez.credit.*` (EZ); `kr.credit.*` (KR) — query `force IN ('credit', 'premium')` |
| Volatility | VIXCLS (US only, from raw cache via `indicators/regime_classifier._load_vix()`); show "N/A" for EZ/KR |

**Implementation notes:**
- Reuse `_build_lens_table()` from `charting.py` directly — import or extract to a shared helper in `dashboard/shared.py`
- Section header composite Z: for Growth/Inflation read from latest `composites` row for the selected date. For Rate/Credit/Volatility compute `mean(zscore)` across the force's signals (exclude NaN, exclude stale)
- Section header Momentum: `+` if majority of signals have `direction = 'rising'`, `−` if `falling`, `→` if mixed
- Country-aware: responds to `country-store`; date-aware: responds to the same date selector used by Regime Map (or defaults to latest)
- No new DB tables needed — reads from existing `signals` table

## Notes for next session
- **119 signals total** (63 US + 34 EZ + 22 KR)
- EZ now 34 signals: 3 FRED growth (stale/historical), 9 Eurostat, 2 ECB IRS, 3 derived, 1 WB GDP, 1 Eurostat debt, 10 WB structural, 5 FRED monetary/currency
- Per-country composites split: `config/composites_policy.yaml` (global) + `config/countries/{cc}_composites.yaml` (per-country)
- Adding Japan: create `jp_bindings.yaml` + `jp_composites.yaml` in `config/countries/`; pipeline auto-discovers
- EZ: `gov_10dd_edpt1` (annual debt) requires NO `s_adj` dim; `gov_10q_ggnfa` (quarterly fiscal balance) uses `s_adj=NSA`
- Eurostat `bop_c6_q` always 413 even with all dims — too large for JSON API; not usable for EA current account
- ECB SDW IRS flow key format: `FREQ.COUNTRY.MATURITY.RATE_TYPE.ISSUANCE.RATING.CURRENCY.IND.COUNTERPARTY`
- :8502 is primary dashboard (Dash); :8501 is Streamlit reference only

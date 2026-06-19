# Session Checklist — Indicators Machine

## Every Session: Open With

- [ ] Read `CLAUDE.md` (already loaded if this is in context)
- [ ] Read last 3 entries in `worklog.md`
- [ ] Check `docs/decisions/` for any open / pending ADRs
- [ ] Confirm `FRED_API_KEY` is available: `echo $FRED_API_KEY`
- [ ] Confirm Docker is running: `docker info`
- [ ] Know which **phase** is active and what the acceptance gate is

## Every Session: Close With

- [ ] Add a worklog entry: date, what was done, what is next, blockers
- [ ] Mark any completed ADRs as `Status: Accepted`
- [ ] Update this checklist if new blockers/pending items arose
- [ ] **Update `docs/project_plan.md`:** mark newly completed phases in §7, update any `⚠ VERIFY` → `✓` in §4 tables for series confirmed this session, and refresh Appendix A verification lists
- [ ] Update memory if key project facts changed

---

## Open Items / Known Gaps (to resolve before or during Phase 1A)

### G-01: Composite weights not specified in the plan
**Problem:** The spec defines Growth Score and Inflation Score as "weighted indexes" but never states the weights. Without weights the composites cannot be computed.
**Resolution:** ADR-005 — see `docs/decisions/ADR-005-composite-weights.md`.
**Status:** Closed — equal weights are defined in `config/composites.yaml`.

### G-02: PMI proxy definition
**Problem:** `growth.pmi_proxy` uses Philly Fed Manufacturing Survey (`GACDISA066MSFRBPHI`) — a regional US series, not a national PMI.
**Resolution:** ADR-004 — use Philly Fed with `is_proxy=true`; add ISM Manufacturing (`MANEMP` → actually `NAPM`, verify) as a cross-check in Phase 1A.
**Status:** Closed — binding is verified, `is_proxy=true`, and neutral equilibrium is correctly set to 0.

### G-03: WGI governance data lag + API unavailability
**Problem:** World Bank WGI scores (.EST series) are: (a) released with ~1-year lag; and
(b) deleted/archived from the WB v2 indicator API as of 2026-06-18 — confirmed for
PV.EST, CC.EST, GE.EST, RL.EST, RQ.EST.
**Resolution:**
- Deferred slots created in `us_bindings.yaml` with `verified: false`, `source_tier: deferred`.
- Resolution options for Phase 2+: (1) WGI bulk download CSV from World Bank WGI portal
  and load manually; (2) check if WB DataBank API has a separate endpoint.
- Surface data_vintage label + tooltip in dashboard (Phase 1C).
- Log final decision in ADR-006 when building Lens H.
**Status:** API unavailability confirmed. Deferred to Phase 2. ADR-006 pending.

### G-04: Climate lens (Lens I) slot-only
**Problem:** EM-DAT requires manual registration and provides no clean API. The spec says to "build the slot and leave the binding as manual."
**Resolution:** Create the `IndicatorConcept` record with `source_tier="deferred"` and `provider="manual"` from Day 1. Do not let it block anything.
**Status:** Closed — deferred `climate.disaster_loss` manual slot exists in `us_bindings.yaml`.

### G-05: Russia and China coverage gaps
**Problem:** Rosstat/CBR and NBS China are unreliable for automated pulls. WB/IMF harmonized series have gaps, especially post-2022 for Russia.
**Resolution:** Flag with `is_proxy=true` and `low_history=True` as appropriate. Surface coverage gaps in the data-quality log. Do not block Phase 2 on these — roll out Russia and China last.
**Status:** Open — revisit in Phase 2 (Russia/China rollout).

### G-06: ALFRED vintages scope
**Problem:** The spec implies point-in-time vintage backtests, but maintaining full ALFRED history for every series is expensive and complex.
**Resolution:** ADR-003 — defer vintage ingestion to Phase 3. Phase 1 uses `realtime_start=2000-01-01` for initial pull but does not archive rolling vintages.
**Status:** Decided. Close when Phase 3 starts.

### G-08: No testing strategy in the spec
**Problem:** The project plan contains no mention of unit tests, data-validation tests, or integration tests. Without a test harness, ingestion bugs (wrong transforms, silent empty series, wrong Z-score windows) will surface only as bad dashboard output.
**Resolution:** Establish a minimal test layer during Phase 1A scaffold:
- Unit tests for `transform.py` and `normalize.py` (deterministic math — easy to test)
- Data-validation tests: after each ingestion run, assert `len(df) > 0`, value in expected range, no all-NaN columns
- Integration smoke test: `pytest tests/` must pass in the Docker container before Phase 1A acceptance
Use `pytest` + `pytest-cov`. Keep tests under `tests/`. Do not mock the database — use a test DuckDB file in `/tmp`.
**Status:** Closed — unit, loader, normalization, and DuckDB integration coverage is active (79 tests).

### G-09: Phase 1A scope risk
**Problem:** Lenses A–I plus fiscal and demographics = ~45–50 US indicators across 5+ different data providers (FRED, World Bank, IMF, OECD, EIA). Attempting all of them in a single Phase 1A pass is high-risk — one bad provider integration can stall everything.
**Resolution:** Implement Phase 1A in this sub-order:
1. **1A-i:** FRED-only lenses (A, B, C, D, E) — all on a single well-tested provider
2. **1A-ii:** World Bank lenses (F external, G capital/currency, H governance, demographics)
3. **1A-iii:** IMF/OECD lenses (fiscal primary/structural balance)
4. **1A-iv:** Deferred slots (Climate Lens I, deferred-tier items)
Each sub-phase gets its own acceptance check before moving to the next provider. The Phase 1A gate is not passed until all sub-phases are done.
**Status:** Closed — Phase 1A provider sub-phases and deferred slots are complete.

### G-07: `⚠ VERIFY` series IDs must be confirmed before ingestion

**Resolved (Phase 1A-ii, 2026-06-18):**
- ✅ `NE.EXP.GNFS.ZS` — Exports of goods and services (% of GDP)
- ✅ `NE.IMP.GNFS.ZS` — Imports of goods and services (% of GDP)
- ✅ `BX.KLT.DINV.WD.GD.ZS` — FDI net inflows (% of GDP)
- ✅ `PX.REX.REER` — Real effective exchange rate index (2010=100)
- ✅ `SP.POP.GROW` — Population growth (annual %)
- ✅ `SP.URB.TOTL.IN.ZS` — Urban population (% of total)
- ✅ `SL.TLF.CACT.ZS` — Labor force participation rate (ILO modeled)
- ✅ `GC.REV.XGRT.GD.ZS` — Revenue excl. grants (% GDP) — confirmed, reserved for Phase 1A-iii
- ✅ `IEABC` — US current account balance (FRED, quarterly)
- ✅ `IIPUSNETIQ` — Net IIP (FRED, quarterly)
- ✅ `RBUSBIS` — BIS REER for US (FRED, monthly)

**Deferred (WGI API unavailable):**
- ❌ `CC.EST`, `GE.EST`, `RQ.EST`, `PV.EST`, `RL.EST` — WGI governance series deleted/archived
  from WB v2 indicator API (confirmed 2026-06-18). Slots created with `verified: false`,
  `source_tier: deferred`. See G-03 for resolution path.

**Verified in Phase 1A-iii (2026-06-18) — all active series confirmed:**
- ✅ `RTFPNAUSA632NRUG` — TFP (PWT, annual, via FRED)
- ✅ `PPIACO` — Broad PPI all commodities (FRED, monthly)
- ✅ `HDTGPDUSQ163N` — Household debt/GDP (BIS, FRED, quarterly)
- ✅ `BCNSDODNS` — Nonfinancial corporate debt (FRED, quarterly)
- ✅ `FYFSD` — Federal surplus/deficit (FRED, annual)
- ✅ `FYOINT` — Federal interest outlays (FRED, annual)
- ✅ `pb` — IMF primary balance % GDP (Datamapper, 96 obs; replaces `GGXONLB`)
- ✅ `GGCB_G01_PGDP_PT` — IMF structural balance % pot. GDP (Datamapper; replaces `GGSB`)
- ✅ `GC.REV.XGRT.GD.ZS` — WB govt revenue % GDP (bound)

**Status:** ✅ CLOSED. No unresolved ⚠ VERIFY items remain in active config. Phase 2 per-country bindings are the next scope.

### G-10: HY spread (BAMLH0A0HYM2) truncated to 2023 on FRED
**Problem:** ICE/BofA data-licensing change truncated all ICE BofA series on FRED to start 2023-06-19. `premium.high_yield_spread` therefore only has ~787 days of history. Z-score and percentile are relative to a 3-year window — historically misleading (current spreads look "very tight" vs 3 years but the full ICE history shows this is less extreme).
**Resolution:** 
- Long-history credit premium is covered by `premium.credit_spread_corp` (BAA10Y, since 1986) — this is the primary indicator.
- BAMLH0A0HYM2 is kept for current-readings but its Z-score/percentile must be interpreted with caution.
- Phase 1C dashboard: add a tooltip/badge on this signal noting "Z-score vs 3yr window only (FRED data truncated 2023)".
- Future: explore direct ICE BofA API or alternative proxy (DBAA-DAAA quality spread as HY proxy).
**Status:** Open — document in dashboard when Lens E is built.

---

## Acceptance Gates (do not advance phase without passing)

### Phase 1A gate
- [x] All `⚠ VERIFY` IDs confirmed; no unresolved `⚠` in active config
- [x] No active series returns empty / all-null data
- [x] Every series passes sanity range check (or is human-reviewed and logged)
- [x] `vintage_available` is set truthfully for every series
- [x] Deferred-tier items exist as slots with `source_tier="deferred"`, not as active ingestion
- [x] `docker compose up` runs ingestion successfully

### Phase 1B gate
- [ ] Multi-year Growth Score, Inflation Score, Quadrant, and Disequilibrium Score time series in DB
- [ ] Quadrant labels match known historical regimes (spot-check: 2022 should show Stagflation)

### Phase 1C gate
- [ ] `docker compose up` → dashboard renders without error
- [ ] Heat colors are driven by percentile, not raw values
- [ ] Data-quality badges (`is_proxy`, `is_stale`, `vintage_available=false`, `low_history`) visible
- [ ] Manual refresh runs without crashing

### Phase 2 gate (per country)
- [ ] All bindings verified against provider
- [ ] 3–5 recent values spot-checked vs. public reference
- [ ] `vintage_available` set correctly (almost always `false` for non-US)
- [ ] Human sign-off before merging country

### Phase 3 gate
- [ ] 1970s stagflation → Stagflation quadrant (as-of data only, no look-ahead)
- [ ] 2008 GFC → Debt Stress / Crisis quadrant
- [ ] 2020 COVID → Growth Collapse → Reflation transition visible

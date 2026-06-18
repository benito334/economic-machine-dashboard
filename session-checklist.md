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
- [ ] Update memory if key project facts changed

---

## Open Items / Known Gaps (to resolve before or during Phase 1A)

### G-01: Composite weights not specified in the plan
**Problem:** The spec defines Growth Score and Inflation Score as "weighted indexes" but never states the weights. Without weights the composites cannot be computed.
**Resolution:** ADR-005 — see `docs/decisions/ADR-005-composite-weights.md`.
**Status:** Decided (equal weights, overridable in config). Close when `composites.yaml` is written.

### G-02: PMI proxy definition
**Problem:** `growth.pmi_proxy` uses Philly Fed Manufacturing Survey (`GACDISA066MSFRBPHI`) — a regional US series, not a national PMI.
**Resolution:** ADR-004 — use Philly Fed with `is_proxy=true`; add ISM Manufacturing (`MANEMP` → actually `NAPM`, verify) as a cross-check in Phase 1A.
**Status:** Decided. Close when binding is confirmed and `is_proxy=true` is set.

### G-03: WGI governance data lag
**Problem:** World Bank WGI scores are released with ~1-year lag (e.g., 2024 estimates released late 2025). The "Geopolitical-Risk Overlay" in the dashboard will show stale data by design.
**Resolution:** Surface this explicitly in the dashboard with a `data_vintage` label and tooltip. Do not pretend the score is current. Log decision in ADR-006.
**Status:** Open — create ADR-006 when building Lens H.

### G-04: Climate lens (Lens I) slot-only
**Problem:** EM-DAT requires manual registration and provides no clean API. The spec says to "build the slot and leave the binding as manual."
**Resolution:** Create the `IndicatorConcept` record with `source_tier="deferred"` and `provider="manual"` from Day 1. Do not let it block anything.
**Status:** Open — close when slot is created in `us_bindings.yaml`.

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
**Status:** Open — add `tests/` scaffold at Phase 1A kickoff.

### G-09: Phase 1A scope risk
**Problem:** Lenses A–I plus fiscal and demographics = ~45–50 US indicators across 5+ different data providers (FRED, World Bank, IMF, OECD, EIA). Attempting all of them in a single Phase 1A pass is high-risk — one bad provider integration can stall everything.
**Resolution:** Implement Phase 1A in this sub-order:
1. **1A-i:** FRED-only lenses (A, B, C, D, E) — all on a single well-tested provider
2. **1A-ii:** World Bank lenses (F external, G capital/currency, H governance, demographics)
3. **1A-iii:** IMF/OECD lenses (fiscal primary/structural balance)
4. **1A-iv:** Deferred slots (Climate Lens I, deferred-tier items)
Each sub-phase gets its own acceptance check before moving to the next provider. The Phase 1A gate is not passed until all sub-phases are done.
**Status:** Open — enforce sub-order at Phase 1A kickoff.

### G-07: `⚠ VERIFY` series IDs must be confirmed before ingestion
The following IDs from the spec are unconfirmed and must be resolved before ingestion:
- `RTFPNAUSA632NRUG` (TFP, Penn World Table)
- `PPIACO` (broad PPI commodities)
- `HDTGPDUSQ163N` (BIS household debt/GDP)
- `BCNSDODNS` (nonfin corporate debt)
- `NE.EXP.GNFS.ZS`, `NE.IMP.GNFS.ZS` (WB exports/imports % GDP)
- `BX.KLT.DINV.WD.GD.ZS` (WB FDI net inflows % GDP)
- `PX.REX.REER` (WB fallback REER)
- `CC.EST`, `GE.EST`, `RQ.EST` (WGI governance)
- `FYFSD`, `FYOINT` (US fiscal primary balance)
- `GGXONLB`, `GGSB` (IMF WEO fiscal)
- `GC.REV.XGRT.GD.ZS` (WB revenue % GDP)
- `SP.POP.GROW`, `SP.URB.TOTL.IN.ZS`, `SL.TLF.CACT.ZS` (WB demographics)

**Protocol:** Call provider search API first; write confirmed ID + title to binding config before ingesting. Halt if result is empty.
**Status:** Open — close as each ID is verified during Phase 1A.

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
- [ ] All `⚠ VERIFY` IDs confirmed; no unresolved `⚠` in active config
- [ ] No active series returns empty / all-null data
- [ ] Every series passes sanity range check (or is human-reviewed and logged)
- [ ] `vintage_available` is set truthfully for every series
- [ ] Deferred-tier items exist as slots with `source_tier="deferred"`, not as active ingestion
- [ ] `docker compose up` runs ingestion successfully

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

# Worklog — Indicators Machine

Log entries are newest-first. Each entry: date, what was done, what is next, any blockers.

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

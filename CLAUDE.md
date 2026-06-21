# Indicators Machine — CLAUDE.md

> Read this file at the **start of every session** before touching any code. It is the authoritative guide for this project. When in conflict with other sources, this file wins.

---

## What This Project Is

A **diagnostic, cross-country macro-regime dashboard** in the Ray Dalio "Economic Machine" tradition. It ingests macroeconomic data from free/open APIs, normalizes it into a standardized `Signal` contract, classifies each economy into one of four macro seasons (Expansion, Inflationary Boom, Disinflationary Slowdown, Stagflation), and presents a multi-panel diagnostic terminal.

**This is a diagnostic tool, not an allocator.** No portfolio construction, risk-parity weights, or trade recommendations are produced here. Those belong to the separate Allocation Layer project.

Full specification: [docs/project_plan.md](docs/project_plan.md)

---

## Locked-In Paths

| Purpose | Path |
| :--- | :--- |
| Project root | `/mnt/data/projects/all_weather/indicators_machine/` |
| Data / cache | `/mnt/data/project_data/all_weather/indicators_machine/` |
| Database | `/mnt/data/db/all_weather/indicators_machine/` |
| Main DB file | `/mnt/data/db/all_weather/indicators_machine/signals.duckdb` |
| Raw API cache | `/mnt/data/project_data/all_weather/indicators_machine/raw_cache/` |
| Parquet snapshots | `/mnt/data/project_data/all_weather/indicators_machine/snapshots/` |

**Never change these paths.** All code must read them from config/env vars, not hardcode strings.

---

## Non-Negotiable Build Rules

### 1. Dockerize everything
- Every runnable component (ingestion pipeline, scheduler, Streamlit dashboard) must have a `Dockerfile` or be a service in `docker-compose.yml`.
- Local dev is fine in a venv, but the acceptance test for any phase is `docker compose up`.
- Use bind mounts for the data/db paths above — do not bake data into images.

### 2. Use existing packages before building from scratch
Before writing any utility from scratch, check whether it is already available in:
`fredapi`, `wbgapi`, `sdmx`, `imfp`, `duckdb`, `pandas`, `numpy`, `scipy`, `streamlit`, `plotly`, `APScheduler`, `pydantic`, `requests`, `tenacity`, `python-dotenv`

Only write custom code when a package genuinely cannot do the job.

### 3. Never hardcode secrets
API keys (`FRED_API_KEY`, `EIA_API_KEY`) are read from a `.env` file / environment variables only. The code must fail loudly with a clear error if a required key is missing — never substitute stub data silently.

### 4. Never invent or assume series IDs
Every `⚠ VERIFY` ID in the spec must be confirmed via the provider's search/metadata endpoint before first ingestion. Confirmed IDs and their human-readable titles must be written back to the binding config. An empty/all-null result from ingestion is a **failure**, not a success.

### 5. Cache raw API responses on first pull
Cache to `raw_cache/` (DuckDB or parquet) on first successful pull. Develop against the cache. This keeps iteration fast and protects rate-limited APIs.

### 6. Make ingestion idempotent
Upsert on `(id, as_of)`. Re-running the pipeline must not duplicate rows.

### 7. Never forward-fill past a release cycle without setting `is_stale=true`
Preserve native frequency for statistics. Set `is_stale=true` when a series has not updated within its expected release window.

### 8. `vintage_available=true` only where point-in-time data genuinely exists
Currently: US series via FRED API only. All other countries use latest-revised data and must set `vintage_available=false`.

---

## Stack

| Layer | Technology |
| :--- | :--- |
| Language | Python 3.11+ |
| Data — FRED | `fredapi` + REST `api.stlouisfed.org/fred` |
| Data — World Bank | `wbgapi` + REST `/v2/...` |
| Data — IMF | `imfp` or SDMX `sdmx` |
| Data — OECD / ECB | SDMX REST |
| Store | DuckDB |
| Data manipulation | Pandas, NumPy, SciPy |
| Dashboard | Streamlit + Plotly |
| Scheduling | APScheduler |
| Container | Docker + docker-compose |
| Config | YAML + Pydantic models |
| Secrets | `python-dotenv` (`.env` file, never committed) |
| Retry / resilience | `tenacity` |

---

## Current Status

**As of 2026-06-21:** Phases 1A + 1B + 1C + 1D + 1E + 1F + 1G + 1H complete and verified. **319 tests pass.** :8502 Dash UI restructured with left-sidebar navigation and full Regime Map panel set.

| Sub-phase | Status | Notes |
| :--- | :--- | :--- |
| 1A-i FRED lenses A–E + Master | ✅ **Done** | 37/37 signals live in DuckDB, 51 tests pass |
| 1A-ii World Bank lenses F/G/H/demo | ✅ **Done** | 50/50 signals live, 60 tests pass; WGI API unavailable — slots deferred |
| 1A-iii IMF/OECD fiscal lenses | ✅ **Done** | 59/59 signals live, 91 tests pass; deferred climate/governance slots present |
| 1B Composites engine | ✅ **Done** | 558 monthly snapshots; Growth/Inflation scores, Regime Quadrant, Confidence, Disequilibrium |
| 1C Streamlit dashboard | ✅ **Done** | HUD (+ Debt Stress gauge), 4-quadrant scatter + 12-month trail, accordions A–I, badges, sparklines, conflict panel; 225 tests pass |
| 1D Dash charting view | ✅ **Done** | Plotly Dash on :8502; left-sidebar nav (Data / Indicators groups); Chart Overlay, Yield Curve, Regime Map, Regime History, Debt Stress, Data Explorer |
| 1E Data Explorer | ✅ **Done** | Signal browser, time series + Z-score chart, observations table, gap detection, raw vs processed compare, spot-check |
| 1F Long-Term Debt Stress | ✅ **Done** | 7-component Z-score composite; point-in-time exponential staleness decay; `debt_stress_snapshots` table; pipeline Pass 6; HUD gauge + Dash tab |
| 1G Methodology improvements | ✅ **Done** | C1 (±4σ cap), E1 (variance direction), G1 (labour weights), H1/H2 (breakeven/oil), L1–L4 (regime staleness decay + carry caps + stale-lag badges), D1 (momentum percentile), B1 (period audit), A2/I2 (composite PCA); 319 tests pass |
| 1H TradingView system | ✅ **Done** | FastAPI :8004 + nginx :8503 (ADR-007 Option B); 4-tab SPA: Charts, Macro Table, Regime step controls, Yield Curve |
| 1I :8502 UI consolidation | 🔄 **In progress** | Left-sidebar nav done; Regime Map panels done; methodology guide + remaining :8501 content pending |
| 2 Country rollout | ⬜ Queued | Eurozone first — unblocked |
| 3 Back-test / regime replay | ⬜ Pending | FRED vintages |

**To start the next session:** Continue :8502 UI work per user direction. Also run `python3 -m indicators.pipeline --latest` after June 26 to pick up BEA Q1 2026 data (will clear 3 stale signals).

**:8502 Dash nav structure (as of 2026-06-21):**
- Left sidebar: persistent vertical pill nav — Data group (Chart Overlay `/charts`, Data Explorer `/explorer`) + Indicators group (Yield Curve `/yield-curve`, Regime Map `/regime-map`, Regime History `/regime-history`, Debt Stress `/debt-stress`)
- Regime Map page: scatter (55vh, data-driven zoom with 15% buffer) + What Changed + Conflicts + Signal Drill-Downs (10 lens accordions) + Data-Quality Log
- Browser back/forward supported via `dcc.Location`; `page-trigger` store guarantees callback ordering

---

## Phase Map

### Phase 1A-i — FRED-only lenses A–E + Master ✅ COMPLETE (2026-06-18)
- DuckDB schema, `Signal` contract, Pydantic models
- `fredapi` loader with parquet cache + tenacity retry
- Transform, normalize, momentum, equilibrium-distance, staleness
- 29 FRED series + 4 derived (lenses A–E + Master); 37/37 signals verified live
- 51 unit + integration tests passing
- Known: Philly Fed PMI series ID corrected; ICE BofA HY spread truncated to 2023 (G-10)

### Phase 1A-ii — World Bank lenses ✅ COMPLETE (2026-06-18)
- `fetch_wb_series()` added to `loader.py` via direct REST API (not `wbgapi` — JSON-decoding issues in this env)
- 13 new bindings: Lens F (external/trade), Lens G (capital/currency), Lens A R&D, Demographics
- Lens H (governance): 5 WGI deferred slots — `.EST` series deleted/archived from WB v2 API
- Pipeline Pass 2 (WorldBank) + Pass 3 (derived); 60/60 tests; 50/50 signals live

### Phase 1A-iii — IMF/OECD fiscal lenses ✅ COMPLETE (2026-06-18)
- `fetch_imf_series()` added to `loader.py` using IMF Datamapper REST API (no auth, ISO-3 country codes, forecast-year filter)
- 9 new active bindings: TFP (RTFPNAUSA632NRUG), PPI broad (PPIACO), household debt/GDP (HDTGPDUSQ163N), corporate debt (BCNSDODNS), federal deficit (FYFSD), interest payments (FYOINT), govt revenue % GDP (WB), IMF primary balance (`pb`), IMF structural balance (`GGCB_G01_PGDP_PT`); deferred climate slot added
- Pass 3 (IMF) + Pass 4 (derived) in pipeline; 79/79 tests; 59/59 signals live
- All ⚠ VERIFY items in active config resolved; no empty results; 0 sanity warnings
- IMF current-year estimates and future forecasts are excluded from observation signals

### Phase 1B — Composites & Snapshot Engine ✅ COMPLETE (2026-06-18)
- `indicators/composites.py`: Growth Score + Inflation Score (weighted Z-score composites per `composites.yaml`), Regime Quadrant (4-season), Confidence (direction-agreement fraction), Disequilibrium Score (mean absolute standardized distance from declared equilibrium across 5 force groups)
- `indicators/models.py`: `CompositeSnapshot` Pydantic model
- `store/store.py`: `composites` table, `upsert_composites()`, `query_composite_history()`
- `pipeline.py`: Pass 5 — runs composites engine, upserts to DB
- 558 monthly US composite snapshots stored; 91 tests passing
- Historical narrative: COVID-2020 Disinflationary Slowdown → 2021 Inflationary Boom → 2022 Inflationary Boom (employment Z-scores strongly positive; spec's "2022 = Stagflation" assumption was imprecise — Stagflation label correctly appears from Mar 2023 when growth Z-scores turn negative) → 2023–2026 Stagflation
- Current (Jun 2026): Stagflation — Growth=−0.048 / Inflation=+0.428 / Confidence=48% / Disequilibrium=0.702; 8/8 inflation signals active

### Phase 1C — Streamlit Dashboard (US proof) ✅ COMPLETE (2026-06-18)
- `dashboard/app.py` full rewrite: HUD (Regime Quadrant · Confidence · Momentum arrows · Disequilibrium), 4-quadrant Plotly scatter with 12-month connected trail, What Changed feed (top-8 Z-score movers), Cross-Signal Conflict Panel, Geopolitical-Risk Overlay placeholder (WGI deferred)
- Accordion drill-downs for all 10 lens groups; per-signal rows with SVG sparklines, percentile color badges, Z-score, direction arrow, quality badges, causal-linkage tooltips
- `tests/test_dashboard.py`: 39 tests (35 unit, 4 integration); total suite 131/131 passing
- `INDICATORS_TESTING=1` env guard prevents `main()` from executing on import in tests
- Docker acceptance gate: `docker compose up dashboard` → port :8501 serves HTML; pipeline exits 0
- Geopolitical-Risk Overlay (WGI / Lens H): shows deferred placeholder with link to G-03 resolution path
- **All HTML rendering uses `st.html()`** — Streamlit 1.39+ silently ignores `unsafe_allow_html=True` in `st.markdown()`; `st.html()` is the correct API for raw HTML blocks in any future dashboard work

### Phase 1D — Dash Charting View ✅ COMPLETE (2026-06-19)
- `dashboard/charting.py`: Plotly Dash app on port :8502; 3-tab layout (Chart Overlay, Yield Curve, Regime History)
- `dashboard/charting_data.py`: DuckDB query helpers; parquet cache-first for FRED yield maturities
- `config/chart_series.yaml`: 50-series catalog (9 groups) + 6 yield curve maturities (3M/1Y/2Y/5Y/10Y/30Y)
- Series selector sidebar (`dcc.Checklist` grouped by lens); multi-pane subplot builder; shared X-axis; independent Y-axes; `hovermode="x unified"`
- Time-horizon presets (1Y/3Y/5Y/10Y/MAX) + range slider shared above all tabs
- Yield Curve tab: full term structure at selectable date + optional comparison date + historical 10Y-2Y spread bar chart
- `dashboard/charting_lc/`: Option B skeleton (FastAPI + TradingView Lightweight Charts) committed, deferred
- 156/156 tests passing; Docker acceptance gate `:8502` HTTP 200

### Phase 1E — Data Explorer ✅ COMPLETE (2026-06-19)
- `dashboard/explorer_data.py`: signal overview query (59 signals, latest snapshot + obs count + freq label + quality flags), full history loader, gap detector (flags gaps >2× expected release cycle), raw-cache vs processed comparator (parquet → DB delta), anomaly flag (|Z|>3), descriptive stats per signal
- `dashboard/explorer.py`: layout + 8 callbacks; signal browser DataTable (filter by force/flags, sortable); 4-subtab detail panel:
  - **Time Series**: dual-pane chart (raw value + Z-score), equilibrium reference line, stale-point markers, ±2/3σ bands, 6 stat cards, reference spot-check input (enter value from provider → shows DB delta + %)
  - **Observations**: full paginated table with anomaly/stale row highlighting, CSV download
  - **Quality & Gaps**: metadata card, quality flag badges (green/red), gap detection table
  - **Raw vs Processed**: parquet cache value vs DB processed value side by side; delta/% columns; rows with |Δ%|>5% highlighted
- Wired as "🔬 Data Explorer" tab in `dashboard/charting.py`
- 31 original feature tests; 203/203 repository tests passing after code-review regressions; Docker :8502 healthy

### Phase 1F — Long-Term Debt Stress Indicator ✅ COMPLETE (2026-06-19)
- `config/longterm_stress.yaml`: all tunable parameters (weights, rolling windows, coverage threshold, bands, staleness) annotated with `# TUNABLE` — no values buried in code; `staleness:` section with `stale_weight_halflife`, `stale_min_weight_fraction`, `max_carry_quarters`, `extrapolation` gate
- `indicators/longterm_stress.py`: 7-component weighted Z-score composite; rolling Z at quarterly (window=40) or annual (window=10); shift(1) statistical look-ahead protection; unit-safe derived ratios; point-in-time source dates; **Gap 1**: exponential half-life decay by excess staleness lag; **Gap 2**: carry-forward limit + YAML-gated model-based extrapolation (`_extrapolate_z_score`); **Gap 3**: structured stale strings `"cid:lag_q"` + `extrapolated_components` field
- `indicators/models.py`: `DebtStressSnapshot` with `stale_components` (`"cid:lag_q"` format) + `extrapolated_components`
- `store/store.py`: `debt_stress_snapshots` table + `upsert_debt_stress()` + `query_debt_stress_history()`; migration adds `extrapolated_components` column
- `indicators/pipeline.py`: Pass 6 — 185 quarterly snapshots; latest (2026-Q1): stress=+0.488, 5/7 components, retained=72.7%
- `dashboard/charting_data.py`: `load_debt_stress_history()` + `load_debt_stress_component_dates()` (queries signals table for last `as_of` per underlying signal)
- `dashboard/app.py`: HUD Debt Stress cell with stale/extrap badges; `_parse_stale_components()` handles `"cid:lag_q"` and legacy plain-`"cid"` format
- `dashboard/charting.py`: "📉 Debt Stress" tab — **full-width** component table (freq, config wt, eff wt post-decay, last data date, Z-score bar, status/reason); `BLANK` rows explain carry expiry + last known value; chart pushed below; `_parse_stress_components()` + `_fmt_period()` + `_carry_expires()` helpers
- `tests/test_longterm_stress.py`: 42 tests covering staleness gaps 1–3, statistical look-ahead, sign convention, coverage, unit conversion, band labels, config integrity, and country guards; 249/249 repository tests passing

### Phase 2 — Country Rollout (one at a time)
Order: Eurozone → Japan → UK → South Korea → China → India → Brazil → Saudi Arabia → Russia.
Each country requires: binding instantiation → series verification → spot-check vs. public reference → `vintage_available` set honestly → human sign-off.

### Phase 3 — Back-Test / Regime Replay
Replay named scenarios (1970s stagflation, 2008 GFC, 2020 COVID) using FRED vintages. Confirm quadrant classifier lands in expected season with no look-ahead bias.

---

## Signal Contract (canonical shape)

```python
Signal = {
  "id": "us.inflation.core_pce",       # country.force.concept
  "country": "US",
  "force": "inflation",
  "lead_lag": "coincident",
  "as_of": "2026-05-31",
  "value": 0.031,
  "units": "yoy_pct",
  "level_percentile": 0.78,
  "zscore": 0.9,
  "change_1m": 0.001,
  "change_3m": -0.002,
  "change_12m": -0.015,
  "direction": "falling",
  "equilibrium_estimate": 0.02,
  "distance_from_equilibrium": 0.011,
  "surprise": None,
  "is_constructed": False,
  "is_proxy": False,
  "is_stale": False,
  "low_history": False,
  "provider": "FRED",
  "source_tier": "free",
  "vintage_available": True,
  "linkage": "Core PCE persistence drives Fed reaction and the discount rate",
  "source": "FRED:PCEPILFE"
}
```

---

## Session Protocol

At session start:
1. Run `cat CLAUDE.md` (this file) — done if already loaded.
2. Read the last 3 entries in `worklog.md`.
3. Check `session-checklist.md` for any pending items.
4. Check `docs/decisions/` for any open ADRs.

At session end:
1. Add a worklog entry (date, what was done, what is next).
2. Update `session-checklist.md` if any new blockers or pending items arose.
3. Update memory if any key facts changed.

---

## Key Source Paths in the Codebase (once built)

```
indicators_machine/
├── CLAUDE.md                  ← this file
├── worklog.md
├── session-checklist.md
├── docker-compose.yml
├── Dockerfile
├── .env.example               ← committed; .env is gitignored
├── requirements.txt
├── config/
│   ├── us_bindings.yaml       ← US CountryBindings (lenses A–I + fiscal + demo)
│   ├── composites.yaml        ← composite weights + equilibrium constants
│   └── countries/             ← per-country binding files (added in Phase 2)
├── indicators/
│   ├── models.py              ← IndicatorConcept, CountryBinding, Signal (Pydantic)
│   ├── loader.py              ← FRED / WB / IMF / OECD fetchers + cache layer
│   ├── transform.py           ← YoY, level, spread transformations
│   ├── normalize.py           ← Z-score, percentile, momentum, equilibrium distance
│   ├── composites.py          ← Growth Score, Inflation Score, Quadrant, Disequilibrium
│   └── pipeline.py            ← orchestration entry point
├── store/
│   └── store.py               ← DuckDB read/write; schema migration
├── dashboard/
│   └── app.py                 ← Streamlit entry point
└── docs/
    ├── project_plan.md        ← master spec (do not edit)
    └── decisions/             ← ADRs
```

---

## Deferred / Out of Scope (do not build)

- Risk-parity weighting, volatility estimation, correlation matrices, portfolio construction → **Allocation Layer project**
- EIU / ICRG political-risk scores → use WB WGI as live substitute
- EM-DAT disaster losses (Lens I) → build slot + deferred binding only
- SWF holdings → deferred
- CEIC / Bloomberg / Refinitiv → only if a license is provided
- NBS China automated pull → use WB/IMF harmonized for now
- Russia Rosstat/CBR automated → use WB/IMF harmonized; flag gaps

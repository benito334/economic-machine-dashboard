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

**As of 2026-06-18:** Phase 1A + 1B complete and verified.

| Sub-phase | Status | Notes |
| :--- | :--- | :--- |
| 1A-i FRED lenses A–E + Master | ✅ **Done** | 37/37 signals live in DuckDB, 51 tests pass |
| 1A-ii World Bank lenses F/G/H/demo | ✅ **Done** | 50/50 signals live, 60 tests pass; WGI API unavailable — slots deferred |
| 1A-iii IMF/OECD fiscal lenses | ✅ **Done** | 59/59 signals live, 91 tests pass; deferred climate/governance slots present |
| 1B Composites engine | ✅ **Done** | 558 monthly snapshots; Growth/Inflation scores, Regime Quadrant, Confidence, Disequilibrium |
| 1C Streamlit dashboard | ⬜ **Next** | 4-quadrant scatter, HUD, accordion lenses A–I |
| 2 Country rollout | ⬜ Pending | Eurozone first |
| 3 Back-test / regime replay | ⬜ Pending | FRED vintages |

**To start the next session:** `python3 -m indicators.pipeline --latest` to inspect current signals, then proceed with Phase 1C (Streamlit dashboard).

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
- `indicators/composites.py`: Growth Score + Inflation Score (weighted Z-score composites per `composites.yaml`), Regime Quadrant (4-season), Confidence (direction-agreement fraction), Disequilibrium Score (mean |Z-score| across 5 force groups)
- `indicators/models.py`: `CompositeSnapshot` Pydantic model
- `store/store.py`: `composites` table, `upsert_composites()`, `query_composite_history()`
- `pipeline.py`: Pass 5 — runs composites engine, upserts to DB
- 558 monthly US composite snapshots stored; 91 tests passing
- Historical narrative: COVID-2020 Disinflationary Slowdown → 2021 Inflationary Boom → 2022 Inflationary Boom (employment Z-scores strongly positive; spec's "2022 = Stagflation" assumption was imprecise — Stagflation label correctly appears from Mar 2023 when growth Z-scores turn negative) → 2023–2026 Stagflation
- Current (Jun 2026): Stagflation — Growth=−0.05 / Inflation=+0.31 / Confidence=45%

### Phase 1C — Streamlit Dashboard (US proof)
1. Build the §5.1 grid: HUD, 4-quadrant Plotly scatter with 12-month tail, accordions A–I.
2. Percentile color badges, data-quality badges, causal-linkage tooltips, Geopolitical-Risk Overlay.
3. "What Changed This Week/Quarter" feed, Cross-Signal Conflict Panel.
4. **Acceptance gate:** `docker compose up` → dashboard renders, queries DuckDB, color is driven by percentile, manual refresh works.

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

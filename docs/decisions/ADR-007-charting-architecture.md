# ADR-007 — Interactive Charting Architecture

**Date:** 2026-06-18  
**Status:** Decided — Phase 1D implements Option A (Dash); Option B (Lightweight Charts) deferred

---

## Context

Phase 1C delivered a Streamlit diagnostic dashboard suited for regime-level inspection.
The next requirement is an **interactive historical charting view**: the user wants to select
arbitrary combinations of macro series (GDP growth, rates, inflation, jobless rate, govt budget,
debt/GDP, current account, yield curve) on adjustable time horizons, overlay multiple series on
a single chart, and drill into the yield curve in detail — similar to the TradingView UX.

Streamlit's execution model (full-script re-run on every widget change) is not well-suited to
this interaction pattern. Three options were evaluated.

---

## Options Considered

### Option A — Plotly Dash ✅ SELECTED for Phase 1D

Replace the charting view with a Dash app (Plotly's own framework).

- **Reactivity:** True callback model — chart updates instantly on widget change, no page reload.
- **Layout:** `dash-bootstrap-components` or `dbc.Row`/`dbc.Col` for responsive panel layout.
- **Charts:** `dcc.Graph` with Plotly figures — `make_subplots(shared_xaxes=True)` for multi-pane
  linked views; `dcc.RangeSlider` for time-horizon selection.
- **Data:** Same DuckDB backend; Flask (Dash's WSGI layer) serves data from DB on callback.
- **Docker:** New service `charting` in `docker-compose.yml` on port `:8502`; existing Streamlit
  regime dashboard stays on `:8501`.
- **Multi-country:** When Phase 2 delivers Eurozone bindings, a `dcc.Dropdown` for country
  selection and a secondary series selector enable country overlays naturally.

**Implementation plan (Phase 1D):**
1. `dashboard/charting.py` — Dash app entry point
2. `dashboard/charting_data.py` — DuckDB query helpers (cached with `diskcache` or `functools`)
3. `config/chart_series.yaml` — human-readable series catalog (label, signal ID, units, default pane)
4. Update `docker-compose.yml` — add `charting` service
5. Series selector sidebar with `dcc.Checklist` grouped by lens
6. Multi-pane Plotly figure builder: each "pane" is a subplot row with independent Y-axis
7. Time-horizon controls: preset buttons (1Y, 3Y, 5Y, 10Y, MAX) + custom range slider
8. Yield curve pane: special plot type showing the term structure at a selected date with a
   date slider for animation
9. Hover crosshair linked across all panes via `hovermode="x unified"`

### Option B — FastAPI + TradingView Lightweight Charts (deferred)

TradingView's open-source [Lightweight Charts](https://tradingview.github.io/lightweight-charts/)
library provides the exact TradingView UX (smooth canvas zoom/pan, native crosshair, pane
management, volume bars, time-scale synchronisation).

Architecture:
- `api/main.py` — FastAPI app; endpoints return DuckDB query results as JSON
- `frontend/` — minimal HTML/JS using Lightweight Charts v4
- `docker-compose.yml` — `api` service (:8000) + `frontend` served by nginx (:8503)

**Why deferred:** Requires JavaScript frontend work. The Dash implementation delivers ~90% of
the needed UX entirely in Python, which is the right tradeoff for the current project phase.
Option B remains valid if the project matures into a product shown to external users where UX
polish justifies the additional complexity.

**Skeleton preserved at:** `dashboard/charting_lc/` — stub files created in Phase 1D to document
the integration pattern so Option B can be picked up without re-researching.

### Option C — Streamlit tabs + Plotly configurator (rejected)

A sidebar multiselect + `make_subplots` within the existing Streamlit app. Delivers ~70% of
the needed UX but the full-page-rerun model makes the series picker feel sluggish. Rejected
in favour of Dash.

---

## Decision

**Phase 1D implements Option A (Dash).** The Streamlit regime dashboard remains the primary
entry point on `:8501`; the Dash charting view lives on `:8502` as a second service.

Option B skeleton is committed in Phase 1D so it can be activated later without rework.

---

## Consequences

- `requirements.txt` gains: `dash`, `dash-bootstrap-components`, `diskcache`
- `docker-compose.yml` gains a `charting` service
- A `config/chart_series.yaml` catalog maps signal IDs → human-readable chart labels
- The Streamlit dashboard is **not** replaced — both tools coexist
- Phase 2 (Eurozone) must be complete before country-overlay in the charting view is meaningful
